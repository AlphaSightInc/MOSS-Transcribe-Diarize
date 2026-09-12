"""Plan §12.3 -- the terminal pass inside the live runtime (test tier T2).

The finalizer itself is proved elsewhere: handed a tape and a runner it returns one proposal
over `[0, meeting_end)` or a named refusal (`tests/test_live_terminal_finalizer.py`), and
handed the paired file arm's own decode it publishes the paired file arm's own surface
(`prototypes/streaming-diarization/live-convergence/verify_terminal_finalizer.py`). None of
that says the *meeting* gets one.

What only exists once the runtime wires it is the lifecycle, and the lifecycle is a promise
to a reader who is still polling after the meeting ended (plan §7.3, §12.3):

- the stop request returns the meeting's final accounting **before** the terminal decode,
  which takes minutes, and says `running` so the reader knows to come back;
- the surface stays readable and stays the rolling one for that whole interval -- a meeting
  is never blank while its last listener is thinking;
- every ending has a word: `final` when a terminal revision replaced the surface,
  `failed` when a pass produced none, `unavailable` when there was nothing to run one on,
  and `not_started` on a deployment that never asked for one;
- the meeting's audio outlives it by exactly one listener and no longer (Appendix B Q10).

The scripted decoders here are the rolling-wiring file's, for the reason that file gives:
these tests are about the runtime putting pieces together, and the pieces are measured on
real audio somewhere else.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceRuntime,
    _ManualTerminalScheduler,
)
from moss_transcribe_diarize.app.live_session import AudioFrame, LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy
from moss_transcribe_diarize.app.live_tape import PCM16_BYTES_PER_SAMPLE
from moss_transcribe_diarize.app.live_transcript_convergence import (
    RollingStatus,
    TerminalTranscriptFinalizer,
)

from tests.test_live_rolling_wiring import (
    FRAME_SAMPLES,
    ONE_WINDOW_FRAMES,
    ScriptedIdentity,
    ScriptedSpeech,
    WINDOW_SAMPLES,
    _decoders,
    _descriptor,
    _endpoint_config,
)
from tests.test_live_terminal_finalizer import WholeMeetingStub

MEETING_SAMPLES = ONE_WINDOW_FRAMES * FRAME_SAMPLES
TERMINAL_TEXT = "[0][S01]the whole meeting[10]"


def _runtime(
    *,
    finalizer=None,
    tape_bytes: int | None = MEETING_SAMPLES * PCM16_BYTES_PER_SAMPLE,
    rolling: bool = True,
    scheduler: _ManualTerminalScheduler | None = None,
):
    """The rolling-wiring runtime plus E4's two collaborators, both declared by the caller.

    `tape_bytes` is the deployment's capacity (ADR-0003 D2) and `finalizer` is the meeting's
    last listener; neither has a default in production and neither has one here.
    """

    base, witness = _decoders(rolling=rolling)
    descriptor = _descriptor()
    return (
        LiveServiceRuntime(
            descriptor=replace(
                descriptor, bounds=replace(descriptor.bounds, max_tape_bytes=tape_bytes)
            ),
            endpoint_policy_factory=lambda: EndpointPolicy(_endpoint_config()),
            speech_provider_factory=ScriptedSpeech,
            decoder_factory=lambda: base,
            rolling_decoder_factory=None if witness is None else (lambda: witness),
            identity_preparer_factory=ScriptedIdentity,
            terminal_finalizer=finalizer,
            session_id_factory=lambda: "terminal-session",
            _terminal_scheduler=scheduler,
        ),
        witness,
    )


def _finalizer(text: str = TERMINAL_TEXT, **kwargs) -> TerminalTranscriptFinalizer:
    return TerminalTranscriptFinalizer(runner=WholeMeetingStub(text, **kwargs))


def _stop_after_a_meeting(runtime, *, frames: int = ONE_WINDOW_FRAMES) -> str:
    created = runtime.create()
    for sequence in range(frames):
        runtime.accept_frame(
            created.session_id,
            AudioFrame(
                sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
            ),
        )
    asyncio.run(runtime.stop(created.session_id, 5.0))
    return created.session_id


def _kinds(runtime, session_id: str) -> list[str]:
    return [event.kind for event in runtime.events(session_id)]


def _payload(runtime, session_id: str, kind: str) -> dict:
    """The LAST event of this kind: `text_revision_applied` has two producers by design."""

    for event in reversed(runtime.events(session_id)):
        if event.kind == kind:
            return dict(event.payload)
    raise AssertionError(f"no {kind} event on the stream: {_kinds(runtime, session_id)}")


class TerminalLifecycleTest(unittest.TestCase):
    """The four endings a meeting can have, and what a polling reader is told in each."""

    def test_a_deployment_that_names_no_finalizer_is_the_service_as_it_shipped(self):
        """No listener, no pass, no new word -- and the tape still ends with the meeting."""

        runtime, _ = _runtime(finalizer=None)
        session_id = _stop_after_a_meeting(runtime)

        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.finalization_status, "not_started")
        self.assertNotIn("terminal_finalization_started", _kinds(runtime, session_id))
        self.assertIn("session_tape_released", _kinds(runtime, session_id))
        self.assertEqual(
            {segment.authority for segment in snapshot.effective_transcript}, {"rolling"}
        )

    def test_stop_returns_running_before_the_terminal_decode_and_keeps_the_surface(self):
        """Plan §12.3's last paragraph: the stop request is not the thing that decodes."""

        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(finalizer=_finalizer(), scheduler=scheduler)
        session_id = _stop_after_a_meeting(runtime)

        stopped = runtime.snapshot(session_id).session
        self.assertEqual(stopped.status, "closed")
        self.assertEqual(stopped.finalization_status, "running")
        self.assertEqual(scheduler.pending, 1)
        # The reader who polls during the whole `running` interval sees the surface the
        # rolling witness published, not a blank one and not a partial terminal one.
        self.assertEqual(
            {segment.authority for segment in stopped.effective_transcript}, {"rolling"}
        )
        self.assertEqual(stopped.accepted_samples, stopped.accounted_samples)
        # The audio the pass will read is still there: the release moved behind it.
        self.assertNotIn("session_tape_released", _kinds(runtime, session_id))
        started = _payload(runtime, session_id, "terminal_finalization_started")
        self.assertEqual(started["end_sample"], MEETING_SAMPLES)
        self.assertEqual(started["rolling_status"], RollingStatus.ROLLING.value)
        self.assertEqual(started["finalization_status"], "running")

    def test_the_pass_replaces_the_surface_once_and_then_the_audio_is_released(self):
        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(finalizer=_finalizer(), scheduler=scheduler)
        session_id = _stop_after_a_meeting(runtime)
        during = runtime.snapshot(session_id).session

        self.assertTrue(scheduler.run_one())

        after = runtime.snapshot(session_id).session
        self.assertEqual(after.finalization_status, "final")
        self.assertEqual(after.text_revision_version, during.text_revision_version + 1)
        self.assertEqual(after.canonical_through_sample, MEETING_SAMPLES)
        self.assertEqual(
            [(item.start_sample, item.end_sample, item.text) for item in after.effective_transcript],
            [(0, MEETING_SAMPLES, "the whole meeting")],
        )
        self.assertEqual({item.authority for item in after.effective_transcript}, {"terminal"})
        # G-M4-5: a pass that replaced every word changed no accounting.
        self.assertEqual(after.accepted_samples, after.accounted_samples)
        self.assertEqual(after.accepted_samples, MEETING_SAMPLES)
        self.assertIsNone(runtime.snapshot(session_id).terminal_failure)

    def test_the_stream_reads_started_then_revision_then_completed_then_released(self):
        """The order is the meeting's own: nothing is released before its evidence is written."""

        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(finalizer=_finalizer(), scheduler=scheduler)
        session_id = _stop_after_a_meeting(runtime)
        scheduler.run_one()

        kinds = _kinds(runtime, session_id)
        tail = [kind for kind in kinds if kind.startswith(("terminal_", "text_revision", "session_tape"))]
        self.assertEqual(
            tail[-4:],
            [
                "terminal_finalization_started",
                "text_revision_applied",
                "terminal_finalization_completed",
                "session_tape_released",
            ],
        )
        completed = _payload(runtime, session_id, "terminal_finalization_completed")
        self.assertEqual(completed["outcome"], "finalized")
        self.assertEqual((completed["applied"], completed["refusal"]), (True, None))
        self.assertEqual(completed["end_sample"], MEETING_SAMPLES)
        self.assertEqual(completed["tape_samples"], MEETING_SAMPLES)
        self.assertEqual(completed["window_seconds"], 150.0)
        self.assertEqual(completed["stride_seconds"], 120.0)
        self.assertEqual(completed["finalization_status"], "final")
        revision = _payload(runtime, session_id, "text_revision_applied")
        self.assertEqual(revision["source"], "terminal")
        self.assertEqual((revision["start_sample"], revision["end_sample"]), (0, MEETING_SAMPLES))

    def test_no_terminal_event_carries_a_word_of_the_meeting(self):
        """Plan §7.4: counts, samples, timings and typed names. The words are the surface's."""

        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(
            finalizer=_finalizer("[0][S01]confidential board discussion[10]"), scheduler=scheduler
        )
        session_id = _stop_after_a_meeting(runtime)
        scheduler.run_one()

        for event in runtime.events(session_id):
            if not event.kind.startswith(("terminal_", "session_tape")):
                continue
            self.assertNotIn("confidential", repr(event.payload), event.kind)
            self.assertNotIn("board", repr(event.payload), event.kind)


class TerminalFailureLifecycleTest(unittest.TestCase):
    """A meeting that was captured succeeded. Its last listener may still fail, by name."""

    def test_a_failed_decode_preserves_and_reports_the_rolling_surface(self):
        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(
            finalizer=_finalizer(raises=RuntimeError("the model went away")), scheduler=scheduler
        )
        session_id = _stop_after_a_meeting(runtime)
        rolling_surface = runtime.snapshot(session_id).session.effective_transcript
        scheduler.run_one()

        after = runtime.snapshot(session_id).session
        self.assertEqual(after.finalization_status, "failed")
        self.assertEqual(after.effective_transcript, rolling_surface)
        self.assertNotEqual(after.effective_transcript, ())
        failed = _payload(runtime, session_id, "terminal_finalization_failed")
        self.assertEqual((failed["outcome"], failed["reason"]), ("decode_failed", "RuntimeError"))
        self.assertEqual((failed["applied"], failed["finalization_status"]), (False, "failed"))
        from moss_transcribe_diarize.phase2_acceptance_external import _diagnostic_event
        kinds = ("stop_requested", "session_closed", "terminal_finalization_started",
                 "terminal_finalization_failed")
        events = [event for event in runtime.events(session_id) if event.kind in kinds]
        self.assertEqual(tuple(event.kind for event in events), kinds)
        rows = [_diagnostic_event(event.to_dict()) for event in events]
        self.assertTrue(all(row["session_id"] == session_id for row in rows))
        self.assertEqual([row["seq"] for row in rows], sorted(row["seq"] for row in rows))
        times = [row["runtime_monotonic_ns"] for row in rows]
        self.assertTrue(all(value > 0 for value in times))
        self.assertEqual(times, sorted(times))
        self.assertEqual(rows[-1]["reason"], "RuntimeError")
        self.assertEqual(rows[-1]["refusal"], failed.get("refusal"))
        # Failing is still an ending: the audio does not outlive the pass that needed it.
        self.assertIn("session_tape_released", _kinds(runtime, session_id))
        self.assertIsNone(runtime.snapshot(session_id).terminal_failure)

    def test_a_deployment_that_kept_no_tape_says_unavailable_and_names_the_reason(self):
        """Two different facts: "nobody tried" and "there was nothing to try on"."""

        runtime, _ = _runtime(finalizer=_finalizer(), tape_bytes=None)
        session_id = _stop_after_a_meeting(runtime)

        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.finalization_status, "unavailable")
        failed = _payload(runtime, session_id, "terminal_finalization_failed")
        self.assertEqual(failed["reason"], "no_retained_tape")
        self.assertNotIn("terminal_finalization_started", _kinds(runtime, session_id))
        self.assertNotEqual(snapshot.effective_transcript, ())

    def test_a_deployment_with_no_rolling_witness_has_no_extent_to_finalize(self):
        runtime, _ = _runtime(finalizer=_finalizer(), rolling=False)
        session_id = _stop_after_a_meeting(runtime)

        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.finalization_status, "unavailable")
        self.assertEqual(
            _payload(runtime, session_id, "terminal_finalization_failed")["reason"],
            "no_terminal_plan",
        )

    def test_a_defect_in_the_finalizer_is_a_failed_pass_and_never_a_failed_meeting(self):
        class Exploding:
            def finalize(self, **kwargs):
                raise ZeroDivisionError("a defect, not a refusal")

        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(finalizer=Exploding(), scheduler=scheduler)
        session_id = _stop_after_a_meeting(runtime)
        with self.assertLogs("moss_transcribe_diarize.live.terminal", level="WARNING"):
            scheduler.run_one()

        service = runtime.snapshot(session_id)
        self.assertIsNone(service.terminal_failure)
        self.assertEqual(service.session.status, "closed")
        self.assertEqual(service.session.finalization_status, "failed")
        failed = _payload(runtime, session_id, "terminal_finalization_failed")
        self.assertEqual(failed["reason"], "finalizer_defect")
        self.assertIn("session_tape_released", _kinds(runtime, session_id))

    def test_a_second_pass_cannot_unfinalize_a_surface_a_reader_was_already_shown(self):
        """G-M4-9 through the runtime: the session refuses, and the status does not fall back."""

        scheduler = _ManualTerminalScheduler()
        runtime, _ = _runtime(finalizer=_finalizer(), scheduler=scheduler)
        session_id = _stop_after_a_meeting(runtime)
        scheduler.run_one()
        state = runtime._sessions[session_id]
        published = runtime.snapshot(session_id).session.effective_transcript

        runtime._run_terminal(state, state.terminal_plan, state.coordinator.tape)

        after = runtime.snapshot(session_id).session
        self.assertEqual(after.finalization_status, "final")
        self.assertEqual(after.effective_transcript, published)
        self.assertEqual(after.text_revision_version, 2)

    def test_a_witness_that_died_mid_meeting_still_leaves_the_pass_its_extent(self):
        """Rolling and the meeting do not end at the same moment, and terminal follows the meeting.

        A refinement defect stops rolling where it stands. The terminal pass is exactly what
        such a meeting needs most, so the plan it inherits is still the meeting's extent --
        with rolling's own ending recorded beside it rather than overwritten by it.
        """

        scheduler = _ManualTerminalScheduler()
        runtime, witness = _runtime(finalizer=_finalizer(), scheduler=scheduler)
        created = runtime.create()
        coordinator = runtime._sessions[created.session_id].coordinator

        def exploding_submit(decode, item):
            raise ZeroDivisionError("a witness defect")

        coordinator.submit_refinement = exploding_submit
        for sequence in range(ONE_WINDOW_FRAMES):
            runtime.accept_frame(
                created.session_id,
                AudioFrame(
                    sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
                ),
            )
        with self.assertLogs("moss_transcribe_diarize.live.rolling", level="WARNING"):
            asyncio.run(runtime.stop(created.session_id, 5.0))

        started = _payload(runtime, created.session_id, "terminal_finalization_started")
        self.assertEqual(started["end_sample"], MEETING_SAMPLES)
        self.assertEqual(started["rolling_status"], RollingStatus.ROLLING.value)
        self.assertEqual(started["rolling_through_sample"], 0)
        scheduler.run_one()
        after = runtime.snapshot(created.session_id).session
        self.assertEqual(after.finalization_status, "final")
        self.assertEqual(after.canonical_through_sample, MEETING_SAMPLES)

    def test_the_pass_reads_the_whole_meeting_and_only_the_meeting(self):
        scheduler = _ManualTerminalScheduler()
        runner = WholeMeetingStub(TERMINAL_TEXT)
        runtime, _ = _runtime(
            finalizer=TerminalTranscriptFinalizer(runner=runner), scheduler=scheduler
        )
        session_id = _stop_after_a_meeting(runtime)
        scheduler.run_one()

        self.assertEqual(len(runner.calls), 1)
        pcm, rate, channels, _ = runner.calls[0]
        self.assertEqual(len(pcm), MEETING_SAMPLES * PCM16_BYTES_PER_SAMPLE)
        self.assertEqual(pcm, b"\x11\x22" * MEETING_SAMPLES)
        self.assertEqual((rate, channels), (LIVE_SAMPLE_RATE, 1))
        self.assertEqual(MEETING_SAMPLES, WINDOW_SAMPLES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


def test_finalizer_defect_does_not_log_provider_content(caplog):
    class Exploding:
        def finalize(self, **kwargs):
            raise ValueError('PRIVATE_TRANSCRIPT PRIVATE_API_KEY')
    scheduler = _ManualTerminalScheduler()
    runtime, _ = _runtime(finalizer=Exploding(), scheduler=scheduler)
    session_id = _stop_after_a_meeting(runtime)
    with caplog.at_level('WARNING', logger='moss_transcribe_diarize.live.terminal'):
        scheduler.run_one()
    assert 'error_type=ValueError' in caplog.text
    assert 'PRIVATE' not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert runtime.snapshot(session_id).session.finalization_status == 'failed'
