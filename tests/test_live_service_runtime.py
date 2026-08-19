from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import inspect
import json
import os
import threading
import time
import unittest
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceConfigHashes,
    LiveServiceBounds,
    LiveServiceDescriptor,
    LiveServiceEvent,
    LiveServiceFailureRecord,
    LiveServiceFailureKind,
    LiveServiceProviderConfigFailure,
    LiveServiceRuntime,
    LiveServiceTransportPacingFailure,
    _ManualCanonicalPumpScheduler,
    _TransientCanonicalPumpScheduler,
    hash_config,
)
from moss_transcribe_diarize.app import live_service_runtime as runtime_module
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)


def _digest(label: str) -> str:
    return hash_config({"label": label})


class LiveServiceContractTypesTest(unittest.TestCase):
    def test_runtime_public_operation_set_stays_narrow(self):
        operations = [
            name
            for name, value in vars(LiveServiceRuntime).items()
            if not name.startswith("_") and inspect.isfunction(value)
        ]

        self.assertEqual(operations, ["create", "accept_frame", "events", "snapshot", "stop", "abort"])

    def test_descriptor_is_immutable_versioned_and_json_safe(self):
        hashes = LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1600},
            identity_config={"max_speakers": 4},
            decoder_config={"max_samples": 16000},
        )
        descriptor = LiveServiceDescriptor(
            source_revision="eda5e69faf0e0251383029295f7e8875a2a1a4f6",
            provider_name="deterministic-fake",
            provider_revision="test-revision",
            provider_manifest_hash=_digest("provider"),
            config_hashes=hashes,
            bounds=LiveServiceBounds(
                max_frame_samples=LIVE_SAMPLE_RATE,
                max_queue_depth=2,
                max_retained_samples=LIVE_SAMPLE_RATE * 4,
                max_identity_speakers=4,
                max_events=32,
            ),
        )

        payload = descriptor.to_dict()

        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["live_protocol_version"], "moss-live-service.v1")
        self.assertEqual(
            payload["live_protocol"],
            {
                "protocol": "moss-live-service.v2",
                "min_protocol_version": 2,
                "max_protocol_version": 2,
                "capabilities": {
                    "lanes": True,
                    "binary": False,
                    "idempotent_frames": True,
                    "resumable": True,
                },
            },
        )
        self.assertEqual(payload["sample_rate"], LIVE_SAMPLE_RATE)
        self.assertTrue(payload["feature_enabled"])
        self.assertEqual(payload["config_hashes"]["combined_config_hash"], hashes.combined_config_hash)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            descriptor.provider_name = "mutated"  # type: ignore[misc]

    def test_config_hashes_are_deterministic_and_validate_digest_shape(self):
        left = LiveServiceConfigHashes.from_parts(
            endpoint_config={"b": 2, "a": [1, 2]},
            identity_config={"speakers": 4},
            decoder_config={"rtf": 1.0},
        )
        right = LiveServiceConfigHashes.from_parts(
            endpoint_config={"a": [1, 2], "b": 2},
            identity_config={"speakers": 4},
            decoder_config={"rtf": 1.0},
        )

        self.assertEqual(left, right)
        with self.assertRaisesRegex(ValueError, "provider_manifest_hash"):
            LiveServiceDescriptor(
                source_revision="revision",
                provider_name="provider",
                provider_revision="provider-revision",
                provider_manifest_hash="not-a-digest",
                config_hashes=left,
                bounds=LiveServiceBounds(
                    max_frame_samples=1,
                    max_queue_depth=1,
                    max_retained_samples=1,
                    max_identity_speakers=1,
                    max_events=1,
                ),
                frame_samples=1,
            )

    def test_events_and_failures_are_typed_payloads(self):
        failure = LiveServiceProviderConfigFailure(
            "descriptor provider hash mismatch",
            code="descriptor_mismatch",
            detail={"expected": _digest("expected"), "actual": _digest("actual")},
        ).failure
        event = LiveServiceEvent(
            seq=0,
            session_id="session-1",
            kind="terminal_failure",
            snapshot_version=3,
            payload={"failure": failure.to_dict()},
        )

        self.assertEqual(failure.kind, LiveServiceFailureKind.PROVIDER_CONFIG)
        self.assertFalse(failure.retryable)
        self.assertEqual(event.to_dict()["payload"]["failure"]["kind"], "provider_config")


def _descriptor(*, max_queue_depth: int = 4, max_retained_samples: int = 8000) -> LiveServiceDescriptor:
    return LiveServiceDescriptor(
        source_revision="eda5e69faf0e0251383029295f7e8875a2a1a4f6",
        provider_name="deterministic-fake",
        provider_revision="test-revision",
        provider_manifest_hash=_digest("provider"),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1, "min_silence_samples": 1, "hard_cap_samples": 4000},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=max_queue_depth,
            max_retained_samples=max_retained_samples,
            max_identity_speakers=2,
            max_events=64,
            # The deployed shape: both sections declare the same cap. Leaving this `None`
            # while the endpoint policy carried one is the fixture that hid H2 for a year.
            hard_cap_samples=4000,
            stop_drain_deadline_seconds=1.0,
        ),
        frame_samples=1000,
    )


def _frame(sequence: int, samples: int = 1000, byte: bytes = b"\0") -> AudioFrame:
    return AudioFrame(sequence=sequence, pcm=byte * samples * 2, sample_count=samples)


class ScriptedSpeechProvider:
    def __init__(self, speech: tuple[bool, ...]):
        self.speech = list(speech)

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int) -> tuple[SpeechObservation, ...]:
        del frame
        return (
            SpeechObservation(
                start_sample=start_sample,
                end_sample=end_sample,
                speech_present=self.speech.pop(0),
            ),
        )


class RecordingDecoder:
    max_samples = 4000

    def __init__(self, elapsed_sec: float | None = None):
        self.calls: list[tuple[int, int]] = []
        self.elapsed_sec = elapsed_sec

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        self.calls.append((span.start_sample, span.end_sample))
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]decoded[{seconds:g}]", elapsed_sec=self.elapsed_sec)


class BlockingDecoder(RecordingDecoder):
    def __init__(self):
        super().__init__()
        self.entered = threading.Event()
        self.release = threading.Event()
        self.finished = threading.Event()

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        self.entered.set()
        if not self.release.wait(timeout=1.0):
            raise RuntimeError("blocked decoder was not released.")
        try:
            return super().transcribe_pcm(span=span, pcm=pcm)
        finally:
            self.finished.set()


class LabelingDecoder(RecordingDecoder):
    def __init__(self):
        super().__init__()
        self.labels: list[str] = []

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        self.labels.append(pcm[:1].decode("ascii"))
        return super().transcribe_pcm(span=span, pcm=pcm)


class SelectiveFailingDecoder(RecordingDecoder):
    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        if pcm.startswith(b"x"):
            raise RuntimeError("simulated canonical decoder failure.")
        return super().transcribe_pcm(span=span, pcm=pcm)


class SameTickLoop:
    def time(self) -> float:
        return 100.0


class InterleavingWorkChangedEvent(threading.Event):
    def __init__(self) -> None:
        super().__init__()
        self.clear_entered = threading.Event()
        self.set_during_clear = threading.Event()
        self.allow_clear = threading.Event()

    def clear(self) -> None:
        self.clear_entered.set()
        if not self.allow_clear.wait(timeout=1.0):
            raise RuntimeError("test did not release work_changed.clear().")
        super().clear()

    def set(self) -> None:
        if self.clear_entered.is_set() and not self.allow_clear.is_set():
            self.set_during_clear.set()
        super().set()


class InterleavingDrainWaiterSet(set):
    def __init__(self, *, runtime, state, decoder: BlockingDecoder) -> None:
        super().__init__()
        self.runtime = runtime
        self.state = state
        self.decoder = decoder
        self.armed = True
        self.worker_finished_before_registration = False

    def add(self, waiter) -> None:
        if self.armed:
            self.armed = False
            self.decoder.release.set()
            deadline = time.monotonic() + 0.25
            while time.monotonic() < deadline:
                with self.runtime._lock:
                    if not self.runtime._has_unresolved_work_locked(self.state):
                        self.worker_finished_before_registration = True
                        break
                time.sleep(0.005)
        super().add(waiter)


@dataclass
class PreparingIdentity:
    status: str = "prepared"
    reason: str | None = None
    # A preparation built against identity state the session has already moved past. It is
    # the one thing that still refuses to publish now that a non-`prepared` status commits
    # the span unattributed: a stale proposal would overwrite newer identity state, which
    # is a statement about the session rather than about who spoke.
    stale_base_version: bool = False

    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
        proposed = LiveIdentitySnapshot(
            version=base_snapshot.version + 1,
            canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            diagnostics=(("span_id", str(span.id)),),
        )
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version - 1 if self.stale_base_version else base_snapshot.version,
            proposed_snapshot=proposed,
            relabeled_transcript=f"[0][S01]stable[{seconds:g}]",
            status=self.status,
            reason=self.reason,
        )


def _runtime(
    *,
    speech: tuple[bool, ...],
    decoder: RecordingDecoder | None = None,
    identity: PreparingIdentity | None = None,
    descriptor: LiveServiceDescriptor | None = None,
    session_ids: tuple[str, ...] = ("session-1",),
    scheduler: _ManualCanonicalPumpScheduler | None = None,
    vector_journal=None,
    wall_time=None,
    monotonic_ns=None,
) -> LiveServiceRuntime:
    ids = iter(session_ids)
    return LiveServiceRuntime(
        descriptor=descriptor or _descriptor(),
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1, min_silence_samples=1, hard_cap_samples=4000)
        ),
        speech_provider_factory=lambda: ScriptedSpeechProvider(speech),
        decoder_factory=lambda: decoder or RecordingDecoder(),
        identity_preparer_factory=lambda: identity or PreparingIdentity(),
        session_id_factory=lambda: next(ids),
        _canonical_scheduler=scheduler,
        vector_journal=vector_journal,
        wall_time=wall_time,
        monotonic_ns=monotonic_ns,
    )


def _threaded_call(fn):
    done = threading.Event()
    result: dict[str, object] = {}

    def run() -> None:
        try:
            result["value"] = fn()
        except BaseException as exc:  # pragma: no cover - re-raised by the caller
            result["error"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=run)
    thread.start()
    return done, result, thread


def _threaded_result(result: dict[str, object]):
    if "error" in result:
        raise result["error"]
    return result["value"]


def test_runtime_frame_admission_queues_without_canonical_decode():
    decoder = RecordingDecoder()
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()

    first = runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    second = runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    assert first.queued_item_ids == ()
    assert second.queued_item_ids == (0,)
    assert decoder.calls == []
    assert second.snapshot.session.accepted_samples == 2000
    assert second.snapshot.session.accounted_samples == 0
    assert second.snapshot.pending_work_items == 1
    assert [event.seq for event in runtime.events(created.session_id)] == list(range(5))

    assert scheduler.run_one()
    pumped = runtime.snapshot(created.session_id)
    assert decoder.calls == [(0, 1000)]
    assert pumped.session.status == "active"
    assert pumped.session.accounted_samples == 1000
    assert pumped.pending_work_items == 0
    event_kinds = [event.kind for event in runtime.events(created.session_id)]
    assert event_kinds.index("canonical_queued") < event_kinds.index("canonical_started")
    assert event_kinds.index("canonical_started") < event_kinds.index("canonical_processed")


def test_runtime_canonical_processed_event_reports_measured_decode_rtf():
    decoder = RecordingDecoder(elapsed_sec=0.03125)
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    assert scheduler.run_one()

    processed = [event for event in runtime.events(created.session_id) if event.kind == "canonical_processed"][0]
    assert processed.payload["canonical_decode_elapsed_sec"] == 0.03125
    assert processed.payload["frozen_span_sample_count"] == 1000
    assert processed.payload["frozen_span_duration_sec"] == 1000 / LIVE_SAMPLE_RATE
    assert processed.payload["canonical_decode_rtf"] == 0.5
    assert processed.to_dict()["payload"]["canonical_decode_rtf"] == 0.5


def test_runtime_events_measure_queue_and_processing_on_one_server_clock():
    ticks = iter((10_000_000_000, 10_250_000_000, 10_650_000_000, 10_900_000_000))
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(
        speech=(True, False),
        scheduler=scheduler,
        monotonic_ns=lambda: next(ticks),
    )
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    queued = [event for event in runtime.events(created.session_id) if event.kind == "canonical_queued"][0]
    assert queued.payload["runtime_monotonic_ns"] == 10_000_000_000
    assert scheduler.run_one()

    events = runtime.events(created.session_id)
    started = [event for event in events if event.kind == "canonical_started"][0]
    processed = [event for event in events if event.kind == "canonical_processed"][0]
    assert started.payload["runtime_monotonic_ns"] == 10_250_000_000
    assert started.payload["queue_wait_ms"] == 250.0
    assert processed.payload["runtime_monotonic_ns"] == 10_650_000_000
    assert processed.payload["queue_wait_ms"] == 250.0
    assert processed.payload["canonical_processing_elapsed_ms"] == 400.0
    assert processed.payload["queued_to_processed_ms"] == 650.0

    observed_events, observed_ns = runtime._events_with_observation(created.session_id)
    assert observed_events == events
    assert observed_ns == 10_900_000_000
    assert (observed_ns - processed.payload["runtime_monotonic_ns"]) / 1_000_000 == 250.0


def test_blocked_decode_does_not_block_frame_admission_or_snapshot_reads():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(
        speech=(True, False, True),
        decoder=decoder,
        descriptor=_descriptor(max_queue_depth=2, max_retained_samples=6000),
        scheduler=scheduler,
    )
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    queued = runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert queued.queued_item_ids == (0,)
    assert decoder.entered.wait(timeout=1.0)

    snapshot_done, snapshot_result, snapshot_thread = _threaded_call(
        lambda: runtime.snapshot(created.session_id)
    )
    if not snapshot_done.wait(timeout=0.25):
        decoder.release.set()
        snapshot_thread.join(timeout=1.0)
        pytest.fail("snapshot read blocked behind canonical decode.")
    in_flight = _threaded_result(snapshot_result)
    assert in_flight.pending_work_items == 1
    assert in_flight.session.accounted_samples == 0
    event_kinds = [event.kind for event in runtime.events(created.session_id)]
    assert "canonical_started" in event_kinds
    assert "canonical_processed" not in event_kinds

    accept_done, accept_result, accept_thread = _threaded_call(
        lambda: runtime.accept_frame(created.session_id, _frame(2, byte=b"c"))
    )
    if not accept_done.wait(timeout=0.25):
        decoder.release.set()
        accept_thread.join(timeout=1.0)
        pytest.fail("frame admission blocked behind canonical decode.")
    accepted = _threaded_result(accept_result)
    assert accepted.snapshot.session.accepted_samples == 3000
    assert accepted.snapshot.session.accounted_samples == 0
    assert accepted.queued_item_ids == (1,)
    assert accepted.snapshot.pending_work_items == 2

    with pytest.raises(Exception, match="live canonical queue is full"):
        runtime.accept_frame(
            created.session_id,
            _frame(3, byte=b"d"),
            retryable_queue_backpressure=True,
        )
    assert runtime.snapshot(created.session_id).pending_work_items == 2

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)
    drained = runtime.snapshot(created.session_id)
    assert drained.session.accounted_samples == 2000
    assert drained.pending_work_items == 0


def test_impossible_multi_span_frame_fails_without_audio_admission():
    class AlternatingSpeech:
        def observe(self, *, frame, start_sample, end_sample):
            del frame
            step = (end_sample - start_sample) // 4
            return tuple(
                SpeechObservation(
                    start_sample=start_sample + index * step,
                    end_sample=start_sample + (index + 1) * step,
                    speech_present=index % 2 == 0,
                )
                for index in range(4)
            )

    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(
        speech=(),
        descriptor=_descriptor(max_queue_depth=1, max_retained_samples=8000),
        scheduler=scheduler,
    )
    created = runtime.create()
    runtime._sessions[created.session_id].coordinator.speech_provider = AlternatingSpeech()
    staged_frame = AudioFrame(sequence=0, pcm=b"a" * 8000, sample_count=4000)

    with pytest.raises(LiveServiceTransportPacingFailure) as refused:
        runtime.accept_frame(
            created.session_id,
            staged_frame,
            retryable_queue_backpressure=True,
        )

    assert refused.value.failure.code == "frame_work_exceeds_queue_capacity"
    assert refused.value.failure.retryable is False
    assert refused.value.failure.detail == {
        "queue_depth": 0,
        "required_work_items": 3,
        "max_queue_depth": 1,
    }

    snapshot = runtime.snapshot(created.session_id)
    assert snapshot.pending_work_items == 0
    assert snapshot.session.accepted_samples == 0
    assert snapshot.session.next_frame_sequence == 0
    assert snapshot.session.status == "failed"
    assert snapshot.terminal_failure == refused.value.failure


def test_manual_canonical_scheduler_is_coalesced_and_deterministic():
    scheduler = _ManualCanonicalPumpScheduler()
    calls: list[str] = []

    def first() -> None:
        calls.append("first")
        assert scheduler.in_flight
        scheduler.signal(second)

    def second() -> None:
        calls.append("second")

    scheduler.signal(first)
    scheduler.signal(first)

    assert scheduler.pending_signals == 1
    assert scheduler.run_one()
    assert calls == ["first"]
    assert scheduler.pending_signals == 1
    assert scheduler.drain() == 1
    assert calls == ["first", "second"]
    assert scheduler.pending_signals == 0
    assert not scheduler.in_flight


def test_transient_canonical_scheduler_serializes_and_exits_when_idle():
    scheduler = _TransientCanonicalPumpScheduler()
    release = threading.Event()
    entered = threading.Event()
    calls: list[str] = []

    def first() -> None:
        calls.append("first-start")
        entered.set()
        scheduler.signal(second)
        release.wait(timeout=1.0)
        calls.append("first-end")

    def second() -> None:
        calls.append("second")

    scheduler.signal(first)
    scheduler.signal(first)
    assert entered.wait(timeout=1.0)
    worker_count_while_blocked = scheduler.worker_count
    assert scheduler.in_flight
    release.set()
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)

    assert calls == ["first-start", "first-end", "second"]
    assert worker_count_while_blocked == 1
    assert scheduler.worker_count == 0


def test_ready_sessions_drain_round_robin_without_hot_session_starvation():
    scheduler = _ManualCanonicalPumpScheduler()
    decoder = LabelingDecoder()
    runtime = _runtime(
        speech=(True, False, True, False),
        decoder=decoder,
        session_ids=("hot-session", "other-session"),
        scheduler=scheduler,
    )
    hot = runtime.create()
    other = runtime.create()

    runtime.accept_frame(hot.session_id, _frame(0, byte=b"h"))
    runtime.accept_frame(hot.session_id, _frame(1, byte=b"i"))
    runtime.accept_frame(hot.session_id, _frame(2, byte=b"H"))
    runtime.accept_frame(hot.session_id, _frame(3, byte=b"I"))
    runtime.accept_frame(other.session_id, _frame(0, byte=b"o"))
    runtime.accept_frame(other.session_id, _frame(1, byte=b"p"))

    assert scheduler.run_one()

    assert decoder.labels[0] == "h"
    assert decoder.labels.index("o") < decoder.labels.index("i")
    assert runtime.snapshot(hot.session_id).session.accounted_samples == 3000
    assert runtime.snapshot(other.session_id).session.accounted_samples == 1000
    assert runtime.snapshot(hot.session_id).pending_work_items == 0
    assert runtime.snapshot(other.session_id).pending_work_items == 0


def test_runtime_scheduler_is_internal_not_a_public_pump_operation():
    scheduler = _ManualCanonicalPumpScheduler()
    runtime = _runtime(speech=(True,), scheduler=scheduler)

    assert not hasattr(runtime, "pump")
    assert not hasattr(runtime, "run_pump")
    assert not hasattr(runtime, "canonical_pump")
    assert scheduler.pending_signals == 0


def test_runtime_stop_closes_endpoint_and_drains_exact_accounting():
    decoder = RecordingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    snapshot = asyncio.run(runtime.stop(created.session_id, deadline=1.0))

    assert snapshot.session.status == "closed"
    assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 2000
    assert snapshot.pending_work_items == 0
    assert snapshot.session.pending_span_ids == ()
    assert decoder.calls == [(0, 1000), (1000, 2000)]
    event_kinds = [event.kind for event in runtime.events(created.session_id)]
    assert "canonical_processed" in event_kinds
    assert event_kinds[-1] == "session_closed"


def test_stop_with_positive_deadline_yields_while_worker_is_in_flight():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    async def exercise_stop():
        heartbeat_ticks = 0
        stopped = asyncio.Event()

        async def heartbeat() -> None:
            nonlocal heartbeat_ticks
            while not stopped.is_set():
                heartbeat_ticks += 1
                await asyncio.sleep(0.005)

        async def release_decoder() -> None:
            await asyncio.sleep(0.05)
            decoder.release.set()

        heartbeat_task = asyncio.create_task(heartbeat())
        release_task = asyncio.create_task(release_decoder())
        try:
            snapshot = await runtime.stop(created.session_id, deadline=1.0)
        finally:
            stopped.set()
            await heartbeat_task
            await release_task
        return snapshot, heartbeat_ticks

    snapshot, heartbeat_ticks = asyncio.run(exercise_stop())

    assert heartbeat_ticks >= 5
    assert snapshot.session.status == "closed"
    assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 2000
    assert snapshot.pending_work_items == 0


def test_stop_deadline_is_not_delayed_by_saturated_default_executor():
    async def exercise_stop():
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(executor)
        executor_release = threading.Event()
        occupied = loop.run_in_executor(None, executor_release.wait)

        scheduler = _TransientCanonicalPumpScheduler()
        decoder = BlockingDecoder()
        runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
        created = runtime.create()
        runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
        runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
        assert decoder.entered.wait(timeout=1.0)

        def release_later() -> None:
            time.sleep(0.02)
            decoder.release.set()
            time.sleep(0.23)
            executor_release.set()

        helper = threading.Thread(target=release_later)
        helper.start()
        started = time.monotonic()
        snapshot = None
        elapsed = None
        try:
            snapshot = await runtime.stop(created.session_id, deadline=0.10)
            elapsed = time.monotonic() - started
        finally:
            executor_release.set()
            await occupied
            helper.join(timeout=1.0)
            executor.shutdown(wait=True)
        assert snapshot is not None
        assert elapsed is not None
        return snapshot, elapsed

    snapshot, elapsed = asyncio.run(exercise_stop())

    assert snapshot.session.status == "closed"
    assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 2000
    assert elapsed < 0.20


def test_stop_positive_deadline_bounds_permanently_blocked_work():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="stop deadline expired"):
            asyncio.run(runtime.stop(created.session_id, deadline=0.10))
    finally:
        elapsed = time.monotonic() - started
        decoder.release.set()
        decoder.finished.wait(timeout=1.0)

    assert elapsed < 0.5


def test_cancelled_stop_unregisters_waiter_without_default_executor_residue():
    async def exercise_cancelled_stop():
        loop = asyncio.get_running_loop()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(executor)

        scheduler = _TransientCanonicalPumpScheduler()
        decoder = BlockingDecoder()
        runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
        created = runtime.create()
        runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
        runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
        assert decoder.entered.wait(timeout=1.0)

        stop_task = asyncio.create_task(runtime.stop(created.session_id, deadline=0.6))
        await asyncio.sleep(0.05)
        stop_task.cancel()
        try:
            await stop_task
        except asyncio.CancelledError:
            pass

        marker = loop.run_in_executor(None, time.monotonic)
        try:
            await asyncio.wait_for(marker, timeout=0.10)
        finally:
            decoder.release.set()
            executor.shutdown(wait=True)
        state = runtime._get(created.session_id)
        return state.drain_waiters

    waiters = asyncio.run(exercise_cancelled_stop())

    assert waiters == set()


def test_concurrent_stops_across_sessions_share_no_executor_waiters():
    runtime = _runtime(speech=(True,), session_ids=("session-1", "session-2", "session-3"))
    created = [runtime.create() for _ in range(3)]
    for result in created:
        runtime.accept_frame(result.session_id, _frame(0, byte=result.session_id[-1].encode("ascii")))

    async def stop_all():
        return await asyncio.gather(
            *(runtime.stop(result.session_id, deadline=1.0) for result in created)
        )

    snapshots = asyncio.run(stop_all())

    assert [snapshot.session.status for snapshot in snapshots] == ["closed", "closed", "closed"]
    assert [snapshot.pending_work_items for snapshot in snapshots] == [0, 0, 0]
    assert [snapshot.session.accounted_samples for snapshot in snapshots] == [1000, 1000, 1000]


def test_wait_for_drain_registers_and_rechecks_without_lost_wakeup():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    state = runtime._get(created.session_id)
    event = InterleavingWorkChangedEvent()
    state.work_changed = event

    def orchestrate() -> None:
        if not event.clear_entered.wait(timeout=1.0):
            decoder.release.set()
            event.allow_clear.set()
            return
        decoder.release.set()
        event.set_during_clear.wait(timeout=0.15)
        event.allow_clear.set()

    helper = threading.Thread(target=orchestrate)
    helper.start()
    try:
        snapshot = asyncio.run(runtime.stop(created.session_id, deadline=0.5))
    finally:
        decoder.release.set()
        event.allow_clear.set()
        helper.join(timeout=1.0)

    assert snapshot.session.status == "closed"
    assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 2000
    assert not event.set_during_clear.is_set()


def test_wait_for_drain_registers_new_waiter_without_lost_wakeup():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    state = runtime._get(created.session_id)
    waiters = InterleavingDrainWaiterSet(
        runtime=runtime,
        state=state,
        decoder=decoder,
    )
    state.drain_waiters = waiters

    try:
        snapshot = asyncio.run(runtime.stop(created.session_id, deadline=0.6))
    finally:
        decoder.release.set()

    assert snapshot.session.status == "closed"
    assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 2000
    assert snapshot.pending_work_items == 0
    assert not waiters.worker_finished_before_registration


@pytest.mark.parametrize("operation", ("stop", "abort"))
def test_stop_and_abort_serialize_events_with_in_flight_worker(operation: str):
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    lock_violations: list[str] = []
    original_record_event = runtime._record_event

    def record_event_while_locked(state, kind, payload):
        if not runtime._lock._is_owned():
            lock_violations.append(kind)
        original_record_event(state, kind, payload)

    runtime._record_event = record_event_while_locked
    release_timer = threading.Timer(0.02, decoder.release.set)
    release_timer.start()
    try:
        if operation == "stop":
            asyncio.run(runtime.stop(created.session_id, deadline=1.0))
        else:
            asyncio.run(runtime.abort(created.session_id, "caller cancelled"))
    finally:
        decoder.release.set()
        release_timer.cancel()
    assert decoder.finished.wait(timeout=1.0)

    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)
    events = runtime.events(created.session_id)

    assert lock_violations == []
    assert [event.seq for event in events] == list(range(len(events)))
    assert sum(event.kind == "terminal_failure" for event in events) <= 1


def test_zero_deadline_rejects_pending_work_before_decode_when_clock_has_not_advanced():
    decoder = RecordingDecoder()
    runtime = _runtime(speech=(True,), decoder=decoder)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0))

    with patch.object(runtime_module.asyncio, "get_running_loop", return_value=SameTickLoop()):
        with pytest.raises(TimeoutError, match="deadline expired"):
            asyncio.run(runtime.stop(created.session_id, deadline=0.0))

    snapshot = runtime.snapshot(created.session_id)
    assert decoder.calls == []
    assert snapshot.session.accepted_samples == 1000
    assert snapshot.session.accounted_samples == 0
    assert snapshot.pending_work_items == 1
    assert snapshot.terminal_failure is not None
    assert snapshot.terminal_failure.kind == LiveServiceFailureKind.TRANSPORT_PACING


def test_stop_timeout_fences_late_in_flight_canonical_result():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    with pytest.raises(TimeoutError, match="deadline expired"):
        asyncio.run(runtime.stop(created.session_id, deadline=0.0))

    timed_out = runtime.snapshot(created.session_id)
    assert timed_out.terminal_failure is not None
    assert timed_out.terminal_failure.kind == LiveServiceFailureKind.TRANSPORT_PACING
    assert timed_out.session.accepted_samples == 2000
    assert timed_out.session.accounted_samples == 0

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)

    fenced = runtime.snapshot(created.session_id)
    assert fenced.session.accounted_samples == 0
    assert fenced.session.committed == ()
    event_kinds = [event.kind for event in runtime.events(created.session_id)]
    assert "canonical_started" in event_kinds
    assert "canonical_processed" not in event_kinds
    assert "session_closed" not in event_kinds


def test_abort_fences_late_in_flight_canonical_result():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)

    aborted = asyncio.run(runtime.abort(created.session_id, "caller cancelled"))
    assert aborted.terminal_failure is not None
    assert aborted.terminal_failure.kind == LiveServiceFailureKind.TRANSPORT_PACING
    assert aborted.session.status == "aborted"
    assert aborted.session.accounted_samples == 0

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)

    fenced = runtime.snapshot(created.session_id)
    assert fenced.session.status == "aborted"
    assert fenced.session.accounted_samples == 0
    assert fenced.session.committed == ()
    event_kinds = [event.kind for event in runtime.events(created.session_id)]
    assert "canonical_started" in event_kinds
    assert "canonical_processed" not in event_kinds
    assert event_kinds[-1] == "session_aborted"


def test_canonical_failure_does_not_starve_sibling_session():
    scheduler = _ManualCanonicalPumpScheduler()
    decoder = SelectiveFailingDecoder()
    runtime = _runtime(
        speech=(True, False),
        decoder=decoder,
        session_ids=("bad-session", "other-session"),
        scheduler=scheduler,
    )
    bad = runtime.create()
    other = runtime.create()
    runtime.accept_frame(bad.session_id, _frame(0, byte=b"x"))
    runtime.accept_frame(bad.session_id, _frame(1, byte=b"y"))
    runtime.accept_frame(other.session_id, _frame(0, byte=b"o"))
    runtime.accept_frame(other.session_id, _frame(1, byte=b"p"))

    assert scheduler.run_one()

    bad_snapshot = runtime.snapshot(bad.session_id)
    other_snapshot = runtime.snapshot(other.session_id)
    assert bad_snapshot.terminal_failure is not None
    assert bad_snapshot.session.accounted_samples == 0
    assert other_snapshot.terminal_failure is None
    assert other_snapshot.session.accounted_samples == 1000
    assert other_snapshot.pending_work_items == 0


def test_runtime_terminal_failure_is_session_local():
    bad_identity = PreparingIdentity(stale_base_version=True)
    runtime = _runtime(
        speech=(False, False),
        identity=bad_identity,
        descriptor=_descriptor(max_queue_depth=1),
        session_ids=("bad-session", "other-session"),
    )
    bad = runtime.create()
    other = runtime.create()
    runtime.accept_frame(bad.session_id, _frame(0))

    with pytest.raises(Exception, match="atomically publish"):
        asyncio.run(runtime.stop(bad.session_id, deadline=1.0))

    bad_snapshot = runtime.snapshot(bad.session_id)
    assert isinstance(bad_snapshot.terminal_failure, LiveServiceFailureRecord)
    assert bad_snapshot.terminal_failure.kind == LiveServiceFailureKind.IDENTITY_COMMIT

    other_result = runtime.accept_frame(other.session_id, _frame(0))
    assert other_result.snapshot.terminal_failure is None
    assert other_result.snapshot.session.accepted_samples == 1000


if __name__ == "__main__":
    unittest.main()


# --------------------------------------------------------------------------------------
# ADR-0002's final sweep, from the runtime's side: which ending runs it, and where in the
# ending it runs. The correction it produces is measured on the real parts in
# `test_live_pipeline_seams`; what these two nodes pin is that the meeting's last sweep
# happens on the path a reader is still watching, and not on the path nobody can see.
# --------------------------------------------------------------------------------------


@dataclass
class FinalizingIdentity(PreparingIdentity):
    def __post_init__(self) -> None:
        self.finalized: list[LiveIdentitySnapshot] = []

    def finalize_identity(self, *, base_snapshot: LiveIdentitySnapshot) -> None:
        self.finalized.append(base_snapshot)


@dataclass
class JournalingIdentity(FinalizingIdentity):
    def journal_observations(self):
        return (
            SimpleNamespace(
                speaker_label="speaker-0001",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=3,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
            SimpleNamespace(
                speaker_label="speaker-refused",
                centroid=(float("nan"),),
                sample_seconds=1.0,
                exemplar_count=0,
                provisional=True,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        )


def test_a_clean_stop_settles_identity_after_the_drain_and_before_the_session_closes():
    """The stop response is what a reader is handed, so the correction belongs inside it.

    After the drain, because a sweep that ran with spans still in flight would be re-matching
    an unfinished meeting; before the close, because the snapshot `stop` returns is the last
    thing many readers ever fetch. A closed session is revisable anyway -- this ordering is a
    courtesy rather than a constraint, and it is asserted because nothing else would notice
    if it silently moved.
    """

    identity = FinalizingIdentity()
    runtime = _runtime(speech=(True, False), identity=identity)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    asyncio.run(runtime.stop(created.session_id, deadline=1.0))

    assert len(identity.finalized) == 1
    events = runtime.events(created.session_id)
    event_kinds = [event.kind for event in events]
    assert event_kinds[-2:] == ["identity_finalized", "session_closed"]
    # Ordering by event position would be satisfied by settling identity *after* the session
    # closed, because `session_closed` is recorded later still. The version each event was
    # stamped with is what separates the two: `LiveSession.stop` bumps on the way through, so
    # a finalize that ran before it necessarily carries a lower version than the close does.
    versions = {event.kind: event.snapshot_version for event in events}
    assert versions["identity_finalized"] < versions["session_closed"]
    # Recorded whether or not anything changed: "the last sweep found nothing" and "the last
    # sweep never ran" are opposite facts that would otherwise both read as an absence.
    payload = [event for event in runtime.events(created.session_id) if event.kind == "identity_finalized"][0].payload
    assert payload == {
        "identity_revision_version": 0,
        "identity_revision_spans": 0,
        "identity_revision_units": 0,
        "identity_revision_merges": 0,
        "identity_revision_refusals": {},
    }


def test_an_abort_does_not_sweep_a_session_no_reader_could_see():
    """An aborted session is terminal, and a terminal session is not viewable.

    A correction published to one reaches nobody, so the only thing a final sweep could add
    on the abort path is work on the one path that must do as little as possible.
    """

    identity = FinalizingIdentity()
    runtime = _runtime(speech=(True, False), identity=identity)
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    asyncio.run(runtime.abort(created.session_id, "operator"))

    assert identity.finalized == []
    assert "identity_finalized" not in [event.kind for event in runtime.events(created.session_id)]


def test_clean_stop_journals_completed_identity_and_names_unusable_speaker(tmp_path, caplog):
    from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal

    journal_path = tmp_path / "speaker-vectors.jsonl"
    identity = JournalingIdentity()
    runtime = _runtime(
        speech=(True, False),
        identity=identity,
        vector_journal=LiveVectorJournal(journal_path),
        wall_time=lambda: 1_800_000_006.0,
    )
    created = runtime.create(echo_mode="speakers")
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    stopped = asyncio.run(runtime.stop(created.session_id, deadline=1.0))

    assert stopped.session.status == "closed"
    assert json.loads(journal_path.read_text(encoding="utf-8")) == {
        "session_id": created.session_id,
        "speaker_label": "speaker-0001",
        "centroid": [0.25, 0.75],
        "sample_seconds": 2.5,
        "exemplar_count": 3,
        "provisional": False,
        "embedder_id": "wespeaker:test-revision",
        "embedder_state_sha": "ab" * 32,
        "created_at": 1_800_000_006.0,
        "echo_mode": "speakers",
    }
    assert journal_path.stat().st_mode & 0o777 == 0o600
    journal_event = [event for event in runtime.events(created.session_id) if event.kind == "vector_journal_appended"]
    assert len(journal_event) == 1
    assert journal_event[0].payload == {
        "written": 1,
        "refusals": {"speaker-refused": "centroid_non_finite"},
    }
    assert "speaker_label=speaker-refused reason=centroid_non_finite" in caplog.text


def test_journal_refuses_bad_contract_rows_without_dropping_valid_observations(tmp_path):
    from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal

    journal_path = tmp_path / "speaker-vectors.jsonl"
    result = LiveVectorJournal(journal_path).append_session(
        session_id="completed-session",
        echo_mode="headphones",
        created_at=1_800_000_007.0,
        observations=(
            SimpleNamespace(
                speaker_label="speaker-valid",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=1,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
            SimpleNamespace(
                speaker_label="speaker-bad-count",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=-1,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
            SimpleNamespace(
                speaker_label="speaker-bad-provisional",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=0,
                provisional="yes",
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
            SimpleNamespace(
                speaker_label="speaker-missing-field",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=1,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        ),
    )

    assert result.written == 1
    assert [(item.speaker_label, item.reason) for item in result.refusals] == [
        ("speaker-bad-count", "exemplar_count_invalid"),
        ("speaker-bad-provisional", "provisional_invalid"),
        ("speaker-missing-field", "provisional_missing"),
    ]
    assert json.loads(journal_path.read_text(encoding="utf-8")) == {
        "session_id": "completed-session",
        "speaker_label": "speaker-valid",
        "centroid": [0.25, 0.75],
        "sample_seconds": 2.5,
        "exemplar_count": 1,
        "provisional": False,
        "embedder_id": "wespeaker:test-revision",
        "embedder_state_sha": "ab" * 32,
        "created_at": 1_800_000_007.0,
        "echo_mode": "headphones",
    }


def test_journal_declines_an_unserializable_row_without_losing_the_other_speakers(
    tmp_path, monkeypatch
):
    """A four-speaker meeting where one row cannot be encoded keeps the other three.

    Validating field types is not enough on its own: the encode step runs after
    validation, and joining the whole batch into one payload made any encoder error
    escape `append_session`. The runtime catches that as one opaque
    `vector_journal_failed` and the entire meeting's identity evidence is gone.
    """

    from moss_transcribe_diarize.app import live_vector_journal

    def observation(label):
        return SimpleNamespace(
            speaker_label=label,
            centroid=(0.25, 0.75),
            sample_seconds=2.5,
            exemplar_count=1,
            provisional=False,
            embedder_id="wespeaker:test-revision",
            embedder_state_sha="ab" * 32,
        )

    journal_path = tmp_path / "speaker-vectors.jsonl"
    journal = live_vector_journal.LiveVectorJournal(journal_path)
    batch = (
        observation("speaker-0001"),
        observation("speaker-0002"),
        observation(b"speaker-0003"),
        observation("speaker-0004"),
    )

    result = journal.append_session(
        session_id="completed-session",
        echo_mode="headphones",
        created_at=1_800_000_011.0,
        observations=batch,
    )

    assert result.written == 3
    assert [(item.speaker_label, item.reason) for item in result.refusals] == [
        ("<invalid:bytes>", "speaker_label_invalid")
    ]
    assert [row["speaker_label"] for row in journal.read_rows()] == [
        "speaker-0001",
        "speaker-0002",
        "speaker-0004",
    ]

    # The same guarantee must hold when the encoder itself fails on a row whose
    # fields all validated -- the reason the encode is per row rather than per batch.
    real_dumps = live_vector_journal.json.dumps

    def refuse_one_speaker(row, **kwargs):
        if row["speaker_label"] == "speaker-0002":
            raise TypeError("probe: this row cannot be encoded")
        return real_dumps(row, **kwargs)

    injected_path = tmp_path / "injected.jsonl"
    injected = live_vector_journal.LiveVectorJournal(injected_path)
    monkeypatch.setattr(live_vector_journal.json, "dumps", refuse_one_speaker)
    injected_result = injected.append_session(
        session_id="completed-session",
        echo_mode="headphones",
        created_at=1_800_000_012.0,
        observations=batch[:2] + batch[3:],
    )
    monkeypatch.undo()

    assert injected_result.written == 2
    assert [(item.speaker_label, item.reason) for item in injected_result.refusals] == [
        ("speaker-0002", "row_not_serializable")
    ]
    assert [row["speaker_label"] for row in injected.read_rows()] == [
        "speaker-0001",
        "speaker-0004",
    ]


def test_journal_terminates_a_refusal_only_torn_tail_and_reader_skips_it(tmp_path):
    from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal

    journal_path = tmp_path / "speaker-vectors.jsonl"
    torn_prefix = b'{"session_id":"failed-before-fsync","speaker_label":"speaker-0001"'
    journal_path.write_bytes(torn_prefix)
    journal = LiveVectorJournal(journal_path)

    refused = journal.append_session(
        session_id="refusal-only-session",
        echo_mode="headphones",
        created_at=1_800_000_008.0,
        observations=(
            SimpleNamespace(
                speaker_label="speaker-refused",
                centroid=(),
                sample_seconds=1.0,
                exemplar_count=0,
                provisional=True,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        ),
    )

    assert refused.written == 0
    assert journal_path.read_bytes() == torn_prefix + b"\n"
    journal_path.write_bytes(torn_prefix + b"\n\n")

    written = journal.append_session(
        session_id="next-clean-session",
        echo_mode="headphones",
        created_at=1_800_000_009.0,
        observations=(
            SimpleNamespace(
                speaker_label="speaker-0002",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=2,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        ),
    )

    assert written.written == 1
    assert journal.read_rows() == (
        {
            "session_id": "next-clean-session",
            "speaker_label": "speaker-0002",
            "centroid": [0.25, 0.75],
            "sample_seconds": 2.5,
            "exemplar_count": 2,
            "provisional": False,
            "embedder_id": "wespeaker:test-revision",
            "embedder_state_sha": "ab" * 32,
            "created_at": 1_800_000_009.0,
            "echo_mode": "headphones",
        },
    )


def test_journal_truncation_race_does_not_create_a_leading_blank(tmp_path, monkeypatch):
    from moss_transcribe_diarize.app import live_vector_journal

    journal_path = tmp_path / "speaker-vectors.jsonl"
    journal_path.write_bytes(b'{"session_id":"about-to-truncate"')
    real_read = live_vector_journal.os.read

    def truncate_before_read(descriptor, size):
        os.ftruncate(descriptor, 0)
        return real_read(descriptor, size)

    monkeypatch.setattr(live_vector_journal.os, "read", truncate_before_read)
    result = live_vector_journal.LiveVectorJournal(journal_path).append_session(
        session_id="next-clean-session",
        echo_mode="headphones",
        created_at=1_800_000_010.0,
        observations=(
            SimpleNamespace(
                speaker_label="speaker-0003",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=2,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        ),
    )

    journal_bytes = journal_path.read_bytes()

    assert result.written == 1
    assert journal_bytes.startswith(b"{")
    assert json.loads(journal_bytes)["session_id"] == "next-clean-session"


def test_declared_journal_repairs_preexisting_loose_directory_and_file(tmp_path):
    from moss_transcribe_diarize.app.live_vector_journal import (
        JOURNAL_DIRECTORY_MODE,
        JOURNAL_FILE_MODE,
        LiveVectorJournal,
    )

    directory = tmp_path / "private-journal"
    directory.mkdir()
    os.chmod(directory, 0o777)
    journal_path = directory / "speaker-vectors.jsonl"
    journal_path.write_text('{"preexisting":true}\n', encoding="utf-8")
    os.chmod(journal_path, 0o644)

    journal = LiveVectorJournal.declared(
        journal_path,
        checkout_root=tmp_path / "checkout",
    )
    assert directory.stat().st_mode & 0o777 == JOURNAL_DIRECTORY_MODE
    assert journal_path.stat().st_mode & 0o777 == JOURNAL_FILE_MODE

    result = journal.append_session(
        session_id="completed-session",
        echo_mode="headphones",
        created_at=1_800_000_007.0,
        observations=(
            SimpleNamespace(
                speaker_label="speaker-0002",
                centroid=(0.25, 0.75),
                sample_seconds=2.5,
                exemplar_count=1,
                provisional=False,
                embedder_id="wespeaker:test-revision",
                embedder_state_sha="ab" * 32,
            ),
        ),
    )

    rows = journal_path.read_text(encoding="utf-8").splitlines()

    assert result.written == 1
    assert journal_path.stat().st_mode & 0o777 == JOURNAL_FILE_MODE
    assert json.loads(rows[0]) == {"preexisting": True}
    assert json.loads(rows[1])["session_id"] == "completed-session"


def test_declared_journal_tightens_a_peer_writable_ancestor_it_owns(tmp_path):
    """A 0775 ancestor this service created itself is repaired, not made fatal.

    Releases before this one built the chain with `mkdir(parents=True)`, which leaves
    every intermediate directory at the process umask -- 0775 under a umask of 002.
    Refusing that outright bricks `--live` startup on exactly the hosts that ran the
    older code, because `web_cli` builds the journal before the app exists.
    """

    from moss_transcribe_diarize.app.live_vector_journal import (
        JOURNAL_DIRECTORY_MODE,
        LiveVectorJournal,
    )

    loose_ancestor = tmp_path / "loose-ancestor"
    loose_ancestor.mkdir()
    os.chmod(loose_ancestor, 0o777)
    journal_path = loose_ancestor / "new-journal" / "speaker-vectors.jsonl"

    journal = LiveVectorJournal.declared(journal_path, checkout_root=tmp_path / "checkout")

    assert loose_ancestor.stat().st_mode & 0o777 == 0o755
    assert journal.path.parent.stat().st_mode & 0o777 == JOURNAL_DIRECTORY_MODE


def test_declared_journal_refuses_an_ancestor_it_cannot_make_private(tmp_path, monkeypatch):
    """An ancestor owned by another principal is refused and left untouched.

    That principal can rename a component out from under the journal, and this
    process cannot chmod what it does not own -- so there is nothing to repair and
    the only safe answer is to refuse. `geteuid` is redirected because a test
    cannot create a directory owned by another user without privilege.
    """

    from moss_transcribe_diarize.app import live_vector_journal

    loose_ancestor = tmp_path / "loose-ancestor"
    loose_ancestor.mkdir()
    os.chmod(loose_ancestor, 0o777)
    journal_path = loose_ancestor / "new-journal" / "speaker-vectors.jsonl"
    foreign_uid = os.geteuid() + 1
    monkeypatch.setattr(live_vector_journal.os, "geteuid", lambda: foreign_uid)

    with pytest.raises(ValueError, match="could not be made private"):
        live_vector_journal.LiveVectorJournal.declared(
            journal_path, checkout_root=tmp_path / "checkout"
        )

    assert loose_ancestor.stat().st_mode & 0o777 == 0o777
    assert not journal_path.parent.exists()


def test_declared_journal_refuses_a_filesystem_that_ignores_directory_modes(tmp_path, monkeypatch):
    """The private mode is asserted as a postcondition, not assumed from chmod."""

    from moss_transcribe_diarize.app import live_vector_journal

    loose_ancestor = tmp_path / "loose-ancestor"
    loose_ancestor.mkdir()
    os.chmod(loose_ancestor, 0o777)
    journal_path = loose_ancestor / "new-journal" / "speaker-vectors.jsonl"
    monkeypatch.setattr(live_vector_journal.os, "chmod", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="could not be made private"):
        live_vector_journal.LiveVectorJournal.declared(
            journal_path, checkout_root=tmp_path / "checkout"
        )


def test_declared_journal_creates_private_intermediate_directories(tmp_path):
    from moss_transcribe_diarize.app.live_vector_journal import (
        JOURNAL_DIRECTORY_MODE,
        LiveVectorJournal,
    )

    root = tmp_path / "private-root"
    root.mkdir(mode=JOURNAL_DIRECTORY_MODE)
    intermediate = root / "intermediate"
    # Pin the umask: under a umask of 0o077 a plain mkdir would land on 0700 by
    # accident and this assertion would hold with the enforcement deleted.
    previous_umask = os.umask(0o022)
    try:
        journal = LiveVectorJournal.declared(
            intermediate / "live" / "speaker-vectors.jsonl",
            checkout_root=tmp_path / "checkout",
        )
    finally:
        os.umask(previous_umask)

    assert intermediate.stat().st_mode & 0o777 == JOURNAL_DIRECTORY_MODE
    assert journal.path.parent.stat().st_mode & 0o777 == JOURNAL_DIRECTORY_MODE


def test_web_cli_journal_survives_the_umask_masked_chain_an_earlier_release_left(tmp_path):
    """The real route: `web_cli._live_vector_journal` must open the chain it created.

    This is the caller that a refusal would take down -- it runs before the app is
    constructed, so a `ValueError` here is a startup outage rather than a degraded
    session.
    """

    from types import SimpleNamespace as _Args

    from moss_transcribe_diarize.app.live_vector_journal import (
        JOURNAL_DIRECTORY_MODE,
        JOURNAL_FILE_MODE,
    )
    from moss_transcribe_diarize.app.web_cli import _live_vector_journal

    data_root = tmp_path / "share" / "moss-transcribe-diarize"
    leaf = data_root / "live"
    leaf.mkdir(parents=True)
    journal_path = leaf / "speaker-vectors.jsonl"
    journal_path.write_text('{"preexisting":true}\n', encoding="utf-8")
    os.chmod(journal_path, 0o644)
    os.chmod(data_root, 0o775)

    journal = _live_vector_journal(
        _Args(live=True, live_vector_journal_path=str(journal_path)),
        checkout_root=tmp_path / "checkout",
    )

    assert journal.path == journal_path.resolve()
    assert data_root.stat().st_mode & 0o777 == 0o755
    assert leaf.stat().st_mode & 0o777 == JOURNAL_DIRECTORY_MODE
    assert journal_path.stat().st_mode & 0o777 == JOURNAL_FILE_MODE


def test_journaling_session_accepts_a_bodyless_create_and_records_it_as_unspecified(tmp_path):
    """A client that sends no echo choice must still get a session.

    This previously asserted the opposite -- that journaling made `echo_mode` mandatory.
    That contract was a total live-capture outage: `echo_mode` is a browser-preflight
    concept from an unbuilt page, and no client that exists sends it (the shipping macOS
    capture app posts no body at all), so every `POST /api/live/sessions` returned 400 in
    the default `--live` deployment. Journaling an honest "unspecified" is strictly better
    than refusing the meeting.
    """
    from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal

    def journaling_runtime(name):
        return _runtime(
            speech=(),
            vector_journal=LiveVectorJournal(tmp_path / f"{name}.jsonl"),
        )

    runtime = journaling_runtime("bodyless")
    created = runtime.create()
    assert created.session_id
    assert runtime._sessions[created.session_id].echo_mode == "unspecified"

    # An explicitly supplied value is still validated, so a real preflight cannot smuggle
    # an unknown mode past the journal.
    assert journaling_runtime("explicit").create(echo_mode="headphones").session_id
    with pytest.raises(ValueError, match="echo_mode must be headphones or speakers"):
        journaling_runtime("invalid").create(echo_mode="bogus")


def test_abort_never_writes_completed_identity_observations(tmp_path):
    from moss_transcribe_diarize.app.live_vector_journal import LiveVectorJournal

    journal_path = tmp_path / "speaker-vectors.jsonl"
    identity = JournalingIdentity()
    runtime = _runtime(
        speech=(True, False),
        identity=identity,
        vector_journal=LiveVectorJournal(journal_path),
    )
    created = runtime.create(echo_mode="headphones")
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))

    asyncio.run(runtime.abort(created.session_id, "operator"))

    assert not journal_path.exists()
    assert "vector_journal_appended" not in [event.kind for event in runtime.events(created.session_id)]


def _runtime_driven_to_terminal_failure() -> tuple[LiveServiceRuntime, str, int]:
    """A session killed the way a provider kills one: mid-meeting, with no clean stop.

    Retention backpressure is used because it is the cheapest deterministic path onto
    `_fail` that never asks the session object to transition -- which is the property
    under test. `stop(deadline=0)` would not do: `LiveSession.stop` bumps the version on
    its way to "closing", so it hides the gap this test exists to hold open.
    """

    runtime = _runtime(
        speech=(True, False, True, False),
        descriptor=_descriptor(max_retained_samples=2000),
    )
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0))
    runtime.accept_frame(created.session_id, _frame(1))
    version_the_reader_holds = runtime.snapshot(created.session_id).session.version
    with pytest.raises(Exception):
        runtime.accept_frame(created.session_id, _frame(2))
    return runtime, created.session_id, version_the_reader_holds


def test_a_terminal_failure_reaches_a_reader_that_already_holds_the_current_version():
    """A dead meeting must not hide behind `since_version`.

    `_fail` fences the session on the runtime and never asks the session object -- which
    owns `version` -- to transition, so the version a caught-up reader holds does not move
    when the meeting dies. A reader polling `since_version=<what it last rendered>` was
    therefore told "unchanged" for the rest of the meeting: it showed "active" beside a
    frozen transcript and kept polling a session that was already over. Projecting the
    status onto the snapshot body is not enough on its own, because the body is never sent.
    """

    runtime, session_id, cursor = _runtime_driven_to_terminal_failure()

    fenced = runtime.snapshot(session_id)
    assert fenced.terminal_failure is not None
    # The premise: nothing bumped the counter the gate compares against.
    assert fenced.session.version == cursor

    delivered = runtime.snapshot(session_id, since_version=cursor)
    assert delivered is not None, "the version gate withheld the end of the meeting"
    assert delivered.session.status == "failed"
    assert delivered.session.failure_reason
    assert delivered.terminal_failure is not None
    # And it keeps being delivered: a reader that polled once more must not be told
    # "unchanged" on the read it would have used to stop.
    assert runtime.snapshot(session_id, since_version=delivered.session.version) is not None


def test_a_healthy_session_still_answers_unchanged_to_a_caught_up_reader():
    """The bypass above is scoped to terminality, not a blanket removal of the gate."""

    runtime = _runtime(speech=(True,))
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0))
    cursor = runtime.snapshot(created.session_id).session.version

    assert runtime.snapshot(created.session_id, since_version=cursor) is None
    assert runtime.snapshot(created.session_id, since_version=cursor - 1) is not None


def test_a_terminal_failure_does_not_relabel_a_session_that_already_ended():
    """A teardown that lands after a clean close must not rewrite how the meeting ended.

    `abort` on an already-closed session records a runtime terminal failure -- that is the
    helper-lease-expiry path, which aborts the mono runtime after the fact -- while the
    session object correctly stays "closed". Projecting "failed" over it would tell an
    operator a meeting that finished cleanly had died.
    """

    runtime = _runtime(speech=(True, False))
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0))
    runtime.accept_frame(created.session_id, _frame(1))
    closed = asyncio.run(runtime.stop(created.session_id, deadline=1.0))
    assert closed.session.status == "closed"
    assert closed.terminal_failure is None

    late = asyncio.run(runtime.abort(created.session_id, "helper_lease_expired"))

    assert late.terminal_failure is not None, "the late teardown is still recorded"
    assert late.session.status == "closed"
    assert runtime.snapshot(created.session_id).session.status == "closed"


def test_events_accepts_the_cursor_before_the_first_event_and_refuses_anything_lower():
    """`/events` is inclusive, so "nothing rendered yet" needs a cursor below seq 0.

    A reader that starts at 0 asks for `seq >= 0` and then has to discard seq 0 as
    already-seen, so `session_created` is fetched and thrown away for the life of the
    session and never reaches the reader at all. -1 is the one cursor that means "no
    event rendered"; -2 and below are still nonsense and must be refused rather than
    silently treated as 0.
    """

    runtime = _runtime(speech=(True,))
    created = runtime.create()

    assert [event.seq for event in runtime.events(created.session_id, since_seq=-1)] == [0]
    assert [event.kind for event in runtime.events(created.session_id, since_seq=-1)] == ["session_created"]
    # Inclusive: a reader that has rendered seq 0 re-fetches it and must filter it itself.
    assert [event.seq for event in runtime.events(created.session_id, since_seq=0)] == [0]
    with pytest.raises(ValueError, match="at least -1"):
        runtime.events(created.session_id, since_seq=-2)
