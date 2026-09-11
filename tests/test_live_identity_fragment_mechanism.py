"""Controlled geometry, not a measurement of any real speaker's embeddings."""
import pytest

from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot


class ScriptedEncoder:
    def __init__(self, vectors):
        self.vectors = iter(vectors)

    def embed(self, wav_path, intervals):
        return next(self.vectors)


@pytest.mark.parametrize('gap', [0.0, 0.6, 10.0])
@pytest.mark.parametrize('vectors,seconds,expected_count,expected_bank', [
    ([(1., 0., 0.)] * 3, 1.2, 1, 0),
    ([(1., 0., 0.), (0., 1., 0.), (0., 0., 1.)], 1.2, 3, 0),
    ([(1., 0., 0.), (0., 1., 0.), (0., 0., 1.)], 0.8, 0, 0),
    ([(1., 0., 0.)] * 3, 2.2, 1, 3),
])
def test_fragment_births_depend_on_evidence_not_elapsed_gap(
    gap, vectors, seconds, expected_count, expected_bank,
):
    album = FingerprintAlbum(admission_seconds=2.0)
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=ScriptedEncoder(vectors), album=album,
        birth_min_seconds=1.0, min_segment_samples=8000,
    )
    preparer = BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(max_speakers=16, min_match_score=0.35, min_match_margin=0.1),
        evidence_provider=provider,
    )
    snapshot = LiveIdentitySnapshot()
    samples = round(seconds * 16000)
    for index in range(3):
        start = round(index * (seconds + gap) * 16000)
        span = FrozenSpan(index + 1, 0, start, start + samples, 'end_silence')
        result = preparer.prepare(
            span=span, pcm=b'\0' * samples * 2,
            transcript=f'[0][S01]test[{seconds}]', base_snapshot=snapshot,
        )
        assert result.status == 'prepared'
        snapshot = result.proposed_snapshot
    provider.finalize_identity(base_snapshot=snapshot)
    assert len(snapshot.canonical_speakers) == expected_count
    assert sum(album.exemplar_count(s) for s in album.speakers()) == expected_bank
    if expected_count and not expected_bank:
        assert all(album.has_provisional(s) for s in album.speakers())
