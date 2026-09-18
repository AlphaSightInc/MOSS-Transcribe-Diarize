"""24/48-second producer isolation. Identical lane PCM in paired and lane-alone runs.
Alternation: first half system, second half microphone, source-clock slices preserved.
Overlap: both lanes throughout. No guessed partial-window WER references.
"""
import importlib.util,sys,ssl,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import Client,lane_pcm,CORPUS
spec=importlib.util.spec_from_file_location('stress',ROOT/'prototypes/identity-stress/run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.OUT=ROOT/'evidence/mvpfix/wp17/durations';m.OUT.mkdir(exist_ok=True)
m.SCRATCH=ROOT/'runs/wp17/durations';m.SCRATCH.mkdir(exist_ok=True)
m.Client=lambda base,context:Client('https://127.0.0.1:17877',context)
p=m.Probe()
for seconds in (24,48):
 for case in ('alternation','overlap'):
  system=lane_pcm(CORPUS/'interview_bill_ackman_60s/audio.wav',seconds)
  mic=lane_pcm(CORPUS/'interview_keyu_jin_60s/audio.wav',seconds,.03)
  if case=='alternation':
   half=seconds*16000
   system=system[:half]+bytes(half);mic=bytes(half)+mic[half:]
  for arm in ('paired','system-alone','microphone-alone'):
   tag=f'{seconds}-{case}-{arm}'
   p.meeting(tag,system if arm!='microphone-alone' else bytes(len(system)),[],mic=mic if arm!='system-alone' else bytes(len(mic)))
