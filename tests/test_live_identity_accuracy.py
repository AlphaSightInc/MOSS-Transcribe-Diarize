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
    SWEEP_INTERVAL_SECONDS,
    assert_fixture_matches_production,
    evidence_units,
    load_meeting,
    mean_accuracy,
    mean_live_accuracy,
    min_accuracy,
    replay,
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


def test_the_retrospective_sweep_is_invisible_to_the_live_path():
    """A sweep rewrites history; it must not change what the live path wrote in the first place.

    This is the harness's own integrity check and it has to come before any convergence
    claim: if retaining evidence or re-matching it perturbed the causal path, the
    `live_accuracy` a swept run reports would be a different meeting's number and the gap
    below would be measuring the perturbation instead of the sweep.
    """

    swept = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)
    unswept = replay_all(policy="album")

    for name in MEETINGS:
        assert swept[name].live_accuracy == unswept[name].accuracy, name
        assert swept[name].canonical_speaker_count == unswept[name].canonical_speaker_count, name
        assert unswept[name].sweeps == 0 and unswept[name].corrections == 0, name


def test_the_swept_transcript_converges_on_adr_0002s_whole_file_accuracy():
    """ADR-0002 gate B, on production code: the step the ADR calls the album's other half.

    The ADR classifies the album shipped alone as "a terminal-state failure" -- without
    retrospective rewrites, live accuracy diverges from whole-file the way the sibling
    project's did at <80 %. Measured here: the transcript a reader ends the meeting with is
    materially better than the one they were reading during it, on every meeting, and it lands
    above the ADR's own gate-A figure.

    The convergence half is true by construction (the final sweep *is* the whole-file pass --
    see the harness docstring), so what this node actually proves is that converging there is
    worth something: both numbers are scored against ground truth, so a rewriter that churned
    labels without improving them would fail here rather than pass.
    """

    swept = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)

    for name in MEETINGS:
        result = swept[name]
        assert result.accuracy > result.live_accuracy, name
        assert result.corrections > 0, name
    assert min_accuracy(swept) >= 0.97
    assert mean_accuracy(swept) >= 0.98  # ADR-0002 gate A's own whole-file figure: 98.5 %
    assert mean_accuracy(swept) - mean_live_accuracy(swept) >= 0.04


def test_applying_a_revision_leaves_nothing_for_the_next_sweep_to_correct():
    """Convergence, not oscillation -- asserted on real meetings rather than a built ledger.

    `test_live_identity_sweep` proves this property over constructed evidence. It is worth
    re-asking of eight real meetings because the failure it rules out is a cadence one: two
    near-equal references trading a unit back and forth would show up as a sweep that keeps
    finding work on evidence that has not changed, and every trade is a visible transcript
    revision a reader watches happen.
    """

    swept = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)

    for name in MEETINGS:
        assert swept[name].sweeps > 1, name
        assert swept[name].residual_corrections == 0, name


def test_the_sweep_closes_the_gap_the_16_speaker_bound_opens():
    """Candidate 55 re-priced against the finished design: the bound costs the reader nothing.

    Measured in iteration 16, `max_identity_speakers` 16 costs the *live* transcript 4.5 pp,
    which is the whole of the distance between production and ADR-0002's number. Measured
    here, it costs the *swept* transcript nothing at all -- capped and uncapped land on the
    same figure -- because the sweep re-matches the units a saturated capacity stranded.

    That does not close candidate 55. A voice arriving after saturation is still unlabelled
    for a reader watching live, and this corpus is read speech with a 0.5 s evidence floor.
    It does say the defect is a *latency* of labelling rather than a permanent loss of it,
    which is a materially different thing to authorize a fix for.
    """

    capped = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)
    uncapped = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS, max_speakers=64)
    uncapped_live = replay_all(policy="album", max_speakers=64)

    assert mean_accuracy(capped) >= mean_accuracy(uncapped_live)
    assert abs(mean_accuracy(capped) - mean_accuracy(uncapped)) < 0.005
    assert mean_live_accuracy(uncapped) - mean_live_accuracy(capped) >= 0.03


def test_the_gain_is_re_matching_and_not_a_single_merge():
    """The merge does not fire on this corpus, and the number says so out loud.

    Iteration 22 landed the merge expecting it to heal candidate 55's fragmentation. It does
    not, here, and the reason is structural rather than incidental: a merge needs an *admitted*
    exemplar bank on both sides, and the canonical speakers a saturated capacity mints are born
    from sub-admission fragments that never earn one. The banked speakers, meanwhile, are
    genuinely different voices -- their centroids sit at 0.19-0.43, nowhere near the 0.70
    threshold.

    So every point of the gain above is re-matching. The node is kept in this falsifiable form
    on purpose: if a parameter change ever makes a merge fire on this corpus, this fails and
    the finding gets re-measured instead of being inherited.
    """

    swept = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)

    for name in MEETINGS:
        assert swept[name].merges == 0, name
        assert 0.0 < swept[name].rewritten_share < 0.20, name


def test_a_sweep_needs_an_album_to_re_match_against():
    """`policy="overwrite"` has no album, so sweeping it would answer a different question.

    A sweep that silently found nothing to match against would report "the sweep did not help"
    for a configuration where there was never anything to sweep -- the same class of defect as
    a verdict word that does not name what it decides.
    """

    with pytest.raises(ValueError, match="album"):
        replay(load_meeting(MEETINGS[0]), policy="overwrite", sweep_interval=SWEEP_INTERVAL_SECONDS)
