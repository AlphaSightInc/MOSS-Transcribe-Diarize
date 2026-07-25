from __future__ import annotations

import base64
import importlib.util
import tempfile
import unittest
from dataclasses import dataclass

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.live_session import AudioFrame, FrozenSpan, LiveIdentityPreparation, LiveIdentitySnapshot


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


def frame_payload(sequence: int, samples: int, *, sample_rate: int = LIVE_SAMPLE_RATE) -> dict:
    return {
        "sequence": sequence,
        "pcm_base64": base64.b64encode(b"\0" * samples * 2).decode("ascii"),
        "sample_count": samples,
        "sample_rate": sample_rate,
    }


def v2_frame_payload(sequence: int, samples: int, *, lane: str = "system", sample_rate: int = LIVE_SAMPLE_RATE) -> dict:
    return frame_payload(sequence, samples, sample_rate=sample_rate) | {
        "lane": lane,
        "capture_timestamp_ns": 123,
        "device_epoch": 0,
        "silent": False,
        "discontinuity": False,
    }


def _digest(label: str) -> str:
    return hash_config({"label": label})


class ApiSpeechProvider:
    def __init__(self, speech: tuple[bool, ...]):
        self.speech = list(speech)

    def observe(self, *, frame: AudioFrame, start_sample: int, end_sample: int) -> tuple[SpeechObservation, ...]:
        del frame
        speech_present = self.speech.pop(0) if self.speech else False
        return (SpeechObservation(start_sample=start_sample, end_sample=end_sample, speech_present=speech_present),)


class ApiDecoder:
    max_samples = 4000

    def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
        del pcm
        seconds = span.sample_count / LIVE_SAMPLE_RATE
        return InferenceTranscript(f"[0][S01]decoded[{seconds:g}]")


@dataclass
class ApiIdentity:
    def prepare(
        self,
        *,
        span: FrozenSpan,
        pcm: bytes,
        transcript: str,
        base_snapshot: LiveIdentitySnapshot,
    ) -> LiveIdentityPreparation:
        del pcm, transcript
        return LiveIdentityPreparation(
            span_id=span.id,
            epoch=span.epoch,
            start_sample=span.start_sample,
            end_sample=span.end_sample,
            base_snapshot_version=base_snapshot.version,
            proposed_snapshot=LiveIdentitySnapshot(
                version=base_snapshot.version + 1,
                canonical_speakers=base_snapshot.canonical_speakers or ("speaker-0001",),
            ),
            relabeled_transcript=f"[0][S01]stable[{span.sample_count / LIVE_SAMPLE_RATE:g}]",
        )


def make_live_runtime(
    *,
    max_retained_samples: int = 8,
    speech: tuple[bool, ...] = (),
    session_id: str = "api-session",
) -> LiveServiceRuntime:
    descriptor = LiveServiceDescriptor(
        source_revision="eda5e69faf0e0251383029295f7e8875a2a1a4f6",
        provider_name="api-fake",
        provider_revision="test-revision",
        provider_manifest_hash=_digest("provider"),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={"min_speech_samples": 1, "min_silence_samples": 1, "hard_cap_samples": 4000},
            identity_config={"max_speakers": 2},
            decoder_config={"max_samples": 4000},
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=LIVE_SAMPLE_RATE,
            max_queue_depth=2,
            max_retained_samples=max_retained_samples,
            max_identity_speakers=2,
            max_events=64,
        ),
        frame_samples=1000,
    )
    ids = iter((session_id,))
    return LiveServiceRuntime(
        descriptor=descriptor,
        endpoint_policy_factory=lambda: EndpointPolicy(
            EndpointPolicyConfig(min_speech_samples=1, min_silence_samples=1, hard_cap_samples=4000)
        ),
        speech_provider_factory=lambda: ApiSpeechProvider(speech),
        decoder_factory=ApiDecoder,
        identity_preparer_factory=ApiIdentity,
        session_id_factory=lambda: next(ids),
    )


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi is not installed")
class LiveApiTest(unittest.TestCase):
    def test_live_routes_are_absent_by_default_and_runtime_is_unchanged(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir)
            client = TestClient(app)

            self.assertEqual(client.post("/api/live/sessions").status_code, 404)
            runtime = client.get("/api/runtime")
            self.assertEqual(runtime.status_code, 200)
            self.assertNotIn("live", runtime.json())

    def test_live_enablement_requires_explicit_runtime_factory(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, "live_runtime_factory is required"):
                create_app(model_path="fake-model", runs_dir=tmpdir, live_enabled=True)

    def test_live_routes_are_runtime_backed_with_descriptor_events_and_backpressure(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=4),
            )
            client = TestClient(app)

            descriptor = client.get("/api/live/descriptor")
            self.assertEqual(descriptor.status_code, 200)
            self.assertEqual(descriptor.json()["descriptor"]["provider_name"], "api-fake")
            self.assertEqual(descriptor.json()["descriptor"]["live_protocol"]["protocol"], "moss-live-service.v2")
            self.assertEqual(descriptor.json()["descriptor"]["live_protocol"]["min_protocol_version"], 2)
            self.assertFalse(descriptor.json()["descriptor"]["live_protocol"]["capabilities"]["binary"])

            negotiated = client.get(
                "/api/live/descriptor?client_min_protocol_version=1&client_max_protocol_version=2"
            )
            self.assertEqual(negotiated.status_code, 200)
            self.assertEqual(negotiated.json()["negotiation"]["selected_protocol_version"], 2)

            obsolete = client.get(
                "/api/live/descriptor?client_min_protocol_version=1&client_max_protocol_version=1"
            )
            self.assertEqual(obsolete.status_code, 426)
            self.assertEqual(obsolete.json()["failure"]["required_min_protocol_version"], 2)

            created = client.post("/api/live/sessions")
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["id"]
            self.assertFalse(hasattr(app.state.manager, "live_runtime"))
            self.assertIsNotNone(app.state.live_runtime.snapshot(session_id))

            ack = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 2))
            self.assertEqual(ack.status_code, 200)
            self.assertEqual(
                ack.json()["ack"],
                {
                    "sequence": 0,
                    "start_sample": 0,
                    "end_sample": 2,
                    "accepted_samples": 2,
                    "retained_samples": 2,
                    "frozen_span_ids": [],
                },
            )

            accepted = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(1, 2))
            self.assertEqual(accepted.status_code, 200)
            backpressure = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(2, 1))
            self.assertEqual(backpressure.status_code, 429)
            self.assertEqual(backpressure.json()["snapshot"]["session"]["accepted_samples"], 4)

            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot?since_version=0")
            self.assertEqual(snapshot.status_code, 200)
            self.assertFalse(snapshot.json()["unchanged"])
            self.assertEqual(snapshot.json()["snapshot"]["session"]["next_frame_sequence"], 2)

            events = client.get(f"/api/live/sessions/{session_id}/events?since_seq=1")
            self.assertEqual(events.status_code, 200)
            event_payloads = events.json()["events"]
            self.assertEqual([event["seq"] for event in event_payloads], [1, 2, 3])
            self.assertEqual(event_payloads[-1]["kind"], "terminal_failure")

    def test_stop_timeout_and_abort_return_terminal_failure_semantics(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8, speech=(True,)),
            )
            client = TestClient(app)
            session_id = client.post("/api/live/sessions").json()["id"]

            frame = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 4))
            self.assertEqual(frame.status_code, 200)

            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})
            self.assertEqual(stopped.status_code, 409)
            self.assertEqual(stopped.json()["snapshot"]["session"]["accepted_samples"], 4)
            self.assertEqual(stopped.json()["snapshot"]["session"]["accounted_samples"], 0)
            self.assertEqual(stopped.json()["snapshot"]["terminal_failure"]["kind"], "transport_pacing")

            aborted = client.post(f"/api/live/sessions/{session_id}/abort", json={"reason": "caller cancelled"})
            self.assertEqual(aborted.status_code, 200)
            self.assertEqual(aborted.json()["snapshot"]["session"]["status"], "aborted")
            self.assertEqual(aborted.json()["snapshot"]["session"]["failure_reason"], "caller cancelled")

            rejected = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(1, 1))
            self.assertEqual(rejected.status_code, 429)

    def test_v2_frame_adapter_validates_before_mono_runtime_and_returns_lane_ack(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
            )
            client = TestClient(app)
            session_id = client.post("/api/live/sessions").json()["id"]

            invalid = v2_frame_payload(0, 2)
            invalid["sample_count"] = 3
            rejected = client.post(f"/api/live/sessions/{session_id}/frames", json=invalid)
            self.assertEqual(rejected.status_code, 400)
            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 0)
            self.assertEqual(snapshot["next_frame_sequence"], 0)

            accepted = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(0, 2, lane="microphone"),
            )
            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(
                accepted.json()["ack"],
                {
                    "lane": "microphone",
                    "sequence": 0,
                    "start_sample": 0,
                    "end_sample": 2,
                    "accepted_samples": 2,
                    "retained_samples": 2,
                    "frozen_span_ids": [],
                },
            )
