#!/usr/bin/env python3
"""Probe that loopback shared-principal revocation survives a fresh registry start."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from moss_transcribe_diarize.app.live_auth import (
    LiveAccessRegistry,
    LiveAccessUnauthorized,
    LivePeer,
)


FINGERPRINT = "ab" * 32
LOOPBACK = LivePeer("127.0.0.1", "http")
LAN_TLS = LivePeer("192.168.68.20", "https")


def _is_rejected(registry: LiveAccessRegistry, token: str) -> bool:
    try:
        registry.authorize(LAN_TLS, token, "create", None, now=2.0)
    except LiveAccessUnauthorized:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        state_path = Path(tmpdir) / "live-auth.json"
        token = "probe-shared-bearer"
        registry = LiveAccessRegistry(
            state_path=state_path,
            server_cert_sha256=FINGERPRINT,
            shared_token=token,
        )
        principal = registry.authorize(LAN_TLS, token, "create", None, now=1.0).principal
        revocation = registry.revoke_device(LOOPBACK, principal.device_id, now=1.5)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        restarted = LiveAccessRegistry(
            state_path=state_path,
            server_cert_sha256=FINGERPRINT,
            shared_token=token,
        )

        result = {
            "probe": "shared_principal_revocation_survives_fresh_registry_start",
            "revocation_returned_device_id": revocation.device_id,
            "in_process_authority_rejected": _is_rejected(registry, token),
            "persisted_revocation": bool(
                state.get("devices", {}).get(principal.device_id, {}).get("revoked")
            ),
            "fresh_registry_authority_rejected": _is_rejected(restarted, token),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, sort_keys=True))

    return 0 if all(
        (
            result["in_process_authority_rejected"],
            result["persisted_revocation"],
            result["fresh_registry_authority_rejected"],
        )
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
