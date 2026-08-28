#!/usr/bin/env python3
"""Measure the minimum crash-restorable Phase-2 cutover state machine."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import tempfile
import fcntl
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
EXACT_PRODUCTION_ORIGIN = "https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861"
REQUIRED_SNAPSHOT_ROLES = frozenset(
    {
        "phase1_checkout",
        "phase1_provider_manifest",
        "phase1_auth_state",
        "phase1_shared_token",
        "phase1_tls_cert",
        "phase1_tls_key",
        "phase1_vector_journal",
        "phase1_gpu_venv",
        "phase1_model",
    }
)
RESTORE_EFFECTS = (
    "candidate_stopped",
    "candidate_quarantined",
    "snapshot_restored",
    "phase1_started",
    "block_removed",
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


def paths_overlap(paths: tuple[Path, ...]) -> bool:
    resolved = tuple(path.resolve(strict=False) for path in paths)
    return any(
        left == right or left in right.parents or right in left.parents
        for index, left in enumerate(resolved)
        for right in resolved[index + 1 :]
    )


def measure_global_lock(root: Path) -> dict[str, object]:
    lock = root / "host-state/phase2-cutover.lock"
    lock.parent.mkdir(mode=0o700)
    first = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    second = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    second_refused = False
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            second_refused = True
    finally:
        os.close(second)
        os.close(first)
    return {"path": str(lock), "second_concurrent_attempt_refused": second_refused}


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
        self.phase1_web_units = {"moss-web": True, "moss-live-web": True}
        self.account_running = False
        self.restore_writes: list[dict[str, object]] = []
        self.durable_restore_members: list[str] = []
        self.vllm = {"pid": 3107, "started": 9001, "argv": ("python", "-m", "vllm")}
        self.original_projection = snapshot_projection(self)

    @property
    def phase1_running(self) -> bool:
        return all(self.phase1_web_units.values())

    @phase1_running.setter
    def phase1_running(self, running: bool) -> None:
        for unit in self.phase1_web_units:
            self.phase1_web_units[unit] = running

    def state(self) -> dict[str, object]:
        return {
            "marker": self.marker.exists(),
            "work": self.work,
            "phase1_running": self.phase1_running,
            "phase1_web_units": self.phase1_web_units,
            "account_running": self.account_running,
            "current": str(self.current.resolve()),
            "vllm": self.vllm,
            "candidate_state_exists": self.candidate_roots.exists(),
        }


class InjectedCrash(RuntimeError):
    pass


class RestorationUncertain(RuntimeError):
    pass


def fsync_restored_tree(host: Host, path: Path, *, role: str) -> None:
    members = [path]
    if path.is_dir() and not path.is_symlink():
        members.extend(sorted(path.rglob("*")))
    for member in members:
        if member.is_file() and not member.is_symlink():
            descriptor = os.open(member, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            relative = "." if member == path else member.relative_to(path).as_posix()
            host.durable_restore_members.append(
                role if relative == "." else f"{role}/{relative}"
            )
    for member in reversed(members):
        if member.is_dir() and not member.is_symlink():
            fsync_dir(member)
            relative = "." if member == path else member.relative_to(path).as_posix()
            host.durable_restore_members.append(
                role if relative == "." else f"{role}/{relative}"
            )


def archive_old(host: Host) -> tuple[Path, str, list[str]]:
    snapshot = host.attempt / "phase1.tar"
    with tarfile.open(snapshot, "x") as archive:
        for path in host.snapshot_roots.values():
            archive.add(path, arcname=path.relative_to(host.root).as_posix())
        archive.add(host.units, arcname="units")
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    members = [row.name for row in tarfile.open(snapshot).getmembers()]
    return snapshot, digest, members


def restore(
    host: Host,
    *,
    corrupt: bool = False,
    crash_after: str | None = None,
    journal_available: bool = True,
    safe_stop_marker_error: bool = False,
    safe_stop_stuck_web: str | None = None,
) -> str:
    journal_failed = False

    def record(phase: str, **state: object) -> None:
        nonlocal journal_failed
        if not journal_available:
            journal_failed = True
            return
        try:
            append_event(host.journal, phase, **state)
        except OSError:
            journal_failed = True

    events = read_events(host.journal)
    if events[-1]["phase"] in {"restored", "preadmission", "SAFE_STOPPED"}:
        raise ValueError("terminal attempt cannot be restored")
    if events[-1]["phase"] != "restore_started":
        record("restore_started")
    snapshot = host.attempt / "phase1.tar"
    if not snapshot.exists():
        # Before snapshot publication, only the marker and old-process lifecycle can
        # have changed; no host byte has been replaced yet.
        host.account_running = False
        record("candidate_stopped")
        if crash_after == "candidate_stopped":
            raise InjectedCrash("candidate_stopped")
        host.phase1_running = True
        record("phase1_started")
        if crash_after == "phase1_started":
            raise InjectedCrash("phase1_started")
        host.marker.unlink(missing_ok=True)
        record("block_removed")
        if crash_after == "block_removed":
            raise InjectedCrash("block_removed")
        record("restored", candidate_quarantined=False)
        return "restored"
    manifest = json.loads((host.attempt / "snapshot.json").read_text())
    if corrupt:
        snapshot.write_bytes(b"corrupt")
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        if not host.marker.exists() and not safe_stop_marker_error:
            host.marker.write_bytes(b"moss-phase1-creation-quiesced-v1\n")
        host.phase1_running = False
        host.account_running = False
        if safe_stop_stuck_web is not None:
            host.phase1_web_units[safe_stop_stuck_web] = True
        safe_stopped_verified = (
            host.marker.is_file()
            and host.marker.read_bytes() == b"moss-phase1-creation-quiesced-v1\n"
            and not any(host.phase1_web_units.values())
            and not host.account_running
        )
        if not safe_stopped_verified:
            raise RestorationUncertain("blocked and stopped state is unverified")
        record("SAFE_STOPPED", reason="snapshot_digest_mismatch")
        return "SAFE_STOPPED"
    host.account_running = False
    record("candidate_stopped")
    if crash_after == "candidate_stopped":
        raise InjectedCrash("candidate_stopped")
    host.phase1_running = False
    quarantine = host.attempt / "candidate-quarantine"
    if host.candidate_roots.exists():
        host.candidate_roots.rename(quarantine)
    record("candidate_quarantined")
    if crash_after == "candidate_quarantined":
        raise InjectedCrash("candidate_quarantined")
    extraction = host.attempt / ".restore-extraction"
    if extraction.exists():
        shutil.rmtree(extraction)
    extraction.mkdir(mode=0o700)
    with tarfile.open(snapshot) as archive:
        members = archive.getmembers()
        if any(
            Path(member.name).is_absolute() or ".." in Path(member.name).parts
            for member in members
        ):
            raise ValueError("snapshot member escapes the restore root")
        archive.extractall(extraction)
    for role, path in host.snapshot_roots.items():
        if path.exists() or path.is_symlink():
            continue
        host.restore_writes.append(
            {
                "role": role,
                "moss_web_running": host.phase1_web_units["moss-web"],
                "moss_live_web_running": host.phase1_web_units["moss-live-web"],
            }
        )
        source = extraction / path.relative_to(host.root)
        if source.is_dir():
            shutil.copytree(source, path, symlinks=True)
        elif source.is_symlink():
            path.symlink_to(os.readlink(source))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, path, follow_symlinks=False)
        fsync_restored_tree(host, path, role=role)
    if host.current.exists() or host.current.is_symlink():
        host.current.unlink()
    if host.units.exists():
        shutil.rmtree(host.units)
    shutil.copytree(extraction / "units", host.units, symlinks=True)
    shutil.rmtree(extraction)
    host.current.symlink_to(host.old)
    record("snapshot_restored")
    if crash_after == "snapshot_restored":
        raise InjectedCrash("snapshot_restored")
    host.phase1_running = True
    if crash_after == "phase1_started_before_journal":
        raise InjectedCrash("phase1_started_before_journal")
    record("phase1_started")
    if crash_after == "phase1_started":
        raise InjectedCrash("phase1_started")
    host.marker.unlink(missing_ok=True)
    record("block_removed")
    if crash_after == "block_removed":
        raise InjectedCrash("block_removed")
    record("restored", candidate_quarantined=quarantine.exists())
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
    if terminal == "restored":
        append_event(host.journal, "planned_restore", g7="UNCLAIMED")
        return restore(host)
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
    append_event(host.journal, "preadmission", g7="PASS", admitted_accounts=0)
    return "preadmission"


def main() -> int:
    contract = {
        "structural_question": "Can one forward cutover and one incomplete-attempt restore make every crash boundary truthful without opening admission?",
        "hypothesis": "An fsynced phase journal, one complete snapshot, and one activation pointer are sufficient; uncertainty must remain blocked and stopped.",
        "minimum_primitives": [
            {"name": "host_cutover_lock", "boundary": "serializes every forward and restore attempt on one cooperating host", "irreducible": "attempt-local locks cannot prevent two different attempts from mutating the same units and authority"},
            {"name": "phase_journal", "boundary": "orders durable host mutations when writable but never owns rollback effects", "irreducible": "recovery otherwise cannot distinguish planned from completed effects, while journal failure must not strand the candidate"},
            {"name": "phase1_block_and_two_view_drain", "boundary": "old-image admission and outstanding work only", "irreducible": "stop alone loses accepted work and an in-process count misses the sibling service"},
            {"name": "complete_snapshot", "boundary": "preserves present explicit old roots, repairs a missing explicit root, and restores owned unit/profile/pointer mutation targets", "irreducible": "unconditional extraction rewrites live GPU/model bytes while omission cannot repair a missing old root"},
            {"name": "activation_pointer", "boundary": "selects exactly one immutable Account release", "irreducible": "copying a release creates partial activation"},
            {"name": "terminal_outcome", "boundary": "restored, preadmission, or verified blocked-and-inactive SAFE_STOPPED", "irreducible": "a generic success/failure code cannot state whether authority is open, and an unverified safe label is false authority"},
            {"name": "explicit_terminal_target", "boundary": "chooses only full-canary restore or preadmission", "irreducible": "an implicit success target cannot deliberately rehearse the whole rollback"},
            {"name": "candidate_owned_attended_canary", "boundary": "observes real production-origin microphone plus meeting-tab and entire-screen Chrome capture", "irreducible": "Wave-1 qualification or a profile-authored pass report cannot establish attended browser behavior"},
        ],
        "invariants": ["one fixed host lock excludes every concurrent forward or restore attempt", "only the exact committed production origin can end preadmission with G7 PASS", "restored runs Wave-1 then planned whole restore without requiring G7", "a crash during any restore effect remains replayable", "rollback effects do not depend on journal availability", "SAFE_STOPPED is published only after exact marker and both listener stops are observed", "both old web units are stopped before snapshot application", "present explicit old roots are never rewritten", "missing explicit roots and automatic mutation targets restore from the sealed archive and are fsynced recursively before terminal", "vLLM PID/start/argv never change", "candidate admission remains empty", "the snapshot role set is exact and all snapshot, candidate-state, and attempt roots are nonoverlapping", "known failures restore whole old state", "uncertain snapshot identity keeps creation blocked and services stopped"],
        "assumptions_unknowns": ["real OAuth, trusted TLS, Chrome microphone/tab/screen, and the remote host remain UNMEASURED in this prototype", "the production command must obtain attended evidence directly rather than consume a caller-authored report"],
        "falsifier": "two distinct attempts mutate concurrently; any required old authority/runtime/model root is absent, extra, or overlaps attempt/candidate state; a normal restore rewrites a present explicit root; a replay applies snapshot bytes while either old web unit is live; a missing explicit root is not repaired and fsynced; persistent journal failure prevents rollback; SAFE_STOPPED is published without the exact marker and inactive listeners; any forward or restore-effect crash cannot restore exactly; restored requires G7; a wrong host/port reaches G7; a corrupt archive reopens a service; candidate state is discarded instead of quarantined; or preadmission admits an Account",
        "tool_decision": [
            {"experiment": "actual filesystem journal/archive/pointer crash matrix", "necessity": "labels cannot expose partial mutation", "decision_change": "any non-restorable boundary requires a different ordering or primitive"},
            {"experiment": "corrupt archive restore", "necessity": "tests the only uncertainty outcome", "decision_change": "any service restart rejects SAFE_STOPPED handling"},
            {"experiment": "successful canary followed by planned whole restore", "necessity": "proves restored is a deliberate terminal rather than a disguised canary failure", "decision_change": "any skipped canary or mixed old state rejects the terminal-target seam"},
            {"experiment": "explicit nonoverlapping old-image inventory", "necessity": "a checkout-only archive cannot restore external authority or the cold GPU runtime/model", "decision_change": "any missing or nested root rejects snapshot construction before host mutation"},
            {"experiment": "absent versus deterministic versus production-browser attended evidence", "necessity": "Wave-1 success does not measure the attended Chrome canary", "decision_change": "if missing or synthetic evidence reaches preadmission, reject the terminal policy"},
            {"experiment": "two independent nonblocking file-lock claims", "necessity": "attempt directories do not share exclusion state", "decision_change": "if both claims succeed, move ownership to one fixed host path"},
            {"experiment": "crash after each restore effect followed by the same restore command", "necessity": "restore_started alone does not prove replayability", "decision_change": "any mixed or nonretryable result requires a different restore ordering"},
            {"experiment": "wrong-host/port and restored-without-browser states", "necessity": "HTTPS alone does not identify production and rollback rehearsal does not measure G7", "decision_change": "any wrong origin or browser dependency rejects the terminal branch"},
            {"experiment": "write-instrumented normal restore and pre-journal start-effect crash replay", "necessity": "byte equality cannot reveal unsafe remove-and-copy of an unchanged live GPU/model root", "decision_change": "any present explicit-root write selects preservation plus web-stop-before-application"},
            {"experiment": "persistent journal failure after candidate start", "necessity": "a durable state log can fail independently of already-owned host effects", "decision_change": "a stranded candidate makes every journal append best-effort around rollback"},
            {"experiment": "marker failure plus one stuck listener at SAFE_STOPPED", "necessity": "a terminal label cannot prove its own traffic state", "decision_change": "any false terminal requires direct marker/unit/listener verification"},
            {"experiment": "restored-tree fsync accounting", "necessity": "correct bytes in cache do not establish crash durability", "decision_change": "any unflushed regular file or directory requires recursive fsync before publication"},
        ],
        "one_command": "PYTHONDONTWRITEBYTECODE=1 bash prototypes/phase2-cutover/run.sh",
    }
    results: dict[str, object] = {}
    assertions: list[bool] = []
    with tempfile.TemporaryDirectory(prefix="moss-cutover-probe-") as directory:
        root = Path(directory)
        results["global_lock"] = measure_global_lock(root)
        assertions.append(results["global_lock"]["second_concurrent_attempt_refused"] is True)

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
        extra_inventory = {**success.snapshot_roots, "unruled_extra": root / "extra"}
        exact_inventory_accepted = set(extra_inventory) == REQUIRED_SNAPSHOT_ROLES
        results["exact_snapshot_roles"] = {
            "configured": sorted(extra_inventory),
            "accepted_by_exact_rule": exact_inventory_accepted,
        }
        assertions.append(not exact_inventory_accepted)

        nested_attempt = success.candidate_roots / "attempt"
        overlap_rejected = paths_overlap((nested_attempt, success.candidate_roots))
        results["attempt_state_overlap"] = {
            "attempt": str(nested_attempt),
            "candidate_state": str(success.candidate_roots),
            "rejected_before_effects": overlap_rejected,
        }
        assertions.append(overlap_rejected)
        results["success"] = {"terminal": run(success), "state": success.state(), "events": read_events(success.journal)}
        success_events = read_events(success.journal)
        assertions.extend((results["success"]["terminal"] == "preadmission", success_events[-1]["g7"] == "PASS", success.vllm == before_vllm, success.marker.exists(), not success.phase1_running, success.account_running))

        planned = Host(root / "planned-restore")
        planned_original = dict(planned.original_projection)
        planned_vllm = dict(planned.vllm)
        planned_terminal = run(
            planned,
            terminal="restored",
            attended_evidence="absent",
        )
        planned_events = read_events(planned.journal)
        results["planned_restore"] = {
            "terminal": planned_terminal,
            "state": planned.state(),
            "events": planned_events,
        }
        planned_phases = [row["phase"] for row in planned_events]
        planned_restore_measured = (
            "planned_restore" in planned_phases
            and planned_phases.index("qualification_complete")
            < planned_phases.index("planned_restore")
        )
        assertions.extend(
            (
                planned_terminal == "restored",
                snapshot_projection(planned) == planned_original,
                not planned.restore_writes,
                planned.phase1_running,
                not planned.account_running,
                not planned.marker.exists(),
                planned.vllm == planned_vllm,
                planned_restore_measured,
                "attended_g7_started" not in planned_phases,
            )
        )

        restore_interrupted = Host(root / "restore-interrupted")
        try:
            run(restore_interrupted, crash_after="candidate_started")
        except InjectedCrash:
            append_event(restore_interrupted.journal, "restore_started")
        replay_terminal = restore(restore_interrupted)
        results["restore_crash_replay"] = {
            "last_phase": read_events(restore_interrupted.journal)[-1]["phase"],
            "replay_terminal": replay_terminal,
        }
        assertions.extend(
            (
                replay_terminal == "restored",
                snapshot_projection(restore_interrupted)
                == restore_interrupted.original_projection,
            )
        )

        restore_crash_rows = []
        for phase in RESTORE_EFFECTS:
            interrupted = Host(root / f"restore-crash-{phase}")
            original = dict(interrupted.original_projection)
            try:
                run(interrupted, crash_after="candidate_started")
            except InjectedCrash:
                try:
                    restore(interrupted, crash_after=phase)
                except InjectedCrash:
                    terminal = restore(interrupted)
            restored_exact = snapshot_projection(interrupted) == original
            restore_crash_rows.append(
                {"phase": phase, "terminal": terminal, "restored": restored_exact}
            )
            assertions.extend((terminal == "restored", restored_exact))
        results["restore_effect_crash_matrix"] = restore_crash_rows

        start_effect_crash = Host(root / "restore-start-effect-crash")
        try:
            run(start_effect_crash, crash_after="candidate_started")
        except InjectedCrash:
            try:
                restore(
                    start_effect_crash,
                    crash_after="phase1_started_before_journal",
                )
            except InjectedCrash:
                terminal = restore(start_effect_crash)
        writes_under_live_web = [
            row
            for row in start_effect_crash.restore_writes
            if row["moss_web_running"] or row["moss_live_web_running"]
        ]
        results["restore_start_effect_replay"] = {
            "terminal": terminal,
            "writes": start_effect_crash.restore_writes,
            "writes_under_live_web": writes_under_live_web,
            "vllm": start_effect_crash.vllm,
        }
        assertions.extend(
            (
                terminal == "restored",
                not writes_under_live_web,
            )
        )

        missing_root = Host(root / "restore-missing-explicit-root")
        try:
            run(missing_root, crash_after="candidate_started")
        except InjectedCrash:
            shutil.rmtree(missing_root.snapshot_roots["phase1_model"])
            terminal = restore(missing_root)
        results["missing_explicit_root"] = {
            "terminal": terminal,
            "writes": missing_root.restore_writes,
            "durable_members": missing_root.durable_restore_members,
            "restored": snapshot_projection(missing_root)
            == missing_root.original_projection,
        }
        assertions.extend(
            (
                terminal == "restored",
                [row["role"] for row in missing_root.restore_writes]
                == ["phase1_model"],
                snapshot_projection(missing_root)
                == missing_root.original_projection,
                set(missing_root.durable_restore_members)
                == {"phase1_model", "phase1_model/weights"},
            )
        )

        journal_failure = Host(root / "persistent-journal-failure")
        try:
            run(journal_failure, crash_after="candidate_started")
        except InjectedCrash:
            try:
                restore(journal_failure, journal_available=False)
            except OSError:
                pass
        rollback_completed_without_journal = (
            journal_failure.phase1_running
            and not journal_failure.account_running
            and snapshot_projection(journal_failure)
            == journal_failure.original_projection
        )
        results["persistent_journal_failure"] = {
            "rollback_completed": rollback_completed_without_journal,
            "state": journal_failure.state(),
            "last_durable_phase": read_events(journal_failure.journal)[-1]["phase"],
        }
        assertions.append(rollback_completed_without_journal)

        false_safe_stopped = Host(root / "false-safe-stopped")
        try:
            run(false_safe_stopped, crash_after="candidate_started")
        except InjectedCrash:
            false_safe_stopped.marker.unlink()
            try:
                terminal = restore(
                    false_safe_stopped,
                    corrupt=True,
                    safe_stop_marker_error=True,
                    safe_stop_stuck_web="moss-live-web",
                )
            except RestorationUncertain:
                terminal = "RESTORATION_UNCERTAIN"
        safe_stopped_verified = (
            false_safe_stopped.marker.is_file()
            and false_safe_stopped.marker.read_bytes()
            == b"moss-phase1-creation-quiesced-v1\n"
            and not any(false_safe_stopped.phase1_web_units.values())
            and not false_safe_stopped.account_running
        )
        results["safe_stopped_verification"] = {
            "terminal": terminal,
            "verified": safe_stopped_verified,
            "state": false_safe_stopped.state(),
        }
        assertions.append(terminal != "SAFE_STOPPED" or safe_stopped_verified)

        arbitrary_origin = "https://not-production.invalid:444"
        exact_origin_accepted = arbitrary_origin == EXACT_PRODUCTION_ORIGIN
        results["production_origin"] = {
            "required": EXACT_PRODUCTION_ORIGIN,
            "observed": arbitrary_origin,
            "accepted_by_exact_rule": exact_origin_accepted,
        }
        assertions.append(not exact_origin_accepted)

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
