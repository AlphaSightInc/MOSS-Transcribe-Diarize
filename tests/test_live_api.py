from __future__ import annotations

import base64
import contextlib
import importlib.util
import io
import tempfile
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_auth import VIEW_ABSOLUTE_CAP_SECONDS
from moss_transcribe_diarize.app.live_endpoint import EndpointPolicy, EndpointPolicyConfig, SpeechObservation
from moss_transcribe_diarize.app.live_lane_contract import LIVE_V2_REPLAY_ACK_WINDOW, LiveLane
from moss_transcribe_diarize.app.live_helper_presence import HELPER_HEALTH_SCHEMA
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
LIVE_AUTH_FINGERPRINT = "ab" * 32


class AuthorizedLiveClient:
    def __init__(self, app, token: str):
        from fastapi.testclient import TestClient

        self._client = TestClient(
            app,
            base_url="https://moss.lan",
            client=("192.168.68.20", 50000),
        )
        self._headers = {"Authorization": f"Bearer {token}"}

    def get(self, path: str, **kwargs):
        return self._client.get(path, **self._with_auth(path, kwargs))

    def post(self, path: str, **kwargs):
        return self._client.post(path, **self._with_auth(path, kwargs))

    def delete(self, path: str, **kwargs):
        return self._client.delete(path, **self._with_auth(path, kwargs))

    def _with_auth(self, path: str, kwargs: dict) -> dict:
        if path == "/api/live/sessions" or path.startswith("/api/live/sessions/"):
            headers = dict(self._headers)
            headers.update(kwargs.pop("headers", {}))
            kwargs["headers"] = headers
        return kwargs


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


def helper_heartbeat_payload(
    *,
    sequence: int = 0,
    sent_monotonic_ns: int = 10,
    state: str = "capturing",
    lane_state: str = "capturing",
    failed_lane: str | None = None,
    failure_code: str | None = None,
) -> dict:
    lane = {
        "state": lane_state,
        "device_epoch": 0,
        "dropped_frames": 0,
        "discontinuities": 0,
        "failure_code": failure_code if lane_state == "failed" else None,
    }
    lanes = {"system": dict(lane), "microphone": dict(lane)}
    if failed_lane is not None:
        lanes[failed_lane]["state"] = "failed"
        lanes[failed_lane]["failure_code"] = failure_code
    return {
        "schema": HELPER_HEALTH_SCHEMA,
        "instance_id": "helper-a",
        "sequence": sequence,
        "sent_monotonic_ns": sent_monotonic_ns,
        "helper_version": "0.1.0",
        "state": state,
        "lanes": lanes,
    }


class _FakeTimerHandle:
    def __init__(self, callback):
        self.callback = callback
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.callback()


class _FakeTimer:
    def __init__(self) -> None:
        self.scheduled: list[tuple[int, _FakeTimerHandle]] = []

    def schedule(self, deadline_monotonic_ns: int, callback) -> _FakeTimerHandle:
        handle = _FakeTimerHandle(callback)
        self.scheduled.append((deadline_monotonic_ns, handle))
        return handle


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
            # Same value as the endpoint policy below: one span cap, declared twice.
            hard_cap_samples=4000,
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
    def _live_auth_kwargs(self, tmpdir: str) -> dict:
        return {
            "live_auth_state_path": Path(tmpdir) / "live-auth.json",
            "live_server_cert_sha256": LIVE_AUTH_FINGERPRINT,
            "live_helper_lease_seconds": 30.0,
        }

    def _paired_client(self, app) -> AuthorizedLiveClient:
        from fastapi.testclient import TestClient

        local = TestClient(
            app,
            base_url="http://127.0.0.1",
            client=("127.0.0.1", 50000),
        )
        lan = TestClient(
            app,
            base_url="https://moss.lan",
            client=("192.168.68.20", 50001),
        )
        issued = local.post("/api/live/pairing-codes")
        self.assertEqual(issued.status_code, 200)
        paired = lan.post(
            "/api/live/pairings",
            json={"device_id": "test-device", "pairing_payload": issued.json()["pairing_payload"]},
        )
        self.assertEqual(paired.status_code, 200)
        return AuthorizedLiveClient(app, paired.json()["device_token"])

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

    def test_live_enablement_requires_positive_helper_lease(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            required = {
                "model_path": "fake-model",
                "runs_dir": tmpdir,
                "live_enabled": True,
                "live_runtime_factory": lambda: make_live_runtime(),
                "live_auth_state_path": Path(tmpdir) / "live-auth.json",
                "live_server_cert_sha256": LIVE_AUTH_FINGERPRINT,
            }
            with self.assertRaisesRegex(ValueError, "live_helper_lease_seconds is required"):
                create_app(**required)
            for value in (0, -1):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(ValueError, "live_helper_lease_seconds must be positive"):
                        create_app(**required, live_helper_lease_seconds=value)

    def test_forwarding_headers_cannot_grant_loopback_admin_authority(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(),
                **self._live_auth_kwargs(tmpdir),
            )
            lan = TestClient(
                app,
                base_url="https://moss.lan",
                client=("192.168.68.20", 50000),
            )

            for headers in (
                {"X-Forwarded-For": "127.0.0.1"},
                {"X-Real-IP": "127.0.0.1"},
                {"Forwarded": "for=127.0.0.1"},
            ):
                with self.subTest(headers=headers):
                    self.assertEqual(
                        lan.post("/api/live/pairing-codes", headers=headers).status_code,
                        403,
                    )
                    self.assertEqual(
                        lan.delete("/api/live/devices/test-device", headers=headers).status_code,
                        403,
                    )

    def test_live_credentials_stay_out_of_query_parameters_and_process_output(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(),
                **self._live_auth_kwargs(tmpdir),
            )
            local = TestClient(
                app,
                base_url="http://127.0.0.1",
                client=("127.0.0.1", 50000),
            )
            lan = TestClient(
                app,
                base_url="https://moss.lan",
                client=("192.168.68.20", 50001),
            )
            stdout = io.StringIO()
            stderr = io.StringIO()

            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                issued = local.post("/api/live/pairing-codes")
                paired = lan.post(
                    "/api/live/pairings",
                    json={
                        "device_id": "test-device",
                        "pairing_payload": issued.json()["pairing_payload"],
                    },
                )
                created = lan.post(
                    "/api/live/sessions",
                    headers={"Authorization": f"Bearer {paired.json()['device_token']}"},
                )

            self.assertEqual(issued.status_code, 200)
            self.assertEqual(paired.status_code, 200)
            self.assertEqual(created.status_code, 200)
            captured_output = stdout.getvalue() + stderr.getvalue()
            for credential in (
                issued.json()["pairing_payload"],
                paired.json()["device_token"],
                created.json()["view_token"],
            ):
                self.assertNotIn(credential, captured_output)

            session_id = created.json()["id"]
            query_only = lan.get(
                f"/api/live/sessions/{session_id}/snapshot",
                params={"token": created.json()["view_token"]},
            )
            self.assertEqual(query_only.status_code, 401)

    def test_live_routes_are_runtime_backed_with_descriptor_events_and_backpressure(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=4),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)

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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
            self.assertEqual(rejected.status_code, 403)

    def test_clean_stop_immediately_revokes_view_authority(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
            created = client.post("/api/live/sessions").json()
            session_id = created["id"]
            viewer = AuthorizedLiveClient(app, created["view_token"])

            self.assertEqual(
                viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code,
                200,
            )
            remaining = created["view_expires_at"] - time.time()
            self.assertLessEqual(remaining, VIEW_ABSOLUTE_CAP_SECONDS)
            self.assertGreater(remaining, VIEW_ABSOLUTE_CAP_SECONDS - 60.0)

            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})
            self.assertEqual(stopped.status_code, 200)
            self.assertEqual(stopped.json()["snapshot"]["session"]["status"], "closed")

            self.assertEqual(
                viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code,
                401,
            )
            self.assertEqual(
                viewer.get(f"/api/live/sessions/{session_id}/events").status_code,
                401,
            )

    def test_failed_stop_revokes_the_view_without_stranding_capture_authority(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8, speech=(True,)),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
            created = client.post("/api/live/sessions").json()
            session_id = created["id"]
            viewer = AuthorizedLiveClient(app, created["view_token"])

            self.assertEqual(
                client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 4)).status_code,
                200,
            )
            self.assertEqual(viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code, 200)

            # A stop that fails accounting leaves the session terminal without releasing
            # the ownership entry - the capture client still has to be able to abort.
            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.0})
            self.assertEqual(stopped.status_code, 409)
            # The mono session still reads "active" here; only the runtime's terminal
            # failure records that the session is over. The view must follow the latter.
            self.assertEqual(stopped.json()["snapshot"]["session"]["status"], "active")
            self.assertEqual(stopped.json()["snapshot"]["terminal_failure"]["kind"], "transport_pacing")

            self.assertEqual(viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code, 401)
            aborted = client.post(f"/api/live/sessions/{session_id}/abort", json={"reason": "cleanup"})
            self.assertEqual(aborted.status_code, 200)
            self.assertEqual(viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code, 401)

    def test_operator_view_revocation_is_loopback_only_and_keeps_capture_streaming(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
            created = client.post("/api/live/sessions").json()
            session_id = created["id"]
            viewer = AuthorizedLiveClient(app, created["view_token"])
            local = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))

            self.assertEqual(viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code, 200)
            self.assertEqual(
                client.delete(f"/api/live/sessions/{session_id}/view").status_code,
                403,
            )
            self.assertEqual(viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code, 200)

            revoked = local.delete(f"/api/live/sessions/{session_id}/view")
            self.assertEqual(revoked.status_code, 200)
            self.assertEqual(revoked.json(), {"session_id": session_id, "view_revoked": True})

            self.assertEqual(viewer.get(f"/api/live/sessions/{session_id}/snapshot").status_code, 401)
            self.assertEqual(
                client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 4)).status_code,
                200,
            )
            self.assertEqual(local.delete(f"/api/live/sessions/{session_id}/view").status_code, 404)

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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
            self.assertEqual(rejected_after_abort.status_code, 403)

    def test_v2_failed_terminal_stop_releases_registry_entry(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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

    def test_explicit_failed_lane_heartbeat_calls_v2_fail_lane_without_releasing_peer(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
            session_id = client.post("/api/live/sessions").json()["id"]
            heartbeat = client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=helper_heartbeat_payload(
                    failed_lane="microphone",
                    failure_code="permission_denied",
                ),
            )
            peer_frame = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(0, 2, lane="system"),
            )

            self.assertEqual(heartbeat.status_code, 200)
            self.assertEqual(peer_frame.status_code, 200)
            v2_snapshot = app.state.live_v2_sessions.get(session_id).snapshot().to_dict()
            self.assertEqual(v2_snapshot["lanes"]["microphone"]["health"], "failed")
            self.assertEqual(
                v2_snapshot["lanes"]["microphone"]["failure_code"],
                "permission_denied",
            )
            self.assertIn(session_id, app.state.live_v2_sessions)

    def test_helper_lease_expiry_aborts_mono_expires_v2_and_releases_cleanup(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            timer = _FakeTimer()
            app.state.live_helper_failures._timer = timer
            client = self._paired_client(app)
            session_id = client.post("/api/live/sessions").json()["id"]

            heartbeat = client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=helper_heartbeat_payload(),
            )
            timer.scheduled[0][1].fire()
            late_frame = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(0, 1, lane="system"),
            )

            self.assertEqual(heartbeat.status_code, 200)
            self.assertEqual(late_frame.status_code, 403)
            self.assertNotIn(session_id, app.state.live_v2_sessions)
            with self.assertRaises(KeyError):
                app.state.live_v2_mixers.get(session_id)
            self.assertIsNone(app.state.live_helper_presence.snapshot(session_id))
            self.assertEqual(
                app.state.live_runtime.snapshot(session_id).session.status,
                "aborted",
            )

    def test_stale_lease_callback_after_renewal_does_not_abort_live_session(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            timer = _FakeTimer()
            app.state.live_helper_failures._timer = timer
            client = self._paired_client(app)
            session_id = client.post("/api/live/sessions").json()["id"]
            client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=helper_heartbeat_payload(),
            )
            renewed = client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=helper_heartbeat_payload(sequence=1, sent_monotonic_ns=20),
            )

            timer.scheduled[0][1].fire()
            peer_frame = client.post(
                f"/api/live/sessions/{session_id}/frames",
                json=v2_frame_payload(0, 1, lane="system"),
            )

            self.assertEqual(renewed.status_code, 200)
            self.assertEqual(peer_frame.status_code, 200)
            self.assertIn(session_id, app.state.live_v2_sessions)
            self.assertEqual(app.state.live_runtime.snapshot(session_id).session.status, "active")
            self.assertTrue(timer.scheduled[0][1].cancelled)
            self.assertFalse(timer.scheduled[1][1].cancelled)

    def test_muted_alive_degraded_recovering_do_not_fail_live_session(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=8),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
            session_id = client.post("/api/live/sessions").json()["id"]

            degraded = client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=helper_heartbeat_payload(state="degraded"),
            )
            recovering = client.post(
                f"/api/live/sessions/{session_id}/heartbeat",
                json=helper_heartbeat_payload(
                    sequence=1,
                    sent_monotonic_ns=20,
                    state="recovering",
                ),
            )

            self.assertEqual(degraded.status_code, 200)
            self.assertEqual(recovering.status_code, 200)
            self.assertIn(session_id, app.state.live_v2_sessions)
            self.assertEqual(app.state.live_runtime.snapshot(session_id).session.status, "active")

    def test_v2_http_streams_320_single_lane_frames_across_ack_window_without_mono_bypass(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=321),
                **self._live_auth_kwargs(tmpdir),
            )
            client = self._paired_client(app)
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
                **self._live_auth_kwargs(tmpdir),
            )
            idle_client = self._paired_client(idle_app)
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
