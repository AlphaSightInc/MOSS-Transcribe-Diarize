"""THROWAWAY stack launcher. Everything written stays inside this worktree."""
from pathlib import Path
import os, sys, runpy, threading, time, json
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
os.environ['TMPDIR'] = str(HERE/'scratch')
import moss_transcribe_diarize.app
moss_transcribe_diarize.app.__path__.insert(0, str(HERE/'runtime/app'))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
original=VllmRunner._post_multipart
lock=threading.Lock()
count=len((HERE/'scratch/latencies.jsonl').read_text().splitlines()) if (HERE/'scratch/latencies.jsonl').exists() else 0
def measured(self,*args,**kwargs):
    global count
    with lock:
        count += 1
        if count > 650: raise RuntimeError('WP1 request budget exhausted')
        request_id=count
    start=time.monotonic()
    try:return original(self,*args,**kwargs)
    finally:
        with lock, (HERE/'scratch/latencies.jsonl').open('a') as f:
            f.write(json.dumps({'request':request_id,'start':start,'seconds':time.monotonic()-start,'thread':threading.current_thread().name})+'\n')
VllmRunner._post_multipart=measured
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime
original_snapshot=LiveServiceRuntime.snapshot
def observed(self,*args,**kwargs):
    result=original_snapshot(self,*args,**kwargs)
    with (HERE/'scratch/queues.jsonl').open('a') as f:
        f.write(json.dumps({'time':time.monotonic(),'pending_signals':self._canonical_scheduler.pending_signals,**self._operator_queue_snapshot()})+'\n')
    return result
LiveServiceRuntime.snapshot=observed
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
original_decode=RunnerBoundedWavInference.transcribe_pcm
def span_measured(self,*,span,pcm):
    started=time.monotonic()
    try:return original_decode(self,span=span,pcm=pcm)
    finally:
        with (HERE/'scratch/spans.jsonl').open('a') as f:
            f.write(json.dumps({'start':started,'seconds':time.monotonic()-started,'samples':span.sample_count,'reason':span.reason,'all_zero':not any(pcm)})+'\n')
RunnerBoundedWavInference.transcribe_pcm=span_measured
source=(ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py').read_text().replace('127.0.0.1:18000','127.0.0.1:18101')
exec(compile(source,str(ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py'),'exec'),{'__name__':'__main__','__file__':str(ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py')})
