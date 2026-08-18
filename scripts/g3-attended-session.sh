#!/usr/bin/env bash
# Stand up everything the G3 attended checklist needs, on this machine, in one command.
#
#   ./scripts/g3-attended-session.sh
#
# Requires either a reachable MOSS_VLLM_BASE_URL or an explicit MOSS_HF_MODEL directory.
# The GPU host is READ-ONLY: we send it inference requests only, and run the service here.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

PORT=7861
STATE_DIR="${HOME}/.local/share/moss-transcribe-diarize/g3"
CERT="${STATE_DIR}/live-cert.pem"
KEY="${STATE_DIR}/live-key.pem"
TOKEN_FILE="${STATE_DIR}/shared-token"
mkdir -p "$STATE_DIR"; chmod 700 "$STATE_DIR"

: "${MOSS_LIVE_PROVIDER_MANIFEST:?set MOSS_LIVE_PROVIDER_MANIFEST to the finalized local live-provider-manifest.json first}"
: "${MOSS_LIVE_HELPER_LEASE_SECONDS:?set MOSS_LIVE_HELPER_LEASE_SECONDS to the declared positive helper lease first}"

MODEL_ARGS=()
MODEL_BACKEND=""
if [[ -n "${MOSS_VLLM_BASE_URL:-}" ]]; then
  echo "==> checking the configured vLLM endpoint"
  code=$(curl -sS -k -o /dev/null -w '%{http_code}' --max-time 8 "${MOSS_VLLM_BASE_URL%/}/models" 2>/dev/null)
  if [[ "$code" == "200" ]]; then
    MODEL_ARGS=(--backend vllm --vllm-base-url "$MOSS_VLLM_BASE_URL")
    MODEL_BACKEND="vllm"
    echo "    OK: using vLLM"
  else
    echo "    endpoint returned '$code'; falling back to MOSS_HF_MODEL"
  fi
fi

if [[ -z "$MODEL_BACKEND" ]]; then
  : "${MOSS_HF_MODEL:?set MOSS_HF_MODEL to a local Hugging Face model directory when vLLM is unavailable}"
  [[ -d "$MOSS_HF_MODEL" ]] || { echo "MOSS_HF_MODEL is not a directory: $MOSS_HF_MODEL"; exit 1; }
  [[ -f "$MOSS_HF_MODEL/config.json" ]] || { echo "MOSS_HF_MODEL has no config.json: $MOSS_HF_MODEL"; exit 1; }
  MODEL_ARGS=(--backend hf --model "$MOSS_HF_MODEL")
  MODEL_BACKEND="hf"
  echo "==> using local HF model: $MOSS_HF_MODEL"
fi

if [[ ! -f "$CERT" ]]; then
  echo "==> generating a self-signed TLS cert (the browser needs a secure context for microphone access)"
  ./ops/generate-live-tls.sh --output-dir "$STATE_DIR" >/dev/null 2>&1 \
    || openssl req -x509 -newkey rsa:2048 -nodes -keyout "$KEY" -out "$CERT" -days 30 \
         -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
  chmod 600 "$KEY"
fi

if [[ ! -f "$TOKEN_FILE" ]]; then
  ( umask 077; head -c 32 /dev/urandom | base64 | tr -d '\n=' > "$TOKEN_FILE" )
fi
TOKEN="$(cat "$TOKEN_FILE")"

echo
echo "============================================================"
echo "  OPEN THIS:      https://localhost:${PORT}/"
echo "  CAPTURE BEARER: ${TOKEN}"
echo "  PLAY THIS in the shared tab:"
echo "     evidence/phase1/g3-attended/two-speaker-fixture-90s.wav"
echo "============================================================"
echo
echo "Accept the browser's certificate warning ONCE (it is our own self-signed cert)."
echo "Ctrl-C here when the checklist is done."
echo

exec .venv/bin/python -m moss_transcribe_diarize.app.web_cli \
  "${MODEL_ARGS[@]}" \
  --live \
  --live-provider-manifest "$MOSS_LIVE_PROVIDER_MANIFEST" \
  --host 127.0.0.1 --port "$PORT" \
  --live-tls-certfile "$CERT" --live-tls-keyfile "$KEY" \
  --live-auth-state "${STATE_DIR}/live-auth.json" \
  --live-shared-token-file "$TOKEN_FILE" \
  --live-helper-lease-seconds "$MOSS_LIVE_HELPER_LEASE_SECONDS"
