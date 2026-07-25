from __future__ import annotations

import base64
import importlib.util
import tempfile
import threading
import time
import unittest
from dataclasses import dataclass

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_lane_contract import LIVE_V2_REPLAY_ACK_WINDOW, LiveLane
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


def frame_payload(
    sequence: int,
    samples: int,
    *,
    sample_rate: int = LIVE_SAMPLE_RATE,
) -> dict:
    return {
        "sequence": sequence,
        "pcm_base64": base64.b64encode(b"\0" * samples * 2).decode("ascii"),
        "sample_count": samples,
        "sample_rate": sample_rate,
    }


def v2_frame_payload(
    sequence: int,
    samples: int,
    *,
    lane: str = "system",
    sample_rate: int = LIVE_SAMPLE_RATE,
    capture_timestamp_ns: int | None = None,
) -> dict:
    if capture_timestamp_ns is None:
        capture_timestamp_ns = sequence * samples * 1_000_000_000 // sample_rate
    return frame_payload(sequence, samples, sample_rate=sample_rate) | {
        "lane": lane,
        "capture_timestamp_ns": capture_timestamp_ns,
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
    decoder_factory=ApiDecoder,
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
        decoder_factory=decoder_factory,
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
            self.assertIn(session_id, app.state.live_v2_sessions)

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
            self.assertEqual(snapshot.json()["v2_session"]["lanes"]["system"]["next_sequence"], 0)
            self.assertEqual(snapshot.json()["v2_session"]["lanes"]["microphone"]["next_sequence"], 0)

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

    def test_stop_composes_v2_and_mono_work_under_one_client_deadline(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        class SlowApiDecoder(ApiDecoder):
            def transcribe_pcm(self, *, span: FrozenSpan, pcm: bytes) -> InferenceTranscript:
                time.sleep(0.6)
                return super().transcribe_pcm(span=span, pcm=pcm)

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(
                    max_retained_samples=8,
                    speech=(True,),
                    decoder_factory=SlowApiDecoder,
                ),
            )
            client = TestClient(app)
            session_id = client.post("/api/live/sessions").json()["id"]
            self.assertEqual(
                client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 4)).status_code,
                200,
            )
            self.assertEqual(
                client.post(
                    f"/api/live/sessions/{session_id}/frames",
                    json=v2_frame_payload(0, 2),
                ).status_code,
                200,
            )

            def account_v2_lane() -> None:
                time.sleep(0.18)
                app.state.live_v2_sessions.get(session_id).account_through({LiveLane.SYSTEM: 0})

            consumer = threading.Thread(target=account_v2_lane)
            consumer.start()
            started = time.monotonic()
            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.25})
            elapsed = time.monotonic() - started
            consumer.join()

            self.assertEqual(stopped.status_code, 409)
            self.assertLessEqual(elapsed, 0.32)

    def test_v1_stop_retry_preserves_typed_mono_terminal_failure(self):
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
            self.assertEqual(
                client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 4)).status_code,
                200,
            )

            first = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})
            retried = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 1.0})

            self.assertEqual(first.status_code, 409)
            self.assertEqual(retried.status_code, 429)
            self.assertEqual(retried.json()["failure"]["kind"], "transport_pacing")
            self.assertEqual(retried.json()["failure"]["code"], "backpressure_or_deadline")
            self.assertEqual(retried.json()["snapshot"]["terminal_failure"]["kind"], "transport_pacing")

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
            self.assertEqual(accepted.json()["queued_item_ids"], [])
            self.assertEqual(accepted.json()["snapshot_version"], 0)
            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()
            self.assertEqual(snapshot["snapshot"]["session"]["accepted_samples"], 0)
            self.assertEqual(snapshot["snapshot"]["session"]["next_frame_sequence"], 0)
            self.assertEqual(snapshot["v2_session"]["lanes"]["microphone"]["next_sequence"], 1)
            self.assertEqual(snapshot["v2_session"]["lanes"]["microphone"]["accepted_samples"], 2)
            self.assertEqual(snapshot["v2_session"]["lanes"]["microphone"]["retained_samples"], 2)
            self.assertEqual(snapshot["v2_session"]["lanes"]["microphone"]["pruned_through_sequence"], -1)
            self.assertEqual(snapshot["v2_session"]["lanes"]["system"]["next_sequence"], 0)

    def test_v2_frame_adapter_mixes_sealed_lanes_into_mono_runtime(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(
                    max_retained_samples=9000,
                    speech=(True,),
                ),
            )
            client = TestClient(app)
            session_id = client.post("/api/live/sessions").json()["id"]
            frames_url = f"/api/live/sessions/{session_id}/frames"

            for sequence in range(2):
                timestamp = sequence * 250_000_000
                self.assertEqual(
                    client.post(
                        frames_url,
                        json=v2_frame_payload(
                            sequence,
                            4000,
                            lane="system",
                            capture_timestamp_ns=timestamp,
                        ),
                    ).status_code,
                    200,
                )
                accepted = client.post(
                    frames_url,
                    json=v2_frame_payload(
                        sequence,
                        4000,
                        lane="microphone",
                        capture_timestamp_ns=timestamp,
                    ),
                )

            self.assertEqual(accepted.status_code, 200)
            self.assertEqual(accepted.json()["queued_item_ids"], [0])
            self.assertGreater(accepted.json()["snapshot_version"], 0)
            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()
            self.assertEqual(snapshot["snapshot"]["session"]["accepted_samples"], 4000)
            self.assertEqual(snapshot["snapshot"]["session"]["next_frame_sequence"], 1)
            self.assertEqual(snapshot["v2_session"]["lanes"]["system"]["accounted_samples"], 4000)
            self.assertEqual(snapshot["v2_session"]["lanes"]["microphone"]["accounted_samples"], 4000)
            self.assertEqual(snapshot["v2_session"]["lanes"]["system"]["retained_samples"], 4000)
            self.assertEqual(snapshot["v2_session"]["lanes"]["microphone"]["retained_samples"], 4000)

    def test_v2_http_replays_prior_ack_and_keeps_lane_sequences_distinct(self):
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
            frames_url = f"/api/live/sessions/{session_id}/frames"

            system_zero = client.post(frames_url, json=v2_frame_payload(0, 2, lane="system"))
            replayed_system_zero = client.post(frames_url, json=v2_frame_payload(0, 2, lane="system"))
            microphone_zero = client.post(frames_url, json=v2_frame_payload(0, 2, lane="microphone"))

            self.assertEqual(system_zero.status_code, 200)
            self.assertEqual(replayed_system_zero.status_code, 200)
            self.assertEqual(replayed_system_zero.json()["ack"], system_zero.json()["ack"])
            self.assertEqual(replayed_system_zero.json()["queued_item_ids"], [])
            self.assertEqual(microphone_zero.status_code, 200)
            self.assertEqual(
                microphone_zero.json()["ack"],
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
            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 0)
            self.assertEqual(snapshot["next_frame_sequence"], 0)

    def test_v2_empty_stop_releases_registry_entry(self):
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
            self.assertIn(session_id, app.state.live_v2_sessions)

            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})

            self.assertEqual(stopped.status_code, 200)
            self.assertEqual(stopped.json()["snapshot"]["session"]["status"], "closed")
            self.assertEqual(stopped.json()["v2_session"]["status"], "closed")
            self.assertNotIn(session_id, app.state.live_v2_sessions)
            with self.assertRaises(KeyError):
                app.state.live_v2_mixers.get(session_id)

    def test_v2_http_rejects_out_of_order_lane_sequence_with_typed_conflict(self):
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

            rejected = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(1, 2, lane="system"),
            )

            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(
                rejected.json()["failure"],
                {
                    "code": "v2_out_of_order_frame",
                    "lane": "system",
                    "expected_sequence": 0,
                    "received_sequence": 1,
                },
            )
            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 0)
            self.assertEqual(snapshot["next_frame_sequence"], 0)

    def test_v2_http_maps_epoch_fences_to_typed_conflicts_without_sequence_mutation(self):
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
            frames_url = f"/api/live/sessions/{session_id}/frames"

            first = v2_frame_payload(0, 2, lane="system")
            first["device_epoch"] = 10
            self.assertEqual(client.post(frames_url, json=first).status_code, 200)

            unmarked_transition = v2_frame_payload(1, 2, lane="system")
            unmarked_transition["device_epoch"] = 11
            rejected_transition = client.post(frames_url, json=unmarked_transition)
            self.assertEqual(rejected_transition.status_code, 409)
            self.assertEqual(rejected_transition.json()["failure"]["code"], "v2_epoch_discontinuity_required")
            self.assertEqual(rejected_transition.json()["failure"]["current_device_epoch"], 10)
            self.assertEqual(rejected_transition.json()["failure"]["received_device_epoch"], 11)

            marked_transition = dict(unmarked_transition)
            marked_transition["discontinuity"] = True
            accepted_transition = client.post(frames_url, json=marked_transition)
            self.assertEqual(accepted_transition.status_code, 200)
            self.assertEqual(accepted_transition.json()["ack"]["sequence"], 1)
            self.assertEqual(accepted_transition.json()["ack"]["start_sample"], 2)

            stale_epoch = v2_frame_payload(2, 2, lane="system")
            stale_epoch["device_epoch"] = 10
            rejected_stale = client.post(frames_url, json=stale_epoch)
            self.assertEqual(rejected_stale.status_code, 409)
            self.assertEqual(rejected_stale.json()["failure"]["code"], "v2_stale_device_epoch")

            current_epoch = dict(stale_epoch)
            current_epoch["device_epoch"] = 11
            accepted_current = client.post(frames_url, json=current_epoch)
            self.assertEqual(accepted_current.status_code, 200)
            self.assertEqual(accepted_current.json()["ack"]["sequence"], 2)

            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 0)
            self.assertEqual(snapshot["next_frame_sequence"], 0)

    def test_v2_http_maps_lane_capacity_to_429_without_mutating_or_sharing_capacity(self):
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
            session_id = client.post("/api/live/sessions").json()["id"]
            frames_url = f"/api/live/sessions/{session_id}/frames"

            accepted_system = client.post(frames_url, json=v2_frame_payload(0, 3, lane="system"))
            rejected_system = client.post(frames_url, json=v2_frame_payload(1, 2, lane="system"))
            accepted_microphone = client.post(frames_url, json=v2_frame_payload(0, 4, lane="microphone"))
            corrected_system = client.post(frames_url, json=v2_frame_payload(1, 1, lane="system"))

            self.assertEqual(accepted_system.status_code, 200)
            self.assertEqual(rejected_system.status_code, 429)
            self.assertEqual(rejected_system.json()["failure"]["code"], "v2_lane_retention_capacity_reached")
            self.assertEqual(rejected_system.json()["failure"]["lane"], "system")
            self.assertEqual(accepted_microphone.status_code, 200)
            self.assertEqual(accepted_microphone.json()["ack"]["retained_samples"], 4)
            self.assertEqual(corrected_system.status_code, 200)
            self.assertEqual(corrected_system.json()["ack"]["sequence"], 1)
            self.assertEqual(corrected_system.json()["ack"]["retained_samples"], 4)
            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 0)
            self.assertEqual(snapshot["next_frame_sequence"], 0)

    def test_v2_stop_fails_closed_until_abort_discards_unconsumed_lane_frames(self):
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

            accepted = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(0, 2, lane="microphone"),
            )
            self.assertEqual(accepted.status_code, 200)

            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})
            self.assertEqual(stopped.status_code, 409)
            self.assertEqual(stopped.json()["failure"]["code"], "v2_mix_source_missing")
            self.assertEqual(stopped.json()["snapshot"]["session"]["status"], "active")
            self.assertEqual(stopped.json()["v2_session"]["status"], "closing")
            self.assertIn(session_id, app.state.live_v2_sessions)

            aborted = client.post(f"/api/live/sessions/{session_id}/abort", json={"reason": "caller cancelled"})
            self.assertEqual(aborted.status_code, 200)
            self.assertEqual(aborted.json()["snapshot"]["session"]["status"], "aborted")
            self.assertNotIn(session_id, app.state.live_v2_sessions)
            with self.assertRaises(KeyError):
                app.state.live_v2_mixers.get(session_id)

            rejected_after_abort = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(1, 1, lane="microphone"),
            )
            self.assertEqual(rejected_after_abort.status_code, 409)

    def test_v2_failed_terminal_stop_releases_registry_entry(self):
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
            frames_url = f"/api/live/sessions/{session_id}/frames"

            accepted = client.post(frames_url, json=v2_frame_payload(0, 2, lane="system"))
            self.assertEqual(accepted.status_code, 200)
            failed = app.state.live_v2_sessions.get(session_id).fail_lane(
                LiveLane.SYSTEM,
                "helper_inactive",
            )
            self.assertEqual(failed.to_dict()["lanes"]["system"]["failed_samples"], 2)

            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})

            self.assertEqual(stopped.status_code, 409)
            self.assertEqual(stopped.json()["failure"]["code"], "v2_stop_accounting_mismatch")
            self.assertEqual(stopped.json()["failure"]["reason"], "helper_inactive")
            self.assertEqual(stopped.json()["v2_session"]["status"], "failed")
            self.assertEqual(stopped.json()["v2_session"]["lanes"]["system"]["retained_samples"], 0)
            self.assertEqual(stopped.json()["v2_session"]["lanes"]["system"]["failed_samples"], 2)
            self.assertNotIn(session_id, app.state.live_v2_sessions)
            with self.assertRaises(KeyError):
                app.state.live_v2_mixers.get(session_id)

    def test_v2_http_streams_320_single_lane_frames_across_ack_window_without_mono_bypass(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=321),
            )
            client = TestClient(app)
            created = client.post("/api/live/sessions").json()
            frames_url = f"/api/live/sessions/{created['id']}/frames"

            for sequence in range(320):
                with self.subTest(sequence=sequence):
                    response = client.post(frames_url, json=v2_frame_payload(sequence, 1, lane="system"))
                    self.assertEqual(response.status_code, 200)
                    payload = response.json()
                    self.assertEqual(payload["queued_item_ids"], [])
                    self.assertEqual(payload["snapshot_version"], 0)
                    self.assertEqual(
                        payload["ack"],
                        {
                            "lane": "system",
                            "sequence": sequence,
                            "start_sample": sequence,
                            "end_sample": sequence + 1,
                            "accepted_samples": sequence + 1,
                            "retained_samples": sequence + 1,
                            "frozen_span_ids": [],
                        },
                    )

            snapshot = client.get(f"/api/live/sessions/{created['id']}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 0)
            self.assertEqual(snapshot["next_frame_sequence"], 0)

            pruned = client.post(frames_url, json=v2_frame_payload(0, 2, lane="system"))
            self.assertEqual(pruned.status_code, 409)
            self.assertEqual(pruned.json()["failure"]["code"], "v2_pruned_replay")
            self.assertEqual(pruned.json()["failure"]["lane"], "system")
            self.assertGreaterEqual(
                pruned.json()["failure"]["pruned_through_sequence"],
                0,
            )

            too_large_system = client.post(frames_url, json=v2_frame_payload(320, 2, lane="system"))
            self.assertEqual(too_large_system.status_code, 429)
            self.assertEqual(too_large_system.json()["failure"]["code"], "v2_lane_retention_capacity_reached")

            corrected_system = client.post(frames_url, json=v2_frame_payload(320, 1, lane="system"))
            first_microphone = client.post(frames_url, json=v2_frame_payload(0, 1, lane="microphone"))
            self.assertEqual(corrected_system.status_code, 200)
            self.assertEqual(corrected_system.json()["ack"]["retained_samples"], 321)
            self.assertEqual(first_microphone.status_code, 200)
            self.assertEqual(first_microphone.json()["ack"]["retained_samples"], 1)

            accepted_v1 = client.post(frames_url, json=frame_payload(0, 1))
            self.assertEqual(accepted_v1.status_code, 200)
            self.assertEqual(accepted_v1.json()["ack"]["sequence"], 0)
            snapshot = client.get(f"/api/live/sessions/{created['id']}/snapshot").json()["snapshot"]["session"]
            self.assertEqual(snapshot["accepted_samples"], 1)
            self.assertEqual(snapshot["next_frame_sequence"], 1)

            idle_app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=258),
            )
            idle_client = TestClient(idle_app)
            idle_created = idle_client.post("/api/live/sessions").json()
            idle_frames_url = f"/api/live/sessions/{idle_created['id']}/frames"
            self.assertEqual(
                idle_client.post(idle_frames_url, json=v2_frame_payload(0, 1, lane="system")).status_code,
                200,
            )
            for sequence in range(LIVE_V2_REPLAY_ACK_WINDOW + 1):
                response = idle_client.post(
                    idle_frames_url,
                    json=v2_frame_payload(sequence, 1, lane="microphone"),
                )
                self.assertEqual(response.status_code, 200)
            resumed_idle_system = idle_client.post(
                idle_frames_url,
                json=v2_frame_payload(1, 1, lane="system"),
            )
            self.assertEqual(resumed_idle_system.status_code, 200)
            self.assertEqual(resumed_idle_system.json()["ack"]["start_sample"], 1)

    def test_v2_pruned_replay_maps_to_typed_conflict_payload(self):
        from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2PrunedReplayError
        from moss_transcribe_diarize.app.live_transport import live_v2_replay_conflict_response

        status, payload = live_v2_replay_conflict_response(
            LiveV2PrunedReplayError(
                lane=LiveLane.MICROPHONE,
                sequence=3,
                pruned_through_sequence=4,
            )
        )

        self.assertEqual(status, 409)
        self.assertEqual(
            payload["failure"],
            {
                "code": "v2_pruned_replay",
                "lane": "microphone",
                "sequence": 3,
                "pruned_through_sequence": 4,
            },
        )
