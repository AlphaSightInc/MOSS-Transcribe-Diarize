"""WP20 retained measurement bench trace: actual admitted PCM, endpoint partitions and producer text.
State lives in ignored runs/wp20; no policies or production code change.
"""
import json, runpy, sys, threading, time
from pathlib import Path
from dataclasses import asdict, replace
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
from moss_transcribe_diarize.app import live_lane_decode
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _speech_provider
SCRATCH = ROOT / 'runs/wp20'
config = LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
lock = threading.Lock()
def emit(kind, **row):
    with lock:
        with (SCRATCH/'trace.jsonl').open('a') as f:
            f.write(json.dumps(dict(kind=kind,time=time.monotonic(),**row))+'\n')
accept = LiveCoordinator.accept_frame
def traced_accept(self, frame):
    result = accept(self, frame)
    if not hasattr(self, '_wp20'):
        self._wp20 = {lane: (_speech_provider(config), EndpointPolicy(self.endpoint_policy.config)) for lane in ('system','microphone')}
    start, end = result.accepted_start_sample, result.accepted_end_sample
    for lane, raw in frame.lane_pcm:
        pcm = bytes(len(raw)) if dict(frame.lane_silent).get(lane,False) else raw
        with (SCRATCH/f'{self.session_key}-{lane}.pcm').open('ab') as f: f.write(pcm)
        provider, policy = self._wp20[lane]
        for obs in provider.observe(frame=replace(frame,pcm=pcm,analysis_pcm=None),start_sample=start,end_sample=end):
            for span in policy.observe(obs): emit('local_boundary',session=self.session_key,lane=lane,**asdict(span))
    for span in result.frozen_spans: emit('mixed_boundary',session=self.session_key,**asdict(span))
    return result
LiveCoordinator.accept_frame = traced_accept
stop = LiveCoordinator.stop_endpoint
def traced_stop(self):
    if hasattr(self,'_wp20'):
        for lane, (_,policy) in self._wp20.items():
            for span in policy.stop(): emit('local_boundary',session=self.session_key,lane=lane,**asdict(span))
    return stop(self)
LiveCoordinator.stop_endpoint = traced_stop
decode = LiveCoordinator._decode
def traced_decode(self, span, pcm):
    result = decode(self,span,pcm)
    lanes = [lane for lane,tape in self.lane_tapes.items() if tape.read(start_sample=span.start_sample,end_sample=span.end_sample)==pcm]
    emit('canonical',session=self.session_key,lanes=lanes,span=asdict(span),text=result.transcript,elapsed=result.elapsed_sec)
    return result
LiveCoordinator._decode = traced_decode
revision = live_lane_decode.revision_segments
def traced_revision(c,lane,span,pcm,text,authority):
    result = revision(c,lane,span,pcm,text,authority)
    emit('revision',session=c.session_key,lane=lane,span=asdict(span),authority=str(authority),text=text)
    return result
live_lane_decode.revision_segments = traced_revision
runpy.run_path(str(ROOT/'prototypes/streaming-diarization/draft-lane/run_local_stack.py'),run_name='__main__')
