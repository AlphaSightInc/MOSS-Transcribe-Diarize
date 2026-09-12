"""Throwaway: measure repeated asset verification on the real embedding path.
Run: .venv/bin/python prototypes/streaming-diarization/voiceprint-first-match/hash_probe.py
Hypothesis: each observation re-hashes an unchanged model; stat-keyed reuse removes this
I/O without changing vectors. Falsifier: hashing is negligible or embeddings differ.
"""
import json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from moss_transcribe_diarize.app import speaker_identity as identity
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
config=LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
encoder=_identity_encoder(config)
audio=Path(__file__).resolve().parents[3]/'tests/fixtures/idea_020_provider_smoke.wav'
original=identity._sha256_file; calls=[]
def timed(path):
    start=time.perf_counter(); value=original(path); calls.append(time.perf_counter()-start); return value
identity._sha256_file=timed
encoder.embed(audio,[(0.,2.)])  # explicit warm-up, exclude model load and library imports
results=[]; vectors=[]
for label in ('before1','before2','cached1','cached2'):
    if label=='cached1':
        cache={}
        def cached(path):
            stat=path.stat(); key=(str(path),stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
            if key not in cache: cache[key]=timed(path)
            return cache[key]
        identity._sha256_file=cached
    start=time.perf_counter(); count=len(calls)
    vectors.append(encoder.embed(audio,[(0.,2.)]))
    results.append({'phase':label,'seconds':time.perf_counter()-start,'hash_calls':len(calls)-count,'hash_seconds':sum(calls[count:])})
print(json.dumps({'asset_bytes':encoder.state_path.stat().st_size,'results':results,'max_vector_difference':max(abs(a-b) for vector in vectors[1:] for a,b in zip(vectors[0],vector))},indent=2))
