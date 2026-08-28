from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import stat
from pathlib import Path

import pytest

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
)
from moss_transcribe_diarize.phase2_g7_canary import (
    AttendedCanaryError,
    G7_EVIDENCE_SCHEMA,
    G7_EVIDENCE_SOURCE,
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
        "origin": "https://moss.example",
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

    def stop_candidate(self):
        self.candidate_running = False

    def run_qualification(self, *, artifacts, candidate_sha, attempt):
        if self.qualification_fails:
            raise RuntimeError("injected qualification failure")
        reported_sha = "0" * 40 if self.qualification_sha_mismatch else candidate_sha
        output = attempt / "qualification/evidence/phase2/wave-1/run"
        output.mkdir(parents=True)
        (output / "verdict.json").write_text(json.dumps({"schema": "moss-phase2-acceptance.v1", "wave": 1, "candidate_sha": reported_sha, "qualified": True, "g7": "UNCLAIMED"}), encoding="utf-8")
        (output / "gate-table.json").write_text(json.dumps({"passed": True, "required": ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G10"]}), encoding="utf-8")
        (output / "candidate-manifest.json").write_text(json.dumps({"git_sha": reported_sha, "git_tree": self.fixture["candidate"]["git_tree"], "uv_lock_sha256": self.fixture["candidate"]["uv_lock_sha256"]}), encoding="utf-8")
        return output

    def run_attended_g7(self, *, candidate):
        if self.attended_fails:
            raise AttendedCanaryError("injected attended prerequisite absence")
        return _attended_evidence(candidate, source=self.attended_source)

    def verify_vllm_unchanged(self, original):
        return self.vllm == dict(original.vllm)

    def safe_stop(self):
        self.phase1_running = False
        self.candidate_running = False
        self.safe_stopped = True


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


def test_planned_restored_terminal_runs_canary_then_whole_restore(monkeypatch, tmp_path):
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
    assert phases[-1] == "restored"
    assert ops.phase1_running is True and ops.candidate_running is False
    assert not fixture["marker"].exists()


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


def test_snapshot_inventory_refuses_nested_or_missing_sources_before_effects(
    monkeypatch, tmp_path
):
    fixture = _cutover_fixture(monkeypatch, tmp_path)
    payload = json.loads(fixture["profile"].read_text())
    snapshots = payload["phase1"]["snapshot_paths"]
    snapshots["nested_runs"] = str(fixture["snapshot_paths"]["phase1_checkout"] / "runs")
    _write_private(fixture["profile"], payload)
    with pytest.raises(CutoverRefused, match="must not overlap"):
        CutoverRun.prepare(
            profile_path=fixture["profile"],
            attempt=tmp_path / "overlap-attempt",
            terminal="restored",
        )
    assert not fixture["marker"].exists()
    assert not (tmp_path / "overlap-attempt").exists()

    snapshots.pop("nested_runs")
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


def test_partial_journal_tail_safe_stops_incomplete_attempt(monkeypatch, tmp_path):
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
    result = CutoverRun.open_incomplete(attempt=attempt, ops=ops).restore()
    assert result.terminal == "SAFE_STOPPED"
    assert ops.safe_stopped is True
    assert fixture["marker"].read_bytes() == PHASE1_MARKER_BYTES
    assert json.loads((attempt / "result.json").read_text())["terminal"] == "SAFE_STOPPED"


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
