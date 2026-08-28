#!/usr/bin/env python3
"""Measure the minimum crash-restorable Phase-2 cutover state machine."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path


MUTATIONS = (
    "blocked",
    "drained",
    "old_stopped",
    "snapshotted",
    "activated",
    "units_swapped",
    "candidate_started",
)


def write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("write made no progress")
        view = view[written:]


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def append_event(path: Path, phase: str, **state: object) -> None:
    payload = (json.dumps({"phase": phase, **state}, sort_keys=True) + "\n").encode()
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        write_all(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    fsync_dir(path.parent)


def read_events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def projection(root: Path) -> dict[str, tuple[str, bytes | str]]:
    rows: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            rows[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            rows[relative] = ("directory", b"")
    return rows


def snapshot_projection(host: "Host") -> dict[str, object]:
    rows: dict[str, object] = {}
    for role, path in host.snapshot_roots.items():
        if path.is_dir():
            rows[role] = ("directory", projection(path))
        elif path.is_symlink():
            rows[role] = ("symlink", os.readlink(path))
        else:
            rows[role] = ("file", path.read_bytes())
    return rows


class Host:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.old = root / "old"
        self.release = root / "release"
        self.control = root / "control"
        self.attempt = root / "attempt"
        self.journal = self.attempt / "journal.jsonl"
        self.marker = self.control / "phase1-creation-quiesced"
        self.current = root / "account-current"
        self.units = root / "units"
        self.candidate_roots = root / "candidate-state"
        for path in (self.old, self.release / "bin", self.control, self.units):
            path.mkdir(parents=True, mode=0o700)
        (self.old / "state.db").write_bytes(b"phase1-state")
        (self.old / "moss-web.service").write_bytes(b"old-web")
        (self.old / "moss-vllm.service").write_bytes(b"old-vllm")
        (self.units / "moss-web.service").write_bytes(b"old-web")
        (self.units / "moss-vllm.service").write_bytes(b"old-vllm")
        (self.release / "bin/mtd-account-web").write_bytes(b"candidate-web")
        self.current.symlink_to(self.old)
        live = root / "phase1-live"
        live.mkdir(mode=0o700)
        files = {
            "phase1_provider_manifest": "live-provider-manifest.json",
            "phase1_auth_state": "live-auth.json",
            "phase1_shared_token": "shared-token",
            "phase1_tls_cert": "live.crt",
            "phase1_tls_key": "live.key",
            "phase1_vector_journal": "speaker-vectors.jsonl",
        }
        external = {}
        for role, name in files.items():
            path = live / name
            path.write_bytes(role.encode())
            external[role] = path
        gpu_venv = root / "phase1-gpu-venv"
        model = root / "phase1-model"
        gpu_venv.mkdir(mode=0o700)
        model.mkdir(mode=0o700)
        (gpu_venv / "runtime").write_bytes(b"cold-vllm-runtime")
        (model / "weights").write_bytes(b"cold-model")
        self.snapshot_roots = {
            "phase1_checkout": self.old,
            **external,
            "phase1_gpu_venv": gpu_venv,
            "phase1_model": model,
        }
        self.work = {
            "batch": {"entrants": 1, "active_live": 0, "active_jobs": 1, "queued_jobs": 1},
            "live": {"entrants": 0, "active_live": 2, "active_jobs": 0, "queued_jobs": 0},
        }
        self.phase1_running = True
        self.account_running = False
        self.vllm = {"pid": 3107, "started": 9001, "argv": ("python", "-m", "vllm")}
        self.original_projection = snapshot_projection(self)

    def state(self) -> dict[str, object]:
        return {
            "marker": self.marker.exists(),
            "work": self.work,
            "phase1_running": self.phase1_running,
            "account_running": self.account_running,
            "current": str(self.current.resolve()),
            "vllm": self.vllm,
            "candidate_state_exists": self.candidate_roots.exists(),
        }


class InjectedCrash(RuntimeError):
    pass


def archive_old(host: Host) -> tuple[Path, str, list[str]]:
    snapshot = host.attempt / "phase1.tar"
    with tarfile.open(snapshot, "x") as archive:
        for path in host.snapshot_roots.values():
            archive.add(path, arcname=path.relative_to(host.root).as_posix())
        archive.add(host.units, arcname="units")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    members = [row.name for row in tarfile.open(snapshot).getmembers()]
    return snapshot, digest, members


def restore(host: Host, *, corrupt: bool = False) -> str:
    events = read_events(host.journal)
    if events[-1]["phase"] in {"restored", "preadmission", "SAFE_STOPPED"}:
        raise ValueError("terminal attempt cannot be restored")
    snapshot = host.attempt / "phase1.tar"
    if not snapshot.exists():
        # Before snapshot publication, only the marker and old-process lifecycle can
        # have changed; no host byte has been replaced yet.
        host.marker.unlink(missing_ok=True)
        host.phase1_running = True
        host.account_running = False
        append_event(host.journal, "restored", candidate_quarantined=False)
        return "restored"
    manifest = json.loads((host.attempt / "snapshot.json").read_text())
    if corrupt:
        snapshot.write_bytes(b"corrupt")
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        host.phase1_running = False
        host.account_running = False
        append_event(host.journal, "SAFE_STOPPED", reason="snapshot_digest_mismatch")
        return "SAFE_STOPPED"
    quarantine = host.attempt / "candidate-quarantine"
    if host.candidate_roots.exists():
        host.candidate_roots.rename(quarantine)
    if host.current.exists() or host.current.is_symlink():
        host.current.unlink()
    for path in host.snapshot_roots.values():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    if host.units.exists():
        shutil.rmtree(host.units)
    with tarfile.open(snapshot) as archive:
        members = archive.getmembers()
        if any(
            Path(member.name).is_absolute() or ".." in Path(member.name).parts
            for member in members
        ):
            raise ValueError("snapshot member escapes the restore root")
        archive.extractall(host.root)
    host.current.symlink_to(host.old)
    host.marker.unlink(missing_ok=True)
    host.phase1_running = True
    host.account_running = False
    append_event(host.journal, "restored", candidate_quarantined=quarantine.exists())
    return "restored"


def run(
    host: Host,
    *,
    terminal: str = "preadmission",
    crash_after: str | None = None,
    canary_passes: bool = True,
    attended_evidence: str = "production_browser",
) -> str:
    if terminal not in {"restored", "preadmission"}:
        raise ValueError("terminal must be restored or preadmission")
    host.attempt.mkdir(mode=0o700)
    append_event(
        host.journal,
        "started",
        qualification="G0-G6+G10",
        target_terminal=terminal,
        g7="UNCLAIMED",
    )

    host.marker.write_bytes(b"moss-phase1-creation-quiesced-v1\n")
    host.marker.chmod(0o600)
    append_event(host.journal, "blocked", views=2)
    if crash_after == "blocked":
        raise InjectedCrash("blocked")

    initial_work = sum(sum(row.values()) for row in host.work.values())
    for row in host.work.values():
        for key in row:
            row[key] = 0
    append_event(host.journal, "drained", initial_work=initial_work, final_work=0)
    if crash_after == "drained":
        raise InjectedCrash("drained")

    host.phase1_running = False
    append_event(host.journal, "old_stopped")
    if crash_after == "old_stopped":
        raise InjectedCrash("old_stopped")

    snapshot, digest, members = archive_old(host)
    (host.attempt / "snapshot.json").write_text(
        json.dumps({"archive": snapshot.name, "archive_sha256": digest, "members": members})
    )
    append_event(host.journal, "snapshotted", archive_sha256=digest, members=len(members))
    if crash_after == "snapshotted":
        raise InjectedCrash("snapshotted")

    next_pointer = host.root / ".account-current.next"
    next_pointer.symlink_to(host.release)
    os.replace(next_pointer, host.current)
    append_event(host.journal, "activated")
    if crash_after == "activated":
        raise InjectedCrash("activated")

    (host.units / "moss-web.service").write_bytes(b"candidate-web-unit")
    (host.units / "moss-vllm.service").write_bytes(b"candidate-vllm-unit")
    append_event(host.journal, "units_swapped", vllm_unchanged=True)
    if crash_after == "units_swapped":
        raise InjectedCrash("units_swapped")

    host.candidate_roots.mkdir(mode=0o700)
    (host.candidate_roots / "phase2.sqlite3").write_bytes(b"schema-v1-empty")
    host.account_running = True
    append_event(host.journal, "candidate_started", schema=1, accounts=0, meetings=0)
    if crash_after == "candidate_started":
        raise InjectedCrash("candidate_started")

    if not canary_passes:
        append_event(host.journal, "canary_failed", g7="UNCLAIMED")
        return restore(host)
    append_event(host.journal, "qualification_complete", g7="UNCLAIMED")
    if attended_evidence not in {"production_browser", "deterministic_rehearsal"}:
        append_event(host.journal, "attended_g7_unmeasured", g7="UNCLAIMED")
        return restore(host)
    if attended_evidence == "deterministic_rehearsal" and terminal != "restored":
        append_event(host.journal, "attended_g7_rejected", g7="UNCLAIMED")
        return restore(host)
    append_event(
        host.journal,
        "attended_g7_complete",
        source=attended_evidence,
        g7="PASS" if attended_evidence == "production_browser" else "UNCLAIMED",
    )
    if terminal == "restored":
        append_event(host.journal, "planned_restore", g7="UNCLAIMED")
        return restore(host)
    append_event(host.journal, "preadmission", g7="PASS", admitted_accounts=0)
    return "preadmission"


def main() -> int:
    contract = {
        "structural_question": "Can one forward cutover and one incomplete-attempt restore make every crash boundary truthful without opening admission?",
        "hypothesis": "An fsynced phase journal, one complete snapshot, and one activation pointer are sufficient; uncertainty must remain blocked and stopped.",
        "minimum_primitives": [
            {"name": "phase_journal", "boundary": "orders only durable host mutations", "irreducible": "recovery otherwise cannot distinguish planned from completed effects"},
            {"name": "phase1_block_and_two_view_drain", "boundary": "old-image admission and outstanding work only", "irreducible": "stop alone loses accepted work and an in-process count misses the sibling service"},
            {"name": "complete_snapshot", "boundary": "the nonoverlapping checkout, provider/auth/token/TLS/vector, GPU-runtime, model, unit, and profile roots", "irreducible": "omitting one root or nesting roots permits mixed authentication, runtime, or service state"},
            {"name": "activation_pointer", "boundary": "selects exactly one immutable Account release", "irreducible": "copying a release creates partial activation"},
            {"name": "terminal_outcome", "boundary": "restored, preadmission, or SAFE_STOPPED", "irreducible": "a generic success/failure code cannot state whether authority is open"},
            {"name": "explicit_terminal_target", "boundary": "chooses only full-canary restore or preadmission", "irreducible": "an implicit success target cannot deliberately rehearse the whole rollback"},
            {"name": "candidate_owned_attended_canary", "boundary": "observes real production-origin microphone plus meeting-tab and entire-screen Chrome capture", "irreducible": "Wave-1 qualification or a profile-authored pass report cannot establish attended browser behavior"},
        ],
        "invariants": ["only candidate-owned production-browser evidence can end preadmission with G7 PASS", "deterministic rehearsal evidence remains G7 UNCLAIMED", "vLLM PID/start/argv never change", "candidate admission remains empty", "all snapshot roots are explicit and nonoverlapping", "known failures restore whole old state", "uncertain restore keeps creation blocked and services stopped"],
        "assumptions_unknowns": ["real OAuth, trusted TLS, Chrome microphone/tab/screen, and the remote host remain UNMEASURED in this prototype", "the production command must obtain attended evidence directly rather than consume a caller-authored report"],
        "falsifier": "any required old authority/runtime/model root is absent or nested, any crash cannot restore exactly, any corrupt archive reopens a service, a candidate root is discarded rather than quarantined, absent/synthetic G7 evidence reaches preadmission, or preadmission admits an Account",
        "tool_decision": [
            {"experiment": "actual filesystem journal/archive/pointer crash matrix", "necessity": "labels cannot expose partial mutation", "decision_change": "any non-restorable boundary requires a different ordering or primitive"},
            {"experiment": "corrupt archive restore", "necessity": "tests the only uncertainty outcome", "decision_change": "any service restart rejects SAFE_STOPPED handling"},
            {"experiment": "successful canary followed by planned whole restore", "necessity": "proves restored is a deliberate terminal rather than a disguised canary failure", "decision_change": "any skipped canary or mixed old state rejects the terminal-target seam"},
            {"experiment": "explicit nonoverlapping old-image inventory", "necessity": "a checkout-only archive cannot restore external authority or the cold GPU runtime/model", "decision_change": "any missing or nested root rejects snapshot construction before host mutation"},
            {"experiment": "absent versus deterministic versus production-browser attended evidence", "necessity": "Wave-1 success does not measure the attended Chrome canary", "decision_change": "if missing or synthetic evidence reaches preadmission, reject the terminal policy"},
        ],
        "one_command": "PYTHONDONTWRITEBYTECODE=1 bash prototypes/phase2-cutover/run.sh",
    }
    results: dict[str, object] = {}
    assertions: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="moss-cutover-probe-") as directory:
        root = Path(directory)
        success = Host(root / "success")
        before_vllm = dict(success.vllm)
        inventory_paths = tuple(success.snapshot_roots.values())
        inventory_nonoverlap = all(
            left not in right.parents and right not in left.parents
            for index, left in enumerate(inventory_paths)
            for right in inventory_paths[index + 1 :]
        )
        results["snapshot_inventory"] = {
            "roles": sorted(success.snapshot_roots),
            "nonoverlapping": inventory_nonoverlap,
        }
        assertions.extend((len(success.snapshot_roots) == 9, inventory_nonoverlap))
        results["success"] = {"terminal": run(success), "state": success.state(), "events": read_events(success.journal)}
        success_events = read_events(success.journal)
        assertions.extend((results["success"]["terminal"] == "preadmission", success_events[-1]["g7"] == "PASS", success.vllm == before_vllm, success.marker.exists(), not success.phase1_running, success.account_running))

        planned = Host(root / "planned-restore")
        planned_original = dict(planned.original_projection)
        planned_vllm = dict(planned.vllm)
        planned_terminal = run(
            planned,
            terminal="restored",
            attended_evidence="deterministic_rehearsal",
        )
        planned_events = read_events(planned.journal)
        results["planned_restore"] = {
            "terminal": planned_terminal,
            "state": planned.state(),
            "events": planned_events,
        }
        planned_phases = [row["phase"] for row in planned_events]
        assertions.extend(
            (
                planned_terminal == "restored",
                snapshot_projection(planned) == planned_original,
                planned.phase1_running,
                not planned.account_running,
                not planned.marker.exists(),
                planned.vllm == planned_vllm,
                planned_phases.index("qualification_complete")
                < planned_phases.index("planned_restore"),
                next(
                    row for row in planned_events if row["phase"] == "attended_g7_complete"
                )["g7"]
                == "UNCLAIMED",
            )
        )

        missing_g7 = Host(root / "missing-g7")
        missing_original = dict(missing_g7.original_projection)
        missing_terminal = run(missing_g7, attended_evidence="absent")
        results["missing_g7"] = {
            "terminal": missing_terminal,
            "state": missing_g7.state(),
            "events": read_events(missing_g7.journal),
        }
        assertions.extend(
            (
                missing_terminal == "restored",
                snapshot_projection(missing_g7) == missing_original,
                missing_g7.phase1_running,
                not missing_g7.marker.exists(),
            )
        )

        fake_g7 = Host(root / "fake-g7")
        fake_original = dict(fake_g7.original_projection)
        fake_terminal = run(
            fake_g7,
            terminal="preadmission",
            attended_evidence="deterministic_rehearsal",
        )
        results["synthetic_g7"] = {
            "terminal": fake_terminal,
            "state": fake_g7.state(),
            "events": read_events(fake_g7.journal),
        }
        assertions.extend(
            (
                fake_terminal == "restored",
                snapshot_projection(fake_g7) == fake_original,
                fake_g7.phase1_running,
                not fake_g7.marker.exists(),
            )
        )

        failed = Host(root / "failed")
        failed_original = dict(failed.original_projection)
        results["canary_failure"] = {"terminal": run(failed, canary_passes=False), "state": failed.state(), "events": read_events(failed.journal)}
        assertions.extend((results["canary_failure"]["terminal"] == "restored", snapshot_projection(failed) == failed_original, failed.phase1_running, not failed.marker.exists(), (failed.attempt / "candidate-quarantine").is_dir()))

        crash_rows = []
        for phase in MUTATIONS:
            crashed = Host(root / f"crash-{phase}")
            original = dict(crashed.original_projection)
            try:
                run(crashed, crash_after=phase)
            except InjectedCrash:
                terminal = restore(crashed)
            crash_rows.append({"phase": phase, "terminal": terminal, "restored": snapshot_projection(crashed) == original, "vllm": crashed.vllm})
            assertions.extend((terminal == "restored", snapshot_projection(crashed) == original, crashed.phase1_running, not crashed.marker.exists()))
        results["crash_matrix"] = crash_rows

        uncertain = Host(root / "uncertain")
        try:
            run(uncertain, crash_after="candidate_started")
        except InjectedCrash:
            terminal = restore(uncertain, corrupt=True)
        results["uncertain"] = {"terminal": terminal, "state": uncertain.state(), "events": read_events(uncertain.journal)}
        assertions.extend((terminal == "SAFE_STOPPED", uncertain.marker.exists(), not uncertain.phase1_running, not uncertain.account_running))

    verdict = {"contract": contract, "results": results, "assertions_passed": sum(assertions), "assertions_total": len(assertions), "verdict": "PASS" if all(assertions) else "FAIL"}
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 0 if all(assertions) else 1


if __name__ == "__main__":
    raise SystemExit(main())
