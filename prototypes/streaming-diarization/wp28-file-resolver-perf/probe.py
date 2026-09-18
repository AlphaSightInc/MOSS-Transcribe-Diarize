"""WP28 retained measurement bench: prototype absorbed into production.
Question: which work dominates and can be removed with byte-identical output?
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> this-file --minutes 6 30
No transcript text or audio is persisted outside ignored worktree scratch.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import time
import resource
from threading import Lock
from unittest.mock import patch

from moss_transcribe_diarize.app import speaker_identity as si
from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
from moss_transcribe_diarize.app.windowed_transcription import plan_windows
from moss_transcribe_diarize.transcript_parser import parse_transcript

ROOT = Path('.wp28runtime')
OUT = Path('evidence/mvpfix/wp28')

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--minutes', type=int, nargs='+', default=[6, 30])
    p.add_argument('--arm', default='production')
    p.add_argument('--serial', action='store_true')
    args = p.parse_args()
    if args.arm == "baseline" and not args.serial:
        p.error("baseline must explicitly use --serial")
    config = LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
    for minutes in args.minutes:
        times = Counter(); counts = Counter(); seconds = Counter(); duplicates = Counter(); absolute_duplicates = Counter()
        lock = Lock()
        resolver = AlbumIdentityResolver(config=config, encoder=_identity_encoder(config) if args.serial else None)
        windows = plan_windows(minutes*60, window_seconds=150, stride_seconds=120)
        folder = ROOT / f'real-{minutes}'
        groups = [parse_transcript(json.loads((folder/f'decode-{w.index}.json').read_text())['text']) for w in windows]
        paths = [folder/f'window-{w.index}.wav' for w in windows]
        def timed(name, fn):
            def call(*a, **kw):
                t=time.perf_counter()
                try: return fn(*a, **kw)
                finally:
                    elapsed=time.perf_counter()-t
                    with lock:
                        times[name]+=elapsed; counts[name]+=1
            return call
        old_embed = si._OnnxWeSpeakerEmbedder.embed
        def embed(self,path,intervals):
            seconds['requested_audio'] += sum(e-s for s,e in intervals)
            counts['intervals'] += len(intervals)
            duplicates.update((str(path),s,e) for s,e in intervals)
            offset=windows[paths.index(path)].start
            absolute_duplicates.update((round((offset+s)*16000),round((offset+e)*16000)) for s,e in intervals)
            return timed('embedding',old_embed)(self,path,intervals)
        old_load=si._OnnxWeSpeakerEmbedder._load_session
        def load(self):
            if self._session is None: return timed('session_creation',old_load)(self)
            return old_load(self)
        with patch.object(si,'_sha256_file',timed('asset_hash',si._sha256_file)), \
             patch.object(si,'_run_onnx_embedding',timed('onnx',si._run_onnx_embedding)), \
             patch.object(si._OnnxWeSpeakerEmbedder,'_features',timed('features',si._OnnxWeSpeakerEmbedder._features)), \
             patch.object(si._OnnxWeSpeakerEmbedder,'_load_audio',timed('audio_load',si._OnnxWeSpeakerEmbedder._load_audio)), \
             patch.object(si._OnnxWeSpeakerEmbedder,'_load_session',load), \
             patch.object(si._OnnxWeSpeakerEmbedder,'embed',embed):
            t=time.perf_counter()
            result=resolver.resolve(windows,groups,window_audio_paths=paths)
            times['resolver']=time.perf_counter()-t
        payload=json.dumps(asdict(result),sort_keys=True,separators=(',',':'))
        (ROOT/f'{args.arm}-{minutes}-result.json').write_text(payload)
        report=dict(arm=args.arm,minutes=minutes,windows=len(windows),counts=counts,seconds=seconds,times=times,
                    duplicate_intervals=sum(n-1 for n in duplicates.values()),
                    exact_absolute_duplicate_intervals=sum(n-1 for n in absolute_duplicates.values()),summary=result.summary,
                    process_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    window_states=result.diagnostics['windows'],sweep=result.diagnostics['sweep'])
        if args.arm != 'baseline':
            report['byte_identical']=payload==(ROOT/f'baseline-{minutes}-result.json').read_text()
        (OUT/f'{args.arm}-{minutes}.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:v for k,v in report.items() if k not in ('window_states','sweep')}),flush=True)
        assert all(w['reason']=='ok' for w in result.diagnostics['windows'])
        assert report.get('byte_identical',True)
if __name__=='__main__': main()
