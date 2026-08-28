"""One crash-restorable transition from the quiesced Phase-1 image to pre-admission.

The public interface is deliberately only :class:`CutoverRun`: start one new attempt, or restore
one incomplete attempt.  Host commands are an adapter behind that interface; journal, archive,
activation, quarantine, and terminal-outcome policy remain here.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import socket
import ssl
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .installed_candidate import CandidateArtifacts, validated_candidate_artifacts
from .phase2_g7_canary import run_attended_g7_canary, validate_attended_g7


PROFILE_SCHEMA = "moss-phase2-cutover-profile.v1"
JOURNAL_SCHEMA = "moss-phase2-cutover-journal.v1"
SNAPSHOT_SCHEMA = "moss-phase2-cutover-snapshot.v1"
RESULT_SCHEMA = "moss-phase2-cutover-result.v1"
RESTORE_PLAN_SCHEMA = "moss-phase2-cutover-restore-plan.v1"
PHASE1_MARKER_BYTES = b"moss-phase1-creation-quiesced-v1\n"
TERMINAL_PHASES = frozenset({"restored", "preadmission", "SAFE_STOPPED"})
MUTATED_AFTER_SNAPSHOT = frozenset(
    {"activated", "units_profiles_swapped", "candidate_started", "qualification_started"}
)
PHASE1_UNITS = ("moss-web.service", "moss-live-web.service")
VLLM_UNIT = "moss-vllm.service"
CANDIDATE_WEB_UNIT = "moss-web.service"
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
REQUIRED_ACCOUNT_PROFILE_KEYS = frozenset(
    {
        "MOSS_GOOGLE_CLIENT_ID",
        "MOSS_GOOGLE_CLIENT_SECRET_FILE",
        "MOSS_OAUTH_COOKIE_SECRET_FILE",
        "MOSS_TLS_CERTFILE",
        "MOSS_TLS_KEYFILE",
        "MOSS_LIVE_PROVIDER_MANIFEST",
        "MOSS_PHASE2_DATABASE",
        "MOSS_PHASE2_CONTROL_SOCKET",
        "MOSS_FILE_WORK_ROOT",
        "MOSS_MEETING_AUDIO_ROOT",
    }
)


def _default_acceptance_profile() -> Path:
    return (
        Path.home() / ".config/moss-transcribe-diarize/phase2-acceptance.json"
    ).resolve(strict=False)


class CutoverRefused(RuntimeError):
    """Cutover cannot begin without violating a settled guard."""


class CutoverUnsafe(RuntimeError):
    """Restoration is uncertain; both product surfaces must remain stopped."""


@dataclass(frozen=True, slots=True)
class RuntimeView:
    name: str
    origin: str
    ca_file: Path | None


@dataclass(frozen=True, slots=True)
class CutoverProfile:
    path: Path
    candidate_manifest: Path
    phase1_marker: Path
    runtime_views: tuple[RuntimeView, RuntimeView]
    snapshot_paths: Mapping[str, Path]
    account_profile_source: Path
    vllm_profile_source: Path
    acceptance_profile: Path


@dataclass(frozen=True, slots=True)
class CutoverResult:
    terminal: str
    attempt: str
    candidate_sha: str
    g7: str = "UNCLAIMED"
    admitted: bool = False
    error: str | None = None


def result_payload(result: CutoverResult) -> dict[str, object]:
    return {"schema": RESULT_SCHEMA, **asdict(result)}


@dataclass(frozen=True, slots=True)
class OriginalState:
    service_states: Mapping[str, Mapping[str, object]]
    vllm: Mapping[str, object]
    runtime_views: tuple[Mapping[str, object], ...]


class CutoverOps(Protocol):
    """Private host seam; production and deterministic adapters exercise one state machine."""

    def capture_original_state(self) -> OriginalState: ...

    def enable_phase1_block(self) -> None: ...

    def disable_phase1_block(self) -> None: ...

    def runtime_statuses(self) -> tuple[Mapping[str, object], ...]: ...

    def stop_phase1(self) -> None: ...

    def start_phase1(self, original: OriginalState) -> None: ...

    def install_candidate(self, artifacts: CandidateArtifacts) -> None: ...

    def start_candidate(self, artifacts: CandidateArtifacts) -> None: ...

    def stop_candidate(self) -> None: ...

    def run_qualification(
        self,
        *,
        artifacts: CandidateArtifacts,
        candidate_sha: str,
        attempt: Path,
    ) -> Path: ...

    def run_attended_g7(
        self,
        *,
        candidate: Mapping[str, object],
    ) -> Mapping[str, object]: ...

    def verify_vllm_unchanged(self, original: OriginalState) -> bool: ...

    def safe_stop(self) -> None: ...


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("write made no progress")
        view = view[written:]


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_once(path: Path, payload: object) -> None:
    encoded = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        _write_all(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _atomic_private_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".stage", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        _write_all(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


class CutoverJournal:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, phase: str, **fields: object) -> None:
        if not phase:
            raise ValueError("journal phase is empty")
        sequence = len(self.read()) + 1
        encoded = (
            json.dumps(
                {
                    "schema": JOURNAL_SCHEMA,
                    "sequence": sequence,
                    "phase": phase,
                    **fields,
                },
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        try:
            _write_all(descriptor, encoded)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _fsync_directory(self.path.parent)

    def read(self) -> list[dict[str, object]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, object]] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
            for expected, line in enumerate(lines, 1):
                value = json.loads(line)
                if (
                    not isinstance(value, dict)
                    or value.get("schema") != JOURNAL_SCHEMA
                    or value.get("sequence") != expected
                    or not isinstance(value.get("phase"), str)
                ):
                    raise CutoverUnsafe("cutover journal is malformed")
                rows.append(value)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CutoverUnsafe("cutover journal is malformed") from exc
        return rows

    def last_phase(self) -> str | None:
        rows = self.read()
        return None if not rows else str(rows[-1]["phase"])


def _load_private_json(path: Path, *, schema: str) -> dict[str, object]:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise CutoverRefused(f"required private file is unavailable: {path}") from exc
    if mode != 0o600:
        raise CutoverRefused(f"required private file must be mode 0600: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CutoverRefused(f"required private JSON is invalid: {path}") from exc
    if not isinstance(value, dict) or value.get("schema") != schema:
        raise CutoverRefused(f"required private JSON schema mismatch: {path}")
    return value


def _resolved_path(value: object, *, field: str) -> Path:
    if not isinstance(value, str) or not value:
        raise CutoverRefused(f"cutover profile field is missing: {field}")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise CutoverRefused(f"cutover profile path must be absolute: {field}")
    return path.resolve(strict=False)


def _paths_overlap(paths: Sequence[Path]) -> bool:
    values = tuple(paths)
    return any(
        left == right or left in right.parents or right in left.parents
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    )


def load_cutover_profile(path: Path) -> CutoverProfile:
    resolved = path.expanduser().resolve()
    payload = _load_private_json(resolved, schema=PROFILE_SCHEMA)
    phase1 = payload.get("phase1")
    candidate = payload.get("candidate")
    if not isinstance(phase1, dict) or not isinstance(candidate, dict):
        raise CutoverRefused("cutover profile requires phase1 and candidate objects")
    raw_views = phase1.get("runtime_views")
    if not isinstance(raw_views, list) or len(raw_views) != 2:
        raise CutoverRefused("cutover requires exactly two Phase-1 runtime views")
    views: list[RuntimeView] = []
    for item in raw_views:
        if not isinstance(item, dict):
            raise CutoverRefused("Phase-1 runtime view is malformed")
        name = item.get("name")
        origin = item.get("origin")
        if name not in {"batch", "live"} or not isinstance(origin, str):
            raise CutoverRefused("Phase-1 runtime view identity is malformed")
        expected_origin = (
            "http://127.0.0.1:7860" if name == "batch" else "https://127.0.0.1:7861"
        )
        if origin != expected_origin:
            raise CutoverRefused("Phase-1 runtime views must use their exact loopback schemes")
        ca_value = item.get("ca_file")
        ca_file = None if ca_value is None else _resolved_path(ca_value, field=f"{name}.ca_file")
        if name == "live" and (ca_file is None or not ca_file.is_file()):
            raise CutoverRefused("Phase-1 live runtime view requires its trusted CA file")
        if name == "batch" and ca_file is not None:
            raise CutoverRefused("Phase-1 batch runtime view cannot declare TLS")
        views.append(RuntimeView(str(name), origin, ca_file))
    if {item.name for item in views} != {"batch", "live"}:
        raise CutoverRefused("cutover requires batch and live Phase-1 views")
    raw_snapshots = phase1.get("snapshot_paths")
    if not isinstance(raw_snapshots, dict):
        raise CutoverRefused("Phase-1 snapshot paths are missing")
    snapshots = {
        str(role): _resolved_path(value, field=f"snapshot_paths.{role}")
        for role, value in raw_snapshots.items()
        if isinstance(role, str) and role
    }
    if set(snapshots) != set(raw_snapshots) or not REQUIRED_SNAPSHOT_ROLES <= set(snapshots):
        raise CutoverRefused("Phase-1 snapshot roles are incomplete")
    if _paths_overlap(tuple(snapshots.values())):
        raise CutoverRefused("Phase-1 snapshot paths must not overlap")
    if any(not path.exists() and not path.is_symlink() for path in snapshots.values()):
        raise CutoverRefused("every Phase-1 snapshot source must exist before cutover")
    marker = _resolved_path(phase1.get("marker_path"), field="phase1.marker_path")
    expected_marker = (
        Path.home()
        / ".local/state/moss-transcribe-diarize/phase1-creation-quiesced"
    ).resolve(strict=False)
    if marker != expected_marker:
        raise CutoverRefused("cutover must use the exact deployed Phase-1 creation marker")
    acceptance_profile = _resolved_path(
        candidate.get("acceptance_profile"), field="candidate.acceptance_profile"
    )
    if acceptance_profile != _default_acceptance_profile():
        raise CutoverRefused("cutover must use the fixed Phase-2 acceptance profile")
    try:
        if stat.S_IMODE(acceptance_profile.stat().st_mode) != 0o600:
            raise CutoverRefused("Phase-2 acceptance profile must be mode 0600")
        if not isinstance(json.loads(acceptance_profile.read_text(encoding="utf-8")), dict):
            raise CutoverRefused("Phase-2 acceptance profile is malformed")
    except (OSError, json.JSONDecodeError) as exc:
        raise CutoverRefused("Phase-2 acceptance profile is unavailable") from exc
    return CutoverProfile(
        path=resolved,
        candidate_manifest=_resolved_path(
            payload.get("candidate_manifest"), field="candidate_manifest"
        ),
        phase1_marker=marker,
        runtime_views=(views[0], views[1]),
        snapshot_paths=snapshots,
        account_profile_source=_resolved_path(
            candidate.get("account_profile_source"), field="candidate.account_profile_source"
        ),
        vllm_profile_source=_resolved_path(
            candidate.get("vllm_profile_source"), field="candidate.vllm_profile_source"
        ),
        acceptance_profile=acceptance_profile,
    )


def _parse_env_file(path: Path) -> dict[str, str]:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError as exc:
        raise CutoverRefused(f"service profile is unavailable: {path}") from exc
    if mode != 0o600:
        raise CutoverRefused(f"service profile must be mode 0600: {path}")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, separator, value = stripped.partition("=")
        if not separator or not key or not value or key in values:
            raise CutoverRefused(f"service profile contains an invalid assignment: {path}")
        values[key] = value
    return values


def _candidate_state_paths(account_profile: Mapping[str, str]) -> dict[str, Path]:
    missing = REQUIRED_ACCOUNT_PROFILE_KEYS - set(account_profile)
    if missing:
        raise CutoverRefused(f"Account profile is missing required keys: {sorted(missing)}")
    paths = {
        "database": _resolved_path(account_profile["MOSS_PHASE2_DATABASE"], field="MOSS_PHASE2_DATABASE"),
        "database_wal": Path(
            f"{_resolved_path(account_profile['MOSS_PHASE2_DATABASE'], field='MOSS_PHASE2_DATABASE')}-wal"
        ),
        "database_shm": Path(
            f"{_resolved_path(account_profile['MOSS_PHASE2_DATABASE'], field='MOSS_PHASE2_DATABASE')}-shm"
        ),
        "control_socket": _resolved_path(account_profile["MOSS_PHASE2_CONTROL_SOCKET"], field="MOSS_PHASE2_CONTROL_SOCKET"),
        "file_work": _resolved_path(account_profile["MOSS_FILE_WORK_ROOT"], field="MOSS_FILE_WORK_ROOT"),
        "meeting_audio": _resolved_path(account_profile["MOSS_MEETING_AUDIO_ROOT"], field="MOSS_MEETING_AUDIO_ROOT"),
    }
    if len(set(paths.values())) != len(paths):
        raise CutoverRefused("candidate state paths must be distinct")
    for key in (
        "MOSS_GOOGLE_CLIENT_SECRET_FILE",
        "MOSS_OAUTH_COOKIE_SECRET_FILE",
        "MOSS_TLS_CERTFILE",
        "MOSS_TLS_KEYFILE",
        "MOSS_LIVE_PROVIDER_MANIFEST",
    ):
        dependency = _resolved_path(account_profile[key], field=key)
        if not dependency.is_file():
            raise CutoverRefused(f"Account prerequisite is missing: {key}")
    return paths


def _candidate_roots_empty(paths: Mapping[str, Path]) -> bool:
    for name, path in paths.items():
        if name in {"database", "database_wal", "database_shm", "control_socket"}:
            if path.exists() or path.is_symlink():
                return False
        elif path.exists() and (not path.is_dir() or any(path.iterdir())):
            return False
    return True


def _existing_device(path: Path) -> int:
    current = path
    while not current.exists():
        if current.parent == current:
            raise CutoverRefused(f"no existing parent for cutover path: {path}")
        current = current.parent
    return current.stat().st_dev


def _tree_member_rows(path: Path, *, role: str) -> list[dict[str, object]]:
    if not path.exists() and not path.is_symlink():
        return []
    members = [path]
    if path.is_dir() and not path.is_symlink():
        members.extend(sorted(path.rglob("*")))
    rows: list[dict[str, object]] = []
    for member in members:
        metadata = member.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            kind = "symlink"
            size = len(os.readlink(member).encode())
        elif stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            size = 0
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
            size = metadata.st_size
        else:
            raise CutoverRefused(f"snapshot role contains unsupported member: {role}")
        relative = "." if member == path else member.relative_to(path).as_posix()
        rows.append(
            {
                "relative": relative,
                "kind": kind,
                "mode": stat.S_IMODE(metadata.st_mode),
                "bytes": size,
            }
        )
    return rows


def _archive_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink(missing_ok=True)
    elif path.is_dir():
        shutil.rmtree(path)


def _copy_restored(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    stage = target.parent / f".{target.name}.moss-restore-stage"
    _remove_path(stage)
    if source.is_symlink():
        stage.symlink_to(os.readlink(source))
    elif source.is_dir():
        shutil.copytree(source, stage, symlinks=True)
    else:
        shutil.copy2(source, stage, follow_symlinks=False)
    _remove_path(target)
    os.replace(stage, target)
    _fsync_directory(target.parent)


class SystemCutoverOps:
    """Cooperating-host adapter; no direct product database access or second daemon."""

    def __init__(
        self,
        *,
        profile: CutoverProfile,
        artifacts: CandidateArtifacts | None,
        account_profile: Mapping[str, str],
    ) -> None:
        self.profile = profile
        self.artifacts = artifacts
        self.account_profile = account_profile
        self.home = Path.home()
        self.unit_dir = self.home / ".config/systemd/user"
        self.config_dir = self.home / ".config/moss-transcribe-diarize"
        self.activation = self.home / ".local/share/moss-transcribe-diarize/account-current"

    def _systemctl(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ("systemctl", "--user", *args), check=False, capture_output=True, text=True
        )
        if check and result.returncode:
            raise RuntimeError(f"systemctl {' '.join(args)} failed")
        return result

    def _unit_state(self, name: str) -> dict[str, object]:
        active = self._systemctl("is-active", name, check=False)
        enabled = self._systemctl("is-enabled", name, check=False)
        show = self._systemctl(
            "show",
            name,
            "--property=MainPID,ActiveEnterTimestampMonotonic",
            check=False,
        )
        fields = dict(
            line.split("=", 1) for line in show.stdout.splitlines() if "=" in line
        )
        pid = int(fields.get("MainPID", "0") or 0)
        argv: list[str] = []
        if pid > 0:
            argv = [
                item.decode("utf-8", "strict")
                for item in Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                if item
            ]
        return {
            "active": active.stdout.strip() == "active",
            "enabled": enabled.stdout.strip() == "enabled",
            "pid": pid,
            "started": fields.get("ActiveEnterTimestampMonotonic", ""),
            "argv": argv,
        }

    def _runtime_status(self, view: RuntimeView) -> Mapping[str, object]:
        context = None
        if view.ca_file is not None:
            context = ssl.create_default_context(cafile=str(view.ca_file))
        request = urllib.request.Request(
            f"{view.origin}/api/runtime", headers={"Cache-Control": "no-store"}
        )
        try:
            with urllib.request.urlopen(request, timeout=10, context=context) as response:
                payload = json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Phase-1 runtime view unavailable: {view.name}") from exc
        creation = payload.get("phase1_creation") if isinstance(payload, dict) else None
        if not isinstance(creation, dict):
            raise RuntimeError(f"Phase-1 runtime view malformed: {view.name}")
        expected = {
            "state",
            "entrants",
            "active_jobs",
            "queued_jobs",
            "active_live_sessions",
        }
        if set(creation) != expected:
            raise RuntimeError(f"Phase-1 runtime view shape mismatch: {view.name}")
        return {"name": view.name, **creation}

    def capture_original_state(self) -> OriginalState:
        states = {
            unit: self._unit_state(unit) for unit in (*PHASE1_UNITS, VLLM_UNIT)
        }
        if not states[VLLM_UNIT]["active"] or int(states[VLLM_UNIT]["pid"]) <= 0:
            raise CutoverRefused("vLLM must be active before cutover")
        return OriginalState(states, states[VLLM_UNIT], self.runtime_statuses())

    def enable_phase1_block(self) -> None:
        if self.profile.phase1_marker.exists():
            if self.profile.phase1_marker.read_bytes() != PHASE1_MARKER_BYTES:
                raise CutoverRefused("Phase-1 creation marker has unexpected contents")
            return
        _atomic_private_file(self.profile.phase1_marker, PHASE1_MARKER_BYTES)

    def disable_phase1_block(self) -> None:
        self.profile.phase1_marker.unlink(missing_ok=True)
        _fsync_directory(self.profile.phase1_marker.parent)

    def runtime_statuses(self) -> tuple[Mapping[str, object], ...]:
        return tuple(self._runtime_status(view) for view in self.profile.runtime_views)

    def stop_phase1(self) -> None:
        self._systemctl("stop", *PHASE1_UNITS)

    def start_phase1(self, original: OriginalState) -> None:
        self._systemctl("daemon-reload")
        for unit in PHASE1_UNITS:
            state = original.service_states[unit]
            self._systemctl("enable" if state["enabled"] else "disable", unit)
            if state["active"]:
                self._systemctl("start", unit)

    def install_candidate(self, artifacts: CandidateArtifacts) -> None:
        self.activation.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.activation.parent / ".account-current.cutover"
        temporary.unlink(missing_ok=True)
        temporary.symlink_to(artifacts.release)
        os.replace(temporary, self.activation)
        self.unit_dir.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name, source in artifacts.units.items():
            target = self.unit_dir / name
            _atomic_private_file(target, source.read_bytes())
            target.chmod(0o644)
        _atomic_private_file(
            self.config_dir / "moss-account.env", self.profile.account_profile_source.read_bytes()
        )
        _atomic_private_file(
            self.config_dir / "vllm.env", self.profile.vllm_profile_source.read_bytes()
        )
        self._systemctl("daemon-reload")

    def start_candidate(self, artifacts: CandidateArtifacts) -> None:
        self._systemctl("disable", "--now", "moss-live-web.service", check=False)
        self._systemctl("enable", CANDIDATE_WEB_UNIT)
        self._systemctl("start", CANDIDATE_WEB_UNIT)
        current = self._unit_state(CANDIDATE_WEB_UNIT)
        if not current["active"]:
            raise RuntimeError("candidate web unit did not start")
        with socket.socket() as probe:
            probe.settimeout(0.2)
            if probe.connect_ex(("127.0.0.1", 7860)) == 0:
                raise RuntimeError("retired plaintext port 7860 remains open")

    def stop_candidate(self) -> None:
        self._systemctl("stop", CANDIDATE_WEB_UNIT, check=False)

    def run_qualification(
        self,
        *,
        artifacts: CandidateArtifacts,
        candidate_sha: str,
        attempt: Path,
    ) -> Path:
        qualification = attempt / "qualification"
        subprocess.run(
            ("git", "clone", "--quiet", "--no-local", str(artifacts.checkout), str(qualification)),
            check=True,
        )
        subprocess.run(
            ("git", "-C", str(qualification), "checkout", "--quiet", "--detach", candidate_sha),
            check=True,
        )
        (qualification / ".venv").symlink_to(artifacts.release)
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        output = qualification / f"evidence/phase2/wave-1/{stamp}-{candidate_sha[:7]}"
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        sqlite_prefix = Path(str(json.loads(self.profile.candidate_manifest.read_text())["sqlite_prefix"]))
        environment["LD_LIBRARY_PATH"] = str(sqlite_prefix / "lib")
        completed = subprocess.run(
            (
                str(artifacts.release / "bin/python"),
                str(qualification / "scripts/phase2-acceptance/run.py"),
                "--wave",
                "1",
                "--output",
                str(output),
            ),
            cwd=qualification,
            env=environment,
            check=False,
        )
        if completed.returncode:
            raise RuntimeError("same-SHA Wave-1 qualification failed")
        return output

    def run_attended_g7(
        self,
        *,
        candidate: Mapping[str, object],
    ) -> Mapping[str, object]:
        return run_attended_g7_canary(
            acceptance_profile=self.profile.acceptance_profile,
            candidate=candidate,
        )

    def verify_vllm_unchanged(self, original: OriginalState) -> bool:
        return self._unit_state(VLLM_UNIT) == dict(original.vllm)

    def safe_stop(self) -> None:
        self._systemctl("stop", *PHASE1_UNITS, check=False)


class CutoverRun:
    """Deep cutover module: one forward run and one incomplete-attempt restore."""

    def __init__(
        self,
        *,
        profile: CutoverProfile,
        attempt: Path,
        candidate: Mapping[str, object],
        artifacts: CandidateArtifacts | None,
        account_profile: Mapping[str, str],
        state_paths: Mapping[str, Path],
        ops: CutoverOps,
        target_terminal: str | None,
    ) -> None:
        self.profile = profile
        self.attempt = attempt.resolve()
        self.candidate = candidate
        self.artifacts = artifacts
        self.account_profile = account_profile
        self.state_paths = state_paths
        self.ops = ops
        self.target_terminal = target_terminal
        self.journal = CutoverJournal(self.attempt / "journal.jsonl")
        self.lock_file = self.attempt / ".lock"
        home = Path.home()
        self.activation = home / ".local/share/moss-transcribe-diarize/account-current"
        self.unit_targets = {
            "moss-web.service": home / ".config/systemd/user/moss-web.service",
            "moss-vllm.service": home / ".config/systemd/user/moss-vllm.service",
            "moss-live-web.service": home / ".config/systemd/user/moss-live-web.service",
            "moss-account.env": home / ".config/moss-transcribe-diarize/moss-account.env",
            "vllm.env": home / ".config/moss-transcribe-diarize/vllm.env",
            "account-current": self.activation,
        }

    @staticmethod
    def _stored_profile(path: Path) -> CutoverProfile:
        payload = _load_private_json(path, schema=PROFILE_SCHEMA)
        phase1 = payload.get("phase1")
        candidate = payload.get("candidate")
        if not isinstance(phase1, dict) or not isinstance(candidate, dict):
            raise CutoverUnsafe("stored cutover profile is malformed")
        raw_views = phase1.get("runtime_views")
        snapshots = phase1.get("snapshot_paths")
        if not isinstance(raw_views, list) or len(raw_views) != 2 or not isinstance(snapshots, dict):
            raise CutoverUnsafe("stored cutover profile is malformed")
        views = tuple(
            RuntimeView(
                str(item["name"]),
                str(item["origin"]),
                None if item.get("ca_file") is None else Path(str(item["ca_file"])),
            )
            for item in raw_views
            if isinstance(item, dict)
        )
        if len(views) != 2:
            raise CutoverUnsafe("stored cutover profile is malformed")
        return CutoverProfile(
            path=path,
            candidate_manifest=Path(str(payload["candidate_manifest"])),
            phase1_marker=Path(str(phase1["marker_path"])),
            runtime_views=(views[0], views[1]),
            snapshot_paths={str(key): Path(str(value)) for key, value in snapshots.items()},
            account_profile_source=Path(str(candidate["account_profile_source"])),
            vllm_profile_source=Path(str(candidate["vllm_profile_source"])),
            acceptance_profile=Path(str(candidate["acceptance_profile"])),
        )

    @classmethod
    def prepare(
        cls,
        *,
        profile_path: Path,
        attempt: Path,
        terminal: str,
        ops: CutoverOps | None = None,
    ) -> "CutoverRun":
        if terminal not in {"restored", "preadmission"}:
            raise CutoverRefused("cutover terminal must be restored or preadmission")
        profile = load_cutover_profile(profile_path)
        candidate = _load_private_json(
            profile.candidate_manifest, schema="moss-account-candidate.v1"
        )
        try:
            artifacts = validated_candidate_artifacts(candidate)
        except ValueError as exc:
            raise CutoverRefused("staged candidate identity is invalid") from exc
        account_profile = _parse_env_file(profile.account_profile_source)
        _parse_env_file(profile.vllm_profile_source)
        state_paths = _candidate_state_paths(account_profile)
        if _paths_overlap((*profile.snapshot_paths.values(), *state_paths.values())):
            raise CutoverRefused("Phase-1 snapshot and candidate state paths must not overlap")
        if not _candidate_roots_empty(state_paths):
            raise CutoverRefused("candidate state roots are not empty")
        if profile.phase1_marker.exists() or profile.phase1_marker.is_symlink():
            raise CutoverRefused(
                "Phase-1 is already quiesced; restore its owning attempt instead"
            )
        target_paths = (
            Path.home() / ".config/moss-transcribe-diarize/moss-account.env",
            Path.home() / ".config/moss-transcribe-diarize/vllm.env",
        )
        if profile.account_profile_source in target_paths or profile.vllm_profile_source in target_paths:
            raise CutoverRefused("candidate service profiles must be inert staged sources")
        resolved_attempt = attempt.expanduser().resolve()
        if resolved_attempt.exists():
            raise CutoverRefused("cutover attempt already exists")
        resolved_attempt.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        attempt_device = _existing_device(resolved_attempt.parent)
        if any(_existing_device(path.parent) != attempt_device for path in state_paths.values()):
            raise CutoverRefused(
                "cutover attempt and candidate state must share one quarantine filesystem"
            )
        os.mkdir(resolved_attempt, mode=0o700)
        _fsync_directory(resolved_attempt.parent)
        _write_once(resolved_attempt / "profile.json", json.loads(profile.path.read_text()))
        _write_once(resolved_attempt / "candidate-manifest.json", candidate)
        _write_once(
            resolved_attempt / "restore-plan.json",
            {
                "schema": RESTORE_PLAN_SCHEMA,
                "candidate_sha": candidate["git_sha"],
                "candidate_state_paths": {
                    name: str(path) for name, path in state_paths.items()
                },
            },
        )
        adapter = ops or SystemCutoverOps(
            profile=profile, artifacts=artifacts, account_profile=account_profile
        )
        return cls(
            profile=profile,
            attempt=resolved_attempt,
            candidate=candidate,
            artifacts=artifacts,
            account_profile=account_profile,
            state_paths=state_paths,
            ops=adapter,
            target_terminal=terminal,
        )

    @classmethod
    def open_incomplete(
        cls,
        *,
        attempt: Path,
        ops: CutoverOps | None = None,
    ) -> "CutoverRun":
        resolved = attempt.expanduser().resolve()
        profile = cls._stored_profile(resolved / "profile.json")
        candidate = _load_private_json(
            resolved / "candidate-manifest.json", schema="moss-account-candidate.v1"
        )
        restore_plan = _load_private_json(
            resolved / "restore-plan.json", schema=RESTORE_PLAN_SCHEMA
        )
        raw_state_paths = restore_plan.get("candidate_state_paths")
        if (
            restore_plan.get("candidate_sha") != candidate.get("git_sha")
            or not isinstance(raw_state_paths, dict)
            or not raw_state_paths
        ):
            raise CutoverUnsafe("stored restore plan is malformed")
        state_paths = {
            str(name): Path(str(value)) for name, value in raw_state_paths.items()
        }
        adapter = ops or SystemCutoverOps(
            profile=profile, artifacts=None, account_profile={}
        )
        return cls(
            profile=profile,
            attempt=resolved,
            candidate=candidate,
            artifacts=None,
            account_profile={},
            state_paths=state_paths,
            ops=adapter,
            target_terminal=None,
        )

    def _locked(self):
        descriptor = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return os.fdopen(descriptor, "r+")

    @property
    def candidate_sha(self) -> str:
        return str(self.candidate["git_sha"])

    def _snapshot_sources(self) -> dict[str, Path]:
        values = dict(self.profile.snapshot_paths)
        for name, path in self.unit_targets.items():
            values[f"mutation_{name}"] = path
        if _paths_overlap(tuple(values.values())):
            raise CutoverRefused("snapshot and mutation targets overlap")
        attempt = self.attempt
        for path in values.values():
            if path == attempt or attempt in path.parents or path in attempt.parents:
                raise CutoverRefused("cutover attempt overlaps a snapshot source")
        return values

    def _create_snapshot(self) -> None:
        sources = self._snapshot_sources()
        archive_stage = self.attempt / ".phase1-snapshot.tar.stage"
        archive = self.attempt / "phase1-snapshot.tar"
        rows: list[dict[str, object]] = []
        archive_descriptor = os.open(
            archive_stage, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
        )
        with os.fdopen(archive_descriptor, "wb") as archive_stream:
            with tarfile.open(fileobj=archive_stream, mode="w") as output:
                for role, source in sorted(sources.items()):
                    existed = source.exists() or source.is_symlink()
                    members = _tree_member_rows(source, role=role)
                    rows.append(
                        {
                            "role": role,
                            "source": str(source),
                            "existed": existed,
                            "members": members,
                        }
                    )
                    if existed:
                        output.add(source, arcname=f"roots/{role}", recursive=True)
            archive_stream.flush()
            os.fsync(archive_stream.fileno())
        descriptor = os.open(archive_stage, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(archive_stage, archive)
        _fsync_directory(self.attempt)
        manifest = {
            "schema": SNAPSHOT_SCHEMA,
            "archive": archive.name,
            "archive_sha256": _archive_digest(archive),
            "sources": rows,
        }
        _write_once(self.attempt / "snapshot-manifest.json", manifest)
        self.journal.append(
            "snapshotted",
            archive_bytes=archive.stat().st_size,
            source_roles=len(rows),
        )

    def _validate_qualification(self, output: Path) -> None:
        verdict = json.loads((output / "verdict.json").read_text(encoding="utf-8"))
        gate_table = json.loads((output / "gate-table.json").read_text(encoding="utf-8"))
        candidate = json.loads(
            (output / "candidate-manifest.json").read_text(encoding="utf-8")
        )
        required = {"G0", "G1", "G2", "G3", "G4", "G5", "G6", "G10"}
        if (
            verdict.get("schema") != "moss-phase2-acceptance.v1"
            or verdict.get("wave") != 1
            or verdict.get("candidate_sha") != self.candidate_sha
            or verdict.get("qualified") is not True
            or verdict.get("g7") != "UNCLAIMED"
            or gate_table.get("passed") is not True
            or set(gate_table.get("required", ())) != required
            or candidate.get("git_sha") != self.candidate_sha
            or candidate.get("git_tree") != self.candidate.get("git_tree")
            or candidate.get("uv_lock_sha256") != self.candidate.get("uv_lock_sha256")
        ):
            raise RuntimeError("same-SHA Wave-1 qualification bundle is not complete")

    def _publish_terminal(
        self,
        result: CutoverResult,
        *,
        phase: str,
        fields: Mapping[str, object],
    ) -> None:
        stage = self.attempt / f".result.{phase}.json.stage"
        final = self.attempt / "result.json"
        _write_once(stage, result_payload(result))
        self.journal.append(phase, **fields)
        try:
            os.replace(stage, final)
            _fsync_directory(self.attempt)
        except OSError:
            # The fsynced terminal journal is authoritative.  A missing convenience
            # projection cannot change or roll back that host state.
            pass

    def _all_drained(self, statuses: Sequence[Mapping[str, object]]) -> bool:
        expected = {"batch", "live"}
        if {row.get("name") for row in statuses} != expected:
            raise RuntimeError("Phase-1 runtime views changed identity")
        return all(
            row.get("state") == "quiesced"
            and all(
                isinstance(row.get(key), int) and int(row[key]) == 0
                for key in (
                    "entrants",
                    "active_jobs",
                    "queued_jobs",
                    "active_live_sessions",
                )
            )
            for row in statuses
        )

    def _all_restored_open(self, statuses: Sequence[Mapping[str, object]]) -> bool:
        return (
            {row.get("name") for row in statuses} == {"batch", "live"}
            and all(
                row.get("state") == "open"
                and all(
                    isinstance(row.get(key), int) and int(row[key]) == 0
                    for key in (
                        "entrants",
                        "active_jobs",
                        "queued_jobs",
                        "active_live_sessions",
                    )
                )
                for row in statuses
            )
        )

    def run(self) -> CutoverResult:
        with self._locked():
            if self.journal.read():
                raise CutoverRefused("cutover attempt cannot be resumed")
            original = self.ops.capture_original_state()
            if (
                {row.get("name") for row in original.runtime_views} != {"batch", "live"}
                or any(row.get("state") != "open" for row in original.runtime_views)
                or any(
                    set(row)
                    != {
                        "name",
                        "state",
                        "entrants",
                        "active_jobs",
                        "queued_jobs",
                        "active_live_sessions",
                    }
                    or any(
                        not isinstance(row.get(key), int) or int(row[key]) < 0
                        for key in (
                            "entrants",
                            "active_jobs",
                            "queued_jobs",
                            "active_live_sessions",
                        )
                    )
                    for row in original.runtime_views
                )
                or any(
                    not bool(original.service_states[unit].get("active"))
                    for unit in PHASE1_UNITS
                )
            ):
                raise CutoverRefused("Phase-1 must be open with both runtime views active")
            if self.artifacts is None:
                raise CutoverUnsafe("new cutover attempt lacks candidate artifacts")
            _write_once(self.attempt / "original-state.json", asdict(original))
            self.journal.append(
                "started",
                candidate_sha=self.candidate_sha,
                target_terminal=self.target_terminal,
                g7="UNCLAIMED",
                admitted=False,
            )
            try:
                self.ops.enable_phase1_block()
                self.journal.append("blocked", runtime_views=2)
                while True:
                    statuses = self.ops.runtime_statuses()
                    self.journal.append(
                        "drain_observed",
                        views=[
                            {
                                key: row[key]
                                for key in (
                                    "name",
                                    "state",
                                    "entrants",
                                    "active_jobs",
                                    "queued_jobs",
                                    "active_live_sessions",
                                )
                            }
                            for row in statuses
                        ],
                        work=sum(
                            int(row[key])
                            for row in statuses
                            for key in (
                                "entrants",
                                "active_jobs",
                                "queued_jobs",
                                "active_live_sessions",
                            )
                        ),
                    )
                    if self._all_drained(statuses):
                        break
                    time.sleep(1)
                self.journal.append("drained")
                self.ops.stop_phase1()
                self.journal.append("old_stopped")
                self._create_snapshot()
                self.ops.install_candidate(self.artifacts)
                self.journal.append("activated", release=str(self.artifacts.release))
                if not self.ops.verify_vllm_unchanged(original):
                    raise RuntimeError("vLLM process changed during unit/profile swap")
                self.journal.append("units_profiles_swapped", vllm_unchanged=True)
                self.ops.start_candidate(self.artifacts)
                self.journal.append("candidate_started", admitted=False)
                self.journal.append("qualification_started")
                output = self.ops.run_qualification(
                    artifacts=self.artifacts,
                    candidate_sha=self.candidate_sha,
                    attempt=self.attempt,
                )
                self._validate_qualification(output)
                if not self.ops.verify_vllm_unchanged(original):
                    raise RuntimeError("vLLM process changed during qualification")
                self.journal.append("attended_g7_started", admitted=False)
                attended = self.ops.run_attended_g7(candidate=self.candidate)
                validate_attended_g7(attended, candidate=self.candidate)
                _write_once(self.attempt / "attended-g7.json", attended)
                self.journal.append(
                    "attended_g7_complete",
                    evidence="attended-g7.json",
                    g7="PASS" if self.target_terminal == "preadmission" else "UNCLAIMED",
                    admitted=False,
                )
                if not self.ops.verify_vllm_unchanged(original):
                    raise RuntimeError("vLLM process changed during attended canary")
                if self.target_terminal == "restored":
                    self.journal.append(
                        "planned_restore",
                        qualification_bundle=str(output.relative_to(self.attempt)),
                        g7="UNCLAIMED",
                        admitted=False,
                    )
                    return self._restore_locked(
                        original=original,
                        cause="planned_post_canary_restore",
                        error=None,
                    )
                result = CutoverResult(
                    "preadmission", str(self.attempt), self.candidate_sha, g7="PASS"
                )
                self._publish_terminal(
                    result,
                    phase="preadmission",
                    fields={
                        "qualification_bundle": str(output.relative_to(self.attempt)),
                        "g7": "PASS",
                        "admitted": False,
                    },
                )
                return result
            except BaseException as exc:
                self.journal.append("failure_observed", error=type(exc).__name__)
                return self._restore_locked(
                    original=original,
                    cause=type(exc).__name__,
                    error=type(exc).__name__,
                )

    def restore(self) -> CutoverResult:
        with self._locked():
            try:
                phase = self.journal.last_phase()
            except CutoverUnsafe:
                return self._safe_stopped("journal_uncertain")
            if phase is None:
                raise CutoverRefused("cutover attempt has no durable state")
            if phase in TERMINAL_PHASES:
                raise CutoverRefused("terminal cutover attempt cannot be restored")
            if phase == "restore_started":
                return self._safe_stopped("prior_restore_interrupted")
            original_payload = json.loads(
                (self.attempt / "original-state.json").read_text(encoding="utf-8")
            )
            original = OriginalState(
                service_states=original_payload["service_states"],
                vllm=original_payload["vllm"],
                runtime_views=tuple(original_payload["runtime_views"]),
            )
            return self._restore_locked(
                original=original,
                cause="operator_restore",
                error=None,
            )

    def _quarantine_candidate_state(self) -> None:
        quarantine = self.attempt / "candidate-quarantine"
        quarantine.mkdir(mode=0o700, exist_ok=True)
        for role, path in self.state_paths.items():
            if not path.exists() and not path.is_symlink():
                continue
            target = quarantine / role
            if target.exists() or target.is_symlink():
                raise CutoverUnsafe("candidate quarantine target already exists")
            if path.parent.stat().st_dev != quarantine.stat().st_dev:
                raise CutoverUnsafe("candidate quarantine is not on the candidate filesystem")
            os.replace(path, target)
            _fsync_directory(path.parent)
            _fsync_directory(quarantine)

    def _restore_snapshot(self) -> None:
        manifest_path = self.attempt / "snapshot-manifest.json"
        archive = self.attempt / "phase1-snapshot.tar"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("schema") != SNAPSHOT_SCHEMA
            or manifest.get("archive") != archive.name
            or manifest.get("archive_sha256") != _archive_digest(archive)
        ):
            raise CutoverUnsafe("Phase-1 snapshot identity is uncertain")
        extraction = self.attempt / ".restore-extraction"
        _remove_path(extraction)
        extraction.mkdir(mode=0o700)
        with tarfile.open(archive, mode="r") as source:
            members = source.getmembers()
            if any(
                Path(member.name).is_absolute()
                or ".." in Path(member.name).parts
                or not member.name.startswith("roots/")
                for member in members
            ):
                raise CutoverUnsafe("Phase-1 snapshot contains an unsafe member")
            source.extractall(extraction)
        rows = manifest.get("sources")
        if not isinstance(rows, list):
            raise CutoverUnsafe("Phase-1 snapshot source manifest is absent")
        for row in rows:
            if not isinstance(row, dict):
                raise CutoverUnsafe("Phase-1 snapshot source manifest is malformed")
            role = row.get("role")
            source_value = row.get("source")
            existed = row.get("existed")
            if not isinstance(role, str) or not isinstance(source_value, str) or not isinstance(existed, bool):
                raise CutoverUnsafe("Phase-1 snapshot source manifest is malformed")
            target = Path(source_value)
            _remove_path(target)
            if existed:
                restored = extraction / "roots" / role
                if not restored.exists() and not restored.is_symlink():
                    raise CutoverUnsafe("Phase-1 snapshot member is absent")
                _copy_restored(restored, target)
        shutil.rmtree(extraction)

    def _restore_locked(
        self,
        *,
        original: OriginalState,
        cause: str,
        error: str | None,
    ) -> CutoverResult:
        self.journal.append("restore_started", cause=cause)
        try:
            self.ops.stop_candidate()
            if (self.attempt / "snapshot-manifest.json").exists():
                self._quarantine_candidate_state()
                self._restore_snapshot()
            self.ops.start_phase1(original)
            self.ops.disable_phase1_block()
            if not self.ops.verify_vllm_unchanged(original):
                raise CutoverUnsafe("vLLM process changed during cutover or restore")
            if not self._all_restored_open(self.ops.runtime_statuses()):
                raise CutoverUnsafe("restored Phase-1 runtime views are not open and zero")
            result = CutoverResult(
                "restored", str(self.attempt), self.candidate_sha, error=error
            )
            self._publish_terminal(
                result,
                phase="restored",
                fields={"cause": cause, "g7": "UNCLAIMED", "admitted": False},
            )
            return result
        except BaseException as exc:
            return self._safe_stopped(type(exc).__name__)

    def _safe_stopped(self, reason: str) -> CutoverResult:
        try:
            self.ops.enable_phase1_block()
        except BaseException as exc:
            reason = f"{reason}+{type(exc).__name__}"
        finally:
            self.ops.safe_stop()
        result = CutoverResult(
            "SAFE_STOPPED", str(self.attempt), self.candidate_sha, error=reason
        )
        try:
            last_phase = self.journal.last_phase()
        except CutoverUnsafe:
            try:
                _atomic_private_file(
                    self.attempt / "result.json",
                    (json.dumps(result_payload(result), sort_keys=True) + "\n").encode(),
                )
            except OSError:
                pass
            return result
        if last_phase != "SAFE_STOPPED":
            self._publish_terminal(
                result,
                phase="SAFE_STOPPED",
                fields={"reason": reason, "g7": "UNCLAIMED", "admitted": False},
            )
        return result
