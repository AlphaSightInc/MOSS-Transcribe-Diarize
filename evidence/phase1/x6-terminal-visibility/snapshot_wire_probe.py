#!/usr/bin/env python3
"""Print the literal `/snapshot` body a polling viewer receives after its session dies.

This is a wire probe, not a unit test: it drives a real FastAPI app over the real live
routes, kills the session the way a provider kills one, and dumps the JSON body verbatim --
fetched with the cursor the viewer is actually holding at that moment, which is the whole
point. `since_version=0` proves nothing, because 0 is below every version a session that has
accepted a frame ever had, so the version gate can never suppress it.

    .venv/bin/python evidence/phase1/x6-terminal-visibility/snapshot_wire_probe.py
    .venv/bin/python evidence/phase1/x6-terminal-visibility/snapshot_wire_probe.py --baseline

`--baseline` runs the identical scenario against the product files as they stand on `dev`,
so the before/after is two runs of one probe rather than a remembered claim. It never writes
to the working tree: it copies the package into a temp dir, overwrites the two files this
ticket owns with `git show dev:<path>`, and runs there.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
OWNED = (
    "moss_transcribe_diarize/app/live_service_runtime.py",
    "moss_transcribe_diarize/app/live_portal.py",
)
# The scenario builds its session out of the live-API test helpers, so the baseline has to
# stage dev's copy of those too: this branch's copy imports names dev's runtime does not
# export, and importing it would fail before the scenario ever ran.
BASELINE_HELPERS = ("tests/test_live_api.py",)


def scenario(staged: str | None = None) -> dict:
    """Create a session, catch a viewer up, kill it, and poll once more."""
    import tempfile as _tempfile

    sys.path.insert(0, str(Path(staged) / "tests") if staged else str(REPO / "tests"))
    from test_live_api import LiveApiTest, frame_payload, make_live_runtime
    from moss_transcribe_diarize.app.server import create_app

    class _Harness(LiveApiTest):
        def runTest(self):  # pragma: no cover - harness only
            pass

    harness = _Harness()
    with _tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(
            model_path="fake-model",
            runs_dir=tmpdir,
            live_enabled=True,
            live_runtime_factory=lambda: make_live_runtime(max_retained_samples=4),
            **harness._live_auth_kwargs(tmpdir),
        )
        client = harness._paired_client(app)
        session_id = client.post("/api/live/sessions").json()["id"]

        client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(0, 2))
        client.post(f"/api/live/sessions/{session_id}/frames", json=frame_payload(1, 2))

        # The viewer catches up and records the cursor it will keep polling with.
        caught_up = client.get(
            f"/api/live/sessions/{session_id}/snapshot?since_version=0"
        ).json()
        cursor = caught_up["snapshot"]["session"]["version"]

        refused = client.post(
            f"/api/live/sessions/{session_id}/frames", json=frame_payload(2, 1)
        )

        polls = [
            client.get(
                f"/api/live/sessions/{session_id}/snapshot?since_version={cursor}"
            ).json()
            for _ in range(3)
        ]
        return {
            "healthy_snapshot_status": caught_up["snapshot"]["session"]["status"],
            "viewer_cursor": cursor,
            "frame_after_death_status_code": refused.status_code,
            "polls_after_death": polls,
        }


def run_baseline() -> dict:
    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging)
        shutil.copytree(REPO / "moss_transcribe_diarize", stage / "moss_transcribe_diarize")
        (stage / "tests").mkdir()
        for rel in (*OWNED, *BASELINE_HELPERS):
            source = subprocess.run(
                ["git", "show", f"dev:{rel}"],
                cwd=REPO, capture_output=True, text=True, check=True,
            ).stdout
            (stage / rel).write_text(source, encoding="utf-8")
        done = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--emit-json", "--staged", str(stage)],
            cwd=REPO,
            env={"PYTHONPATH": f"{stage}:{REPO}", "PATH": "/usr/bin:/bin"},
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            raise SystemExit(done.stderr)
        return json.loads(done.stdout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline", action="store_true", help="run against dev's product files")
    parser.add_argument("--emit-json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--staged", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args.emit_json:
        print(json.dumps(scenario(args.staged)))
        return 0

    if args.baseline:
        result = run_baseline()
        label = "BEFORE -- product files as they stand on dev"
    else:
        result = scenario()
        label = "AFTER -- product files as they stand on this branch"

    print(label)
    print(f"the viewer's cursor when the session died: since_version={result['viewer_cursor']}")
    print(f"the session was healthy at that cursor:    status={result['healthy_snapshot_status']!r}")
    print(f"the frame that killed it was answered:     HTTP {result['frame_after_death_status_code']}")
    print()
    for index, body in enumerate(result["polls_after_death"], start=1):
        print(f"--- poll {index} after the session died, GET /snapshot?since_version="
              f"{result['viewer_cursor']} ---")
        print(json.dumps(body, indent=2, sort_keys=True))
        print()
    statuses = [
        None if body.get("snapshot") is None else body["snapshot"]["session"]["status"]
        for body in result["polls_after_death"]
    ]
    print(f"session.status the viewer could read on each poll: {statuses}")
    print(
        "a viewer that stops on session.status stops here"
        if statuses[0] in {"closed", "aborted", "failed"}
        else "a viewer that stops on session.status NEVER STOPS -- it polls a dead session forever"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
