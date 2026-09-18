#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests/phase2:prototypes/lane-decode-proto
export TMPDIR="$PWD/.wp12/tmp"
mkdir -p "$TMPDIR"
exec /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider -p pytest_local tests --basetemp=.wp12/full-tests
