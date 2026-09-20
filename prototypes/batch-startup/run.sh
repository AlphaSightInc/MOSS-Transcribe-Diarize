#!/bin/sh
set -eu

PYTHON=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
CASE=${1:-all}
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. "$PYTHON" prototypes/batch-startup/prototype.py --case "$CASE"
