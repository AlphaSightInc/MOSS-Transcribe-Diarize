#!/usr/bin/env bash
# Ralph AFK loop engine.
#
# Project-agnostic by design: everything the agent should DO lives in the
# markdown files next to this script. The engine only iterates, injects run
# facts into the prompt, records telemetry, checkpoints git state, and stops
# on completion, stall, stop request, or budget exhaustion.
#
#   prompt.md    - per-iteration procedure (static; {{ITERATION}} {{BUDGET}} {{DIR}} substituted)
#   prd.md       - goal, acceptance bar, constraints (write-once)
#   context.md   - current evidence + candidate work (living; agents update it)
#   progress.txt - append-only journal (agents append; engine adds [loop] markers)
#
# Usage:
#   ./ralph-afk.sh [iterations]          # default 30
#   RALPH_DRY_RUN=1 ./ralph-afk.sh 1     # validate setup and preview the prompt
#
# Agent selection:
#   RALPH_AGENT=auto|claude|codex        # default auto (claude first, then codex)
#   RALPH_AGENT_CMD='...'                # full custom command; prompt is appended as one argv
#   RALPH_MODEL=sonnet                   # claude model
#   RALPH_CODEX_MODEL=gpt-5.5            # codex model
#   RALPH_CODEX_REASONING_EFFORT=high    # codex reasoning effort
#
# Behavior:
#   RALPH_COMMIT_SCOPE='src docs'        # limit checkpoint commits (default: all changes)
#   RALPH_SLEEP_SECONDS=2                # pause between iterations
#   RALPH_MAX_STALLS=3                   # stop after N consecutive iterations with no new
#                                        # commit, agent failures included (0 disables)
#   RALPH_FAIL_BACKOFF_SECONDS=30        # after a failed agent run, wait 30s/60s/90s...
#                                        # (x consecutive failures, capped at 10x; 0 disables)
#   RALPH_PREFLIGHT_CMD='curl ...'       # run before each iteration; status injected into prompt
#   RALPH_PREFLIGHT_REQUIRED=0           # 1 = stop the loop when preflight fails
#   RALPH_ALLOW_PLACEHOLDERS=0           # 1 = template smoke tests only
#   RALPH_ALLOW_DIRTY=0                  # 1 = explicitly permit a dirty launch
#   RALPH_EXPECTED_BRANCH=name           # optional launch-time branch fence
#   RALPH_REQUIRED_ANCESTOR=sha          # optional launch-time ancestry fence
#
# Stop controls:
#   touch <this dir>/.stop               # graceful stop after the current iteration
#   INT/TERM to the launcher             # same
#
# Exit codes: 0 complete/stopped, 1 error, 2 blocked/stalled/incomplete budget.

set -uo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

command -v git >/dev/null 2>&1 || fail "git is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)" \
  || fail "not inside a git worktree: $SCRIPT_DIR"
REL_DIR="$(git -C "$SCRIPT_DIR" rev-parse --show-prefix)"
REL_DIR="${REL_DIR%/}"
[[ -n "$REL_DIR" ]] || REL_DIR="."

ITERATIONS="${1:-30}"
[[ "$ITERATIONS" =~ ^[1-9][0-9]*$ ]] || fail "iterations must be a positive integer"

PROMPT_FILE="$SCRIPT_DIR/prompt.md"
PRD_FILE="$SCRIPT_DIR/prd.md"
CONTEXT_FILE="$SCRIPT_DIR/context.md"
PROGRESS_FILE="$SCRIPT_DIR/progress.txt"
STOP_FILE="$SCRIPT_DIR/.stop"
LOCK_DIR="$SCRIPT_DIR/.lock"
TELEMETRY_DIR="$SCRIPT_DIR/telemetry"
RUN_ID="$(date -u +%Y%m%d-%H%M%S)-$$"
RUN_DIR="$TELEMETRY_DIR/run-$RUN_ID"

MODEL="${RALPH_MODEL:-sonnet}"
CODEX_MODEL="${RALPH_CODEX_MODEL:-gpt-5.5}"
CODEX_EFFORT="${RALPH_CODEX_REASONING_EFFORT:-high}"
COMMIT_SCOPE="${RALPH_COMMIT_SCOPE:-}"
SLEEP_SECONDS="${RALPH_SLEEP_SECONDS:-2}"
MAX_STALLS="${RALPH_MAX_STALLS:-3}"
FAIL_BACKOFF="${RALPH_FAIL_BACKOFF_SECONDS:-30}"
PREFLIGHT_CMD="${RALPH_PREFLIGHT_CMD:-}"
PREFLIGHT_REQUIRED="${RALPH_PREFLIGHT_REQUIRED:-0}"
ALLOW_DIRTY="${RALPH_ALLOW_DIRTY:-0}"
EXPECTED_BRANCH="${RALPH_EXPECTED_BRANCH:-}"
REQUIRED_ANCESTOR="${RALPH_REQUIRED_ANCESTOR:-}"
COMPLETE_TOKEN='<promise>COMPLETE</promise>'
BLOCKED_TOKEN='<promise>BLOCKED</promise>'
PROGRESS_PATH="$REL_DIR/progress.txt"

[[ "$SLEEP_SECONDS" =~ ^[0-9]+([.][0-9]+)?$ ]] || fail "RALPH_SLEEP_SECONDS must be a non-negative number"
[[ "$MAX_STALLS" =~ ^[0-9]+$ ]] || fail "RALPH_MAX_STALLS must be a non-negative integer"
[[ "$FAIL_BACKOFF" =~ ^[0-9]+$ ]] || fail "RALPH_FAIL_BACKOFF_SECONDS must be a non-negative integer"
[[ "$PREFLIGHT_REQUIRED" =~ ^[01]$ ]] || fail "RALPH_PREFLIGHT_REQUIRED must be 0 or 1"
[[ "${RALPH_DRY_RUN:-0}" =~ ^[01]$ ]] || fail "RALPH_DRY_RUN must be 0 or 1"
[[ "${RALPH_ALLOW_PLACEHOLDERS:-0}" =~ ^[01]$ ]] || fail "RALPH_ALLOW_PLACEHOLDERS must be 0 or 1"
[[ "$ALLOW_DIRTY" =~ ^[01]$ ]] || fail "RALPH_ALLOW_DIRTY must be 0 or 1"

for f in "$PROMPT_FILE" "$PRD_FILE" "$CONTEXT_FILE"; do
  [[ -f "$f" ]] || fail "missing $f"
done
[[ -f "$PROGRESS_FILE" ]] || touch "$PROGRESS_FILE"

if [[ "${RALPH_ALLOW_PLACEHOLDERS:-0}" != "1" ]]; then
  matches="$(LC_ALL=C grep -HnE '__[A-Z0-9][A-Z0-9_]*__' \
    "$PROMPT_FILE" "$PRD_FILE" "$CONTEXT_FILE" "$PROGRESS_FILE" 2>/dev/null || true)"
  if [[ -n "$matches" ]]; then
    printf '%s\n' "$matches" | head -n 20 >&2
    fail "unresolved __PLACEHOLDER__ tokens remain; fill or remove them (RALPH_ALLOW_PLACEHOLDERS=1 for smoke tests only)"
  fi
fi

cd "$REPO_ROOT" || fail "cannot cd to repo root: $REPO_ROOT"

# --- agent resolution ---------------------------------------------------------

AGENT_KIND="custom"
if [[ -n "${RALPH_AGENT_CMD:-}" ]]; then
  AGENT_CMD=()
  while IFS= read -r part; do AGENT_CMD+=("$part"); done < <(
    python3 -c 'import shlex, sys
for p in shlex.split(sys.argv[1]):
    print(p)' "$RALPH_AGENT_CMD"
  )
  (( ${#AGENT_CMD[@]} > 0 )) || fail "RALPH_AGENT_CMD did not parse to a command"
else
  case "${RALPH_AGENT:-auto}" in
    claude) command -v claude >/dev/null 2>&1 || fail "claude CLI not found" ;;
    codex)  command -v codex  >/dev/null 2>&1 || fail "codex CLI not found" ;;
    auto)
      if command -v claude >/dev/null 2>&1; then RALPH_AGENT=claude
      elif command -v codex >/dev/null 2>&1; then RALPH_AGENT=codex
      else fail "no agent CLI found; install claude/codex or set RALPH_AGENT_CMD"
      fi ;;
    *) fail "RALPH_AGENT must be auto, claude, or codex" ;;
  esac
  if [[ "$RALPH_AGENT" == "claude" ]]; then
    AGENT_CMD=(claude --model "$MODEL" --dangerously-skip-permissions
               --print --output-format stream-json --verbose)
  else
    AGENT_CMD=(codex exec --json --dangerously-bypass-approvals-and-sandbox
               -m "$CODEX_MODEL" -c "model_reasoning_effort=\"$CODEX_EFFORT\"")
  fi
fi
case "$(basename "${AGENT_CMD[0]}")" in
  claude) AGENT_KIND="claude" ;;
  codex)  AGENT_KIND="codex" ;;
esac

# --- helpers ------------------------------------------------------------------

mark() { printf '\n[loop %s] %s\n' "$RUN_ID" "$*" >> "$PROGRESS_FILE"; }

stage_changes() {
  if [[ -z "$COMMIT_SCOPE" ]]; then
    git add -A
    return 0
  fi
  local path
  for path in $COMMIT_SCOPE; do
    if [[ -e "$path" ]] || [[ -n "$(git ls-files -- "$path" 2>/dev/null | head -n 1)" ]]; then
      git add -A -- "$path"
    fi
  done
  git add -A -- "$REL_DIR"   # loop state is always checkpointed
}

commit_if_changed() {
  local subject="$1" body="$2"
  stage_changes
  git diff --cached --quiet && return 0
  git commit --no-verify -q -m "$subject" -m "$body" || return 1
  echo "  committed: $(git log -1 --format='%h %s')"
}

commit_paths_if_changed() {
  local subject="$1" body="$2"
  shift 2
  git add -A -- "$@"
  git diff --cached --quiet -- "$@" && return 0
  git commit --no-verify -q -m "$subject" -m "$body" -- "$@" || return 1
  echo "  committed: $(git log -1 --format='%h %s')"
}

# Run-boundary bookkeeping: marker + checkpoint + exit.
finish() {
  local code="$1"; shift
  mark "$*"
  commit_if_changed "ralph: run $RUN_ID - $*" \
    "Launcher run-boundary checkpoint. See $REL_DIR/progress.txt." \
    || echo "WARNING: boundary commit failed; inspect git status." >&2
  echo "Ralph AFK: $* (exit $code)"
  exit "$code"
}

PREFLIGHT_STATUS="none"
run_preflight() {
  [[ -n "$PREFLIGHT_CMD" ]] || return 0
  if bash -c "$PREFLIGHT_CMD" >/dev/null 2>&1; then
    PREFLIGHT_STATUS="ok"
  else
    PREFLIGHT_STATUS="failing"
    return 1
  fi
}

PROMPT_BODY_TEMPLATE="$(cat "$PROMPT_FILE")"

build_prompt() {
  local i="$1" nudge="${2:-}"
  local body="$PROMPT_BODY_TEMPLATE"
  body="${body//"{{ITERATION}}"/$i}"
  body="${body//"{{BUDGET}}"/$ITERATIONS}"
  body="${body//"{{DIR}}"/$REL_DIR}"
  {
    echo "You are one iteration of an autonomous improvement loop (run $RUN_ID)."
    echo
    echo "Repository (your working directory): $REPO_ROOT"
    echo "Loop state directory: $REL_DIR"
    echo "Iteration: $i of $ITERATIONS"
    if [[ "$PREFLIGHT_STATUS" != "none" ]]; then
      echo "Preflight check (\`$PREFLIGHT_CMD\`): $PREFLIGHT_STATUS"
    fi
    if [[ -n "$nudge" ]]; then
      echo
      echo "NOTE: $nudge"
    fi
    echo
    printf '%s\n' "$body"
    echo
    echo "Completion contract: only if the full acceptance bar in $REL_DIR/prd.md is met with evidence recorded in $REL_DIR/progress.txt, end your reply with this exact line on its own:"
    echo
    echo "$COMPLETE_TOKEN"
    echo
    echo "If every remaining item is blocked on specific input the loop cannot obtain, record the blocker in $REL_DIR/progress.txt and end with this exact line instead:"
    echo
    echo "$BLOCKED_TOKEN"
    echo
    echo "Otherwise do not output either token anywhere."
  }
}

# Sets AGENT_STATUS, ITER_LOG, ITER_RESULT.
run_agent() {
  local i="$1" prompt="$2" n
  n="$(printf '%03d' "$i")"
  ITER_LOG="$RUN_DIR/iter-$n.log"
  ITER_RESULT="$RUN_DIR/iter-$n.result.txt"
  AGENT_STATUS=0

  if [[ "$AGENT_KIND" == "claude" && "${AGENT_CMD[*]}" == *"--output-format stream-json"* ]]; then
    "${AGENT_CMD[@]}" "$prompt" 2>&1 | tee "$ITER_LOG" | python3 -u -c '
import json, sys
for line in sys.stdin:
    line = line.strip()
    if not line.startswith("{"):
        continue
    try:
        obj = json.loads(line)
    except Exception:
        continue
    if obj.get("type") == "assistant":
        for block in (obj.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                print(block["text"], flush=True)
'
    AGENT_STATUS=${PIPESTATUS[0]}
    python3 - "$ITER_LOG" > "$ITER_RESULT" <<'PY'
import json, sys
result, texts = None, []
with open(sys.argv[1], encoding="utf-8", errors="replace") as f:
    for line in f:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") == "result" and obj.get("result"):
            result = obj["result"]
        elif obj.get("type") == "assistant":
            for block in (obj.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "text" and block.get("text"):
                    texts.append(block["text"])
sys.stdout.write(result if result is not None else "\n".join(texts))
PY
  elif [[ "$AGENT_KIND" == "codex" && "${AGENT_CMD[*]}" == *"--json"* ]]; then
    local cmd=("${AGENT_CMD[@]}")
    if [[ "${AGENT_CMD[*]}" != *"--output-last-message"* ]]; then
      cmd+=(--output-last-message "$ITER_RESULT")
    fi
    "${cmd[@]}" "$prompt" > "$ITER_LOG" 2>&1
    AGENT_STATUS=$?
    [[ -s "$ITER_RESULT" ]] || cp "$ITER_LOG" "$ITER_RESULT" 2>/dev/null || true
    echo "  --- final message (tail) ---"
    tail -c 1500 "$ITER_RESULT" 2>/dev/null || true
    echo
  else
    "${AGENT_CMD[@]}" "$prompt" 2>&1 | tee "$ITER_LOG"
    AGENT_STATUS=${PIPESTATUS[0]}
    cp "$ITER_LOG" "$ITER_RESULT" 2>/dev/null || true
  fi

  echo "  agent exit: $AGENT_STATUS  log: $ITER_LOG"
}

record_iteration() {
  python3 - "$RUN_DIR/run.jsonl" "$RUN_ID" "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" <<'PY'
import json, sys
path, run_id, iteration, started, ended, duration, status, before, after, preflight = sys.argv[1:11]
rec = {
    "run": run_id,
    "iteration": int(iteration),
    "started_at": started,
    "ended_at": ended,
    "duration_seconds": int(duration),
    "agent_exit": int(status),
    "head_before": before,
    "head_after": after,
    "preflight": preflight,
}
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(rec) + "\n")
PY
}

# --- launch -------------------------------------------------------------------

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
if [[ -n "$EXPECTED_BRANCH" && "$BRANCH" != "$EXPECTED_BRANCH" ]]; then
  fail "expected launch branch $EXPECTED_BRANCH, got $BRANCH"
fi
if [[ -n "$REQUIRED_ANCESTOR" ]]; then
  git cat-file -e "$REQUIRED_ANCESTOR^{commit}" 2>/dev/null \
    || fail "required ancestor is not a commit: $REQUIRED_ANCESTOR"
  git merge-base --is-ancestor "$REQUIRED_ANCESTOR" HEAD \
    || fail "HEAD does not descend from required ancestor $REQUIRED_ANCESTOR"
fi
if [[ "$ALLOW_DIRTY" != "1" && -n "$(git status --porcelain 2>/dev/null | head -n 1)" ]]; then
  fail "working tree is dirty; commit/review it before launch (RALPH_ALLOW_DIRTY=1 only for an intentional recovery)"
fi

echo "Ralph AFK loop"
echo "  repo      : $REPO_ROOT ($BRANCH)"
echo "  state     : $REL_DIR"
echo "  run       : $RUN_ID"
echo "  budget    : $ITERATIONS iterations"
echo "  agent     : ${AGENT_CMD[*]} ($AGENT_KIND)"
echo "  scope     : ${COMMIT_SCOPE:-all changes}"
echo "  stalls    : ${MAX_STALLS} consecutive no-progress iterations stop the loop (0=never; failures back off ${FAIL_BACKOFF}s)"
echo "  preflight : ${PREFLIGHT_CMD:-none}"

if [[ -n "$(git status --porcelain 2>/dev/null | head -n 1)" ]]; then
  echo "WARNING: working tree already has uncommitted changes; the first checkpoint will include them." >&2
fi

if [[ -n "$PREFLIGHT_CMD" ]]; then
  run_preflight || echo "WARNING: preflight failing: $PREFLIGHT_CMD" >&2
  echo "  preflight status: $PREFLIGHT_STATUS"
fi

if [[ "${RALPH_DRY_RUN:-0}" == "1" ]]; then
  echo
  echo "--- prompt preview (iteration 1) ---"
  preview="$(build_prompt 1)"
  printf '%s\n' "$preview"
  echo "--- end preview ---"
  leftover="$(printf '%s' "$preview" | grep -oE '\{\{[A-Za-z_]+\}\}' | sort -u || true)"
  [[ -n "$leftover" ]] && echo "WARNING: unsubstituted tokens in prompt.md: $leftover" >&2
  echo "Dry run: not starting the loop."
  exit 0
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  pid="$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    fail "another ralph loop appears active (pid $pid); remove $LOCK_DIR if stale"
  fi
  rm -rf "$LOCK_DIR"
  mkdir "$LOCK_DIR" 2>/dev/null || fail "cannot acquire lock: $LOCK_DIR"
fi
echo $$ > "$LOCK_DIR/pid"
trap 'rm -rf "$LOCK_DIR"' EXIT

rm -f "$STOP_FILE"
STOP_REQUESTED=false
trap 'STOP_REQUESTED=true; echo ""; echo "Signal received; stopping after the current iteration."' INT TERM

mkdir -p "$RUN_DIR"
mark "start budget=$ITERATIONS agent=$AGENT_KIND branch=$BRANCH"
commit_paths_if_changed "ralph: run $RUN_ID start" \
  "Launcher run-start marker. See $REL_DIR/progress.txt." \
  "$PROGRESS_PATH" \
  || fail "run-start checkpoint failed; inspect git status"

STALLS=0
FAILS=0
AGENT_STATUS=0
LAST_CTX_HASH=""
CTX_UNCHANGED=0

for ((i = 1; i <= ITERATIONS; i++)); do
  if [[ "$STOP_REQUESTED" == true || -f "$STOP_FILE" ]]; then
    finish 0 "stopped before iteration $i"
  fi

  if [[ -n "$PREFLIGHT_CMD" ]]; then
    if ! run_preflight; then
      echo "WARNING: preflight failing: $PREFLIGHT_CMD" >&2
      [[ "$PREFLIGHT_REQUIRED" == "1" ]] && finish 1 "preflight failed before iteration $i"
    fi
  fi

  ctx_hash="$(git hash-object "$CONTEXT_FILE" 2>/dev/null || echo none)"
  if [[ "$ctx_hash" == "$LAST_CTX_HASH" ]]; then
    CTX_UNCHANGED=$((CTX_UNCHANGED + 1))
  else
    CTX_UNCHANGED=0
  fi
  LAST_CTX_HASH="$ctx_hash"
  NUDGE=""
  if (( CTX_UNCHANGED >= 3 )); then
    NUDGE="context.md has not changed for $CTX_UNCHANGED iterations. Before choosing work, verify its candidates and evidence against current reality and update it."
  fi

  echo
  echo "=== iteration $i / $ITERATIONS (run $RUN_ID) ==="
  head_before="$(git rev-parse HEAD 2>/dev/null || echo none)"
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  SECONDS=0

  PROMPT="$(build_prompt "$i" "$NUDGE")"
  run_agent "$i" "$PROMPT"

  if ! commit_if_changed "ralph: iteration $i checkpoint (run $RUN_ID)" \
    "Checkpoint of changes the iteration agent left uncommitted. See $REL_DIR/progress.txt."; then
    mark "commit failed at iteration $i"
    fail "commit failed at iteration $i; inspect git status"
  fi

  head_after="$(git rev-parse HEAD 2>/dev/null || echo none)"
  record_iteration "$i" "$started" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$SECONDS" \
    "$AGENT_STATUS" "$head_before" "$head_after" "$PREFLIGHT_STATUS"

  if grep -qE '^[[:space:]]*<promise>COMPLETE</promise>[[:space:]]*$' "$ITER_RESULT" 2>/dev/null; then
    finish 0 "complete at iteration $i"
  fi
  if grep -qE '^[[:space:]]*<promise>BLOCKED</promise>[[:space:]]*$' "$ITER_RESULT" 2>/dev/null; then
    finish 2 "blocked at iteration $i"
  fi

  # Transient agent failures (rate limits, network blips) must not kill an
  # unattended run: failures are surfaced, backed off, and counted toward the
  # same no-progress cutoff instead of exiting immediately.
  if (( AGENT_STATUS != 0 )); then
    FAILS=$((FAILS + 1))
    echo "WARNING: agent exited $AGENT_STATUS at iteration $i" >&2
  else
    FAILS=0
  fi

  if [[ "$head_after" == "$head_before" ]]; then
    STALLS=$((STALLS + 1))
    echo "  no progress this iteration (agent exit $AGENT_STATUS; streak $STALLS, cutoff $MAX_STALLS)"
  else
    STALLS=0
  fi
  if (( MAX_STALLS > 0 && STALLS >= MAX_STALLS )); then
    finish 2 "stalled after $STALLS consecutive iterations without progress (last agent exit: $AGENT_STATUS)"
  fi

  if (( i < ITERATIONS )); then
    if (( FAILS > 0 && FAIL_BACKOFF > 0 )); then
      backoff=$((FAIL_BACKOFF * FAILS))
      (( backoff > FAIL_BACKOFF * 10 )) && backoff=$((FAIL_BACKOFF * 10))
      echo "  backing off ${backoff}s after agent failure"
      sleep "$backoff"
    else
      sleep "$SLEEP_SECONDS"
    fi
  fi
done

if (( AGENT_STATUS != 0 )); then
  finish 1 "budget exhausted after $ITERATIONS iterations with unresolved agent failure (last agent exit: $AGENT_STATUS)"
fi
finish 2 "budget exhausted after $ITERATIONS iterations without completion"
