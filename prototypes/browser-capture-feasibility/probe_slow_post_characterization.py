#!/usr/bin/env python3
"""PROTOTYPE: regression-test the page's real worklet-to-POST behavior under a slow POST.

Question: when strict-v2 frame POST responses are slower than the descriptor frame
period, does the actual browser page admit every elapsed-cadence frame while keeping one
in-flight POST per lane?

Run:
  PYTHONDONTWRITEBYTECODE=1 python3 \
    prototypes/browser-capture-feasibility/probe_slow_post_characterization.py \
    --output evidence/phase1/x1-frame-drop/iteration-2-slow-post-characterization.json

The local FastAPI app is the existing production-route harness.  Its middleware delays
only the response after the real strict-v2 frame handler has admitted the request, so
the browser's fetch remains in flight while the page and server paths stay real.  The
deterministic provider and synthetic sources keep this a capture-transport measurement,
not a model or display-capture claim.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]

import sys

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO_ROOT))

from production_route_server import build_app


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _json(url: str) -> dict:
    with urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _chrome_binary(explicit: str | None) -> str:
    if explicit:
        return explicit
    path = shutil.which("google-chrome")
    if path:
        return path
    macos = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if macos.is_file():
        return str(macos)
    raise RuntimeError("Google Chrome not found; supply --chrome-bin")


def _start_server(app):
    import uvicorn

    port = _free_loopback_port()
    base_url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)
    )
    server.install_signal_handlers = lambda: None
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        try:
            _json(f"{base_url}/prototype/verdict")
            return base_url, server, thread
        except Exception:
            time.sleep(0.05)
    server.should_exit = True
    thread.join(timeout=5)
    raise RuntimeError("production-route server did not start")


def _stop_server(app, server, thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)
    app.state.prototype_scratch.cleanup()


def _stop_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)


def _frame_records(verdict: dict, lane: str) -> list[dict]:
    telemetry = verdict.get("telemetry", {}).get("lanes", {}).get(lane, {})
    return sorted(
        telemetry.values(),
        key=lambda record: int(record.get("sequence", -1)),
    )


def _lane_summary(records: list[dict], *, frame_period_ms: float, accepted: int) -> dict:
    timestamps = [record.get("client_wall_ms") for record in records]
    if not all(isinstance(value, int) for value in timestamps):
        raise RuntimeError("page telemetry did not provide integer client_wall_ms values")
    elapsed_ms = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0
    elapsed_expected_frames = round(elapsed_ms / frame_period_ms) + 1
    return {
        "emitted_frames": len(records),
        "accepted_frames": accepted,
        "elapsed_ms": elapsed_ms,
        "elapsed_expected_frames": elapsed_expected_frames,
        "emitted_minus_elapsed_expected": len(records) - elapsed_expected_frames,
        "accepted_minus_emitted": accepted - len(records),
        "accepted_minus_elapsed_expected": accepted - elapsed_expected_frames,
        "first_sequence": records[0].get("sequence"),
        "last_sequence": records[-1].get("sequence"),
        "wire_sequences": [record.get("wire_sequence") for record in records],
        "queue_capacities": sorted({record.get("queue_capacity") for record in records}),
        "max_queue_depth_at_enqueue": max(
            int(record.get("queue_depth_at_enqueue", 0)) for record in records
        ),
    }


def _attach_response_delay(app, response_delay_seconds: float) -> dict:
    metrics = {
        "response_delay_ms": round(response_delay_seconds * 1_000),
        "frame_responses_started": 0,
        "frame_responses_completed": 0,
        "responses_currently_held": 0,
        "max_responses_held": 0,
        "frame_status_counts": {},
        "lanes": {},
    }
    lock = threading.Lock()

    @app.middleware("http")
    async def delay_frame_response(request, call_next):
        is_frame = request.method == "POST" and request.url.path.endswith("/frames")
        lane = None
        if is_frame:
            lane = request.headers.get("x-prototype-lane")
            if lane not in {"system", "microphone"}:
                raise RuntimeError(f"frame route missing prototype lane header: {lane!r}")
        response = await call_next(request)
        if not is_frame:
            return response
        with lock:
            metrics["frame_responses_started"] += 1
            status = str(response.status_code)
            metrics["frame_status_counts"][status] = metrics["frame_status_counts"].get(status, 0) + 1
            metrics["responses_currently_held"] += 1
            metrics["max_responses_held"] = max(
                metrics["max_responses_held"], metrics["responses_currently_held"]
            )
            lane_metrics = metrics["lanes"].setdefault(
                lane,
                {"responses_currently_held": 0, "max_responses_held": 0},
            )
            lane_metrics["responses_currently_held"] += 1
            lane_metrics["max_responses_held"] = max(
                lane_metrics["max_responses_held"], lane_metrics["responses_currently_held"]
            )
        try:
            import asyncio

            await asyncio.sleep(response_delay_seconds)
            return response
        finally:
            with lock:
                metrics["responses_currently_held"] -= 1
                metrics["frame_responses_completed"] += 1
                metrics["lanes"][lane]["responses_currently_held"] -= 1

    return metrics


def _run(*, chrome_bin: str, response_delay_seconds: float, target_frames_per_lane: int) -> dict:
    app = build_app()
    slow_post_metrics = _attach_response_delay(app, response_delay_seconds)
    base_url, server, thread = _start_server(app)
    profile = tempfile.TemporaryDirectory(prefix="moss-x1-slow-post-")
    page = None
    try:
        page = subprocess.Popen(
            [
                chrome_bin,
                "--headless=new",
                "--no-first-run",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
                f"--user-data-dir={profile.name}",
                f"{base_url}/capture-harness?autostart=1",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.monotonic() + 30.0
        last_lane_counts: dict[str, int] = {}
        last_v2_status = None
        while time.monotonic() < deadline:
            verdict = _json(f"{base_url}/prototype/verdict")
            system = _frame_records(verdict, "system")
            microphone = _frame_records(verdict, "microphone")
            last_lane_counts = {"system": len(system), "microphone": len(microphone)}
            last_v2_status = None if verdict.get("v2_session") is None else verdict["v2_session"].get("status")
            if (
                verdict.get("v2_session")
                and len(system) >= target_frames_per_lane
                and len(microphone) >= target_frames_per_lane
            ):
                break
            time.sleep(0.05)
        else:
            raise RuntimeError(
                "page did not produce the requested strict-v2 frame telemetry: "
                f"lane_counts={last_lane_counts} v2_status={last_v2_status} "
                f"held={slow_post_metrics['max_responses_held']}"
            )

        verdict = _json(f"{base_url}/prototype/verdict")
        descriptor = verdict["descriptor"]
        frame_period_ms = descriptor["frame_samples"] / descriptor["sample_rate"] * 1_000
        v2 = verdict["v2_session"]
        lane_summaries = {
            lane: _lane_summary(
                _frame_records(verdict, lane),
                frame_period_ms=frame_period_ms,
                accepted=v2["lanes"][lane]["next_sequence"],
            )
            for lane in ("system", "microphone")
        }
        assertions = {
            "accepted_frames_approximately_match_emitted_frames": all(
                abs(summary["accepted_minus_emitted"]) <= 1
                for summary in lane_summaries.values()
            ),
            # This direct admission-to-elapsed-cadence join is the P0 gate: reinstating a
            # one-in-flight worklet guard would make accepted frames fall behind elapsed frames.
            "admitted_frames_approximately_match_elapsed_cadence": all(
                abs(summary["accepted_minus_elapsed_expected"]) <= 1
                for summary in lane_summaries.values()
            ),
            "per_lane_frame_posts_are_serial": all(
                lane_metrics["max_responses_held"] == 1
                for lane_metrics in slow_post_metrics["lanes"].values()
            ) and set(slow_post_metrics["lanes"]) == {"system", "microphone"},
            "wire_sequences_follow_admitted_worklet_order": all(
                # The route can admit one response before the page's asynchronous telemetry
                # POST lands; compare wire order to the recorded successful sends, while the
                # direct admission-to-cadence assertion above covers that one-record race.
                summary["wire_sequences"] == list(range(summary["emitted_frames"]))
                for summary in lane_summaries.values()
            ),
        }
        if not all(assertions.values()):
            raise RuntimeError(f"slow-POST characterization assertions failed: {assertions}")
        return {
            "descriptor": descriptor,
            "frame_period_ms": frame_period_ms,
            "lane_summaries": lane_summaries,
            "slow_post_metrics": dict(slow_post_metrics),
            "assertions": assertions,
            "verdict": verdict,
        }
    finally:
        if page is not None:
            _stop_process_group(page)
        profile.cleanup()
        _stop_server(app, server, thread)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    # This is 1.6 times the route's default 62.5 ms frame period: enough to prove
    # overlap without starving its separate heartbeat route on Chrome's local HTTP pool.
    parser.add_argument("--response-delay-ms", type=float, default=100.0)
    parser.add_argument("--target-frames-per-lane", type=int, default=48)
    parser.add_argument("--chrome-bin")
    args = parser.parse_args()
    if args.response_delay_ms <= 0:
        parser.error("--response-delay-ms must be positive")
    if args.target_frames_per_lane < 2:
        parser.error("--target-frames-per-lane must be at least 2")

    result: dict = {
        "probe": "prototypes/browser-capture-feasibility/probe_slow_post_characterization.py",
        "question": (
            "under a real strict-v2 POST response delay, does the actual page preserve capture "
            "cadence and admissions with a bounded per-lane serial sender"
        ),
        "scope": (
            "local production HTTP routes, deterministic provider, synthetic 48 kHz browser "
            "sources, and a real headless Chrome page; no model inference or display capture"
        ),
        "requested_response_delay_ms": args.response_delay_ms,
        "requested_frames_per_lane": args.target_frames_per_lane,
        "passed": False,
    }
    try:
        result.update(
            _run(
                chrome_bin=_chrome_binary(args.chrome_bin),
                response_delay_seconds=args.response_delay_ms / 1_000,
                target_frames_per_lane=args.target_frames_per_lane,
            )
        )
        result["passed"] = True
    except Exception as exc:
        result["error"] = str(exc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
