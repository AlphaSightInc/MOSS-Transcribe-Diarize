#!/usr/bin/env bash
# Stand up everything charter section 7's attended checklist needs.
#
#   ./scripts/g3-attended-session.sh
#
# The browser must run on the machine holding the MICROPHONE. That is the M4 MacBook Pro, not
# this Mac Studio, so the service binds to all interfaces and the laptop reaches it over the
# tailnet. Browser capture needs a secure context, so this is HTTPS with a self-signed cert whose
# SANs cover the tailnet name -- you accept that warning once, in the browser, on the laptop.
#
# Inference goes to the GPU host only (operator ruling: this Mac must NOT load the model).
# vLLM there listens on its own loopback, so we reach it through an SSH tunnel.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

PORT=7861
TUNNEL_PORT=18000
TAILNET_NAME=macstudio.tailnet.aisight.us
STATE_DIR="${HOME}/.local/share/moss-transcribe-diarize/g3"
CERT="${STATE_DIR}/live-cert.pem"
KEY="${STATE_DIR}/live-key.pem"
TOKEN_FILE="${STATE_DIR}/shared-token"
MANIFEST="${MOSS_LIVE_PROVIDER_MANIFEST:-${HOME}/.local/share/moss-transcribe-diarize/live/live-provider-manifest.json}"
mkdir -p "$STATE_DIR"; chmod 700 "$STATE_DIR"

TAILNET_IP="$(ifconfig 2>/dev/null | awk '/inet 100\./{print $2; exit}')"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)"

echo "==> ensuring the SSH tunnel to the GPU host's vLLM"
./scripts/moss-vllm-tunnel.sh >/dev/null 2>&1
: "${MOSS_VLLM_BASE_URL:=http://127.0.0.1:${TUNNEL_PORT}/v1}"
export MOSS_VLLM_BASE_URL
code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 8 "${MOSS_VLLM_BASE_URL%/}/models" 2>/dev/null)
[[ "$code" == "200" ]] || { echo "    model endpoint returned '$code'. Run ./scripts/moss-vllm-tunnel.sh and retry."; exit 1; }
echo "    OK - model reachable at ${MOSS_VLLM_BASE_URL}"

[[ -f "$MANIFEST" ]] || { echo "FATAL: provider manifest missing at $MANIFEST"; exit 1; }

# Regenerate the cert whenever it does not already cover the tailnet name, because a cert issued
# for localhost alone makes the laptop's browser refuse rather than merely warn.
need_cert=1
if [[ -f "$CERT" ]] && openssl x509 -in "$CERT" -noout -text 2>/dev/null | grep -q "$TAILNET_NAME"; then
  need_cert=0
fi
if [[ "$need_cert" == "1" ]]; then
  echo "==> generating a TLS cert valid for the laptop's URL"
  SAN="DNS:${TAILNET_NAME},DNS:localhost,DNS:$(hostname),IP:127.0.0.1"
  [[ -n "$TAILNET_IP" ]] && SAN="${SAN},IP:${TAILNET_IP}"
  [[ -n "$LAN_IP" ]]     && SAN="${SAN},IP:${LAN_IP}"
  openssl req -x509 -newkey rsa:2048 -nodes -keyout "$KEY" -out "$CERT" -days 30 \
    -subj "/CN=${TAILNET_NAME}" -addext "subjectAltName=${SAN}" >/dev/null 2>&1 \
    || { echo "FATAL: could not generate cert"; exit 1; }
  chmod 600 "$KEY"
  echo "    SANs: ${SAN}"
fi

[[ -f "$TOKEN_FILE" ]] || ( umask 077; head -c 32 /dev/urandom | base64 | tr -d '\n=' > "$TOKEN_FILE" )
TOKEN="$(cat "$TOKEN_FILE")"

cat <<BANNER

================================================================
  ON THE M4 MACBOOK PRO  (the machine with the microphone)

  OPEN:            https://${TAILNET_NAME}:${PORT}/
  CAPTURE BEARER:  ${TOKEN}

  Chrome will warn the certificate is not trusted. That is ours,
  self-signed. Click Advanced -> Proceed. Once only.
  Do NOT open port 8000 in a browser -- that is the model API,
  it serves JSON, and it is not published.

  PLAY IN THE SHARED TAB:
    evidence/phase1/g3-attended/two-speaker-fixture-90s.wav
================================================================

BANNER
[[ -n "$TAILNET_IP" ]] && echo "  (if the name fails, use https://${TAILNET_IP}:${PORT}/ )"
echo "  Ctrl-C here when the checklist is done."
echo

exec .venv/bin/python -m moss_transcribe_diarize.app.web_cli \
  --live \
  --host 0.0.0.0 --port "$PORT" \
  --live-provider-manifest "$MANIFEST" \
  --live-tls-certfile "$CERT" --live-tls-keyfile "$KEY" \
  --live-auth-state "${STATE_DIR}/live-auth.json" \
  --live-shared-token-file "$TOKEN_FILE" \
  --live-helper-lease-seconds "${MOSS_LIVE_HELPER_LEASE_SECONDS:-30}" \
  --live-vector-journal-path "${STATE_DIR}/vector-journal.jsonl"
