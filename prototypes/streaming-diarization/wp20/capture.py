"""WP20 baseline: full-reference quality + same 24/48-second WP17 duration inputs.
One command with isolated stack running: PYTHONPATH=. python prototypes/streaming-diarization/wp20/capture.py
"""
import sys, json, ssl, importlib.util
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tests.e2e import verify_demo_lanes as lanes
OUT=ROOT/'evidence/mvpfix/wp20';SCRATCH=ROOT/'runs/wp20'
BASE='https://127.0.0.1:17880'
class Retain(lanes.Client):
    def call(self,method,path,body=None):
        result=super().call(method,path,body)
        if method=='GET' and ('snapshot' in path or path.startswith('/api/meetings/')):
            with (SCRATCH/'surfaces.jsonl').open('a') as f:f.write(json.dumps(dict(path=path,result=result))+'\n')
        return result
for case in ('alternation','overlap'):
    result=lanes.run_case(BASE,ssl._create_unverified_context(),case,client=Retain(BASE,ssl._create_unverified_context()))
    (OUT/f'baseline-{case}.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
spec=importlib.util.spec_from_file_location('stress',ROOT/'prototypes/identity-stress/run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.OUT=OUT/'durations';m.OUT.mkdir(exist_ok=True)
m.SCRATCH=SCRATCH/'durations';m.SCRATCH.mkdir(exist_ok=True)
m.Client=lambda base,context: Retain(BASE,context)
p=m.Probe()
for seconds in (24,48):
    for case in ('alternation','overlap'):
        system=lanes.lane_pcm(lanes.CORPUS/'interview_bill_ackman_60s/audio.wav',seconds)
        mic=lanes.lane_pcm(lanes.CORPUS/'interview_keyu_jin_60s/audio.wav',seconds,.03)
        if case=='alternation':
            half=seconds*16000;system=system[:half]+bytes(half);mic=bytes(half)+mic[half:]
        p.meeting(f'{seconds}-{case}',system,[],mic=mic)
