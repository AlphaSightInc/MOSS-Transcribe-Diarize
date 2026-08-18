#!/usr/bin/env bash
# Launch one AFK4 ralph loop in its assigned worktree.
#
#   ./scripts/afk4-launch.sh <ticket> [iterations]
#   ./scripts/afk4-launch.sh y1-file-mode 12
#
# Each ticket owns one worktree so the loops cannot collide on the index or on
# build artifacts. The guardrail preflight runs before every iteration and stops
# the loop on any ownership or evidence violation.
#
# Stop a running loop gracefully:
#   touch <worktree>/scripts/afk4-<ticket>/.stop
set -uo pipefail

TICKET="${1:?usage: afk4-launch.sh <ticket> [iterations]}"
ITERATIONS="${2:-12}"

case "$TICKET" in
  y1-file-mode)           WT=1 ;;
  y2-transcript-export)   WT=2 ;;
  y3-session-reattach)    WT=4 ;;
  y4-concurrency-cert)    WT=3 ;;
  y5-guardrail-and-floor) WT=5 ;;
  y6-browser-reload)      WT=6 ;;
  y7-jobs-auth-and-export-caveat) WT=3 ;;
  *) echo "unknown ticket: $TICKET" >&2; exit 1 ;;
esac

WORKTREE="/Users/gao/.treehouse/MOSS-Transcribe-Diarize-e7521b/${WT}/MOSS-Transcribe-Diarize"
[[ -d "$WORKTREE" ]] || { echo "missing worktree: $WORKTREE" >&2; exit 1; }

BRANCH="$(git -C "$WORKTREE" rev-parse --abbrev-ref HEAD)"
[[ "$BRANCH" == "afk4/$TICKET" ]] || {
  echo "worktree $WT is on '$BRANCH', expected 'afk4/$TICKET'" >&2; exit 1; }

# npm lives in homebrew only; `npm ci` genuinely fails on this host, and `log` is
# shadowed by a builtin, so keep /usr/bin ahead of nothing and homebrew first.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
export PYTHONDONTWRITEBYTECODE=1

export RALPH_AGENT=codex
export RALPH_CODEX_MODEL="${RALPH_CODEX_MODEL:-gpt-5.6-terra}"
export RALPH_CODEX_REASONING_EFFORT="${RALPH_CODEX_REASONING_EFFORT:-xhigh}"
export RALPH_PREFLIGHT_CMD="scripts/afk-guardrails/preflight.py $TICKET"
export RALPH_PREFLIGHT_REQUIRED=1
export RALPH_MAX_STALLS="${RALPH_MAX_STALLS:-3}"

cd "$WORKTREE" || exit 1
echo "[afk4] $TICKET  wt=$WT  branch=$BRANCH  iterations=$ITERATIONS"
echo "[afk4] agent=$RALPH_AGENT model=$RALPH_CODEX_MODEL effort=$RALPH_CODEX_REASONING_EFFORT"
exec "./scripts/afk4-$TICKET/ralph-afk.sh" "$ITERATIONS"
