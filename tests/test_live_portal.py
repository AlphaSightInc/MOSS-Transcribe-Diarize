from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from test_live_api import LIVE_AUTH_FINGERPRINT, make_live_runtime


BASE_INDEX_SHA256 = "aaa308fa135e8e29ed1d96e9b9417952959c9c0218f783ddd4b62ff249a6e43d"
EXPECTED_LIVE_API = {
    ("GET", "/api/live/descriptor"),
    ("POST", "/api/live/pairing-codes"),
    ("POST", "/api/live/pairings"),
    ("POST", "/api/live/sessions"),
    ("POST", "/api/live/sessions/{session_id}/frames"),
    ("GET", "/api/live/sessions/{session_id}/snapshot"),
    ("GET", "/api/live/sessions/{session_id}/events"),
    ("POST", "/api/live/sessions/{session_id}/stop"),
    ("POST", "/api/live/sessions/{session_id}/abort"),
    ("DELETE", "/api/live/devices/{device_id}"),
}


def _live_api_routes(app) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if not route.path.startswith("/api/live"):
            continue
        for method in route.methods or ():
            if method not in {"HEAD", "OPTIONS"}:
                routes.add((method, route.path))
    return routes


class LivePortalRouteTest(unittest.TestCase):
    def test_live_portal_is_absent_by_default_and_batch_root_is_byte_exact(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir)
            client = TestClient(app)

            portal = client.get("/live")
            batch = client.get("/")

            self.assertEqual(portal.status_code, 404)
            self.assertEqual(batch.status_code, 200)
            self.assertEqual(batch.headers.get("cache-control"), "no-store")
            self.assertEqual(hashlib.sha256(batch.content).hexdigest(), BASE_INDEX_SHA256)

    def test_live_portal_is_enabled_no_store_and_does_not_add_live_api_routes(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=16),
                live_auth_state_path=Path(tmpdir) / "live-auth.json",
                live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
            )
            client = TestClient(app)

            portal = client.get("/live")

            self.assertEqual(portal.status_code, 200)
            self.assertEqual(portal.headers.get("cache-control"), "no-store")
            self.assertTrue(portal.headers.get("content-type", "").startswith("text/html"))
            self.assertIn('id="livePortal"', portal.text)
            self.assertEqual(_live_api_routes(app), EXPECTED_LIVE_API)

    def test_live_portal_document_uses_manual_memory_only_authority_shell(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=16),
                live_auth_state_path=Path(tmpdir) / "live-auth.json",
                live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
            )
            html = TestClient(app).get("/live").text
            lower = html.lower()

            self.assertIn('id="sessionId"', html)
            self.assertIn('id="viewToken"', html)
            self.assertIn('type="password"', html)
            self.assertIn('autocomplete="off"', html)
            self.assertIn("Authorization", html)
            self.assertIn("Bearer ", html)
            self.assertIn("/api/live/sessions/", html)
            self.assertIn("since_version", html)
            self.assertIn("since_seq", html)
            self.assertIn("disconnected", html)
            self.assertIn("reconnecting", html)
            self.assertNotIn("localhost", lower)
            self.assertNotIn("127.0.0.1", lower)
            self.assertNotIn("websocket", lower)
            self.assertNotIn("eventsource", lower)
            self.assertNotIn("localstorage", lower)
            self.assertNotIn("sessionstorage", lower)
            self.assertNotIn("document.cookie", lower)
            self.assertNotIn(".innerHTML", html)
