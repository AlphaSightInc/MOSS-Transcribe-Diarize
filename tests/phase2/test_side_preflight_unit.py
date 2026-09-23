"""The configured side web unit owns load telemetry; the decoder unit stays fixed."""

import json
import subprocess
from pathlib import Path

import pytest

from moss_transcribe_diarize import phase2_acceptance_external as external
from moss_transcribe_diarize import phase2_acceptance_journal as journal


SIDE = "moss-r6-side.service"


@pytest.mark.parametrize(("web_unit", "expected_web"), [
    (SIDE, SIDE), (None, "moss-web.service"),
])
def test_capacity_load_selects_configured_web_pid_and_journal(
    tmp_path, monkeypatch, web_unit, expected_web
):
    units = []
    journals = []
    campaign = external.FixedAccountCampaign(candidate_sha="a" * 40, config={
        "repo_root": str(Path(__file__).resolve().parents[2]),
        "campaign_work_dir": str(tmp_path / "campaign"),
        "account_a_cookie_file": str(tmp_path / "a.cookie"),
        "account_b_cookie_file": str(tmp_path / "b.cookie"),
        "web_unit": web_unit,
    })

    def pid(unit):
        units.append(unit)
        return 1

    def window(unit):
        journals.append(unit)
        if len(journals) == 2:
            raise RuntimeError("telemetry boundary reached")

    monkeypatch.setattr(external, "_unit_pid", pid)
    monkeypatch.setattr(external, "_process_tree_rss", lambda _pid: 0)
    monkeypatch.setattr(campaign, "_journal_window", window)
    with pytest.raises(RuntimeError, match="telemetry boundary reached"):
        campaign._run_live_load(sessions=2, duration_seconds=0.5)
    assert units == [expected_web, "moss-vllm.service"]
    assert journals == [expected_web, "moss-vllm.service"]


def test_side_pid_requires_loaded_user_service(monkeypatch):
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        value = "loaded\n" if "LoadState" in argv else "741\n"
        return subprocess.CompletedProcess(argv, 0, value, "")

    monkeypatch.setattr(external.subprocess, "run", run)
    assert external._unit_pid(SIDE) == 741
    assert any("LoadState" in args for args in calls)
    assert all(args[:4] == ("systemctl", "--user", "show", SIDE) for args in calls)

    def missing(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, 0, "not-found\n", "")

    monkeypatch.setattr(external.subprocess, "run", missing)
    with pytest.raises(external.ExternalMeasurementError):
        external._unit_pid(SIDE)


@pytest.mark.parametrize("unit", ["moss-web.service", "moss-vllm.service"])
def test_canonical_pid_command_is_unchanged(monkeypatch, unit):
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "741\n", "")

    monkeypatch.setattr(external.subprocess, "run", run)
    assert external._unit_pid(unit) == 741
    assert calls == [("systemctl", "--user", "show", unit,
                      "--property", "MainPID", "--value")]


@pytest.mark.parametrize("unit", ["other.service", "moss-r6-side.timer", "moss-../x.service", "moss-a.service;echo"])
def test_side_pid_refuses_unrelated_or_unsafe_names_without_systemctl(monkeypatch, unit):
    monkeypatch.setattr(external.subprocess, "run", lambda *_args, **_kwargs:
                        pytest.fail("unsafe name reached systemctl"))
    with pytest.raises(external.ExternalMeasurementError):
        external._unit_pid(unit)


def test_side_journal_reads_only_proven_side_unit(monkeypatch):
    calls = []

    def run(argv, **_kwargs):
        calls.append(argv)
        row = {"__CURSOR": "side-cursor", "_SYSTEMD_USER_UNIT": SIDE, "MESSAGE": "safe"}
        return subprocess.CompletedProcess(argv, 0, json.dumps(row), "")

    monkeypatch.setattr(journal.subprocess, "run", run)
    window = journal.ServiceJournalWindow(SIDE)
    assert window.read() == b"safe"
    assert window.observation()["unit"] == SIDE
    assert all(args[3] == SIDE for args in calls)


@pytest.mark.parametrize("unit", ["other.service", "moss-r6-side.timer", "moss-../x.service"])
def test_side_journal_refuses_unsafe_name_without_journalctl(monkeypatch, unit):
    monkeypatch.setattr(journal.subprocess, "run", lambda *_args, **_kwargs:
                        pytest.fail("unsafe name reached journalctl"))
    with pytest.raises(journal.JournalMeasurementError):
        journal.ServiceJournalWindow(unit)
