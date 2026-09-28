#!/usr/bin/env bash
# One-command local MOSS with the Gemini live engine (D8 launcher).
#   scripts/gemini-live/start-gemini.sh [port]      default port 18600
# Opens https://127.0.0.1:<port>/ (self-signed certificate; accept it once in the browser).
# Needs: this worktree's venv (<worktree>.venv), GEMINI_API_KEY in <worktree>/.env.local,
# built frontend assets, and the local live provider manifest (VAD + WeSpeaker settings).
# State (meetings, voiceprints, audio) persists in ~/.local/share/moss-gemini-live/state.
set -euo pipefail
wt="$(cd "$(dirname "$0")/../.." && pwd)"
port="${1:-18600}"
state="${MOSS_GEMINI_STATE:-$HOME/.local/share/moss-gemini-live/state}"
manifest="${MOSS_LIVE_MANIFEST:-$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json}"
py="${wt}.venv/bin/python"
[[ -x "$py" ]] || { echo "Missing venv: $py" >&2; exit 2; }
grep -q '^GEMINI_API_KEY=.' "$wt/.env.local" 2>/dev/null || { echo "Put GEMINI_API_KEY=... in $wt/.env.local" >&2; exit 2; }
[[ -f "$manifest" ]] || { echo "Missing live provider manifest: $manifest" >&2; exit 2; }
for asset in app.js styles.css worklets/lane-framer.js; do
  [[ -f "$wt/moss_transcribe_diarize/app/frontend_assets/$asset" ]] || {
    echo "Building frontend assets (missing $asset)…" >&2; npm --prefix "$wt/frontend" run build >&2; break; }
done
mkdir -p "$state/file-work" "$state/meeting-audio"; chmod 700 "$state"
# Unix socket paths are limited to ~104 bytes on macOS; keep the control socket short.
sock="$HOME/.moss-gemini-live-$port.sock"
if [[ ! -f "$state/cert.pem" || ! -f "$state/key.pem" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj '/CN=127.0.0.1' \
    -addext 'subjectAltName=IP:127.0.0.1' -keyout "$state/key.pem" -out "$state/cert.pem" >/dev/null 2>&1
  chmod 600 "$state/key.pem"
fi
cd "$wt"
echo "MOSS (Gemini live engine) → https://127.0.0.1:$port/   state=$state   Ctrl-C to stop" >&2
exec env MOSS_OPEN_WORKSPACE=1 PYTHONDONTWRITEBYTECODE=1 "$py" -m moss_transcribe_diarize.app.phase2_web_cli \
  --database "$state/phase2.sqlite" --control-socket "$sock" \
  --tls-certfile "$state/cert.pem" --tls-keyfile "$state/key.pem" \
  --file-work-root "$state/file-work" --meeting-audio-root "$state/meeting-audio" \
  --live-provider-manifest "$manifest" --live-helper-lease-seconds 30 \
  --live-engine gemini --host 127.0.0.1 --port "$port"
