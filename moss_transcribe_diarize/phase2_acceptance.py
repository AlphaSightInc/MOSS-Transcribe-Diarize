"""One append-only qualification attempt for one Phase-2 candidate.

The module observes through Git, subprocesses, HTTP/browser-produced reports, and the existing
operator command.  It never opens the product database or starts another product runtime.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
import platform
import base64
import csv
import io
import re
import sqlite3
import subprocess
import sys
import time
import tempfile
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from .concurrency_evidence import (
    canonical_lifecycle_fairness,
    prestop_inference_projection,
)
from .installed_candidate import installed_dependency_projection, record_projection_sha256
from .app.phase2 import GOOGLE_CALLBACK_URL


SCHEMA = "moss-phase2-acceptance.v1"
OBSERVATION_SCHEMA = "moss-phase2-observations.v1"
REQUIRED_SQLITE = "3.53.4"
CORE_GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G10")
LAYERS = ("deterministic", "deployed", "pre_admission")
DEFAULT_PROFILE = Path.home() / ".config" / "moss-transcribe-diarize" / "phase2-acceptance.json"

DETERMINISTIC_COMMANDS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("python", ("{python}", "-m", "pytest", "-q", "tests/"), CORE_GATES),
    (
        "logout-stop-failure-contract",
        (
            "{python}",
            "-m",
            "pytest",
            "-q",
            "tests/phase2/test_owner_bound_live_meeting.py::test_logout_stop_failure_keeps_cookie_session_and_reopens_creation",
        ),
        ("G2",),
    ),
    ("frontend-test", ("npm", "--prefix", "frontend", "test"), ("G1", "G3", "G10")),
    ("frontend-typecheck", ("npm", "--prefix", "frontend", "run", "typecheck"), ("G10",)),
    ("frontend-build", ("npm", "--prefix", "frontend", "run", "build"), ("G10",)),
    (
        "prototype-account-lifecycle",
        ("{python}", "prototypes/phase2-account-lifecycle/probe.py"),
        ("G1", "G2", "G3", "G5"),
    ),
    (
        "prototype-live-owner-binding",
        ("{python}", "prototypes/phase2-live-owner-binding/probe.py"),
        ("G1", "G3", "G4"),
    ),
    (
        "prototype-operator-interrupt",
        ("{python}", "prototypes/phase2-operator-interrupt/probe.py"),
        ("G5", "G6"),
    ),
    (
        "prototype-operator-status",
        ("{python}", "prototypes/phase2-operator-status/probe.py"),
        ("G6",),
    ),
    (
        "prototype-file-owner",
        ("{python}", "prototypes/phase2-owner-bound-file-task/prototype.py"),
        ("G1", "G3", "G5"),
    ),
    (
        "prototype-serial-url",
        ("{python}", "prototypes/phase2-serial-url-acquisition/prototype.py"),
        ("G1", "G3"),
    ),
    (
        "prototype-shared-history",
        ("{python}", "prototypes/phase2-shared-history/probe.py"),
        ("G1", "G3"),
    ),
)

REQUIRED_PYTHON_TEST_FILES = (
    "tests/phase2/test_attended_g7_canary.py",
    "tests/phase2/test_atomic_cutover.py",
    "tests/phase2/test_account_deployment_surface.py",
    "tests/phase2/test_account_file_ingress.py",
    "tests/phase2/test_file_mp3_artifact.py",
    "tests/phase2/test_google_account_workspace.py",
    "tests/phase2/test_legacy_surface_absence.py",
    "tests/phase2/test_multi_file_url_meetings.py",
    "tests/phase2/test_operator_status.py",
    "tests/phase2/test_owner_bound_file_meeting.py",
    "tests/phase2/test_owner_bound_live_meeting.py",
    "tests/phase2/test_runner_composition.py",
    "tests/phase2/test_shared_meeting_history.py",
    "tests/phase2/test_wave1_qualification.py",
    "tests/phase2/test_workspace_reachability.py",
)
REQUIRED_PYTHON_TEST_CASES = (
    "tests.phase2.test_attended_g7_canary.test_attended_meter_checkpoint_accepts_delayed_signal_and_refuses_all_zero",
    "tests.phase2.test_attended_g7_canary.test_candidate_owned_runner_reads_only_prerequisites_and_builds_fixed_evidence",
    "tests.phase2.test_attended_g7_canary.test_attended_evidence_rejects_every_wrong_production_host_or_port",
    "tests.phase2.test_atomic_cutover.test_activation_pointer_replace_is_fsynced_before_install_returns",
    "tests.phase2.test_atomic_cutover.test_attempt_nested_in_candidate_state_is_refused_before_creating_parent",
    "tests.phase2.test_atomic_cutover.test_distinct_forward_attempts_share_one_host_cutover_lock",
    "tests.phase2.test_atomic_cutover.test_missing_or_synthetic_attended_g7_restores_without_preadmission",
    "tests.phase2.test_atomic_cutover.test_malformed_journal_physically_stops_without_publishing_a_terminal",
    "tests.phase2.test_atomic_cutover.test_planned_restored_terminal_runs_wave1_then_whole_restore_without_attended_g7",
    "tests.phase2.test_atomic_cutover.test_normal_restore_preserves_every_present_explicit_phase1_root",
    "tests.phase2.test_atomic_cutover.test_persistent_journal_failure_after_candidate_start_cannot_prevent_rollback",
    "tests.phase2.test_atomic_cutover.test_restore_repairs_only_an_explicit_root_that_is_missing",
    "tests.phase2.test_atomic_cutover.test_restore_fsyncs_parent_after_deleting_originally_absent_activation",
    "tests.phase2.test_atomic_cutover.test_restore_replays_after_process_exit_during_restore_effects",
    "tests.phase2.test_atomic_cutover.test_restored_tree_fsyncs_regular_files_and_directories_before_rename",
    "tests.phase2.test_atomic_cutover.test_safe_stopped_is_not_published_when_marker_and_listener_stop_are_unverified",
    "tests.phase2.test_atomic_cutover.test_snapshot_inventory_refuses_an_unruled_extra_role_before_effects",
    "tests.phase2.test_atomic_cutover.test_system_safe_stop_requires_successful_stop_inactive_units_and_closed_listeners",
    "tests.phase2.test_google_account_workspace.test_authlib_172_offline_prototype_rejects_signed_claim_failures_before_admission",
    "tests.phase2.test_google_account_workspace.test_unverified_or_disallowed_callback_leaves_no_account_or_session",
    "tests.phase2.test_google_account_workspace.test_wrong_sqlite_runtime_is_refused_before_database_or_parent_creation",
    "tests.phase2.test_owner_bound_live_meeting.test_logout_stop_failure_keeps_cookie_session_and_reopens_creation",
)
REQUIRED_FRONTEND_TEST_FILES = (
    "frontend/src/App.test.tsx",
    "frontend/src/api/meetings.test.ts",
    "frontend/src/api/mossPoller.test.ts",
    "frontend/src/capture/captureClient.test.ts",
    "frontend/src/components/ControlPanel.test.tsx",
    "frontend/src/components/MeetingHistory.test.tsx",
    "frontend/src/components/TranscriptPane.test.tsx",
    "frontend/src/components/laneMeter.test.ts",
    "frontend/src/lib/keyboardShortcuts.test.ts",
    "frontend/src/lib/meetingHistory.test.ts",
    "frontend/src/lib/mergeTranscript.test.ts",
    "frontend/src/lib/persistence.test.ts",
    "frontend/src/lib/speakerMap.test.ts",
    "frontend/src/lib/transcriptExport.test.ts",
    "frontend/src/lib/transcriptKeys.test.ts",
    "frontend/src/lib/transcriptModel.test.ts",
    "frontend/src/lib/transcriptSearch.test.ts",
)
# These baselines are raised with each committed load-bearing suite.  Falling below them means a
# test was removed or ceased collection.
MINIMUM_PYTHON_TESTS = 1068
MINIMUM_FRONTEND_TESTS = 121

EXTERNAL_REQUIREMENTS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "deployed": {
        "G0": ("installed_candidate_identity", "zero_work_end"),
        "G1": ("cross_owner_matrix", "sentinel_absence", "same_account_convergence"),
        "G2": ("real_google_oauth", "revocation_lifecycle"),
        "G3": ("meeting_modes_history_restart", "crash_recovery"),
        "G4": ("four_session_capacity", "eight_session_overload", "quality_corpus"),
        "G5": ("audio_durability_download",),
        "G6": ("operator_control",),
        "G10": ("account_product_regression", "transcript_pane_fidelity"),
    },
    "pre_admission": {
        "G0": ("installed_candidate_identity", "zero_work_end"),
        "G1": ("cross_owner_matrix", "sentinel_absence"),
        "G2": ("real_google_oauth", "revocation_lifecycle"),
        "G3": ("meeting_modes_history_restart",),
        "G4": ("four_session_capacity", "eight_session_overload", "quality_corpus"),
        "G5": ("audio_durability_download",),
        "G6": ("operator_control",),
        "G10": ("account_product_regression", "transcript_pane_fidelity"),
    },
}

QUALITY_BOUNDS = {
    "immediate_wer": ("max", 0.166655),
    "settled_wer": ("max", 0.140442),
    "recall": ("min", 0.929636),
    "time_speaker_attribution": ("min", 0.876970),
    "diarization_error_rate": ("max", 0.161430),
    "matched_speaker_accuracy": ("min", 0.911512),
    "reference_speech_der": ("max", 0.134804),
    "final_wer": ("max", 0.095074),
}
FIXTURE_PATHS = {
    "quality_corpus_manifest": "evidence/live-policy-sweep-20260825/corpus/corpus-manifest.json",
    "concurrency_fixture": "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json",
    "concurrency_preregistration": "prototypes/streaming-diarization/concurrency/preregistration.json",
}
QUALITY_CASE_IDS = {
    "mono_javier_intro_50s",
    "interview_bill_ackman_60s",
    "interview_keyu_jin_60s",
    "interview_adam_frank_180s",
    "discussion_jamie_dimon_180s",
    "discussion_rtfl_90s",
}
QUALIFICATION_URL_FIXTURE = "https://www.youtube.com/watch?v=Rtfl-EiTCFQ"
REQUIRED_CONTENT_BOUNDARY_ROLES = (
    "account_a_sentinel",
    "account_b_sentinel",
    "account_a_session_cookie",
    "account_a_peer_session_cookie",
    "account_b_session_cookie",
    "account_b_peer_session_cookie",
    "google_client_secret",
    "moss_cookie_signing_secret",
)
G1_CROSS_OWNER_MATRIX: Mapping[str, tuple[str, str, int]] = {
    "meeting_read_foreign": ("GET", "/api/meetings/{foreign_meeting_id}", 404),
    "meeting_rename_foreign": ("PUT", "/api/meetings/{foreign_meeting_id}/title", 404),
    "audio_download_foreign": (
        "GET",
        "/api/meetings/{foreign_meeting_id}/audio/download",
        404,
    ),
    "live_frame_foreign": ("POST", "/api/live/sessions/{foreign_session_id}/frames", 404),
    "live_heartbeat_foreign": (
        "POST",
        "/api/live/sessions/{foreign_session_id}/heartbeat",
        404,
    ),
    "live_snapshot_foreign": (
        "GET",
        "/api/live/sessions/{foreign_session_id}/snapshot",
        404,
    ),
    "live_events_cursor_foreign": (
        "GET",
        "/api/live/sessions/{foreign_session_id}/events?since_seq={foreign_cursor}",
        404,
    ),
    "live_stop_foreign": ("POST", "/api/live/sessions/{foreign_session_id}/stop", 404),
    "live_abort_foreign": ("POST", "/api/live/sessions/{foreign_session_id}/abort", 404),
    "legacy_rerun_absent": ("POST", "/api/" + "jobs/{foreign_job_id}/rerun", 404),
    "legacy_resume_absent": ("POST", "/api/" + "jobs/{foreign_job_id}/resume", 404),
    "url_retry_absent": ("POST", "/api/meetings/{foreign_meeting_id}/retry", 404),
    "invalid_session_meeting": ("GET", "/api/meetings/{foreign_meeting_id}", 401),
    "revoked_session_meeting": ("GET", "/api/meetings/{foreign_meeting_id}", 401),
    "revoked_live_reattach": (
        "GET",
        "/api/live/sessions/{foreign_session_id}/snapshot",
        401,
    ),
}
G1_SENTINEL_SURFACES = {
    "account_ui",
    "meeting_history",
    "persistence_projection",
    "live_snapshot",
    "live_events",
    "operator_status",
    "operator_journal",
    "server_logs",
    "llm_prompt_log",
}


class AcceptanceRefused(RuntimeError):
    """The attempt cannot truthfully qualify its candidate."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    name: str
    argv: tuple[str, ...]
    returncode: int
    elapsed_seconds: float
    stdout_bytes: int
    stderr_bytes: int
    forbidden_matches: int
    denominators: dict[str, int] | None = None
    required_files: tuple[str, ...] = ()


def _write_once(path: Path, payload: object, *, mode: int = 0o600) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AttemptBundle:
    """An exclusive directory whose records are written once or appended as events."""

    def __init__(self, output: Path):
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        _fsync_directory(output.parent)
        _fsync_directory(output.parent.parent)
        claim = output.parent / f".{output.name}.claim"
        descriptor = os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(output.parent)
        try:
            os.mkdir(output, mode=0o700)
        except BaseException:
            # The permanent exclusive claim intentionally prevents an ambiguous retry.
            raise
        _fsync_directory(output.parent)
        self.path = output
        (self.path / "raw").mkdir(mode=0o700)
        _fsync_directory(self.path)
        self._events = (self.path / "attempts.jsonl").open("x", encoding="utf-8")
        self._events.flush()
        os.fsync(self._events.fileno())
        _fsync_directory(self.path)

    def event(self, kind: str, **fields: object) -> None:
        self._events.write(json.dumps({"kind": kind, **fields}, sort_keys=True) + "\n")
        self._events.flush()
        os.fsync(self._events.fileno())

    def write(self, relative: str, payload: object) -> None:
        _write_once(self.path / relative, payload)

    def write_bytes(self, relative: str, payload: bytes) -> None:
        path = self.path / relative
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            _write_all(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(path.parent)

    def finalize(self, verdict: Mapping[str, object]) -> None:
        """Publish the terminal verdict only after its last append-only event is durable."""

        stage = self.path / ".verdict.json.stage"
        final = self.path / "verdict.json"
        _write_once(stage, verdict)
        self.event(
            "attempt_finalizing",
            qualified=bool(verdict["qualified"]),
            g7="UNCLAIMED",
        )
        if final.exists():
            raise FileExistsError(final)
        os.rename(stage, final)
        _fsync_directory(self.path)

    def close(self) -> None:
        if not self._events.closed:
            self._events.close()


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", *args), cwd=repo, check=False, capture_output=True, text=True
    )
    if result.returncode:
        raise AcceptanceRefused(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("write returned no progress")
        view = view[written:]


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def discover_candidate(repo: Path) -> dict[str, object]:
    status = _git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
        "--",
        ".",
        ":(exclude)evidence/phase2/**",
    )
    dirty = tuple(line for line in status.splitlines() if line)
    sha = _git(repo, "rev-parse", "HEAD")
    return {
        "schema": SCHEMA,
        "git_sha": sha,
        "git_short_sha": sha[:12],
        "git_tree": _git(repo, "rev-parse", "HEAD^{tree}"),
        "dirty": list(dirty),
        "runtime": {
            "python": platform.python_version(),
            "executable": str(Path(sys.executable).resolve()),
            "sqlite": sqlite3.sqlite_version,
            "aiosqlite": _package_version("aiosqlite"),
            "authlib": _package_version("Authlib"),
            "platform": platform.platform(),
        },
        "dependencies": {
            name: _package_version(name)
            for name in ("fastapi", "uvicorn", "httpx", "yt-dlp", "moss-transcribe-diarize")
        },
        "dependency_projection": installed_dependency_projection(),
        "uv_lock_sha256": hashlib.sha256((repo / "uv.lock").read_bytes()).hexdigest(),
        "fixtures": {
            name: hashlib.sha256((repo / relative).read_bytes()).hexdigest()
            for name, relative in FIXTURE_PATHS.items()
        },
        "wheel": None,
    }


def build_candidate_wheel(
    *, repo: Path, bundle: AttemptBundle, source_identity: Mapping[str, object]
) -> tuple[dict[str, object] | None, list[str]]:
    if source_identity.get("dirty"):
        return None, ["candidate_wheel_refused_dirty_source"]
    with tempfile.TemporaryDirectory(prefix="moss-candidate-wheel-") as directory:
        build_root = Path(directory) / "source"
        ignore = shutil.ignore_patterns(".git", ".venv", "node_modules", "dist", "evidence")
        shutil.copytree(repo, build_root, ignore=ignore)
        embedded = {
            "schema": SCHEMA,
            "git_sha": source_identity["git_sha"],
            "git_tree": source_identity["git_tree"],
            "uv_lock_sha256": source_identity["uv_lock_sha256"],
            "fixtures": source_identity["fixtures"],
        }
        (build_root / "moss_transcribe_diarize" / "build_candidate.json").write_text(
            json.dumps(embedded, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        wheel_dir = Path(directory) / "wheel"
        process = subprocess.run(
            ("uv", "build", "--wheel", "--out-dir", str(wheel_dir)),
            cwd=build_root,
            check=False,
            capture_output=True,
        )
        bundle.write_bytes("raw/wheel-build.stdout", process.stdout)
        bundle.write_bytes("raw/wheel-build.stderr", process.stderr)
        if process.returncode:
            return None, ["candidate_wheel_build_failed"]
        wheels = tuple(wheel_dir.glob("*.whl"))
        if len(wheels) != 1:
            return None, ["candidate_wheel_count"]
        wheel_bytes = wheels[0].read_bytes()
        bundle.write_bytes(f"raw/{wheels[0].name}", wheel_bytes)
        try:
            inspection = inspect_candidate_wheel(wheels[0], source_identity)
        except (KeyError, ValueError, zipfile.BadZipFile) as exc:
            return None, [f"candidate_wheel_invalid:{type(exc).__name__}"]
        return inspection, []


def inspect_candidate_wheel(path: Path, source_identity: Mapping[str, object]) -> dict[str, object]:
    wheel_bytes = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(wheel_bytes)) as archive:
        names = set(archive.namelist())
        manifest_name = "moss_transcribe_diarize/build_candidate.json"
        if manifest_name not in names:
            raise ValueError("candidate manifest absent from wheel")
        embedded = json.loads(archive.read(manifest_name))
        for key in ("git_sha", "git_tree", "uv_lock_sha256", "fixtures"):
            if embedded.get(key) != source_identity.get(key):
                raise ValueError(f"wheel {key} differs from candidate")
        record_names = [name for name in names if name.endswith(".dist-info/RECORD")]
        if len(record_names) != 1:
            raise ValueError("wheel must contain one RECORD")
        records = list(csv.reader(io.StringIO(archive.read(record_names[0]).decode("utf-8"))))
        verified = 0
        for filename, digest, size in records:
            if not digest:
                if filename != record_names[0]:
                    raise ValueError("only RECORD may omit its digest")
                continue
            algorithm, encoded = digest.split("=", 1)
            if algorithm != "sha256":
                raise ValueError("wheel RECORD uses a non-sha256 digest")
            payload = archive.read(filename)
            actual = base64.urlsafe_b64encode(hashlib.sha256(payload).digest()).decode().rstrip("=")
            if actual != encoded or int(size) != len(payload):
                raise ValueError(f"wheel RECORD mismatch: {filename}")
            verified += 1
    return {
        "filename": path.name,
        "sha256": hashlib.sha256(wheel_bytes).hexdigest(),
        "bytes": len(wheel_bytes),
        "embedded_candidate": embedded,
        "record_entries_verified": verified,
        "record_verified": True,
        "record_projection_sha256": record_projection_sha256(records),
    }


def load_profile(path: Path) -> tuple[dict[str, object], list[str]]:
    if not path.exists():
        return {}, ["profile_missing"]
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        return {}, [f"profile_mode_{mode:o}_not_600"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"profile_unreadable:{type(exc).__name__}"]
    if not isinstance(payload, dict):
        return {}, ["profile_not_object"]
    return payload, []


def _load_forbidden_values(
    profile: Mapping[str, object],
) -> tuple[tuple[bytes, ...], dict[str, object], list[str]]:
    """Read content boundaries from mode-0600 files without serializing their values."""

    if "forbidden_values" in profile:
        return (), {}, ["profile_must_not_embed_forbidden_values"]
    values: list[bytes] = []
    errors: list[str] = []
    configured = profile.get("forbidden_files")
    if not isinstance(configured, dict):
        return (), {}, ["forbidden_files_not_object"]
    missing = [role for role in REQUIRED_CONTENT_BOUNDARY_ROLES if role not in configured]
    if missing:
        errors.extend(f"forbidden_role_missing:{role}" for role in missing)
    configured_paths: set[Path] = set()
    for role in sorted(configured):
        value = configured[role]
        if not isinstance(value, str) or not value:
            errors.append(f"forbidden_file_invalid:{role}")
            continue
        path = Path(value).expanduser()
        configured_paths.add(path.resolve())
        try:
            if path.stat().st_mode & 0o777 != 0o600:
                errors.append(f"forbidden_file_mode:{role}")
                continue
            content = path.read_bytes().strip()
        except OSError:
            errors.append(f"forbidden_file_unreadable:{role}")
            continue
        if not content:
            errors.append(f"forbidden_file_empty:{role}")
            continue
        values.append(content)
    if len(set(values)) != len(values):
        errors.append("forbidden_file_values_not_distinct")
    measurements = profile.get("measurements")
    sensitive_paths: list[tuple[str, Path]] = []
    if isinstance(measurements, dict):
        for layer in ("deployed", "pre_admission"):
            layer_config = measurements.get(layer)
            if not isinstance(layer_config, dict):
                continue
            for key, value in layer_config.items():
                if (
                    isinstance(value, str)
                    and (key.endswith("_cookie_file") or key.endswith("_sentinel_file"))
                ):
                    sensitive_paths.append((f"{layer}:{key}", Path(value).expanduser().resolve()))
    for label, path in sensitive_paths:
        if path not in configured_paths:
            errors.append(f"measurement_boundary_unruled:{label}")
    cookie_paths = [path for label, path in sensitive_paths if label.endswith("_cookie_file")]
    if len(set(cookie_paths)) != len(cookie_paths):
        errors.append("measurement_cookie_files_not_distinct")
    summary = {
        "roles": sorted(configured),
        "count": len(values),
        "required_roles": list(REQUIRED_CONTENT_BOUNDARY_ROLES),
    }
    return tuple(values), summary, errors


def _forbidden_matches(data: bytes, forbidden: Sequence[bytes]) -> int:
    return sum(data.count(value) for value in forbidden if value)


def execute_command(
    *,
    bundle: AttemptBundle,
    repo: Path,
    name: str,
    argv: Sequence[str],
    forbidden: Sequence[bytes],
    environment: Mapping[str, str] | None = None,
    record_argv: bool = True,
) -> CommandResult:
    started = time.monotonic()
    safe_argv = (
        tuple(
            "<content-boundary>"
            if any(value and value in item.encode("utf-8") for value in forbidden)
            else item
            for item in argv
        )
        if record_argv
        else ("<profile-derived-command>",)
    )
    bundle.event("command_started", name=name, argv=list(safe_argv))
    process = subprocess.run(
        argv,
        cwd=repo,
        check=False,
        capture_output=True,
        env={**os.environ, **dict(environment or {})},
    )
    elapsed = round(time.monotonic() - started, 6)
    matches = _forbidden_matches(process.stdout, forbidden) + _forbidden_matches(
        process.stderr, forbidden
    )
    if matches:
        bundle.write(
            f"raw/{name}-content-boundary.json",
            {
                "stdout_bytes": len(process.stdout),
                "stderr_bytes": len(process.stderr),
                "forbidden_matches": matches,
                "retained": False,
            },
        )
    else:
        bundle.write_bytes(f"raw/{name}.stdout", process.stdout)
        bundle.write_bytes(f"raw/{name}.stderr", process.stderr)
    result = CommandResult(
        name=name,
        argv=safe_argv,
        returncode=process.returncode,
        elapsed_seconds=elapsed,
        stdout_bytes=len(process.stdout),
        stderr_bytes=len(process.stderr),
        forbidden_matches=matches,
    )
    bundle.write(f"raw/{name}.json", asdict(result))
    bundle.event("command_finished", **asdict(result))
    return result


def _pytest_denominators(
    report: Path, *, repo: Path
) -> tuple[dict[str, int], tuple[str, ...], list[str]]:
    try:
        root = ET.parse(report).getroot()
    except (OSError, ET.ParseError) as exc:
        return {}, (), [f"pytest_report_unreadable:{type(exc).__name__}"]
    cases = root.findall(".//testcase")
    case_failures = sum(
        case.find("failure") is not None or case.find("error") is not None for case in cases
    )
    case_skips = sum(case.find("skipped") is not None for case in cases)
    required_seen: list[str] = []
    required_failures: list[str] = []
    observed_nodes = {
        f"{str(case.get('classname', ''))}.{str(case.get('name', '')).split('[', 1)[0]}"
        for case in cases
    }
    for required in REQUIRED_PYTHON_TEST_CASES:
        if required not in observed_nodes:
            required_failures.append(f"pytest_required_case_missing:{required}")
    for required in REQUIRED_PYTHON_TEST_FILES:
        if not (repo / required).is_file():
            required_failures.append(f"pytest_required_file_missing:{required}")
            continue
        stem = Path(required).stem
        selected = [
            case
            for case in cases
            if str(case.get("file", "")).replace("\\", "/").endswith(required)
            or stem in str(case.get("classname", "")).split(".")
        ]
        if selected:
            required_seen.append(required)
        else:
            required_failures.append(f"pytest_required_file_missing:{required}")
            continue
        if any(
            case.find("failure") is not None
            or case.find("error") is not None
            or case.find("skipped") is not None
            for case in selected
        ):
            required_failures.append(f"pytest_required_file_not_all_passed:{required}")
    declared_element = root if root.tag == "testsuite" else root.find("testsuite")
    declared = {} if declared_element is None else declared_element.attrib
    declared_tests = int(declared.get("tests", len(cases)))
    declared_failures = int(declared.get("failures", 0)) + int(declared.get("errors", 0))
    declared_skips = int(declared.get("skipped", 0))
    denominators = {
        "collected": declared_tests,
        "executed": declared_tests - declared_skips,
        "passed": declared_tests - declared_failures - declared_skips,
        "failed": declared_failures,
        "skipped": declared_skips,
        "unmeasured": 0,
    }
    errors = list(required_failures)
    # Pytest's JUnit counter includes subtests while its XML contains only their parent testcase.
    if (
        declared_tests < len(cases)
        or declared_failures < case_failures
        or declared_skips < case_skips
        or denominators["passed"] < 0
    ):
        errors.append("pytest_report_count_mismatch")
    if declared_tests < MINIMUM_PYTHON_TESTS:
        errors.append("pytest_test_denominator_decreased")
    if declared_failures:
        errors.append("pytest_failures")
    return denominators, tuple(required_seen), errors


def _vitest_denominators(
    report: Path, *, repo: Path
) -> tuple[dict[str, int], tuple[str, ...], list[str]]:
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, (), [f"vitest_report_unreadable:{type(exc).__name__}"]
    if not isinstance(payload, dict) or not isinstance(payload.get("testResults"), list):
        return {}, (), ["vitest_report_schema"]
    keys = {
        "collected": "numTotalTests",
        "passed": "numPassedTests",
        "failed": "numFailedTests",
        "skipped": "numPendingTests",
    }
    try:
        denominators = {name: int(payload[key]) for name, key in keys.items()}
        denominators["skipped"] += int(payload.get("numTodoTests", 0))
    except (KeyError, TypeError, ValueError):
        return {}, (), ["vitest_report_counts"]
    denominators["executed"] = denominators["collected"] - denominators["skipped"]
    denominators["unmeasured"] = 0
    observed: set[str] = set()
    derived_total = 0
    derived_failed = 0
    derived_skipped = 0
    for result in payload["testResults"]:
        if not isinstance(result, dict) or not isinstance(result.get("name"), str):
            return denominators, (), ["vitest_result_schema"]
        name = result["name"].replace("\\", "/")
        for required in REQUIRED_FRONTEND_TEST_FILES:
            if name.endswith(required):
                observed.add(required)
        assertions = result.get("assertionResults")
        if not isinstance(assertions, list):
            return denominators, (), ["vitest_assertions_missing"]
        derived_total += len(assertions)
        for assertion in assertions:
            status = assertion.get("status") if isinstance(assertion, dict) else None
            if status == "failed":
                derived_failed += 1
            elif status in {"pending", "todo", "skipped", "disabled"}:
                derived_skipped += 1
            elif status != "passed":
                return denominators, (), ["vitest_assertion_status"]
    errors = [
        f"vitest_required_file_missing:{required}"
        for required in REQUIRED_FRONTEND_TEST_FILES
        if required not in observed or not (repo / required).is_file()
    ]
    if (
        derived_total != denominators["collected"]
        or derived_failed != denominators["failed"]
        or derived_skipped != denominators["skipped"]
        or denominators["passed"] + denominators["failed"] + denominators["skipped"]
        != denominators["collected"]
    ):
        errors.append("vitest_report_count_mismatch")
    if denominators["collected"] < MINIMUM_FRONTEND_TESTS:
        errors.append("vitest_test_denominator_decreased")
    if denominators["failed"] or denominators["skipped"] or payload.get("success") is not True:
        errors.append("vitest_not_all_passed")
    return denominators, tuple(sorted(observed)), errors


def execute_deterministic_command(
    *,
    bundle: AttemptBundle,
    repo: Path,
    name: str,
    argv: Sequence[str],
    forbidden: Sequence[bytes],
) -> tuple[CommandResult, list[str]]:
    parser = None
    suffix = ""
    with tempfile.TemporaryDirectory(prefix=f"moss-{name}-report-") as directory:
        report = Path(directory) / "report"
        if name == "python":
            argv = (*argv, f"--junitxml={report}")
            parser = _pytest_denominators
            suffix = ".xml"
        elif name == "frontend-test":
            argv = (*argv, "--", "--reporter=json", f"--outputFile={report}")
            parser = _vitest_denominators
            suffix = ".json"
        result = execute_command(
            bundle=bundle,
            repo=repo,
            name=name,
            argv=argv,
            forbidden=forbidden,
        )
        if parser is None:
            return result, []
        denominators, required_files, errors = parser(report, repo=repo)
        if report.is_file():
            encoded = report.read_bytes()
            matches = _forbidden_matches(encoded, forbidden)
            if matches:
                bundle.write(
                    f"raw/{name}-report-content-boundary.json",
                    {"bytes": len(encoded), "forbidden_matches": matches, "retained": False},
                )
                errors.append(f"{name}_report_content_boundary")
            else:
                bundle.write_bytes(f"raw/{name}-report{suffix}", encoded)
        result = replace(result, denominators=denominators, required_files=required_files)
        bundle.write(
            f"raw/{name}-denominators.json",
            {"counts": denominators, "required_files": list(required_files), "errors": errors},
        )
        return result, errors


def _read_external_report(
    path_value: object,
    *,
    layer: str,
    candidate_sha: str,
    bundle: AttemptBundle,
    forbidden: Sequence[bytes],
) -> tuple[dict[str, object] | None, list[str]]:
    if not isinstance(path_value, str) or not path_value:
        return None, [f"{layer}_evidence_missing"]
    path = Path(path_value).expanduser()
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"{layer}_evidence_unreadable:{type(exc).__name__}"]
    if not isinstance(payload, dict):
        return None, [f"{layer}_evidence_not_object"]
    matches = _forbidden_matches(raw, forbidden)
    if matches:
        bundle.write(
            f"raw/{layer}-content-boundary.json",
            {"bytes": len(raw), "forbidden_matches": matches, "retained": False},
        )
        return None, [f"{layer}_content_boundary"]
    errors: list[str] = []
    if payload.get("schema") != OBSERVATION_SCHEMA:
        errors.append(f"{layer}_schema")
    if payload.get("layer") != layer:
        errors.append(f"{layer}_layer")
    if payload.get("candidate_sha") != candidate_sha:
        errors.append(f"{layer}_candidate_sha")
    bundle.write_bytes(f"raw/{layer}-observations.json", raw)
    return payload, errors


def _capture_collector_artifacts(
    payload: Mapping[str, object] | None,
    *,
    layer: str,
    raw_dir: Path,
    bundle: AttemptBundle,
    forbidden: Sequence[bytes],
) -> list[str]:
    if payload is None:
        return [f"{layer}_collector_report_missing"]
    collector = payload.get("collector")
    artifacts = collector.get("artifacts") if isinstance(collector, dict) else None
    if (
        not isinstance(collector, dict)
        or collector.get("id") != "candidate-owned-raw-reducer.v1"
        or collector.get("raw_schema") != "moss-phase2-raw-observation.v1"
        or not isinstance(artifacts, list)
        or not artifacts
    ):
        return [f"{layer}_collector_provenance"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict):
            errors.append(f"{layer}_artifact_{index}_invalid")
            continue
        name = artifact.get("name")
        relative = Path(name) if isinstance(name, str) else None
        if (
            relative is None
            or relative.is_absolute()
            or not relative.parts
            or any(part in {"", ".", ".."} for part in relative.parts)
            or name in seen
        ):
            errors.append(f"{layer}_artifact_{index}_name")
            continue
        seen.add(name)
        try:
            encoded = (raw_dir / relative).read_bytes()
        except OSError:
            errors.append(f"{layer}_artifact_{index}_unreadable")
            continue
        if (
            artifact.get("sha256") != hashlib.sha256(encoded).hexdigest()
            or artifact.get("bytes") != len(encoded)
        ):
            errors.append(f"{layer}_artifact_{index}_identity")
            continue
        matches = _forbidden_matches(encoded, forbidden)
        if matches:
            bundle.write(
                f"raw/{layer}-{index}-content-boundary.json",
                {"bytes": len(encoded), "forbidden_matches": matches, "retained": False},
            )
            errors.append(f"{layer}_artifact_{index}_content_boundary")
            continue
        retained = bundle.path / "raw" / f"{layer}-collector" / relative
        retained.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        bundle.write_bytes(
            f"raw/{layer}-collector/{relative.as_posix()}", encoded
        )
    return errors


def _predicate_passes(predicate: Mapping[str, object]) -> bool:
    cases = predicate.get("cases")
    counts = predicate.get("counts")
    if not isinstance(cases, list) or not cases:
        return False
    if not isinstance(counts, dict):
        return False
    executed = sum(
        1 for item in cases if isinstance(item, dict) and item.get("executed") is True
    )
    passed = sum(
        1
        for item in cases
        if isinstance(item, dict)
        and item.get("executed") is True
        and item.get("passed") is True
    )
    failed = sum(
        1
        for item in cases
        if isinstance(item, dict)
        and item.get("executed") is True
        and item.get("passed") is False
    )
    unmeasured = len(cases) - executed
    expected = {
        "collected": len(cases),
        "executed": executed,
        "passed": passed,
        "failed": failed,
        "skipped": 0,
        "unmeasured": unmeasured,
    }
    return (
        all(counts.get(key) == value for key, value in expected.items())
        and executed == len(cases)
        and passed == len(cases)
        and failed == 0
        and unmeasured == 0
    )


def _type7(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise ValueError("percentile requires observations")
    ordered = sorted(float(value) for value in values)
    if not all(math.isfinite(value) for value in ordered):
        raise ValueError("percentile observations must be finite")
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _validate_capacity(predicate: Mapping[str, object]) -> bool:
    raw = predicate.get("raw")
    if not isinstance(raw, dict):
        return False
    sessions = raw.get("session_observations")
    wrong_owner = raw.get("wrong_owner_observations")
    rss_samples = raw.get("rss_samples")
    cache_samples = raw.get("vllm_gpu_cache_samples")
    log_matches = raw.get("log_match_counts")
    backpressure = raw.get("backpressure_observation")
    campaign_interval = raw.get("campaign_interval")
    if not (
        isinstance(sessions, list)
        and len(sessions) == 4
        and isinstance(wrong_owner, list)
        and wrong_owner
        and isinstance(rss_samples, list)
        and len(rss_samples) >= 2
        and isinstance(cache_samples, list)
        and len(cache_samples) >= 2
        and isinstance(log_matches, dict)
        and isinstance(backpressure, dict)
        and isinstance(campaign_interval, dict)
    ):
        return False
    try:
        ordered_sessions = sorted(sessions, key=lambda item: int(item["session_ordinal"]))
        if [int(item["session_ordinal"]) for item in ordered_sessions] != [1, 2, 3, 4]:
            return False
        if {int(item["account_ordinal"]) for item in ordered_sessions} != {1, 2}:
            return False
        max_p95 = max(_type7(item["lags"], 0.95) for item in ordered_sessions)
        rss = [int(value) for value in rss_samples]
        cache = [float(value) for value in cache_samples]
        if any(value < 0 for value in rss) or not all(
            math.isfinite(value) and value >= 0 for value in cache
        ):
            return False
        expected_samples = int(float(raw["requested_duration_seconds"]) * 16_000)
        campaign_started_ns = int(campaign_interval["started_monotonic_ns"])
        campaign_finished_ns = int(campaign_interval["finished_monotonic_ns"])
        observed_duration = (campaign_finished_ns - campaign_started_ns) / 1_000_000_000
        if campaign_finished_ns <= campaign_started_ns:
            return False
    except (KeyError, ValueError, TypeError):
        return False

    lifecycle: list[tuple[int, int, Mapping[str, object]]] = []
    sequence_gaps = 0
    dropped_commits = 0
    marker_failures = 0
    capacity_events: list[Mapping[str, object]] = []
    refinement_pending: dict[int, set[int]] = {}
    refinement_depth = 0
    terminal_failures = 0
    for item in ordered_sessions:
        if not isinstance(item, dict) or not isinstance(item.get("events"), list):
            return False
        ordinal = int(item["session_ordinal"])
        sequence_gaps += int(
            int(item.get("frames", -1)) * 8_000 != expected_samples
            or int(item.get("accepted_samples", -1)) != expected_samples
        )
        dropped_commits += int(
            int(item.get("accounted_samples", -1))
            != int(item.get("accepted_samples", -2))
        )
        marker_failures += int(
            item.get("own_marker_present") is not True
            or item.get("foreign_markers_absent") is not True
        )
        refinement_pending[ordinal] = set()
        for event in item["events"]:
            if not isinstance(event, dict):
                return False
            capacity_events.append({"session_id": str(ordinal), **event})
            timestamp = event.get("runtime_monotonic_ns")
            if not isinstance(timestamp, int):
                return False
            lifecycle.append((timestamp, ordinal, event))
            kind = event.get("kind")
            if kind == "terminal_finalization_failed":
                terminal_failures += 1

    canonical_events: list[dict[str, object]] = []
    for _timestamp, ordinal, event in sorted(lifecycle, key=lambda item: item[0]):
        kind = event.get("kind")
        if kind in {"canonical_queued", "canonical_started", "canonical_processed"}:
            canonical_events.append(
                {
                    "session_id": str(ordinal),
                    "kind": kind,
                    "payload": {key: value for key, value in event.items() if key != "kind"},
                }
            )
        if kind == "rolling_decode_queued" and event.get("admitted") is True:
            item_id = event.get("item_id")
            if not isinstance(item_id, int):
                return False
            refinement_pending[ordinal].add(item_id)
            refinement_depth = max(refinement_depth, len(refinement_pending[ordinal]))
        elif kind == "rolling_decode_completed":
            item_id = event.get("item_id")
            if not isinstance(item_id, int):
                return False
            refinement_pending[ordinal].discard(item_id)

    fairness = canonical_lifecycle_fairness(
        canonical_events,
        {str(ordinal) for ordinal in range(1, 5)},
        maximum_skew=1,
    )
    dispatch_skew = int(fairness["maximum_contended_pair_dispatch_skew"])

    try:
        wrong_ordinals = {
            int(item["session_ordinal"])
            for item in wrong_owner
            if isinstance(item, dict)
            and item.get("status") == 404
            and item.get("foreign_matches") == 0
        }
        cross_deliveries = sum(
            int(item.get("foreign_matches", -1))
            for item in wrong_owner
            if isinstance(item, dict)
        )
        oom_errors = int(log_matches.get("oom", -1))
        accelerator_errors = int(log_matches.get("accelerator", -1))
        probe_sequences = {
            ordinal: sorted(
                int(item["sequence"])
                for item in wrong_owner
                if isinstance(item, dict)
                and int(item.get("session_ordinal", -1)) == ordinal
            )
            for ordinal in range(1, 5)
        }
    except (KeyError, TypeError, ValueError):
        return False
    continuous_probes = all(
        sequences == list(range(int(ordered_sessions[ordinal - 1]["frames"])))
        for ordinal, sequences in probe_sequences.items()
    )
    try:
        accepted_audio_seconds = sum(
            int(item["accepted_samples"]) for item in ordered_sessions
        ) / 16_000
        inference = prestop_inference_projection(
            capacity_events,
            accepted_audio_seconds=accepted_audio_seconds,
        )
    except ValueError:
        return False
    rtf = float(inference["rtf"])
    rss_growth = max(rss) - min(rss)
    cache_peak = max(cache)
    return (
        raw.get("sessions") == 4
        and int(raw.get("accounts", 0)) >= 2
        and observed_duration >= 600
        and math.isclose(float(raw.get("duration_seconds", 0)), observed_duration)
        and float(raw.get("requested_duration_seconds", 0)) == 600
        and raw.get("real_human_speech") is True
        and float(raw.get("ingress_cadence_seconds", -1)) == 0.5
        and wrong_ordinals == {1, 2, 3, 4}
        and continuous_probes
        and cross_deliveries == 0
        and max_p95 <= 10.0
        and fairness.get("applicability") == "measured"
        and fairness.get("passes") is True
        and dispatch_skew <= 1
        and rtf < 1
        and refinement_depth <= 1
        and cache_peak <= 0.95
        and rss_growth <= 4 * 1024**3
        and oom_errors == 0
        and accelerator_errors == 0
        and sequence_gaps == 0
        and dropped_commits == 0
        and terminal_failures == 0
        and marker_failures == 0
        and all(
            backpressure.get(key) is True
            for key in ("observed_429", "peer_progress", "same_sequence_retry")
        )
        and int(raw.get("dispatch_skew", -1)) == dispatch_skew
        and raw.get("fairness_measured") is True
        and raw.get("fairness_observation") == fairness
        and math.isclose(float(raw.get("prestop_inference_rtf", math.inf)), rtf)
        and int(raw.get("refinement_queue_depth", -1)) == refinement_depth
        and math.isclose(float(raw.get("vllm_gpu_cache_use", math.inf)), cache_peak)
        and int(raw.get("rss_growth_bytes", -1)) == rss_growth
    )


def _validate_overload(predicate: Mapping[str, object]) -> bool:
    raw = predicate.get("raw")
    if not isinstance(raw, dict):
        return False
    sessions = raw.get("session_observations")
    probes = raw.get("wrong_owner_observations")
    backpressure = raw.get("backpressure_observation")
    interval = raw.get("campaign_interval")
    if not (
        isinstance(sessions, list)
        and len(sessions) == 8
        and isinstance(probes, list)
        and probes
        and isinstance(backpressure, dict)
        and isinstance(interval, dict)
    ):
        return False
    try:
        ordered = sorted(sessions, key=lambda item: int(item["session_ordinal"]))
        if [int(item["session_ordinal"]) for item in ordered] != list(range(1, 9)):
            return False
        if {int(item["account_ordinal"]) for item in ordered} != {1, 2}:
            return False
        requested = float(raw["requested_duration_seconds"])
        started = int(interval["started_monotonic_ns"])
        finished = int(interval["finished_monotonic_ns"])
        observed = (finished - started) / 1_000_000_000
        if requested != 30 or observed <= 0 or not math.isclose(
            float(raw["duration_seconds"]), observed
        ):
            return False
        campaign_ordinals = [int(value) for value in backpressure["campaign_session_ordinals"]]
        target_ordinal = int(backpressure["target_session_ordinal"])
        peer_ordinal = int(backpressure["peer_session_ordinal"])
        refused_ns = int(backpressure["refused_monotonic_ns"])
        peer_ns = int(backpressure["peer_progress_monotonic_ns"])
        retry_ns = int(backpressure["retry_monotonic_ns"])
        if (
            campaign_ordinals != list(range(1, 9))
            or target_ordinal == peer_ordinal
            or {target_ordinal, peer_ordinal} - set(campaign_ordinals)
            or not (started <= refused_ns <= peer_ns <= retry_ns <= finished)
        ):
            return False
        expected_samples = int(requested * 16_000)
        lifecycle: list[tuple[int, int, Mapping[str, object]]] = []
        sequence_gaps = isolation_failures = 0
        for item in ordered:
            ordinal = int(item["session_ordinal"])
            sequence_gaps += int(
                int(item["frames"]) * 8_000 != expected_samples
                or int(item["accepted_samples"]) != expected_samples
                or int(item["accounted_samples"]) != int(item["accepted_samples"])
            )
            isolation_failures += int(
                item.get("own_marker_present") is not True
                or item.get("foreign_markers_absent") is not True
            )
            events = item.get("events")
            if not isinstance(events, list):
                return False
            for event in events:
                if not isinstance(event, dict) or not isinstance(
                    event.get("runtime_monotonic_ns"), int
                ):
                    return False
                lifecycle.append((int(event["runtime_monotonic_ns"]), ordinal, event))
        canonical_events: list[dict[str, object]] = []
        for _timestamp, ordinal, event in sorted(lifecycle, key=lambda item: item[0]):
            if event.get("kind") in {
                "canonical_queued",
                "canonical_started",
                "canonical_processed",
            }:
                canonical_events.append(
                    {
                        "session_id": str(ordinal),
                        "kind": event.get("kind"),
                        "payload": {
                            key: value for key, value in event.items() if key != "kind"
                        },
                    }
                )
        fairness = canonical_lifecycle_fairness(
            canonical_events,
            {str(ordinal) for ordinal in range(1, 9)},
            maximum_skew=1,
        )
        dispatch_skew = int(fairness["maximum_contended_pair_dispatch_skew"])
        probe_sequences = {
            ordinal: sorted(
                int(item["sequence"])
                for item in probes
                if isinstance(item, dict)
                and int(item.get("session_ordinal", -1)) == ordinal
                and item.get("status") == 404
                and item.get("foreign_matches") == 0
            )
            for ordinal in range(1, 9)
        }
        probes_complete = all(
            values == list(range(int(ordered[ordinal - 1]["frames"])))
            for ordinal, values in probe_sequences.items()
        )
    except (KeyError, TypeError, ValueError):
        return False
    return (
        raw.get("sessions") == 8
        and int(raw.get("accounts", 0)) == 2
        and sequence_gaps == 0
        and isolation_failures == 0
        and probes_complete
        and fairness.get("applicability") == "measured"
        and fairness.get("passes") is True
        and dispatch_skew <= 1
        and all(
            backpressure.get(key) is True
            for key in ("observed_429", "peer_progress", "same_sequence_retry")
        )
        and raw.get("sequence_gaps") == 0
        and raw.get("cross_account_sentinel_deliveries") == 0
        and raw.get("isolation_failures") == 0
        and raw.get("fairness_failures") == 0
        and raw.get("fairness_measured") is True
        and raw.get("fairness_observation") == fairness
    )


def _validate_quality(predicate: Mapping[str, object]) -> bool:
    raw = predicate.get("raw")
    if not isinstance(raw, dict):
        return False
    metrics = raw.get("macro")
    if not isinstance(metrics, dict):
        return False
    per_case = raw.get("per_case")
    input_identities = raw.get("input_identities")
    if not (
        raw.get("cases") == 6
        and raw.get("passes") == 2
        and raw.get("sessions") == 12
        and int(raw.get("windows", 0)) == 122
        and float(raw.get("duration_seconds", 0)) >= 1239.987
        and isinstance(per_case, list)
        and len(per_case) == 12
        and isinstance(raw.get("per_category"), dict)
        and isinstance(raw.get("duration_weighted"), dict)
        and isinstance(input_identities, list)
        and len(input_identities) == 6
    ):
        return False
    indexed_inputs = {
        item.get("case_id"): item
        for item in input_identities
        if isinstance(item, dict)
    }
    if set(indexed_inputs) != QUALITY_CASE_IDS:
        return False
    for item in indexed_inputs.values():
        checks = item.get("checks")
        if not isinstance(checks, dict) or not checks or not all(
            value is True for value in checks.values()
        ):
            return False
        if item.get("source_present") is True and not (
            item.get("source_audio_match") is True
            and item.get("source_reference_match") is True
        ):
            return False
    case_passes: set[tuple[str, int]] = set()
    session_ids: set[str] = set()
    total_case_seconds = 0.0
    total_case_windows = 0
    rows: list[dict[str, object]] = []
    metric_fields = (
        "wer",
        "tbsa",
        "der",
        "content_recall",
        "matched_word_speaker_accuracy",
        "reference_speech_der",
    )
    for item in per_case:
        if not isinstance(item, dict):
            return False
        case_id = item.get("case_id")
        pass_number = item.get("pass")
        if not isinstance(case_id, str) or pass_number not in (1, 2):
            return False
        case_passes.add((case_id, pass_number))
        session_id = item.get("session_id")
        if not isinstance(session_id, str) or not session_id or session_id in session_ids:
            return False
        session_ids.add(session_id)
        try:
            duration_seconds = float(item["duration_seconds"])
            windows = int(item["windows"])
        except (KeyError, TypeError, ValueError):
            return False
        if not math.isfinite(duration_seconds) or duration_seconds <= 0 or windows <= 0:
            return False
        total_case_seconds += duration_seconds
        total_case_windows += windows
        category = item.get("category")
        item_metrics = item.get("metrics")
        if not isinstance(category, str) or not category or not isinstance(item_metrics, dict):
            return False
        for surface in ("immediate", "settled", "final"):
            values = item_metrics.get(surface)
            if not isinstance(values, dict):
                return False
            for field in metric_fields:
                value = values.get(field)
                if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    return False
        rows.append(item)
    expected_case_passes = {(case_id, pass_number) for case_id in QUALITY_CASE_IDS for pass_number in (1, 2)}
    if (
        case_passes != expected_case_passes
        or raw.get("corpus_manifest_sha256")
        != "80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c"
        or total_case_windows != 122
        or total_case_seconds < 1239.987
    ):
        return False
    def mean(surface: str, field: str, selected: Sequence[dict[str, object]] = rows) -> float:
        return sum(float(item["metrics"][surface][field]) for item in selected) / len(selected)  # type: ignore[index]

    recomputed_macro = {
        "immediate_wer": mean("immediate", "wer"),
        "settled_wer": mean("settled", "wer"),
        "recall": mean("settled", "content_recall"),
        "time_speaker_attribution": mean("settled", "tbsa"),
        "diarization_error_rate": mean("settled", "der"),
        "matched_speaker_accuracy": mean(
            "settled", "matched_word_speaker_accuracy"
        ),
        "reference_speech_der": mean("settled", "reference_speech_der"),
        "final_wer": mean("final", "wer"),
    }
    if set(metrics) != set(recomputed_macro) or any(
        not math.isclose(float(metrics[name]), value, rel_tol=0, abs_tol=1e-12)
        for name, value in recomputed_macro.items()
        if isinstance(metrics.get(name), (int, float))
    ) or any(not isinstance(metrics.get(name), (int, float)) for name in recomputed_macro):
        return False

    expected_weighted = {
        field: sum(
            float(item["duration_seconds"])
            * float(item["metrics"]["settled"][field])  # type: ignore[index]
            for item in rows
        )
        / total_case_seconds
        for field in metric_fields
    }
    weighted = raw.get("duration_weighted")
    if not isinstance(weighted, dict) or set(weighted) != set(expected_weighted) or any(
        not isinstance(weighted.get(field), (int, float))
        or not math.isfinite(float(weighted[field]))
        or not math.isclose(
            float(weighted[field]), value, rel_tol=0, abs_tol=1e-12
        )
        for field, value in expected_weighted.items()
    ):
        return False

    expected_categories: dict[str, dict[str, float]] = {}
    for category in {str(item["category"]) for item in rows}:
        selected = [item for item in rows if item["category"] == category]
        expected_categories[category] = {
            field: mean("settled", field, selected) for field in metric_fields
        }
    categories = raw.get("per_category")
    if not isinstance(categories, dict) or set(categories) != set(expected_categories):
        return False
    for category, expected in expected_categories.items():
        observed = categories.get(category)
        if not isinstance(observed, dict) or set(observed) != set(expected):
            return False
        if any(
            not isinstance(observed.get(field), (int, float))
            or not math.isfinite(float(observed[field]))
            or not math.isclose(
                float(observed[field]), value, rel_tol=0, abs_tol=1e-12
            )
            for field, value in expected.items()
        ):
            return False

    for name, (comparison, bound) in QUALITY_BOUNDS.items():
        value = recomputed_macro[name]
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return False
        if comparison == "max" and float(value) > bound:
            return False
        if comparison == "min" and float(value) < bound:
            return False
    return True


def external_denominator_projection(
    payload: Mapping[str, object] | None,
) -> dict[str, dict[str, int]]:
    """Derive load-bearing external campaign units from retained raw arrays."""

    predicates = payload.get("predicates") if isinstance(payload, Mapping) else None
    indexed = (
        {
            item.get("id"): item
            for item in predicates
            if isinstance(item, dict)
        }
        if isinstance(predicates, list)
        else {}
    )

    def project(
        predicate_id: str,
        collected: int,
        valid: bool,
    ) -> dict[str, int]:
        predicate = indexed.get(predicate_id)
        counts = predicate.get("counts") if isinstance(predicate, dict) else None
        executed = (
            collected
            if isinstance(counts, dict) and counts.get("executed") == 1
            else 0
        )
        passed = collected if executed and valid else 0
        return {
            "collected": collected,
            "executed": executed,
            "passed": passed,
            "failed": collected if executed and not valid else 0,
            "skipped": 0,
            "unmeasured": collected if not executed else 0,
        }

    cross = indexed.get("cross_owner_matrix")
    cross_raw = cross.get("raw") if isinstance(cross, dict) else None
    cross_cases = cross_raw.get("cases") if isinstance(cross_raw, dict) else None
    cross_collected = len(cross_cases) if isinstance(cross_cases, list) else 0
    cross_valid = bool(
        isinstance(cross, dict)
        and _predicate_passes(cross)
        and _validate_raw_predicate(
            "cross_owner_matrix",
            cross,
            candidate_sha="",
            candidate_tree="",
            uv_lock_sha256="",
            fixtures={},
            wheel_record_projection_sha256="",
            dependency_projection_sha256="",
        )
    )

    capacity = indexed.get("four_session_capacity")
    capacity_raw = capacity.get("raw") if isinstance(capacity, dict) else None
    capacity_sessions = (
        capacity_raw.get("session_observations")
        if isinstance(capacity_raw, dict)
        else None
    )
    capacity_collected = (
        len(capacity_sessions) if isinstance(capacity_sessions, list) else 0
    )
    capacity_valid = bool(
        isinstance(capacity, dict)
        and _predicate_passes(capacity)
        and _validate_capacity(capacity)
    )

    overload = indexed.get("eight_session_overload")
    overload_raw = overload.get("raw") if isinstance(overload, dict) else None
    overload_sessions = (
        overload_raw.get("session_observations")
        if isinstance(overload_raw, dict)
        else None
    )
    overload_collected = (
        len(overload_sessions) if isinstance(overload_sessions, list) else 0
    )
    overload_valid = bool(
        isinstance(overload, dict)
        and _predicate_passes(overload)
        and _validate_overload(overload)
    )

    quality = indexed.get("quality_corpus")
    quality_raw = quality.get("raw") if isinstance(quality, dict) else None
    quality_cases = quality_raw.get("per_case") if isinstance(quality_raw, dict) else None
    quality_collected = len(quality_cases) if isinstance(quality_cases, list) else 0
    try:
        quality_windows = (
            sum(
                int(item["windows"])
                for item in quality_cases
                if isinstance(item, dict)
            )
            if isinstance(quality_cases, list)
            else 0
        )
    except (KeyError, TypeError, ValueError):
        quality_windows = 0
    quality_valid = bool(
        isinstance(quality, dict)
        and _predicate_passes(quality)
        and _validate_quality(quality)
    )
    return {
        "cross_owner_actions": project(
            "cross_owner_matrix", cross_collected, cross_valid
        ),
        "four_session_capacity": project(
            "four_session_capacity", capacity_collected, capacity_valid
        ),
        "eight_session_overload": project(
            "eight_session_overload", overload_collected, overload_valid
        ),
        "quality_sessions": project(
            "quality_corpus", quality_collected, quality_valid
        ),
        "quality_windows": project(
            "quality_corpus", quality_windows, quality_valid
        ),
    }


def _zero_mapping(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and all(item == 0 for item in value.values())


def _validate_raw_predicate(
    predicate_id: str,
    predicate: Mapping[str, object],
    *,
    candidate_sha: str,
    candidate_tree: str,
    uv_lock_sha256: str,
    fixtures: Mapping[str, str],
    wheel_record_projection_sha256: str,
    dependency_projection_sha256: str,
) -> bool:
    raw = predicate.get("raw")
    if not isinstance(raw, dict):
        return False
    if predicate_id == "installed_candidate_identity":
        process = raw.get("process")
        manifest = raw.get("manifest")
        descriptor = raw.get("descriptor")
        toolchain = raw.get("toolchain")
        accelerator = raw.get("accelerator")
        tls = raw.get("tls")
        inputs = raw.get("input_fixtures")
        file_input = inputs.get("file") if isinstance(inputs, dict) else None
        return (
            raw.get("candidate_sha") == candidate_sha
            and raw.get("candidate_tree") == candidate_tree
            and raw.get("uv_lock_sha256") == uv_lock_sha256
            and raw.get("fixtures") == fixtures
            and raw.get("candidate_header_sha") == candidate_sha
            and raw.get("wheel_record_verified") is True
            and int(raw.get("wheel_record_entries_verified", 0)) > 0
            and raw.get("wheel_record_projection_sha256") == wheel_record_projection_sha256
            and raw.get("dependency_projection_sha256") == dependency_projection_sha256
            and raw.get("sqlite_runtime") == REQUIRED_SQLITE
            and raw.get("aiosqlite") == "0.22.1"
            and raw.get("authlib") == "1.7.2"
            and isinstance(manifest, dict)
            and manifest.get("schema") == "moss-account-candidate.v1"
            and manifest.get("activation_state") == "staged_inert"
            and isinstance(manifest.get("release"), str)
            and bool(manifest["release"])
            and manifest.get("release_launcher")
            == f"{manifest['release']}/bin/mtd-account-web"
            and isinstance(manifest.get("release_launcher_sha256"), str)
            and len(manifest["release_launcher_sha256"]) == 64
            and manifest.get("release_admin_launcher")
            == f"{manifest['release']}/bin/mtd-admin"
            and isinstance(manifest.get("release_admin_launcher_sha256"), str)
            and len(manifest["release_admin_launcher_sha256"]) == 64
            and manifest.get("release_cutover_launcher")
            == f"{manifest['release']}/bin/mtd-phase2-cutover"
            and isinstance(manifest.get("release_cutover_launcher_sha256"), str)
            and len(manifest["release_cutover_launcher_sha256"]) == 64
            and manifest.get("release_vllm_launcher")
            == f"{manifest['release']}/bin/mtd-vllm"
            and isinstance(manifest.get("release_vllm_launcher_sha256"), str)
            and len(manifest["release_vllm_launcher_sha256"]) == 64
            and isinstance(manifest.get("web_unit_sha256"), str)
            and len(manifest["web_unit_sha256"]) == 64
            and isinstance(manifest.get("vllm_unit_sha256"), str)
            and len(manifest["vllm_unit_sha256"]) == 64
            and manifest.get("installed_units_match_manifest") is True
            and manifest.get("active_pointer_resolves_to_release") is True
            and isinstance(process, dict)
            and isinstance(process.get("pid"), int)
            and process["pid"] > 0
            and all(isinstance(process.get(key), str) and process[key] for key in ("cwd", "exe"))
            and isinstance(process.get("argv"), list)
            and len(process["argv"]) >= 3
            and process["argv"][0] == f"{manifest['release']}/bin/python"
            and process["argv"][1:3]
            == ["-m", "moss_transcribe_diarize.app.phase2_web_cli"]
            and isinstance(descriptor, dict)
            and descriptor.get("source_revision") == candidate_sha
            and all(
                isinstance(descriptor.get(key), str) and descriptor[key]
                for key in (
                    "provider_name",
                    "provider_revision",
                    "provider_manifest_hash",
                    "live_protocol_version",
                    "combined_config_hash",
                )
            )
            and isinstance(descriptor.get("schema_version"), int)
            and descriptor.get("sample_rate") == 16_000
            and isinstance(descriptor.get("frame_samples"), int)
            and int(descriptor["frame_samples"]) > 0
            and isinstance(descriptor.get("bounds"), dict)
            and bool(descriptor["bounds"])
            and isinstance(descriptor.get("config_hashes"), dict)
            and set(descriptor["config_hashes"])
            == {
                "endpoint_config_hash",
                "identity_config_hash",
                "decoder_config_hash",
                "combined_config_hash",
            }
            and all(
                isinstance(value, str) and len(value) == 64
                for value in descriptor["config_hashes"].values()
            )
            and isinstance(toolchain, dict)
            and set(toolchain) == {"chrome", "node", "npm", "ffmpeg", "ffprobe"}
            and all(isinstance(value, str) and value for value in toolchain.values())
            and isinstance(accelerator, dict)
            and set(accelerator) == {"vllm", "torch", "cuda"}
            and all(isinstance(value, str) and value for value in accelerator.values())
            and isinstance(tls, dict)
            and tls.get("trusted") is True
            and isinstance(tls.get("subject"), str)
            and bool(tls["subject"])
            and isinstance(tls.get("subject_alt_names"), list)
            and bool(tls["subject_alt_names"])
            and isinstance(tls.get("not_after"), str)
            and bool(tls["not_after"])
            and isinstance(file_input, dict)
            and isinstance(file_input.get("sha256"), str)
            and len(file_input["sha256"]) == 64
            and int(file_input.get("bytes", 0)) > 0
            and int(file_input.get("channels", 0)) > 0
            and int(file_input.get("sample_width_bytes", 0)) > 0
            and int(file_input.get("sample_rate_hz", 0)) > 0
            and int(file_input.get("frames", 0)) > 0
            and inputs.get("url") == QUALIFICATION_URL_FIXTURE
        )
    if predicate_id == "zero_work_end":
        return raw.get("active_live") == 0 and raw.get("active_file") == 0 and _zero_mapping(raw.get("queue_depths"))
    if predicate_id == "cross_owner_matrix":
        cases = raw.get("cases")
        if not isinstance(cases, list) or len(cases) != len(G1_CROSS_OWNER_MATRIX):
            return False
        indexed = {
            item.get("id"): item for item in cases if isinstance(item, dict)
        }
        if set(indexed) != set(G1_CROSS_OWNER_MATRIX):
            return False
        for case_id, (method, route, expected_status) in G1_CROSS_OWNER_MATRIX.items():
            item = indexed[case_id]
            if not (
                item.get("method") == method
                and item.get("route") == route
                and item.get("observed_status") == expected_status
                and item.get("owner_state_unchanged") is True
                and item.get("owner_content_matches") == 0
            ):
                return False
        return True
    if predicate_id == "sentinel_absence":
        surfaces = raw.get("surfaces")
        audio_checks = raw.get("audio_sentinel_checks")
        if not isinstance(surfaces, list) or len(surfaces) != len(G1_SENTINEL_SURFACES):
            return False
        indexed = {
            item.get("id"): item for item in surfaces if isinstance(item, dict)
        }
        return (
            set(indexed) == G1_SENTINEL_SURFACES
            and all(
                int(item.get("searches", 0)) > 0 and item.get("foreign_matches") == 0
                for item in indexed.values()
            )
            and isinstance(audio_checks, list)
            and len(audio_checks) == 2
            and all(
                isinstance(item, dict)
                and item.get("owner_status") == 200
                and item.get("owner_identity_match") is True
                and item.get("foreign_status") == 404
                and int(item.get("foreign_artifact_bytes", -1)) == 0
                for item in audio_checks
            )
        )
    if predicate_id == "same_account_convergence":
        return int(raw.get("clients", 0)) >= 2 and int(raw.get("observations", 0)) > 0 and raw.get("mismatches") == 0
    if predicate_id == "real_google_oauth":
        cookie = raw.get("cookie_contract")
        tls = raw.get("tls_identity")
        return (
            raw.get("provider") == "google"
            and raw.get("real_external_accounts") is True
            and raw.get("allowed_completed") == 1
            and raw.get("denied_completed") == 1
            and raw.get("denied_accounts_created") == 0
            and raw.get("tls_trusted_without_interstitial") is True
            and isinstance(tls, dict)
            and tls.get("trusted") is True
            and isinstance(tls.get("subject"), str)
            and bool(tls["subject"])
            and isinstance(tls.get("subject_alt_names"), list)
            and bool(tls["subject_alt_names"])
            and isinstance(tls.get("not_after"), str)
            and bool(tls["not_after"])
            and raw.get("browser_restart_session_survived") is True
            and raw.get("history_survived_restart") is True
            and raw.get("callback_url") == GOOGLE_CALLBACK_URL
            and raw.get("callback_observations") == 2
            and isinstance(cookie, dict)
            and cookie.get("cookie_secure") is True
            and cookie.get("cookie_http_only") is True
            and cookie.get("cookie_same_site") == "Lax"
        )
    if predicate_id == "revocation_lifecycle":
        return (
            int(raw.get("cases", 0)) >= 4
            and raw.get("failures") == 0
            and raw.get("late_commits") == 0
            and raw.get("stale_authority_revived") == 0
            and raw.get("durable_prefix_preserved") is True
            and raw.get("partial_audio_playable") is True
        )
    if predicate_id == "meeting_modes_history_restart":
        modes = raw.get("modes")
        submissions = raw.get("submissions")
        return (
            isinstance(modes, list)
            and set(modes) == {"live", "file", "multi_file", "url", "serial_batch"}
            and int(raw.get("same_account_clients", 0)) >= 2
            and raw.get("history_mismatches") == 0
            and raw.get("restart_failures") == 0
            and raw.get("one_item_failure_isolated") is True
            and isinstance(submissions, dict)
            and all(key in submissions for key in ("single_file", "multi_file", "url", "serial_batch", "browser_closed_after_accept"))
            and submissions.get("multi_file") == 2
            and submissions.get("url") == 2
            and submissions.get("accepted_failure") == 1
            and submissions.get("input_boundary_rejection") == 1
        )
    if predicate_id == "crash_recovery":
        return (
            int(raw.get("cases", 0)) > 0
            and raw.get("nonempty_durable_prefix") is True
            and raw.get("lost_commits") == 0
            and raw.get("durable_document_mismatches") == 0
            and raw.get("audio_prefix_failures") == 0
            and raw.get("process_replaced") is True
            and raw.get("resumed_capture") == 0
            and raw.get("non_interrupted_active_rows") == 0
        )
    if predicate_id == "audio_durability_download":
        return (
            int(raw.get("live_cases", 0)) > 0
            and int(raw.get("file_cases", 0)) > 0
            and raw.get("format_mismatches") == 0
            and raw.get("durability_failures") == 0
            and raw.get("cleanup_failures") == 0
            and raw.get("owner_download_failures") == 0
            and raw.get("foreign_leaks") == 0
            and raw.get("unauthenticated_failures") == 0
            and raw.get("revoked_failures") == 0
            and raw.get("partial_download_failures") == 0
            and int(raw.get("partial_or_unavailable_crash_cases", 0)) > 0
            and raw.get("path_failures") == 0
            and raw.get("permission_failures") == 0
            and raw.get("out_of_band_reconciled") is True
            and isinstance(raw.get("ffprobe"), list)
            and len(raw["ffprobe"]) >= 3
        )
    if predicate_id == "operator_control":
        interrupt = raw.get("interrupt_probe")
        surfaces = raw.get("status_surfaces")
        return (
            raw.get("socket_mode") == "0600"
            and raw.get("tcp_admin_surfaces") == 0
            and raw.get("forbidden_content_matches") == 0
            and raw.get("count_mismatches") == 0
            and isinstance(surfaces, dict)
            and surfaces.get("json_exact_projection") is True
            and surfaces.get("human_exact_projection") is True
            and surfaces.get("json_stderr_bytes") == 0
            and surfaces.get("human_stderr_bytes") == 0
            and surfaces.get("forbidden_matches") == 0
            and isinstance(interrupt, dict)
            and interrupt.get("admitted_work_observed") is True
            and interrupt.get("command_interrupted") is True
            and interrupt.get("durable_interrupted") is True
            and interrupt.get("transcript_unchanged") is True
            and interrupt.get("target_active_after") == 0
            and interrupt.get("queue_depth_after") == 0
            and interrupt.get("queued_item_started_events") == 0
            and interrupt.get("admitted_item_processed_events") == 0
            and interrupt.get("queued_item_discarded_events") == 1
            and interrupt.get("audio_partial_playable") is True
            and interrupt.get("late_frame_status") == 409
        )
    if predicate_id == "account_product_regression":
        suites = raw.get("suites")
        return (
            isinstance(suites, list)
            and len(suites) >= 4
            and all(
                isinstance(item, dict)
                and int(item.get("collected", 0)) > 0
                and item.get("executed") == item.get("collected")
                and item.get("passed") == item.get("collected")
                and item.get("failed") == 0
                and item.get("skipped") == 0
                and item.get("unmeasured") == 0
                for item in suites
            )
        )
    if predicate_id == "transcript_pane_fidelity":
        viewports = raw.get("viewports")
        reference = raw.get("reference_identity")
        return (
            isinstance(viewports, list)
            and {(item.get("width"), item.get("height")) for item in viewports if isinstance(item, dict)} == {(1440, 900), (1280, 800)}
            and all(
                float(item.get("total_difference", 1)) <= 0.02
                and float(item.get("largest_connected_difference", 1)) <= 0.01
                for item in viewports
                if isinstance(item, dict)
            )
            and isinstance(reference, dict)
            and reference.get("head")
            == "6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70"
            and reference.get("clean") is True
        )
    return True


def evaluate_external_report(
    payload: Mapping[str, object] | None,
    *,
    layer: str,
    candidate_sha: str,
    candidate_tree: str,
    uv_lock_sha256: str,
    fixtures: Mapping[str, str],
    wheel_record_projection_sha256: str,
    dependency_projection_sha256: str,
) -> tuple[dict[str, bool], list[str]]:
    outcomes = {gate: False for gate in CORE_GATES}
    if payload is None:
        return outcomes, [f"{layer}_unmeasured"]
    predicates = payload.get("predicates")
    if not isinstance(predicates, list):
        return outcomes, [f"{layer}_predicates_missing"]
    indexed = {
        (item.get("gate"), item.get("id")): item
        for item in predicates
        if isinstance(item, dict)
    }
    errors: list[str] = []
    for gate, required in EXTERNAL_REQUIREMENTS[layer].items():
        gate_passed = True
        for predicate_id in required:
            predicate = indexed.get((gate, predicate_id))
            if predicate is None:
                errors.append(f"{layer}:{gate}:{predicate_id}:missing")
                gate_passed = False
                continue
            passed = _predicate_passes(predicate)
            passed = passed and _validate_raw_predicate(
                predicate_id,
                predicate,
                candidate_sha=candidate_sha,
                candidate_tree=candidate_tree,
                uv_lock_sha256=uv_lock_sha256,
                fixtures=fixtures,
                wheel_record_projection_sha256=wheel_record_projection_sha256,
                dependency_projection_sha256=dependency_projection_sha256,
            )
            if predicate_id == "four_session_capacity":
                passed = passed and _validate_capacity(predicate)
            elif predicate_id == "eight_session_overload":
                passed = passed and _validate_overload(predicate)
            elif predicate_id == "quality_corpus":
                passed = passed and _validate_quality(predicate)
            if not passed:
                errors.append(f"{layer}:{gate}:{predicate_id}:failed")
                gate_passed = False
        outcomes[gate] = gate_passed
    return outcomes, errors


def _installed_identity_raw(payload: Mapping[str, object] | None) -> Mapping[str, object] | None:
    predicates = payload.get("predicates") if isinstance(payload, Mapping) else None
    if not isinstance(predicates, list):
        return None
    for predicate in predicates:
        if (
            isinstance(predicate, dict)
            and predicate.get("gate") == "G0"
            and predicate.get("id") == "installed_candidate_identity"
            and isinstance(predicate.get("raw"), dict)
        ):
            return predicate["raw"]
    return None


def _cross_layer_identity_errors(
    deployed: Mapping[str, object] | None,
    pre_admission: Mapping[str, object] | None,
) -> list[str]:
    first = _installed_identity_raw(deployed)
    second = _installed_identity_raw(pre_admission)
    if first is None or second is None:
        return ["cross_layer_identity_unmeasured"]
    fields = (
        "candidate_sha",
        "candidate_tree",
        "uv_lock_sha256",
        "fixtures",
        "candidate_header_sha",
        "wheel_record_projection_sha256",
        "dependency_projection_sha256",
        "sqlite_runtime",
        "aiosqlite",
        "authlib",
        "manifest",
        "toolchain",
        "accelerator",
        "tls",
        "input_fixtures",
        "descriptor",
    )
    errors = [f"cross_layer_identity_mismatch:{field}" for field in fields if first.get(field) != second.get(field)]
    for field in ("cwd", "exe", "argv"):
        first_process = first.get("process")
        second_process = second.get("process")
        if not (
            isinstance(first_process, dict)
            and isinstance(second_process, dict)
            and first_process.get(field) == second_process.get(field)
        ):
            errors.append(f"cross_layer_process_mismatch:{field}")
    return errors


def _run_rehearsal(
    config: object,
    *,
    bundle: AttemptBundle,
    repo: Path,
    forbidden: Sequence[bytes],
) -> tuple[bool, list[str]]:
    if not isinstance(config, dict):
        return False, ["cutover_rehearsal_unmeasured"]
    values = {key: config.get(key) for key in ("original_fixture", "candidate_manifest")}
    if any(not isinstance(value, str) or not value for value in values.values()):
        return False, ["cutover_rehearsal_paths"]
    with tempfile.TemporaryDirectory(prefix="moss-cutover-rehearsal-output-") as directory:
        output = Path(directory) / "state.json"
        result = execute_command(
            bundle=bundle,
            repo=repo,
            name="cutover-rehearsal",
            argv=(sys.executable, str(repo / "scripts" / "phase2-acceptance" / "rehearse.py")),
            forbidden=forbidden,
            environment={
                "MOSS_REHEARSAL_ORIGINAL_FIXTURE": str(
                    Path(str(values["original_fixture"])).expanduser().resolve()
                ),
                "MOSS_REHEARSAL_CANDIDATE_MANIFEST": str(
                    Path(str(values["candidate_manifest"])).expanduser().resolve()
                ),
                "MOSS_REHEARSAL_OUTPUT": str(output),
            },
        )
        if result.returncode or result.forbidden_matches or not output.is_file():
            return False, ["cutover_rehearsal_failed"]
        encoded = output.read_bytes()
    matches = _forbidden_matches(encoded, forbidden)
    if matches:
        bundle.write(
            "raw/cutover-rehearsal-content-boundary.json",
            {"bytes": len(encoded), "forbidden_matches": matches, "retained": False},
        )
        return False, ["cutover_rehearsal_content_boundary"]
    try:
        payload = json.loads(encoded)
    except json.JSONDecodeError:
        return False, ["cutover_rehearsal_invalid"]
    bundle.write_bytes("raw/cutover-rehearsal-state.json", encoded)
    required = (
        "block",
        "drain",
        "snapshot",
        "install",
        "verify",
        "forced_failure",
        "restore",
        "prove_original",
    )
    passed = (
        payload.get("production") is False
        and tuple(payload.get("steps", ())) == required
        and payload.get("runtime_views") == 2
        and int(payload.get("initial_work_units", 0)) > 0
        and payload.get("post_block_work_units") == payload.get("initial_work_units")
        and payload.get("drain_transitions") == payload.get("initial_work_units")
        and payload.get("post_block_admission_rejected") is True
        and payload.get("all_views_quiesced_and_zero") is True
        and int(payload.get("snapshot_bytes", 0)) > 0
        and payload.get("candidate_installed_and_verified") is True
        and payload.get("forced_failure_observed") is True
        and payload.get("original_restored") is True
        and payload.get("candidate_pointer_absent") is True
        and payload.get("vllm_runtime_mutations") == 0
        and payload.get("passed") is True
    )
    return passed, [] if passed else ["cutover_rehearsal_state"]


def _final_gate_table(
    *,
    identity_errors: Sequence[str],
    deterministic: Mapping[str, bool],
    deployed: Mapping[str, bool],
    pre_admission: Mapping[str, bool],
    wave: int,
) -> dict[str, object]:
    rows: dict[str, object] = {}
    for gate in CORE_GATES:
        layers = {
            "deterministic": bool(deterministic.get(gate)),
            "deployed": bool(deployed.get(gate)),
            "pre_admission": bool(pre_admission.get(gate)),
        }
        rows[gate] = {"layers": layers, "passed": not identity_errors and all(layers.values())}
    if wave >= 2:
        rows["G8"] = {"layers": {layer: False for layer in LAYERS}, "passed": False, "reason": "unmeasured"}
    if wave >= 3:
        rows["G9"] = {"layers": {layer: False for layer in LAYERS}, "passed": False, "reason": "unmeasured"}
    rows["G7"] = {"status": "UNCLAIMED", "passed": False, "owner": "Issue #23"}
    required = [*CORE_GATES, *(() if wave == 1 else ("G8",)), *(() if wave < 3 else ("G9",))]
    return {
        "gates": rows,
        "required": required,
        "passed": all(bool(rows[gate]["passed"]) for gate in required),
        "g7": "UNCLAIMED",
    }


def run_acceptance(*, wave: int, output: Path, repo: Path, profile_path: Path = DEFAULT_PROFILE) -> int:
    if wave not in (1, 2, 3):
        raise ValueError("wave must be 1, 2, or 3")
    source_identity = discover_candidate(repo)
    evidence_root = (repo / "evidence" / "phase2").resolve()
    resolved_output = output.resolve()
    expected_parent = evidence_root / f"wave-{wave}"
    expected_name = re.compile(
        rf"^[0-9]{{8}}T[0-9]{{6}}Z-{re.escape(str(source_identity['git_sha'])[:7])}$"
    )
    if resolved_output.parent != expected_parent or not expected_name.fullmatch(
        resolved_output.name
    ):
        raise ValueError(
            "output must be evidence/phase2/wave-<wave>/"
            "<YYYYMMDDTHHMMSSZ>-<git-short-sha> for this candidate"
        )
    profile, profile_errors = load_profile(profile_path)
    bundle = AttemptBundle(resolved_output)
    measurement_workspaces: list[Path] = []
    bundle.event("attempt_started", schema=SCHEMA, wave=wave)
    errors: list[str] = []
    try:
        errors.extend(profile_errors)
        candidate = source_identity
        wheel, wheel_errors = build_candidate_wheel(
            repo=repo, bundle=bundle, source_identity=source_identity
        )
        candidate["wheel"] = wheel
        errors.extend(wheel_errors)
        bundle.write("candidate-manifest.json", candidate)
        identity_errors = list(profile_errors)
        if candidate["dirty"]:
            identity_errors.append("candidate_dirty")
        if candidate["runtime"]["sqlite"] != REQUIRED_SQLITE:
            identity_errors.append("sqlite_runtime_mismatch")
        if candidate["runtime"]["aiosqlite"] != "0.22.1":
            identity_errors.append("aiosqlite_runtime_mismatch")
        if candidate["runtime"]["authlib"] != "1.7.2":
            identity_errors.append("authlib_runtime_mismatch")
        if not isinstance(candidate.get("wheel"), dict) or candidate["wheel"].get("record_verified") is not True:
            identity_errors.append("candidate_wheel_unmeasured")

        forbidden, forbidden_summary, forbidden_errors = _load_forbidden_values(profile)
        bundle.write("content-boundaries.json", forbidden_summary)
        errors.extend(forbidden_errors)
        identity_errors.extend(forbidden_errors)
        deterministic_requirements = {
            gate: {name for name, _, gates in DETERMINISTIC_COMMANDS if gate in gates}
            for gate in CORE_GATES
        }
        deterministic_passes = {gate: set() for gate in CORE_GATES}
        command_results: list[CommandResult] = []
        deterministic_errors: list[str] = []
        if not identity_errors:
            for name, template, gates in DETERMINISTIC_COMMANDS:
                argv = tuple(value.format(python=sys.executable) for value in template)
                result, command_errors = execute_deterministic_command(
                    bundle=bundle,
                    repo=repo,
                    name=name,
                    argv=argv,
                    forbidden=forbidden,
                )
                command_results.append(result)
                deterministic_errors.extend(command_errors)
                if (
                    result.returncode == 0
                    and result.forbidden_matches == 0
                    and not command_errors
                ):
                    for gate in gates:
                        deterministic_passes[gate].add(name)
            post_status = _git(
                repo,
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
                "--",
                ".",
                ":(exclude)evidence/phase2/**",
            )
            if post_status:
                identity_errors.append("candidate_became_dirty")
        else:
            bundle.event("deterministic_refused", reasons=identity_errors)

        deterministic = {
            gate: deterministic_passes[gate] == deterministic_requirements[gate]
            for gate in CORE_GATES
        }

        collector_errors: list[str] = []
        report_paths: dict[str, Path] = {}
        raw_dirs: dict[str, Path] = {}
        measurements = profile.get("measurements")
        for layer in ("deployed", "pre_admission"):
            measurement = (
                measurements.get(layer) if isinstance(measurements, dict) else None
            )
            if not isinstance(measurement, dict):
                collector_errors.append(f"{layer}_measurement_missing")
                continue
            workspace = Path(
                tempfile.mkdtemp(prefix=f"moss-phase2-{layer}-measurement-")
            ).resolve()
            measurement_workspaces.append(workspace)
            report_path = workspace / "observations.json"
            raw_dir = workspace / "raw"
            report_paths[layer] = report_path
            raw_dirs[layer] = raw_dir
            if not identity_errors:
                measure_argv = (
                    sys.executable,
                    str(repo / "scripts" / "phase2-acceptance" / "measure.py"),
                )
                measure_result = execute_command(
                    bundle=bundle,
                    repo=repo,
                    name=f"measure-{layer}",
                    argv=measure_argv,
                    forbidden=forbidden,
                    environment={
                        "MOSS_ACCEPTANCE_LAYER": layer,
                        "MOSS_ACCEPTANCE_CANDIDATE_SHA": str(candidate["git_sha"]),
                        "MOSS_ACCEPTANCE_RAW_DIR": str(raw_dir),
                        # Data-only configuration. No report, raw state, argv, or executable is
                        # accepted from the operator profile.
                        "MOSS_ACCEPTANCE_MEASUREMENT_CONFIG": json.dumps(
                            {
                                **{
                                    key: value
                                    for key, value in measurement.items()
                                    if key != "workspace"
                                },
                                "repo_root": str(repo),
                                "campaign_work_dir": str(workspace / "campaign"),
                                "content_boundary_files": profile.get("forbidden_files"),
                            },
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                )
                if measure_result.returncode not in (0, 2) or measure_result.forbidden_matches:
                    collector_errors.append(f"{layer}_measurement_failed")
                if not raw_dir.is_dir():
                    collector_errors.append(f"{layer}_measurement_raw_absent")
                    continue
                collect_argv = (
                    sys.executable,
                    str(repo / "scripts" / "phase2-acceptance" / "collect.py"),
                )
                result = execute_command(
                    bundle=bundle,
                    repo=repo,
                    name=f"collector-{layer}",
                    argv=collect_argv,
                    forbidden=forbidden,
                    environment={
                        "MOSS_ACCEPTANCE_LAYER": layer,
                        "MOSS_ACCEPTANCE_CANDIDATE_SHA": str(candidate["git_sha"]),
                        "MOSS_ACCEPTANCE_WHEEL_SHA256": str(candidate["wheel"]["sha256"]),
                        "MOSS_ACCEPTANCE_REPORT_PATH": str(report_path),
                        "MOSS_ACCEPTANCE_RAW_DIR": str(raw_dir),
                    },
                )
                if result.returncode or result.forbidden_matches:
                    collector_errors.append(f"{layer}_collector_failed")
                if not report_path.is_file():
                    collector_errors.append(f"{layer}_collector_report_absent")

        deployed_report, deployed_read_errors = _read_external_report(
            str(report_paths["deployed"]) if "deployed" in report_paths else None,
            layer="deployed",
            candidate_sha=str(candidate["git_sha"]),
            bundle=bundle,
            forbidden=forbidden,
        )
        pre_report, pre_read_errors = _read_external_report(
            str(report_paths["pre_admission"]) if "pre_admission" in report_paths else None,
            layer="pre_admission",
            candidate_sha=str(candidate["git_sha"]),
            bundle=bundle,
            forbidden=forbidden,
        )
        for layer, report in (("deployed", deployed_report), ("pre_admission", pre_report)):
            raw_dir = raw_dirs.get(layer)
            if raw_dir is not None:
                collector_errors.extend(
                    _capture_collector_artifacts(
                        report,
                        layer=layer,
                        raw_dir=raw_dir,
                        bundle=bundle,
                        forbidden=forbidden,
                    )
                )
        deployed, deployed_errors = evaluate_external_report(
            deployed_report,
            layer="deployed",
            candidate_sha=str(candidate["git_sha"]),
            candidate_tree=str(candidate["git_tree"]),
            uv_lock_sha256=str(candidate["uv_lock_sha256"]),
            fixtures=candidate["fixtures"],
            wheel_record_projection_sha256=str(candidate["wheel"]["record_projection_sha256"]),
            dependency_projection_sha256=str(candidate["dependency_projection"]["sha256"]),
        )
        pre_admission, pre_errors = evaluate_external_report(
            pre_report,
            layer="pre_admission",
            candidate_sha=str(candidate["git_sha"]),
            candidate_tree=str(candidate["git_tree"]),
            uv_lock_sha256=str(candidate["uv_lock_sha256"]),
            fixtures=candidate["fixtures"],
            wheel_record_projection_sha256=str(candidate["wheel"]["record_projection_sha256"]),
            dependency_projection_sha256=str(candidate["dependency_projection"]["sha256"]),
        )
        cross_layer_errors = _cross_layer_identity_errors(
            deployed_report, pre_report
        )
        rehearsal_passed, rehearsal_errors = _run_rehearsal(
            profile.get("cutover_rehearsal"), bundle=bundle, repo=repo, forbidden=forbidden
        )
        # Rehearsal is required tooling evidence, but never G7 or production admission.
        pre_admission["G0"] = pre_admission["G0"] and rehearsal_passed

        all_errors = [
            *errors,
            *identity_errors,
            *deterministic_errors,
            *collector_errors,
            *deployed_read_errors,
            *pre_read_errors,
            *deployed_errors,
            *pre_errors,
            *cross_layer_errors,
            *rehearsal_errors,
        ]
        qualification_blockers = [
            *identity_errors,
            *collector_errors,
            *deployed_read_errors,
            *pre_read_errors,
            *cross_layer_errors,
            *rehearsal_errors,
        ]
        table = _final_gate_table(
            identity_errors=qualification_blockers,
            deterministic=deterministic,
            deployed=deployed,
            pre_admission=pre_admission,
            wave=wave,
        )
        bundle.write("gate-table.json", table)
        verdict = {
            "schema": SCHEMA,
            "wave": wave,
            "candidate_sha": candidate["git_sha"],
            "qualified": bool(table["passed"]),
            "g7": "UNCLAIMED",
            "errors": sorted(set(all_errors)),
            "commands": [asdict(item) for item in command_results],
            "denominators": {
                "commands_collected": len(DETERMINISTIC_COMMANDS),
                "commands_executed": len(command_results),
                "commands_passed": sum(item.returncode == 0 and item.forbidden_matches == 0 for item in command_results),
                "commands_failed": sum(item.returncode != 0 or item.forbidden_matches != 0 for item in command_results),
                "commands_skipped": 0,
                "commands_unmeasured": len(DETERMINISTIC_COMMANDS) - len(command_results),
                "test_suites": {
                    item.name: item.denominators
                    for item in command_results
                    if item.denominators is not None
                },
                "external_campaigns": {
                    "deployed": external_denominator_projection(deployed_report),
                    "pre_admission": external_denominator_projection(pre_report),
                },
            },
        }
        bundle.finalize(verdict)
        print(json.dumps(verdict, indent=2, sort_keys=True))
        return 0 if verdict["qualified"] else 1
    except BaseException as exc:
        failure = {"schema": SCHEMA, "qualified": False, "g7": "UNCLAIMED", "error": f"{type(exc).__name__}: {exc}"}
        try:
            bundle.write("terminal-error.json", failure)
            bundle.event("attempt_failed", error=type(exc).__name__)
        finally:
            print(json.dumps(failure, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for workspace in measurement_workspaces:
            shutil.rmtree(workspace, ignore_errors=True)
        bundle.close()
