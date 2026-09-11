"""Real pinned embeddings; fixed cuts, no decoder or reference-label input."""
from pathlib import Path
import argparse
import json
import sys
import wave
import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
from moss_transcribe_diarize.app.speaker_identity import WeSpeakerResNet152LmAdapter
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum, cosine_similarity
from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot


def save(path, data):
    path.write_text(json.dumps(data, indent=2) + '\n')


def distribution(values):
    return dict(zip(('min', 'p05', 'p25', 'median', 'p75', 'p95', 'max'),
                    map(float, np.quantile(values, [0, .05, .25, .5, .75, .95, 1]))))


class RecordedEncoder:
    def __init__(self, records):
        self.records = iter(records)
    def embed(self, wav_path, intervals):
        return next(self.records)['vector']


class RecordingProvider(WeSpeakerLiveEvidenceProvider):
    def score(self, **kwargs):
        self.last_scores = super().score(**kwargs)
        return self.last_scores


def replay(records, seconds):
    album = FingerprintAlbum(admission_seconds=2.0)
    provider = RecordingProvider(encoder=RecordedEncoder(records), album=album,
                                birth_min_seconds=1.0, min_segment_samples=8000)
    preparer = BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(max_speakers=16, min_match_score=.35, min_match_margin=.1),
        evidence_provider=provider)
    state = LiveIdentitySnapshot()
    trace = []
    for i, record in enumerate(records):
        start = round(i * (seconds + .6) * 16000)
        n = round(seconds * 16000)
        span = FrozenSpan(i + 1, 0, start, start + n, 'controlled_cut')
        before = list(state.canonical_speakers)
        preparation = preparer.prepare(span=span, pcm=b'\0' * n * 2,
            transcript=f'[0][S01]controlled interval[{seconds}]', base_snapshot=state)
        scores = sorted([e.score for e in provider.last_scores], reverse=True)
        state = preparation.proposed_snapshot
        trace.append(dict(source_start=record['start'], status=preparation.status,
            reason=preparation.reason, scores={e.canonical_speaker: e.score for e in provider.last_scores},
            top_score=scores[0] if scores else None,
            margin=scores[0] - (scores[1] if len(scores) > 1 else 0) if scores else None,
            new_ids=[s for s in state.canonical_speakers if s not in before],
            diagnostics=dict(state.diagnostics)))
    provider.finalize_identity(base_snapshot=state)
    return dict(identities=list(state.canonical_speakers), trace=trace,
                admitted={s: album.exemplar_count(s) for s in album.speakers()},
                provisional={s: album.has_provisional(s) for s in album.speakers()})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    args = parser.parse_args()
    out = Path(__file__).parent
    source = REPO / 'evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav'
    with wave.open(str(source)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        duration = wav.getnframes() / 16000
    adapter = WeSpeakerResNet152LmAdapter(args.model)
    preflight = adapter.preflight()
    assert preflight.available, preflight.reason
    result = dict(source=str(source.relative_to(REPO)), duration=duration,
                  model_path=str(args.model), model_descriptor=adapter.descriptor,
                  method='Nonoverlapping fixed source intervals; all full windows; no reference input. '
                  'Pair counts unordered, excluding self. Replay uses measured vectors and synthetic single-local-speaker intervals; '
                  '0.6 s gaps; no decoder, endpoint detector or retrospective sweep. 10 s control exceeds live span cap.',
                  groups={})
    save(out / 'results.json', result)
    for seconds in (1.0, 1.5, 2.0, 10.0):
        records = []
        for i in range(int(duration // seconds)):
            start, end = i * seconds, (i + 1) * seconds
            vector = adapter.embed(source, [(start, end)])
            records.append(dict(start=start, end=end, vector=vector))
            save(out / f'vectors-{seconds:g}s.json', records)
            print(f'{seconds:g}s {len(records)}/{int(duration // seconds)}', flush=True)
        pairs = [dict(left=i, right=j, score=cosine_similarity(a['vector'], b['vector']))
                 for i, a in enumerate(records) for j, b in enumerate(records) if j > i]
        values = [p['score'] for p in pairs]
        failed = [p for p in pairs if p['score'] < .35]
        sequential = replay(records, seconds)
        group = dict(windows=len(records), excluded_tail_seconds=duration-len(records)*seconds,
            pair_count=len(pairs), distribution=distribution(values),
            below_035=len(failed), fraction_below_035=len(failed)/len(pairs),
            lowest_pairs=sorted(pairs, key=lambda p: p['score'])[:10],
            adjacent_below_035=sum(p['score'] < .35 for p in pairs if p['right']==p['left']+1),
            adjacent_pairs=len(records)-1, sequential=sequential)
        result['groups'][str(seconds)] = group
        save(out / f'pairs-{seconds:g}s.json', pairs)
        save(out / 'results.json', result)
        print(json.dumps({k:v for k,v in group.items() if k not in ('sequential','lowest_pairs')}), flush=True)

if __name__ == '__main__':
    main()
