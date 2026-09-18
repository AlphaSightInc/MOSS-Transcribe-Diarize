"""Same PCM, no lane merge. Sequential requests, counts retained; text stays scratch."""
import sys,json,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tests.e2e.verify_demo_lanes import reference_inputs
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.transcript_parser import parse_transcript
from moss_transcribe_diarize.lane_word_oracle import words,distance
runner=VllmRunner(base_url='http://127.0.0.1:18117/v1',model='OpenMOSS-Team/MOSS-Transcribe-Diarize')
results=[]
for gain in (.03,1.):
 for lane,row in reference_inputs(gain).items():
  path=ROOT/f'runs/wp17/alone-{lane}-{gain}.wav'
  with wave.open(str(path),'wb') as w:w.setparams((1,2,16000,0,'NONE','not compressed'));w.writeframes(row['pcm'])
  with (ROOT/'evidence/mvpfix/wp17/alone-requests.jsonl').open('a') as f:f.write(json.dumps({'lane':lane,'gain':gain})+'\n')
  result=runner.transcribe(path,max_new_tokens=12000)
  text=' '.join(s.text for s in parse_transcript(result.text))
  record=dict(lane=lane,gain=gain,text=text,segments=result.text,score=distance(words(row['reference']),words(text)))
  results.append(record)
  print(json.dumps(record),flush=True)
  (ROOT/'runs/wp17/alone.json').write_text(json.dumps(results,indent=2))
