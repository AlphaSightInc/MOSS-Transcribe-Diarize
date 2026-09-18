"""WP12 measurement instrumentation only; no production policy changes."""
import os, sys, time, json, threading, runpy
from pathlib import Path
ROOT=Path.cwd()
ARM=os.environ.get('WP12_ARM','lane')
source_root={'mono':ROOT/'.wp12','mono-traced':ROOT/'.wp12','serial':ROOT/'.wp12/base-b316','serial-traced':ROOT/'.wp12/base-b316'}.get(ARM,ROOT)
sys.path.insert(0,str(source_root))
OUT=ROOT/'evidence/mvpfix/wp12'
lock=threading.Lock()
context=threading.local()
def emit(kind,**data):
    with lock, (OUT/'trace.jsonl').open('a') as f:
        f.write(json.dumps(dict(time=time.monotonic(),arm=ARM,kind=kind,**data))+'\n')
import moss_transcribe_diarize
emit("source",package=moss_transcribe_diarize.__file__)
from moss_transcribe_diarize.app.vllm_runner import VllmRunner
original=VllmRunner._post_multipart
capacity=threading.BoundedSemaphore(2)
def request(self,*a,**k):
    with capacity:
        with lock:
            path=OUT/'requests.jsonl'
            count=len(path.read_text().splitlines()) if path.exists() else 0
            if count>=1200:raise RuntimeError('WP12 request cap exhausted')
            with path.open('a') as f:f.write(json.dumps(dict(request=count+1,time=time.monotonic(),arm=ARM))+'\n')
        start=time.monotonic()
        try:return original(self,*a,**k)
        finally:emit('request',request=count+1,start=start,seconds=time.monotonic()-start,thread=threading.current_thread().name)
VllmRunner._post_multipart=request
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime
record=LiveServiceRuntime._record_event
def event(self,state,kind,payload):
    if kind.startswith(('terminal_', 'canonical_', 'rolling_')) or kind in ('stop_requested','session_closed','identity_finalized'):
        emit('event',event=kind,payload=payload,pending=self._canonical_scheduler.pending_signals,queues=self._operator_queue_snapshot())
    return record(self,state,kind,payload)
LiveServiceRuntime._record_event=event
# Attribute drain time to the actual jobs, not queue snapshots alone.
def timed_method(cls, name):
    original_method=getattr(cls,name)
    def measured(self,*args,**kwargs):
        start=time.monotonic();emit('phase_start',phase=name,thread=threading.current_thread().name)
        try:return original_method(self,*args,**kwargs)
        finally:
            owners=getattr(args[0].coordinator,'_lane_preparers',{})
            emit('phase_end',phase=name,start=start,seconds=time.monotonic()-start,thread=threading.current_thread().name,owners={lane:id(p.evidence_provider) for lane,p in owners.items()})
    setattr(cls,name,measured)
for name in ('_process_in_flight_item','_process_refinement_item','_finalize_identity_locked'):
    timed_method(LiveServiceRuntime,name)
drain=LiveServiceRuntime._wait_for_drain
async def measured_drain(self,*args,**kwargs):
    start=time.monotonic();emit('drain_start')
    try:return await drain(self,*args,**kwargs)
    finally:emit('drain_end',start=start,seconds=time.monotonic()-start)
LiveServiceRuntime._wait_for_drain=measured_drain
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
terminal=TerminalTranscriptFinalizer.finalize
def finalize(self,**k):
    start=time.monotonic();emit('terminal_start',samples=k['plan'].end_sample,speakers=list(k['canonical_speakers']))
    try:
        result=terminal(self,**k)
        emit('terminal_end',start=start,seconds=time.monotonic()-start,accounting=result.accounting.to_dict())
        return result
    except Exception as e:emit('terminal_error',error=type(e).__name__);raise
TerminalTranscriptFinalizer.finalize=finalize
from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
if hasattr(WeSpeakerLiveEvidenceProvider,'revision_reader'):
    reader=WeSpeakerLiveEvidenceProvider.revision_reader
    def measured_reader(self):
        result=reader(self)
        emit('revision_reader',provider=id(result),owner=id(self))
        return result
    WeSpeakerLiveEvidenceProvider.revision_reader=measured_reader
score=WeSpeakerLiveEvidenceProvider.score
def scored(self,**k):
    start=time.monotonic()
    context.score=dict(provider=id(self),span=k['span'].id,reason=k['span'].reason,offset=k['span'].start_sample)
    try:result=score(self,**k)
    finally:context.score=None
    emit('scores',provider=id(self),span=k['span'].id,reason=k['span'].reason,start_sample=k['span'].start_sample,end_sample=k['span'].end_sample,seconds=time.monotonic()-start,album=list(self._album.speakers()) if self._album else None,pending={s:v[1] for s,v in self._pending_vectors.get(k['span'].id,{}).items()},scores=[dict(local=x.local_speaker,canonical=x.canonical_speaker,score=x.score) for x in result])
    return result
WeSpeakerLiveEvidenceProvider.score=scored
prepare=BoundedCausalIdentityPreparer.prepare
def prepared(self,**k):
    start=time.monotonic();result=prepare(self,**k)
    emit('identity',provider=id(self.evidence_provider),span=k['span'].id,reason=k['span'].reason,seconds=time.monotonic()-start,allowed=k.get('allowed_speakers'),min_match_score=self.config.min_match_score,min_match_margin=self.config.min_match_margin,diagnostics=dict(result.proposed_snapshot.diagnostics),status=result.status)
    return result
BoundedCausalIdentityPreparer.prepare=prepared
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
embed=_OnnxWeSpeakerEmbedder.embed
def measured_embed(self,wav_path,intervals):
    start=time.monotonic();details=getattr(context,'score',None) or {}
    try:return embed(self,wav_path,intervals)
    finally:emit('embedding',start=start,seconds=time.monotonic()-start,intervals=intervals,audio_seconds=sum(b-a for a,b in intervals),**details)
_OnnxWeSpeakerEmbedder.embed=measured_embed
# Same current harness recipe and arguments for both checked-out production arms.
runpy.run_path(str(ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py'),run_name='__main__')
