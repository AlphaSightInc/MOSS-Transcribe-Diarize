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
    FIXTURE_EMBEDDING_SILENCE_SPLIT_SECONDS,
    MEETINGS,
    PRE_ALBUM_MIN_MATCH_MARGIN,
    PRE_ALBUM_MIN_MATCH_SCORE,
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
    true_speaker_count,
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


def test_the_admission_gate_does_two_separable_jobs_and_this_measures_both():
    """Matching is the bank's job; birth is the gate's. Neither substitutes for the other.

    Until candidate 55's fix this node asserted the admission gate was *spare* -- true while
    it governed only enrollment, because a full bank is itself a duration filter (`_admit`
    evicts the shortest). Q1 gave it the second job, and the two are measured apart here:

    * **matching** -- collapse the bank to one exemplar and most of the overwrite defect comes
      back (0.892 against 0.991 banked, over 0.720 for overwrite). Admission does not rescue
      that; accumulation does.
    * **birth** -- drop the independent birth floor to 0.01 s, the weaker
      "any embedded speech at all"
      floor the ninth amendment records as *measured wrong*, and the mean canonical speaker
      count rises 4.00 -> 6.25 for meetings holding 2-6 voices, costing 0.3 pp of accuracy.
      The bank cannot rescue that either: a speaker that should never have existed has its
      own bank.

    One claim this node used to make is now **false and is deliberately not restated**: that
    the bank's gain over a single exemplar exceeds the album's own gain over overwrite. The
    birth floor lifts the *weakest* reference policy the most -- single-exemplar 0.792 ->
    0.892 against banked 0.934 -> 0.991 -- because a noisy reference is exactly what spurious
    births damage. The ordering flipped; the two jobs are what survive it.
    """

    banked = replay_all(policy="album")
    weak_floor = replay_all(policy="album", birth_min_seconds=0.01)
    single = replay_all(policy="album", exemplars_per_speaker=1)
    overwrite = replay_all(policy="overwrite")

    assert mean_accuracy(overwrite) < mean_accuracy(single) < mean_accuracy(banked) - 0.09

    born = [banked[name].canonical_speaker_count for name in MEETINGS]
    weakly_born = [weak_floor[name].canonical_speaker_count for name in MEETINGS]
    assert sum(weakly_born) > sum(born) * 1.4
    assert mean_accuracy(weak_floor) < mean_accuracy(banked)


def test_the_historical_pre_album_thresholds_cost_the_album_its_bar():
    """ADR-0002 says the matcher needs recalibrating against album statistics. By how much.

    The album initially landed without touching `min_match_score` / `min_match_margin`.
    Measured, that historical configuration does not reach the ADR's bar. Phase N subsequently
    shipped the calibrated pair; this counterfactual prevents that decision being erased.

    The pair proved against the bar above is `live_identity_album.ALBUM_MIN_MATCH_*`, which is
    also what a deployment states through the finalizer's `--min-match-score` /
    `--min-match-margin` flags. That is deliberate: measuring one pair and deploying another
    is the whole of the defect this node prices.
    """

    adr = replay_all(policy="album")
    historical = replay_all(
        policy="album",
        min_match_score=PRE_ALBUM_MIN_MATCH_SCORE,
        min_match_margin=PRE_ALBUM_MIN_MATCH_MARGIN,
    )

    assert (PRE_ALBUM_MIN_MATCH_SCORE, PRE_ALBUM_MIN_MATCH_MARGIN) != (
        ADR_MIN_MATCH_SCORE,
        ADR_MIN_MATCH_MARGIN,
    )
    assert mean_accuracy(historical) < 0.90
    assert mean_accuracy(adr) - mean_accuracy(historical) >= 0.10


def test_the_birth_floor_ends_the_capacity_saturation_candidate_55_priced():
    """Candidate 55, before and after, on the code that ships.

    **Before Q1** every one of these meetings minted exactly 16 canonical speakers -- the
    whole of `max_identity_speakers` -- for 2 to 6 real voices, and once saturated an
    unmatched voice could only abstain. **After**, the count tracks the meeting: never more
    than one canonical above the truth, and the 16-speaker bound stops binding altogether.

    The last assertion is the one that would notice a regression: lifting the bound to 64
    changes *nothing at all* -- every meeting's live accuracy, swept accuracy and canonical
    count are identical -- which can only be true while no meeting is reaching it. It also
    prices the bound honestly for the first time, because the bound was never the defect; the
    births that filled it were.
    """

    capped = replay_all(policy="album")
    uncapped = replay_all(policy="album", max_speakers=64)
    uncapped_overwrite = replay_all(policy="overwrite", max_speakers=64)

    assert mean_accuracy(uncapped_overwrite) <= 0.70  # ADR-0002 gate A: 66.4 % mean
    for name in MEETINGS:
        voices = true_speaker_count(load_meeting(name))
        assert voices <= capped[name].canonical_speaker_count <= voices + 1, name
        assert capped[name].canonical_speaker_count == uncapped[name].canonical_speaker_count, name
        assert capped[name].accuracy == uncapped[name].accuracy, name
        assert capped[name].live_accuracy == uncapped[name].live_accuracy, name


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

    **Re-stated after candidate 55's birth floor, and the change is the finding.** Before Q1
    the sweep carried 6.3 pp -- it was recovering the units a saturated capacity had stranded,
    and it improved every meeting. Now the live path strands almost nothing, so the sweep
    carries 0.5 pp and two of the eight meetings have nothing left to correct. The bar the ADR
    states is on the *final* number and is unchanged and still met; what moved is how much of
    it the reader already had while the meeting was running, which is the direction the fix
    was for. The per-meeting assertion is therefore "never worse", not "always better": a
    sweep that found nothing on an already-correct meeting is the success case, and one that
    made a meeting worse is the failure this still catches.
    """

    swept = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)

    for name in MEETINGS:
        result = swept[name]
        assert result.accuracy >= result.live_accuracy, name
    assert sum(1 for name in MEETINGS if swept[name].corrections > 0) >= len(MEETINGS) - 2
    assert min_accuracy(swept) >= 0.97
    assert mean_accuracy(swept) >= 0.98  # ADR-0002 gate A's own whole-file figure: 98.5 %
    assert mean_accuracy(swept) > mean_live_accuracy(swept)


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


def test_the_birth_floor_gives_the_live_reader_what_the_sweep_used_to_have_to_recover():
    """What Q1 bought, in the one unit that matters: the transcript during the meeting.

    Iteration 16 priced the saturated capacity at 4.5 pp of the *live* transcript and the
    sweep was what recovered it -- correct, but a reader had to wait up to a cadence for a
    label the system could have written immediately. With births gated on evidence the album
    would enrol, the unswept live number lands within 0.2 pp of the old *swept* number
    (0.9913 against 0.9926), and the sweep's remaining work is half a point.

    Asserted as relations between the runs rather than as literals: the corpus is regenerable
    and the encoder is pinned, so what has to stay true is the ordering, not the digits. The
    upper bound on the sweep's remaining gain is not a ceiling on quality -- it is the claim
    that the live path is no longer leaving the sweep a pile of stranded units, and it fails
    if a regression ever puts them back.
    """

    live_now = replay_all(policy="album")
    swept_now = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)

    # The live path alone now reaches ADR-0002's whole-file gate, which before Q1 only the
    # swept transcript did (live 0.928 -> 0.991, swept 0.993 -> 0.997).
    assert mean_live_accuracy(swept_now) >= 0.98
    assert mean_live_accuracy(swept_now) == mean_accuracy(live_now)
    assert 0.0 < mean_accuracy(swept_now) - mean_live_accuracy(swept_now) < 0.02


def test_the_gain_is_re_matching_and_not_a_single_merge():
    """The merge does not fire on this corpus, and the number says so out loud.

    Iteration 22 landed the merge expecting it to heal candidate 55's fragmentation. It does
    not, here, and the reason has changed with candidate 55's fix while the answer has not.
    *Before Q1* a merge was structurally unreachable: it needs an **admitted** exemplar bank on
    both sides, and the canonical speakers a saturated capacity minted were born from
    sub-admission fragments that never earned one. *After Q1* every birth carries an admitted
    exemplar by construction -- so a merge is now eligible on every pair and still never fires,
    because the speakers that remain are genuinely different voices whose centroids sit
    nowhere near the 0.70 threshold. The claim is the stronger one now: not "it could not",
    but "it could and declined".

    So every point of the gain above is re-matching. The node is kept in this falsifiable form
    on purpose: if a parameter change ever makes a merge fire on this corpus, this fails and
    the finding gets re-measured instead of being inherited.
    """

    swept = replay_all(policy="album", sweep_interval=SWEEP_INTERVAL_SECONDS)

    for name in MEETINGS:
        assert swept[name].merges == 0, name
        assert 0.0 <= swept[name].rewritten_share < 0.20, name
    # A sweep that rewrote nothing anywhere would pass the loop above while proving nothing.
    assert sum(swept[name].rewritten_share for name in MEETINGS) > 0.0


def test_a_sweep_needs_an_album_to_re_match_against():
    """`policy="overwrite"` has no album, so sweeping it would answer a different question.

    A sweep that silently found nothing to match against would report "the sweep did not help"
    for a configuration where there was never anything to sweep -- the same class of defect as
    a verdict word that does not name what it decides.
    """

    with pytest.raises(ValueError, match="album"):
        replay(load_meeting(MEETINGS[0]), policy="overwrite", sweep_interval=SWEEP_INTERVAL_SECONDS)
