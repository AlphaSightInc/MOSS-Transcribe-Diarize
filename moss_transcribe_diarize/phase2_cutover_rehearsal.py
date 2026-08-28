"""Isolated mechanical rehearsal of the Phase-1 to Account release pointer rollback."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


STEPS = (
    "block",
    "drain",
    "snapshot",
    "install",
    "verify",
    "forced_failure",
    "restore",
    "prove_original",
)


def rehearse(*, original_fixture: Path, candidate_manifest: Path) -> dict[str, object]:
    original_payload = json.loads(original_fixture.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    if original_payload.get("schema") != "moss-isolated-cutover-fixture.v1":
        raise ValueError("cutover rehearsal fixture schema mismatch")
    if candidate.get("schema") != "moss-account-candidate.v1" or candidate.get(
        "activation_state"
    ) != "staged_inert":
        raise ValueError("cutover rehearsal requires one staged candidate manifest")
    zero_fields = ("entrants", "active_live", "active_jobs", "queued_jobs")
    if any(original_payload.get(field) != 0 for field in zero_fields):
        raise ValueError("cutover rehearsal fixture is not drained")
    original_bytes = original_fixture.read_bytes()
    observed_steps: list[str] = []

    with tempfile.TemporaryDirectory(prefix="moss-cutover-rehearsal-") as directory:
        root = Path(directory)
        state = root / "phase1.json"
        snapshot = root / "phase1.snapshot"
        current = root / "account-current"
        state.write_bytes(original_bytes)
        blocked = dict(original_payload)
        blocked["creation_blocked"] = True
        state.write_text(json.dumps(blocked, sort_keys=True), encoding="utf-8")
        observed_steps.append("block")
        observed_steps.append("drain")
        snapshot.write_bytes(original_bytes)
        observed_steps.append("snapshot")
        current.symlink_to(str(candidate["release"]))
        observed_steps.append("install")
        if current.readlink().as_posix() != str(candidate["release"]):
            raise RuntimeError("candidate pointer verification failed")
        observed_steps.append("verify")
        # The rehearsal deliberately rejects admission, then exercises whole restore.
        forced_failure = True
        observed_steps.append("forced_failure")
        current.unlink()
        state.write_bytes(snapshot.read_bytes())
        observed_steps.append("restore")
        restored_bytes = state.read_bytes()
        observed_steps.append("prove_original")
        pointer_absent = not current.exists() and not current.is_symlink()

    return {
        "schema": "moss-phase2-cutover-rehearsal.v1",
        "production": False,
        "steps": observed_steps,
        "forced_failure_observed": forced_failure,
        "original_bytes": len(original_bytes),
        "restored_bytes": len(restored_bytes),
        "original_restored": restored_bytes == original_bytes,
        "candidate_pointer_absent": pointer_absent,
        "vllm_runtime_mutations": 0,
        "passed": tuple(observed_steps) == STEPS
        and forced_failure
        and restored_bytes == original_bytes
        and pointer_absent,
    }


def write_rehearsal(payload: dict[str, object], output: Path) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        view = memoryview(encoded)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("write returned no progress")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
