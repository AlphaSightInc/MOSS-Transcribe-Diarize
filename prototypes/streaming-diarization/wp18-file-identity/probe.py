"""WP18 measurement bench: unchanged resolver, disabled/enabled provider.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <venv-python> this-file [--decode]
Real PCM/decoder cache stay in ignored scratch; retained decisions contain no words.
"""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import time
import urllib.request
import wave
from moss_transcribe_diarize.app.speaker_identity import IdentityResolver, IdentityResolverConfig, TierBPreflight
from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
from moss_transcribe_diarize.app.runner_composition import build_file_runner
from moss_transcribe_diarize.app.windowed_transcription import plan_windows, extract_window_wav, _stitch_segments
from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

SCRATCH=Path('.wp18runtime'); OUT=Path('evidence/mvpfix/wp18')
def emit(name, row):
    (OUT/(name+'.json')).write_text(json.dumps(row, indent=2)+'\n')
    print(json.dumps({'case':name,**row}),flush=True)
def counts(result, windows):
    return dict(resolver_identities=len({s.speaker for group in result.relabeled_results for s in group}),
                stitched_identities=len({s.speaker for s in _stitch_segments(windows,result.relabeled_results)}),
                summary=result.summary,diagnostics=result.diagnostics)
class Fake:
    def preflight(self): return TierBPreflight(True,None,{})
    def embed(self,path,intervals): return [1.,0.] if intervals[0][0]<30 else [0.,1.]

def main():
    global OUT
    parser=argparse.ArgumentParser()
    parser.add_argument('--decode',action='store_true')
    parser.add_argument('--fake-only',action='store_true')
    parser.add_argument('--output',type=Path,default=OUT)
    args=parser.parse_args(); OUT=args.output; OUT.mkdir(parents=True,exist_ok=True)
    windows=plan_windows(360,window_seconds=150,stride_seconds=120)
    for voices in (1,2):
        segments=[[TranscriptSegment(20,25,'S01','x')]+([TranscriptSegment(40,45,'S02','y')] if voices==2 else []) for _ in windows]
        for active in (False,True):
            resolver=IdentityResolver(config=IdentityResolverConfig(tier_b_enabled=active),tier_b_encoder=Fake())
            emit(f'fake-{voices}-{active}',counts(resolver.resolve(windows,segments,window_audio_paths=['unused']*3),windows))
    if args.fake_only: return
    corpus=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus')
    source=SCRATCH/'media/six.wav'
    with wave.open(str(source),'wb') as out:
        out.setparams((1,2,16000,0,'NONE','not compressed'))
        for i in range(6):
            with wave.open(str(corpus/['interview_bill_ackman_60s','interview_keyu_jin_60s'][i%2]/'audio.wav'),'rb') as src:
                out.writeframes(src.readframes(960000))
    runner=build_file_runner(model_path='unused',device='cpu',dtype='bf16',backend='vllm',vllm_base_url='http://127.0.0.1:18118/v1',vllm_model='OpenMOSS-Team/MOSS-Transcribe-Diarize',vllm_api_key='EMPTY',vllm_timeout=1800)
    emit('file-constructor',runner.identity_resolver.contract())
    paths=[]; segments=[]
    for w in windows:
        path=SCRATCH/f'media/window-{w.index}.wav'; paths.append(path)
        extract_window_wav(source,path,start_seconds=w.start,duration_seconds=w.duration)
        cache=SCRATCH/f'decode-{w.index}.json'
        if args.decode:
            metrics=urllib.request.urlopen('http://127.0.0.1:18118/metrics').read().decode()
            queue=[s for s in metrics.splitlines() if s.startswith(('vllm:num_requests_running{','vllm:num_requests_waiting{'))]
            print(json.dumps({'window':asdict(w),'queue_before':queue}),flush=True)
            t=time.monotonic(); result=runner._decode_window(path,w,dict(max_length=16384,max_new_tokens=12000,decoding='greedy'))
            cache.write_text(json.dumps(result.to_dict()))
            emit(f'decode-{w.index}',dict(window=asdict(w),queue_before=queue,elapsed=time.monotonic()-t,tokens=result.generated_tokens,local_speakers=len({s.speaker for s in parse_transcript(result.text)})))
        raw=json.loads(cache.read_text()); segments.append(parse_transcript(raw['text']))
    config=LiveProviderBundleConfig.from_manifest(Path.home()/'.local/share/moss-transcribe-diarize/live/live-provider-manifest.json')
    encoder=_identity_encoder(config)
    for active in (False,True):
        resolver=IdentityResolver(config=IdentityResolverConfig(tier_b_enabled=active),tier_b_encoder=encoder)
        started=time.monotonic(); result=resolver.resolve(windows,segments,window_audio_paths=paths)
        emit(f'real-{active}',{**counts(result,windows),'elapsed':time.monotonic()-started,'reference_voices':3})
if __name__=='__main__': main()
