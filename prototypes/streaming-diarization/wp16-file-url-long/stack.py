"""WP16 measurement-only wrappers: record window metadata, never words/audio."""
import importlib.util, json, threading, time
from pathlib import Path
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner
original=WindowedRunner._decode_window
lock=threading.Lock()
def measured(self,audio,window,kwargs):
    started=time.monotonic(); row=dict(thread=threading.get_ident(),index=window.index,start=window.start,end=window.end,started=started)
    try:
        result=original(self,audio,window,kwargs)
        row.update(tokens=result.generated_tokens,diagnostics=result.window_diagnostics)
        return result
    except Exception as exc:
        row.update(exception=type(exc).__name__,condition=getattr(exc,'condition',None)); raise
    finally:
        row['elapsed']=time.monotonic()-started
        with lock,Path('evidence/mvpfix/wp16/windows.jsonl').open('a') as stream: stream.write(json.dumps(row)+'\n')
WindowedRunner._decode_window=measured
spec=importlib.util.spec_from_file_location('local_stack', 'prototypes/streaming-diarization/draft-lane/run_local_stack.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); module.main()
