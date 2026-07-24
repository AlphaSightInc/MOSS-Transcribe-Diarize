from __future__ import annotations

import asyncio
import dataclasses
import threading
import time
import unittest
from dataclasses import dataclass

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
            hard_cap_samples=None,
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

    def __init__(self):
        self.calls: list[tuple[int, int]] = []

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        self.calls.append((span.start_sample, span.end_sample))
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]decoded[{seconds:g}]")


class LabelingDecoder(RecordingDecoder):
    def __init__(self):
        super().__init__()
        self.labels: list[str] = []

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        self.labels.append(pcm[:1].decode("ascii"))
        return super().transcribe_pcm(span=span, pcm=pcm)


@dataclass
class PreparingIdentity:
    status: str = "prepared"
    reason: str | None = None

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
            base_snapshot_version=base_snapshot.version,
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


def test_runtime_terminal_failure_is_session_local():
    bad_identity = PreparingIdentity(status="abstain", reason="ambiguous_identity")
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
