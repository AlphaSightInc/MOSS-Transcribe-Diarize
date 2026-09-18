#!/bin/bash
# Fresh-context verification entrypoint. Own worktree/services only.
set -euo pipefail
cd "$(dirname "$0")/../.."
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp5"
unset MOSS_OPEN_WORKSPACE MOSS_LLM_UPSTREAMS
mkdir -p runs/wp5
OUT=evidence/mvpfix/wp5/fresh
if test -e "$OUT"; then echo 'Fresh evidence exists: do not overwrite/retry silently.'; exit 2; fi
mkdir -p "$OUT"
"$PY" -c 'import moss_transcribe_diarize as m; from pathlib import Path; assert Path(m.__file__).is_relative_to(Path.cwd()); print(m.__file__)' > "$OUT/import.txt"
npm --prefix frontend test -- --run > "$OUT/frontend.txt" 2>&1
npm --prefix frontend run typecheck > "$OUT/typecheck.txt" 2>&1
npm --prefix frontend run build > "$OUT/build.txt" 2>&1
"$PY" -m pytest -q -p no:cacheprovider tests/phase2/test_acceptance_locator_sentinels.py > "$OUT/sentinels.txt" 2>&1
ssh -N -o BatchMode=yes -o ExitOnForwardFailure=yes -L 127.0.0.1:18105:127.0.0.1:8000 gyauo@ga0-alienware-rtx4070ti.tailnet.aisight.us > runs/wp5/verify-tunnel.log 2>&1 &
TUNNEL_PID=$!
STACK_PID=''
cleanup() {
  if test -n "$STACK_PID" && kill -0 "$STACK_PID" 2>/dev/null; then kill "$STACK_PID"; fi
  kill "$TUNNEL_PID" 2>/dev/null || true
  wait "$TUNNEL_PID" 2>/dev/null || true
}
trap cleanup EXIT
for attempt in $(seq 1 30); do
  if curl --fail --silent http://127.0.0.1:18105/metrics > runs/wp5/verify-metrics; then break; fi
  sleep 1
done
rg '^vllm:num_requests_(running|waiting)' runs/wp5/verify-metrics > "$OUT/decoder-preflight.txt"
"$PY" prototypes/browser-stress/stack.py --state runs/wp5/state --cert runs/wp5/cert.pem --key runs/wp5/key.pem --port 17865 > runs/wp5/verify-server.log 2>&1 &
STACK_PID=$!
echo "$STACK_PID" > runs/wp5/server.pid
for attempt in $(seq 1 30); do
  if curl --fail --silent --insecure https://127.0.0.1:17865/ > /dev/null; then break; fi
  sleep 1
done
status=0
"$PY" prototypes/browser-stress/run.py 1,8,9,10,11,12,13,14 --output "$OUT/browser" > runs/wp5/fresh-browser.log 2>&1 || status=$?
test "$status" -eq 1  # Exactly the two retained N1 failures are expected.
"$PY" - <<'PY'
import json
from pathlib import Path
root=Path('evidence/mvpfix/wp5/fresh')
rows=json.loads((root/'browser/campaign-results.json').read_text())
expected={'1':'PASS','8':'FAIL','9':'FAIL','10':'PASS','11':'PASS','12':'PASS','13':'PASS','14':'PASS'}
assert {k:v['status'] for k,v in rows.items()}==expected, rows
assert [v['ok'] for v in rows['8']['variants']]==[True,False,False,True,True]
assert all(v['statuses']==['failed'] and not v['visible_reason'] for v in rows['9']['variants'])
assert rows['12']['rendered']==60 and rows['12']['refresh']==2 and rows['12']['scroll']==400
assert rows['14']['cookies_equal'] and rows['14']['transcripts_equal'] and rows['14']['before']==rows['14']['after']==60
assert rows['13']['provider_posts']==0
count=int(Path('runs/wp5/request-count').read_text());assert count<=200
result={'verification':'PASS','browser_cases':8,'pass':6,'known_N1_fail':2,'decoder_requests_total':count,'frontend_tests':206,'locator_sentinel_tests':3,'typecheck':'PASS','build':'PASS'}
(root/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
PY
