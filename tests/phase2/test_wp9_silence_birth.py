from moss_transcribe_diarize.app.live_provider_bundle import bounded_live_inference
from moss_transcribe_diarize.app.live_coordinator import CoordinatorWorkInput
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot
from tests.test_live_coordinator import coordinator


def test_wp7_zero_gap_birth_span_never_prepares_identity():
    class Forbidden:
        def transcribe(self, *a, **kw):
            raise AssertionError('zero span reached decoder')
        def prepare(self, **kw):
            raise AssertionError('zero-word span reached identity')
    # Deployed lanes build their decoder through the composition root, which seats
    # the digital-silence dispatch guard (WP10); a bare adapter would not carry it.
    decoder = bounded_live_inference(Forbidden(), max_samples=40000)
    live, _, _, _ = coordinator(speech=(), decoder=decoder, identity=Forbidden())
    base = LiveIdentitySnapshot(1, ('speaker-0001',))
    result = live.prepare_work_item(CoordinatorWorkInput(
        FrozenSpan(2, 0, 404000, 444000, 'end_silence'), bytes(80000), base))
    assert result.preparation is None
    assert result.transcript == ''
    assert base.canonical_speakers == ('speaker-0001',)
