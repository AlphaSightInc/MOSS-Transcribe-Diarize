#!/usr/bin/env bash
# M0(d) paired re-acquisition: four strictly-sequential measurement passes against the
# running deployed service (one in-flight vLLM request per harness). Detached from the
# caller so an agent/session exit cannot truncate a pass mid-run.
#
#   run_paired_reacquisition.sh <out-root>
#
# Writes <out-root>/{trio-A,trio-B,keyu5m-A,keyu5m-B}/ plus <out-root>/console/*.log
# and, on completion, <out-root>/DONE.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$REPO/.venv/bin/python"
ROOT="${1:?usage: run_paired_reacquisition.sh <out-root>}"
LOG="$ROOT/console"
mkdir -p "$LOG"
cd "$REPO" || exit 1

pass() {  # pass <label> <driver-relpath>
  local label="$1" driver="$2" rc
  echo "=== $label START $(date -u +%FT%TZ) ===" | tee -a "$LOG/runner.log"
  PYTHONDONTWRITEBYTECODE=1 "$PY" "$REPO/$driver" "$ROOT/$label" >"$LOG/$label.log" 2>&1
  rc=$?
  echo "=== $label EXIT $rc $(date -u +%FT%TZ) ===" | tee -a "$LOG/runner.log"
}

pass trio-A    prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py
pass trio-B    prototypes/live-file-gap-baseline-20260824/remeasure_live_vs_file.py
pass keyu5m-A  prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py
pass keyu5m-B  prototypes/live-file-gap-baseline-20260824/remeasure_5m_case.py
echo "ALL PASSES DONE $(date -u +%FT%TZ)" | tee -a "$LOG/runner.log"
touch "$ROOT/DONE"
