#!/bin/bash
# THROWAWAY real-stack experiment. All output/state stays inside the WP1 worktree.
set -euo pipefail
cd "$(dirname "$0")/../.."
WP1_PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/prototypes/lane-decode-proto/scratch"
mkdir -p "$TMPDIR" evidence/mvpfix/wp1
"$WP1_PY" prototypes/lane-decode-proto/build_overlay.py
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$TMPDIR/key.pem" -out "$TMPDIR/cert.pem" -days 2 -subj /CN=127.0.0.1 -addext subjectAltName=IP:127.0.0.1 2>/dev/null
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -o ConnectTimeout=10 -L 127.0.0.1:18101:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us > "$TMPDIR/tunnel.log" 2>&1 &
WP1_TUNNEL=$!
WP1_STACK=''
cleanup() { if [ -n "$WP1_STACK" ]; then kill "$WP1_STACK" 2>/dev/null || true; wait "$WP1_STACK" 2>/dev/null || true; fi; kill "$WP1_TUNNEL" 2>/dev/null || true; wait "$WP1_TUNNEL" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
for _ in $(seq 1 20); do if curl -fsS --max-time 1 http://127.0.0.1:18101/metrics > "$TMPDIR/metrics.txt" 2>/dev/null; then break; fi; sleep 1; done
rg '^vllm:num_requests_(running|waiting)' "$TMPDIR/metrics.txt"
"$WP1_PY" - "$TMPDIR/metrics.txt" <<'PYCODE'
import re,sys,json,time
from pathlib import Path
body=Path(sys.argv[1]).read_text()
values={key:sum(float(x) for x in re.findall(r'^vllm:num_requests_'+key+r'\{[^\n]+\} ([0-9.e+-]+)$',body,re.M)) for key in ('running','waiting')}
assert all(('vllm:num_requests_'+key+'{') in body for key in values), 'missing decoder queue metrics'
with Path('evidence/mvpfix/wp1/batch-admission.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),**values})+'\n')
assert not any(values.values()), 'decoder busy; batch not started'
PYCODE
"$WP1_PY" prototypes/lane-decode-proto/stack.py --state .wp1 --cert "$TMPDIR/cert.pem" --key "$TMPDIR/key.pem" --port 17871 > "$TMPDIR/stack.log" 2>&1 &
WP1_STACK=$!
for _ in $(seq 1 30); do if curl -kfsS --max-time 1 https://127.0.0.1:17871/ > /dev/null 2>&1; then break; fi; sleep 1; done
for WP1_CASE in "${@:-same}"; do
  if "$WP1_PY" prototypes/lane-decode-proto/run.py "$WP1_CASE"; then :; else
    WP1_RESULT=$?
    "$WP1_PY" prototypes/lane-decode-proto/score.py
    exit "$WP1_RESULT"
  fi
done
"$WP1_PY" prototypes/lane-decode-proto/score.py
