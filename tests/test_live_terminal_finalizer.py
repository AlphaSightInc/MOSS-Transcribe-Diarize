"""Plan E4 steps 4-6 -- the terminal finalizer (test tiers T1/T2).

The meeting is over, the whole of it is on the tape, and the pipeline that decodes a whole
meeting already exists: file mode's 150/120 `WindowedRunner`. Plan §6 M6 asks for a *small
adapter*, so what these tests hold in place is exactly what the adapter is allowed to own,
and nothing the file pipeline or the session already owns:

- where the audio comes from -- one read of `[0, meeting_end)` through the tape seam, and a
  refusal there is `unavailable`, not a crash and not a shorter meeting;
- what clock the words land on -- session samples, clamped inside the meeting;
- who the decoder's local speakers are on this meeting's album -- one-to-one **per speaker**,
  because a terminal pass heard the whole meeting and its labels are a partition of it;
- what is published when any of that fails -- a name, never a word of the meeting.

Publication itself belongs to `LiveSession` (ADR-0005) and is not re-implemented here; the
T2 class drives the real seam to show the adapter's output satisfies all seven validations
and that a second terminal pass is refused `already_finalized`.

The corpus reading -- does this adapter, handed the paired file arm's own decode, publish the
paired file arm's own surface? -- is
`prototypes/streaming-diarization/live-convergence/verify_terminal_finalizer.py`.
"""

from __future__ import annotations

import unittest
import wave

from moss_transcribe_diarize.app.live_session import (
    EffectiveTranscriptSegment,
    LIVE_SAMPLE_RATE,
    PCM16_BYTES_PER_SAMPLE,
    LiveSession,
    TextRevisionProposal,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTape
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    TerminalDecodePlan,
    TerminalOutcome,
    TerminalTranscriptFinalizer,
    resolve_segment_overlaps,
    terminal_speaker_mapping,
)

from tests.test_live_session import publish_prepared
from tests.test_live_text_revision import SPEAKERS, session_with_base

SECOND = LIVE_SAMPLE_RATE
MEETING = 4 * SECOND


class WholeMeetingStub:
    """A `WindowedRunner` stand-in: it answers with one transcript and records what it was given."""

    window_seconds = 150
    stride_seconds = 120

    def __init__(self, text: str = "", *, raises: Exception | None = None, **fields):
        self.text = text
        self.raises = raises
        self.fields = {"generated_tokens": 120, "prompt_len": 340, "window_count": 1,
                       "completed_windows": 1, "possibly_truncated": False, **fields}
        self.calls: list[tuple[bytes, int, int, dict]] = []

    def transcribe(self, audio_path, **kwargs):
        with wave.open(str(audio_path), "rb") as handle:
            pcm = handle.readframes(handle.getnframes())
            rate, channels = handle.getframerate(), handle.getnchannels()
        self.calls.append((pcm, rate, channels, dict(kwargs)))
        if self.raises is not None:
            raise self.raises
        return type("Result", (), {"text": self.text, **self.fields})()


def tape_of(samples: int, *, fill: bytes = b"\x11\x22", capacity: int | None = None) -> CompleteMixedTape:
    tape = CompleteMixedTape(
        epoch=0,
        capacity_bytes=capacity or samples * PCM16_BYTES_PER_SAMPLE,
    )
    tape.append(start_sample=0, pcm=fill * samples)
    return tape


def plan_for(samples: int = MEETING, **kwargs) -> TerminalDecodePlan:
    return TerminalDecodePlan(
        epoch=kwargs.pop("epoch", 0),
        end_sample=samples,
        rolling_through_sample=kwargs.pop("rolling_through_sample", samples),
        rolling_status=kwargs.pop("rolling_status", RollingStatus.STOPPED),
        windows_completed=kwargs.pop("windows_completed", 0),
        windows_failed=kwargs.pop("windows_failed", 0),
    )


def base_segment(start: int, end: int, speaker: str | None) -> EffectiveTranscriptSegment:
    return EffectiveTranscriptSegment(
        start_sample=start, end_sample=end, text="base", canonical_speaker=speaker,
        authority="provisional",
    )


class TerminalFinalizerTest(unittest.TestCase):
    """T1 -- the adapter alone: a tape, a runner stub, and no session."""

    def test_the_whole_meeting_is_decoded_once_and_proposed_as_one_revision(self):
        runner = WholeMeetingStub("[0][S01]alpha[1][1][S02]beta[4]")

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(), tape=tape_of(MEETING), base_text_revision_version=3,
        )

        assert result.outcome is TerminalOutcome.FINALIZED
        proposal = result.proposal
        assert proposal is not None
        assert (proposal.source, proposal.start_sample, proposal.end_sample) == ("terminal", 0, MEETING)
        assert proposal.base_text_revision_version == 3
        assert [(item.start_sample, item.end_sample, item.text) for item in proposal.segments] == [
            (0, SECOND, "alpha"),
            (SECOND, MEETING, "beta"),
        ]
        assert {item.authority for item in proposal.segments} == {"terminal"}
        assert len(runner.calls) == 1

    def test_the_runner_is_handed_the_tape_itself_as_the_meeting_s_own_wav(self):
        """One read of `[0, meeting_end)`, at the live sample rate, in mono. Nothing resampled."""

        runner = WholeMeetingStub("[0][S01]words[4]")
        tape = tape_of(MEETING, fill=b"\x07\x08")

        TerminalTranscriptFinalizer(
            runner=runner, transcribe_kwargs={"decoding": "greedy", "max_new_tokens": 2048},
        ).finalize(plan=plan_for(), tape=tape, base_text_revision_version=0)

        pcm, rate, channels, kwargs = runner.calls[0]
        assert pcm == b"\x07\x08" * MEETING
        assert (rate, channels) == (LIVE_SAMPLE_RATE, 1)
        # File mode's own inference arguments reach the runner unchanged: a terminal pass that
        # decoded with different arguments is not the file arm's comparator.
        assert kwargs == {"decoding": "greedy", "max_new_tokens": 2048}

    def test_a_tape_that_cannot_serve_the_meeting_reports_unavailable_and_names_its_gaps(self):
        tape = tape_of(MEETING)
        tape.append(start_sample=MEETING + SECOND, pcm=b"\x00\x00" * SECOND)  # a hole
        runner = WholeMeetingStub("[0][S01]never decoded[6]")

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(MEETING + 2 * SECOND), tape=tape, base_text_revision_version=0,
        )

        assert result.outcome is TerminalOutcome.TAPE_UNAVAILABLE
        assert result.accounting.outcome.finalization_status == "unavailable"
        assert result.proposal is None
        assert result.accounting.tape_gaps == 1
        assert runner.calls == []

    def test_a_tape_that_is_merely_short_serves_nothing_rather_than_its_prefix(self):
        """The dangerous tape is the healthy one that stopped early, not the broken one.

        A degraded or released tape refuses every read, so any fallback still refuses. A tape
        that simply never received the last frames is intact, and asking it for "whatever you
        have" would hand the pass three seconds of a four-second meeting -- which then
        publishes words over a clock the audio never covered. So the extent is always named.
        """

        tape = tape_of(3 * SECOND, capacity=MEETING * PCM16_BYTES_PER_SAMPLE)
        assert len(tape.read()) == 3 * SECOND * PCM16_BYTES_PER_SAMPLE
        runner = WholeMeetingStub("[0][S01]three seconds of a four second meeting[3]")

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(MEETING), tape=tape, base_text_revision_version=0,
        )

        assert result.outcome is TerminalOutcome.TAPE_UNAVAILABLE
        assert result.accounting.tape_gaps == 1
        assert runner.calls == []

    def test_a_released_tape_is_unavailable_rather_than_a_shorter_meeting(self):
        tape = tape_of(MEETING)
        tape.release()

        result = TerminalTranscriptFinalizer(runner=WholeMeetingStub("[0][S01]x[4]")).finalize(
            plan=plan_for(), tape=tape, base_text_revision_version=0,
        )

        assert result.outcome is TerminalOutcome.TAPE_UNAVAILABLE
        assert result.accounting.tape_samples == 0

    def test_a_runner_that_fails_reports_its_type_and_never_the_words_it_rejected(self):
        runner = WholeMeetingStub(raises=RuntimeError("window 0 failed: [0][S01]secret meeting words[4]"))

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(), tape=tape_of(MEETING), base_text_revision_version=0,
        )

        assert result.outcome is TerminalOutcome.DECODE_FAILED
        assert result.accounting.outcome.finalization_status == "failed"
        assert result.accounting.reason == "RuntimeError"
        assert "secret" not in repr(result.accounting.to_dict())
        assert result.accounting.decode_elapsed_sec is not None

    def test_an_answer_with_no_words_in_it_is_a_failed_pass_not_an_empty_meeting(self):
        """`no_transcript` keeps the rolling surface: erasing it would lose real words."""

        for text in ("", "   ", "not a transcript at all", "[0][S01]   [4]"):
            with self.subTest(text=text):
                result = TerminalTranscriptFinalizer(runner=WholeMeetingStub(text)).finalize(
                    plan=plan_for(), tape=tape_of(MEETING), base_text_revision_version=0,
                )
                assert result.outcome is TerminalOutcome.NO_TRANSCRIPT
                assert result.accounting.outcome.finalization_status == "failed"
                assert result.proposal is None

    def test_a_timestamp_past_the_end_of_the_meeting_is_clamped_into_it(self):
        """The decoder marks the end of what it heard; the session owns what the meeting was."""

        runner = WholeMeetingStub("[0][S01]inside[3][3][S01]over the end[9]")

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(), tape=tape_of(MEETING), base_text_revision_version=0,
        )

        assert [item.end_sample for item in result.proposal.segments] == [3 * SECOND, MEETING]

    def test_the_accounting_reports_the_windowing_the_pass_actually_ran(self):
        runner = WholeMeetingStub("[0][S01]x[4]", window_count=3, completed_windows=3)

        accounting = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(), tape=tape_of(MEETING), base_text_revision_version=0,
        ).accounting

        assert (accounting.window_seconds, accounting.stride_seconds) == (150.0, 120.0)
        assert (accounting.window_count, accounting.completed_windows) == (3, 3)
        assert accounting.decoded_audio_samples == MEETING
        assert accounting.tape_samples == MEETING
        assert accounting.rolling_status == "stopped"


class TerminalSpeakerMappingTest(unittest.TestCase):
    """T1 -- plan §12.3 step 5: the terminal partition is preserved, only its names decided."""

    def test_a_speaker_whose_segments_straddle_base_turns_stays_one_speaker(self):
        """The case a per-segment projection gets wrong, and the reason this rule is per speaker.

        `S01` speaks twice; between them the base surface says the other person spoke, and its
        second turn overlaps that other person more than its own. Voting segment by segment
        would split one terminal speaker across two people and destroy the diarization the
        terminal pass just produced.
        """

        placed = [
            ("S01", 0, SECOND, "one"),
            ("S02", SECOND, 2 * SECOND, "two"),
            ("S01", 2 * SECOND, 3 * SECOND, "three"),
        ]
        base = (
            base_segment(0, SECOND, "speaker-a"),
            base_segment(SECOND, 2 * SECOND, "speaker-b"),
            base_segment(2 * SECOND, 3 * SECOND, "speaker-b"),
        )

        mapping = terminal_speaker_mapping(placed, base_surface=base, canonical_speakers=SPEAKERS)

        assert mapping == {"S01": "speaker-a", "S02": "speaker-b"}
        assert len(set(mapping.values())) == len(mapping)

    def test_a_local_speaker_the_meeting_never_established_publishes_unattributed(self):
        """No overlap is no evidence, and no evidence may not become a name."""

        placed = [("S01", 0, SECOND, "one"), ("S02", 3 * SECOND, MEETING, "two")]
        base = (base_segment(0, SECOND, "speaker-a"),)

        mapping = terminal_speaker_mapping(placed, base_surface=base, canonical_speakers=SPEAKERS)

        assert mapping == {"S01": "speaker-a"}

    def test_more_terminal_speakers_than_the_album_holds_leaves_the_extra_ones_unnamed(self):
        placed = [
            ("S01", 0, SECOND, "one"),
            ("S02", SECOND, 2 * SECOND, "two"),
            ("S03", 2 * SECOND, 3 * SECOND, "three"),
        ]
        base = (
            base_segment(0, SECOND, "speaker-a"),
            base_segment(SECOND, 3 * SECOND, "speaker-b"),
        )

        mapping = terminal_speaker_mapping(placed, base_surface=base, canonical_speakers=SPEAKERS)

        assert set(mapping) <= {"S01", "S02", "S03"}
        assert len(set(mapping.values())) == len(mapping) <= len(SPEAKERS)
        assert mapping["S01"] == "speaker-a"

    def test_a_meeting_with_no_established_identity_publishes_every_word_unattributed(self):
        placed = [("S01", 0, SECOND, "one")]

        assert terminal_speaker_mapping(placed, base_surface=(), canonical_speakers=SPEAKERS) == {}
        assert terminal_speaker_mapping(
            placed, base_surface=(base_segment(0, SECOND, "speaker-a"),), canonical_speakers=()
        ) == {}

    def test_the_finalizer_attributes_its_segments_through_that_mapping(self):
        runner = WholeMeetingStub("[0][S01]one[1][1][S02]two[2][2][S01]three[4]")
        base = (
            base_segment(0, SECOND, "speaker-a"),
            base_segment(SECOND, 2 * SECOND, "speaker-b"),
            base_segment(2 * SECOND, MEETING, "speaker-a"),
        )

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(), tape=tape_of(MEETING), base_text_revision_version=0,
            base_surface=base, canonical_speakers=SPEAKERS,
        )

        assert [item.canonical_speaker for item in result.proposal.segments] == [
            "speaker-a", "speaker-b", "speaker-a",
        ]
        assert (result.accounting.local_speakers, result.accounting.mapped_speakers) == (2, 2)
        assert result.accounting.unattributed_segments == 0


#: The seam the campaign corpus actually produced, in session samples: file mode's windows
#: `[0,150)` and `[120,180)` each kept a segment whose midpoint they owned, and the two
#: overlap by 2.34 s (`lex_adam_frank`, both runs, both file arms of
#: `evidence/live-convergence-0824/M4-e4-exit/`).
MEETING_SEAM = (
    ("S01", 2099040, 2180640, "when two stars passed by each other closely"),
    ("S01", 2143200, 2185920, "and then material was gravitationally squeezed out."),
)

#: Every overlap shape a two-window seam can produce, not only the one the corpus holds.
#: Boundaries are small integers because the rule is arithmetic on a sample clock, and these
#: are the shapes the selection harness was made total on
#: (`prototypes/streaming-diarization/live-convergence/measure_seam_overlap.py`).
SEAM_SHAPES = {
    "disjoint": (("A", 0, 100, "one"), ("A", 100, 200, "two")),
    "touching": (("A", 0, 100, "one"), ("A", 100, 200, "two"), ("A", 200, 300, "three")),
    "pair_same_speaker": (("A", 0, 160, "one"), ("A", 120, 200, "two")),
    "pair_cross_speaker": (("A", 0, 160, "one"), ("B", 120, 200, "two")),
    "contained": (("A", 0, 200, "one"), ("A", 50, 100, "two")),
    "contained_cross_speaker": (("A", 0, 200, "one"), ("B", 50, 100, "two")),
    "identical": (("A", 0, 100, "one"), ("A", 0, 100, "two")),
    "chain_of_three": (("A", 0, 150, "one"), ("A", 100, 250, "two"), ("A", 200, 300, "three")),
    "chain_mixed_speakers": (("A", 0, 150, "one"), ("B", 100, 250, "two"), ("A", 200, 300, "three")),
    "later_ends_earlier": (("A", 0, 200, "one"), ("A", 100, 150, "two"), ("A", 220, 300, "three")),
    "unsorted_input": (("A", 200, 300, "three"), ("A", 0, 100, "one"), ("A", 100, 200, "two")),
    "single": (("A", 0, 100, "one"),),
}


class SegmentOverlapResolutionTest(unittest.TestCase):
    """T1 -- the seam rule alone (`evidence/live-convergence-0824/M4-seam-overlap/`).

    File mode stitches its 150/120 windows by midpoint ownership, so two segments straddling
    the 30-second overlap can both survive and publish one stretch of audio twice. A file
    transcript may say that; a live surface may not (ADR-0005 D4, one owner per interval), and
    the whole proposal is refused `segments_out_of_order` if it does. These tests hold the
    resolution that was selected by measurement -- merge one speaker's overlapping decodings
    over the union of their extents -- and, more importantly, the two properties that make it
    admissible rather than merely different: no boundary is invented, and no word is lost.
    """

    def test_a_proposal_with_no_overlap_is_returned_unchanged(self):
        """The common case, and the one a rule like this most easily damages."""

        for name in ("disjoint", "touching", "single"):
            with self.subTest(shape=name):
                resolution = resolve_segment_overlaps(SEAM_SHAPES[name])
                assert resolution.segments == SEAM_SHAPES[name]
                assert (resolution.merged, resolution.dropped) == (0, 0)
                assert resolution.displaced_samples == 0

    def test_every_shape_a_window_seam_can_produce_becomes_a_publishable_surface(self):
        """Totality: sorted, advancing, disjoint, and inside the boundaries it was given.

        The last clause is plan §3.4 as a property -- the campaign never invents a timestamp,
        so every boundary emitted must be one the decoder itself produced.
        """

        for name, shape in SEAM_SHAPES.items():
            with self.subTest(shape=name):
                resolution = resolve_segment_overlaps(shape)
                boundaries = {item[1] for item in shape} | {item[2] for item in shape}
                frontier = min(item[1] for item in shape)
                for _speaker, start, end, _text in resolution.segments:
                    assert start >= frontier and end > start
                    assert {start, end} <= boundaries
                    frontier = end
                assert frontier <= max(item[2] for item in shape)
                words_in = sum(len(item[3].split()) for item in shape)
                words_out = sum(len(item[3].split()) for item in resolution.segments)
                assert words_out <= words_in
                if len({item[0] for item in shape}) == 1:
                    # One speaker never loses a word to this rule: two decodings of one
                    # stretch are joined, never traded against each other.
                    assert (resolution.dropped, words_out) == (0, words_in)

    def test_one_speakers_two_decodings_of_one_stretch_become_one_segment_over_their_union(self):
        """The corpus's own seam, sample for sample."""

        resolution = resolve_segment_overlaps(MEETING_SEAM)

        assert resolution.segments == (
            (
                "S01",
                2099040,
                2185920,
                "when two stars passed by each other closely"
                " and then material was gravitationally squeezed out.",
            ),
        )
        assert (resolution.merged, resolution.dropped) == (1, 0)
        # Nothing was trimmed: the union covers exactly the audio the two decodings covered.
        assert resolution.displaced_samples == 0

    def test_two_speakers_over_one_interval_leave_the_later_one_the_audio_that_is_left(self):
        """One interval, one owner. The later speaker keeps its words over what remains."""

        resolution = resolve_segment_overlaps(SEAM_SHAPES["pair_cross_speaker"])

        assert resolution.segments == (("A", 0, 160, "one"), ("B", 160, 200, "two"))
        assert (resolution.merged, resolution.dropped) == (0, 0)
        assert resolution.displaced_samples == 40

    def test_a_second_speaker_with_no_interval_left_is_dropped_rather_than_given_one(self):
        """The one case that loses words -- and the alternative is inventing a boundary."""

        resolution = resolve_segment_overlaps(SEAM_SHAPES["contained_cross_speaker"])

        assert resolution.segments == (("A", 0, 200, "one"),)
        assert (resolution.merged, resolution.dropped) == (0, 1)

    def test_the_order_the_decoder_emitted_its_segments_in_does_not_change_the_result(self):
        shape = SEAM_SHAPES["unsorted_input"]

        assert resolve_segment_overlaps(shape).segments == tuple(
            sorted(shape, key=lambda item: item[1])
        )


class TerminalSeamAndSpeakerNamesTest(unittest.TestCase):
    """T1 -- the seam is resolved *before* the names are decided, and that matters.

    `terminal_speaker_mapping` weighs a local speaker against a canonical one by how many
    samples of the base surface they share, summed over segments. A stretch of audio decoded
    twice is therefore weighed twice, and the mapping is a one-to-one assignment: an inflated
    weight does not merely exaggerate a name, it can take a name away from the speaker whose
    audio actually earned it.
    """

    def test_a_stretch_decoded_twice_does_not_get_to_vote_twice_for_a_name(self):
        base = (
            base_segment(0, 100, "speaker-a"),
            base_segment(100, 200, "speaker-b"),
            base_segment(200, 300, "speaker-a"),
        )
        # `A` genuinely owns 100 samples of speaker-a and 45 of speaker-b; `B` owns 100 of
        # speaker-a and 50 of speaker-b. Counting `A`'s overlapping pair twice makes its
        # speaker-b evidence 80 instead of 45 -- enough to win the name off `B`.
        placed = [
            ("A", 0, 100, "a1"), ("A", 100, 140, "a2"), ("A", 105, 145, "a3"),
            ("B", 150, 200, "b1"), ("B", 200, 300, "b2"),
        ]

        as_decoded = terminal_speaker_mapping(placed, base_surface=base, canonical_speakers=SPEAKERS)
        resolved = terminal_speaker_mapping(
            resolve_segment_overlaps(placed).segments,
            base_surface=base, canonical_speakers=SPEAKERS,
        )

        assert as_decoded == {"A": "speaker-b", "B": "speaker-a"}
        assert resolved == {"A": "speaker-a", "B": "speaker-b"}

    def test_the_finalizer_resolves_the_seam_before_it_asks_who_spoke(self):
        """The order is the rule: the same shape, through the adapter that ships.

        `S01` is decoded twice over one stretch of `speaker-b`'s audio. Counted twice, that
        stretch is worth more than `S02`'s genuine 0.5 s there, and the one-to-one assignment
        hands `S01` the name `speaker-b` -- taking it from the speaker whose audio earned it
        and pushing `S02` onto `speaker-a`. Resolving the seam first is what prevents it.
        """

        runner = WholeMeetingStub(
            "[0][S01]a one[1][1][S01]a two[1.4][1.05][S01]a three[1.45]"
            "[1.5][S02]b one[2][2][S02]b two[3]"
        )
        base = (
            base_segment(0, SECOND, "speaker-a"),
            base_segment(SECOND, 2 * SECOND, "speaker-b"),
            base_segment(2 * SECOND, 3 * SECOND, "speaker-a"),
        )

        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(3 * SECOND), tape=tape_of(3 * SECOND), base_text_revision_version=0,
            base_surface=base, canonical_speakers=SPEAKERS,
        )

        assert [item.canonical_speaker for item in result.proposal.segments] == [
            "speaker-a", "speaker-a", "speaker-b", "speaker-b",
        ]
        assert result.accounting.seam_merged_segments == 1

    def test_the_corpus_seam_does_not_move_a_single_name(self):
        """Checked rather than assumed: on the meeting that has the seam, nothing moves."""

        base = (
            base_segment(2_000_000, 2_150_000, "speaker-a"),
            base_segment(2_150_000, 2_200_000, "speaker-b"),
        )
        placed = list(MEETING_SEAM) + [("S02", 2_190_000, 2_200_000, "so one of the things")]

        assert terminal_speaker_mapping(
            resolve_segment_overlaps(placed).segments,
            base_surface=base, canonical_speakers=SPEAKERS,
        ) == terminal_speaker_mapping(placed, base_surface=base, canonical_speakers=SPEAKERS)


class TerminalFinalizerSessionTest(unittest.TestCase):
    """T2 -- the adapter's output against the real publication seam (ADR-0005)."""

    def test_the_proposal_replaces_the_whole_surface_and_a_second_one_is_refused(self):
        session = session_with_base("[0][S01]alpha bet[1]", "[0][S01]gamma delt[1]")
        snapshot = session.snapshot()
        runner = WholeMeetingStub("[0][S01]alpha beta[1][1][S01]gamma delta[2]")
        finalizer = TerminalTranscriptFinalizer(runner=runner)

        result = finalizer.finalize(
            plan=plan_for(2 * SECOND),
            tape=tape_of(2 * SECOND),
            base_text_revision_version=snapshot.text_revision_version,
            base_surface=snapshot.effective_transcript,
            canonical_speakers=snapshot.identity_snapshot.canonical_speakers,
        )
        outcome = session.apply_text_revision(result.proposal)

        after = session.snapshot()
        assert (outcome.applied, outcome.finalization_status) == (True, "final")
        assert [item.text for item in after.effective_transcript] == ["alpha beta", "gamma delta"]
        assert {item.authority for item in after.effective_transcript} == {"terminal"}
        assert after.canonical_through_sample == 2 * SECOND
        # D2: what the short path published is still exactly what it published.
        assert after.committed == snapshot.committed
        assert after.committed_prefix_hash == snapshot.committed_prefix_hash

        second = finalizer.finalize(
            plan=plan_for(2 * SECOND),
            tape=tape_of(2 * SECOND),
            base_text_revision_version=after.text_revision_version,
            base_surface=after.effective_transcript,
            canonical_speakers=after.identity_snapshot.canonical_speakers,
        )
        refused = session.apply_text_revision(second.proposal)

        assert (refused.applied, refused.refusal) == (False, "already_finalized")
        assert session.snapshot().effective_transcript == after.effective_transcript

    def test_a_terminal_pass_over_a_rolling_prefix_replaces_it_from_sample_zero(self):
        """Terminal is exempt from the frontier rule because it owns all of the audio."""

        session = session_with_base("[0][S01]one[1]", "[0][S01]two[1]", "[0][S01]three[1]")
        snapshot = session.snapshot()
        from tests.test_live_text_revision import proposal, segment

        session.apply_text_revision(
            proposal(session, 0, SECOND, (segment(0, SECOND, "ONE"),))
        )
        rolled = session.snapshot()
        assert rolled.canonical_through_sample == SECOND

        result = TerminalTranscriptFinalizer(
            runner=WholeMeetingStub("[0][S01]one two three[3]")
        ).finalize(
            plan=plan_for(3 * SECOND, rolling_status=RollingStatus.PROPOSAL_REFUSED),
            tape=tape_of(3 * SECOND),
            base_text_revision_version=rolled.text_revision_version,
            base_surface=rolled.effective_transcript,
            canonical_speakers=rolled.identity_snapshot.canonical_speakers,
        )
        outcome = session.apply_text_revision(result.proposal)

        final = session.snapshot()
        assert outcome.applied is True
        assert [item.text for item in final.effective_transcript] == ["one two three"]
        assert final.canonical_through_sample == 3 * SECOND
        assert final.finalization_status == "final"
        assert snapshot.finalization_status == "not_started"

    def test_the_corpus_two_window_seam_is_refused_as_decoded_and_published_once_resolved(self):
        """The defect this rule exists for, end to end on the numbers that produced it.

        `lex_adam_frank` is the only meeting in the campaign corpus long enough for file mode
        to plan two windows, and its terminal pass reproduced the file arm exactly -- including
        two segments that overlap by 2.34 s at the window seam. The session refused the whole
        proposal, so the meeting finalized `failed` and kept its rolling surface. Same decode,
        same session: refused as the decoder emitted it, published once the seam is resolved.
        """

        meeting = 137 * SECOND
        session = LiveSession(max_retained_samples=meeting)
        for index in range(4):
            publish_prepared(
                session, meeting // 4, index,
                text=f"[0][S01]span {index}[1]",
                canonical_speakers=SPEAKERS, local_speakers=("S01",),
            )
        snapshot = session.snapshot()
        committed = snapshot.committed_samples

        as_decoded = TextRevisionProposal(
            epoch=session.epoch,
            base_text_revision_version=snapshot.text_revision_version,
            source="terminal",
            start_sample=0,
            end_sample=committed,
            segments=tuple(
                EffectiveTranscriptSegment(
                    start_sample=start, end_sample=end, text=text,
                    canonical_speaker=None, authority="terminal",
                )
                for _speaker, start, end, text in MEETING_SEAM
            ),
            decode_elapsed_sec=1.0,
        )
        refused = session.apply_text_revision(as_decoded)

        assert (refused.applied, refused.refusal) == (False, "segments_out_of_order")

        runner = WholeMeetingStub(
            "[131.19][S01]when two stars passed by each other closely[136.29]"
            "[133.95][S01]and then material was gravitationally squeezed out.[136.62]"
        )
        result = TerminalTranscriptFinalizer(runner=runner).finalize(
            plan=plan_for(committed),
            tape=tape_of(committed),
            base_text_revision_version=snapshot.text_revision_version,
            base_surface=snapshot.effective_transcript,
            canonical_speakers=snapshot.identity_snapshot.canonical_speakers,
        )
        outcome = session.apply_text_revision(result.proposal)

        after = session.snapshot()
        assert (outcome.applied, outcome.finalization_status) == (True, "final")
        assert [(item.start_sample, item.end_sample) for item in after.effective_transcript] == [
            (2099040, 2185920)
        ]
        # Every word of both decodings, in the order they were decoded.
        assert after.effective_transcript[0].text == (
            "when two stars passed by each other closely"
            " and then material was gravitationally squeezed out."
        )
        # The pass says what it did to the surface before it published it.
        accounting = result.accounting
        assert (accounting.seam_merged_segments, accounting.seam_dropped_segments) == (1, 0)
        assert accounting.seam_displaced_samples == 0
        assert accounting.segments == 1

    def test_a_failed_terminal_pass_leaves_the_rolling_surface_exactly_where_it_was(self):
        session = session_with_base("[0][S01]one[1]", "[0][S01]two[1]")
        before = session.snapshot()

        result = TerminalTranscriptFinalizer(
            runner=WholeMeetingStub(raises=RuntimeError("boom"))
        ).finalize(
            plan=plan_for(2 * SECOND), tape=tape_of(2 * SECOND),
            base_text_revision_version=before.text_revision_version,
        )

        assert result.proposal is None
        after = session.snapshot()
        assert after.effective_transcript == before.effective_transcript
        assert after.finalization_status == "not_started"
        assert after.text_revision_version == before.text_revision_version


if __name__ == "__main__":
    unittest.main()


def test_silent_tail_reaches_window_decoder_and_retains_speechless_condition(tmp_path):
    """Deterministic silence probe; it does not assert what a real model will emit."""
    from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner
    from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError, EmptyTranscriptCause
    from moss_transcribe_diarize.phase2_acceptance_external import _diagnostic_event
    from tests.test_windowed_transcription import result
    # Received audio, not padding: 150 seconds nonzero followed by 450 seconds silence.
    tape = CompleteMixedTape(epoch=0, capacity_bytes=600 * SECOND * 2)
    tape.append(start_sample=0, pcm=b"\x01\x00" * (150 * SECOND))
    tape.append(start_sample=150 * SECOND, pcm=b"\0\0" * (450 * SECOND))
    assert tape.read(start_sample=240 * SECOND, end_sample=390 * SECOND) == b"\0\0" * (150 * SECOND)
    calls = []
    class Decoder:
        model_path = "silence-probe"
        def transcribe(self, path, **kwargs):
            with wave.open(str(path)) as handle:
                pcm = handle.readframes(handle.getnframes())
            calls.append((len(pcm) // 2, any(pcm)))
            if not any(pcm):
                raise EmptyTranscriptionError("PRIVATE", cause=EmptyTranscriptCause.NO_GENERATED_TOKENS)
            return result("[0][S01]speech[1]")
    def extract(source, destination, *, start_seconds, duration_seconds):
        with wave.open(str(source)) as src:
            src.setpos(int(start_seconds * SECOND))
            pcm = src.readframes(int(duration_seconds * SECOND))
        with wave.open(str(destination), "wb") as dst:
            dst.setnchannels(1); dst.setsampwidth(2); dst.setframerate(SECOND); dst.writeframes(pcm)
    runner = WindowedRunner(Decoder(), duration_probe=lambda p: 600, window_extractor=extract)
    final = TerminalTranscriptFinalizer(runner=runner).finalize(
        plan=plan_for(600 * SECOND), tape=tape, base_text_revision_version=0,
    )
    assert calls == [(150 * SECOND, True), (150 * SECOND, True),
                     (150 * SECOND, False), (150 * SECOND, False), (120 * SECOND, False)]
    payload = final.accounting.to_dict()
    assert payload["outcome"] == "finalized"
    assert payload["finalization_status"] == "running"  # Proposal; publication is checked separately.
    assert payload["window_failure"] is None
    assert [d["window_index"] for d in payload["window_diagnostics"]] == [2, 3, 4]
    payload["window_diagnostics"][0]["text"] = "PRIVATE"
    retained = _diagnostic_event({"kind": "terminal_finalization_completed", "payload": payload})
    assert "PRIVATE" not in str(retained)
    assert retained["window_diagnostics"][0]["condition"] == "speechless_window_empty"
