"""ADR-0002 step 3: the retrospective sweep.

The failure these nodes exist to keep dead is the sibling project's, quoted in ADR-0002: live
labels that used only the evidence available at time T, never revisited, so live accuracy
*diverged* from whole-file accuracy at <80 %. The album decides what a label is matched against;
only these rules decide whether a label already written down can still be wrong.
"""

import math

import pytest

from moss_transcribe_diarize.app.live_identity import LiveIdentityConfig
from moss_transcribe_diarize.app.live_identity_album import (
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    FingerprintAlbum,
    cosine_similarity,
)
from moss_transcribe_diarize.app.live_identity_sweep import (
    KEPT,
    KEPT_AMBIGUOUS,
    KEPT_BELOW_MARGIN,
    KEPT_UNSCORED,
    LABELLED,
    MERGED,
    NO_REFERENCE,
    REASSIGNED,
    RECORDED,
    REJECTED_INVALID_DURATION,
    REJECTED_INVALID_VECTOR,
    REJECTED_LEDGER_FULL,
    REPLACED,
    SWEEP_INTERVAL_SECONDS,
    SWEEP_LEDGER_MAX_UNITS,
    SWEEP_MERGE_THRESHOLD,
    LiveIdentitySweeper,
    SweepLedger,
    SweepRevision,
    sweep,
)

CONFIG = LiveIdentityConfig(
    max_speakers=16,
    min_match_score=ALBUM_MIN_MATCH_SCORE,
    min_match_margin=ALBUM_MIN_MATCH_MARGIN,
)


def unit_vector(angle_degrees: float) -> tuple[float, float]:
    """A voiceprint on the unit circle, so a cosine between two of them is readable by eye."""

    radians = math.radians(angle_degrees)
    return (math.cos(radians), math.sin(radians))


def album_with(*speakers: tuple[str, tuple[float, ...], float]) -> FingerprintAlbum:
    album = FingerprintAlbum()
    for index, (speaker, vector, duration) in enumerate(speakers):
        album.observe(canonical_speaker=speaker, vector=vector, duration_sec=duration, span_id=index)
    return album


# --------------------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------------------


def test_the_ledger_retains_one_unit_per_span_and_local_speaker():
    ledger = SweepLedger()

    assert (
        ledger.record(
            span_id=1,
            local_speaker="S01",
            canonical_speaker="speaker-0001",
            vector=unit_vector(0),
            duration_sec=2.0,
        )
        == RECORDED
    )
    assert (
        ledger.record(
            span_id=1,
            local_speaker="S02",
            canonical_speaker="speaker-0002",
            vector=unit_vector(90),
            duration_sec=1.5,
        )
        == RECORDED
    )

    assert (ledger.unit_count, ledger.span_count) == (2, 1)
    span_id, units = next(ledger.spans())
    assert span_id == 1
    assert [unit.local_speaker for unit in units] == ["S01", "S02"]
    assert [unit.canonical_speaker for unit in units] == ["speaker-0001", "speaker-0002"]


def test_re_recording_a_unit_replaces_it_without_growing_the_ledger():
    ledger = SweepLedger()
    ledger.record(span_id=1, local_speaker="S01", canonical_speaker=None, vector=unit_vector(0), duration_sec=1.0)

    disposition = ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=unit_vector(10),
        duration_sec=2.0,
    )

    assert disposition == REPLACED
    assert ledger.unit_count == 1
    assert ledger.canonical_speaker(1, "S01") == "speaker-0001"


def test_an_unlabelled_unit_is_retained_because_a_sweep_can_rescue_it():
    """An abstained span is exactly the span a later album has the most to say about."""

    ledger = SweepLedger()

    disposition = ledger.record(
        span_id=7,
        local_speaker="S01",
        canonical_speaker=None,
        vector=unit_vector(0),
        duration_sec=0.8,
    )

    assert disposition == RECORDED
    assert ledger.canonical_speaker(7, "S01") is None


@pytest.mark.parametrize(
    "vector, duration, expected",
    [
        ([], 1.0, REJECTED_INVALID_VECTOR),
        ([float("nan"), 0.0], 1.0, REJECTED_INVALID_VECTOR),
        ([float("inf"), 0.0], 1.0, REJECTED_INVALID_VECTOR),
        (["not a number", 0.0], 1.0, REJECTED_INVALID_VECTOR),
        ([1.0, 0.0], 0.0, REJECTED_INVALID_DURATION),
        ([1.0, 0.0], -1.0, REJECTED_INVALID_DURATION),
        ([1.0, 0.0], float("nan"), REJECTED_INVALID_DURATION),
        ([1.0, 0.0], float("inf"), REJECTED_INVALID_DURATION),
    ],
)
def test_an_unusable_observation_is_refused_by_name_and_never_raises(vector, duration, expected):
    ledger = SweepLedger()

    assert (
        ledger.record(
            span_id=1,
            local_speaker="S01",
            canonical_speaker="speaker-0001",
            vector=vector,
            duration_sec=duration,
        )
        == expected
    )
    assert ledger.unit_count == 0


def test_the_cap_refuses_new_units_rather_than_evicting_old_ones():
    """A sweep's value is in the early decisions, so the early evidence is what the cap keeps."""

    ledger = SweepLedger(max_units=2)
    for span_id in (1, 2):
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker="speaker-0001",
            vector=unit_vector(0),
            duration_sec=1.0,
        )

    disposition = ledger.record(
        span_id=3,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=unit_vector(0),
        duration_sec=1.0,
    )

    assert disposition == REJECTED_LEDGER_FULL
    assert (ledger.unit_count, ledger.refused_units) == (2, 1)
    assert [span_id for span_id, _ in ledger.spans()] == [1, 2]


def test_a_full_ledger_still_accepts_a_replacement_of_a_unit_it_already_holds():
    ledger = SweepLedger(max_units=1)
    ledger.record(span_id=1, local_speaker="S01", canonical_speaker=None, vector=unit_vector(0), duration_sec=1.0)

    disposition = ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=unit_vector(0),
        duration_sec=3.0,
    )

    assert disposition == REPLACED
    assert (ledger.unit_count, ledger.refused_units) == (1, 0)


def test_the_ledger_bound_is_positive():
    with pytest.raises(ValueError):
        SweepLedger(max_units=0)


def test_the_default_bound_covers_a_three_hour_meeting():
    """F3 measured 443 spans in 1029 s; the arithmetic behind the cap is in the module."""

    spans_per_second = 443 / 1029
    three_hour_spans = spans_per_second * 3 * 3600
    assert SWEEP_LEDGER_MAX_UNITS >= 2 * three_hour_spans


# --------------------------------------------------------------------------------------
# What a sweep may and may not change
# --------------------------------------------------------------------------------------


def test_a_sweep_reassigns_a_unit_the_live_path_labelled_wrongly():
    """The whole point: better evidence later means the earlier label can be corrected."""

    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(90), 4.0),
    )
    ledger = SweepLedger()
    ledger.record(
        span_id=3,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(5),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert [item.to_dict()["canonical_speaker"] for item in revision.corrections] == ["speaker-0001"]
    correction = revision.corrections[0]
    assert (correction.span_id, correction.local_speaker) == (3, "S01")
    assert (correction.previous_speaker, correction.reason) == ("speaker-0002", REASSIGNED)
    assert correction.score == pytest.approx(cosine_similarity(unit_vector(5), unit_vector(0)))


def test_a_sweep_labels_a_unit_the_live_path_left_unlabelled():
    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    ledger = SweepLedger()
    ledger.record(span_id=3, local_speaker="S01", canonical_speaker=None, vector=unit_vector(5), duration_sec=0.8)

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert [(item.reason, item.previous_speaker, item.canonical_speaker) for item in revision.corrections] == [
        (LABELLED, None, "speaker-0001")
    ]


def test_a_sweep_never_removes_a_label_it_cannot_replace():
    """Identity answers *who*, never *whether* (J2). An erasure is not a correction."""

    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    ledger = SweepLedger()
    # A voice that matches nothing in the album: 89 degrees away from its only reference.
    ledger.record(
        span_id=3,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(89),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert revision.corrections == ()
    assert ledger.canonical_speaker(3, "S01") == "speaker-0002"


def test_a_sweep_never_invents_a_canonical_speaker():
    """Births are a live decision under the 16-speaker cap; a sweep only redistributes."""

    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    ledger = SweepLedger()
    for span_id, angle in ((1, 5), (2, 88), (3, 175)):
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=None,
            vector=unit_vector(angle),
            duration_sec=2.0,
        )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert {item.canonical_speaker for item in revision.corrections} <= set(album.speakers())


def test_a_near_tie_between_the_incumbent_and_a_rival_leaves_the_label_alone():
    """Two near-equal candidates must not trade a unit back and forth every cadence."""

    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(60), 4.0),
    )
    ledger = SweepLedger()
    # Exactly between the two references, so neither wins by the margin.
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(30),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert cosine_similarity(unit_vector(0), unit_vector(60)) < SWEEP_MERGE_THRESHOLD
    assert revision.corrections == ()
    assert dict(revision.dispositions) == {KEPT_AMBIGUOUS: 1}


def test_a_sweep_can_repair_a_birth_without_matching_the_unit_to_itself():
    """A provisional born from this unit is not independent evidence for this unit."""

    album = FingerprintAlbum()
    album.observe(
        canonical_speaker="speaker-0001",
        vector=unit_vector(0),
        duration_sec=1.2,
        span_id=7,
    )
    album.observe(
        canonical_speaker="speaker-0002",
        vector=unit_vector(20),
        duration_sec=4.0,
        span_id=2,
    )
    ledger = SweepLedger()
    ledger.record(
        span_id=7,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=unit_vector(0),
        duration_sec=1.2,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert [
        (item.reason, item.previous_speaker, item.canonical_speaker)
        for item in revision.corrections
    ] == [(REASSIGNED, "speaker-0001", "speaker-0002")]
    ledger.apply(revision)
    assert sweep(ledger=ledger, album=album, config=CONFIG).corrections == ()


def test_every_correction_beats_the_incumbent_by_the_deployed_margin():
    """The stability property itself, asserted over corrections rather than over one contrived tie.

    Under the deployed thresholds the production matcher already guarantees this -- it refuses to
    assign at all when the winner fails to beat the runner-up by `min_match_margin`, and the
    incumbent is one of the runners-up. `KEPT_BELOW_MARGIN` therefore never fires here; it exists
    for a deployment that states a margin above its own match floor, where the matcher's guarantee
    stops covering the incumbent. That the guard is redundant at 0.35/0.1 is a fact about those
    two numbers, not a property to rely on.
    """

    references = {"speaker-0001": unit_vector(0), "speaker-0002": unit_vector(90)}
    album = album_with(*((speaker, vector, 4.0) for speaker, vector in references.items()))
    ledger = SweepLedger()
    vectors = {1: unit_vector(5), 2: unit_vector(85), 3: unit_vector(12)}
    for span_id, canonical in ((1, "speaker-0002"), (2, "speaker-0001"), (3, None)):
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=canonical,
            vector=vectors[span_id],
            duration_sec=2.0,
        )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert len(revision.corrections) == 3
    for correction in revision.corrections:
        incumbent = references.get(correction.previous_speaker)
        incumbent_score = 0.0 if incumbent is None else cosine_similarity(vectors[correction.span_id], incumbent)
        assert correction.score - incumbent_score >= CONFIG.min_match_margin
    assert KEPT_BELOW_MARGIN not in dict(revision.dispositions)


def test_an_ambiguous_span_keeps_the_labels_it_has():
    """The live path abstains for the whole span; a sweep declines the whole span. One ruling."""

    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(2), 4.0),
    )
    ledger = SweepLedger()
    for local, angle in (("S01", 0.5), ("S02", 1.5)):
        ledger.record(
            span_id=1,
            local_speaker=local,
            canonical_speaker=None,
            vector=unit_vector(angle),
            duration_sec=2.0,
        )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert revision.corrections == ()
    assert dict(revision.dispositions)[KEPT_AMBIGUOUS] == 2


def test_two_units_in_one_span_cannot_land_on_the_same_speaker():
    """One-to-one inside a span is the production matcher's rule, and a sweep inherits it."""

    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(90), 4.0),
    )
    ledger = SweepLedger()
    ledger.record(span_id=1, local_speaker="S01", canonical_speaker=None, vector=unit_vector(3), duration_sec=2.0)
    ledger.record(span_id=1, local_speaker="S02", canonical_speaker=None, vector=unit_vector(87), duration_sec=2.0)

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assigned = {item.local_speaker: item.canonical_speaker for item in revision.corrections}
    assert assigned == {"S01": "speaker-0001", "S02": "speaker-0002"}
    assert len(set(assigned.values())) == len(assigned)


def test_a_speaker_with_no_reference_leaves_every_unit_alone_by_name():
    ledger = SweepLedger()
    ledger.record(span_id=1, local_speaker="S01", canonical_speaker="speaker-0001", vector=unit_vector(0), duration_sec=2.0)

    revision = sweep(ledger=ledger, album=FingerprintAlbum(), config=CONFIG)

    assert revision.corrections == ()
    assert dict(revision.dispositions) == {NO_REFERENCE: 1}
    assert (revision.swept_spans, revision.swept_units) == (1, 1)


def test_a_vector_no_reference_can_be_compared_with_is_named_not_silently_unmatched():
    album = album_with(("speaker-0001", (1.0, 0.0), 4.0))
    ledger = SweepLedger()
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=(1.0, 0.0, 0.0),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert dict(revision.dispositions) == {KEPT_UNSCORED: 1}
    assert revision.corrections == ()


# --------------------------------------------------------------------------------------
# Merging: one voice that was born twice
# --------------------------------------------------------------------------------------


def test_two_speakers_above_the_merge_threshold_are_one_voice():
    album = album_with(
        ("speaker-0001", unit_vector(0), 8.0),
        ("speaker-0007", unit_vector(30), 2.0),
    )
    ledger = SweepLedger()
    ledger.record(
        span_id=5,
        local_speaker="S01",
        canonical_speaker="speaker-0007",
        vector=unit_vector(30),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert cosine_similarity(unit_vector(0), unit_vector(30)) >= SWEEP_MERGE_THRESHOLD
    assert [(item.kept, item.absorbed) for item in revision.merges] == [("speaker-0001", "speaker-0007")]
    assert [(item.reason, item.previous_speaker, item.canonical_speaker) for item in revision.corrections] == [
        (MERGED, "speaker-0007", "speaker-0001")
    ]


def test_the_best_established_voice_keeps_its_id():
    """Most admitted speech wins, not the lowest id -- otherwise birth order decides identity."""

    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=unit_vector(0), duration_sec=2.0, span_id=1)
    album.observe(canonical_speaker="speaker-0009", vector=unit_vector(20), duration_sec=9.0, span_id=2)

    revision = sweep(ledger=SweepLedger(), album=album, config=CONFIG)

    assert [(item.kept, item.absorbed) for item in revision.merges] == [("speaker-0009", "speaker-0001")]


def test_a_merge_needs_an_admitted_bank_on_both_sides():
    """A sub-admission stand-in may be matched against; it may not collapse two speakers."""

    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=unit_vector(0), duration_sec=4.0, span_id=1)
    # Below the 1.0 s admission floor, so this speaker is held provisionally and never merged.
    album.observe(canonical_speaker="speaker-0002", vector=unit_vector(5), duration_sec=0.4, span_id=2)

    revision = sweep(ledger=SweepLedger(), album=album, config=CONFIG)

    assert album.exemplar_count("speaker-0002") == 0
    assert album.has_provisional("speaker-0002")
    assert revision.merges == ()


def test_a_provisional_only_speaker_is_still_matched_against():
    """Un-mergeable is not unmatchable: the stand-in is what the live path is matching on now."""

    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0002", vector=unit_vector(0), duration_sec=0.4, span_id=1)
    ledger = SweepLedger()
    ledger.record(span_id=1, local_speaker="S01", canonical_speaker=None, vector=unit_vector(3), duration_sec=0.6)

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert album.exemplar_count("speaker-0002") == 0
    assert [(item.reason, item.canonical_speaker) for item in revision.corrections] == [(LABELLED, "speaker-0002")]


def test_a_unit_labelled_with_a_speaker_the_album_has_forgotten_is_re_matched_not_refused():
    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    ledger = SweepLedger()
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0099",
        vector=unit_vector(4),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert [(item.previous_speaker, item.canonical_speaker, item.reason) for item in revision.corrections] == [
        ("speaker-0099", "speaker-0001", REASSIGNED)
    ]


def test_a_merged_group_matches_on_the_union_of_its_exemplars():
    """Not the average of two centroids: the exemplars carry the seconds that weight them."""

    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=unit_vector(0), duration_sec=9.0, span_id=1)
    album.observe(canonical_speaker="speaker-0002", vector=unit_vector(30), duration_sec=2.0, span_id=2)
    ledger = SweepLedger()
    # A voice at 24 degrees is closer to speaker-0002's own centroid than to the merged one, so a
    # sweep that matched against the absorbed speaker's vector would answer differently here.
    ledger.record(span_id=1, local_speaker="S01", canonical_speaker=None, vector=unit_vector(24), duration_sec=2.0)

    revision = sweep(ledger=ledger, album=album, config=CONFIG)
    merged_reference = (
        9.0 * unit_vector(0)[0] + 2.0 * unit_vector(30)[0],
        9.0 * unit_vector(0)[1] + 2.0 * unit_vector(30)[1],
    )

    assert [item.canonical_speaker for item in revision.corrections] == ["speaker-0001"]
    assert revision.corrections[0].score == pytest.approx(cosine_similarity(unit_vector(24), merged_reference))


def test_a_merge_applies_even_to_a_span_the_sweep_declines_to_re_assign():
    """A merge is not an assignment question. A stale id is not a preserved label."""

    album = FingerprintAlbum()
    album.observe(canonical_speaker="speaker-0001", vector=unit_vector(0), duration_sec=8.0, span_id=1)
    album.observe(canonical_speaker="speaker-0002", vector=unit_vector(20), duration_sec=8.0, span_id=2)
    ledger = SweepLedger()
    # Two units that sit on top of each other: the matcher cannot tell them apart, so the span is
    # ambiguous -- and both of them still belong to a speaker that no longer exists separately.
    ledger.record(
        span_id=4,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(10),
        duration_sec=2.0,
    )
    ledger.record(
        span_id=4,
        local_speaker="S02",
        canonical_speaker="speaker-0002",
        vector=unit_vector(10),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert [item.absorbed for item in revision.merges] == ["speaker-0002"]
    assert {item.reason for item in revision.corrections} == {MERGED}
    assert {item.canonical_speaker for item in revision.corrections} == {"speaker-0001"}


def test_a_chain_of_similar_speakers_merges_into_one_group():
    album = FingerprintAlbum()
    for index, angle in enumerate((0, 25, 50)):
        album.observe(
            canonical_speaker=f"speaker-{index + 1:04d}",
            vector=unit_vector(angle),
            duration_sec=4.0 + index,
            span_id=index,
        )

    revision = sweep(ledger=SweepLedger(), album=album, config=CONFIG)

    # 0-50 degrees is 0.643, under the threshold on its own; the chain through 25 links them.
    assert cosine_similarity(unit_vector(0), unit_vector(50)) < SWEEP_MERGE_THRESHOLD
    assert {item.kept for item in revision.merges} == {"speaker-0003"}
    assert {item.absorbed for item in revision.merges} == {"speaker-0001", "speaker-0002"}


# --------------------------------------------------------------------------------------
# Stability
# --------------------------------------------------------------------------------------


def test_a_sweep_is_deterministic():
    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(90), 4.0),
    )
    ledger = SweepLedger()
    for span_id, angle, canonical in ((1, 5, "speaker-0002"), (2, 85, "speaker-0001"), (3, 45, None)):
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=canonical,
            vector=unit_vector(angle),
            duration_sec=2.0,
        )

    first = sweep(ledger=ledger, album=album, config=CONFIG)
    second = sweep(ledger=ledger, album=album, config=CONFIG)

    assert first == second


def test_applying_a_revision_leaves_nothing_for_the_next_sweep_to_correct():
    """Convergence, not oscillation: unchanged evidence must produce no second correction."""

    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(90), 4.0),
    )
    ledger = SweepLedger()
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(5),
        duration_sec=2.0,
    )
    ledger.record(span_id=2, local_speaker="S01", canonical_speaker=None, vector=unit_vector(85), duration_sec=2.0)

    first = sweep(ledger=ledger, album=album, config=CONFIG)
    applied = ledger.apply(first)
    second = sweep(ledger=ledger, album=album, config=CONFIG)

    assert (len(first.corrections), applied) == (2, 2)
    assert second.corrections == ()
    assert (ledger.canonical_speaker(1, "S01"), ledger.canonical_speaker(2, "S01")) == (
        "speaker-0001",
        "speaker-0002",
    )


def test_a_repeated_merge_claim_stands_until_the_album_itself_is_merged():
    """Applying the corrections does not un-split the album, and the revision says so."""

    album = album_with(
        ("speaker-0001", unit_vector(0), 8.0),
        ("speaker-0007", unit_vector(30), 2.0),
    )
    ledger = SweepLedger()
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0007",
        vector=unit_vector(30),
        duration_sec=2.0,
    )

    ledger.apply(sweep(ledger=ledger, album=album, config=CONFIG))
    second = sweep(ledger=ledger, album=album, config=CONFIG)

    assert second.corrections == ()
    assert [item.absorbed for item in second.merges] == ["speaker-0007"]


def test_an_empty_ledger_sweeps_to_an_empty_revision():
    revision = sweep(ledger=SweepLedger(), album=FingerprintAlbum(), config=CONFIG)

    assert revision == SweepRevision()
    assert revision.is_empty


def test_the_revision_serialises_to_named_fields():
    album = album_with(
        ("speaker-0001", unit_vector(0), 4.0),
        ("speaker-0002", unit_vector(90), 4.0),
    )
    ledger = SweepLedger()
    ledger.record(
        span_id=2,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(0),
        duration_sec=2.0,
    )

    payload = sweep(ledger=ledger, album=album, config=CONFIG).to_dict()

    assert payload["corrections"] == [
        {
            "span_id": 2,
            "local_speaker": "S01",
            "previous_speaker": "speaker-0002",
            "canonical_speaker": "speaker-0001",
            "reason": REASSIGNED,
            "score": 1.0,
        }
    ]
    assert payload["merges"] == []
    assert payload["dispositions"] == {}
    assert (payload["swept_spans"], payload["swept_units"]) == (1, 1)


def test_adr_0002_starting_parameters_are_the_defaults():
    assert (SWEEP_MERGE_THRESHOLD, SWEEP_INTERVAL_SECONDS) == (0.70, 60.0)


def test_a_kept_unit_is_counted_but_produces_no_correction():
    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    ledger = SweepLedger()
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=unit_vector(2),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert revision.corrections == ()
    assert dict(revision.dispositions) == {KEPT: 1}


# --------------------------------------------------------------------------------------
# The sweeper -- one meeting's retained evidence, cadence and applied revisions
# --------------------------------------------------------------------------------------


def sweeper_with(album: FingerprintAlbum, **kwargs) -> LiveIdentitySweeper:
    return LiveIdentitySweeper(album=album, config=CONFIG, **kwargs)


def test_the_sweeper_records_a_unit_twice_and_the_second_one_replaces_the_first():
    """The live path's ordinary shape: a vector is retained before its label exists.

    `_reconcile_committed_vectors` only learns an assignment when the *next* span is prepared,
    so every unit arrives unlabelled first. If the second arrival counted as a new unit the
    ledger's cap would be reached at half the meeting length it is sized for.
    """

    sweeper = sweeper_with(album_with(("speaker-0001", unit_vector(0), 4.0)))

    first = sweeper.record(
        span_id=7,
        local_speaker="S01",
        canonical_speaker=None,
        vector=unit_vector(1),
        duration_sec=2.0,
    )
    second = sweeper.record(
        span_id=7,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=unit_vector(1),
        duration_sec=2.0,
    )

    assert (first, second) == (RECORDED, REPLACED)
    assert sweeper.ledger.unit_count == 1
    assert sweeper.ledger.canonical_speaker(7, "S01") == "speaker-0001"


def test_the_cadence_is_meeting_time_and_fires_once_per_interval():
    sweeper = sweeper_with(album_with(("speaker-0001", unit_vector(0), 4.0)), interval_seconds=10.0)

    assert sweeper.maybe_sweep(meeting_seconds=0.0) is None
    assert sweeper.maybe_sweep(meeting_seconds=9.999) is None
    assert sweeper.maybe_sweep(meeting_seconds=10.0) is not None
    assert sweeper.maybe_sweep(meeting_seconds=12.5) is None
    assert sweeper.maybe_sweep(meeting_seconds=19.9) is None
    assert sweeper.maybe_sweep(meeting_seconds=20.1) is not None
    assert sweeper.sweeps == 2


def test_a_long_gap_schedules_the_next_sweep_from_now_rather_than_catching_up():
    """A meeting that arrives in a burst after an outage is not swept once per skipped interval.

    The evidence retained during a gap is nothing, so a burst of sweeps over it would re-match
    the same ledger against the same album several times and produce identical revisions.
    """

    sweeper = sweeper_with(album_with(("speaker-0001", unit_vector(0), 4.0)), interval_seconds=10.0)

    assert sweeper.maybe_sweep(meeting_seconds=305.0) is not None
    assert sweeper.sweeps == 1
    assert sweeper.maybe_sweep(meeting_seconds=309.0) is None
    assert sweeper.maybe_sweep(meeting_seconds=310.0) is not None
    assert sweeper.sweeps == 2


def test_an_untrustworthy_meeting_time_does_not_sweep_and_does_not_raise():
    """The *Duration vs timestamp* rule, one layer out: a bad number degrades, it never ends a
    meeting. Meeting time is a sample count divided by the sample rate and cannot go backwards,
    so a non-finite value here means a caller lost track of the meeting, not that time did."""

    sweeper = sweeper_with(album_with(("speaker-0001", unit_vector(0), 4.0)), interval_seconds=10.0)

    assert sweeper.maybe_sweep(meeting_seconds=float("nan")) is None
    assert sweeper.maybe_sweep(meeting_seconds=float("-inf")) is None
    assert sweeper.maybe_sweep(meeting_seconds=None) is None
    assert sweeper.sweeps == 0
    assert sweeper.maybe_sweep(meeting_seconds=10.0) is not None


@pytest.mark.parametrize("interval", [0.0, -1.0, float("nan"), float("inf")])
def test_the_sweeper_refuses_a_cadence_that_would_never_come_round(interval):
    with pytest.raises(ValueError):
        sweeper_with(album_with(("speaker-0001", unit_vector(0), 4.0)), interval_seconds=interval)


def test_a_sweep_applies_its_own_revision_so_the_next_one_converges():
    album = album_with(("speaker-0001", unit_vector(0), 4.0), ("speaker-0002", unit_vector(90), 4.0))
    sweeper = sweeper_with(album, interval_seconds=10.0)
    sweeper.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0002",
        vector=unit_vector(2),
        duration_sec=2.0,
    )

    first = sweeper.maybe_sweep(meeting_seconds=10.0)
    second = sweeper.maybe_sweep(meeting_seconds=20.0)

    assert [item.canonical_speaker for item in first.corrections] == ["speaker-0001"]
    assert second.corrections == ()
    assert sweeper.sweeps == 2
    assert sweeper.corrections == 1
    assert sweeper.latest_revision is second


def test_the_cumulative_correction_count_survives_a_revision_being_consumed():
    """`corrections` answers "how much of this meeting has been rewritten", so it only grows."""

    album = album_with(("speaker-0001", unit_vector(0), 4.0), ("speaker-0002", unit_vector(90), 4.0))
    sweeper = sweeper_with(album, interval_seconds=10.0)
    for span_id in (1, 2):
        sweeper.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker="speaker-0002",
            vector=unit_vector(2),
            duration_sec=2.0,
        )
        sweeper.maybe_sweep(meeting_seconds=10.0 * span_id)

    assert sweeper.corrections == 2
    assert sweeper.latest_revision.corrections != ()


def test_an_empty_revision_is_not_logged_and_a_real_one_names_only_counts(caplog):
    album = album_with(("speaker-0001", unit_vector(0), 4.0), ("speaker-0002", unit_vector(90), 4.0))
    sweeper = sweeper_with(album)

    with caplog.at_level("INFO", logger="moss_transcribe_diarize.live.identity"):
        sweeper.sweep_now()
        assert caplog.messages == []
        sweeper.record(
            span_id=1,
            local_speaker="S01",
            canonical_speaker="speaker-0002",
            vector=unit_vector(2),
            duration_sec=2.0,
        )
        sweeper.sweep_now()

    assert caplog.messages == ["live identity sweep: spans=1 units=1 corrections=1 merges=0"]


def test_the_sweeper_shares_the_album_it_re_matches_against():
    """One album, not a copy: the whole point of a retrospective sweep is that it sees the
    album as it stands *now*, including exemplars admitted after the unit it is re-matching."""

    album = FingerprintAlbum()
    sweeper = sweeper_with(album)
    sweeper.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker=None,
        vector=unit_vector(0),
        duration_sec=2.0,
    )

    assert sweeper.sweep_now().corrections == ()

    album.observe(canonical_speaker="speaker-0001", vector=unit_vector(1), duration_sec=4.0, span_id=2)
    rescued = sweeper.sweep_now()

    assert [(item.canonical_speaker, item.reason) for item in rescued.corrections] == [
        ("speaker-0001", LABELLED)
    ]


# --------------------------------------------------------------------------------------
# Scoring a whole span at once, and the scalar rule it must never disagree with
# --------------------------------------------------------------------------------------


def _realistic_ledger_and_album(*, speakers=6, spans=40, dimension=32):
    """A meeting shaped like a real one: many spans, several speakers, a real embedding width."""

    import random

    rng = random.Random(4)

    def voice(seed):
        local = random.Random(seed)
        raw = [local.gauss(0.0, 1.0) for _ in range(dimension)]
        norm = math.sqrt(sum(value * value for value in raw))
        return tuple(value / norm for value in raw)

    album = FingerprintAlbum()
    for index in range(speakers):
        for exemplar in range(3):
            album.observe(
                canonical_speaker=f"speaker-{index:04d}",
                vector=voice(index * 10 + exemplar),
                duration_sec=2.0,
                span_id=exemplar,
            )
    ledger = SweepLedger()
    for span_id in range(spans):
        speaker = rng.randrange(speakers)
        ledger.record(
            span_id=span_id,
            local_speaker="S01",
            canonical_speaker=f"speaker-{rng.randrange(speakers):04d}",
            vector=voice(speaker * 10 + rng.randrange(3)),
            duration_sec=1.5,
        )
    return ledger, album


def test_scoring_a_span_as_a_batch_answers_exactly_what_the_scalar_rule_answers(monkeypatch):
    """The batch path is an optimisation, so it has to be provably indistinguishable.

    Measured on F3's own shape -- 443 spans, 886 units, 16 speakers, 256 dimensions -- one
    sweep costs 295 ms scoring pair by pair and 39 ms scoring span by span, and at three hours
    3097 ms against 366 ms. The sweep runs inline on the serial canonical pump, where 3 s is
    longer than the whole 2.5 s span cap, so the difference is between a cadence that fits
    inside a live meeting and one that stalls it.
    """

    ledger, album = _realistic_ledger_and_album()

    batched = sweep(ledger=ledger, album=album, config=CONFIG)
    monkeypatch.setattr(
        "moss_transcribe_diarize.app.live_identity_sweep._reference_matrix",
        lambda references, reference_speakers: None,
    )
    scalar = sweep(ledger=ledger, album=album, config=CONFIG)

    assert batched.corrections != ()
    assert batched.to_dict() == scalar.to_dict()


def test_a_unit_with_no_length_sends_its_span_down_the_scalar_path_and_is_named(recwarn):
    """`_unit_rows` refuses exactly what `cosine_similarity` refuses, so a batch can never
    answer where the scalar rule would have said "undefined".

    The refusal is made *before* the division rather than caught after it: dividing by a zero
    norm produces the same `None` either way, and also a `RuntimeWarning` per span for the life
    of the meeting. A live service that has to emit noise to reach the right answer is one
    nobody will read the logs of.
    """

    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    ledger = SweepLedger()
    ledger.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker="speaker-0001",
        vector=(0.0, 0.0),
        duration_sec=2.0,
    )

    revision = sweep(ledger=ledger, album=album, config=CONFIG)

    assert dict(revision.dispositions) == {KEPT_UNSCORED: 1}
    assert revision.corrections == ()
    assert [str(item.message) for item in recwarn.list] == []


def test_a_revision_is_handed_over_once_and_an_empty_sweep_hands_over_nothing():
    """The consumption half, kept apart from the diagnosis half.

    `latest_revision` never empties -- it answers "what did the last sweep think" for as long
    as the meeting runs. `take_revision` is what the transcript's owner calls, so it must
    empty: a caller that polled it on every span would otherwise re-publish the same
    correction for the rest of the meeting, and a correction re-applied is a version bump a
    reader is told to go and fetch for nothing.
    """

    album = album_with(("speaker-0001", unit_vector(0), 4.0))
    sweeper = sweeper_with(album)
    assert sweeper.take_revision() is None

    sweeper.record(
        span_id=1,
        local_speaker="S01",
        canonical_speaker=None,
        vector=unit_vector(0),
        duration_sec=2.0,
    )
    revision = sweeper.sweep_now()

    assert revision.corrections != ()
    assert sweeper.take_revision() is revision
    assert sweeper.take_revision() is None
    # Diagnosis still answers after consumption; only the claim was handed over.
    assert sweeper.latest_revision is revision

    # The applied revision converged, so the next sweep proposes nothing -- and a sweep with
    # nothing to say hands over nothing rather than an empty revision the caller must test.
    assert sweeper.sweep_now().corrections == ()
    assert sweeper.take_revision() is None
