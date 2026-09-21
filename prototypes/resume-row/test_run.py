from __future__ import annotations

import json
import runpy
import socket
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "prototypes/resume-row/run.py"


def load_runner() -> dict:
    return runpy.run_path(str(RUNNER))


def test_plan_counts_every_decoder_request_and_stays_bounded() -> None:
    plan = load_runner()["request_plan"]("freeze-sha")
    assert plan["population"]["n"] == 3
    assert plan["population"]["k"] == 1
    assert plan["requests"] == {
        "uninterrupted_reference": 3,
        "before_sigkill": 1,
        "after_restart": 2,
        "planned_decoder": 6,
        "cap": 12,
    }
    assert plan["brief_arithmetic"]["status"] == "UNDERCOUNTS_PRE_SIGKILL_K"


def test_missing_evidence_and_upstream_errors_are_incomplete() -> None:
    status = load_runner()["row_status"]
    assert status({"all": True}) == "PASS"
    assert status({"all": False}) == "INCOMPLETE"
    assert status({"all": True}, upstream_error=True) == "INCOMPLETE"


def test_plan_only_opens_no_socket_or_subprocess(monkeypatch, tmp_path: Path) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("plan-only attempted dispatch")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    namespace = load_runner()
    output = tmp_path / "plan.json"
    assert namespace["main"]([
        "--plan-only", "--frozen-sha", "freeze-sha", "--out", str(output)
    ]) == 0
    assert json.loads(output.read_text())["actual_calls"] == {"decoder": 0, "provider": 0}


def test_fake_dry_run_exercises_sigkill_and_restart(tmp_path: Path) -> None:
    output = tmp_path / "fake"
    completed = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--fake-dry-run",
            "--frozen-sha",
            "freeze-sha",
            "--out",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads((output / "receipt.json").read_text())
    assert receipt["status"] == "PASS"
    assert receipt["checks"] == {
        "checkpoint_observed": True,
        "sigkill_observed": True,
        "restart_completed": True,
        "owner_reclaimed": True,
        "phase_counts_exact": True,
    }
