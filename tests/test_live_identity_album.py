"""ADR-0002 step 1: the fingerprint album's admission and reference policy.

The defect these nodes exist to keep dead is the latest-span overwrite ADR-0002 measured at
66.4 % mean live speaker accuracy: one short noisy fragment replacing a good voice reference.
"""

import math

import pytest

from moss_transcribe_diarize.app.live_identity_album import (
    ADMITTED,
    ALBUM_ADMISSION_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    PROVISIONAL,
    REJECTED_BELOW_ADMISSION,
    REJECTED_INVALID_DURATION,
    REJECTED_INVALID_VECTOR,
    REJECTED_WEAKER_THAN_BANK,
    REJECTED_WEAKER_THAN_PROVISIONAL,
    FingerprintAlbum,
)


def _cosine(left, right):
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def test_adr_0002_starting_parameters_are_the_defaults():
    album = FingerprintAlbum()

    assert (album.admission_seconds, album.exemplars_per_speaker) == (2.0, 10)
    assert (ALBUM_ADMISSION_SECONDS, ALBUM_EXEMPLARS_PER_SPEAKER) == (2.0, 10)


def test_a_short_fragment_cannot_overwrite_an_admitted_reference():
    """The asymmetry, and the whole point of the album: matching is not enrollment."""

    album = FingerprintAlbum()
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=2.0, span_id=1)
        == ADMITTED
    )

    # The overwrite policy this replaces would now hold [0.0, 1.0] -- a different voice
    # entirely -- because it was simply the latest thing said.
    disposition = album.observe(
        canonical_speaker="speaker-0001",
        vector=[0.0, 1.0],
        duration_sec=0.5,
        span_id=2,
    )

    assert disposition == REJECTED_BELOW_ADMISSION
    assert album.reference("speaker-0001") == pytest.approx((1.0, 0.0))
    assert album.exemplar_count("speaker-0001") == 1


def test_the_reference_is_a_duration_weighted_centroid_not_the_latest_exemplar():
    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=4.0, span_id=1)
    album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=2.0, span_id=2)

    reference = album.reference("speaker-0001")

    # 2:1 weighting -> unit vector along (2, 1), which is neither exemplar and is closer to the
    # one that carried twice the speech.
    assert reference == pytest.approx((2 / math.sqrt(5), 1 / math.sqrt(5)))
    assert _cosine(reference, (1.0, 0.0)) > _cosine(reference, (0.0, 1.0))


def test_a_speaker_born_from_a_short_span_is_still_matchable():
    """Without a stand-in, birth semantics would change: an unmatchable speaker births again."""

    album = FingerprintAlbum()

    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=0.5, span_id=1)
        == PROVISIONAL
    )
    assert album.reference("speaker-0001") == (1.0, 0.0)
    assert album.exemplar_count("speaker-0001") == 0
    assert album.has_provisional("speaker-0001")


def test_the_provisional_stand_in_keeps_the_longest_and_is_retired_by_the_first_exemplar():
    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=0.8, span_id=1)

    # Shorter than the incumbent: even the stand-in tier refuses latest-wins.
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=0.4, span_id=2)
        == REJECTED_WEAKER_THAN_PROVISIONAL
    )
    assert album.reference("speaker-0001") == (1.0, 0.0)

    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=2.0, span_id=3)
        == ADMITTED
    )
    # Retired, not averaged: the refused 0.8 s fragment must not reach the centroid sideways.
    assert not album.has_provisional("speaker-0001")
    assert album.reference("speaker-0001") == pytest.approx((0.0, 1.0))


def test_an_equal_length_stand_in_does_not_churn():
    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=0.5, span_id=1)

    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=0.5, span_id=2)
        == REJECTED_WEAKER_THAN_PROVISIONAL
    )
    assert album.reference("speaker-0001") == (1.0, 0.0)


def test_the_bank_is_bounded_at_k_and_keeps_the_longest_exemplars():
    album = FingerprintAlbum(exemplars_per_speaker=3)
    for index, duration in enumerate((3.0, 2.5, 2.5), start=1):
        assert (
            album.observe(
                canonical_speaker="speaker-0001",
                vector=[1.0, 0.0],
                duration_sec=duration,
                span_id=index,
            )
            == ADMITTED
        )

    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=2.2, span_id=4)
        == REJECTED_WEAKER_THAN_BANK
    )
    assert album.exemplar_count("speaker-0001") == 3
    assert album.reference("speaker-0001") == pytest.approx((1.0, 0.0))

    # Longer than the weakest held exemplar: it evicts a 2.5 s one and enters.
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=2.7, span_id=5)
        == ADMITTED
    )
    assert album.exemplar_count("speaker-0001") == 3
    assert album.reference("speaker-0001")[1] > 0.0


def test_a_full_bank_still_tracks_the_meeting_on_a_tie():
    """Equal duration, newer span: replace the oldest, or an album frozen in minute one wins."""

    album = FingerprintAlbum(exemplars_per_speaker=2)
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=2.0, span_id=1)
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=2.0, span_id=2)

    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[0.0, 1.0], duration_sec=2.0, span_id=3)
        == ADMITTED
    )
    assert album.reference("speaker-0001") == pytest.approx((1 / math.sqrt(2), 1 / math.sqrt(2)))


def test_speakers_are_independent_and_an_unknown_speaker_has_no_reference():
    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=2.0, span_id=1)
    album.observe(canonical_speaker="speaker-0002", vector=[0.0, 1.0], duration_sec=2.0, span_id=1)

    assert album.reference("speaker-0001") == pytest.approx((1.0, 0.0))
    assert album.reference("speaker-0002") == pytest.approx((0.0, 1.0))
    assert album.reference("speaker-0003") is None
    assert album.speakers() == ("speaker-0001", "speaker-0002")


def test_an_unusable_observation_is_declined_by_name_and_never_raises():
    """The live path's terminal-failure policy: degrade with a named refusal, never end a meeting."""

    album = FingerprintAlbum()

    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[], duration_sec=2.0, span_id=1)
        == REJECTED_INVALID_VECTOR
    )
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[math.nan], duration_sec=2.0, span_id=1)
        == REJECTED_INVALID_VECTOR
    )
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=["x"], duration_sec=2.0, span_id=1)
        == REJECTED_INVALID_VECTOR
    )
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[1.0], duration_sec=0.0, span_id=1)
        == REJECTED_INVALID_DURATION
    )
    assert (
        album.observe(canonical_speaker="speaker-0001", vector=[1.0], duration_sec=math.nan, span_id=1)
        == REJECTED_INVALID_DURATION
    )
    assert album.reference("speaker-0001") is None


def test_a_bank_whose_exemplars_disagree_on_dimension_loses_its_reference_not_the_session():
    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=2.0, span_id=1)
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0, 0.0], duration_sec=2.0, span_id=2)

    assert album.reference("speaker-0001") is None


def test_opposing_exemplars_degrade_to_no_reference_rather_than_a_zero_vector():
    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=[1.0, 0.0], duration_sec=2.0, span_id=1)
    album.observe(canonical_speaker="speaker-0001", vector=[-1.0, 0.0], duration_sec=2.0, span_id=2)

    assert album.reference("speaker-0001") is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"admission_seconds": 0.0},
        {"admission_seconds": -1.0},
        {"admission_seconds": math.inf},
        {"exemplars_per_speaker": 0},
        {"exemplars_per_speaker": -3},
    ],
)
def test_the_album_refuses_a_nonsensical_configuration_at_construction(kwargs):
    with pytest.raises(ValueError):
        FingerprintAlbum(**kwargs)
