#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp12/tmp"
mkdir -p "$TMPDIR"
P=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
openssl req -x509 -newkey rsa:2048 -nodes -keyout .wp12/key.pem -out .wp12/cert.pem -days 2 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1 2>/dev/null
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -L 127.0.0.1:18112:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us > .wp12/tunnel.log 2>&1 &
T=$!;S=''
cleanup(){ if [ -n "$S" ]; then kill "$S" 2>/dev/null || true; wait "$S" 2>/dev/null || true; fi; kill "$T" 2>/dev/null || true; wait "$T" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 20); do if curl -fsS --max-time 1 http://127.0.0.1:18112/metrics > .wp12/metrics.txt 2>/dev/null; then break; fi; sleep 1; done
rg '^vllm:num_requests_(running|waiting)' .wp12/metrics.txt | tee -a evidence/mvpfix/wp12/admission.txt
"$P" - <<'PY'
import re
from pathlib import Path
s=Path('.wp12/metrics.txt').read_text()
v=re.findall(r'^vllm:num_requests_(?:running|waiting)\{[^\n]+\} ([0-9.e+-]+)$',s,re.M)
assert len(v)>=2 and not any(float(x) for x in v),'decoder busy or metrics absent'
PY
"$P" prototypes/streaming-diarization/wp12-stop-identity/stack.py --state ".wp12/state-${WP12_ARM:-lane}" --cert .wp12/cert.pem --key .wp12/key.pem --port 17872 --vllm-base-url http://127.0.0.1:18112/v1 > ".wp12/stack-${WP12_ARM:-lane}.log" 2>&1 &
S=$!
for _ in $(seq 1 30); do if curl -kfsS --max-time 1 https://127.0.0.1:17872/ > /dev/null 2>&1; then break; fi; sleep 1; done
"$P" prototypes/streaming-diarization/wp12-stop-identity/run.py "$@"
