"""WP20 retained LOGIC measurement probe: replay producer intervals alone, then lane-local endpoints.
Uses real bounded production inference with unchanged token cap/salvage behavior.
One command after capture: PYTHONPATH=. python prototypes/streaming-diarization/wp20/replay.py
No concurrent calls. All calls share a hard total 500 ledger with the stack.
"""
import json, sys, time, wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.app.live_provider_bundle import bounded_live_inference
from moss_transcribe_diarize.app.live_session import FrozenSpan
from moss_transcribe_diarize.transcript_parser import parse_transcript
from moss_transcribe_diarize.lane_word_oracle import words,distance
S=ROOT/'runs/wp20'; O=ROOT/'evidence/mvpfix/wp20'
trace=[json.loads(x) for x in (S/'trace.jsonl').read_text().splitlines()]
runner=VllmRunner(base_url='http://127.0.0.1:18120/v1',model='OpenMOSS-Team/MOSS-Transcribe-Diarize')
original=runner._post_multipart
ledger=O/'replay-requests.jsonl'
def counted(*a,**kw):
    total=sum(len(p.read_text().splitlines()) for p in (S/'state/requests.jsonl',ledger) if p.exists())
    if total>=500: raise RuntimeError('WP20 total request budget exhausted')
    with ledger.open('a') as f:f.write(json.dumps(dict(time=time.monotonic(),request=total+1))+'\n')
    return original(*a,**kw)
runner._post_multipart=counted
canonical=bounded_live_inference(runner,max_samples=120000,scratch_dir=S/'tmp')
rolling=bounded_live_inference(runner,max_samples=160000,scratch_dir=S/'tmp')
raws={};reuse={};records=[]
def plain(text):return ' '.join(x.text for x in parse_transcript(text))
def run(session,lane,span,stage):
    raw=raws.setdefault((session,lane),(S/f'{session}-{lane}.pcm').read_bytes())
    pcm=raw[span['start_sample']*2:span['end_sample']*2]
    assert len(pcm)==2*(span['end_sample']-span['start_sample'])
    frozen=FrozenSpan(id=span.get('id',0),epoch=span.get('epoch',0),start_sample=span['start_sample'],end_sample=span['end_sample'],reason=span['reason'])
    started=time.monotonic()
    if stage=='terminal':
        path=S/'replay.wav'
        with wave.open(str(path),'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(pcm)
        text=runner.transcribe(path,max_new_tokens=12000).text if any(pcm) else ''
    else:text=(rolling if stage=='rolling' else canonical).transcribe_pcm(span=frozen,pcm=pcm).transcript
    return text,pcm,time.monotonic()-started

def save(row):
    records.append(row)
    with (S/'replay.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    print(json.dumps({k:v for k,v in row.items() if k not in ('text','baseline_text')}),flush=True)

# Every actual producer request gets an independent, single-lane replay with exact geometry.
for row in trace:
    if row['kind'] not in ('canonical','revision'):continue
    stage='canonical' if row['kind']=='canonical' else row['authority']
    lanes=row['lanes'] if stage=='canonical' else [row['lane']]
    for lane in lanes:
        text,pcm,elapsed=run(row['session'],lane,row['span'],stage)
        if stage=='canonical':reuse[(pcm,row['span']['reason'])]=text
        save(dict(arm='same-boundary-alone',session=row['session'],lane=lane,stage=stage,span=row['span'],text=text,baseline_text=row['text'],elapsed=elapsed,difference=distance(words(plain(row['text'])),words(plain(text)))))
# Reuse exact same PCM+freeze reason only after the independent same-boundary replay above.
for row in trace:
    if row['kind']!='local_boundary':continue
    span={k:row[k] for k in ('start_sample','end_sample','reason')}
    raw=raws[(row['session'],row['lane'])];pcm=raw[span['start_sample']*2:span['end_sample']*2]
    key=(pcm,span['reason']);reused=key in reuse
    if reused:text,elapsed=reuse[key],0.0
    else:text,_,elapsed=run(row['session'],row['lane'],span,'canonical');reuse[key]=text
    save(dict(arm='lane-local',session=row['session'],lane=row['lane'],stage='canonical',span=span,text=text,elapsed=elapsed,reused_exact_pcm_and_reason=reused))
