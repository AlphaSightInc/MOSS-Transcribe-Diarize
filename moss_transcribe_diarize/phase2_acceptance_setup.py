"""Attempt-owned qualification workspaces, issued only through normal HTTP bootstrap."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

import httpx

from .app.phase2 import SESSION_COOKIE
from .phase2_acceptance import _write_all, load_profile
from .phase2_g7_canary import G7_PRODUCTION_ORIGIN


class QualificationSetupError(RuntimeError):
    pass


def _private_once(path: Path, content: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(descriptor, content)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _bootstrap(client) -> tuple[str, str]:
    # A new normal visitor, never an injected database credential.
    client.cookies.clear()
    response = client.post("/api/workspace/bootstrap")
    if response.status_code != 200:
        raise QualificationSetupError("Qualification workspace bootstrap failed")
    owner = response.json().get("workspace_id")
    credential = response.cookies.get(SESSION_COOKIE)
    if not isinstance(owner, str) or not owner or not credential or owner == credential:
        raise QualificationSetupError("Qualification workspace authority is invalid")
    restored = client.get("/api/auth/session")
    if restored.status_code != 200 or restored.json().get("workspace_id") != owner:
        raise QualificationSetupError("Qualification workspace cookie did not round-trip")
    return owner, credential


def prepare_acceptance_profile(*, source: Path, attempt: Path, candidate_sha: str) -> Path:
    """Provision six disposable owners and their same-browser peers for two layers.

    Called only after cutover's empty-state preparation and candidate start. Failed
    attempts retain private evidence and are restored by the existing cutover owner.
    No provider credentials, login profiles or caller-selected commands are needed.
    """
    from .phase2_cutover import RESTORE_PLAN_SCHEMA

    profile, errors = load_profile(source)
    if errors:
        raise QualificationSetupError("Qualification source profile is unavailable")
    restore_path = attempt / "restore-plan.json"
    restore = json.loads(restore_path.read_text())
    if restore.get("schema") != RESTORE_PLAN_SCHEMA or restore.get("candidate_sha") != candidate_sha:
        raise QualificationSetupError("Qualification setup is not bound to this candidate")
    measurements = profile.get("measurements")
    if not isinstance(measurements, dict) or any(
        not isinstance(measurements.get(layer), dict)
        or measurements[layer].get("https_origin", "").rstrip("/") != G7_PRODUCTION_ORIGIN
        for layer in ("deployed", "pre_admission")
    ):
        raise QualificationSetupError("Qualification layers require the canonical HTTPS origin")
    root = attempt / "acceptance-private"
    root.mkdir(mode=0o700)  # Exclusive: a failed attempt is never silently reused.
    forbidden = {}
    seen_owners, seen_credentials = set(), set()
    for layer in ("deployed", "pre_admission"):
        config = dict(measurements[layer])
        directory = root / layer
        directory.mkdir(mode=0o700)
        # No redirect or TLS bypass: the response must come from the tested origin.
        with httpx.Client(base_url=G7_PRODUCTION_ORIGIN, timeout=30, follow_redirects=False) as client:
            for role in ("a", "b", "revoked_probe"):
                owner, credential = _bootstrap(client)
                if owner in seen_owners or credential in seen_credentials:
                    raise QualificationSetupError("Independent qualification workspaces were merged")
                seen_owners.add(owner)
                seen_credentials.add(credential)
                path = directory / f"account-{role}.cookie"
                _private_once(path, credential.encode())
                config[f"account_{role}_cookie_file"] = str(path)
                prefix = "" if layer == "deployed" else "pre_admission_"
                forbidden[f"{prefix}account_{role}_session_cookie"] = str(path)
        for role in ("a", "b"):
            # Tabs share one browser cookie; distinct credentials would invent a
            # sign-in/linking policy that this product deliberately does not have.
            config[f"account_{role}_peer_cookie_file"] = config[f"account_{role}_cookie_file"]
            path = directory / f"account-{role}.sentinel"
            _private_once(path, f"moss-{layer}-{role}-{secrets.token_urlsafe(24)}".encode())
            forbidden[f"{prefix}account_{role}_sentinel"] = str(path)
            config[f"account_{role}_sentinel_file"] = str(path)
        config["cutover_restore_plan"] = str(restore_path)
        measurements[layer] = config
    # All qualification secrets are generated above. Retired OAuth secrets and
    # manually copied cookies are not content-boundary prerequisites anymore.
    profile["forbidden_files"] = forbidden
    path = root / "profile.json"
    _private_once(path, (json.dumps(profile, indent=2, sort_keys=True) + "\n").encode())
    return path
