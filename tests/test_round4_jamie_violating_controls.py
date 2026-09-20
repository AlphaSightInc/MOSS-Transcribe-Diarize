"""R4-4 violating controls: these must fail on the unpatched base."""
import pytest

from moss_transcribe_diarize.app.live_identity_album import FingerprintAlbum


@pytest.mark.parametrize("durations", [(0.60, 0.60), (0.78, 0.78)])
@pytest.mark.xfail(
    strict=True,
    reason="R4-4: base keeps only one provisional span instead of pooling mutually matching retained evidence",
)
def test_r4_4_compatible_provisional_support_accumulates(durations):
    album = FingerprintAlbum(admission_seconds=2.0)
    vector = (1.0, 0.0)
    for span_id, duration in enumerate(durations, start=1):
        album.observe(
            canonical_speaker="speaker-0003",
            vector=vector,
            duration_sec=duration,
            span_id=span_id,
        )

    support = album.reference_support("speaker-0003")
    assert sum(item.duration_sec for item in support) == pytest.approx(sum(durations))
