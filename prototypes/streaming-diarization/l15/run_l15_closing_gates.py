#!/usr/bin/env python3
"""Run and preserve the full Swift/Python/diff closing gates for L1.5."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
EVIDENCE = HERE / "evidence/closing"
PYTHON = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python")
BASE = "15d45afc418e2cc83e3967110553371010da1784"


def run_gate(name: str, argv: list[str], *, env: dict[str, str] | None = None) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    clock = time.monotonic()
    completed = subprocess.run(
        argv,
        cwd=REPO,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = EVIDENCE / f"gate-{name}.txt"
    output.write_text(completed.stdout, encoding="utf-8")
    return {
        "name": name,
        "argv": argv,
        "started_at": started,
        "wall_seconds": time.monotonic() - clock,
        "exit_code": completed.returncode,
        "output_path": output.relative_to(REPO).as_posix(),
        "passed": completed.returncode == 0,
        "stdout": completed.stdout,
    }


def main() -> int:
    summary_path = EVIDENCE / "closing-gates.json"
    if summary_path.exists():
        raise RuntimeError("l15_closing_gates_exist")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    syntax_failures = []
    python_files = sorted(HERE.glob("*.py"))
    for path in python_files:
        try:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            syntax_failures.append(f"{path.name}:{exc}")
    syntax_path = EVIDENCE / "gate-prototype-python-syntax.txt"
    syntax_path.write_text(
        ("PASS" if not syntax_failures else "FAIL")
        + f" files={len(python_files)}"
        + ("" if not syntax_failures else " failures=" + ";".join(syntax_failures))
        + "\n"
    )
    swift = run_gate(
        "swift",
        ["swift", "test", "--package-path", "macos/MOSSCapture"],
    )
    python_env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    pytest = run_gate(
        "pytest",
        [str(PYTHON), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
        env=python_env,
    )
    diff_committed = run_gate(
        "diff-committed",
        ["git", "-C", str(REPO), "diff", "--check", f"{BASE}..HEAD"],
    )
    diff_worktree = run_gate(
        "diff-worktree",
        ["git", "-C", str(REPO), "diff", "--check"],
    )
    swift_counts = [int(value) for value in re.findall(r"Executed (\d+) tests?", swift["stdout"])]
    pytest_summary = next(
        (line for line in reversed(pytest["stdout"].splitlines()) if " passed" in line),
        "",
    )
    results = [swift, pytest, diff_committed, diff_worktree]
    summary = {
        "schema": "moss-l15-closing-gates.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prototype_python_syntax": {
            "file_count": len(python_files),
            "failures": syntax_failures,
            "output_path": syntax_path.relative_to(REPO).as_posix(),
            "passed": not syntax_failures,
        },
        "gates": [
            {key: value for key, value in result.items() if key != "stdout"}
            for result in results
        ],
        "count_reconciliation": {
            "swift_executed_counts": swift_counts,
            "swift_max_executed_tests": max(swift_counts, default=0),
            "swift_testing_zero_suite_line_benign": "0 tests in 0 suites" in swift["stdout"],
            "pytest_summary_line": pytest_summary,
        },
        "overall": "PASS" if not syntax_failures and all(result["passed"] for result in results) else "FAIL",
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
