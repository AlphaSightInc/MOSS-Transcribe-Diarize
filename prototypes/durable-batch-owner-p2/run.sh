#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/durable-batch-owner-p2/prototype.py
