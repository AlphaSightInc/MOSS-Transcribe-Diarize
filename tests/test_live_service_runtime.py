from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import inspect
import threading
import time
import unittest
from dataclasses import dataclass
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

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)
    drained = runtime.snapshot(created.session_id)
    assert drained.session.accounted_samples == 2000
    assert drained.pending_work_items == 0


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
