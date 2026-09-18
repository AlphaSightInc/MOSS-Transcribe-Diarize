"""Replay WP7's wholly silent birth span through the integrated production coordinator.
No service, model or encoder needed: either would be a bug for this zero-word span.
"""
import json
import sys
import wave
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tests.test_live_coordinator import coordinator
from moss_transcribe_diarize.app.live_adapters import RunnerBoundedWavInference
from moss_transcribe_diarize.app.live_coordinator import CoordinatorWorkInput
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot


def probe(pcm):
    class Forbidden:
        def transcribe(self, *a, **kw):
            raise AssertionError('zero PCM reached decoder')
        def prepare(self, **kw):
            raise AssertionError('wordless silence reached identity preparation')
    decoder = RunnerBoundedWavInference(Forbidden(), max_samples=len(pcm)//2)
    live, _, _, _ = coordinator(speech=(), decoder=decoder, identity=Forbidden())
    base = LiveIdentitySnapshot(version=1, canonical_speakers=('speaker-0001',))
    work = CoordinatorWorkInput(FrozenSpan(2, 0, 404000, 444000, 'end_silence'), pcm, base)
    prepared = live.prepare_work_item(work)
    assert prepared.transcript == '' and prepared.preparation is None
    return dict(span_seconds=[25.25, 27.75], nonzero_bytes=sum(b != 0 for b in pcm),
                decoder_requests=0, identity_preparations=0, extra_births=0,
                transcript=prepared.transcript, empty_reason=prepared.empty_reason,
                base_speakers=list(base.canonical_speakers))


def main():
    corpus = Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_adam_frank_180s/audio.wav')
    with wave.open(str(corpus)) as wav:
        wav.setpos(49*16000)
        adam = wav.readframes(60*16000)
    assert len(adam) == 60*32000
    gap = adam[:25*32000] + bytes(10*32000) + adam[35*32000:]
    result = probe(gap[404000*2:444000*2])
    print(json.dumps(result))


if __name__ == '__main__':
    main()
