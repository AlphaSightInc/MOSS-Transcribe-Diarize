"""Measurement-only observer; no changed policy or protocol."""
import importlib.util,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
original=FingerprintAlbum.observe

def observe(self,**kwargs):
    result=original(self,**kwargs)
    row={k:v for k,v in kwargs.items() if k!='vector'}
    row.update(time=time.monotonic(),album=id(self),disposition=result)
    with (ROOT/'evidence/mvpfix/wp7/album-events.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
    return result
FingerprintAlbum.observe=observe
spec=importlib.util.spec_from_file_location('local_stack',ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main()
