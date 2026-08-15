#!/usr/bin/env python3
"""PROTOTYPE: measure hidden-tab strict-v2 admission at a requested route geometry.

Question: after Chrome has remained hidden beyond the five-minute intensive-throttling
threshold, do AudioWorklet-triggered frames continue to receive strict-v2 admission at
the requested production geometry while helper heartbeats remain inside their lease?

Run:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
    prototypes/browser-capture-feasibility/probe_g7_hidden_tab.py \\
    --frame-samples 8000 \\
    --hidden-seconds 310 \\
    --output evidence/phase1/x1-frame-drop/iteration-5-g7-hidden-8000.json

The caller configures only the local probe route.  The page reads that route's descriptor
normally.  Successful strict-v2 route admissions are joined to post-ACK worklet telemetry,
so pre-send telemetry cannot satisfy this probe.  This remains a deterministic-runtime,
synthetic-source cadence measurement, not an inference or attended-display-capture claim.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from dataclasses import replace
from pathlib import Path

from probe_recreate_session import (
    _DevToolsSocket,
    _chrome_binary,
    _json,
    _start_server,
    _stop_process_group,
    _stop_server,
    _test_live_api_module,
)
from production_route_server import build_app


_MINIMUM_HIDDEN_SECONDS = 300.0
_LANES = ("system", "microphone")


class _G7ChromePage:
    """Start the real capture page with only the autoplay allowance it needs."""

    def __init__(self, *, chrome_bin: str, url: str):
        self._profile = tempfile.TemporaryDirectory(prefix="moss-x1-g7-")
        self._process = subprocess.Popen(
            [
                chrome_bin,
                "--headless=new",
                "--no-first-run",
                "--no-default-browser-check",
                "--autoplay-policy=no-user-gesture-required",
                "--remote-debugging-port=0",
                f"--user-data-dir={self._profile.name}",
                url,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._socket = self._connect()

    def _connect(self) -> _DevToolsSocket:
        active_port = Path(self._profile.name) / "DevToolsActivePort"
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                raise RuntimeError(f"Chrome exited before DevTools was ready ({self._process.returncode})")
            if active_port.is_file():
                lines = active_port.read_text(encoding="utf-8").splitlines()
                if lines:
                    try:
                        targets = _json(f"http://127.0.0.1:{int(lines[0])}/json/list")
                        page = next(target for target in targets if target.get("type") == "page")
                        return _DevToolsSocket(page["webSocketDebuggerUrl"])
                    except Exception:
                        pass
            time.sleep(0.05)
        raise RuntimeError("Chrome DevTools did not become available")

    def evaluate(self, expression: str) -> object:
        return self._socket.evaluate(expression)

    def close(self) -> None:
        try:
            self._socket.close()
        finally:
            _stop_process_group(self._process)
            self._profile.cleanup()


def _debug_port(page: _G7ChromePage) -> int:
    lines = (Path(page._profile.name) / "DevToolsActivePort").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise RuntimeError("Chrome DevToolsActivePort did not contain a port")
    return int(lines[0])


def _cdp_call(client: _DevToolsSocket, method: str, params: dict | None = None) -> dict:
    request_id = client._next_id
    client._next_id += 1
    client._send_json({"id": request_id, "method": method, "params": params or {}})
    while True:
        message = client._read_json()
        if message.get("id") != request_id:
            continue
        if "error" in message:
            raise RuntimeError(f"Chrome {method} failed: {message['error']}")
        return message.get("result", {})


def _wait_for(predicate, *, timeout_seconds: float, description: str):
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for {description}")


def _hidden_duration_ms(records: list[dict], *, key: str) -> int:
    values = [record[key] for record in records if isinstance(record.get(key), int)]
    return max(values) - min(values) if len(values) >= 2 else 0


def _frame_matches_heartbeat(frame_records: dict[str, list[dict]], heartbeat: dict) -> bool:
    lane = heartbeat.get("trigger_lane")
    emitted_sequence = heartbeat.get("trigger_frame_sequence")
    return isinstance(lane, str) and isinstance(emitted_sequence, int) and any(
        record.get("emitted_sequence") == emitted_sequence
        for record in frame_records.get(lane, [])
    )


def _runtime_at_descriptor_geometry(frame_samples: int):
    helpers = _test_live_api_module()
    runtime = helpers.make_live_runtime(
        max_retained_samples=320_000,
        max_queue_depth=64,
        speech=(True, False) * 10_000,
    )
    runtime.descriptor = replace(
        runtime.descriptor,
        frame_samples=frame_samples,
        bounds=replace(
            runtime.descriptor.bounds,
            max_frame_samples=max(runtime.descriptor.bounds.max_frame_samples, frame_samples),
        ),
    )
    return runtime


def _contiguous_progression(records: list[dict]) -> bool:
    sequences = [record.get("sequence") for record in records]
    return (
        len(sequences) > 1
        and all(isinstance(sequence, int) for sequence in sequences)
        and all(right == left + 1 for left, right in zip(sequences, sequences[1:]))
    )


def _route_admissions_match_descriptor(records: list[dict], descriptor: dict) -> bool:
    return bool(records) and all(
        record.get("sample_count") == descriptor.get("frame_samples")
        and record.get("sample_rate") == descriptor.get("sample_rate")
        for record in records
    )


def _admission_cadence(records: list[dict], descriptor: dict) -> dict:
    timestamps = [record.get("client_wall_ms") for record in records]
    if not timestamps or not all(isinstance(timestamp, int) for timestamp in timestamps):
        raise RuntimeError("strict-v2 admission join lacks integer worklet timestamps")
    elapsed_ms = timestamps[-1] - timestamps[0] if len(timestamps) > 1 else 0
    frame_period_ms = descriptor["frame_samples"] / descriptor["sample_rate"] * 1_000
    expected_frames = round(elapsed_ms / frame_period_ms) + 1
    return {
        "accepted_frames": len(records),
        "elapsed_ms": elapsed_ms,
        "elapsed_expected_frames": expected_frames,
        "accepted_minus_elapsed_expected": len(records) - expected_frames,
        "frame_period_ms": frame_period_ms,
    }


def _run(*, chrome_bin: str, frame_samples: int, hidden_seconds: float) -> dict:
    runtime = _runtime_at_descriptor_geometry(frame_samples)
    app = build_app(runtime_factory_override=lambda: runtime)
    base_url, server, thread = _start_server(app)
    page = None
    browser = None
    try:
        route_descriptor = _json(
            f"{base_url}/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2"
        )["descriptor"]
        page = _G7ChromePage(
            chrome_bin=chrome_bin,
            url=f"{base_url}/capture-harness?autostart=1",
        )

        def started() -> dict | None:
            verdict = _json(f"{base_url}/prototype/g7-verdict")
            admitted = verdict["raw_strict_v2_frame_acceptances"]
            has_admission = all(
                any(record.get("lane") == lane for record in admitted) for lane in _LANES
            )
            return verdict if verdict["session_active_after_hidden_phase"] and has_admission else None

        _wait_for(started, timeout_seconds=20.0, description="the page to create an active session")
        version = _json(f"http://127.0.0.1:{_debug_port(page)}/json/version")
        browser = _DevToolsSocket(version["webSocketDebuggerUrl"])
        sibling = _cdp_call(browser, "Target.createTarget", {"url": "about:blank"})
        _cdp_call(browser, "Target.activateTarget", {"targetId": sibling["targetId"]})
        _wait_for(
            lambda: page.evaluate("document.visibilityState") == "hidden",
            timeout_seconds=10.0,
            description="the capture page to become hidden",
        )
        hidden_started = time.monotonic()
        while time.monotonic() - hidden_started < hidden_seconds:
            if not _json(f"{base_url}/prototype/g7-verdict")["session_active_after_hidden_phase"]:
                raise RuntimeError("session became inactive during the hidden phase")
            time.sleep(0.25)

        verdict = _json(f"{base_url}/prototype/g7-verdict")
        full_verdict = _json(f"{base_url}/prototype/verdict")
        raw_heartbeats = verdict["raw_hidden_heartbeats"]
        raw_frames = verdict["raw_hidden_frames"]
        v2 = verdict["v2_session"]
        hidden_duration_ms = _hidden_duration_ms(raw_heartbeats, key="started_wall_ms")
        cadence = {lane: _admission_cadence(raw_frames[lane], route_descriptor) for lane in _LANES}
        assertions = {
            "page_was_observed_hidden": page.evaluate("document.visibilityState") == "hidden",
            "hidden_phase_exceeded_five_minutes": hidden_duration_ms > _MINIMUM_HIDDEN_SECONDS * 1_000,
            "route_advertised_requested_geometry": route_descriptor["frame_samples"] == frame_samples,
            "route_advertised_geometry_matches_production_verdict": (
                full_verdict["descriptor"] == route_descriptor
            ),
            "both_lanes_have_hidden_strict_v2_route_admissions": all(raw_frames[lane] for lane in _LANES),
            "hidden_route_admissions_match_route_descriptor": all(
                _route_admissions_match_descriptor(raw_frames[lane], route_descriptor) for lane in _LANES
            ),
            "each_lane_has_contiguous_hidden_accepted_sequence_progression": all(
                _contiguous_progression(raw_frames[lane]) for lane in _LANES
            ),
            "admitted_frames_approximately_match_hidden_elapsed_cadence": all(
                abs(cadence[lane]["accepted_minus_elapsed_expected"]) <= 1 for lane in _LANES
            ),
            "each_hidden_heartbeat_has_a_hidden_worklet_frame_trigger": bool(raw_heartbeats)
            and all(_frame_matches_heartbeat(raw_frames, heartbeat) for heartbeat in raw_heartbeats),
            "all_hidden_heartbeats_succeeded": bool(raw_heartbeats)
            and all(heartbeat.get("status") == 200 for heartbeat in raw_heartbeats),
            "hidden_heartbeat_sequences_are_contiguous": not verdict["heartbeat_summary"]["sequence_gaps"],
            "hidden_max_heartbeat_delta_stayed_below_helper_lease": verdict["heartbeat_summary"]["hidden_max_delta_below_lease"],
            "session_stayed_active_after_hidden_phase": verdict["session_active_after_hidden_phase"],
            "strict_v2_accounting_matches_descriptor_frames": all(
                v2["lanes"][lane]["accepted_samples"]
                == v2["lanes"][lane]["next_sequence"] * route_descriptor["frame_samples"]
                for lane in _LANES
            ),
        }
        if not all(assertions.values()):
            raise RuntimeError(f"G7 assertions failed: {assertions}")
        return {
            "descriptor": route_descriptor,
            "hidden_duration_ms": hidden_duration_ms,
            "hidden_admission_cadence": cadence,
            "assertions": assertions,
            "verdict": verdict,
        }
    finally:
        if browser is not None:
            browser.close()
        if page is not None:
            page.close()
        _stop_server(app, server, thread)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frame-samples", type=int, required=True)
    parser.add_argument("--hidden-seconds", type=float, default=310.0)
    parser.add_argument("--chrome-bin")
    args = parser.parse_args()
    if args.frame_samples <= 0:
        parser.error("--frame-samples must be positive")
    if args.hidden_seconds <= 0:
        parser.error("--hidden-seconds must be positive")

    result: dict = {
        "probe": "prototypes/browser-capture-feasibility/probe_g7_hidden_tab.py",
        "question": (
            "does a real Chrome capture tab retain strict-v2 frame admission and helper lease "
            "while hidden beyond five minutes at a caller-selected route geometry"
        ),
        "scope": (
            "local production HTTP routes, deterministic provider, synthetic 48 kHz browser sources, "
            "and headless Chrome hidden by a DevTools-created sibling; no model inference or display capture"
        ),
        "requested_frame_samples": args.frame_samples,
        "requested_hidden_seconds": args.hidden_seconds,
        "passed": False,
    }
    try:
        result.update(
            _run(
                chrome_bin=_chrome_binary(args.chrome_bin),
                frame_samples=args.frame_samples,
                hidden_seconds=args.hidden_seconds,
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
