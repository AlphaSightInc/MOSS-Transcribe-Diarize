"""WP7 case 3 on WP17's own stack; retained public-corpus scratch only."""
import importlib.util,sys,ssl
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('identity_stress',ROOT/'prototypes/identity-stress/run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
phase=sys.argv[1]
m.OUT=ROOT/f'evidence/mvpfix/wp17/recognition-{phase}';m.OUT.mkdir(exist_ok=True)
m.SCRATCH=ROOT/f'runs/wp17/recognition-{phase}';m.SCRATCH.mkdir(exist_ok=True)
Client=m.Client
m.Client=lambda base,context:Client('https://127.0.0.1:17877',context)
p=m.Probe()
if phase=='before':p.run('recognition')
else:
    adam=m.audio('interview_adam_frank_180s',49,73)
    def enroll(p,ident,ids,elapsed,done):
        if ids and elapsed>=4 and not done:done.append(m.emit('enroll',response=p.name(ident,ids[0],'WP17 Adam')))
    for lane in ('system','microphone'):
        for profile in p.bank():p.action('DELETE',f"/api/voiceprints/{profile['id']}")
        speech=adam[:12*32000];zero=bytes(len(speech))
        p.meeting('enroll-'+lane,speech if lane=='system' else zero,[(0,12,'Adam')],mic=speech if lane=='microphone' else None,actions=enroll)
        for target in ('system','microphone'):
            speech=adam[12*32000:24*32000]
            p.meeting('recognize-'+lane+'-to-'+target,speech if target=='system' else zero,[(0,12,'Adam')],mic=speech if target=='microphone' else None,expected_name='WP17 Adam')
