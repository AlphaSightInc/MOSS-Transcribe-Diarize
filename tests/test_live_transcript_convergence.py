"""The rolling transcript converger's interface (plan §6 M2, §10.5 step 1; ADR-0005).

These are T1 tests: they exercise the same four methods a caller uses, with a scripted decode
adapter instead of MOSS, and they never reach inside the module. The one thing they cannot
show is whether the arm is any good -- that was measured, not asserted, by the plan §10.2
grid, and `prototypes/streaming-diarization/live-convergence/verify_production_converger.py`
replays this module against that grid's own decode cache to prove the shipped code reproduces
the selected column (trio WER `.131861`, content recall `.9439`) to every printed digit.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    CanonicalResult,
    EffectiveTranscriptSegment,
    LiveSession,
)
from moss_transcribe_diarize.app.live_transcript_convergence import (
    DEFAULT_ROLLING_GEOMETRY,
    RollingGeometry,
    RollingStatus,
    RollingTranscriptConverger,
    TerminalDecodePlan,
    TerminalOutcome,
    TerminalTranscriptFinalizer,
    UnmeasuredRollingGeometry,
)
from moss_transcribe_diarize.app.live_tape import CompleteMixedTapeUnavailable

SAMPLE_RATE = 16000
WINDOW = DEFAULT_ROLLING_GEOMETRY.window_samples


@dataclass(frozen=True, slots=True)
class Surface:
    """A base snapshot, reduced to the four fields the converger reads (plan §7.3)."""

    epoch: int = 0
    committed_samples: int = 0
    canonical_through_sample: int = 0
    text_revision_version: int = 0


def silence(samples: int) -> bytes:
    return b"\x00\x00" * samples


def window_transcript(*turns: tuple[float, str, float, str]) -> str:
    return "".join(f"[{start:g}][{speaker}]{text}[{end:g}]" for start, speaker, text, end in turns)


def decoded(transcript: str, *, elapsed: float | None = 1.2) -> InferenceTranscript:
    return InferenceTranscript(transcript=transcript, elapsed_sec=elapsed)


def feed(converger: RollingTranscriptConverger, samples: int) -> None:
    """Hand over `samples` of audio the way a session does -- in frames, in order."""

    frame = SAMPLE_RATE // 2
    remaining = samples
    while remaining > 0:
        size = min(frame, remaining)
        converger.accept_pcm(converger.accounting().accepted_samples, silence(size))
        remaining -= size


class _TimingTape:
    has_signal = True

    def __init__(self, *, delay: float = 0.0, failure: Exception | None = None):
        self.delay = delay
        self.failure = failure

    def gaps(self, through_sample: int) -> tuple[object, ...]:
        del through_sample
        return ()

    def write_wav(self, destination: str | Path, *, start_sample: int, end_sample: int) -> int:
        del start_sample
        time.sleep(self.delay)
        if self.failure is not None:
            raise self.failure
        Path(destination).write_bytes(b"timing fixture")
        return end_sample


class _TimingRunner:
    def __init__(self, text: str, *, delay: float = 0.0, failure: Exception | None = None):
        self.text = text
        self.delay = delay
        self.failure = failure

    def transcribe(self, audio_path: Path):
        del audio_path
        time.sleep(self.delay)
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(text=self.text)


def _terminal_plan() -> TerminalDecodePlan:
    return TerminalDecodePlan(
        epoch=0,
        end_sample=SAMPLE_RATE,
        rolling_through_sample=0,
        rolling_status=RollingStatus.STOPPED,
        windows_completed=0,
        windows_failed=0,
    )


def test_terminal_stage_clocks_leave_unreached_stages_null(tmp_path):
    preparation_failure = TerminalTranscriptFinalizer(
        runner=_TimingRunner("never"), scratch_dir=tmp_path
    ).finalize(
        plan=_terminal_plan(),
        tape=_TimingTape(failure=CompleteMixedTapeUnavailable("injected preparation failure")),
        base_text_revision_version=0,
    ).accounting
    assert preparation_failure.preparation_elapsed_sec is not None
    assert preparation_failure.decode_elapsed_sec is None
    assert preparation_failure.other_finalize_elapsed_sec is None
    assert preparation_failure.total_elapsed_sec is not None
    assert preparation_failure.to_dict()["decode_elapsed_sec"] is None
    assert preparation_failure.to_dict()["other_finalize_elapsed_sec"] is None

    decode_failure = TerminalTranscriptFinalizer(
        runner=_TimingRunner("never", failure=RuntimeError("injected decode failure")),
        scratch_dir=tmp_path,
    ).finalize(
        plan=_terminal_plan(), tape=_TimingTape(), base_text_revision_version=0
    ).accounting
    assert decode_failure.preparation_elapsed_sec is not None
    assert decode_failure.decode_elapsed_sec is not None
    assert decode_failure.other_finalize_elapsed_sec is None
    assert decode_failure.total_elapsed_sec is not None
    assert decode_failure.to_dict()["other_finalize_elapsed_sec"] is None

    empty = TerminalTranscriptFinalizer(
        runner=_TimingRunner(""), scratch_dir=tmp_path
    ).finalize(
        plan=_terminal_plan(), tape=_TimingTape(), base_text_revision_version=0
    ).accounting
    assert empty.outcome is TerminalOutcome.NO_TRANSCRIPT
    assert empty.preparation_elapsed_sec is not None
    assert empty.decode_elapsed_sec is not None
    assert empty.other_finalize_elapsed_sec is not None
    assert empty.total_elapsed_sec is not None


def test_terminal_stage_clocks_partition_total_without_relabeling_decode(tmp_path):
    accounting = TerminalTranscriptFinalizer(
        runner=_TimingRunner("[0][S01]words[1]", delay=0.03),
        scratch_dir=tmp_path,
    ).finalize(
        plan=_terminal_plan(),
        tape=_TimingTape(delay=0.02),
        base_text_revision_version=0,
    ).accounting

    assert accounting.preparation_elapsed_sec >= 0.015
    assert accounting.decode_elapsed_sec >= 0.025
    assert accounting.other_finalize_elapsed_sec is not None
    assert accounting.total_elapsed_sec is not None
    assert accounting.total_elapsed_sec == pytest.approx(
        accounting.preparation_elapsed_sec
        + accounting.decode_elapsed_sec
        + accounting.other_finalize_elapsed_sec,
        abs=1e-6,
    )


TURNS = (
    (0.0, "S01", "So the thing about compounding is that it is slow at first.", 5.0),
    (5.0, "S02", "And then it is not slow at all.", 9.5),
)


# ---------------------------------------------------------------- geometry


def test_the_default_geometry_is_the_arm_the_selection_grid_chose():
    assert DEFAULT_ROLLING_GEOMETRY.window_samples == 10 * SAMPLE_RATE
    assert DEFAULT_ROLLING_GEOMETRY.stride_samples == 10 * SAMPLE_RATE
    assert DEFAULT_ROLLING_GEOMETRY.max_retained_samples == 20 * SAMPLE_RATE


def test_an_overlapping_geometry_is_refused_because_no_stitcher_was_measured():
    with pytest.raises(UnmeasuredRollingGeometry):
        RollingGeometry(window_samples=10 * SAMPLE_RATE, stride_samples=5 * SAMPLE_RATE)


def test_a_nonsense_geometry_is_refused():
    with pytest.raises(UnmeasuredRollingGeometry):
        RollingGeometry(window_samples=0, stride_samples=0)


# ---------------------------------------------------------------- planning


def test_no_window_is_planned_before_the_base_has_committed_a_whole_one():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, WINDOW)
    assert converger.observe_base(Surface(committed_samples=WINDOW - 1)) == ()
    assert converger.accounting().windows_planned == 0


def test_a_committed_window_is_planned_once_with_its_own_audio():
    converger = RollingTranscriptConverger(epoch=7)
    feed(converger, WINDOW)
    requests = converger.observe_base(Surface(epoch=7, committed_samples=WINDOW))
    assert len(requests) == 1
    request = requests[0]
    assert (request.start_sample, request.end_sample) == (0, WINDOW)
    assert len(request.pcm) == WINDOW * 2
    assert request.token_cap == 938
    assert request.coalesce_key == "rolling:7"
    assert converger.observe_base(Surface(epoch=7, committed_samples=WINDOW)) == ()


def test_only_one_witness_is_in_flight_per_session():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    assert len(converger.observe_base(Surface(committed_samples=2 * WINDOW))) == 1
    assert converger.observe_base(Surface(committed_samples=2 * WINDOW)) == ()
    assert converger.accounting().windows_planned == 1


def test_the_next_window_waits_for_the_session_to_accept_the_previous_revision():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    request = converger.observe_base(Surface(committed_samples=2 * WINDOW))[0]
    assert converger.complete(request.id, decoded(window_transcript(*TURNS))) is not None

    # The session has not applied it yet: the frontier is still 0, so window 1 would not start
    # at the frontier and is not asked for.
    assert converger.observe_base(Surface(committed_samples=2 * WINDOW)) == ()
    following = converger.observe_base(
        Surface(committed_samples=2 * WINDOW, canonical_through_sample=WINDOW)
    )
    assert len(following) == 1
    assert (following[0].start_sample, following[0].end_sample) == (WINDOW, 2 * WINDOW)


def test_accepted_windows_tile_the_owned_prefix_without_overlap_or_gap():
    """D4's whole mechanism, checked as a partition rather than inferred from a metric."""

    converger = RollingTranscriptConverger(epoch=0)
    frontier = 0
    intervals: list[tuple[int, int]] = []
    for _ in range(6):
        feed(converger, WINDOW)  # audio and base commits arrive together, as in a session
        committed = converger.accounting().accepted_samples
        requests = converger.observe_base(
            Surface(committed_samples=committed, canonical_through_sample=frontier)
        )
        assert len(requests) == 1
        proposal = converger.complete(requests[0].id, decoded(window_transcript(*TURNS)))
        assert proposal is not None
        assert proposal.start_sample == frontier
        intervals.append((proposal.start_sample, proposal.end_sample))
        frontier = proposal.end_sample
    assert intervals == [(index * WINDOW, (index + 1) * WINDOW) for index in range(6)]
    assert converger.accounting().decoded_audio_samples == 6 * WINDOW


# ---------------------------------------------------------------- proposals


def test_a_completed_window_proposes_its_words_on_the_session_clock():
    converger = RollingTranscriptConverger(epoch=3)
    feed(converger, 2 * WINDOW)
    converger.observe_base(
        Surface(epoch=3, committed_samples=2 * WINDOW, canonical_through_sample=0)
    )
    request = converger.observe_base(
        Surface(
            epoch=3,
            committed_samples=2 * WINDOW,
            canonical_through_sample=0,
            text_revision_version=4,
        )
    )
    assert request == ()  # already in flight; the version is still observed

    proposal = converger.complete(0, decoded(window_transcript(*TURNS), elapsed=2.5))
    assert proposal is not None
    assert (proposal.epoch, proposal.source) == (3, "rolling")
    assert proposal.base_text_revision_version == 4
    assert (proposal.start_sample, proposal.end_sample) == (0, WINDOW)
    assert proposal.decode_elapsed_sec == 2.5
    assert [(segment.start_sample, segment.end_sample) for segment in proposal.segments] == [
        (0, 5 * SAMPLE_RATE),
        (5 * SAMPLE_RATE, int(9.5 * SAMPLE_RATE)),
    ]
    assert [segment.text for segment in proposal.segments] == [turn[2] for turn in TURNS]
    assert {segment.authority for segment in proposal.segments} == {"rolling"}
    # A decoder's local `S01` is not a meeting identity; attribution is not this module's.
    assert {segment.canonical_speaker for segment in proposal.segments} == {None}


def test_a_timestamp_past_the_window_is_clamped_into_it_never_owned_outside():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, WINDOW)
    request = converger.observe_base(Surface(committed_samples=WINDOW))[0]
    proposal = converger.complete(
        request.id, decoded(window_transcript((0.0, "S01", "Over the edge.", 10.4)))
    )
    assert proposal is not None
    assert proposal.segments[-1].end_sample == WINDOW


def test_retained_jamie_window_4_is_normalized_and_makes_window_5_plannable():
    """G4: the observed cross-speaker overlap cannot forfeit the rest of the meeting."""

    session = LiveSession(max_retained_samples=6 * WINDOW)
    session.accept_frame(
        AudioFrame(sequence=0, pcm=silence(6 * WINDOW), sample_count=6 * WINDOW)
    )
    frozen = session.freeze_until(6 * WINDOW, reason="retained_jamie_regression")
    assert session.submit_canonical(
        CanonicalResult(
            span_id=frozen.id,
            epoch=frozen.epoch,
            start_sample=0,
            end_sample=6 * WINDOW,
            transcript="[0][S01]base[60]",
        )
    )

    converger = RollingTranscriptConverger(epoch=0)
    for _ in range(4):
        feed(converger, WINDOW)
        request = converger.observe_base(session.snapshot())[0]
        proposal = converger.complete(request.id, decoded(window_transcript(*TURNS)))
        assert proposal is not None
        assert session.apply_text_revision(proposal).applied

    feed(converger, WINDOW)
    request = converger.observe_base(session.snapshot())[0]
    # Window 5 is already retained by the time window 4 answers, as in paced live capture.
    feed(converger, WINDOW)
    proposal = converger.complete(
        request.id,
        decoded(
            window_transcript(
                (0.00, "S01", "Incredible.", 0.98),
                (
                    0.81,
                    "S02",
                    "So the question, of course, is how did he do it? I mean, banks fail. "
                    "Financial firms often have spectacular blowups and large",
                    9.97,
                ),
            )
        ),
    )
    assert proposal is not None

    raw_segments = (
        EffectiveTranscriptSegment(640000, 655680, "Incredible.", None, "rolling"),
        EffectiveTranscriptSegment(
            652960,
            799520,
            "So the question, of course, is how did he do it? I mean, banks fail. "
            "Financial firms often have spectacular blowups and large",
            None,
            "rolling",
        ),
    )
    raw_outcome = session.apply_text_revision(replace(proposal, segments=raw_segments))
    assert (raw_outcome.applied, raw_outcome.refusal) == (False, "segments_out_of_order")

    assert [(row.start_sample, row.end_sample) for row in proposal.segments] == [
        (640000, 655680),
        (655680, 799520),
    ]
    assert proposal.normalization_displaced_samples == 2720
    assert proposal.normalization_merged_segments == 0
    assert proposal.normalization_dropped_segments == 0
    assert len(" ".join(row.text for row in proposal.segments).split()) == 24
    assert session.apply_text_revision(proposal).applied

    following = converger.observe_base(session.snapshot())
    assert len(following) == 1
    assert (following[0].window_index, following[0].start_sample, following[0].end_sample) == (
        5,
        5 * WINDOW,
        6 * WINDOW,
    )


# ---------------------------------------------------------------- failure behaviour


def test_a_stale_completion_changes_nothing():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    request = converger.observe_base(Surface(committed_samples=2 * WINDOW))[0]
    assert converger.complete(request.id + 99, decoded(window_transcript(*TURNS))) is None
    assert converger.accounting().stale_completions == 1
    assert converger.accounting().in_flight_request_id == request.id
    assert converger.complete(request.id, decoded(window_transcript(*TURNS))) is not None


def test_a_window_that_publishes_nothing_stalls_instead_of_emptying_its_interval():
    """Plan §5.2 rolling failure: keep the surface, record the window, plan no more."""

    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    request = converger.observe_base(Surface(committed_samples=2 * WINDOW))[0]
    assert converger.complete(request.id, decoded("")) is None
    accounting = converger.accounting()
    assert (accounting.status, accounting.windows_failed) == (RollingStatus.WINDOW_FAILED, 1)
    assert converger.observe_base(
        Surface(committed_samples=2 * WINDOW, canonical_through_sample=WINDOW)
    ) == ()


def test_a_refused_proposal_keeps_its_cause_and_accounts_later_audio_without_retaining_it():
    """A3: refinement stops; base capture and the session sample clock do not."""

    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    request = converger.observe_base(Surface(committed_samples=2 * WINDOW))[0]
    assert converger.complete(request.id, decoded(window_transcript(*TURNS))) is not None
    before = converger.accounting()

    converger.note_proposal_refused("stale_text_revision_version")
    refused = converger.accounting()
    assert refused.status is RollingStatus.PROPOSAL_REFUSED
    assert refused.proposal_refusals == 1
    assert refused.last_proposal_refusal == "stale_text_revision_version"
    assert refused.windows_completed == before.windows_completed == 1
    assert refused.windows_failed == before.windows_failed == 0
    assert refused.decoded_audio_samples == before.decoded_audio_samples == WINDOW
    assert refused.observed_frontier_sample == before.observed_frontier_sample == 0
    assert refused.retained_samples == 0
    assert refused.in_flight_request_id is None

    feed(converger, 3 * WINDOW)
    after = converger.accounting()
    assert after.status is RollingStatus.PROPOSAL_REFUSED
    assert after.last_proposal_refusal == "stale_text_revision_version"
    assert after.proposal_refusals == 1
    assert after.accepted_samples == 5 * WINDOW
    assert after.retained_samples == 0
    assert converger.observe_base(
        Surface(committed_samples=5 * WINDOW, canonical_through_sample=0)
    ) == ()


def test_retained_audio_stays_inside_the_plan_bound_and_says_so_when_it_evicts():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 6 * WINDOW)  # the base commits nothing, so no window is ever planned
    accounting = converger.accounting()
    assert accounting.windows_planned == 0
    assert accounting.retained_samples <= DEFAULT_ROLLING_GEOMETRY.max_retained_samples
    assert accounting.retained_high_water_samples <= DEFAULT_ROLLING_GEOMETRY.max_retained_samples
    assert accounting.status is RollingStatus.PCM_EVICTED
    assert converger.observe_base(Surface(committed_samples=6 * WINDOW)) == ()


def test_a_healthy_session_never_evicts_and_holds_one_window_of_newer_audio():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, WINDOW)
    request = converger.observe_base(Surface(committed_samples=WINDOW))[0]
    feed(converger, WINDOW)
    accounting = converger.accounting()
    assert accounting.status is RollingStatus.ROLLING
    assert accounting.retained_samples == WINDOW
    assert len(request.pcm) == WINDOW * 2  # the in-flight payload is its own immutable copy


# ---------------------------------------------------------------- contract violations


def test_rolling_pcm_must_be_contiguous():
    converger = RollingTranscriptConverger(epoch=0)
    converger.accept_pcm(0, silence(SAMPLE_RATE))
    with pytest.raises(ValueError):
        converger.accept_pcm(2 * SAMPLE_RATE, silence(SAMPLE_RATE))


def test_a_snapshot_from_another_session_is_refused():
    converger = RollingTranscriptConverger(epoch=1)
    with pytest.raises(ValueError):
        converger.observe_base(Surface(epoch=2))


@pytest.mark.parametrize(
    "first, second",
    [
        (Surface(committed_samples=WINDOW), Surface(committed_samples=WINDOW - 1)),
        (
            Surface(committed_samples=2 * WINDOW, canonical_through_sample=WINDOW),
            Surface(committed_samples=2 * WINDOW, canonical_through_sample=0),
        ),
    ],
)
def test_neither_committed_audio_nor_the_frontier_may_move_backwards(first, second):
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    converger.observe_base(first)
    with pytest.raises(ValueError):
        converger.observe_base(second)


# ---------------------------------------------------------------- session end


def test_stop_states_what_the_terminal_pass_inherits_and_releases_the_ring():
    converger = RollingTranscriptConverger(epoch=5)
    feed(converger, 2 * WINDOW)
    request = converger.observe_base(Surface(epoch=5, committed_samples=2 * WINDOW))[0]
    converger.complete(request.id, decoded(window_transcript(*TURNS)))
    converger.observe_base(
        Surface(epoch=5, committed_samples=2 * WINDOW, canonical_through_sample=WINDOW)
    )

    plan = converger.stop(2 * WINDOW)
    assert plan.epoch == 5
    assert plan.end_sample == 2 * WINDOW
    assert plan.rolling_through_sample == WINDOW
    assert plan.rolling_status is RollingStatus.ROLLING
    assert (plan.windows_completed, plan.windows_failed) == (1, 0)

    accounting = converger.accounting()
    assert accounting.status is RollingStatus.STOPPED
    assert accounting.retained_samples == 0
    with pytest.raises(ValueError):
        converger.accept_pcm(2 * WINDOW, silence(SAMPLE_RATE))


def test_stop_reports_the_stall_that_ended_rolling_convergence():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, 2 * WINDOW)
    request = converger.observe_base(Surface(committed_samples=2 * WINDOW))[0]
    converger.complete(request.id, decoded(""))
    plan = converger.stop(2 * WINDOW)
    assert plan.rolling_status is RollingStatus.WINDOW_FAILED
    assert plan.rolling_through_sample == 0


def test_stop_refuses_an_end_behind_the_audio_it_was_given():
    converger = RollingTranscriptConverger(epoch=0)
    feed(converger, WINDOW)
    with pytest.raises(ValueError):
        converger.stop(WINDOW - 1)
