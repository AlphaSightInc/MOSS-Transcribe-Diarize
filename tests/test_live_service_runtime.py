from __future__ import annotations

import asyncio
import concurrent.futures
import dataclasses
import inspect
import threading
import time
import unittest
from dataclasses import dataclass
from types import SimpleNamespace

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
from moss_transcribe_diarize.app.live_session import (
    AudioFrame,
    FrozenSpan,
    LIVE_SAMPLE_RATE,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSessionClosed,
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


def test_production_canonical_topology_stays_one_serial_pump_across_sessions():
    decoder = BlockingDecoder()
    runtime = _runtime(
        speech=(True, False),
        decoder=decoder,
        session_ids=("meeting-one", "meeting-two"),
    )
    first = runtime.create()
    second = runtime.create()

    runtime.accept_frame(first.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(first.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1)
    runtime.accept_frame(second.session_id, _frame(0, byte=b"c"))
    runtime.accept_frame(second.session_id, _frame(1, byte=b"d"))

    # The shared canonical scheduler has one worker. The dispatch gate adds a separate
    # background lane; it deliberately does not turn production into two Live pumps.
    assert runtime._canonical_scheduler.worker_count == 1
    assert not any(
        event.kind == "canonical_started"
        for event in runtime.events(second.session_id)
    )

    decoder.release.set()
    deadline = time.monotonic() + 1
    while runtime.snapshot(second.session_id).pending_work_items and time.monotonic() < deadline:
        time.sleep(0.001)

    assert runtime.snapshot(first.session_id).pending_work_items == 0
    assert runtime.snapshot(second.session_id).pending_work_items == 0
    assert decoder.calls == [(0, 1000), (0, 1000)]


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
    assert event_kinds.index("stop_requested") < event_kinds.index("session_closed")
    events = runtime.events(created.session_id)
    timestamps = [event.payload["runtime_monotonic_ns"] for event in events
                  if event.kind in {"stop_requested", "session_closed"}]
    assert timestamps == sorted(timestamps)
    assert all(value > 0 for value in timestamps)


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


def test_zero_deadline_leaves_queued_tail_resumable():
    decoder = RecordingDecoder()
    runtime = _runtime(speech=(True,), decoder=decoder, scheduler=_ManualCanonicalPumpScheduler())
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0))

    with pytest.raises(TimeoutError, match="deadline expired"):
        asyncio.run(runtime.stop(created.session_id, deadline=0.0))

    snapshot = runtime.snapshot(created.session_id)
    assert decoder.calls == []
    assert snapshot.session.accepted_samples == 1000
    assert snapshot.session.accounted_samples == 0
    assert snapshot.pending_work_items == 1
    assert snapshot.terminal_failure is None


def test_stop_timeout_preserves_late_in_flight_canonical_result():
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
    assert timed_out.terminal_failure is None
    assert timed_out.session.accepted_samples == 2000
    assert timed_out.session.accounted_samples == 0

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)

    fenced = runtime.snapshot(created.session_id)
    assert fenced.session.accounted_samples == 2000
    assert fenced.session.committed
    event_kinds = [event.kind for event in runtime.events(created.session_id)]
    assert "canonical_started" in event_kinds
    assert "canonical_processed" in event_kinds
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


def test_abort_releases_terminal_owners_only_after_the_in_flight_reader_finishes():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    base = _descriptor(max_queue_depth=2, max_retained_samples=6000)
    descriptor = dataclasses.replace(
        base,
        bounds=dataclasses.replace(base.bounds, max_tape_bytes=12_000),
    )
    runtime = _runtime(
        speech=(True, False),
        decoder=decoder,
        descriptor=descriptor,
        scheduler=scheduler,
    )
    created = runtime.create()
    runtime.accept_frame(created.session_id, _frame(0, byte=b"a"))
    runtime.accept_frame(created.session_id, _frame(1, byte=b"b"))
    assert decoder.entered.wait(timeout=1.0)
    state = runtime._sessions[created.session_id]
    releases = 0
    original_release = state.coordinator.release_finalized_identity

    def observe_release() -> None:
        nonlocal releases
        releases += 1
        original_release()

    state.coordinator.release_finalized_identity = observe_release
    assert state.coordinator.tape_accounting().retained_bytes == 4000

    asyncio.run(runtime.abort(created.session_id, "caller cancelled"))

    assert state.coordinator.tape_accounting().retained_bytes == 4000
    assert releases == 0
    assert "session_tape_released" not in {
        event.kind for event in runtime.events(created.session_id)
    }

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while scheduler.worker_count and time.monotonic() < deadline:
        time.sleep(0.001)

    assert state.coordinator.tape_accounting().retained_bytes == 0
    assert releases == 1
    events = runtime.events(created.session_id)
    kinds = [event.kind for event in events]
    assert kinds.index("session_aborted") < kinds.index("session_tape_released")
    assert "canonical_processed" not in kinds


def test_abort_discards_only_the_target_session_queued_live_work_and_reconciles_depths():
    scheduler = _TransientCanonicalPumpScheduler()
    decoder = BlockingDecoder()
    runtime = _runtime(
        speech=(True, False),
        decoder=decoder,
        session_ids=("target-session", "peer-session"),
        scheduler=scheduler,
    )
    target = runtime.create()
    peer = runtime.create()
    runtime.accept_frame(target.session_id, _frame(0, byte=b"t"))
    runtime.accept_frame(target.session_id, _frame(1, byte=b"t"))
    assert decoder.entered.wait(timeout=1.0)

    with runtime._lock:
        target_state = runtime._sessions[target.session_id]
        held_timing_ids = set(target_state.canonical_timing)
        target_state.arbiter.submit_batch(key="unrelated-batch", payload={"kind": "batch"})
        canonical = target_state.arbiter.submit_live_canonical(
            key=f"{target.session_id}:queued-canonical",
            payload={"kind": "canonical"},
        )
        runtime._record_canonical_queued(target_state, canonical.item_id)
        refinement = target_state.arbiter.submit_live_refinement(
            coalesce_key=f"{target.session_id}:queued-refinement",
            payload={"kind": "refinement"},
        )
        target_state.rolling_timing[refinement.item_id] = SimpleNamespace(
            queued_ns=runtime._monotonic_ns(),
            started_ns=None,
            window_index=7,
            start_sample=0,
            end_sample=1000,
        )
        target_state.arbiter.submit_live_provisional(
            coalesce_key=f"{target.session_id}:queued-provisional",
            payload={"kind": "provisional"},
        )
        target_before = target_state.arbiter.snapshot()

    runtime.accept_frame(peer.session_id, _frame(0, byte=b"p"))
    runtime.accept_frame(peer.session_id, _frame(1, byte=b"p"))
    aggregate_before = runtime._operator_queue_snapshot()
    assert (
        target_before.live_canonical,
        target_before.live_refinement,
        target_before.live_provisional,
    ) == (1, 1, 1)
    assert (
        aggregate_before["live_canonical"],
        aggregate_before["live_refinement"],
        aggregate_before["live_provisional"],
    ) == (2, 1, 1)
    assert aggregate_before["batch"] == 1

    runtime._fence_session(target.session_id, "interrupted_by_operator")

    with runtime._lock:
        target_state = runtime._sessions[target.session_id]
        target_after = target_state.arbiter.snapshot()
        assert set(target_state.canonical_timing) == held_timing_ids
        assert target_state.rolling_timing == {}
    aggregate_after = runtime._operator_queue_snapshot()
    assert (
        target_after.live_canonical,
        target_after.live_refinement,
        target_after.live_provisional,
    ) == (0, 0, 0)
    assert (
        aggregate_after["live_canonical"],
        aggregate_after["live_refinement"],
        aggregate_after["live_provisional"],
    ) == (1, 0, 0)
    assert aggregate_after["batch"] == 1
    fenced = runtime.snapshot(target.session_id)
    assert fenced.terminal_failure is not None
    assert fenced.terminal_failure.code == "aborted"
    events = runtime.events(target.session_id)
    assert [
        event.payload
        for event in events
        if event.kind == "canonical_discarded"
    ] == [
        {
            "item_id": canonical.item_id,
            "reason": "session_terminal",
            "span_count": 1,
        }
    ]
    assert canonical.item_id not in {
        event.payload["item_id"] for event in events if event.kind == "canonical_started"
    }
    refinement_terminal = [
        event
        for event in events
        if event.kind == "rolling_decode_completed"
        and event.payload["outcome"] == "session_terminal"
    ]
    assert len(refinement_terminal) == 1
    assert refinement_terminal[0].payload["item_id"] == refinement.item_id
    assert refinement_terminal[0].payload["window_index"] == 7

    aborted = asyncio.run(runtime.abort(target.session_id, "interrupted_by_operator"))
    assert aborted.session.status == "aborted"

    decoder.release.set()
    assert decoder.finished.wait(timeout=1.0)
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        peer_snapshot = runtime.snapshot(peer.session_id)
        if peer_snapshot.session.accounted_samples == 1000:
            break
        time.sleep(0.001)
    else:  # pragma: no cover - the assertion above owns the timeout
        raise AssertionError("peer canonical work did not complete")

    target_snapshot = runtime.snapshot(target.session_id)
    with runtime._lock:
        assert runtime._sessions[target.session_id].canonical_timing == {}
    before_repeat = runtime._operator_queue_snapshot()
    repeated = asyncio.run(runtime.abort(target.session_id, "interrupted_by_operator"))
    assert repeated.session.status == "aborted"
    assert runtime._operator_queue_snapshot() == before_repeat
    assert target_snapshot.session.accounted_samples == 0
    assert target_snapshot.session.committed == ()
    assert peer_snapshot.session.accounted_samples == 1000


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


def test_canonical_preview_requires_current_epoch_and_next_frozen_prefix():
    runtime = _runtime(speech=(True, True, True), scheduler=_ManualCanonicalPumpScheduler())
    created = runtime.create()
    for index in range(3):
        runtime.accept_frame(created.session_id, _frame(index))
    state = runtime._sessions[created.session_id]
    with runtime._lock:
        first = state.session.freeze_until(1000, reason="test")
        second = state.session.freeze_until(2000, reason="test")
    original_version = state.session.snapshot().version
    for invalid in (second, dataclasses.replace(first, epoch=first.epoch + 1),
                    dataclasses.replace(first, start_sample=1)):
        runtime._publish_canonical_preview(state, invalid, "[0][S01]future[0.01]")
        assert state.session.snapshot().version == original_version
        assert state.session.snapshot().provisional is None
    runtime._publish_canonical_preview(state, first, "[0][S01]first[0.01][0.02][S02]second[0.03]")
    assert state.session.snapshot().provisional.transcript == "[0][S00]first[0.01][0.02][S00]second[0.03]"
    assert state.session.snapshot().identity_snapshot.canonical_speakers == ()
    asyncio.run(runtime.abort(created.session_id, reason="test abort"))
    version = state.session.snapshot().version
    runtime._publish_canonical_preview(state, first, "[0][S01]late[0.01]")
    assert state.session.snapshot().version == version
    assert state.session.snapshot().provisional is None


@pytest.mark.parametrize('ending', ['retry', 'automatic', 'abort', 'failure'])
def test_expired_stop_keeps_server_drain_alive(ending):
    async def exercise():
        scheduler = _TransientCanonicalPumpScheduler()
        decoder = BlockingDecoder()
        if ending == 'failure':
            original_decode = decoder.transcribe_pcm
            def fail_after_release(**kwargs):
                original_decode(**kwargs)
                raise RuntimeError('genuine provider failure after wait expired')
            decoder.transcribe_pcm = fail_after_release
        runtime = _runtime(speech=(True, False), decoder=decoder, scheduler=scheduler)
        created = runtime.create()
        runtime.accept_frame(created.session_id, _frame(0))
        runtime.accept_frame(created.session_id, _frame(1))
        assert decoder.entered.wait(timeout=1)
        try:
            with pytest.raises(TimeoutError, match='stop deadline expired'):
                await runtime.stop(created.session_id, deadline=0.01)
            pending = runtime.snapshot(created.session_id)
            assert pending.terminal_failure is None
            assert pending.session.status in {'active', 'closing'}
            with pytest.raises(LiveSessionClosed, match='stopping'):
                runtime.accept_frame(created.session_id, _frame(2))
            assert runtime.snapshot(created.session_id).terminal_failure is None
            if ending == 'abort':
                await runtime.abort(created.session_id, 'operator aborted while stopping')
            decoder.release.set()
            if ending == 'retry':
                await runtime.stop(created.session_id, deadline=1)
            for _ in range(200):
                snapshot = runtime.snapshot(created.session_id)
                if not scheduler.worker_count and snapshot.session.status in {'closed', 'aborted', 'failed'}:
                    break
                await asyncio.sleep(0.005)
            if ending == 'failure':
                assert snapshot.session.status == 'failed'
                assert 'genuine provider failure' in snapshot.terminal_failure.message
            elif ending == 'abort':
                assert snapshot.session.status == 'aborted'
                assert snapshot.session.accounted_samples == 0
                assert not any(e.kind in {'canonical_processed', 'session_closed'} for e in runtime.events(created.session_id))
            else:
                assert snapshot.session.status == 'closed'
                assert snapshot.session.accepted_samples == snapshot.session.accounted_samples == 2000
                assert sum(e.kind == 'session_closed' for e in runtime.events(created.session_id)) == 1
                previews = [e.payload['span_id'] for e in runtime.events(created.session_id) if e.kind == 'canonical_preview']
                assert len(previews) == len(set(previews))
                assert snapshot.terminal_failure is None
        finally:
            decoder.release.set()
    asyncio.run(exercise())
