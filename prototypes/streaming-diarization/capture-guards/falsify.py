"""Decode the strongest local-speech false-positive chunk at each quiet gain."""
import json,time
from prototype import *
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
from moss_transcribe_diarize.app.live_session import FrozenSpan
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.transcript_parser import parse_transcript
s=read('interview_bill_ackman_60s');n=read('interview_keyu_jin_60s')
rows=json.loads((ROOT/'evidence/mvpfix/wp3/chunks.json').read_text()); all_cases={name:x for name,x,_ in cases(s,n)}
dec=RunnerBoundedWavInference(VllmRunner(base_url='http://127.0.0.1:18103/v1',model='OpenMOSS-Team/MOSS-Transcribe-Diarize'),max_samples=8000,scratch_dir=ROOT/'evidence/mvpfix/wp3')
for level in [-10,-15,-20]:
    candidates=[r for r in rows if r['name'].startswith(f'near{level}_') and r['decision']=='leak-suspect']
    if not candidates:continue
    row=max(candidates,key=lambda r:float(n[r['start_sample']:r['start_sample']+8000]@n[r['start_sample']:r['start_sample']+8000]));start=row['start_sample']; texts=[]
    for x in [n[start:start+8000]*10**(level/20),all_cases[row['name']][start:start+8000]]:
        out=dec.transcribe_pcm(span=FrozenSpan(id=1,epoch=1,start_sample=0,end_sample=8000,reason='end_silence'),pcm=pcm(x));texts.append(' '.join(v.text for v in parse_transcript(out.transcript)))
    print(json.dumps(dict(**row,vs_lane_alone=metrics(*texts),guard_vs_lane_alone=metrics(texts[0],''))),flush=True)
