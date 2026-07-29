from __future__ import annotations

import asyncio

import pytest

from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalResult,
    LIVE_SAMPLE_RATE,
    LabelRevision,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
)


def frame(sequence: int, samples: int) -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=b"\0" * samples * 2, sample_count=samples)


def transcript(seconds: float, text: str = "ok") -> str:
    return f"[0][S01]{text}[{seconds:g}]"


def result(span, text: str | None = None, *, identity_confirmed: bool = True) -> CanonicalResult:
    return CanonicalResult(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=text if text is not None else transcript(span.sample_count / LIVE_SAMPLE_RATE),
        identity_confirmed=identity_confirmed,
    )


def test_accepts_ordered_16khz_pcm_and_backpressures_before_eviction():
    session = LiveSession(max_retained_samples=4)

    first = session.accept_frame(frame(0, 2))
    second = session.accept_frame(frame(1, 2))

    assert (first.start_sample, first.end_sample) == (0, 2)
    assert (second.start_sample, second.end_sample) == (2, 4)
    assert session.snapshot().accepted_samples == 4
    with pytest.raises(ValueError, match="expected frame sequence 2"):
        session.accept_frame(frame(3, 1))
    with pytest.raises(LiveSessionBackpressure):
        session.accept_frame(frame(2, 1))


def test_accepting_audio_never_freezes_a_span_by_itself():
    """The session records a partition; the endpoint policy decides one.

    Accepting audio used to freeze the session's own `hard_cap` span, which collided with
    the identical span the endpoint policy emits for the same sample and was never queued
    for decode either way. Eight seconds of audio is more than any deployed cap (2.5 s) and
    must still leave the partition entirely in the caller's hands.
    """
    session = LiveSession(max_retained_samples=160000)

    for sequence in range(16):
        ack = session.accept_frame(frame(sequence, 8000))
        assert ack.frozen_span_ids == ()

    snapshot = session.snapshot()
    assert snapshot.accepted_samples == 128000
    assert snapshot.frozen_until_sample == 0
    assert snapshot.pending_span_ids == ()


def test_frozen_spans_are_independent_and_publish_only_in_order():
    session = LiveSession(max_retained_samples=8000)
    session.accept_frame(frame(0, 2000))
    session.accept_frame(frame(1, 6000))

    first = session.freeze_until(4000, reason="hard_cap")
    second = session.freeze_until(8000, reason="hard_cap")

    assert session.submit_canonical(result(second, transcript(0.25, "second"))) is True
    blocked = session.snapshot()
    assert blocked.accounted_samples == 0
    assert blocked.pending_span_ids == (0, 1)

    assert session.submit_canonical(result(first, transcript(0.25, "first"))) is True
    published = session.snapshot()
    assert published.accounted_samples == 8000
    assert [commit.span_id for commit in published.committed] == [0, 1]
    assert [commit.transcript for commit in published.committed] == [
        "[0][S01]first[0.25]",
        "[0][S01]second[0.25]",
    ]
    assert published.committed[0].prefix_hash != published.committed[1].prefix_hash
    with pytest.raises(ValueError):
        session.freeze_until(8000, reason="duplicate")


def test_provisional_suffix_is_replace_only_and_stale_generations_are_ignored():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    session.freeze_until(4000, reason="hard_cap")
    epoch, old_generation, start_sample = session.begin_provisional()
    assert session.publish_provisional(
        epoch=epoch,
        generation=old_generation,
        start_sample=start_sample,
        end_sample=4000,
        transcript="old",
    )

    epoch, new_generation, start_sample = session.begin_provisional()
    assert not session.publish_provisional(
        epoch=epoch,
        generation=old_generation,
        start_sample=start_sample,
        end_sample=4000,
        transcript="stale",
    )
    assert session.publish_provisional(
        epoch=epoch,
        generation=new_generation,
        start_sample=start_sample,
        end_sample=4000,
        transcript="new",
    )
    assert session.snapshot().provisional.transcript == "new"

    span = session._frozen_spans[0]
    session.submit_canonical(result(span))
    assert session.snapshot().provisional is None


def test_canonical_validation_fails_closed_and_preserves_unresolved_samples():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")

    with pytest.raises(LiveSessionFailed, match="stable session identity"):
        session.submit_canonical(result(span, identity_confirmed=False))

    snapshot = session.snapshot()
    assert snapshot.status == "failed"
    assert snapshot.accepted_samples == 4000
    assert snapshot.accounted_samples == 0
    assert snapshot.pending_span_ids == (span.id,)
    with pytest.raises(LiveSessionClosed):
        session.accept_frame(frame(1, 1))


def test_stale_epoch_results_are_ignored_after_abort():
    session = LiveSession(max_retained_samples=4000, session_epoch=7)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")

    asyncio.run(session.abort("caller cancelled"))

    stale = CanonicalResult(
        span_id=span.id,
        epoch=span.epoch + 1,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=transcript(0.25),
    )
    assert session.submit_canonical(stale) is False
    assert session.snapshot().status == "aborted"
    with pytest.raises(LiveSessionClosed):
        session.accept_frame(frame(1, 1))


def test_stop_flush_requires_exact_accepted_accounted_equality():
    async def scenario():
        session = LiveSession(max_retained_samples=8)
        session.accept_frame(frame(0, 6))
        with pytest.raises(TimeoutError):
            await session.stop(0.001)

        span = session._frozen_spans[0]
        session.submit_canonical(result(span, transcript(6 / LIVE_SAMPLE_RATE)))
        stopped = await session.stop(0.1)
        assert stopped.status == "closed"
        assert stopped.accepted_samples == stopped.accounted_samples == 6
        assert stopped.retained_samples == 0

    asyncio.run(scenario())


def test_replay_after_committed_prefix_prunes_retention_and_keeps_hash_chain():
    session = LiveSession(max_retained_samples=4)
    session.accept_frame(frame(0, 2))
    first_span = session.freeze_until(2, reason="hard_cap")

    session.submit_canonical(result(first_span, transcript(2 / LIVE_SAMPLE_RATE, "first")))
    first_snapshot = session.snapshot()
    assert first_snapshot.accounted_samples == 2
    assert first_snapshot.retained_samples == 0
    assert len(first_snapshot.committed) == 1
    first_hash = first_snapshot.committed_prefix_hash

    session.accept_frame(frame(1, 4))
    second_span = session.freeze_until(4, reason="hard_cap")
    third_span = session.freeze_until(6, reason="hard_cap")
    assert (second_span.id, third_span.id) == (1, 2)
    session.submit_canonical(result(third_span, transcript(2 / LIVE_SAMPLE_RATE, "third")))
    assert session.snapshot().accounted_samples == 2

    session.submit_canonical(result(second_span, transcript(2 / LIVE_SAMPLE_RATE, "second")))
    replayed = session.snapshot()
    assert replayed.accepted_samples == replayed.accounted_samples == 6
    assert replayed.retained_samples == 0
    assert [commit.transcript for commit in replayed.committed] == [
        "[0][S01]first[0.000125]",
        "[0][S01]second[0.000125]",
        "[0][S01]third[0.000125]",
    ]
    assert replayed.committed[0].prefix_hash == first_hash
    assert replayed.committed_prefix_hash != first_hash


def test_canonical_result_mismatch_is_failure_injection_not_partial_commit():
    session = LiveSession(max_retained_samples=4000)
    session.accept_frame(frame(0, 4000))
    span = session.freeze_until(4000, reason="hard_cap")
    bad = CanonicalResult(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample - 1,
        transcript=transcript(0.25),
    )

    with pytest.raises(LiveSessionFailed, match="does not match frozen span"):
        session.submit_canonical(bad)

    failed = session.snapshot()
    assert failed.status == "failed"
    assert failed.accepted_samples == 4000
    assert failed.accounted_samples == 0
    assert failed.pending_span_ids == (span.id,)


# --------------------------------------------------------------------------------------
# The living document: ADR-0002 step 3's user-visible half.
#
# A retrospective sweep re-matches a meeting's retained evidence against the album as it
# stands *now*, so it will conclude that a span published in minute one belongs to a
# speaker the session only understood in minute nine. `revise_labels` is where that
# conclusion reaches the words a reader is looking at -- and where every way it could reach
# them wrongly is refused by name instead.
# --------------------------------------------------------------------------------------


def prepared(
    span,
    base: LiveIdentitySnapshot,
    *,
    text: str,
    canonical_speakers: tuple[str, ...],
    local_speakers: tuple[str, ...],
) -> CanonicalResult:
    preparation = LiveIdentityPreparation(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        base_snapshot_version=base.version,
        proposed_snapshot=LiveIdentitySnapshot(
            version=base.version + 1,
            canonical_speakers=canonical_speakers,
            diagnostics=(("span_id", str(span.id)),),
        ),
        relabeled_transcript=text,
    )
    return CanonicalResult(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript=text,
        identity_preparation=preparation,
        local_speakers=local_speakers,
    )


def publish_prepared(session: LiveSession, samples: int, sequence: int, **kwargs) -> None:
    session.accept_frame(frame(sequence, samples))
    span = session.freeze_until(session.snapshot().accepted_samples, reason="end_silence")
    submission = session.submit_prepared_canonical(
        prepared(span, session.snapshot().identity_snapshot, **kwargs)
    )
    assert submission.submitted is True


def test_a_revision_relabels_published_speech_and_leaves_the_words_and_the_hash_alone():
    """The correction a reader sees, and the two things it must never move.

    `prefix_hash` chains the committed transcripts, so the chain records what was **said**;
    a living document's corrections are a different fact about the same words and are
    published beside them. If the correction edited `transcript` instead, every client that
    verified the chain would see the meeting rewritten under it.
    """
    session = LiveSession(max_retained_samples=8000)
    publish_prepared(
        session,
        4000,
        0,
        text="[0][S01]who said this[0.25]",
        canonical_speakers=("speaker-0001", "speaker-0002"),
        local_speakers=("S01",),
    )
    before = session.snapshot()

    outcome = session.revise_labels(
        (LabelRevision(span_id=0, local_speaker="S01", canonical_speaker="speaker-0002"),)
    )

    after = session.snapshot()
    assert (outcome.version, outcome.revised_spans, outcome.revised_units) == (1, 1, 1)
    assert after.committed[0].revised_transcript == "[0][S02]who said this[0.25]"
    # The words, the committed transcript and the chain are all exactly where they were.
    assert after.committed[0].transcript == before.committed[0].transcript
    assert after.committed[0].prefix_hash == before.committed[0].prefix_hash
    assert after.committed_prefix_hash == before.committed_prefix_hash
    assert after.label_revision_version == 1 and before.label_revision_version == 0
    # A reader polling `since_version` is told to come back for it.
    assert after.version > before.version


def test_a_revision_reaches_a_span_that_published_no_speaker_at_all():
    """The abstained span is the one a sweep has the most to say about.

    J2 publishes an ambiguous span's words under `S00` and drops only the claim, and the
    ledger deliberately retains those units unlabelled. That is worth nothing unless the
    later answer can be addressed to them -- and it cannot be addressed by displayed label,
    because every one of the span's speakers displays the same `S00`.
    """
    session = LiveSession(max_retained_samples=8000)
    publish_prepared(
        session,
        4000,
        0,
        text="[0][S01]first voice[0.25]",
        canonical_speakers=("speaker-0001",),
        local_speakers=("S01",),
    )
    session.accept_frame(frame(1, 4000))
    span = session.freeze_until(8000, reason="end_silence")
    submission = session.submit_unlabeled_canonical(
        span_id=span.id,
        epoch=span.epoch,
        start_sample=span.start_sample,
        end_sample=span.end_sample,
        transcript="[0][S00]ambiguous words[0.1][0.1][S00]and more[0.25]",
        local_speakers=("S01", "S02"),
    )
    assert submission.submitted is True

    outcome = session.revise_labels(
        (LabelRevision(span_id=1, local_speaker="S01", canonical_speaker="speaker-0001"),)
    )

    assert (outcome.revised_spans, outcome.revised_units) == (1, 1)
    # Only the corrected speaker's words gain a name; the other stays honestly unattributed.
    assert session.snapshot().committed[1].revised_transcript == (
        "[0][S01]ambiguous words[0.1][0.1][S00]and more[0.25]"
    )


def test_a_revision_names_every_correction_it_declines_and_never_raises():
    """Four ways a correction cannot land, all counted, none of them terminal.

    A rewriter nobody can audit is worse than no rewriter: every one of these would
    otherwise be a correction that silently evaporated, which is this project's own
    "known but not shown" defect wearing new clothes.
    """
    session = LiveSession(max_retained_samples=8000)
    publish_prepared(
        session,
        4000,
        0,
        text="[0][S01]words[0.25]",
        canonical_speakers=("speaker-0001",),
        local_speakers=("S01",),
    )
    session.accept_frame(frame(1, 4000))
    empty_span = session.freeze_until(8000, reason="end_silence")
    session.submit_empty_canonical(
        span_id=empty_span.id,
        epoch=empty_span.epoch,
        start_sample=empty_span.start_sample,
        end_sample=empty_span.end_sample,
    )
    before = session.snapshot()

    outcome = session.revise_labels(
        (
            LabelRevision(span_id=97, local_speaker="S01", canonical_speaker="speaker-0001"),
            LabelRevision(span_id=1, local_speaker="S01", canonical_speaker="speaker-0001"),
            LabelRevision(span_id=0, local_speaker="S09", canonical_speaker="speaker-0001"),
            LabelRevision(span_id=0, local_speaker="S01", canonical_speaker="speaker-0404"),
        )
    )

    assert dict(outcome.refusals) == {
        "span_not_committed": 1,
        "span_has_no_label_track": 1,
        "local_speaker_not_in_span": 1,
        "canonical_speaker_unknown": 1,
        "label_unchanged": 2,
    }
    assert (outcome.version, outcome.revised_spans, outcome.revised_units) == (0, 0, 0)
    assert session.snapshot() == before


def test_a_revision_that_would_put_two_of_one_spans_speakers_on_one_identity_is_refused():
    """The live matcher's one-to-one rule, kept when the labels are rewritten later.

    A sweep re-matches unit by unit, so nothing in it forbids two units of the same span
    landing on one canonical speaker across different dispositions. Publishing that would
    claim the span's own local diarization was wrong -- a claim a sweep is explicitly not
    allowed to make, because it re-matches evidence and never re-hears audio.
    """
    session = LiveSession(max_retained_samples=8000)
    publish_prepared(
        session,
        4000,
        0,
        text="[0][S01]one[0.1][0.1][S02]two[0.25]",
        canonical_speakers=("speaker-0001", "speaker-0002"),
        local_speakers=("S01", "S02"),
    )

    outcome = session.revise_labels(
        (LabelRevision(span_id=0, local_speaker="S02", canonical_speaker="speaker-0001"),)
    )

    assert dict(outcome.refusals) == {"span_labels_would_collide": 1}
    assert session.snapshot().committed[0].revised_transcript is None


def test_a_span_whose_transcript_does_not_re_render_to_itself_keeps_every_byte():
    """The guard that makes a label rewrite unable to cost a word.

    The revision writes the span's segments back through the same renderer that wrote them,
    so a transcript the parser does not round-trip would come back subtly different -- here
    with its own spacing removed. Proving the round trip per span, rather than assuming the
    grammar is total, is what keeps a mislabelled speaker from being fixed at the price of
    the words attached to it.
    """
    session = LiveSession(max_retained_samples=8000)
    publish_prepared(
        session,
        4000,
        0,
        text="[0][S01]  spaced out  [0.25]",
        canonical_speakers=("speaker-0001", "speaker-0002"),
        local_speakers=("S01",),
    )

    outcome = session.revise_labels(
        (LabelRevision(span_id=0, local_speaker="S01", canonical_speaker="speaker-0002"),)
    )

    assert dict(outcome.refusals) == {"span_does_not_re_render": 1}
    committed = session.snapshot().committed[0]
    assert committed.revised_transcript is None
    assert committed.transcript == "[0][S01]  spaced out  [0.25]"


def test_a_closed_session_is_revisable_and_a_second_revision_builds_on_the_first():
    """The session-end sweep is where ADR-0002 measured essentially all of the accuracy.

    It necessarily arrives after the last span, so a session that stopped accepting
    corrections when it stopped accepting audio would refuse the most valuable one of the
    meeting. Revising twice must also compose: the second correction is applied to the
    labelling the reader has, not to the one the live path published and nobody still sees.
    """
    session = LiveSession(max_retained_samples=8000)
    publish_prepared(
        session,
        4000,
        0,
        text="[0][S01]one[0.1][0.1][S02]two[0.25]",
        canonical_speakers=("speaker-0001", "speaker-0002", "speaker-0003"),
        local_speakers=("S01", "S02"),
    )
    session.revise_labels(
        (LabelRevision(span_id=0, local_speaker="S01", canonical_speaker="speaker-0003"),)
    )
    asyncio.run(session.stop(0.0))
    assert session.snapshot().status == "closed"

    outcome = session.revise_labels(
        (LabelRevision(span_id=0, local_speaker="S02", canonical_speaker="speaker-0001"),)
    )

    assert (outcome.version, outcome.revised_spans, outcome.revised_units) == (2, 1, 1)
    # The first correction is still there: the second was applied to the labelling the reader
    # has, not to the one the live path published and nobody is looking at any more.
    assert session.snapshot().committed[0].revised_transcript == "[0][S03]one[0.1][0.1][S01]two[0.25]"
