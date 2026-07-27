from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from live_integration_replay import LocalIntegrationReplay


# Resolved independently of the replay module so a mocked or relocated product
# cannot satisfy the executable-path assertion by agreeing with itself.
SHOW_BIN_PATH_ARGV = tuple("swift build --show-bin-path".split())
SWIFT_PACKAGE_PATH = "macos/MOSSCapture"
MTD_CAPTURE_PRODUCT = "mtd-capture"


def _target_root() -> Path:
    return Path(os.environ.get("MOSS_TARGET_REPO", Path(__file__).resolve().parents[1]))


def _expected_mtd_capture_executable() -> Path:
    argv = (*SHOW_BIN_PATH_ARGV, "--package-path", str(_target_root() / SWIFT_PACKAGE_PATH))
    completed = subprocess.run(argv, check=False, capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, f"`{' '.join(argv)}` failed: {completed.stderr}"
    return Path(completed.stdout.strip()) / MTD_CAPTURE_PRODUCT


@pytest.fixture(scope="module")
def report():
    """One immutable coordination report shared by every scenario node below."""
    with tempfile.TemporaryDirectory() as tmpdir:
        return LocalIntegrationReplay(tmpdir=tmpdir).run()


@pytest.fixture(scope="module")
def cli_probes(report):
    return {probe.action: probe for probe in report.cli_probes}


def test_start_view_transcript_and_health_are_one_coordinated_scenario(report):
    assert report.session_created is True
    assert report.transcript_lines
    assert report.view_snapshot_status == "active"
    assert report.helper_state == "capturing"
    assert report.helper_sequence == 2
    assert {
        lane.lane: (lane.state, lane.failure_code)
        for lane in report.helper_lanes
    }["microphone"] == ("failed", "permission_denied")
    lanes = {lane.lane: lane for lane in report.lanes}
    assert lanes["system"].health == "active"
    assert lanes["system"].next_sequence == 2
    assert {
        (exchange.action, exchange.status_code)
        for exchange in report.exchanges
    } >= {
        ("heartbeat:capture", 200),
        ("view:snapshot:transcript", 200),
        ("view:events", 200),
        ("view:snapshot:failed-lane", 200),
    }


def test_reconnect_replay_typed_failure_and_final_terminal_state(report):
    assert report.exact_duplicate_ack == report.changed_payload_duplicate_ack
    assert report.replay_counter_unchanged is True
    assert report.system_continuation_ack.lane == "system"
    assert report.system_continuation_ack.sequence == 2
    lanes = {lane.lane: lane for lane in report.lanes}
    assert lanes["microphone"].health == "failed"
    assert lanes["microphone"].failure_code == "permission_denied"
    assert lanes["microphone"].failed_samples > 0
    assert [event.seq for event in report.events] == sorted({event.seq for event in report.events})
    assert report.stop_deadline == 5.0
    assert report.stop_status_code == 409
    assert report.terminal_v2_status == "failed"
    assert report.terminal_reason == "permission_denied"
    assert ("view:stop", 409) in {
        (exchange.action, exchange.status_code) for exchange in report.exchanges
    }


def test_built_mtd_capture_executable_is_resolved_from_the_package_bin_path(cli_probes):
    expected = _expected_mtd_capture_executable()

    assert expected.exists()
    assert os.access(expected, os.X_OK)
    assert expected.name == MTD_CAPTURE_PRODUCT
    for probe in cli_probes.values():
        assert Path(probe.executable) == expected

    usage = subprocess.run(
        (str(expected),),
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )

    assert usage.returncode == 64
    assert usage.stdout == ""
    assert "usage: mtd-capture" in usage.stderr


def test_built_cli_usage_and_missing_app_socket_probes_stay_silent_about_authority(cli_probes):
    assert cli_probes["cli:usage"].return_code == 64
    assert "usage: mtd-capture" in cli_probes["cli:usage"].stderr
    assert cli_probes["cli:usage"].stdout == ""
    assert cli_probes["cli:missing-app-socket-status"].return_code == 70
    assert cli_probes["cli:missing-app-socket-status"].stdout == ""
    assert cli_probes["cli:missing-app-socket-status"].stderr == "{\"ok\":false}\n"
    combined_cli_output = "".join(
        probe.stdout + probe.stderr for probe in cli_probes.values()
    )
    for secret_marker in ("capture-bearer", "certificate-pin", "pairing-secret"):
        assert secret_marker not in combined_cli_output


def test_local_integration_replay_report_is_redacted_and_immutable(report):
    assert report.authority_redaction_checked is True
    with pytest.raises(FrozenInstanceError):
        report.stop_deadline = 0.0
