"""WP19 retained bench: measured prototype absorbed into the product album resolver.
One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> this-file
Hypothesis: comparing local voices with canonical album entries removes occurrence rivalry.
Falsifier: perfect recurring vectors split or the retained six-minute decode is not 3 voices.
Print state after every window; retain no transcript words or raw vectors in evidence.
"""
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import time
from moss_transcribe_diarize.app.live_identity import assign_speakers, LiveSpeakerEvidence, LiveIdentityError
from moss_transcribe_diarize.app.live_identity_album import cosine_similarity
from moss_transcribe_diarize.app.live_identity_sweep import LiveIdentitySweeper
from moss_transcribe_diarize.app.live_provider_bundle import (LiveProviderBundleConfig, _identity_encoder, _identity_config, _fingerprint_album, _birth_min_seconds)
from moss_transcribe_diarize.app.windowed_transcription import plan_windows, _stitch_segments
from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

CONFIG = LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')

def resolve(windows, groups, paths, encoder):
    from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
    result = AlbumIdentityResolver(config=CONFIG, encoder=encoder).resolve(
        windows, groups, window_audio_paths=paths)
    states = result.diagnostics['windows']
    for state in states: print(json.dumps(state), flush=True)
    return result.relabeled_results, dict(states=states,sweep=result.diagnostics['sweep'])

class Fake:
    descriptor = {"provider": "perfect-vector-probe"}
    def embed(self,path,intervals): return [1.,0.] if intervals[0][0]<30 else [0.,1.]

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--fake-only',action='store_true'); parser.add_argument('--output',type=Path,default=Path('evidence/mvpfix/wp19'))
    args=parser.parse_args(); out=args.output; out.mkdir(exist_ok=True,parents=True)
    windows = plan_windows(360,window_seconds=150,stride_seconds=120)
    for n in (1,2):
        groups = [[TranscriptSegment(20,25,'S01','x')] + ([TranscriptSegment(40,45,'S02','y')] if n == 2 else []) for w in windows]
        result, state = resolve(windows,groups,['unused']*3,Fake())
        state.update(identities=len({s.speaker for g in result for s in g}),expected=n,text_time_unchanged=all((a.start,a.end,a.text)==(b.start,b.end,b.text) for ga,gb in zip(groups,result) for a,b in zip(ga,gb)))
        (out/f'prototype-fake-{n}.json').write_text(json.dumps(state,indent=2)+'\n')
        print(json.dumps({'case':n,'identities':state['identities']}),flush=True)
    if args.fake_only: return
    groups = [parse_transcript(json.loads(Path(f'.wp19runtime/decode-{w.index}.json').read_text())['text']) for w in windows]
    start = time.monotonic()
    result,state = resolve(windows,groups,[Path(f'.wp19runtime/media/window-{w.index}.wav') for w in windows],_identity_encoder(CONFIG))
    state.update(identities=len({s.speaker for s in _stitch_segments(windows,result) if s.speaker != 'S00'}),unattributed=sum(s.speaker=='S00' for s in _stitch_segments(windows,result)),elapsed=time.monotonic()-start,expected=3)
    (out/'prototype-real.json').write_text(json.dumps(state,indent=2)+'\n')
    Path('.wp19runtime/prototype-segments.json').write_text(json.dumps([asdict(s) for s in _stitch_segments(windows,result)]))
    print(json.dumps({k:v for k,v in state.items() if k not in ('states','sweep')}),flush=True)
if __name__ == '__main__': main()
