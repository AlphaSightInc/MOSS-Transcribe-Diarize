"""Retained WP20 control: identical speech, different full-tape silence context.
Two paired repeats distinguish overlap-stage damage from standalone decoder variation.
No thresholds or endpoint/window lengths changed in production.
"""
import json,sys,time,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner
from moss_transcribe_diarize.transcript_parser import parse_transcript
from moss_transcribe_diarize.lane_word_oracle import words,distance
from tests.e2e.verify_demo_lanes import reference_inputs
S=ROOT/'runs/wp20';O=ROOT/'evidence/mvpfix/wp20'
cases={k:json.loads((O/f'baseline-{k}.json').read_text()) for k in ('alternation','overlap')}
pcm={k:(S/f"{v['meeting']}-system.pcm").read_bytes() for k,v in cases.items()}
n=len(pcm['overlap']);assert pcm['alternation'][:n]==pcm['overlap'] and not any(pcm['alternation'][n:])
runner=VllmRunner(base_url='http://127.0.0.1:18120/v1',model='OpenMOSS-Team/MOSS-Transcribe-Diarize')
original=runner._post_multipart;ledger=O/'replay-requests.jsonl'
def counted(*a,**kw):
 total=len((O/'stack-requests.jsonl').read_text().splitlines())+len(ledger.read_text().splitlines())
 assert total<500
 with ledger.open('a') as f:f.write(json.dumps(dict(time=time.monotonic(),request=total+1,control='padding'))+'\n')
 return original(*a,**kw)
runner._post_multipart=counted
windowed=WindowedRunner(runner)
ref=reference_inputs(.03)['system']['reference'];records=[]
for trial in (1,2):
 for case,raw in pcm.items():
  p=S/'padding.wav'
  with wave.open(str(p),'wb') as f:f.setparams((1,2,16000,0,'NONE','not compressed'));f.writeframes(raw)
  result=windowed.transcribe(p,max_new_tokens=12000,max_length=16384,decoding='greedy',temperature=None)
  text=' '.join(s.text for s in parse_transcript(result.text))
  row=dict(trial=trial,case=case,samples=len(raw)//2,score=distance(words(ref),words(text)))
  records.append(row);print(json.dumps(row),flush=True)
  with (S/'padding-raw.jsonl').open('a') as f:f.write(json.dumps(dict(**row,text=result.text))+'\n')
(O/'padding-control.json').write_text(json.dumps(dict(speech_prefix_equal_samples=n//2,alternation_extra_zero_samples=(len(pcm['alternation'])-n)//2,records=records),indent=2)+'\n')
