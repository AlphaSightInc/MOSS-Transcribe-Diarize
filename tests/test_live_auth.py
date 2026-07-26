from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from moss_transcribe_diarize.app.live_auth import (
    CapturePrincipal,
    LiveAccessConflict,
    LiveAccessForbidden,
    LiveAccessRegistry,
    LiveAccessUnauthorized,
    LivePeer,
    PAIRING_TTL_SECONDS,
    SECRET_BYTES,
    VIEW_TTL_SECONDS,
)


FINGERPRINT = "ab" * 32
LOOPBACK = LivePeer("127.0.0.1", "http")
LAN_TLS = LivePeer("192.168.68.20", "https")
LAN_CLEAR = LivePeer("192.168.68.20", "http")
TAILNET_TLS = LivePeer("100.64.10.20", "https")
ULA_TLS = LivePeer("fd7a:115c:a1e0::20", "https")
PUBLIC_TLS = LivePeer("8.8.8.8", "https")


class ScriptedSecrets:
    def __init__(self) -> None:
        self.issued: list[tuple[int, str]] = []
        self._index = 0

    def __call__(self, nbytes: int) -> str:
        self.issued.append((nbytes, f"secret-{self._index:02d}-" + ("x" * 40)))
        self._index += 1
        return self.issued[-1][1]


class LiveAccessRegistryTest(unittest.TestCase):
    def test_peer_admission_uses_direct_address_and_tls_policy(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self._registry(tmpdir)

            tailnet_pairing = registry.issue_pairing(LOOPBACK, now=0.0)
            self.assertEqual(
                registry.exchange_pairing(TAILNET_TLS, tailnet_pairing.pairing_payload, device_id="tailnet", now=1.0).device_id,
                "tailnet",
            )
            ula_pairing = registry.issue_pairing(LOOPBACK, now=2.0)
            self.assertEqual(
                registry.exchange_pairing(ULA_TLS, ula_pairing.pairing_payload, device_id="ula", now=3.0).device_id,
                "ula",
            )
            with self.assertRaisesRegex(LiveAccessForbidden, "TLS"):
                registry.issue_pairing(LAN_CLEAR, now=0.0)
            with self.assertRaisesRegex(LiveAccessForbidden, "private live network"):
                registry.issue_pairing(PUBLIC_TLS, now=0.0)

    def test_pairing_issue_is_loopback_only_and_exchange_is_cert_bound_single_use(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self._registry(tmpdir)

            with self.assertRaisesRegex(LiveAccessForbidden, "loopback"):
                registry.issue_pairing(LAN_TLS, now=0.0)
            issued = registry.issue_pairing(LOOPBACK, now=10.0)
            self.assertTrue(issued.pairing_payload.startswith("mtd1."))
            self.assertTrue(issued.pairing_payload.endswith(FINGERPRINT))
            self.assertEqual(issued.expires_at, 10.0 + PAIRING_TTL_SECONDS)

            capture = registry.exchange_pairing(
                LAN_TLS,
                issued.pairing_payload,
                device_id="mac-1",
                now=11.0,
            )

            self.assertEqual(capture.device_id, "mac-1")
            self.assertEqual(capture.scope, "capture")
            with self.assertRaisesRegex(LiveAccessUnauthorized, "invalid"):
                registry.exchange_pairing(
                    LAN_TLS,
                    issued.pairing_payload,
                    device_id="mac-replay",
                    now=12.0,
                )

            issued2 = registry.issue_pairing(LOOPBACK, now=20.0)
            mismatched = issued2.pairing_payload[:-64] + ("cd" * 32)
            with self.assertRaisesRegex(LiveAccessUnauthorized, "certificate"):
                registry.exchange_pairing(LAN_TLS, mismatched, device_id="mac-2", now=21.0)

            issued3 = registry.issue_pairing(LOOPBACK, now=30.0)
            with self.assertRaisesRegex(LiveAccessUnauthorized, "expired"):
                registry.exchange_pairing(
                    LAN_TLS,
                    issued3.pairing_payload,
                    device_id="mac-3",
                    now=30.0 + PAIRING_TTL_SECONDS,
                )

    def test_capture_and_view_authority_have_exact_action_and_session_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self._registry(tmpdir)
            capture = self._pair(registry, "mac-1", now=1.0)
            decision = registry.authorize(LAN_TLS, capture.device_token, "create", None, now=2.0)
            self.assertEqual(decision.principal, CapturePrincipal("mac-1"))

            view = registry.bind_session(decision.principal, "session-1", now=3.0)
            self.assertEqual(view.owner_device_id, "mac-1")
            self.assertEqual(view.expires_at, 3.0 + VIEW_TTL_SECONDS)
            self.assertEqual(
                registry.authorize(LAN_TLS, capture.device_token, "frame", "session-1", now=4.0).principal,
                CapturePrincipal("mac-1"),
            )
            self.assertEqual(
                registry.authorize(LAN_TLS, capture.device_token, "heartbeat", "session-1", now=4.0).principal,
                CapturePrincipal("mac-1"),
            )
            self.assertEqual(
                registry.authorize(LAN_TLS, view.view_token, "snapshot", "session-1", now=4.0).principal.session_id,
                "session-1",
            )

            with self.assertRaisesRegex(LiveAccessForbidden, "view authority"):
                registry.authorize(LAN_TLS, view.view_token, "frame", "session-1", now=4.0)
            with self.assertRaisesRegex(LiveAccessForbidden, "view authority"):
                registry.authorize(LAN_TLS, view.view_token, "heartbeat", "session-1", now=4.0)
            with self.assertRaisesRegex(LiveAccessForbidden, "different session"):
                registry.authorize(LAN_TLS, view.view_token, "snapshot", "session-2", now=4.0)
            with self.assertRaisesRegex(LiveAccessUnauthorized, "invalid"):
                registry.authorize(LAN_TLS, "wrong", "snapshot", "session-1", now=4.0)
            with self.assertRaisesRegex(LiveAccessUnauthorized, "missing"):
                registry.authorize(LAN_TLS, None, "snapshot", "session-1", now=4.0)

    def test_device_ownership_revocation_release_and_view_expiry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = self._registry(tmpdir)
            capture1 = self._pair(registry, "mac-1", now=1.0)
            capture2 = self._pair(registry, "mac-2", now=2.0)
            owner = registry.authorize(LAN_TLS, capture1.device_token, "create", None, now=3.0)
            view = registry.bind_session(owner.principal, "session-1", now=3.0)

            with self.assertRaisesRegex(LiveAccessForbidden, "not owned"):
                registry.authorize(LAN_TLS, capture2.device_token, "frame", "session-1", now=4.0)
            with self.assertRaisesRegex(LiveAccessUnauthorized, "invalid"):
                registry.authorize(LAN_TLS, view.view_token, "events", "session-1", now=3.0 + VIEW_TTL_SECONDS)
            self.assertEqual(
                registry.authorize(
                    LAN_TLS,
                    capture1.device_token,
                    "events",
                    "session-1",
                    now=3.0 + VIEW_TTL_SECONDS,
                ).principal,
                CapturePrincipal("mac-1"),
            )

            revoked = registry.revoke_device(LOOPBACK, "mac-1", now=5.0)
            self.assertEqual(revoked.session_ids, ("session-1",))
            with self.assertRaisesRegex(LiveAccessUnauthorized, "invalid"):
                registry.authorize(LAN_TLS, capture1.device_token, "events", "session-1", now=6.0)
            with self.assertRaisesRegex(LiveAccessUnauthorized, "invalid"):
                registry.authorize(LAN_TLS, view.view_token, "events", "session-1", now=6.0)
            with self.assertRaisesRegex(LiveAccessForbidden, "loopback"):
                registry.revoke_device(LAN_TLS, "mac-2", now=7.0)

            issued = registry.issue_pairing(LOOPBACK, now=8.0)
            with self.assertRaisesRegex(LiveAccessConflict, "revoked"):
                registry.exchange_pairing(LAN_TLS, issued.pairing_payload, device_id="mac-1", now=9.0)

            owner2 = registry.authorize(LAN_TLS, capture2.device_token, "create", None, now=10.0)
            view2 = registry.bind_session(owner2.principal, "session-2", now=10.0)
            registry.release_session("session-2")
            with self.assertRaisesRegex(LiveAccessUnauthorized, "invalid"):
                registry.authorize(LAN_TLS, view2.view_token, "events", "session-2", now=11.0)

    def test_persistence_is_digest_only_private_and_survives_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets = ScriptedSecrets()
            registry = self._registry(tmpdir, secret_factory=secrets)
            issued = registry.issue_pairing(LOOPBACK, now=1.0)
            capture = registry.exchange_pairing(LAN_TLS, issued.pairing_payload, device_id="mac-1", now=2.0)
            registry.revoke_device(LOOPBACK, "mac-revoked", now=3.0)
            state_path = Path(tmpdir) / "live-auth.json"

            state_text = state_path.read_text(encoding="utf-8")
            self.assertNotIn(issued.pairing_payload, state_text)
            self.assertNotIn(capture.device_token, state_text)
            self.assertNotIn("secret-00", state_text)
            self.assertNotIn("secret-01", state_text)
            self.assertIn('"token_digest"', state_text)
            if os.name != "nt":
                self.assertEqual(state_path.stat().st_mode & 0o077, 0)

            restarted = self._registry(tmpdir)
            self.assertEqual(
                restarted.authorize(LAN_TLS, capture.device_token, "create", None, now=4.0).principal,
                CapturePrincipal("mac-1"),
            )
            issued2 = restarted.issue_pairing(LOOPBACK, now=5.0)
            with self.assertRaisesRegex(LiveAccessConflict, "revoked"):
                restarted.exchange_pairing(LAN_TLS, issued2.pairing_payload, device_id="mac-revoked", now=6.0)

            state = json.loads(state_text)
            self.assertEqual(sorted(state["devices"]), ["mac-1", "mac-revoked"])

    def test_all_generated_secrets_request_32_bytes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            secrets = ScriptedSecrets()
            registry = self._registry(tmpdir, secret_factory=secrets)
            issued = registry.issue_pairing(LOOPBACK, now=1.0)
            capture = registry.exchange_pairing(LAN_TLS, issued.pairing_payload, device_id="mac-1", now=2.0)
            owner = registry.authorize(LAN_TLS, capture.device_token, "create", None, now=3.0)
            registry.bind_session(owner.principal, "session-1", now=4.0)

            self.assertEqual(SECRET_BYTES, 32)
            self.assertEqual([nbytes for nbytes, _ in secrets.issued], [32, 32, 32])

    def test_live_access_secret_files_are_ignored_by_git(self):
        repo_root = Path(__file__).resolve().parents[1]
        for relative_path in (
            "ops/live-tls.key",
            "ops/live-tls.pem",
            "ops/live-auth.json",
            "ops/pairing-payload.txt",
        ):
            with self.subTest(relative_path=relative_path):
                result = subprocess.run(
                    ["git", "check-ignore", "--quiet", "--", relative_path],
                    cwd=repo_root,
                    check=False,
                )
                self.assertEqual(result.returncode, 0)

    def _registry(self, tmpdir: str, secret_factory=None) -> LiveAccessRegistry:
        return LiveAccessRegistry(
            state_path=Path(tmpdir) / "live-auth.json",
            server_cert_sha256=FINGERPRINT,
            secret_factory=secret_factory,
        )

    def _pair(self, registry: LiveAccessRegistry, device_id: str, *, now: float):
        issued = registry.issue_pairing(LOOPBACK, now=now)
        return registry.exchange_pairing(LAN_TLS, issued.pairing_payload, device_id=device_id, now=now + 0.5)


if __name__ == "__main__":
    unittest.main()
