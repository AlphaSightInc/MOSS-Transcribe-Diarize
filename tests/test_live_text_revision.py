"""T1 tests for the session's word-revision authority (plan §6 M3, ADR-0005).

One seam, seven validations, four snapshot fields, and the label projection the E2 grid was
measured through. Everything here drives `LiveSession` directly: a producer is only ever
inert data at this boundary, so the whole contract is reachable without a decoder.
"""

from __future__ import annotations

from moss_transcribe_diarize.app.live_session import (
    EffectiveTranscriptSegment,
    LabelRevision,
    LiveSession,
    TextRevisionProposal,
)

from tests.test_live_session import frame, publish_prepared

SPEAKERS = ("speaker-a", "speaker-b")
SECOND = 16000


def session_with_base(*texts: str, local: str = "S01") -> LiveSession:
    """A session whose committed base is one 1-second span per `texts` entry."""

    session = LiveSession(max_retained_samples=64 * SECOND)
    for index, text in enumerate(texts):
        publish_prepared(
            session,
            SECOND,
            index,
            text=text,
            canonical_speakers=SPEAKERS,
            local_speakers=(local,) * max(1, text.count("][S")),
        )
    return session


def segment(start: int, end: int, text: str, speaker: str | None = None) -> EffectiveTranscriptSegment:
    return EffectiveTranscriptSegment(
        start_sample=start, end_sample=end, text=text, canonical_speaker=speaker, authority="rolling"
    )


def proposal(
    session: LiveSession,
    start: int,
    end: int,
    segments: tuple[EffectiveTranscriptSegment, ...],
    *,
    source: str = "rolling",
    epoch: int | None = None,
    base_version: int | None = None,
) -> TextRevisionProposal:
    snapshot = session.snapshot()
    return TextRevisionProposal(
        epoch=snapshot.epoch if epoch is None else epoch,
        base_text_revision_version=(
            snapshot.text_revision_version if base_version is None else base_version
        ),
        source=source,
        start_sample=start,
        end_sample=end,
        segments=segments,
        decode_elapsed_sec=0.25,
    )


def surface(session: LiveSession) -> list[tuple[int, int, str, str | None, str]]:
    return [
        (item.start_sample, item.end_sample, item.text, item.canonical_speaker, item.authority)
        for item in session.snapshot().effective_transcript
    ]


# ------------------------------------------------------------------ what it publishes


def test_a_rolling_revision_publishes_better_words_and_leaves_the_committed_record_alone():
    """D2: the base commits are the preserved original every revision is a diff against."""

    session = session_with_base("[0][S01]alpha bet[1]", "[0][S02]gamma delta[1]")
    before = session.snapshot()

    outcome = session.apply_text_revision(
        proposal(
            session,
            0,
            2 * SECOND,
            (segment(0, SECOND, "alpha beta"), segment(SECOND, 2 * SECOND, "gamma delta")),
        )
    )

    after = session.snapshot()
    assert (outcome.applied, outcome.version, outcome.revised_segments) == (True, 1, 2)
    assert outcome.canonical_through_sample == 2 * SECOND
    assert after.canonical_through_sample == 2 * SECOND
    assert after.text_revision_version == 1
    assert after.committed == before.committed
    assert after.committed_prefix_hash == before.committed_prefix_hash
    assert after.label_revision_version == before.label_revision_version
    assert [item[2] for item in surface(session)] == ["alpha beta", "gamma delta"]
    assert after.version > before.version


def test_the_effective_surface_is_the_revised_prefix_then_the_untouched_base_suffix():
    """Plan §5.1: rolling authority to the frontier, provisional base after it."""

    session = session_with_base(
        "[0][S01]one[1]", "[0][S01]two[1]", "[0][S02]three[1]"
    )

    session.apply_text_revision(
        proposal(session, 0, 2 * SECOND, (segment(0, 2 * SECOND, "one two"),))
    )

    assert surface(session) == [
        (0, 2 * SECOND, "one two", "speaker-a", "rolling"),
        (2 * SECOND, 3 * SECOND, "three", "speaker-b", "provisional"),
    ]


def test_a_base_segment_that_straddles_the_frontier_is_owned_by_the_revision_not_published_twice():
    """D4's whole point: one owner per interval, keyed on where a segment begins."""

    session = session_with_base("[0][S01]held over[1]", "[0][S01]after[1]")
    frontier = SECOND // 2

    session.apply_text_revision(
        proposal(session, 0, frontier, (segment(0, frontier, "held"),))
    )

    assert surface(session) == [
        (0, frontier, "held", "speaker-a", "rolling"),
        (SECOND, 2 * SECOND, "after", "speaker-a", "provisional"),
    ]


def test_the_provisional_suffix_stays_its_own_field_and_is_not_duplicated_into_the_surface():
    session = session_with_base("[0][S01]committed[1]")
    session.accept_frame(frame(1, SECOND))
    epoch, generation, start = session.begin_provisional()
    session.publish_provisional(
        epoch=epoch,
        generation=generation,
        start_sample=start,
        end_sample=2 * SECOND,
        transcript="[0][S01]not yet committed[1]",
    )

    snapshot = session.snapshot()

    assert snapshot.provisional is not None
    assert [item.text for item in snapshot.effective_transcript] == ["committed"]


# ------------------------------------------------------------------ the label projection


def test_a_revision_arrives_unattributed_and_the_session_says_who_spoke():
    """A witness's local `S01` is one decode's bookkeeping; meeting identity lives here."""

    session = session_with_base("[0][S01]mine[1]", "[0][S02]yours[1]")

    session.apply_text_revision(
        proposal(
            session,
            0,
            2 * SECOND,
            (segment(0, SECOND, "mine"), segment(SECOND, 2 * SECOND, "yours")),
        )
    )

    assert [item[3] for item in surface(session)] == ["speaker-a", "speaker-b"]


def test_the_identity_that_owns_the_most_of_a_stretch_wins_it():
    session = session_with_base("[0][S01]a[1]", "[0][S02]b[1]", "[0][S02]c[1]")

    session.apply_text_revision(
        proposal(session, 0, 3 * SECOND, (segment(0, 3 * SECOND, "a b c"),))
    )

    assert surface(session)[0][3] == "speaker-b"


def test_unattributed_base_speech_is_a_real_candidate_and_can_win():
    """`S00` is what the base publishes where identity abstained; suppressing it would invent
    attribution the meeting never had."""

    session = session_with_base("[0][S00]nobody[1]", "[0][S00]still nobody[1]", "[0][S01]me[1]")

    session.apply_text_revision(
        proposal(session, 0, 3 * SECOND, (segment(0, 3 * SECOND, "nobody still nobody me"),))
    )

    assert surface(session)[0][3] is None


def test_a_revision_over_a_silent_gap_takes_the_nearest_committed_speech():
    session = session_with_base("[0][S01]early[0.25]", "[0.75][S02]late[1]")

    session.apply_text_revision(
        proposal(
            session,
            0,
            2 * SECOND,
            (segment(SECOND // 2, SECOND // 2 + 800, "between"),),
        )
    )

    # The gap runs [0.25 s, 1.75 s); its first half is nearer the S01 segment that ends at
    # 0.25 s than the S02 segment that starts at 1.75 s.
    assert surface(session)[0][3] == "speaker-a"


def test_a_producer_that_carries_its_own_speaker_evidence_is_left_alone():
    """The projection is the fallback authority, not the last word (plan D5 is E3's)."""

    session = session_with_base("[0][S01]mine[1]")

    session.apply_text_revision(
        proposal(session, 0, SECOND, (segment(0, SECOND, "mine", speaker="speaker-b"),))
    )

    assert surface(session)[0][3] == "speaker-b"


def test_a_later_label_revision_reprojects_the_rolling_surface():
    """Both dimensions of the living document meet here: the words are the revision's, the
    speaker is whoever the base now says spoke them."""

    session = session_with_base("[0][S00]who said this[1]")
    session.apply_text_revision(
        proposal(session, 0, SECOND, (segment(0, SECOND, "who said this"),))
    )
    assert surface(session)[0][3] is None

    outcome = session.revise_labels(
        [LabelRevision(span_id=0, local_speaker="S01", canonical_speaker="speaker-b")]
    )

    assert outcome.revised_spans == 1
    assert surface(session)[0][3] == "speaker-b"


# ------------------------------------------------------------------ the seven validations


def refused(session: LiveSession, item: TextRevisionProposal) -> str:
    before = session.snapshot()
    outcome = session.apply_text_revision(item)
    after = session.snapshot()
    assert outcome.applied is False
    assert outcome.refusal is not None
    assert after.text_revision_version == before.text_revision_version
    assert after.canonical_through_sample == before.canonical_through_sample
    assert after.effective_transcript == before.effective_transcript
    return outcome.refusal


def test_every_validation_refuses_by_its_own_name_and_changes_nothing():
    session = session_with_base("[0][S01]a[1]", "[0][S01]b[1]")
    whole = (segment(0, 2 * SECOND, "a b"),)

    cases = {
        "stale_epoch": proposal(session, 0, 2 * SECOND, whole, epoch=7),
        "unknown_revision_source": proposal(session, 0, 2 * SECOND, whole, source="sweep"),
        "stale_text_revision_version": proposal(session, 0, 2 * SECOND, whole, base_version=3),
        "not_at_frontier": proposal(session, SECOND, 2 * SECOND, (segment(SECOND, 2 * SECOND, "b"),)),
        "interval_does_not_advance": proposal(session, 0, 0, ()),
        "beyond_committed_audio": proposal(
            session, 0, 3 * SECOND, (segment(0, 3 * SECOND, "a b c"),)
        ),
        "segment_outside_owned_interval": proposal(
            session, 0, SECOND, (segment(0, 2 * SECOND, "a b"),)
        ),
        "segment_does_not_advance": proposal(session, 0, SECOND, (segment(SECOND, SECOND, ""),)),
        "segments_out_of_order": proposal(
            session,
            0,
            2 * SECOND,
            (segment(SECOND, 2 * SECOND, "b"), segment(0, SECOND, "a")),
        ),
    }

    for expected, item in cases.items():
        assert refused(session, item) == expected


def test_segments_that_merely_touch_are_ordered_and_a_one_sample_overlap_is_not():
    session = session_with_base("[0][S01]a[1]", "[0][S01]b[1]")

    touching = session.apply_text_revision(
        proposal(
            session,
            0,
            2 * SECOND,
            (segment(0, SECOND, "a"), segment(SECOND, 2 * SECOND, "b")),
        )
    )

    assert touching.applied is True
    session = session_with_base("[0][S01]a[1]", "[0][S01]b[1]")
    assert (
        refused(
            session,
            proposal(
                session,
                0,
                2 * SECOND,
                (segment(0, SECOND + 1, "a"), segment(SECOND, 2 * SECOND, "b")),
            ),
        )
        == "segments_out_of_order"
    )


def test_refusals_are_counted_by_stable_reason_and_carried_on_every_outcome():
    session = session_with_base("[0][S01]a[1]")
    stale = proposal(session, 0, SECOND, (segment(0, SECOND, "a"),), epoch=9)

    session.apply_text_revision(stale)
    session.apply_text_revision(stale)
    outcome = session.apply_text_revision(
        proposal(session, 0, SECOND, (segment(0, SECOND, "a"),))
    )

    assert outcome.applied is True
    assert outcome.refusals == (("stale_epoch", 2),)


def test_a_second_rolling_revision_extends_the_first_from_the_frontier():
    session = session_with_base("[0][S01]a[1]", "[0][S01]b[1]")

    session.apply_text_revision(proposal(session, 0, SECOND, (segment(0, SECOND, "a"),)))
    second = session.apply_text_revision(
        proposal(session, SECOND, 2 * SECOND, (segment(SECOND, 2 * SECOND, "b"),))
    )

    assert second.applied is True
    assert [item[2] for item in surface(session)] == ["a", "b"]
    assert session.snapshot().text_revision_version == 2


# ------------------------------------------------------------------ terminal finalization


def test_terminal_finalization_replaces_the_whole_surface_once():
    session = session_with_base("[0][S01]a[1]", "[0][S02]b[1]")
    session.apply_text_revision(proposal(session, 0, SECOND, (segment(0, SECOND, "a"),)))
    assert session.snapshot().finalization_status == "not_started"

    outcome = session.apply_text_revision(
        proposal(
            session,
            0,
            2 * SECOND,
            (
                EffectiveTranscriptSegment(0, SECOND, "a", None, "final"),
                EffectiveTranscriptSegment(SECOND, 2 * SECOND, "b", None, "final"),
            ),
            source="terminal",
        )
    )

    assert outcome.applied is True
    assert outcome.finalization_status == "final"
    assert surface(session) == [
        (0, SECOND, "a", "speaker-a", "final"),
        (SECOND, 2 * SECOND, "b", "speaker-b", "final"),
    ]
    assert (
        refused(
            session,
            proposal(
                session,
                0,
                2 * SECOND,
                (EffectiveTranscriptSegment(0, 2 * SECOND, "a b", None, "final"),),
                source="terminal",
            ),
        )
        == "already_finalized"
    )


def test_a_terminal_pass_that_does_not_own_the_whole_surface_is_refused():
    session = session_with_base("[0][S01]a[1]", "[0][S02]b[1]")

    assert (
        refused(
            session,
            proposal(
                session,
                SECOND,
                2 * SECOND,
                (EffectiveTranscriptSegment(SECOND, 2 * SECOND, "b", None, "final"),),
                source="terminal",
            ),
        )
        == "terminal_must_replace_full_surface"
    )
    assert (
        refused(
            session,
            proposal(
                session,
                0,
                SECOND,
                (EffectiveTranscriptSegment(0, SECOND, "a", None, "final"),),
                source="terminal",
            ),
        )
        == "terminal_must_replace_full_surface"
    )


def test_a_closed_session_still_accepts_the_terminal_pass_it_is_waiting_for():
    import asyncio

    session = session_with_base("[0][S01]a[1]")
    asyncio.run(session.stop(1.0))
    assert session.snapshot().status == "closed"

    outcome = session.apply_text_revision(
        proposal(
            session,
            0,
            SECOND,
            (EffectiveTranscriptSegment(0, SECOND, "a better a", None, "final"),),
            source="terminal",
        )
    )

    assert outcome.applied is True
    assert [item[2] for item in surface(session)] == ["a better a"]
