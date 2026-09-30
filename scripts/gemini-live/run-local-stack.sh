#!/usr/bin/env bash
# Local Account Live HTTPS stack. --stub starts a loopback vLLM substitute on port+1.
set -eo pipefail

wt="$(cd "$(dirname "$0")/../.." && pwd)"
port=18500
stub=0
state=""
manifest="${HOME}/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
extra=()
while (($#)); do
  case "$1" in
    --tree) wt="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --state) state="$2"; shift 2 ;;
    --manifest) manifest="$2"; shift 2 ;;
    --stub) stub=1; shift ;;
    --) shift; extra=("$@"); break ;;
    *) extra+=("$1"); shift ;;
  esac
done
py="${wt}.venv/bin/python"
if ((port < 18500 || port > 18508)); then
  echo "port must be 18500..18508 (stub uses port+1)" >&2
  exit 2
fi
if [[ -z "$state" ]]; then
  state="$(mktemp -d "${TMPDIR:-/tmp}/p62.XXXXXX")"
fi
mkdir -p "$state/file-work" "$state/meeting-audio"
chmod 700 "$state"
for asset in app.js styles.css worklets/lane-framer.js; do
  [[ -f "$wt/moss_transcribe_diarize/app/frontend_assets/$asset" ]] || {
    echo "Missing built frontend asset: $asset; run npm --prefix frontend run build" >&2
    exit 2
  }
done
[[ -f "$manifest" ]] || { echo "Missing provider manifest: $manifest" >&2; exit 2; }
model="$(find "${HOME}/.cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | head -1 || true)"
[[ -n "$model" ]] || { echo "Local model metadata unavailable" >&2; exit 2; }
if [[ ! -f "$state/cert.pem" || ! -f "$state/key.pem" ]]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj '/CN=127.0.0.1' \
    -addext 'subjectAltName=IP:127.0.0.1' -keyout "$state/key.pem" \
    -out "$state/cert.pem" >/dev/null 2>&1
  chmod 600 "$state/key.pem"
fi
stub_pid=""
cleanup() {
  if [[ -n "$stub_pid" ]]; then
    kill "$stub_pid" 2>/dev/null || true
    wait "$stub_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM
if ((stub)); then
  PYTHONDONTWRITEBYTECODE=1 "$py" "$wt/prototypes/gemini-live/harness/loopback_vllm_stub.py" \
    --port "$((port+1))" --out "$state/stub" >"$state/stub.log" 2>&1 &
  stub_pid=$!
  for _ in {1..50}; do
    if curl -fsS "http://127.0.0.1:$((port+1))/v1/models" >/dev/null 2>&1; then break; fi
    sleep .1
  done
fi
echo "state=$state base_url=https://127.0.0.1:$port stub=$stub" >&2
cd "$wt"
PYTHONDONTWRITEBYTECODE=1 "$py" -c 'import moss_transcribe_diarize as m; print("moss_import=" + m.__file__)' >&2
MOSS_OPEN_WORKSPACE=1 PYTHONDONTWRITEBYTECODE=1 "$py" -m moss_transcribe_diarize.app.phase2_web_cli \
  --database "$state/phase2.sqlite" --control-socket "$state/control.sock" \
  --tls-certfile "$state/cert.pem" --tls-keyfile "$state/key.pem" \
  --backend vllm --model "$model" \
  --vllm-base-url "http://127.0.0.1:$((port+1))/v1" \
  --vllm-model OpenMOSS-Team/MOSS-Transcribe-Diarize \
  --vllm-timeout 1800 --file-work-root "$state/file-work" \
  --meeting-audio-root "$state/meeting-audio" \
  --live-provider-manifest "$manifest" --live-helper-lease-seconds 120 \
  --host 127.0.0.1 --port "$port" --max-len 16384 --max-new-tokens 12000 \
  "${extra[@]}"
