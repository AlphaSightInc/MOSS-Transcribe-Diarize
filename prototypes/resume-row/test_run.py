from __future__ import annotations

import json
import runpy
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


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


def _events(statuses: list[int], *, client_ids: bool = True) -> list[dict]:
    events = []
    for index, status in enumerate(statuses, start=1):
        common = {
            "row": "f3r-resume",
            "attempt_id": f"attempt-{index}",
        }
        if client_ids:
            common["client_request_id"] = f"client-{index}"
        events.append({"kind": "start", "active": 1, **common})
        events.append({
            "kind": "end" if 200 <= status < 300 else "upstream_failed",
            "active": 0,
            "upstream_status": status,
            **common,
        })
    return events


def test_all_2xx_proxy_attempts_reconcile_and_can_pass() -> None:
    namespace = load_runner()
    summary, incomplete = namespace["decoder_accounting"](
        _events([200, 201]), planned_requests=2
    )
    assert summary.reconciled is True
    assert incomplete is False
    assert namespace["row_status"](
        {"product": True}, accounting_is_incomplete=incomplete
    ) == "PASS"


def test_503_after_restart_is_incomplete() -> None:
    namespace = load_runner()
    summary, incomplete = namespace["decoder_accounting"](
        _events([200, 503]), planned_requests=2
    )
    assert summary.upstream_failed == 1
    assert incomplete is True
    assert namespace["row_status"](
        {"product": True}, accounting_is_incomplete=incomplete
    ) == "INCOMPLETE"


def test_missing_client_request_ids_alone_are_not_incomplete() -> None:
    namespace = load_runner()
    summary, incomplete = namespace["decoder_accounting"](
        _events([200, 200], client_ids=False), planned_requests=2
    )
    assert summary.missing_client_request_ids == 2
    assert summary.reconciled is True
    assert incomplete is False


def test_unowned_duplicate_and_unreconciled_attempts_are_incomplete() -> None:
    namespace = load_runner()
    accounting = namespace["decoder_accounting"]
    unowned = _events([200])
    for event in unowned:
        event["row"] = None
    duplicate = _events([200, 200])
    duplicate[2]["client_request_id"] = duplicate[0]["client_request_id"]
    duplicate[3]["client_request_id"] = duplicate[0]["client_request_id"]
    unreconciled = _events([200])[:1]
    assert accounting(unowned, planned_requests=1)[1] is True
    assert accounting(duplicate, planned_requests=2)[1] is True
    assert accounting(unreconciled, planned_requests=1)[1] is True


def test_wait_prefix_uses_its_completed_baseline(tmp_path: Path) -> None:
    owner = tmp_path / "owner"
    windows = owner / "checkpoint/windows"
    windows.mkdir(parents=True)
    (windows / "w000000.json").write_text("{}\n", encoding="utf-8")
    proxy = SimpleNamespace(
        snapshot=lambda: SimpleNamespace(accepted=11, completed=8, active=0)
    )
    result = load_runner()["_wait_prefix"](
        owner,
        proxy,
        accepted_before=10,
        completed_before=7,
        k=1,
        timeout=0.05,
    )
    assert result == {"checkpoint_records": 1, "accepted": 1, "completed": 1}


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
