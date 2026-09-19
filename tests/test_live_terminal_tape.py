"""Plan E4 step 1 -- the complete mixed tape a terminal pass runs over (test tiers T1/T2).

Live mode decodes 2.5 seconds at a time and keeps nothing: the base path retains a span until
it commits, the rolling witness a bounded ring of the newest window, and neither can answer
the only question a terminal 150/120 pass asks -- *give me `[0, meeting_end)` of what this
session decoded*. `CompleteMixedTape` is that answer, in memory, and these are the properties
that make it usable as evidence rather than merely as a buffer:

- what it holds equals what the session accepted, sample for sample and byte for byte;
- what it does not hold, it names (the gap manifest of plan §6 M6), instead of letting two
  counts be subtracted into a reassuring zero;
- pressure degrades the tape and never the meeting (ADR-0003 D5): no path here raises at a
  frame, and a meeting whose tape stopped still publishes every word it would have published;
- the audio dies with the meeting (D3), and the accounting that proves it was faithful
  survives that death.

The corpus reading of the same properties, on real speech through the real runtime, is
`prototypes/streaming-diarization/live-convergence/verify_terminal_tape.py`.
"""

from __future__ import annotations

import asyncio
import hashlib
import tracemalloc
import unittest
from dataclasses import replace

from moss_transcribe_diarize.app.live_adapters import LiveProviderError
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceDescriptor,
    LiveServiceRuntime,
)
from moss_transcribe_diarize.app.live_session import PCM16_BYTES_PER_SAMPLE
from moss_transcribe_diarize.app.live_tape import (
    CompleteMixedTape,
    CompleteMixedTapeUnavailable,
    TAPE_CAPACITY_EXHAUSTED,
    TAPE_FRAME_NOT_ADMISSIBLE,
    TAPE_STORAGE_FAILED,
)

from tests.test_live_rolling_wiring import (
    FRAME_SAMPLES,
    ONE_WINDOW_FRAMES,
    ScriptedDecoder,
    _decoders,
    _descriptor,
    _endpoint_config,
    _runtime,
)
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy
from moss_transcribe_diarize.app.live_session import AudioFrame


def _pcm(samples: int, *, fill: bytes = b"\x11\x22") -> bytes:
    return fill * samples


class CompleteMixedTapeTest(unittest.TestCase):
    """T1 -- the tape on its own, with no session, no runtime and no audio provider."""

    def test_a_contiguous_meeting_is_retained_byte_for_byte_with_no_gaps(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        chunks = [_pcm(10), _pcm(20), _pcm(5)]
        cursor = 0
        for chunk in chunks:
            result = tape.append(start_sample=cursor, pcm=chunk)
            self.assertTrue(result.written)
            self.assertTrue(result.taping)
            cursor += len(chunk) // PCM16_BYTES_PER_SAMPLE

        whole = b"".join(chunks)
        accounting = tape.accounting(through_sample=35)
        self.assertEqual(accounting.sample_count, 35)
        self.assertEqual(accounting.gaps, ())
        self.assertTrue(accounting.complete)
        self.assertEqual(accounting.pcm_sha256, hashlib.sha256(whole).hexdigest())
        self.assertEqual(accounting.peak_retained_bytes, len(whole))
        self.assertEqual(tape.read(), whole)

    def test_a_sub_range_is_served_from_the_session_clock(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        tape.append(start_sample=0, pcm=_pcm(4, fill=b"\x00\x01"))
        tape.append(start_sample=4, pcm=_pcm(4, fill=b"\x00\x02"))

        self.assertEqual(tape.read(start_sample=4, end_sample=8), _pcm(4, fill=b"\x00\x02"))
        self.assertTrue(tape.covers(2, 6))
        self.assertFalse(tape.covers(6, 12))
        with self.assertRaises(CompleteMixedTapeUnavailable):
            tape.read(start_sample=6, end_sample=12)

    def test_capacity_stops_the_tape_and_names_the_tail_it_lost(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=20)
        self.assertTrue(tape.append(start_sample=0, pcm=_pcm(10)).written)

        overflow = tape.append(start_sample=10, pcm=_pcm(10))

        self.assertFalse(overflow.written)
        self.assertFalse(overflow.taping)
        self.assertIsNotNone(overflow.degradation)
        self.assertEqual(overflow.degradation.reason, TAPE_CAPACITY_EXHAUSTED)
        self.assertEqual(overflow.degradation.detail["capacity_bytes"], 20)
        self.assertEqual(overflow.degradation.detail["requested_bytes"], 20)
        accounting = tape.accounting(through_sample=20)
        self.assertEqual(accounting.sample_count, 10)
        self.assertEqual(accounting.refused_samples, 10)
        self.assertEqual([gap.to_dict() for gap in accounting.gaps], [
            {"start_sample": 10, "end_sample": 20, "sample_count": 10}
        ])
        self.assertFalse(accounting.complete)

    def test_a_stopped_tape_serves_nothing_at_all(self):
        """A terminal pass over part of a meeting is not a terminal pass."""

        tape = CompleteMixedTape(epoch=0, capacity_bytes=20)
        tape.append(start_sample=0, pcm=_pcm(10))
        tape.append(start_sample=10, pcm=_pcm(10))

        with self.assertRaises(CompleteMixedTapeUnavailable):
            tape.read(start_sample=0, end_sample=10)

    def test_a_hole_is_refused_rather_than_filled_with_silence(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        tape.append(start_sample=0, pcm=_pcm(10))
        before = tape.accounting(through_sample=10).pcm_sha256

        skipped = tape.append(start_sample=25, pcm=_pcm(10))

        self.assertFalse(skipped.written)
        self.assertEqual(skipped.degradation.reason, TAPE_FRAME_NOT_ADMISSIBLE)
        self.assertEqual(skipped.degradation.detail["expected_start_sample"], 10)
        self.assertEqual(skipped.degradation.detail["received_start_sample"], 25)
        after = tape.accounting(through_sample=10)
        self.assertEqual(after.sample_count, 10)
        self.assertEqual(after.pcm_sha256, before)
        self.assertEqual(after.refused_samples, 10)

    def test_a_partial_sample_is_refused_rather_than_stored(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)

        result = tape.append(start_sample=0, pcm=b"\x01\x02\x03")

        self.assertFalse(result.written)
        self.assertEqual(result.degradation.reason, TAPE_FRAME_NOT_ADMISSIBLE)
        self.assertEqual(result.degradation.detail["bytes"], 3)
        self.assertEqual(tape.accounting(through_sample=0).sample_count, 0)

    def test_an_empty_append_changes_nothing_and_keeps_taping(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        tape.append(start_sample=0, pcm=_pcm(4))

        result = tape.append(start_sample=4, pcm=b"")

        self.assertTrue(result.taping)
        self.assertFalse(result.written)
        self.assertEqual(tape.accounting(through_sample=4).sample_count, 4)

    def test_a_deferred_flush_failure_degrades_the_tape_before_accepting_the_frame(self):
        class FlushFailureFile:
            def seek(self, *args):
                return 0

            def write(self, payload):
                return len(payload)

            def flush(self):
                raise OSError("disk full during buffered flush")

            def close(self):
                return None

        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        tape._file.close()
        tape._file = FlushFailureFile()

        result = tape.append(start_sample=0, pcm=_pcm(12))

        self.assertFalse(result.written)
        self.assertEqual(result.degradation.reason, TAPE_STORAGE_FAILED)
        self.assertEqual(result.degradation.detail["operation"], "flush")
        accounting = tape.accounting(through_sample=12)
        self.assertEqual(accounting.sample_count, 0)
        self.assertEqual(accounting.refused_samples, 12)
        self.assertFalse(accounting.complete)

    def test_release_never_raises_when_close_reports_a_deferred_storage_failure(self):
        class CloseFailureFile:
            def close(self):
                raise OSError("disk full during close")

        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        tape.append(start_sample=0, pcm=_pcm(12))
        tape._file.close()
        tape._file = CloseFailureFile()

        tape.release()
        tape.release()

        accounting = tape.accounting(through_sample=12)
        self.assertTrue(accounting.released)
        self.assertEqual(accounting.retained_bytes, 0)
        self.assertEqual(accounting.degradation.reason, TAPE_STORAGE_FAILED)
        self.assertEqual(accounting.degradation.detail["operation"], "close")
        self.assertFalse(accounting.complete)

    def test_release_drops_the_audio_and_keeps_the_evidence(self):
        tape = CompleteMixedTape(epoch=0, capacity_bytes=1024)
        tape.append(start_sample=0, pcm=_pcm(12))
        digest = tape.accounting(through_sample=12).pcm_sha256

        tape.release()
        tape.release()

        accounting = tape.accounting(through_sample=12)
        self.assertTrue(accounting.released)
        self.assertEqual(accounting.retained_bytes, 0)
        self.assertEqual(accounting.peak_retained_bytes, 24)
        self.assertEqual(accounting.sample_count, 12)
        self.assertEqual(accounting.pcm_sha256, digest)
        self.assertFalse(tape.taping)
        with self.assertRaises(CompleteMixedTapeUnavailable):
            tape.read()
        refused = tape.append(start_sample=12, pcm=_pcm(4))
        self.assertFalse(refused.written)

    def test_a_capacity_must_be_declared_as_a_positive_number_of_bytes(self):
        with self.assertRaises(ValueError):
            CompleteMixedTape(epoch=0, capacity_bytes=0)

    def test_long_tape_retention_does_not_keep_the_whole_source_in_python_memory(self):
        retained_bytes = 32 * 1024 * 1024
        chunk = b"\x11\x22" * (512 * 1024)
        tape = CompleteMixedTape(epoch=0, capacity_bytes=retained_bytes)

        tracemalloc.start()
        cursor = 0
        while cursor * PCM16_BYTES_PER_SAMPLE < retained_bytes:
            tape.append(start_sample=cursor, pcm=chunk)
            cursor += len(chunk) // PCM16_BYTES_PER_SAMPLE
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        self.assertEqual(tape.retained_bytes, retained_bytes)
        self.assertLess(peak, 8 * 1024 * 1024)
        self.assertEqual(
            tape.read(start_sample=cursor - 16, end_sample=cursor),
            b"\x11\x22" * 16,
        )
        tape.release()


def _tape_descriptor(max_tape_bytes: int | None) -> LiveServiceDescriptor:
    descriptor = _descriptor()
    return replace(descriptor, bounds=replace(descriptor.bounds, max_tape_bytes=max_tape_bytes))


def _tape_runtime(
    *, max_tape_bytes: int | None, base: ScriptedDecoder | None = None
) -> LiveServiceRuntime:
    decoder = base if base is not None else _decoders(rolling=False)[0]
    runtime = _runtime(base=decoder, rolling=None)
    runtime.descriptor = _tape_descriptor(max_tape_bytes)
    return runtime


def _drive(runtime: LiveServiceRuntime, *, frames: int) -> tuple[str, bytes]:
    created = runtime.create()
    sent: list[bytes] = []
    for sequence in range(frames):
        pcm = bytes([sequence % 251, (sequence * 7) % 251]) * FRAME_SAMPLES
        sent.append(pcm)
        runtime.accept_frame(
            created.session_id,
            AudioFrame(sequence=sequence, pcm=pcm, sample_count=FRAME_SAMPLES),
        )
    return created.session_id, b"".join(sent)


def _released_events(runtime: LiveServiceRuntime, session_id: str) -> list[dict]:
    return [
        event.payload
        for event in runtime.events(session_id)
        if event.kind == "session_tape_released"
    ]


class CompleteTapeRuntimeWiringTest(unittest.TestCase):
    """T2 -- the tape inside the real runtime, which is where the audio actually arrives."""

    def test_a_deployment_that_declares_no_capacity_retains_no_tape(self):
        """ADR-0003 D2, in memory: the posture is asked for, never assumed."""

        runtime = _tape_runtime(max_tape_bytes=None)
        session_id, _ = _drive(runtime, frames=4)
        asyncio.run(runtime.stop(session_id, 5.0))

        coordinator = runtime._sessions[session_id].coordinator
        self.assertIsNone(coordinator.tape)
        self.assertIsNone(coordinator.tape_accounting())
        self.assertEqual(_released_events(runtime, session_id), [])

    def test_the_tape_is_what_the_transport_accepted_and_is_released_with_the_meeting(self):
        runtime = _tape_runtime(max_tape_bytes=4 * FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE)
        session_id, sent = _drive(runtime, frames=4)

        during = runtime._sessions[session_id].coordinator.tape_accounting()
        self.assertTrue(during.complete)
        self.assertEqual(during.retained_bytes, len(sent))

        asyncio.run(runtime.stop(session_id, 5.0))

        snapshot = runtime.snapshot(session_id).session
        payloads = _released_events(runtime, session_id)
        self.assertEqual(len(payloads), 1)
        payload = payloads[0]
        self.assertEqual(payload["sample_count"], snapshot.accepted_samples)
        self.assertEqual(payload["through_sample"], snapshot.accepted_samples)
        self.assertEqual(payload["pcm_sha256"], hashlib.sha256(sent).hexdigest())
        self.assertEqual(payload["gaps"], [])
        self.assertTrue(payload["complete"])
        self.assertTrue(payload["released"])
        self.assertEqual(payload["retained_bytes"], 0)
        self.assertEqual(payload["peak_retained_bytes"], len(sent))
        self.assertEqual(
            runtime._sessions[session_id].coordinator.tape.retained_bytes, 0
        )

    def test_a_tape_that_runs_out_of_capacity_does_not_cost_the_meeting_a_word(self):
        frames = 4
        roomy = _tape_runtime(max_tape_bytes=frames * FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE)
        roomy_session, _ = _drive(roomy, frames=frames)
        asyncio.run(roomy.stop(roomy_session, 5.0))
        expected = runtime_transcript(roomy, roomy_session)

        cramped = _tape_runtime(max_tape_bytes=FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE)
        cramped_session, _ = _drive(cramped, frames=frames)
        asyncio.run(cramped.stop(cramped_session, 5.0))

        self.assertEqual(runtime_transcript(cramped, cramped_session), expected)
        session = cramped.snapshot(cramped_session).session
        self.assertEqual(session.accepted_samples, session.accounted_samples)
        self.assertIsNone(cramped.snapshot(cramped_session).terminal_failure)
        payload = _released_events(cramped, cramped_session)[0]
        self.assertFalse(payload["complete"])
        self.assertEqual(payload["degradation"]["reason"], TAPE_CAPACITY_EXHAUSTED)
        self.assertEqual(payload["sample_count"], FRAME_SAMPLES)
        self.assertEqual(payload["refused_samples"], session.accepted_samples - FRAME_SAMPLES)
        self.assertEqual(
            payload["gaps"],
            [
                {
                    "start_sample": FRAME_SAMPLES,
                    "end_sample": session.accepted_samples,
                    "sample_count": session.accepted_samples - FRAME_SAMPLES,
                }
            ],
        )

    def test_a_meeting_that_ends_badly_keeps_no_audio_either(self):
        base = ScriptedDecoder(
            max_samples=10**9,
            label="base",
            calls=[],
            failure=LiveProviderError("decoder is gone."),
        )
        runtime = _tape_runtime(
            max_tape_bytes=64 * FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE, base=base
        )
        # A decoder that goes away terminalizes the session at whichever call first
        # observes it -- a frame or the stop drain, depending on when the pump thread
        # lands -- so the driver tolerates both and the assertion is on the ending.
        try:
            session_id, _ = _drive(runtime, frames=ONE_WINDOW_FRAMES)
            asyncio.run(runtime.stop(session_id, 5.0))
        except Exception:
            pass
        session_id = next(iter(runtime._sessions))

        self.assertIsNotNone(runtime.snapshot(session_id).terminal_failure)
        payloads = _released_events(runtime, session_id)
        self.assertEqual(len(payloads), 1)
        self.assertTrue(payloads[0]["released"])
        self.assertEqual(payloads[0]["retained_bytes"], 0)
        self.assertEqual(
            runtime._sessions[session_id].coordinator.tape.retained_bytes, 0
        )


def runtime_transcript(runtime: LiveServiceRuntime, session_id: str) -> list[tuple[int, int, str]]:
    session = runtime.snapshot(session_id).session
    return [(item.start_sample, item.end_sample, item.transcript) for item in session.committed]


if __name__ == "__main__":  # pragma: no cover - parity with the other live test modules
    unittest.main()
