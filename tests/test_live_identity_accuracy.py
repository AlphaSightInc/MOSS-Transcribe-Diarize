"""ADR-0002's acceptance bar, measured against the production live identity path.

ADR-0002 accepts the fingerprint album on a number -- ">= 90-95 % live speaker accuracy,
materially above latest-span overwrite" -- that this repository had no way to compute. Its
own 98.5 %-vs-66.4 % came from a prototype that re-implemented the matcher, so a green
`test_live_identity_album` suite proved the album's *rules* and said nothing about whether
the shipped composition labels a meeting correctly.

These nodes drive the real `BoundedCausalIdentityPreparer` + `WeSpeakerLiveEvidenceProvider`
+ `FingerprintAlbum` over eight labelled meetings carrying the real encoder's vectors. See
`tests/live_identity_accuracy.py` for what is real, what is substituted, and the two
fidelity limits the corpus imposes.
"""

import pytest

from live_identity_accuracy import (
    ADR_MIN_MATCH_MARGIN,
    ADR_MIN_MATCH_SCORE,
    DEPLOYED_MIN_MATCH_MARGIN,
    DEPLOYED_MIN_MATCH_SCORE,
    FIXTURE_EMBEDDING_SILENCE_SPLIT_SECONDS,
    MEETINGS,
    SILENCE_SPLIT_SECONDS,
    assert_fixture_matches_production,
    evidence_units,
    load_meeting,
    mean_accuracy,
    min_accuracy,
    replay_all,
)


@pytest.mark.parametrize("name", MEETINGS)
def test_the_fixture_is_what_production_would_have_embedded(name):
    """The substituted encoder is only honest if production selects the same speech.

    Replanning the meeting has to reproduce the stored evidence units exactly, and
    production's own interval filter has to select, for every unit, the seconds of speech
    the stored vector was embedded from. Without this the accuracy numbers below would be
    measuring a corpus that drifted away from the code.
    """

    assert_fixture_matches_production(load_meeting(name))


@pytest.mark.parametrize("name", MEETINGS)
def test_the_corpus_cannot_tell_the_two_silence_splits_apart(name):
    """The plan runs at the deployed 0.5 s split; the vectors were embedded at 0.6 s.

    That is only sound while no inter-utterance gap in the corpus falls between the two, so
    the claim is asserted rather than assumed. If a regenerated corpus ever lands a gap in
    that window this node fails first, which is the right place to find out -- the
    alternative is an accuracy number quietly measured on a different span plan.
    """

    meeting = load_meeting(name)
    assert SILENCE_SPLIT_SECONDS < FIXTURE_EMBEDDING_SILENCE_SPLIT_SECONDS
    gaps = meeting.truth[1:, 0] - meeting.truth[:-1, 1]
    assert not ((gaps >= SILENCE_SPLIT_SECONDS) & (gaps < FIXTURE_EMBEDDING_SILENCE_SPLIT_SECONDS)).any()
    assert len(evidence_units(meeting)) == len(
        evidence_units(meeting, silence_split=FIXTURE_EMBEDDING_SILENCE_SPLIT_SECONDS)
    )


def test_the_album_reaches_adr_0002s_live_accuracy_bar():
    """>= 90 % causal live speaker accuracy on every meeting, at ADR-0002 §7's thresholds."""

    results = replay_all(policy="album")

    assert min_accuracy(results) >= 0.90, {name: r.accuracy for name, r in results.items()}
    assert mean_accuracy(results) >= 0.92


def test_the_album_beats_the_latest_span_overwrite_it_replaced():
    """The defect ADR-0002 exists to remove, measured on the code that removed it.

    `policy="overwrite"` is the same production objects with `album=None`, which falls back
    to `_canonical_vectors` -- the latest-span replacement. No revert and no forked
    implementation is needed to measure the before state; it is still reachable.
    """

    album = replay_all(policy="album")
    overwrite = replay_all(policy="overwrite")

    for name in MEETINGS:
        assert album[name].accuracy > overwrite[name].accuracy, name
    assert mean_accuracy(album) - mean_accuracy(overwrite) >= 0.15


def test_accumulation_not_the_admission_floor_is_what_beats_overwrite():
    """Measured: the top-k duration-weighted bank does the work; the duration gate is spare.

    The superseded sixth amendment's central instruction was to raise an enrollment floor.
    Measurement refutes it as the load-bearing part: dropping admission to effectively zero
    costs nothing, because a full bank *is* a duration gate -- `_admit` evicts the shortest
    exemplar -- while collapsing the bank to a single exemplar gives most of the overwrite
    defect back. The admission gate still earns its place on the birth path (it decides what
    is provisional), which is why it is kept; it is simply not what moves this number.
    """

    banked = replay_all(policy="album")
    no_floor = replay_all(policy="album", admission_seconds=0.01)
    single = replay_all(policy="album", exemplars_per_speaker=1)
    overwrite = replay_all(policy="overwrite")

    assert abs(mean_accuracy(no_floor) - mean_accuracy(banked)) < 0.02
    assert mean_accuracy(single) < mean_accuracy(banked) - 0.10
    assert mean_accuracy(banked) - mean_accuracy(single) > mean_accuracy(single) - mean_accuracy(overwrite)


def test_the_deployed_matcher_thresholds_cost_the_album_its_bar():
    """ADR-0002 says the matcher needs recalibrating against album statistics. By how much.

    The album landed without touching `min_match_score` / `min_match_margin`, so the
    deployed live runtime runs the album at thresholds tuned for the policy it replaced.
    Measured, that configuration does not reach the ADR's bar at all -- the recalibration is
    a shipping requirement, not a refinement.

    The pair proved against the bar above is `live_identity_album.ALBUM_MIN_MATCH_*`, which is
    also what a deployment states through the finalizer's `--min-match-score` /
    `--min-match-margin` flags. That is deliberate: measuring one pair and deploying another
    is the whole of the defect this node prices.
    """

    adr = replay_all(policy="album")
    deployed = replay_all(
        policy="album",
        min_match_score=DEPLOYED_MIN_MATCH_SCORE,
        min_match_margin=DEPLOYED_MIN_MATCH_MARGIN,
    )

    assert (DEPLOYED_MIN_MATCH_SCORE, DEPLOYED_MIN_MATCH_MARGIN) != (
        ADR_MIN_MATCH_SCORE,
        ADR_MIN_MATCH_MARGIN,
    )
    assert mean_accuracy(deployed) < 0.90
    assert mean_accuracy(adr) - mean_accuracy(deployed) >= 0.10


def test_the_16_speaker_bound_is_what_holds_the_album_below_the_adrs_own_number():
    """Candidate 55, measured offline and deterministically for the first time.

    Production fragments identities far more than ADR-0002's prototype did: every meeting
    exhausts `max_identity_speakers` 16 for 2-6 real voices, and from then on an unmatched
    voice can only abstain. Lift the bound and the album lands on the ADR's own figure --
    which is also the strongest available check that this harness measures what the ADR
    measured, since overwrite lands on *its* figure at the same time.

    Nothing here proposes shipping a different bound; it prices the one that ships.
    """

    capped = replay_all(policy="album")
    uncapped = replay_all(policy="album", max_speakers=64)
    uncapped_overwrite = replay_all(policy="overwrite", max_speakers=64)

    assert mean_accuracy(uncapped) - mean_accuracy(capped) >= 0.03
    assert mean_accuracy(uncapped) >= 0.97  # ADR-0002 gate A: 98.5 % mean
    assert mean_accuracy(uncapped_overwrite) <= 0.70  # ADR-0002 gate A: 66.4 % mean
    for name in MEETINGS:
        assert capped[name].canonical_speaker_count == 16, name
