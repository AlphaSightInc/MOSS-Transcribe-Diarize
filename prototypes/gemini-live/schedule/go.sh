#!/usr/bin/env bash
# PROTOTYPE helper: go.sh <logname> <run.py args...>  (runs from worktree root, logs to P65 evidence)
cd "$(dirname "$0")/../../.."
exec env PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/schedule/run.py "${@:2}" > "/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/schedule/$1.log" 2>&1
