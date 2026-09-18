"""WP35 -- what the Stop-time drain still owes, and what the terminal pass supersedes.

The drain that `_finish_stop` awaits used to include the rolling witness, and rolling
re-plans itself: every completed window's `submit_refinement` calls `observe_base` again,
which admits the next one. Because `stop_rolling()` only ran *after* the drain, the queue the
drain waited on refilled itself until rolling had caught up with the whole meeting -- through
the one process-scoped pump worker every session shares. WP25's capacity_4x600 measured that
as 64 post-Stop decodes across four meetings and no terminal pass started inside 90 s.

Everything those windows would have produced is text for spans the base path had already
committed, and the terminal pass proposes `[0, end_sample)` for the whole meeting on top of
it. So for a meeting that will get a terminal pass, the post-Stop rolling work is work whose
result is about to be overwritten; for a meeting that will not, rolling is still the
meeting's last listener and the drain is unchanged. These tests hold both halves, and the
lifecycle contracts that must survive either way.
"""

from __future__ import annotations

import asyncio
import itertools
import unittest
from dataclasses import replace

from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceRuntime,
    _ManualCanonicalPumpScheduler,
    _ManualTerminalScheduler,
)
from moss_transcribe_diarize.app.live_session import AudioFrame
from moss_transcribe_diarize.app.live_transcript_convergence import (
    PCM16_BYTES_PER_SAMPLE,
    TerminalTranscriptFinalizer,
)
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy

from tests.test_live_rolling_wiring import (
    FRAME_SAMPLES,
    ONE_WINDOW_FRAMES,
    ScriptedIdentity,
    ScriptedSpeech,
    TWO_WINDOW_FRAMES,
    _decoders,
    _descriptor,
    _endpoint_config,
)
from tests.test_live_terminal_finalizer import WholeMeetingStub

MEETING_SAMPLES = TWO_WINDOW_FRAMES * FRAME_SAMPLES
TERMINAL_TEXT = "[0][S01]the whole meeting[10]"


SIZED_FOR_THE_MEETING = object()


def _runtime(*, finalizer, sessions: int = 1, tape_bytes=SIZED_FOR_THE_MEETING):
    """One runtime, one manual pump for every session, one manual terminal scheduler.

    The manual pump is the point of the fixture rather than a convenience: it reproduces the
    deployment's single process-scoped worker exactly, and it lets a test say *when* the pump
    runs, which is the only way to put canonical work in the drain deterministically.
    """

    base, witness = _decoders(rolling=True)
    descriptor = _descriptor(max_events=5000)
    capacity = (
        sessions * MEETING_SAMPLES * PCM16_BYTES_PER_SAMPLE
        if tape_bytes is SIZED_FOR_THE_MEETING
        else tape_bytes
    )
    pump = _ManualCanonicalPumpScheduler()
    terminal = _ManualTerminalScheduler()
    names = itertools.count()
    runtime = LiveServiceRuntime(
        descriptor=replace(
            descriptor, bounds=replace(descriptor.bounds, max_tape_bytes=capacity)
        ),
        endpoint_policy_factory=lambda: EndpointPolicy(_endpoint_config()),
        speech_provider_factory=ScriptedSpeech,
        decoder_factory=lambda: base,
        rolling_decoder_factory=lambda: witness,
        identity_preparer_factory=ScriptedIdentity,
        terminal_finalizer=finalizer,
        session_id_factory=lambda: f"stop-drain-{next(names)}",
        _canonical_scheduler=pump,
        _terminal_scheduler=terminal,
    )
    return runtime, witness, pump, terminal


def _finalizer(text: str = TERMINAL_TEXT) -> TerminalTranscriptFinalizer:
    return TerminalTranscriptFinalizer(runner=WholeMeetingStub(text))


def _capture(runtime, session_id, *, frames: int = TWO_WINDOW_FRAMES) -> None:
    """Accept a whole meeting without pumping, so the decode work lands in the drain.

    That is the WP25 shape rather than a contrivance: four meetings feeding one worker in
    real time leave it behind, and what is behind at Stop is what the drain has to answer.
    """

    for sequence in range(frames):
        runtime.accept_frame(
            session_id,
            AudioFrame(
                sequence=sequence, pcm=b"\x11\x22" * FRAME_SAMPLES, sample_count=FRAME_SAMPLES
            ),
        )


def _stop_all(runtime, session_ids, pump, *, deadline: float = 5.0):
    """Stop every session at once and pump the shared worker until they have all answered."""

    async def run():
        tasks = [
            asyncio.create_task(runtime.stop(session_id, deadline))
            for session_id in session_ids
        ]
        # The worker does not run until every stop request has been taken up and is waiting
        # on its drain. In the deployment that ordering is free -- the pump is a thread that
        # was already running when the stop arrived -- but here the pump *is* this loop, and
        # letting it run first would measure the scheduler's start-up order instead of the
        # drain. A session with nothing unresolved answers without ever registering a waiter.
        while not all(
            task.done() or runtime._sessions[session_id].drain_waiters
            for task, session_id in zip(tasks, session_ids)
        ):
            await asyncio.sleep(0)
        while not all(task.done() for task in tasks):
            pump.drain()
            await asyncio.sleep(0)
        return [await task for task in tasks]

    return asyncio.run(run())


def _events(runtime, session_id, kind):
    return [event for event in runtime.events(session_id) if event.kind == kind]


def _after_stop(runtime, session_id):
    events = runtime.events(session_id)
    stop_seq = next(event.seq for event in events if event.kind == "stop_requested")
    return [event for event in events if event.seq > stop_seq]


class StopDrainTest(unittest.TestCase):
    def test_a_meeting_with_a_terminal_pass_decodes_no_rolling_window_after_stop(self):
        runtime, witness, pump, terminal = _runtime(finalizer=_finalizer())
        session_id = runtime.create().session_id
        _capture(runtime, session_id)
        self.assertEqual(witness.calls, [], "the fixture must leave the work in the drain")

        _stop_all(runtime, [session_id], pump)

        self.assertEqual(witness.calls, [])
        after = _after_stop(runtime, session_id)
        self.assertEqual(
            [event.payload["admitted"] for event in after if event.kind == "rolling_decode_queued"],
            [],
        )
        self.assertEqual(terminal.pending, 1)
        terminal.run_one()
        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.finalization_status, "final")
        self.assertEqual(snapshot.accepted_samples, snapshot.accounted_samples)

    def test_a_meeting_with_no_terminal_pass_keeps_its_rolling_drain(self):
        """Cancellation is scoped to the meetings whose surface terminal is about to replace."""

        runtime, witness, pump, terminal = _runtime(finalizer=None)
        session_id = runtime.create().session_id
        _capture(runtime, session_id)

        _stop_all(runtime, [session_id], pump)

        self.assertEqual(witness.calls, [(0, 160000), (160000, 320000)])
        self.assertEqual(terminal.pending, 0)
        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.finalization_status, "not_started")
        self.assertEqual(snapshot.accepted_samples, snapshot.accounted_samples)
        self.assertEqual(
            {segment.authority for segment in snapshot.effective_transcript}, {"rolling"}
        )

    def test_a_deployment_that_kept_no_tape_keeps_its_rolling_drain(self):
        """A named finalizer is not a terminal pass: without the audio there is nothing to run."""

        runtime, witness, pump, _ = _runtime(finalizer=_finalizer(), tape_bytes=None)
        session_id = runtime.create().session_id
        _capture(runtime, session_id)

        _stop_all(runtime, [session_id], pump)

        self.assertEqual(witness.calls, [(0, 160000), (160000, 320000)])
        self.assertEqual(
            runtime.snapshot(session_id).session.finalization_status, "unavailable"
        )

    def test_cancelled_rolling_never_mutates_the_surface_after_stop(self):
        runtime, _, pump, terminal = _runtime(finalizer=_finalizer())
        session_id = runtime.create().session_id
        _capture(runtime, session_id)

        _stop_all(runtime, [session_id], pump)
        drained = runtime.snapshot(session_id).session
        self.assertEqual(
            [event.payload["source"] for event in _events(runtime, session_id, "text_revision_applied")],
            [],
        )
        terminal.run_one()

        after = runtime.snapshot(session_id).session
        # The only revision this meeting ever saw is the terminal one, and it arrived after
        # the stop response -- so no reader was shown a surface a cancelled window wrote.
        self.assertEqual(drained.text_revision_version, 0)
        self.assertEqual(after.text_revision_version, 1)
        self.assertEqual(
            [event.payload["source"] for event in _events(runtime, session_id, "text_revision_applied")],
            ["terminal"],
        )

    def test_an_accepted_stop_still_ends_final_and_accounts_every_sample(self):
        """WP15: an accepted Stop ends final or failed, never interrupted."""

        runtime, _, pump, terminal = _runtime(finalizer=_finalizer())
        session_id = runtime.create().session_id
        _capture(runtime, session_id)

        snapshots = _stop_all(runtime, [session_id], pump)
        terminal.run_one()

        self.assertEqual(snapshots[0].session.status, "closed")
        self.assertIsNone(runtime.snapshot(session_id).terminal_failure)
        snapshot = runtime.snapshot(session_id).session
        self.assertEqual(snapshot.status, "closed")
        self.assertEqual(snapshot.finalization_status, "final")
        self.assertEqual(snapshot.accepted_samples, MEETING_SAMPLES)
        self.assertEqual(snapshot.accepted_samples, snapshot.accounted_samples)
        self.assertEqual(runtime.snapshot(session_id).pending_work_items, 0)

    def test_every_admitted_window_still_closes_its_own_account(self):
        """Plan §7.4's property survives the cancellation: one completion per admission."""

        runtime, _, pump, _ = _runtime(finalizer=_finalizer())
        session_id = runtime.create().session_id
        _capture(runtime, session_id)
        _stop_all(runtime, [session_id], pump)

        admitted = {
            event.payload["item_id"]
            for event in _events(runtime, session_id, "rolling_decode_queued")
            if event.payload["admitted"]
        }
        completed = [
            event.payload["item_id"]
            for event in _events(runtime, session_id, "rolling_decode_completed")
        ]
        self.assertEqual(admitted, set(completed))
        self.assertEqual(len(completed), len(set(completed)))

    def test_four_concurrent_stops_all_reach_final_with_no_post_stop_rolling(self):
        """The WP25 capacity shape, minus the GPU: four meetings, one worker, one Stop each."""

        runtime, witness, pump, terminal = _runtime(finalizer=_finalizer(), sessions=4)
        session_ids = [runtime.create().session_id for _ in range(4)]
        for session_id in session_ids:
            _capture(runtime, session_id, frames=ONE_WINDOW_FRAMES)

        _stop_all(runtime, session_ids, pump)
        self.assertEqual(terminal.pending, 4)
        terminal.drain()

        for session_id in session_ids:
            snapshot = runtime.snapshot(session_id).session
            self.assertEqual(snapshot.finalization_status, "final")
            self.assertEqual(snapshot.accepted_samples, snapshot.accounted_samples)
            self.assertEqual(
                [
                    event
                    for event in _after_stop(runtime, session_id)
                    if event.kind == "rolling_decode_queued"
                ],
                [],
            )
        self.assertEqual(witness.calls, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
