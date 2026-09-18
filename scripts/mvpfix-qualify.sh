#!/usr/bin/env bash
# Local measurement only. No deployment or attended-capture acceptance.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
PY="${MOSS_QUALIFY_PYTHON:-/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python}"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$root"
child=''
cleanup() {
  if [[ -n "$child" ]] && kill -0 "$child" 2>/dev/null; then
    kill -TERM "$child"
    wait "$child" || true
  fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
"$PY" tools/qualify/run.py "$@" &
child=$!
status=0
wait "$child" || status=$?
child=''
exit "$status"
