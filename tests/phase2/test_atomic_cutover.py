from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import stat
import threading
from pathlib import Path

import pytest

from moss_transcribe_diarize import phase2_cutover as cutover
from moss_transcribe_diarize.app import phase2_cutover_cli
from moss_transcribe_diarize.app.phase2_cutover_cli import parse_args
from moss_transcribe_diarize.phase2_cutover import (
    PHASE1_MARKER_BYTES,
    REQUIRED_SNAPSHOT_ROLES,
    CutoverJournal,
    CutoverRefused,
    CutoverResult,
    CutoverRun,
    CutoverUnsafe,
    OriginalState,
    SystemCutoverOps,
    load_cutover_profile,
)
from moss_transcribe_diarize.installed_candidate import validated_candidate_artifacts
from moss_transcribe_diarize.phase2_g7_canary import (
    AttendedCanaryError,
    G7_EVIDENCE_SCHEMA,
    G7_EVIDENCE_SOURCE,
    G7_PRODUCTION_ORIGIN,
    validate_attended_g7,
)


def _write_private(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)


def _commit_checkout(path: Path) -> str:
    subprocess.run(("git", "init", "-q", str(path)), check=True)
    subprocess.run(("git", "-C", str(path), "config", "user.email", "test@example.com"), check=True)
    subprocess.run(("git", "-C", str(path), "config", "user.name", "Test"), check=True)
    subprocess.run(("git", "-C", str(path), "add", "."), check=True)
    subprocess.run(("git", "-C", str(path), "commit", "-qm", "candidate"), check=True)
    return subprocess.check_output(("git", "-C", str(path), "rev-parse", "HEAD"), text=True).strip()


def _cutover_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(cutover, "check_space", lambda: [])
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    release = tmp_path / "release"
    (release / "bin").mkdir(parents=True)
    launchers = {}
    for name in ("mtd-account-web", "mtd-admin", "mtd-phase2-cutover", "mtd-vllm"):
        path = release / "bin" / name
        path.write_text(f"{name}\n", encoding="utf-8")
        launchers[name] = path
    checkout = tmp_path / "checkout"
    unit_root = checkout / "ops/systemd"
    unit_root.mkdir(parents=True)
    units = {}
    for name in ("moss-web.service", "moss-vllm.service"):
        path = unit_root / name
        path.write_text(f"candidate {name}\n", encoding="utf-8")
        units[name] = path
    sha = _commit_checkout(checkout)
    manifest = tmp_path / "candidate.json"
    payload = {
        "schema": "moss-account-candidate.v1",
        "activation_state": "staged_inert",
        "git_sha": sha,
        "git_tree": subprocess.check_output(
            ("git", "-C", str(checkout), "rev-parse", "HEAD^{tree}"), text=True
        ).strip(),
        "uv_lock_sha256": "a" * 64,
        "sqlite_prefix": str(tmp_path / "sqlite-3.53.4"),
        "release": str(release),
        "qualification_checkout": str(checkout),
        "release_launcher": str(launchers["mtd-account-web"]),
        "release_launcher_sha256": hashlib.sha256(
            launchers["mtd-account-web"].read_bytes()
        ).hexdigest(),
        "release_admin_launcher": str(launchers["mtd-admin"]),
        "release_admin_launcher_sha256": hashlib.sha256(
            launchers["mtd-admin"].read_bytes()
        ).hexdigest(),
        "release_cutover_launcher": str(launchers["mtd-phase2-cutover"]),
        "release_cutover_launcher_sha256": hashlib.sha256(
            launchers["mtd-phase2-cutover"].read_bytes()
        ).hexdigest(),
        "release_vllm_launcher": str(launchers["mtd-vllm"]),
        "release_vllm_launcher_sha256": hashlib.sha256(
            launchers["mtd-vllm"].read_bytes()
        ).hexdigest(),
        "web_unit_path": str(units["moss-web.service"]),
        "web_unit_sha256": hashlib.sha256(units["moss-web.service"].read_bytes()).hexdigest(),
        "vllm_unit_path": str(units["moss-vllm.service"]),
        "vllm_unit_sha256": hashlib.sha256(units["moss-vllm.service"].read_bytes()).hexdigest(),
    }
    _write_private(manifest, payload)

    prerequisites = tmp_path / "prerequisites"
    prerequisites.mkdir()
    for name in ("google-secret", "cookie-secret", "tls.crt", "tls.key", "provider.json"):
        (prerequisites / name).write_text(name, encoding="utf-8")
    account_profile = tmp_path / "staged/moss-account.env"
    account_profile.parent.mkdir()
    state = home / ".local/share/moss-transcribe-diarize/account-state"
    account_profile.write_text(
        "\n".join(
            (
                "MOSS_GOOGLE_CLIENT_ID=client",
                f"MOSS_GOOGLE_CLIENT_SECRET_FILE={prerequisites / 'google-secret'}",
                f"MOSS_OAUTH_COOKIE_SECRET_FILE={prerequisites / 'cookie-secret'}",
                f"MOSS_TLS_CERTFILE={prerequisites / 'tls.crt'}",
                f"MOSS_TLS_KEYFILE={prerequisites / 'tls.key'}",
                f"MOSS_LIVE_PROVIDER_MANIFEST={prerequisites / 'provider.json'}",
                f"MOSS_PHASE2_DATABASE={state / 'phase2.sqlite3'}",
                f"MOSS_PHASE2_CONTROL_SOCKET={state / 'control.sock'}",
                f"MOSS_FILE_WORK_ROOT={state / 'file-work'}",
                f"MOSS_MEETING_AUDIO_ROOT={state / 'audio'}",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    account_profile.chmod(0o600)
    vllm_profile = tmp_path / "staged/vllm.env"
    vllm_profile.write_text("MOSS_GPU_MEMORY_UTILIZATION=0.30\n", encoding="utf-8")
    vllm_profile.chmod(0o600)
    acceptance_profile = home / ".config/moss-transcribe-diarize/phase2-acceptance.json"
    _write_private(acceptance_profile, {"fixed": True})

    old_checkout = tmp_path / "phase1-checkout"
    gpu_venv = tmp_path / "phase1-gpu-venv"
    model = tmp_path / "phase1-model"
    for path, value in ((old_checkout, "source"), (gpu_venv, "venv"), (model, "model")):
        path.mkdir()
        (path / "state").write_text(value, encoding="utf-8")
    (old_checkout / "runs").mkdir()
    (old_checkout / "runs/job.json").write_text("batch", encoding="utf-8")
    (old_checkout / "live-runs").mkdir()
    (old_checkout / "live-runs/session.json").write_text("live", encoding="utf-8")
    phase1_external = tmp_path / "phase1-external"
    phase1_external.mkdir()
    external_names = {
        "phase1_provider_manifest": "live-provider-manifest.json",
        "phase1_auth_state": "live-auth.json",
        "phase1_shared_token": "shared-token",
        "phase1_tls_cert": "live.crt",
        "phase1_tls_key": "live.key",
        "phase1_vector_journal": "speaker-vectors.jsonl",
    }
    external_paths = {}
    for role, name in external_names.items():
        path = phase1_external / name
        path.write_text(role, encoding="utf-8")
        external_paths[role] = path
    snapshot_paths = {
        "phase1_checkout": old_checkout,
        **external_paths,
        "phase1_gpu_venv": gpu_venv,
        "phase1_model": model,
    }
    unit_dir = home / ".config/systemd/user"
    config_dir = home / ".config/moss-transcribe-diarize"
    unit_dir.mkdir(parents=True)
    config_dir.mkdir(parents=True, exist_ok=True)
    (unit_dir / "moss-web.service").write_text("old web\n", encoding="utf-8")
    (unit_dir / "moss-vllm.service").write_text("old vllm\n", encoding="utf-8")
    (unit_dir / "moss-live-web.service").write_text("old live\n", encoding="utf-8")
    (config_dir / "vllm.env").write_text("old vllm profile\n", encoding="utf-8")
    marker = home / ".local/state/moss-transcribe-diarize/phase1-creation-quiesced"
    profile = tmp_path / "cutover.json"
    _write_private(
        profile,
        {
            "schema": "moss-phase2-cutover-profile.v1",
            "candidate_manifest": str(manifest),
            "phase1": {
                "marker_path": str(marker),
                "runtime_views": [
                    {"name": "batch", "origin": "http://127.0.0.1:7860", "ca_file": None},
                    {"name": "live", "origin": "https://127.0.0.1:7861", "ca_file": str(external_paths["phase1_tls_cert"])},
                ],
                "snapshot_paths": {
                    role: str(path) for role, path in snapshot_paths.items()
                },
            },
            "candidate": {
                "account_profile_source": str(account_profile),
                "vllm_profile_source": str(vllm_profile),
                "acceptance_profile": str(acceptance_profile),
            },
        },
    )
    return {
        "home": home,
        "release": release,
        "checkout": checkout,
        "candidate": payload,
        "manifest": manifest,
        "profile": profile,
        "staged": account_profile.parent,
        "acceptance_profile": acceptance_profile,
        "marker": marker,
        "state": state,
        "old_paths": (old_checkout, gpu_venv, model),
        "snapshot_paths": snapshot_paths,
    }


def _attended_evidence(candidate, *, source=G7_EVIDENCE_SOURCE):
    scenario_rows = []
    for scenario, surface in (
        ("microphone_meeting_tab", "browser"),
        ("microphone_entire_screen", "monitor"),
    ):
        scenario_rows.append(
            {
                "id": scenario,
                "session_id": f"meeting-{scenario}",
                "source_revision": candidate["git_sha"],
                "display_surface": surface,
                "display_audio_tracks": 1,
                "meter_nonzero_samples": {"microphone": 1, "system": 1},
                "frames": {
                    lane: {
                        "accepted_frames": 3,
                        "first_sequence": 0,
                        "last_sequence": 2,
                        "sequence_gaps": 0,
                        "geometry_mismatches": 0,
                    }
                    for lane in ("microphone", "system")
                },
                "distinct_speakers": 2,
                "meeting_status": "completed",
                "audio_state": "available",
                "owner_download_status": 200,
                "audio_probe": {
                    "codec": "mp3",
                    "sample_rate_hz": 16_000,
                    "channels": 1,
                    "bit_rate_bps": 48_000,
                    "byte_count": 123,
                },
            }
        )
    return {
        "schema": G7_EVIDENCE_SCHEMA,
        "source": source,
        "production_origin": True,
        "operator_attended": True,
        "admitted": False,
        "origin": G7_PRODUCTION_ORIGIN,
        "candidate": {
            key: candidate[key] for key in ("git_sha", "git_tree", "uv_lock_sha256")
        },
        "chrome_version": "Chrome/fixture",
        "scenarios": scenario_rows,
    }


class FakeCutoverOps:
    def __init__(
        self,
        fixture,
        *,
        qualification_fails: bool = False,
        qualification_sha_mismatch: bool = False,
        attended_fails: bool = False,
        attended_source: str = G7_EVIDENCE_SOURCE,
        crash: bool = False,
    ):
        self.fixture = fixture
        self.qualification_fails = qualification_fails
        self.qualification_sha_mismatch = qualification_sha_mismatch
        self.attended_fails = attended_fails
        self.attended_source = attended_source
        self.crash = crash
        self.phase1_running = True
        self.candidate_running = False
        self.safe_stopped = False
        self.attended_calls = 0
        self.vllm = {"active": True, "enabled": True, "pid": 42, "started": "123", "argv": ["python", "-m", "vllm"]}
        self.status_calls = 0

    def capture_original_state(self):
        states = {
            "moss-web.service": {"active": True, "enabled": True},
            "moss-live-web.service": {"active": True, "enabled": True},
            "moss-vllm.service": dict(self.vllm),
        }
        return OriginalState(states, dict(self.vllm), self.runtime_statuses())

    def enable_phase1_block(self):
        self.fixture["marker"].parent.mkdir(parents=True, exist_ok=True)
        self.fixture["marker"].write_bytes(PHASE1_MARKER_BYTES)
        self.fixture["marker"].chmod(0o600)

    def disable_phase1_block(self):
        self.fixture["marker"].unlink(missing_ok=True)

    def runtime_statuses(self):
        self.status_calls += 1
        work = 1 if self.status_calls <= 2 else 0
        state = "quiesced" if self.fixture["marker"].exists() else "open"
        return (
            {"name": "batch", "state": state, "entrants": work, "active_jobs": 0, "queued_jobs": 0, "active_live_sessions": 0},
            {"name": "live", "state": state, "entrants": 0, "active_jobs": 0, "queued_jobs": 0, "active_live_sessions": 0},
        )

    def stop_phase1(self):
        self.phase1_running = False
        self.candidate_running = False

    def start_phase1(self, _original):
        self.phase1_running = True
        self.status_calls = max(self.status_calls, 2)

    def install_candidate(self, artifacts):
        home = self.fixture["home"]
        pointer = home / ".local/share/moss-transcribe-diarize/account-current"
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.unlink(missing_ok=True)
        pointer.symlink_to(artifacts.release)
        unit_dir = home / ".config/systemd/user"
        for name, source in artifacts.units.items():
            (unit_dir / name).write_bytes(source.read_bytes())
        config_dir = home / ".config/moss-transcribe-diarize"
        (config_dir / "moss-account.env").write_bytes(
            (self.fixture["staged"] / "moss-account.env").read_bytes()
        )
        (config_dir / "vllm.env").write_bytes(
            (self.fixture["staged"] / "vllm.env").read_bytes()
        )
        if self.crash:
            os._exit(23)

    def start_candidate(self, _artifacts):
        self.candidate_running = True
        state = self.fixture["state"]
        state.mkdir(parents=True, exist_ok=True)
        (state / "phase2.sqlite3").write_bytes(b"schema-v1")

    def run_qualification(self, *, artifacts, candidate_sha, attempt):
        if self.qualification_fails:
            raise RuntimeError("injected qualification failure")
        reported_sha = "0" * 40 if self.qualification_sha_mismatch else candidate_sha
        output = attempt / "qualification/evidence/phase2/wave-3/run"
        output.mkdir(parents=True)
        (output / "verdict.json").write_text(json.dumps({"schema": "moss-phase2-acceptance.v1", "wave": 3, "candidate_sha": reported_sha, "qualified": True, "g7": "UNCLAIMED"}), encoding="utf-8")
        required = ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G8", "G9", "G10"]
        (output / "gate-table.json").write_text(json.dumps({"passed": True, "required": required,
            "gates": {gate: {"passed": True, "layers": {layer: True for layer in ("deterministic", "deployed", "pre_admission")}} for gate in required}}), encoding="utf-8")
        (output / "candidate-manifest.json").write_text(json.dumps({"git_sha": reported_sha, "git_tree": self.fixture["candidate"]["git_tree"], "uv_lock_sha256": self.fixture["candidate"]["uv_lock_sha256"]}), encoding="utf-8")
        return output

    def run_attended_g7(self, *, candidate):
        self.attended_calls += 1
        if self.attended_fails:
            raise AttendedCanaryError("injected attended prerequisite absence")
        return _attended_evidence(candidate, source=self.attended_source)

    def verify_vllm_unchanged(self, original):
        return self.vllm == dict(original.vllm)

    def safe_stop(self):
        self.phase1_running = False
        self.candidate_running = False
        self.safe_stopped = True
        return True


def test_cutover_success_requires_attended_g7_before_preadmission(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = FakeCutoverOps(fixture)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=attempt,
        terminal="preadmission",
        ops=ops,
    ).run()
    assert result.terminal == "preadmission"
    assert result.g7 == "PASS" and result.admitted is False
    assert fixture["marker"].is_file()
    assert ops.phase1_running is False and ops.candidate_running is True
    rows = CutoverJournal(attempt / "journal.jsonl").read()
    assert rows[-1]["phase"] == "preadmission"
    assert rows[-1]["g7"] == "PASS"
    assert rows[-1]["admitted"] is False
    drain = next(row for row in rows if row["phase"] == "drain_observed")
    assert {row["name"] for row in drain["views"]} == {"batch", "live"}
    assert drain["work"] == 1
    assert (attempt / "snapshot-manifest.json").is_file()
    snapshot = json.loads((attempt / "snapshot-manifest.json").read_text())
    assert REQUIRED_SNAPSHOT_ROLES <= {row["role"] for row in snapshot["sources"]}
    assert stat.S_IMODE((attempt / "phase1-snapshot.tar").stat().st_mode) == 0o600
    assert json.loads((attempt / "attended-g7.json").read_text())["source"] == (
        G7_EVIDENCE_SOURCE
    )
    assert json.loads((attempt / "result.json").read_text())["schema"] == (
        "moss-phase2-cutover-result.v1"
    )
    with pytest.raises(CutoverRefused, match="terminal"):
        CutoverRun.open_incomplete(attempt=attempt, ops=ops).restore()


@pytest.mark.parametrize("outcome", ("ready", "dead", "malformed", "timeout"))
def test_http_readiness_retries_only_unavailable_live_services(monkeypatch, tmp_path, outcome):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = SystemCutoverOps(
        profile=load_cutover_profile(fixture["profile"]), artifacts=None, account_profile={}
    )
    clock = [0.0]
    observations = []
    monkeypatch.setattr(cutover.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(cutover.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(cutover, "WEB_START_TIMEOUT_SECONDS", 2)
    monkeypatch.setattr(ops, "_systemctl", lambda *args, **kwargs: subprocess.CompletedProcess(
        args, 0, "inactive" if outcome == "dead" else "active", ""
    ))

    def observe():
        observations.append(clock[0])
        if outcome == "malformed":
            raise RuntimeError("malformed")
        if outcome == "timeout" or len(observations) == 1:
            raise cutover.RuntimeViewUnavailable("not listening")

    if outcome == "ready":
        ops._wait_for_http("moss-web.service", observe)
        assert observations == [0, 1]
    else:
        with pytest.raises(RuntimeError, match={
            "dead": "stopped", "malformed": "malformed", "timeout": "timed out"
        }[outcome]) as failure:
            ops._wait_for_http("moss-web.service", observe)
        if outcome == "timeout":
            assert "not listening" in str(failure.value)
        assert len(observations) == {"dead": 0, "malformed": 1, "timeout": 3}[outcome]


def test_phase1_start_observes_both_http_views_while_creation_is_blocked(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    fake = FakeCutoverOps(fixture)
    original = fake.capture_original_state()
    fake.enable_phase1_block()
    ops = SystemCutoverOps(
        profile=load_cutover_profile(fixture["profile"]), artifacts=None, account_profile={}
    )
    monkeypatch.setattr(ops, "_systemctl", lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, "active", ""))
    observed = []
    def status(view):
        assert fixture["marker"].exists()
        observed.append(view.name)
        return {"state": "quiesced"}
    monkeypatch.setattr(ops, "_runtime_status", status)
    ops.start_phase1(original)
    assert observed == ["batch", "live"]
    assert fixture["marker"].exists()


@pytest.mark.parametrize("served_sha", ("candidate", "stale"))
def test_candidate_readiness_requires_exact_http_release(monkeypatch, tmp_path, served_sha):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = SystemCutoverOps(
        profile=load_cutover_profile(fixture["profile"]), artifacts=None,
        account_profile={"MOSS_TLS_CERTFILE": "trusted-cert"},
    )
    class Response:
        headers = {"X-MOSS-Candidate-SHA": served_sha}
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
    contexts = []
    monkeypatch.setattr(cutover.ssl, "create_default_context", lambda **kwargs: contexts.append(kwargs))
    monkeypatch.setattr(cutover.urllib.request, "urlopen", lambda *args, **kwargs: Response())
    if served_sha == "candidate":
        ops._candidate_status("candidate")
    else:
        with pytest.raises(RuntimeError, match="wrong release"):
            ops._candidate_status("candidate")
    assert contexts == [{}]


def test_qualification_finds_candidate_owned_uv_under_systemd_path(monkeypatch, tmp_path):
    from moss_transcribe_diarize import phase2_acceptance_setup as setup
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = SystemCutoverOps(
        profile=load_cutover_profile(fixture["profile"]), artifacts=None, account_profile={}
    )
    artifacts = validated_candidate_artifacts(fixture["candidate"])
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0] == "git" and argv[1] == "clone":
            Path(argv[-1]).mkdir(parents=True)
        return subprocess.CompletedProcess(argv, 0)
    monkeypatch.setattr(cutover.subprocess, "run", run)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    prepared = tmp_path / "attempt/acceptance-private/profile.json"
    setup_calls = []
    monkeypatch.setattr(setup, "prepare_acceptance_profile", lambda **kwargs: setup_calls.append(kwargs) or prepared)
    ops.run_qualification(artifacts=artifacts, candidate_sha=fixture["candidate"]["git_sha"], attempt=tmp_path / "attempt")
    assert calls[-1][1]["env"]["PATH"] == f"{artifacts.release}/bin:/usr/bin:/bin"
    scratch = Path(calls[-1][1]["env"]["MOSS_ACCEPTANCE_WORK_ROOT"])
    assert scratch.name == "measurement-workspaces" and scratch.is_dir()
    assert scratch.parent == tmp_path / "attempt"
    assert calls[-2][0] == ("npm", "--prefix", "frontend", "ci")
    assert calls[-2][1]["cwd"] == tmp_path / "attempt/qualification"
    assert calls[-2][1]["check"] is True
    assert calls[-1][0][-2:] == ("--profile", str(prepared))
    assert setup_calls == [{
        "source": fixture["acceptance_profile"], "attempt": tmp_path / "attempt",
        "candidate_sha": fixture["candidate"]["git_sha"],
    }]


def test_activation_pointer_replace_is_fsynced_before_install_returns(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    profile = load_cutover_profile(fixture["profile"])
    artifacts = validated_candidate_artifacts(fixture["candidate"])
    ops = SystemCutoverOps(profile=profile, artifacts=artifacts, account_profile={})
    monkeypatch.setattr(ops, "_systemctl", lambda *_args, **_kwargs: None)
    fsynced: list[Path] = []
    monkeypatch.setattr(cutover, "_fsync_directory", fsynced.append)

    ops.install_candidate(artifacts)

    assert ops.activation.resolve() == fixture["release"].resolve()
    assert ops.activation.parent in fsynced


def test_system_safe_stop_requires_successful_stop_inactive_units_and_closed_listeners(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = SystemCutoverOps(
        profile=load_cutover_profile(fixture["profile"]),
        artifacts=None,
        account_profile={},
    )
    stop_returncode = 0
    stop_calls: list[tuple[str, ...]] = []

    def systemctl(*args, **_kwargs):
        if args[0] == "stop":
            stop_calls.append(args)
            return subprocess.CompletedProcess(args, stop_returncode, "", "")
        if args[0] == "is-active":
            return subprocess.CompletedProcess(args, 3, "inactive\n", "")
        if args[0] == "is-enabled":
            return subprocess.CompletedProcess(args, 1, "disabled\n", "")
        return subprocess.CompletedProcess(
            args, 0, "MainPID=0\nActiveEnterTimestampMonotonic=\n", ""
        )

    listener_open = False

    class Probe:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def settimeout(self, _timeout):
            pass

        def connect_ex(self, _address):
            return 0 if listener_open else 1

    monkeypatch.setattr(ops, "_systemctl", systemctl)
    monkeypatch.setattr(cutover.socket, "socket", Probe)

    assert ops.safe_stop() is True
    assert stop_calls[-1] == (
        "stop",
        "moss-web.service",
        "moss-live-web.service",
    )
    listener_open = True
    assert ops.safe_stop() is False
    listener_open = False
    stop_returncode = 1
    assert ops.safe_stop() is False


def test_restored_tree_fsyncs_regular_files_and_directories_before_rename(
    monkeypatch, tmp_path
):
    source = tmp_path / "source"
    nested = source / "nested"
    nested.mkdir(parents=True)
    (nested / "state.bin").write_bytes(b"old durable state")
    target = tmp_path / "target"
    stage = tmp_path / ".target.moss-restore-stage"
    opened: dict[int, Path] = {}
    fsynced: list[Path] = []
    real_open = cutover.os.open
    real_fsync = cutover.os.fsync

    def observe_open(path, flags, *args):
        descriptor = real_open(path, flags, *args)
        opened[descriptor] = Path(path)
        return descriptor

    def observe_fsync(descriptor):
        if descriptor in opened:
            fsynced.append(opened[descriptor])
        return real_fsync(descriptor)

    monkeypatch.setattr(cutover.os, "open", observe_open)
    monkeypatch.setattr(cutover.os, "fsync", observe_fsync)

    cutover._copy_restored(source, target)

    assert stage / "nested/state.bin" in fsynced
    assert stage / "nested" in fsynced
    assert stage in fsynced
    assert (target / "nested/state.bin").read_bytes() == b"old durable state"


def test_restore_fsyncs_parent_after_deleting_originally_absent_activation(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(cutover.time, "sleep", lambda _: None)
    activation = (
        fixture["home"]
        / ".local/share/moss-transcribe-diarize/account-current"
    )
    fsynced: list[Path] = []
    monkeypatch.setattr(cutover, "_fsync_directory", fsynced.append)

    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=tmp_path / "attempt",
        terminal="preadmission",
        ops=FakeCutoverOps(fixture, qualification_fails=True),
    ).run()

    assert result.terminal == "restored"
    assert not activation.exists() and not activation.is_symlink()
    assert activation.parent in fsynced


def test_distinct_forward_attempts_share_one_host_cutover_lock(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    entered = threading.Event()
    release = threading.Event()
    failures: list[BaseException] = []

    class HeldOps(FakeCutoverOps):
        def capture_original_state(self):
            entered.set()
            assert release.wait(timeout=5)
            return super().capture_original_state()

    first = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=tmp_path / "first-attempt",
        terminal="restored",
        ops=HeldOps(fixture),
    )
    second = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=tmp_path / "second-attempt",
        terminal="restored",
        ops=FakeCutoverOps(fixture),
    )

    def run_first() -> None:
        try:
            first.run()
        except BaseException as exc:
            failures.append(exc)

    worker = threading.Thread(target=run_first)
    worker.start()
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(CutoverRefused, match="another cutover"):
            second.run()
    finally:
        release.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert not failures


def test_known_qualification_failure_restores_whole_old_state_and_quarantines_candidate(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    before = {str(path): (path / "state").read_bytes() for path in fixture["old_paths"]}
    ops = FakeCutoverOps(fixture, qualification_fails=True)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=attempt,
        terminal="preadmission",
        ops=ops,
    ).run()
    assert result.terminal == "restored"
    assert not fixture["marker"].exists()
    assert ops.phase1_running is True and ops.candidate_running is False
    assert {str(path): (path / "state").read_bytes() for path in fixture["old_paths"]} == before
    unit_dir = fixture["home"] / ".config/systemd/user"
    config_dir = fixture["home"] / ".config/moss-transcribe-diarize"
    assert (unit_dir / "moss-web.service").read_bytes() == b"old web\n"
    assert (unit_dir / "moss-vllm.service").read_bytes() == b"old vllm\n"
    assert (config_dir / "vllm.env").read_bytes() == b"old vllm profile\n"
    assert not (config_dir / "moss-account.env").exists()
    assert not (fixture["home"] / ".local/share/moss-transcribe-diarize/account-current").exists()
    assert (attempt / "candidate-quarantine/database").read_bytes() == b"schema-v1"
    assert CutoverJournal(attempt / "journal.jsonl").last_phase() == "restored"


def test_persistent_journal_failure_after_candidate_start_cannot_prevent_rollback(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    before = {str(path): (path / "state").read_bytes() for path in fixture["old_paths"]}
    monkeypatch.setattr(cutover.time, "sleep", lambda _: None)
    real_append = CutoverJournal.append
    journal_failed = False

    def fail_persistently_after_candidate_start(self, phase, **fields):
        nonlocal journal_failed
        if journal_failed:
            raise OSError("injected persistent journal failure")
        real_append(self, phase, **fields)
        if phase == "candidate_started":
            journal_failed = True

    monkeypatch.setattr(CutoverJournal, "append", fail_persistently_after_candidate_start)
    ops = FakeCutoverOps(fixture)

    with pytest.raises(CutoverUnsafe, match="journal"):
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=tmp_path / "attempt",
            terminal="preadmission",
            ops=ops,
        ).run()

    assert ops.phase1_running is True
    assert ops.candidate_running is False
    assert not fixture["marker"].exists()
    assert {str(path): (path / "state").read_bytes() for path in fixture["old_paths"]} == before
    assert CutoverJournal(tmp_path / "attempt/journal.jsonl").last_phase() == "candidate_started"


@pytest.mark.parametrize(
    ("attended_fails", "source"),
    ((True, G7_EVIDENCE_SOURCE), (False, "deterministic-rehearsal")),
)
def test_missing_or_synthetic_attended_g7_restores_without_preadmission(
    monkeypatch, tmp_path, attended_fails, source
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = FakeCutoverOps(
        fixture, attended_fails=attended_fails, attended_source=source
    )
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=attempt,
        terminal="preadmission",
        ops=ops,
    ).run()
    assert result.terminal == "restored" and result.g7 == "UNCLAIMED"
    assert not fixture["marker"].exists()
    assert ops.phase1_running is True and ops.candidate_running is False
    assert not (attempt / "attended-g7.json").exists()
    assert CutoverJournal(attempt / "journal.jsonl").last_phase() == "restored"


def test_attended_g7_reducer_rejects_each_load_bearing_observation(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    candidate = fixture["candidate"]
    valid = _attended_evidence(candidate)
    validate_attended_g7(valid, candidate=candidate)
    mutations = []
    for mutate in (
        lambda row: row.update(source="caller-authored"),
        lambda row: row["candidate"].update(git_sha="0" * 40),
        lambda row: row["scenarios"].pop(),
        lambda row: row["scenarios"][0]["meter_nonzero_samples"].update(system=0),
        lambda row: row["scenarios"][0].update(source_revision="0" * 40),
        lambda row: row["scenarios"][0]["frames"]["system"].update(sequence_gaps=1),
        lambda row: row["scenarios"][0].update(distinct_speakers=1),
        lambda row: row["scenarios"][0].update(meeting_status="active"),
        lambda row: row["scenarios"][0]["audio_probe"].update(codec="aac"),
    ):
        payload = json.loads(json.dumps(valid))
        mutate(payload)
        mutations.append(payload)
    for payload in mutations:
        with pytest.raises(AttendedCanaryError):
            validate_attended_g7(payload, candidate=candidate)


def test_planned_restored_terminal_runs_wave3_then_whole_restore_without_attended_g7(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = FakeCutoverOps(fixture)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=attempt,
        terminal="restored",
        ops=ops,
    ).run()
    phases = [row["phase"] for row in CutoverJournal(attempt / "journal.jsonl").read()]
    assert result.terminal == "restored" and result.error is None
    assert phases.index("qualification_started") < phases.index("planned_restore")
    assert not any(phase.startswith("attended_g7") for phase in phases)
    assert ops.attended_calls == 0
    assert not (attempt / "attended-g7.json").exists()
    assert phases[-1] == "restored"
    assert ops.phase1_running is True and ops.candidate_running is False
    assert not fixture["marker"].exists()


def test_normal_restore_preserves_every_present_explicit_phase1_root(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(cutover.time, "sleep", lambda _: None)
    explicit = {path.resolve() for path in fixture["snapshot_paths"].values()}
    removed: list[Path] = []
    copied: list[Path] = []
    real_remove = cutover._remove_path
    real_copy = cutover._copy_restored

    def observe_remove(path: Path) -> None:
        if path.resolve(strict=False) in explicit:
            removed.append(path)
        real_remove(path)

    def observe_copy(source: Path, target: Path) -> None:
        if target.resolve(strict=False) in explicit:
            copied.append(target)
        real_copy(source, target)

    monkeypatch.setattr(cutover, "_remove_path", observe_remove)
    monkeypatch.setattr(cutover, "_copy_restored", observe_copy)

    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=tmp_path / "attempt",
        terminal="restored",
        ops=FakeCutoverOps(fixture),
    ).run()

    assert result.terminal == "restored"
    assert removed == []
    assert copied == []


def test_restore_repairs_only_an_explicit_root_that_is_missing(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(cutover.time, "sleep", lambda _: None)
    model = fixture["snapshot_paths"]["phase1_model"]

    class MissingModelFailure(FakeCutoverOps):
        def run_qualification(self, **_kwargs):
            shutil.rmtree(model)
            raise RuntimeError("injected failure after model loss")

    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=tmp_path / "attempt",
        terminal="preadmission",
        ops=MissingModelFailure(fixture),
    ).run()

    assert result.terminal == "restored"
    assert (model / "state").read_bytes() == b"model"


def test_same_sha_qualification_mismatch_restores_without_preadmission(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = FakeCutoverOps(fixture, qualification_sha_mismatch=True)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    result = CutoverRun.prepare(
        profile_path=fixture["profile"],
        attempt=tmp_path / "attempt",
        terminal="preadmission",
        ops=ops,
    ).run()
    assert result.terminal == "restored" and result.error == "RuntimeError"
    assert ops.phase1_running is True and ops.candidate_running is False


@pytest.mark.parametrize("mutation", ["wave1", "missing_g8", "failed_g9", "unmeasured_layer"])
def test_release_refuses_incomplete_waves_even_when_aggregate_claims_pass(monkeypatch, tmp_path, mutation):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    class IncompleteWaves(FakeCutoverOps):
        def run_qualification(self, **kwargs):
            output = super().run_qualification(**kwargs)
            verdict_path = output / "verdict.json"
            table_path = output / "gate-table.json"
            verdict = json.loads(verdict_path.read_text())
            table = json.loads(table_path.read_text())
            if mutation == "wave1": verdict["wave"] = 1
            elif mutation == "missing_g8": del table["gates"]["G8"]
            elif mutation == "failed_g9": table["gates"]["G9"]["passed"] = False
            else: table["gates"]["G9"]["layers"]["deployed"] = False
            verdict_path.write_text(json.dumps(verdict))
            table_path.write_text(json.dumps(table))
            return output
    ops = IncompleteWaves(fixture)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    result = CutoverRun.prepare(profile_path=fixture["profile"], attempt=tmp_path / "attempt", terminal="preadmission", ops=ops).run()
    assert result.terminal == "restored"
    assert ops.phase1_running is True and ops.candidate_running is False


def test_snapshot_inventory_refuses_nested_or_missing_sources_before_effects(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    payload = json.loads(fixture["profile"].read_text())
    snapshots = payload["phase1"]["snapshot_paths"]
    vector_journal = snapshots["phase1_vector_journal"]
    snapshots["phase1_vector_journal"] = str(
        fixture["snapshot_paths"]["phase1_checkout"] / "runs"
    )
    _write_private(fixture["profile"], payload)
    with pytest.raises(CutoverRefused, match="must not overlap"):
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=tmp_path / "overlap-attempt",
            terminal="restored",
        )
    assert not fixture["marker"].exists()
    assert not (tmp_path / "overlap-attempt").exists()

    snapshots["phase1_vector_journal"] = vector_journal
    missing = Path(snapshots["phase1_auth_state"])
    missing.unlink()
    _write_private(fixture["profile"], payload)
    with pytest.raises(CutoverRefused, match="must exist"):
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=tmp_path / "missing-attempt",
            terminal="restored",
        )
    assert not (tmp_path / "missing-attempt").exists()


def test_snapshot_inventory_refuses_an_unruled_extra_role_before_effects(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    payload = json.loads(fixture["profile"].read_text())
    extra = tmp_path / "unruled-extra"
    extra.write_text("not part of the settled Phase-1 image", encoding="utf-8")
    payload["phase1"]["snapshot_paths"]["unruled_extra"] = str(extra)
    _write_private(fixture["profile"], payload)

    with pytest.raises(CutoverRefused, match="exactly the settled roles"):
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=tmp_path / "extra-role-attempt",
            terminal="restored",
        )
    assert not fixture["marker"].exists()
    assert not (tmp_path / "extra-role-attempt").exists()


def test_attempt_nested_in_candidate_state_is_refused_before_creating_parent(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    candidate_state = fixture["state"] / "file-work"
    attempt = candidate_state / "cutover-attempt"

    with pytest.raises(CutoverRefused, match="attempt overlaps candidate state"):
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=attempt,
            terminal="restored",
        )
    assert not candidate_state.exists()
    assert not fixture["marker"].exists()


def test_process_crash_restore_needs_only_attempt_owned_evidence(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    pid = os.fork()
    if pid == 0:
        ops = FakeCutoverOps(fixture, crash=True)
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=attempt,
            terminal="preadmission",
            ops=ops,
        ).run()
        os._exit(99)
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 23
    fixture["profile"].unlink()
    fixture["manifest"].unlink()
    shutil.rmtree(fixture["release"])
    shutil.rmtree(fixture["checkout"])
    shutil.rmtree(fixture["staged"])
    fixture["acceptance_profile"].unlink()
    recovery = FakeCutoverOps(fixture)
    restored = CutoverRun.open_incomplete(attempt=attempt, ops=recovery).restore()
    assert restored.terminal == "restored"
    assert not fixture["marker"].exists()


def test_restore_replays_after_process_exit_during_restore_effects(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    before = {str(path): (path / "state").read_bytes() for path in fixture["old_paths"]}
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    web_state = tmp_path / "old-web-state"
    unsafe_write = tmp_path / "snapshot-write-under-live-web"
    web_state.write_text("stopped", encoding="utf-8")
    real_copy = cutover._copy_restored

    def observe_snapshot_application(source: Path, target: Path) -> None:
        if web_state.read_text(encoding="utf-8") == "running":
            unsafe_write.write_text(str(target), encoding="utf-8")
        real_copy(source, target)

    monkeypatch.setattr(cutover, "_copy_restored", observe_snapshot_application)

    forward = os.fork()
    if forward == 0:
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=attempt,
            terminal="preadmission",
            ops=FakeCutoverOps(fixture, crash=True),
        ).run()
        os._exit(99)
    _, forward_status = os.waitpid(forward, 0)
    assert os.waitstatus_to_exitcode(forward_status) == 23

    class InstrumentedOps(FakeCutoverOps):
        def stop_phase1(self):
            super().stop_phase1()
            web_state.write_text("stopped", encoding="utf-8")

        def start_phase1(self, original):
            super().start_phase1(original)
            web_state.write_text("running", encoding="utf-8")

    class ExitDuringRestore(InstrumentedOps):
        def start_phase1(self, _original):
            super().start_phase1(_original)
            os._exit(31)

    restoring = os.fork()
    if restoring == 0:
        CutoverRun.open_incomplete(
            attempt=attempt, ops=ExitDuringRestore(fixture)
        ).restore()
        os._exit(99)
    _, restore_status = os.waitpid(restoring, 0)
    assert os.waitstatus_to_exitcode(restore_status) == 31
    assert CutoverJournal(attempt / "journal.jsonl").last_phase() not in {
        "restored",
        "preadmission",
        "SAFE_STOPPED",
    }

    result = CutoverRun.open_incomplete(
        attempt=attempt, ops=InstrumentedOps(fixture)
    ).restore()
    assert result.terminal == "restored"
    assert not unsafe_write.exists()
    assert not fixture["marker"].exists()
    assert {
        str(path): (path / "state").read_bytes() for path in fixture["old_paths"]
    } == before


def test_corrupt_archive_safe_stops(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    second = tmp_path / "attempt"
    pid = os.fork()
    if pid == 0:
        ops = FakeCutoverOps(fixture, crash=True)
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=second,
            terminal="preadmission",
            ops=ops,
        ).run()
        os._exit(99)
    os.waitpid(pid, 0)
    (second / "phase1-snapshot.tar").write_bytes(b"corrupt")
    unsafe_ops = FakeCutoverOps(fixture)
    unsafe = CutoverRun.open_incomplete(attempt=second, ops=unsafe_ops).restore()
    assert unsafe.terminal == "SAFE_STOPPED"
    assert unsafe_ops.safe_stopped is True
    assert fixture["marker"].read_bytes() == PHASE1_MARKER_BYTES


def test_safe_stopped_is_not_published_when_marker_and_listener_stop_are_unverified(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr(cutover.time, "sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    child = os.fork()
    if child == 0:
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=attempt,
            terminal="preadmission",
            ops=FakeCutoverOps(fixture, crash=True),
        ).run()
        os._exit(99)
    os.waitpid(child, 0)
    (attempt / "phase1-snapshot.tar").write_bytes(b"corrupt")
    fixture["marker"].unlink()

    class UnverifiedSafeStop(FakeCutoverOps):
        def enable_phase1_block(self):
            raise OSError("injected marker failure")

        def safe_stop(self):
            self.phase1_running = False
            self.candidate_running = False
            self.safe_stopped = True
            return False

    with pytest.raises(CutoverUnsafe, match="SAFE_STOPPED"):
        CutoverRun.open_incomplete(
            attempt=attempt, ops=UnverifiedSafeStop(fixture)
        ).restore()

    assert not fixture["marker"].exists()
    assert CutoverJournal(attempt / "journal.jsonl").last_phase() != "SAFE_STOPPED"
    assert not (attempt / "result.json").exists()


def test_malformed_journal_physically_stops_without_publishing_a_terminal(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.time.sleep", lambda _: None)
    attempt = tmp_path / "attempt"
    pid = os.fork()
    if pid == 0:
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=attempt,
            terminal="preadmission",
            ops=FakeCutoverOps(fixture, crash=True),
        ).run()
        os._exit(99)
    os.waitpid(pid, 0)
    with (attempt / "journal.jsonl").open("ab") as stream:
        stream.write(b'{"schema":')
        stream.flush()
        os.fsync(stream.fileno())
    ops = FakeCutoverOps(fixture)
    with pytest.raises(CutoverUnsafe, match="journal"):
        CutoverRun.open_incomplete(attempt=attempt, ops=ops).restore()
    assert ops.safe_stopped is True
    assert fixture["marker"].read_bytes() == PHASE1_MARKER_BYTES
    assert not (attempt / "result.json").exists()


def test_cli_has_only_new_run_and_incomplete_restore_operations():
    assert parse_args(["run", "--profile", "/p", "--attempt", "/a", "--terminal", "restored"]).terminal == "restored"
    assert parse_args(["run", "--profile", "/p", "--attempt", "/a", "--terminal", "preadmission"]).terminal == "preadmission"
    with pytest.raises(SystemExit):
        parse_args(["run", "--profile", "/p", "--attempt", "/a"])
    assert parse_args(["restore", "--attempt", "/a"]).operation == "restore"
    for forbidden in ("admit", "resume", "retry", "skip", "force"):
        with pytest.raises(SystemExit):
            parse_args([forbidden])


def test_cli_reports_planned_restore_as_success_and_failure_restore_as_failure(
    monkeypatch, capsys
):
    results = iter(
        (
            CutoverResult("restored", "/a", "a" * 40),
            CutoverResult("restored", "/b", "b" * 40, error="RuntimeError"),
        )
    )

    class Prepared:
        def run(self):
            return next(results)

    monkeypatch.setattr(
        phase2_cutover_cli.CutoverRun,
        "prepare",
        staticmethod(lambda **_kwargs: Prepared()),
    )
    arguments = [
        "run",
        "--profile",
        "/p",
        "--attempt",
        "/a",
        "--terminal",
        "restored",
    ]
    assert phase2_cutover_cli.main(arguments) == 0
    assert phase2_cutover_cli.main(arguments) == 1
    lines = capsys.readouterr().out.splitlines()
    assert json.loads(lines[0])["error"] is None
    assert json.loads(lines[1])["error"] == "RuntimeError"


def test_cutover_journal_completes_short_writes_and_rejects_sequence_damage(
    monkeypatch, tmp_path
):
    journal = CutoverJournal(tmp_path / "journal.jsonl")
    real_write = os.write

    def short_write(descriptor, payload):
        return real_write(descriptor, bytes(payload)[:3])

    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.os.write", short_write)
    journal.append("started", admitted=False)
    monkeypatch.setattr("moss_transcribe_diarize.phase2_cutover.os.write", real_write)
    assert journal.read()[0]["phase"] == "started"
    damaged = json.loads(journal.path.read_text())
    damaged["sequence"] = 2
    journal.path.write_text(json.dumps(damaged) + "\n", encoding="utf-8")
    with pytest.raises(CutoverUnsafe, match="journal"):
        journal.read()


def test_failed_phase_preserves_message_in_journal_and_result(monkeypatch, tmp_path):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = FakeCutoverOps(fixture)
    message = "candidate HTTP unavailable: certificate issuer is not trusted"
    def fail(_artifacts):
        raise RuntimeError(message)
    monkeypatch.setattr(ops, "start_candidate", fail)
    run = CutoverRun.prepare(profile_path=fixture["profile"], attempt=tmp_path / "attempt", terminal="restored", ops=ops)
    result = run.run()
    assert result.terminal == "restored"
    assert result.error == "RuntimeError"
    assert result.error_message == message
    failure = next(row for row in run.journal.read() if row["phase"] == "failure_observed")
    assert failure["error_message"] == message
    assert json.loads((run.attempt / "result.json").read_text())["error_message"] == message


@pytest.mark.parametrize("filesystem", ["root", "windows_c"])
def test_disk_refusal_precedes_phase1_mutation(monkeypatch, tmp_path, filesystem):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    ops = FakeCutoverOps(fixture)
    attempt = tmp_path / 'disk-refused'
    run = CutoverRun.prepare(profile_path=fixture['profile'], attempt=attempt,
                             terminal='preadmission', ops=ops)
    from moss_transcribe_diarize import candidate_storage
    monkeypatch.setattr(cutover, 'check_space', candidate_storage.check_space)
    monkeypatch.setattr(candidate_storage.shutil, 'disk_usage',
                        lambda path: shutil._ntuple_diskusage(100*10**9, 0, (19 if filesystem == 'root' else 20)*10**9))
    monkeypatch.setattr(candidate_storage, 'is_wsl', lambda: filesystem == 'windows_c')
    monkeypatch.setattr(candidate_storage, 'windows_free_bytes', lambda: 9*10**9)
    with pytest.raises(CutoverRefused, match='insufficient_disk_space'):
        run.run()
    assert ops.phase1_running and not ops.candidate_running
    assert not fixture['marker'].exists()
    assert not run.journal.read()


def test_preadmission_can_attend_without_remeasuring_the_candidate(tmp_path, monkeypatch):
    """The operator may attend a candidate qualified earlier; the record must say so."""

    from moss_transcribe_diarize import phase2_cutover as cutover

    calls: list[str] = []

    class Ops:
        def __getattr__(self, name):
            def record(*_args, **_kwargs):
                calls.append(name)
                return None
            return record

    run = cutover.CutoverRun.__new__(cutover.CutoverRun)
    run.requalify = False
    assert run.requalify is False
    assert "run_qualification" not in calls


def test_a_restored_run_without_qualification_is_refused(tmp_path):
    """Restored terminals exist to produce a record; skipping leaves nothing behind."""

    from moss_transcribe_diarize import phase2_cutover as cutover

    with pytest.raises(cutover.CutoverRefused, match="records nothing"):
        cutover.CutoverRun.prepare(
            profile_path=tmp_path / "absent.json",
            attempt=tmp_path / "attempt",
            terminal="restored",
            requalify=False,
        )
