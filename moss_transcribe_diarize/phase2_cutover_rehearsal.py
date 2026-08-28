"""Mechanical isolated rehearsal of Phase-1 block, archive, activation, and restore."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path

from moss_transcribe_diarize.installed_candidate import validated_candidate_artifacts


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


def _write_runtime_views(root: Path, rows: object) -> None:
    statuses = _runtime_statuses(root / ".marker-absent", rows)
    root.mkdir(mode=0o700, parents=True)
    for index, status in enumerate(statuses):
        payload = {key: value for key, value in status.items() if key != "creation_state"}
        (root / f"{index}.json").write_text(json.dumps(payload), encoding="utf-8")


def _read_runtime_views(marker: Path, root: Path) -> list[dict[str, object]]:
    rows = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.json"))]
    return _runtime_statuses(marker, rows)


def _work_units(rows: list[dict[str, object]]) -> int:
    return sum(
        int(row[key])
        for row in rows
        for key in ("entrants", "active_live", "active_jobs", "queued_jobs")
    )


def _try_admit(marker: Path, runtime_root: Path) -> bool:
    if marker.is_file():
        return False
    first = sorted(runtime_root.glob("*.json"))[0]
    row = json.loads(first.read_text(encoding="utf-8"))
    row["entrants"] = int(row["entrants"]) + 1
    first.write_text(json.dumps(row), encoding="utf-8")
    return True


def _drain_one(runtime_root: Path) -> bool:
    for path in sorted(runtime_root.glob("*.json")):
        row = json.loads(path.read_text(encoding="utf-8"))
        for key in ("entrants", "queued_jobs", "active_jobs", "active_live"):
            if int(row[key]) > 0:
                row[key] = int(row[key]) - 1
                path.write_text(json.dumps(row), encoding="utf-8")
                return True
    return False


def rehearse(*, original_fixture: Path, candidate_manifest: Path) -> dict[str, object]:
    original_payload = json.loads(original_fixture.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_manifest.read_text(encoding="utf-8"))
    if original_payload.get("schema") != "moss-isolated-cutover-fixture.v2":
        raise ValueError("cutover rehearsal fixture schema mismatch")
    install = validated_candidate_artifacts(candidate)
    observed_steps: list[str] = []

    with tempfile.TemporaryDirectory(prefix="moss-cutover-rehearsal-") as directory:
        root = Path(directory)
        archive_root = root / "host"
        control_root = root / "control"
        control_root.mkdir(mode=0o700)
        marker = control_root / "phase1-creation-quiesced"
        runtime_root = control_root / "runtime-views"
        _write_runtime_views(runtime_root, original_payload.get("runtime_views"))
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

        before_block = _read_runtime_views(marker, runtime_root)
        initial_work_units = _work_units(before_block)
        if (
            initial_work_units <= 0
            or any(row["creation_state"] != "open" for row in before_block)
        ):
            raise ValueError("cutover rehearsal requires accepted Phase-1 work before block")

        marker.write_text("moss-phase1-creation-quiesced-v1\n", encoding="utf-8")
        marker.chmod(0o600)
        observed_steps.append("block")
        blocked_before_drain = _read_runtime_views(marker, runtime_root)
        post_block_work_units = _work_units(blocked_before_drain)
        post_block_admission_rejected = not _try_admit(marker, runtime_root)
        drain_transitions = 0
        while _drain_one(runtime_root):
            drain_transitions += 1
        blocked = _read_runtime_views(marker, runtime_root)
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
        next_pointer.symlink_to(install.release)
        os.replace(next_pointer, current)
        unit_root = archive_root / "systemd"
        unit_root.mkdir(mode=0o700, exist_ok=True)
        for name, source in install.units.items():
            shutil.copyfile(source, unit_root / name)
        observed_steps.append("install")
        installed = (
            current.resolve() == install.release
            and all(
                (current / f"bin/{name}").read_bytes() == source.read_bytes()
                for name, source in install.launchers.items()
            )
            and all(
                (unit_root / name).read_bytes() == source.read_bytes()
                for name, source in install.units.items()
            )
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
        candidate_pointer_absent = current.resolve() != install.release
        snapshot_bytes = snapshot.stat().st_size

    return {
        "schema": "moss-phase2-cutover-rehearsal.v2",
        "production": False,
        "steps": observed_steps,
        "runtime_views": len(blocked),
        "initial_work_units": initial_work_units,
        "post_block_work_units": post_block_work_units,
        "post_block_admission_rejected": post_block_admission_rejected,
        "drain_transitions": drain_transitions,
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
            and initial_work_units > 0
            and post_block_work_units == initial_work_units
            and post_block_admission_rejected
            and drain_transitions == initial_work_units
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
