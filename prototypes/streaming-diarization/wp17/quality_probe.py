"""WP17 retained bench: compare raw lane-only decode with producer/saved surfaces.
One command: PYTHONPATH=. python prototypes/streaming-diarization/wp17/quality_probe.py.
Public text retained privately; counts and diffs exported separately after adjudication.
"""
import sys,json,ssl,importlib.util,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tests.e2e import verify_demo_lanes as lanes
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.transcript_parser import parse_transcript
from moss_transcribe_diarize.lane_word_oracle import words,distance
out=ROOT/'runs/wp17'
class Retain(lanes.Client):
    def call(self,method,path,body=None):
        result=super().call(method,path,body)
        if method=='GET' and ('snapshot' in path or path.startswith('/api/meetings/')):
            with (out/'surfaces.jsonl').open('a') as f:f.write(json.dumps(dict(path=path,result=result))+'\n')
        return result

def main():
    phase=sys.argv[1] if len(sys.argv)>1 else 'before'
    for case in ('alternation','overlap'):
        c=Retain('https://127.0.0.1:17877',ssl._create_unverified_context())
        result=lanes.run_case(c._base,c._context,case,client=c)
        (ROOT/f'evidence/mvpfix/wp17/{phase}-{case}.json').write_text(json.dumps(result,indent=2)+'\n')
        print(case,json.dumps(result),flush=True)
if __name__=='__main__':main()
