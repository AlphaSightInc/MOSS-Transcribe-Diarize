"""Regression coverage for evidence citations enforced by the AFK preflight."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PREFLIGHT = REPO / "scripts" / "afk-guardrails" / "preflight.py"
HISTORICAL_REVISION = "4e8cae5"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=True)


def _write_fixture_repo(tmp_path: Path, preflight_source: str) -> Path:
    repo = tmp_path / "fixture-repo"
    guardrails = repo / "scripts" / "afk-guardrails"
    evidence = repo / "evidence" / "phase1" / "fixture"
    guardrails.mkdir(parents=True)
    evidence.mkdir(parents=True)

    (guardrails / "preflight.py").write_text(preflight_source, encoding="utf-8")
    (guardrails / "ownership.json").write_text(
        '{"fixture": {"prerequisites": [], "owns": []}}\n', encoding="utf-8"
    )
    (repo / "regenerate_evidence.py").write_text("def broken(:\n", encoding="utf-8")
    (evidence / "citations.md").write_text(
        "\n".join(
            (
                "generator: run-final-gate.sh",
                "generator: regenerate_evidence.py",
                "traceback: module.py:88",
                "external: /tmp/other-checkout/run-final-gate.sh",
            )
        )
        + "\n",
        encoding="utf-8",
    )

    _run("git", "init", "--quiet", cwd=repo)
    _run("git", "config", "user.email", "guardrail-fixture@example.invalid", cwd=repo)
    _run("git", "config", "user.name", "Guardrail Fixture", cwd=repo)
    _run("git", "add", ".", cwd=repo)
    _run("git", "commit", "--quiet", "-m", "fixture", cwd=repo)
    return repo


def _run_fixture(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (sys.executable, "scripts/afk-guardrails/preflight.py", "fixture", "--base", "HEAD"),
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def test_current_guardrail_catches_citations_missed_by_historic_repair(tmp_path: Path) -> None:
    current_repo = _write_fixture_repo(tmp_path / "current", PREFLIGHT.read_text(encoding="utf-8"))
    current = _run_fixture(current_repo)

    assert current.returncode == 1
    assert "run-final-gate.sh' which is not in the tree" in current.stderr
    assert "regenerate_evidence.py' which does not compile" in current.stderr
    assert "module.py" not in current.stderr
    assert "/tmp/other-checkout" not in current.stderr

    historic_source = _run(
        "git", "show", f"{HISTORICAL_REVISION}:scripts/afk-guardrails/preflight.py", cwd=REPO
    ).stdout
    historic_repo = _write_fixture_repo(tmp_path / "historic", historic_source)
    historic = _run_fixture(historic_repo)

    assert historic.returncode == 0


def test_current_tree_has_no_forbidden_evidence_citations() -> None:
    spec = importlib.util.spec_from_file_location("afk_preflight_under_test", PREFLIGHT)
    assert spec is not None and spec.loader is not None
    preflight = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(preflight)

    assert preflight.check_forbidden() == []
