#!/usr/bin/env python3
"""Name the 409 that ends a live meeting after one capture-lane overrun.

Candidate 54 in `scripts/ralph-afk/context.md` records this as *undetermined*: F3's soak died
because `POST /frames` started answering 409 one second after the Mac's `system` lane reported
`macos_buffer_overrun`, and neither host records the sub-reason - the access log prints only the
status code and the Swift client discards the body by G3's contract. The guess on record was
`LiveV2OutOfOrderFrameError` (a skipped per-lane wire sequence).

This probe answers the question offline, deterministically, against the *real* server modules -
the same `create_app` the deployed unit runs - by reproducing the exact sequence F3 observed:

    healthy frame -> heartbeat reporting ONE lane failed -> the next frame on THAT lane

and by reproducing the rival hypothesis (a real sequence gap) beside it, so the two answers are
compared rather than argued. It starts no server, opens no socket, touches no deployed state and
needs neither GPU nor network: `fastapi.testclient` drives the ASGI app in-process.

rc=0  the run completed and every recorded expectation held
rc=3  an expectation failed - the recorded diagnosis is wrong and context.md must be corrected
rc=2  the probe could not run (missing fastapi, import failure)

Usage:  python3 scripts/ralph-afk/live-lane-refusal-probe.py [--json <path>]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_helpers():
    """Import the tracked API-test helpers as a library.

    They are the canonical payload builders for this wire contract, so restating them here would
    let the probe drift away from the shapes the suite already asserts.
    """
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    # `tests/` is not a package, so load the module by file path rather than by import name.
    spec = importlib.util.spec_from_file_location(
        "ralph_live_api_helpers", REPO_ROOT / "tests" / "test_live_api.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load tests/test_live_api.py")
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    return api


def _pair(app, api) -> Any:
    """Reproduce the suite's two-step pairing and return an authorized client."""
    from fastapi.testclient import TestClient

    local = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    lan = TestClient(app, base_url="https://moss.lan", client=("192.168.68.20", 50001))
    issued = local.post("/api/live/pairing-codes")
    if issued.status_code != 200:
        raise RuntimeError(f"pairing-codes returned {issued.status_code}")
    paired = lan.post(
        "/api/live/pairings",
        json={"device_id": "ralph-lane-refusal-probe", "pairing_payload": issued.json()["pairing_payload"]},
    )
    if paired.status_code != 200:
        raise RuntimeError(f"pairings returned {paired.status_code}")
    return api.AuthorizedLiveClient(app, paired.json()["device_token"])


def _make_app(api, tmpdir: str):
    from moss_transcribe_diarize.app.server import create_app

    return create_app(
        model_path="fake-model",
        runs_dir=tmpdir,
        live_enabled=True,
        live_runtime_factory=lambda: api.make_live_runtime(max_retained_samples=8),
        live_auth_state_path=Path(tmpdir) / "live-auth.json",
        live_server_cert_sha256=api.LIVE_AUTH_FINGERPRINT,
        live_helper_lease_seconds=30.0,
    )


def _record(response) -> dict[str, Any]:
    try:
        body = response.json()
    except Exception:  # noqa: BLE001 - a non-JSON body is itself the evidence
        body = {"_raw": response.text[:400]}
    failure = body.get("failure") if isinstance(body, dict) else None
    return {
        "status": response.status_code,
        "detail": body.get("detail") if isinstance(body, dict) else None,
        "failure_code": failure.get("code") if isinstance(failure, dict) else None,
        "body_keys": sorted(body) if isinstance(body, dict) else None,
    }


def scenario_overrun(api) -> dict[str, Any]:
    """F3's sequence: one lane reports failed on a heartbeat, then publishes again."""
    steps: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        app = _make_app(api, tmpdir)
        client = _pair(app, api)
        session_id = client.post("/api/live/sessions").json()["id"]
        frames = f"/api/live/sessions/{session_id}/frames"
        beats = f"/api/live/sessions/{session_id}/heartbeat"

        steps["healthy_system_frame"] = _record(
            client.post(frames, json=api.v2_frame_payload(0, 2, lane="system"))
        )
        steps["healthy_heartbeat"] = _record(client.post(beats, json=api.helper_heartbeat_payload()))

        # The Mac's `system` lane overruns; K1's projection carries that into the next heartbeat.
        steps["heartbeat_reporting_failed_lane"] = _record(
            client.post(
                beats,
                json=api.helper_heartbeat_payload(
                    sequence=1,
                    sent_monotonic_ns=20,
                    failed_lane="system",
                    failure_code="macos_buffer_overrun",
                ),
            )
        )
        lanes = app.state.live_v2_sessions.get(session_id).snapshot().to_dict()["lanes"]
        steps["v2_lane_state"] = {
            "system": {k: lanes["system"][k] for k in ("health", "failure_code", "failed_samples")},
            "microphone": {k: lanes["microphone"][k] for k in ("health", "failure_code", "failed_samples")},
        }

        # The pump's very next publish turn, on the lane that failed.
        refused = api.v2_frame_payload(1, 2, lane="system")
        steps["next_frame_on_failed_lane"] = _record(client.post(frames, json=refused))
        # The outbox retains an unacknowledged frame and retries the identical bytes forever.
        steps["identical_retry"] = _record(client.post(frames, json=refused))
        steps["retry_again"] = _record(client.post(frames, json=refused))
        # The surviving lane is untouched: the meeting could have continued on one lane.
        steps["peer_lane_frame"] = _record(
            client.post(frames, json=api.v2_frame_payload(0, 2, lane="microphone"))
        )
        # And the lease would have held if the tick had emitted health despite the failed publish.
        steps["heartbeat_after_refusal"] = _record(
            client.post(
                beats,
                json=api.helper_heartbeat_payload(
                    sequence=2,
                    sent_monotonic_ns=30,
                    failed_lane="system",
                    failure_code="macos_buffer_overrun",
                ),
            )
        )
        steps["session_still_registered"] = session_id in app.state.live_v2_sessions
    return steps


def scenario_sequence_gap(api) -> dict[str, Any]:
    """The rival hypothesis: a genuinely skipped per-lane wire sequence."""
    steps: dict[str, Any] = {}
    with tempfile.TemporaryDirectory() as tmpdir:
        app = _make_app(api, tmpdir)
        client = _pair(app, api)
        session_id = client.post("/api/live/sessions").json()["id"]
        frames = f"/api/live/sessions/{session_id}/frames"

        steps["first_frame"] = _record(client.post(frames, json=api.v2_frame_payload(0, 2, lane="system")))
        steps["skipped_sequence"] = _record(
            client.post(frames, json=api.v2_frame_payload(2, 2, lane="system"))
        )
        # A gap is recoverable: the awaited sequence is still accepted afterwards.
        steps["awaited_sequence"] = _record(
            client.post(frames, json=api.v2_frame_payload(1, 2, lane="system"))
        )
    return steps


EXPECTATIONS: tuple[tuple[str, str, Any], ...] = (
    # (scenario, dotted path, expected value)
    ("overrun", "healthy_system_frame.status", 200),
    ("overrun", "healthy_heartbeat.status", 200),
    # One failed lane is NOT terminal: the heartbeat is observed, not refused.
    ("overrun", "heartbeat_reporting_failed_lane.status", 200),
    ("overrun", "v2_lane_state.system.health", "failed"),
    ("overrun", "v2_lane_state.system.failure_code", "macos_buffer_overrun"),
    ("overrun", "v2_lane_state.microphone.health", "active"),
    # The answer candidate 54 asks for.
    ("overrun", "next_frame_on_failed_lane.status", 409),
    ("overrun", "next_frame_on_failed_lane.detail", "v2 system lane is failed."),
    ("overrun", "next_frame_on_failed_lane.failure_code", None),
    # Permanent: retrying the identical frame can never change the answer.
    ("overrun", "identical_retry.status", 409),
    ("overrun", "retry_again.status", 409),
    # The peer lane and the lease are both fine - only the publish is wedged.
    ("overrun", "peer_lane_frame.status", 200),
    ("overrun", "heartbeat_after_refusal.status", 200),
    ("overrun", "session_still_registered", True),
    # The rival hypothesis answers with a different, machine-readable, RECOVERABLE 409.
    ("gap", "first_frame.status", 200),
    ("gap", "skipped_sequence.status", 409),
    ("gap", "skipped_sequence.failure_code", "v2_out_of_order_frame"),
    ("gap", "awaited_sequence.status", 200),
)


def _resolve(tree: dict[str, Any], path: str) -> Any:
    value: Any = tree
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return f"<missing:{path}>"
        value = value[part]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=Path, default=None, help="write the full report to this path")
    args = parser.parse_args()

    if importlib.util.find_spec("fastapi") is None:
        print("probe unavailable: fastapi is not installed", file=sys.stderr)
        return 2
    try:
        api = _load_helpers()
    except Exception as exc:  # noqa: BLE001
        print(f"probe unavailable: {exc}", file=sys.stderr)
        return 2

    report = {"overrun": scenario_overrun(api), "gap": scenario_sequence_gap(api)}

    failures: list[str] = []
    for scenario, path, expected in EXPECTATIONS:
        actual = _resolve(report[scenario], path)
        if actual != expected:
            failures.append(f"{scenario}.{path}: expected {expected!r}, got {actual!r}")

    print(json.dumps(report, indent=2, sort_keys=True))
    if args.json is not None:
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    print()
    if failures:
        print(f"REFUTED: {len(failures)} recorded expectation(s) failed")
        for line in failures:
            print(f"  - {line}")
        return 3
    print("CONFIRMED: an overrun-failed lane answers 409 'v2 <lane> lane is failed.' permanently,")
    print("           carries NO machine-readable failure code, and is a different 409 from")
    print("           v2_out_of_order_frame, which is recoverable. The peer lane and the helper")
    print("           lease both survive it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
