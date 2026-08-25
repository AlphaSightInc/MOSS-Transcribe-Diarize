#!/usr/bin/env bash
# Two warm-decoder paired passes over ONE case, case supplied by argument.
#
#   run_paired_case.sh <out-root> <label> <case-id> <case-dir>
#
# Same protocol as run_paired_passes.sh -- strictly sequential passes against the running
# deployed service (one in-flight vLLM request per harness), each preceded by ONE DISCARDED
# decode request, because the deployed decoder's only observed non-determinism was a
# cold-start flip (M0d). The warming request is never scored.
#
# Writes <out-root>/<label>-A/ and <out-root>/<label>-B/ in the layout
# verify_m2_exit.case_paths reads, plus <out-root>/console/*.log and, on completion,
# <out-root>/DONE.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$REPO/.venv/bin/python"
HERE="$REPO/prototypes/streaming-diarization/live-convergence"
ROOT="${1:?usage: run_paired_case.sh <out-root> <label> <case-id> <case-dir>}"
LABEL="${2:?missing <label>}"
CASE="${3:?missing <case-id>}"
CASE_DIR="${4:?missing <case-dir>}"
LOG="$ROOT/console"
mkdir -p "$LOG"
cd "$REPO" || exit 1

pass() {  # pass <run>
  local run="$1" rc
  echo "--- $LABEL-$run WARMUP $(date -u +%FT%TZ) ---" | tee -a "$LOG/runner.log"
  PYTHONDONTWRITEBYTECODE=1 "$PY" "$HERE/probe_decode_determinism.py" --repeats 1 \
    >"$LOG/$LABEL-$run.warmup.log" 2>&1
  echo "--- $LABEL-$run WARMUP EXIT $? $(date -u +%FT%TZ) ---" | tee -a "$LOG/runner.log"
  echo "=== $LABEL-$run START $(date -u +%FT%TZ) ===" | tee -a "$LOG/runner.log"
  PYTHONDONTWRITEBYTECODE=1 "$PY" "$HERE/remeasure_one_case.py" \
    --case "$CASE" --case-dir "$CASE_DIR" "$ROOT/$LABEL-$run" \
    >"$LOG/$LABEL-$run.log" 2>&1
  rc=$?
  echo "=== $LABEL-$run EXIT $rc $(date -u +%FT%TZ) ===" | tee -a "$LOG/runner.log"
}

pass A
pass B
echo "ALL PASSES DONE $(date -u +%FT%TZ)" | tee -a "$LOG/runner.log"
touch "$ROOT/DONE"
