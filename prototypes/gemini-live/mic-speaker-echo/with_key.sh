#!/usr/bin/env bash
# usage: with_key.sh <command...>   Runs one command with the provider key in its environment only
# (sourced from the r4-int worktree's git-ignored .env.local, the P69 server.sh way). Nothing is printed or copied.
set -euo pipefail
set -a; . /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r4-int/.env.local; set +a
exec "$@"
