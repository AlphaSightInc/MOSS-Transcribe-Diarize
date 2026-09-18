"""WP17 measurement-only producer trace. Public-corpus text stays in ignored scratch."""
import json,sys,threading,time,runpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app import live_lane_decode
lock=threading.Lock()
def emit(kind,**row):
    with lock:
        with (ROOT/'runs/wp17/producer-trace.jsonl').open('a') as f:f.write(json.dumps(dict(kind=kind,time=time.monotonic(),**row))+'\n')
original=LiveCoordinator._decode
def decode(self,span,pcm):
    result=original(self,span,pcm)
    lanes=[lane for lane,tape in self.lane_tapes.items() if tape.read(start_sample=span.start_sample,end_sample=span.end_sample)==pcm]
    emit('canonical',lanes=lanes,session=self.session_key,span=span.id,start=span.start_sample,end=span.end_sample,text=result.transcript)
    return result
LiveCoordinator._decode=decode
revision=live_lane_decode.revision_segments
def revisions(c,lane,span,pcm,text,authority):
    result=revision(c,lane,span,pcm,text,authority)
    emit('revision',session=c.session_key,lane=lane,start=span.start_sample,end=span.end_sample,authority=str(authority),text=text)
    return result
live_lane_decode.revision_segments=revisions
runpy.run_path(str(ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py'),run_name='__main__')
