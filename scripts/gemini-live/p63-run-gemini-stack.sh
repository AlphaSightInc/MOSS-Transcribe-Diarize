#!/usr/bin/env bash
# Local Gemini Account Live HTTPS stack; caller owns process termination.
set -euo pipefail
wt="$(cd "$(dirname "$0")/../.." && pwd)"
port="${1:-18510}"
state="${2:-${TMPDIR:-/tmp}/p63-gemini-stack}"
manifest="${3:-$HOME/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json}"
if ((port < 18510 || port > 18519)); then echo 'P63 port must be 18510..18519' >&2; exit 2; fi
mkdir -p "$state/file-work" "$state/meeting-audio"
chmod 700 "$state"
if [[ ! -f "$state/cert.pem" || ! -f "$state/key.pem" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj '/CN=127.0.0.1' \
    -addext 'subjectAltName=IP:127.0.0.1' -keyout "$state/key.pem" -out "$state/cert.pem" >/dev/null 2>&1
  chmod 600 "$state/key.pem"
fi
cd "$wt"
echo "state=$state base_url=https://127.0.0.1:$port" >&2
MOSS_OPEN_WORKSPACE=1 PYTHONDONTWRITEBYTECODE=1 "${wt}.venv/bin/python" -m moss_transcribe_diarize.app.phase2_web_cli \
  --database "$state/phase2.sqlite" --control-socket "$state/control.sock" \
  --tls-certfile "$state/cert.pem" --tls-keyfile "$state/key.pem" \
  --file-work-root "$state/file-work" --meeting-audio-root "$state/meeting-audio" \
  --live-provider-manifest "$manifest" --live-helper-lease-seconds 120 \
  --live-engine gemini --host 127.0.0.1 --port "$port"
