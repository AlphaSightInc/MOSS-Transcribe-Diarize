#!/usr/bin/env bash
# Campaign paired measurement passes, warm-decoder protocol.
#
#   run_paired_passes.sh <out-root>
#
# Four strictly-sequential passes against the running deployed service (one in-flight
# vLLM request per harness), each preceded by ONE DISCARDED decode request. The warm-up
# is instrument hygiene fixed for the campaign in
# evidence/live-convergence-0824/M1-salvage-production/PREREGISTRATION.md: the deployed
# decoder's only observed non-determinism was a cold-start flip (M0d), so every pass is
# measured on a warm decoder and the warming request is never scored.
#
# This supersedes run_paired_reacquisition.sh (kept as the M0d reproducer, which ran
# without the warm-up) for M1 onward.
#
# Writes <out-root>/{trio-A,trio-B,keyu5m-A,keyu5m-B}/ plus <out-root>/console/*.log
# and, on completion, <out-root>/DONE.
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PY="$REPO/.venv/bin/python"
ROOT="${1:?usage: run_paired_passes.sh <out-root>}"
LOG="$ROOT/console"
mkdir -p "$LOG"
cd "$REPO" || exit 1

warmup() {  # warmup <label> -- one decode request, discarded
  local label="$1"
  echo "--- $label WARMUP $(date -u +%FT%TZ) ---" | tee -a "$LOG/runner.log"
  PYTHONDONTWRITEBYTECODE=1 "$PY" \
    "$REPO/prototypes/streaming-diarization/live-convergence/probe_decode_determinism.py" \
    --repeats 1 >"$LOG/$label.warmup.log" 2>&1
  echo "--- $label WARMUP EXIT $? $(date -u +%FT%TZ) ---" | tee -a "$LOG/runner.log"
}

pass() {  # pass <label> <driver-relpath>
  local label="$1" driver="$2" rc
  warmup "$label"
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
