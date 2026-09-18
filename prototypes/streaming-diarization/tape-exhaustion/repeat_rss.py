"""WP29 retained repeated-session RSS bench, adapted from WP22. No GPU/network.
Question: does a second 10-minute meeting reuse post-final process memory?
One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> <this-file> --output <jsonl>
Production V2 ingress/mixer/runtime/VAD/ONNX identity/rolling/terminal; stub ASR.
Two sessions retain the same runtime and encoder. No tracemalloc instrumentation.
Manual canonical pump drains after every frame; audio clock and partitions unchanged.
This measures retained memory with zero decoder backlog, not real-time throughput.
"""
import argparse
import asyncio
from dataclasses import fields, is_dataclass, replace
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import wave
from collections import deque

ROOT = Path.cwd()
from moss_transcribe_diarize.app import live_provider_bundle as bundle
from moss_transcribe_diarize.app.live_service_runtime import _ManualCanonicalPumpScheduler, _ManualTerminalScheduler
from moss_transcribe_diarize.app.live_transcript_convergence import TerminalTranscriptFinalizer
from moss_transcribe_diarize.app.live_mixer import LiveCompatibilityMixer
from moss_transcribe_diarize.app.live_v2_session import LiveV2Session
from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame

class StubRunner:
    window_seconds = 150
    stride_seconds = 120
    calls = 0
    def transcribe(self, audio_path, **kwargs):
        self.calls += 1
        with wave.open(str(audio_path), 'rb') as w:
            seconds = w.getnframes()/w.getframerate()
        # Same full-span word shape for every arm; real speech drives VAD/identity.
        text=''.join(f'[{start:g}][S01]memory probe words[{min(start+2.5,seconds):g}]' for start in (i*2.5 for i in range(__import__('math').ceil(seconds/2.5))))
        return SimpleNamespace(text=text,
            prompt_len=0, generated_tokens=10, window_count=1, completed_windows=1,
            possibly_truncated=False)

def size(obj, seen=None):
    """Owned Python graph bytes, excluding code/locks/native encoder. Aliases deduped per owner."""
    if seen is None: seen = set()
    if id(obj) in seen: return 0
    seen.add(id(obj))
    n = sys.getsizeof(obj)
    if isinstance(obj, dict): return n + sum(size(k,seen)+size(v,seen) for k,v in obj.items())
    if isinstance(obj, (list,tuple,set,frozenset,deque)): return n+sum(size(v,seen) for v in obj)
    if is_dataclass(obj): return n+sum(size(getattr(obj,f.name),seen) for f in fields(obj))
    return n

def owners(runtime, sid, source):
    state=runtime._sessions[sid]; c=state.coordinator; s=state.session
    tapes={'mixed':c.tape, **getattr(c,'lane_tapes',{})}
    result={}
    def add(name,obj,count=None):
        result[name]={'bytes':size(obj),'count':len(obj) if count is None else count}
    add('mixer_frames', source.retained_frames())
    add('replay_acks', source._ingress._acks)
    for name,t in tapes.items():
        if t is not None: add('tape_'+name,t._buffer,len(t._buffer)//2)
    for name,p in {'mixed':c._pcm,'analysis':getattr(c,'_analysis_pcm',c._pcm), **getattr(c,'_lane_pcm',{})}.items():
        add('pending_pcm_'+name,p._slices)
    add('session_frames',s._frames); add('commits',s._committed); add('spans',s._frozen_spans)
    add('revisions',s._revision_segments); add('events',state.events)
    add('canonical_timing',state.canonical_timing); add('rolling_timing',state.rolling_timing)
    if c.converger: add('rolling_buffer',c.converger._buffer)
    for lane,p in (getattr(c,'_lane_preparers',{}) or {'mono':c.identity_preparer}).items():
        e=p.evidence_provider
        add('pending_vectors_'+lane,e._pending_vectors)
        add('album_'+lane,e._album._exemplars)
        result['album_entries_'+lane]={'bytes':size(e._album._exemplars), 'count':sum(len(bank) for bank in e._album._exemplars.values())}
        add('album_provisional_'+lane,e._album._provisional)
        add('sweep_'+lane,e._sweeper.ledger._spans)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=600)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--tape-bytes',type=int,default=57600000)
    a=p.parse_args(); (ROOT/'.wp29/t').mkdir(parents=True,exist_ok=True)
    tempfile.tempdir=str(ROOT/'.wp29/t')
    config=bundle.LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
    # Instrumentation-only manifest bound; policies otherwise unchanged.
    config=replace(config,bounds_config={**config.bounds_config,'max_tape_bytes':a.tape_bytes})
    runner=StubRunner()
    inference=getattr(bundle,'bounded_live_inference',bundle.RunnerBoundedWavInference)
    # Build production collaborators directly: no admission hash rewrite for profile-only copy.
    encoder=bundle._identity_encoder(config)
    from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime,LiveServiceDescriptor,LiveServiceConfigHashes,hash_config
    desc=LiveServiceDescriptor(source_revision='a'*40,provider_name='wp29-stub-asr',provider_revision='profile',provider_manifest_hash=hash_config({}),config_hashes=LiveServiceConfigHashes.from_parts(endpoint_config=config.endpoint_config,identity_config=config.identity_config,decoder_config=config.decoder_config),bounds=bundle._bounds(config.bounds_config),frame_samples=config.bounds_config['frame_samples'])
    pump=_ManualCanonicalPumpScheduler(); terminal=_ManualTerminalScheduler()
    runtime=LiveServiceRuntime(descriptor=desc,endpoint_policy_factory=lambda:bundle.EndpointPolicy(bundle._endpoint_config(config.endpoint_config)),speech_provider_factory=lambda:bundle._speech_provider(config),decoder_factory=lambda:inference(runner,max_samples=config.decoder_config['max_samples']),rolling_decoder_factory=lambda:inference(runner,max_samples=bundle.DEFAULT_ROLLING_GEOMETRY.window_samples),identity_preparer_factory=lambda:bundle._identity_preparer(config,encoder=encoder),terminal_finalizer=TerminalTranscriptFinalizer(runner=runner),_canonical_scheduler=pump,_terminal_scheduler=terminal)
    for meeting_index in range(2):
        sid=runtime.create().session_id;source=LiveV2Session(max_retained_samples=desc.bounds.max_retained_samples)
        mixer=LiveCompatibilityMixer(max_output_samples=desc.bounds.max_frame_samples)
        corpus=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
        clips=[]
        import numpy as np
        for name in ['interview_bill_ackman_60s','interview_keyu_jin_60s']:
            with wave.open(str(corpus/name/'audio.wav'),'rb') as w: clips.append(w.readframes(w.getnframes()))
        clips[1]=np.rint(np.frombuffer(clips[1],dtype='<i2')*10**(-10/20)).astype('<i2').tobytes()
        started=time.monotonic()
        def record(second,phase):
            gc.collect()
            with runtime._lock:
                snap=runtime.snapshot(sid); structures=owners(runtime,sid,source)
            row=dict(meeting=meeting_index+1,session_count=len(runtime._sessions),seconds=second,phase=phase,wall_seconds=time.monotonic()-started,rss_bytes=int(subprocess.check_output(['ps','-o','rss=','-p',str(os.getpid())],text=True))*1024,structures=structures,accepted=snap.session.accepted_samples,committed=snap.session.committed_samples,status=snap.session.status,finalization=snap.session.finalization_status,decoder_calls=runner.calls)
            with a.output.open('a') as stream: stream.write(json.dumps(row)+'\n')
            print(json.dumps({k:v for k,v in row.items() if k not in ('structures','allocations')}),flush=True)
        record(0,'baseline');fs=desc.frame_samples
        for seq in range(a.seconds*16000//fs):
            for i,lane in enumerate(LiveLane):
                offset=seq*fs*2%len(clips[i]); pcm=(clips[i]*2)[offset:offset+fs*2]
                source.accept(LiveV2Frame(lane=lane,sequence=seq,capture_timestamp_ns=1_000_000_000+seq*fs*62500,device_epoch=1,silent=False,discontinuity=False,sample_rate=16000,sample_count=fs,pcm=pcm))
            while mixer.admit_available(sid,source,runtime) is not None: pump.drain()
            pump.drain()
            if (seq+1)*fs%(30*16000)==0: record((seq+1)*fs//16000,'capture')
        while mixer.admit_available(sid,source,runtime,final=True) is not None:pump.drain()
        async def stop():
            task=asyncio.create_task(runtime.stop(sid,30))
            while not task.done():
                pump.drain();await asyncio.sleep(.001)
            await task
            await source.stop(30)
        asyncio.run(stop());record(a.seconds,'closed_before_terminal')
        terminal.drain();record(a.seconds,'after_terminal')
        snap=runtime.snapshot(sid)
        (ROOT/'.wp29'/f'rss-meeting-{meeting_index+1}.json').write_text(json.dumps([dict(start=s.start_sample,end=s.end_sample,text=s.text,speaker=s.canonical_speaker,lane=getattr(s,'source_lane',None)) for s in snap.session.effective_transcript],indent=2)+'\n')

if __name__=='__main__': main()
