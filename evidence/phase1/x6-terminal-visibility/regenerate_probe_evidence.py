#!/usr/bin/env python3
"""Regenerate every artifact under `evidence/phase1/x6-terminal-visibility/`.

The artifacts this writes are raw command output and nothing else. There is no hand-edited
evidence in this directory: re-run this script and the files are rebuilt from the tree as it
stands. Three artifacts were quarantined on this repo for citing probes that no longer
existed, so the probe list below is the artifact's contract -- if a node id here has been
renamed or deleted, this script fails loudly instead of writing a stale record.

    .venv/bin/python evidence/phase1/x6-terminal-visibility/regenerate_probe_evidence.py

The shared `.venv` is an editable install of the *primary* checkout, so PYTHONPATH is set to
the repository this script lives in; without it a worktree validates the wrong source tree.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
# The repo's own .venv is the gate. `X6_PYTEST` exists because that venv lives on a volume
# that intermittently refuses access on this machine; the interpreter actually used is
# recorded in every artifact, so a run on a substitute environment says so rather than
# passing itself off as the gate.
PYTEST = shlex.split(os.environ.get("X6_PYTEST", "")) or [str(REPO / ".venv" / "bin" / "pytest")]

# What each artifact is meant to prove, and the committed probes that prove it.
ARTIFACTS: dict[str, tuple[str, tuple[str, ...]]] = {
    "terminal-visibility-from-one-snapshot-read.txt": (
        "A terminally-failed session is discoverable from a single /snapshot read by the\n"
        "reader that actually polls it -- one holding the version cursor it last rendered,\n"
        "not the since_version=0 that the version gate can never suppress. Also: a healthy\n"
        "session still answers `unchanged`, and a meeting that closed cleanly is not\n"
        "relabelled `failed` by a teardown that lands after it.",
        (
            "tests/test_live_api.py::LiveApiTest::test_a_polling_viewer_learns_a_session_died_from_one_snapshot_read",
            "tests/test_live_service_runtime.py::test_a_terminal_failure_reaches_a_reader_that_already_holds_the_current_version",
            "tests/test_live_service_runtime.py::test_a_healthy_session_still_answers_unchanged_to_a_caught_up_reader",
            "tests/test_live_service_runtime.py::test_a_terminal_failure_does_not_relabel_a_session_that_already_ended",
            "tests/test_live_api.py::LiveApiTest::test_failed_stop_revokes_the_view_without_stranding_capture_authority",
        ),
    ),
    "a-released-view-stops-the-portal.txt": (
        "The other half of the outage, and the half no snapshot contract can reach: a\n"
        "view-token reader's grant is released the moment its session stops being viewable,\n"
        "so it is answered 401 on /snapshot and /events and never receives the terminal body\n"
        "at all. The probe asserts that premise as well as the fix -- the portal stops on a\n"
        "released view instead of retrying it on a capped backoff forever.",
        (
            "tests/test_live_portal.py::LivePortalRouteTest::test_a_viewer_whose_grant_the_server_released_stops_instead_of_reconnecting_forever",
            "tests/test_live_api.py::LiveApiTest::test_failed_stop_revokes_the_view_without_stranding_capture_authority",
        ),
    ),
    "portal-renders-seq-zero-exactly-once.txt": (
        "The portal renders sequence 0 (`session_created`) exactly once and stops polling on\n"
        "a served terminal snapshot. The bodies replayed through the portal script are\n"
        "captured off real routes, not hand-written, and the probe asserts the portal asked\n"
        "for the same cursors the capture used. Also: the portal's terminal set is bound to\n"
        "the server's published one rather than repeating it as a literal.",
        (
            "tests/test_live_portal.py::LivePortalRouteTest::test_the_portal_renders_seq_zero_once_and_stops_on_a_served_terminal_snapshot",
            "tests/test_live_portal.py::LivePortalRouteTest::test_the_portal_stops_on_exactly_the_statuses_the_server_calls_terminal",
            "tests/test_live_portal.py::LivePortalRouteTest::test_live_portal_browser_contract_polls_renders_controls_and_stops",
            "tests/test_live_service_runtime.py::test_events_accepts_the_cursor_before_the_first_event_and_refuses_anything_lower",
        ),
    ),
    "gate-suite.txt": (
        "The ticket's gate, run whole.",
        (
            "tests/test_live_service_runtime.py",
            "tests/test_live_api.py",
            "tests/test_live_portal.py",
        ),
    ),
}


def run(argv: list[str]) -> subprocess.CompletedProcess:
    env = dict(os.environ, PYTHONPATH=os.environ.get("PYTHONPATH") or str(REPO))
    return subprocess.run(argv, cwd=REPO, env=env, capture_output=True, text=True)


def main() -> int:
    if not Path(PYTEST[0]).exists():
        print(f"missing {PYTEST[0]}", file=sys.stderr)
        return 2

    collected = run(
        [
            *PYTEST,
            "--collect-only",
            "-q",
            "tests/test_live_service_runtime.py",
            "tests/test_live_api.py",
            "tests/test_live_portal.py",
        ]
    )
    known = {line.strip() for line in collected.stdout.splitlines() if "::" in line}

    failures = 0
    for name, (claim, probes) in ARTIFACTS.items():
        missing = [
            probe
            for probe in probes
            if "::" in probe and probe not in known and not any(line.startswith(probe) for line in known)
        ]
        if missing:
            print(f"{name}: cited probe(s) not collectable: {missing}", file=sys.stderr)
            return 2

        argv = [*PYTEST, "-v" if "::" in probes[0] else "-q", *probes]
        completed = run(argv)
        body = [
            f"x6-terminal-visibility -- {name}",
            "",
            "What this proves:",
            *(f"  {line}" for line in claim.splitlines()),
            "",
            "Committed, re-runnable probes:",
            *(f"  {probe}" for probe in probes),
            "",
            "Regenerate with:",
            "  .venv/bin/python evidence/phase1/x6-terminal-visibility/regenerate_probe_evidence.py",
            "",
            f"Interpreter: {PYTEST[0]}"
            + ("" if "X6_PYTEST" not in os.environ else "   (X6_PYTEST override -- NOT the repo's .venv)"),
            "",
            "$ PYTHONPATH=\"$PWD\" " + " ".join(argv).replace(str(REPO) + "/", ""),
            completed.stdout.rstrip(),
        ]
        if completed.stderr.strip():
            body += ["", "--- stderr ---", completed.stderr.rstrip()]
        body += ["", f"exit status: {completed.returncode}", ""]
        (OUT / name).write_text("\n".join(body), encoding="utf-8")
        print(f"wrote {name} (exit {completed.returncode})")
        failures += completed.returncode != 0

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
