"""Retained transcript diffs by lane and producer; no guessed ground truth for partial clips."""
import json,sys,difflib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.lane_word_oracle import words,distance
from moss_transcribe_diarize.transcript_parser import parse_transcript
OUT=ROOT/'evidence/mvpfix/wp17';SCRATCH=ROOT/'runs/wp17'
def diff(a,b):
    return [dict(operation=op,reference_range=[i,j],observed_range=[k,l],reference=a[i:j],observed=b[k:l])
            for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes() if op!='equal']
def tokens(rows,lane):return words(' '.join(r['text'] for r in rows if r.get('source_lane')==lane))
def surface(raw,name):
    if name=='saved':return raw['saved']['transcript']['segments']
    return raw[name]['snapshot']['session']['effective_transcript']
def trace_tokens(row):return words(' '.join(s.text for s in parse_transcript(row['text'])))
trace=[json.loads(x) for x in (SCRATCH/'producer-trace.jsonl').read_text().splitlines()]
results=[]
for seconds in (24,48):
 for case in ('alternation','overlap'):
  paired=json.loads((SCRATCH/f'durations/{seconds}-{case}-paired.json').read_text())
  for lane in ('system','microphone'):
   alone=json.loads((SCRATCH/f'durations/{seconds}-{case}-{lane}-alone.json').read_text())
   row=dict(seconds=seconds,case=case,lane=lane,comparison='paired vs identical lane PCM alone; NOT ground-truth WER',surfaces={})
   for name in ('pre','final','saved'):
    a,b=tokens(surface(alone,name),lane),tokens(surface(paired,name),lane)
    row['surfaces'][name]={'edit_counts':distance(a,b),'diff':diff(a,b)}
   def spans(ident):
    return {(r['kind'],r.get('authority','canonical'),r['start'],r['end']):trace_tokens(r)
      for r in trace if r['session']==ident and (r.get('lane')==lane or r.get('lanes')==[lane])}
   a,b=spans(alone['id']),spans(paired['id'])
   row['producers']=[]
   for key,ws in b.items():
    item=dict(producer=key[1],start_sample=key[2],end_sample=key[3],paired_words=len(ws),identical_control_window=key in a)
    if key in a:item.update(edit_counts=distance(a[key],ws),diff=diff(a[key],ws))
    row['producers'].append(item)
   row['control_window_count']=len(a)
   results.append(row)
(OUT/'duration-diffs.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps([dict(seconds=r['seconds'],case=r['case'],lane=r['lane'],saved=r['surfaces']['saved']['edit_counts'],producer_windows=len(r['producers'])) for r in results],indent=2))
