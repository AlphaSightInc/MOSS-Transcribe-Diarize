from __future__ import annotations

import base64
import importlib.util
import tempfile
import unittest

from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE


FASTAPI_AVAILABLE = importlib.util.find_spec("fastapi") is not None


def frame_payload(sequence: int, samples: int, *, sample_rate: int = LIVE_SAMPLE_RATE) -> dict:
    return {
        "sequence": sequence,
        "pcm_base64": base64.b64encode(b"\0" * samples * 2).decode("ascii"),
        "sample_count": samples,
        "sample_rate": sample_rate,
    }


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

    def test_live_enablement_requires_explicit_retention_capacity(self):
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaisesRegex(ValueError, "live_max_retained_samples is required"):
                create_app(model_path="fake-model", runs_dir=tmpdir, live_enabled=True)

    def test_ordered_frames_ack_snapshot_and_backpressure_are_explicit(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_max_retained_samples=4,
            )
            client = TestClient(app)

            created = client.post("/api/live/sessions")
            self.assertEqual(created.status_code, 200)
            session_id = created.json()["id"]
            self.assertFalse(hasattr(app.state.manager, "live_sessions"))
            self.assertIsNotNone(app.state.live_sessions.get(session_id))

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

            stale = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(2, 1))
            self.assertEqual(stale.status_code, 409)
            self.assertIn("expected frame sequence 1", stale.json()["detail"])

            accepted = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(1, 2))
            self.assertEqual(accepted.status_code, 200)
            backpressure = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(2, 1))
            self.assertEqual(backpressure.status_code, 429)
            self.assertEqual(backpressure.json()["snapshot"]["accepted_samples"], 4)

            snapshot = client.get(f"/api/live/sessions/{session_id}/snapshot?since_version=0")
            self.assertEqual(snapshot.status_code, 200)
            self.assertFalse(snapshot.json()["unchanged"])
            self.assertEqual(snapshot.json()["snapshot"]["next_frame_sequence"], 2)

    def test_stop_timeout_and_abort_return_terminal_failure_semantics(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_max_retained_samples=8,
            )
            client = TestClient(app)
            session_id = client.post("/api/live/sessions").json()["id"]

            frame = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 4))
            self.assertEqual(frame.status_code, 200)

            stopped = client.post(f"/api/live/sessions/{session_id}/stop", json={"deadline": 0.001})
            self.assertEqual(stopped.status_code, 409)
            self.assertEqual(stopped.json()["snapshot"]["status"], "closing")
            self.assertEqual(stopped.json()["snapshot"]["accepted_samples"], 4)
            self.assertEqual(stopped.json()["snapshot"]["accounted_samples"], 0)

            aborted = client.post(f"/api/live/sessions/{session_id}/abort", json={"reason": "caller cancelled"})
            self.assertEqual(aborted.status_code, 200)
            self.assertEqual(aborted.json()["snapshot"]["status"], "aborted")
            self.assertEqual(aborted.json()["snapshot"]["failure_reason"], "caller cancelled")

            rejected = client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(1, 1))
            self.assertEqual(rejected.status_code, 409)
