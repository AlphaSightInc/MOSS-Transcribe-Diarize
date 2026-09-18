"""Run existing E2E assertions with COMMON heartbeat/single-meeting discipline.
The concurrent-session case is excluded by the user's explicit single-meeting cap.
No assertions are rewritten. Wait for finalization before admitting another meeting.
"""
import io
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'evidence/mvpfix/wp1'
BASE = 'https://127.0.0.1:17871'
os.environ['MOSS_BASE'] = BASE
case = sys.argv[1]
path = ROOT / 'tests/e2e' / (case + '.py')
source = path.read_text()
if case == 'stress_lifecycle':
    begin = source.index('print("\\n=== 6.')
    end = source.index('print("\\n=== 7.')
    source = source[:begin] + 'print("SKIP concurrent-session case: user single-meeting limit")\n' + source[end:]

original = urllib.request.urlopen
health_sequence = {}
health_lanes = {}


class CachedResponse(io.BytesIO):
    def __init__(self, response, body):
        super().__init__(body)
        self.status, self.headers = response.status, response.headers


def request_with_lease(request, *args, **kwargs):
    url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
    headers = dict(request.header_items()) if isinstance(request, urllib.request.Request) else {}
    if url.endswith('/frames'):
        sid = url.rsplit('/', 2)[-2]
        frame = json.loads(request.data)
        lanes = health_lanes.setdefault(sid, {})
        lanes[frame['lane']] = {'state':'capturing','device_epoch':frame['device_epoch'],
                              'dropped_frames':0,'discontinuities':0,'failure_code':None}
        for lane in ('system','microphone'):
            lanes.setdefault(lane, dict(lanes[frame['lane']]))
        seq = health_sequence.get(sid, 0)
        health_sequence[sid] = seq + 1
        body = {'schema':'moss-live-helper-health.v1','instance_id':'wp1-e2e','sequence':seq,
                'sent_monotonic_ns':time.monotonic_ns(),'helper_version':'wp1-e2e',
                'state':'capturing','lanes':lanes}
        heartbeat = urllib.request.Request(url.removesuffix('/frames') + '/heartbeat',
            data=json.dumps(body).encode(),method='POST',headers=headers)
        with original(heartbeat, *args, **kwargs) as response:
            response.read()
    response = original(request, *args, **kwargs)
    if not url.endswith('/stop'):
        return response
    body = response.read()
    cached = CachedResponse(response, body)
    response.close()
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        poll = urllib.request.Request(url.removesuffix('/stop') + '/snapshot', headers=headers)
        with original(poll, *args, **kwargs) as current:
            state = json.loads(current.read())['snapshot']['session']
        if state.get('finalization_status') in ('final','failed','unavailable') or not state['accepted_samples']:
            break
        time.sleep(.25)
    else:
        raise RuntimeError('E2E finalization did not settle; no next meeting admitted')
    return cached


urllib.request.urlopen = request_with_lease
latencies = HERE / 'scratch/latencies.jsonl'
before = len(latencies.read_text().splitlines())
sys.argv = [str(path)] + (['--base', BASE, '--allow-local-self-signed', '--seconds', '20'] if case == 'verify_demo_lanes' else [])
status = 1
try:
    exec(compile(source, str(path), 'exec'), {'__name__':'__main__','__file__':str(path)})
    status = 0
except SystemExit as exc:
    status = exc.code or 0
finally:
    after = len(latencies.read_text().splitlines())
    result = {'case':case,'first':before+1,'last':after,'count':after-before,'exit_code':status,
              'adaptations':['heartbeat every frame','wait for finalization before next meeting'],
              'excluded':['concurrent session case'] if case == 'stress_lifecycle' else [],
              'capture_seconds':20 if case == 'verify_demo_lanes' else None}
    (OUT / ('e2e-' + case + '.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(result))
raise SystemExit(status)
