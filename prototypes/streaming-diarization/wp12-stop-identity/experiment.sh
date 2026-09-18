#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../../.."
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp12/tmp"
mkdir -p "$TMPDIR"
if lsof -nP -iTCP:18112 -iTCP:17872 -sTCP:LISTEN >/dev/null 2>&1; then
  echo 'WP12 measurement ports already in use; no dispatch.' >&2
  exit 1
fi
P=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
openssl req -x509 -newkey rsa:2048 -nodes -keyout .wp12/key.pem -out .wp12/cert.pem -days 2 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1 2>/dev/null
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -L 127.0.0.1:18112:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us > .wp12/tunnel.log 2>&1 &
T=$!;S=''
cleanup(){ if [ -n "$S" ]; then kill "$S" 2>/dev/null || true; wait "$S" 2>/dev/null || true; fi; kill "$T" 2>/dev/null || true; wait "$T" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 20); do if curl -fsS --max-time 1 http://127.0.0.1:18112/metrics > .wp12/metrics.txt 2>/dev/null; then break; fi; sleep 1; done
kill -0 "$T"
rg '^vllm:num_requests_(running|waiting)' .wp12/metrics.txt | tee -a evidence/mvpfix/wp12/admission.txt
"$P" - <<'PY'
import os,re
from pathlib import Path
s=Path('.wp12/metrics.txt').read_text()
v={k:float(x) for k,x in re.findall(r'^vllm:num_requests_(running|waiting)\{[^\n]+\} ([0-9.e+-]+)$',s,re.M)}
allowed_running=1 if os.environ.get('WP12_SINGLE_FLIGHT')=='1' else 0
assert len(v)==2 and v['waiting']==0 and v['running']<=allowed_running,'decoder busy or metrics absent'
PY
"$P" prototypes/streaming-diarization/wp12-stop-identity/stack.py --state ".wp12/state-${WP12_ARM:-lane}" --cert .wp12/cert.pem --key .wp12/key.pem --port 17872 --vllm-base-url http://127.0.0.1:18112/v1 > ".wp12/stack-${WP12_ARM:-lane}.log" 2>&1 &
S=$!
for _ in $(seq 1 30); do if curl -kfsS --max-time 1 https://127.0.0.1:17872/ > /dev/null 2>&1; then break; fi; sleep 1; done
kill -0 "$T" "$S"
"$P" prototypes/streaming-diarization/wp12-stop-identity/run.py "$@"
