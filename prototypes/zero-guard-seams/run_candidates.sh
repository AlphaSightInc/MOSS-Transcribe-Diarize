#!/bin/bash
# PROTOTYPE -- THROWAWAY. WP10: the contracts half of the harness.
#
# One command:  bash prototypes/zero-guard-seams/run_candidates.sh
#
# For each candidate branch it checks the branch out IN THIS WORKTREE, runs the five files
# that hold the nineteen regressed decoder-seam contracts plus WP3's two guard files, runs
# falsify.py (the requirements half), and prints the pair. A candidate has answered the
# question only when BOTH columns are clean. The branch you started on is restored at the end.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
OUT="$ROOT/evidence/mvpfix/wp10"
SEAMS="tests/test_live_pipeline_seams.py tests/phase2/test_draft_lane.py tests/phase2/test_runner_composition.py tests/test_live_rolling_wiring.py tests/test_live_service_replay.py"
GUARDS="tests/test_live_capture_guard.py tests/test_live_terminal_finalizer.py"

CANDIDATES=(
  "c1-dispatch:mvpfix/wp10-zero-guard-seams"
  "c2-mixer:proto/wp10-c2-mixer"
  "c3-adapter:proto/wp10-c3-adapter"
)

cd "$ROOT" || exit 1
mkdir -p "$OUT"
START="$(git rev-parse --abbrev-ref HEAD)"
echo "prototype harness -- starting branch: $START"

for entry in "${CANDIDATES[@]}"; do
  name="${entry%%:*}"; branch="${entry#*:}"
  echo
  echo "================ candidate $name ($branch) ================"
  if ! git checkout --quiet "$branch" 2>/dev/null; then
    echo "  SKIP -- branch $branch does not exist yet"
    continue
  fi
  # shellcheck disable=SC2086
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m pytest -q -p no:cacheprovider $SEAMS \
    >"$OUT/$name-seams.log" 2>&1
  # shellcheck disable=SC2086
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" -m pytest -q -p no:cacheprovider $GUARDS \
    >"$OUT/$name-guards.log" 2>&1
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PY" prototypes/zero-guard-seams/falsify.py \
    >"$OUT/$name-falsify.log" 2>&1
  echo "  seam contracts    : $(tail -1 "$OUT/$name-seams.log")"
  echo "  WP3 guard tests   : $(tail -1 "$OUT/$name-guards.log")"
  echo "  requirements      : $(grep -a 'requirements met' "$OUT/$name-falsify.log" | tail -1 | sed 's/\x1b\[[0-9;]*m//g')"
  grep -a '^FAILED' "$OUT/$name-seams.log" "$OUT/$name-guards.log" | sed 's/^/    /' | head -30
  grep -a 'FAIL.*R[0-9]' "$OUT/$name-falsify.log" | sed 's/\x1b\[[0-9;]*m//g' | sed 's/^/    /'
done

echo
git checkout --quiet "$START"
echo "restored branch: $(git rev-parse --abbrev-ref HEAD)"
echo "logs: $OUT"
