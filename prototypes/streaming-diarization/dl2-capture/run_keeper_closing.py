#!/usr/bin/env python3
"""Run and seal the DL2 keeper-closing gates."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


WORKTREE = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent / "evidence" / "keeper-closing-20260809"
PYTHON = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/.venv/bin/python")


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(name: str, command: list[str], env: dict[str, str] | None = None) -> dict[str, object]:
    started = now()
    monotonic = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=WORKTREE,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    log = OUTPUT / f"{name}.txt"
    log.write_text(completed.stdout)
    return {
        "name": name,
        "command": command,
        "started_at_utc": started,
        "ended_at_utc": now(),
        "duration_seconds": round(time.monotonic() - monotonic, 3),
        "exit_code": completed.returncode,
        "log": log.name,
        "log_sha256": sha256(log),
    }


def run_in_gui_domain(
    name: str,
    command: list[str],
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Run a Launch Services gate in the logged-in GUI bootstrap, even from SSH."""
    uid = os.getuid()
    label = f"com.alphasight.moss.keeper-gate.{os.getpid()}.{time.time_ns()}"
    started = now()
    monotonic = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="moss-keeper-gui-") as temporary:
        temporary_path = Path(temporary)
        stdout_path = temporary_path / "stdout.txt"
        stderr_path = temporary_path / "stderr.txt"
        plist_path = temporary_path / f"{label}.plist"
        payload = {
            "Label": label,
            "ProgramArguments": command,
            "WorkingDirectory": str(WORKTREE),
            "RunAtLoad": True,
            "StandardOutPath": str(stdout_path),
            "StandardErrorPath": str(stderr_path),
            "EnvironmentVariables": {
                "PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                **({key: value for key, value in env.items() if key == "PYTHONDONTWRITEBYTECODE"} if env else {}),
            },
        }
        plist_path.write_bytes(plistlib.dumps(payload))
        target = f"gui/{uid}/{label}"
        bootstrap = subprocess.run(
            ["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        launch_state = ""
        exit_code = bootstrap.returncode
        if bootstrap.returncode == 0:
            deadline = time.monotonic() + 900.0
            try:
                while time.monotonic() < deadline:
                    status = subprocess.run(
                        ["launchctl", "print", target],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        check=False,
                    )
                    launch_state = status.stdout
                    last_exit = re.search(r"\blast exit code = (-?\d+)", launch_state)
                    if last_exit:
                        break
                    time.sleep(0.1)
                else:
                    exit_code = 124
                if exit_code != 124:
                    exit_code = int(last_exit.group(1)) if last_exit else 125
            finally:
                subprocess.run(
                    ["launchctl", "bootout", target],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
        stdout = stdout_path.read_text(errors="replace") if stdout_path.exists() else ""
        stderr = stderr_path.read_text(errors="replace") if stderr_path.exists() else ""
        log = OUTPUT / f"{name}.txt"
        log.write_text(
            f"execution_context=gui/{uid}\n"
            f"launch_agent_label={label}\n"
            f"bootstrap_output={bootstrap.stdout.rstrip()}\n"
            f"launch_state:\n{launch_state}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}\n"
        )
    return {
        "name": name,
        "command": command,
        "execution_context": f"gui/{uid} LaunchAgent (SSH-safe Launch Services context)",
        "started_at_utc": started,
        "ended_at_utc": now(),
        "duration_seconds": round(time.monotonic() - monotonic, 3),
        "exit_code": exit_code,
        "log": log.name,
        "log_sha256": sha256(log),
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    results = [
        run("swift-test", ["swift", "test", "--package-path", "macos/MOSSCapture"]),
        run_in_gui_domain(
            "python-pytest",
            [str(PYTHON), "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
            environment,
        ),
        run("git-diff-check", ["git", "-C", str(WORKTREE), "diff", "--check"]),
    ]
    verdict = "PASS" if all(result["exit_code"] == 0 for result in results) else "FAIL"
    summary = {
        "schema_version": 1,
        "generated_at_utc": now(),
        "worktree": str(WORKTREE),
        "base_commit": "f0c092a720cb49dde30d63ccdaece3afc3da2213",
        "verdict": verdict,
        "results": results,
    }
    summary_path = OUTPUT / "KEEPER_CLOSING.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    files = [OUTPUT / result["log"] for result in results] + [summary_path]
    seal = OUTPUT / "KEEPER_CLOSING_EVIDENCE.sha256"
    seal.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in files))
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"seal_sha256={sha256(seal)}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
