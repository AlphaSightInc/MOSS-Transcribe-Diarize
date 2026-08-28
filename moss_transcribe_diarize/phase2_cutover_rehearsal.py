"""Mechanical isolated rehearsal of Phase-1 block, archive, activation, and restore."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
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


def _tree_projection(root: Path) -> dict[str, tuple[str, int, bytes | str]]:
    projection: dict[str, tuple[str, int, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        mode = stat.S_IMODE(path.lstat().st_mode)
        if path.is_symlink():
            projection[relative] = ("symlink", mode, os.readlink(path))
        elif path.is_dir():
            projection[relative] = ("directory", mode, b"")
        elif path.is_file():
            projection[relative] = ("file", mode, path.read_bytes())
        else:
            raise ValueError("isolated host contains an unsupported member")
    return projection


def _runtime_statuses(marker: Path, rows: object) -> list[dict[str, object]]:
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("cutover rehearsal requires both Phase-1 runtime views")
    statuses: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "name",
            "entrants",
            "active_live",
            "active_jobs",
            "queued_jobs",
        }:
            raise ValueError("Phase-1 runtime fixture is malformed")
        statuses.append(
            {
                **row,
                "creation_state": "quiesced" if marker.is_file() else "open",
            }
        )
    return statuses


def _write_fixture_tree(root: Path, files: object) -> None:
    if not isinstance(files, dict) or not files:
        raise ValueError("cutover rehearsal requires nonempty Phase-1 state")
    for relative, content in files.items():
        if (
            not isinstance(relative, str)
            or not isinstance(content, str)
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
        ):
            raise ValueError("Phase-1 snapshot fixture member is invalid")
        destination = root / relative
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        destination.chmod(0o600)


def _candidate_paths(candidate: object) -> tuple[Path, Path, Path, Path]:
    if (
        not isinstance(candidate, dict)
        or candidate.get("schema") != "moss-account-candidate.v1"
        or candidate.get("activation_state") != "staged_inert"
    ):
        raise ValueError("cutover rehearsal requires one staged candidate manifest")
    values = tuple(
        candidate.get(key)
        for key in ("release", "release_launcher", "web_unit_path", "vllm_unit_path")
    )
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("staged candidate manifest lacks install paths")
    release, launcher, web_unit, vllm_unit = (Path(str(value)).resolve() for value in values)
    if (
        not release.is_dir()
        or launcher != release / "bin/mtd-account-web"
        or not launcher.is_file()
        or not web_unit.is_file()
        or not vllm_unit.is_file()
    ):
        raise ValueError("staged candidate release is incomplete")
    expected_digests = {
        launcher: candidate.get("release_launcher_sha256"),
        web_unit: candidate.get("web_unit_sha256"),
        vllm_unit: candidate.get("vllm_unit_sha256"),
    }
    if any(
        not isinstance(expected, str)
        or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        for path, expected in expected_digests.items()
    ):
        raise ValueError("staged candidate install bytes do not match its manifest")
    return release, launcher, web_unit, vllm_unit


def rehearse(*, original_fixture: Path, candidate_manifest: Path) -> dict[str, object]:
    original_payload = json.loads(original_fixture.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    if original_payload.get("schema") != "moss-isolated-cutover-fixture.v2":
        raise ValueError("cutover rehearsal fixture schema mismatch")
    release, launcher, web_unit, vllm_unit = _candidate_paths(candidate)
    observed_steps: list[str] = []

    with tempfile.TemporaryDirectory(prefix="moss-cutover-rehearsal-") as directory:
        root = Path(directory)
        archive_root = root / "host"
        control_root = root / "control"
        control_root.mkdir(mode=0o700)
        marker = control_root / "phase1-creation-quiesced"
        _write_fixture_tree(archive_root, original_payload.get("snapshot_files"))
        vllm_runtime_relative = original_payload.get("vllm_runtime_file")
        if (
            not isinstance(vllm_runtime_relative, str)
            or Path(vllm_runtime_relative).is_absolute()
            or ".." in Path(vllm_runtime_relative).parts
        ):
            raise ValueError("cutover rehearsal vLLM runtime identity is absent")
        vllm_runtime = archive_root / vllm_runtime_relative
        if not vllm_runtime.is_file():
            raise ValueError("cutover rehearsal vLLM runtime identity is absent")
        original_vllm_runtime = vllm_runtime.read_bytes()
        phase1_release = archive_root / "releases/phase1"
        phase1_release.mkdir(mode=0o700, parents=True)
        (phase1_release / "identity.txt").write_text(
            str(original_payload.get("service_identity")), encoding="utf-8"
        )
        current = archive_root / "account-current"
        current.symlink_to(phase1_release)
        original_projection = _tree_projection(archive_root)

        marker.write_text("moss-phase1-creation-quiesced-v1\n", encoding="utf-8")
        marker.chmod(0o600)
        observed_steps.append("block")
        blocked = _runtime_statuses(marker, original_payload.get("runtime_views"))
        if any(
            row["creation_state"] != "quiesced"
            or any(
                row[key] != 0
                for key in ("entrants", "active_live", "active_jobs", "queued_jobs")
            )
            for row in blocked
        ):
            raise ValueError("both Phase-1 runtime views are not quiesced and drained")
        observed_steps.append("drain")

        snapshot = root / "phase1-complete.tar"
        with tarfile.open(snapshot, mode="x") as archive:
            archive.add(archive_root, arcname="host", recursive=True)
        if not snapshot.is_file() or snapshot.stat().st_size <= 0:
            raise RuntimeError("Phase-1 snapshot archive is empty")
        observed_steps.append("snapshot")

        next_pointer = archive_root / ".account-current.next"
        next_pointer.symlink_to(release)
        os.replace(next_pointer, current)
        unit_root = archive_root / "systemd"
        unit_root.mkdir(mode=0o700, exist_ok=True)
        shutil.copyfile(web_unit, unit_root / "moss-web.service")
        shutil.copyfile(vllm_unit, unit_root / "moss-vllm.service")
        observed_steps.append("install")
        installed = (
            current.resolve() == release
            and (current / "bin/mtd-account-web").resolve() == launcher
            and (unit_root / "moss-web.service").read_bytes() == web_unit.read_bytes()
            and (unit_root / "moss-vllm.service").read_bytes() == vllm_unit.read_bytes()
        )
        if not installed:
            raise RuntimeError("candidate installation verification failed")
        observed_steps.append("verify")

        forced_failure = False
        try:
            raise RuntimeError("injected post-install cutover failure")
        except RuntimeError as exc:
            if str(exc) != "injected post-install cutover failure":
                raise
            forced_failure = True
            observed_steps.append("forced_failure")
        vllm_runtime_mutations = int(vllm_runtime.read_bytes() != original_vllm_runtime)
        shutil.rmtree(archive_root)
        with tarfile.open(snapshot, mode="r") as archive:
            members = archive.getmembers()
            if any(
                Path(member.name).is_absolute() or ".." in Path(member.name).parts
                for member in members
            ):
                raise ValueError("snapshot archive contains an unsafe member")
            archive.extractall(root)
        marker.unlink()
        observed_steps.append("restore")
        restored_projection = _tree_projection(archive_root)
        vllm_runtime_mutations += int(
            (archive_root / vllm_runtime_relative).read_bytes()
            != original_vllm_runtime
        )
        observed_steps.append("prove_original")

        original_restored = restored_projection == original_projection
        candidate_pointer_absent = current.resolve() != release
        snapshot_bytes = snapshot.stat().st_size

    return {
        "schema": "moss-phase2-cutover-rehearsal.v2",
        "production": False,
        "steps": observed_steps,
        "runtime_views": len(blocked),
        "all_views_quiesced_and_zero": True,
        "snapshot_bytes": snapshot_bytes,
        "candidate_installed_and_verified": installed,
        "forced_failure_observed": forced_failure,
        "original_restored": original_restored,
        "candidate_pointer_absent": candidate_pointer_absent,
        "vllm_runtime_mutations": vllm_runtime_mutations,
        "passed": (
            tuple(observed_steps) == STEPS
            and len(blocked) == 2
            and snapshot_bytes > 0
            and installed
            and forced_failure
            and original_restored
            and candidate_pointer_absent
            and vllm_runtime_mutations == 0
        ),
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
