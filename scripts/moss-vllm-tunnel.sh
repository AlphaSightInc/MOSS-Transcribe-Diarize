#!/usr/bin/env bash
# Reach the GPU host's vLLM from this Mac without changing anything on that host.
#
#   ./scripts/moss-vllm-tunnel.sh          # start (idempotent)
#   ./scripts/moss-vllm-tunnel.sh stop
#
# vLLM there is bound to 127.0.0.1:8000 and is managed by a systemd --user unit. Binding it to
# the tailnet was attempted and rolled back: the GPU has under 1 GiB free with mineru-api holding
# 0.5 utilisation, so the engine crashed on KV cache. A tunnel needs no GPU memory, no firewall
# change, and no edit to that host -- which charter section 1 forbids anyway.
set -uo pipefail
HOST=gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us
LOCAL_PORT=18000

if [[ "${1:-start}" == "stop" ]]; then
  pkill -f "ssh -f -N.*${LOCAL_PORT}:127.0.0.1:8000" && echo "tunnel stopped" || echo "no tunnel running"
  exit 0
fi

if curl -sS -o /dev/null --max-time 4 "http://127.0.0.1:${LOCAL_PORT}/v1/models" 2>/dev/null; then
  echo "tunnel already up on 127.0.0.1:${LOCAL_PORT}"
else
  pkill -f "ssh -f -N.*${LOCAL_PORT}:127.0.0.1:8000" 2>/dev/null
  ssh -f -N -o BatchMode=yes -o ExitOnForwardFailure=yes \
      -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
      -L "${LOCAL_PORT}:127.0.0.1:8000" "$HOST" || { echo "tunnel failed to start"; exit 1; }
  sleep 3
fi

curl -sS --max-time 8 "http://127.0.0.1:${LOCAL_PORT}/v1/models" >/dev/null 2>&1 \
  || { echo "tunnel is up but vLLM did not answer -- check the host"; exit 1; }

echo
echo "  MOSS_VLLM_BASE_URL=http://127.0.0.1:${LOCAL_PORT}/v1"
echo
