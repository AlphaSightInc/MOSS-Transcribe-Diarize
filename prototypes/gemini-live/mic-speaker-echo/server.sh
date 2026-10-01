#!/usr/bin/env bash
# usage: server.sh <port> <state-name> | server.sh stop <state-name>      (ports 18970-18979 only)
# Starts the product launcher from THIS worktree (gemini/r5-d = 9a1ca171 + docs) with fresh state under the
# P72 evidence folder. The provider key is sourced into the server process only (P69 server.sh way); never printed.
set -euo pipefail
EV="$HOME/Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo"
WT="$(cd "$(dirname "$0")/../../.." && pwd)"
if [[ "$1" == "stop" ]]; then
  pid="$(cat "$EV/server-$2.pid")"; pkill -P "$pid" 2>/dev/null || true; kill "$pid" 2>/dev/null || true; echo "stopped $pid"; exit 0
fi
port="$1"; name="$2"
case "$port" in 1897[0-9]) ;; *) echo "port must be 18970-18979" >&2; exit 2;; esac
mkdir -p "$EV"
cd "$WT"
(
  set -a; . /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-r4-int/.env.local; set +a
  MOSS_GEMINI_OPEN_WORKSPACE=1 MOSS_GEMINI_STATE="$EV/state-$name" exec scripts/gemini-live/start-gemini.sh "$port"
) > "$EV/server-$name.log" 2>&1 &
echo $! > "$EV/server-$name.pid"
for i in $(seq 1 90); do
  if curl -sk "https://127.0.0.1:$port/" -o /dev/null; then echo "up $port pid $(cat "$EV/server-$name.pid")"; exit 0; fi
  sleep 1
done
echo "server did not come up"; tail -20 "$EV/server-$name.log"; exit 1
