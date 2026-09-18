#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp26/tmp"
mkdir -p "$TMPDIR"
exec /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python prototypes/streaming-diarization/wp26/replay.py "$@"
