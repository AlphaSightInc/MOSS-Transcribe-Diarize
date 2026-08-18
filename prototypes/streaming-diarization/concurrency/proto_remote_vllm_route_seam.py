#!/usr/bin/env python3
"""Measure one local live-route canonical decode through a remote vLLM endpoint.

This is deliberately a seam probe, not the W2 matrix: it proves that a locally-owned
live runtime can reach the read-only remote decoder without falling back to a local HF
model. It records the source-revision mismatch when its supplied manifest was not
re-finalized for the current checkout, so such a result cannot be mistaken for G4/G5.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = Path(__file__).with_name("cpu_hf_local_fixture.json")
SERVER_PATH = ROOT / "prototypes/browser-capture-feasibility/production_route_server.py"


class ProbeError(RuntimeError):
    """A fail-closed prerequisite or route result."""


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    bearer: str | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[int, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        raw = error.read().decode("utf-8", errors="replace")
        try:
            body: Any = json.loads(raw)
        except json.JSONDecodeError:
            body = raw
        return error.code, body
    except urllib.error.URLError as error:
        raise ProbeError(f"request failed for {url}: {error.reason}") from error


def _require_200(label: str, response: tuple[int, Any], records: list[dict[str, Any]]) -> Any:
    status, body = response
    records.append({"label": label, "status": status})
    if status != 200:
        detail = body.get("detail") if isinstance(body, dict) else body
        raise ProbeError(f"{label} returned HTTP {status}: {detail}")
    return body


class _Heartbeat:
    """Keep helper presence independent from a remote canonical decode's duration."""

    def __init__(self, *, base_url: str, session_id: str, bearer: str, lease_seconds: float):
        self._base_url = base_url
        self._session_id = session_id
        self._bearer = bearer
        self._interval_seconds = lease_seconds / 4.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sequence = 0
        self.statuses: list[int] = []
        self.error: str | None = None
        self._thread = threading.Thread(target=self._run, name="w2-remote-vllm-heartbeat", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval_seconds + 5.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                sequence = self._sequence
                self._sequence += 1
            payload = {
                "schema": "moss-live-helper-health.v1",
                "instance_id": "w2-remote-vllm-route-seam",
                "sequence": sequence,
                "sent_monotonic_ns": time.monotonic_ns(),
                "helper_version": "w2-remote-vllm-route-seam-v1",
                "state": "capturing",
                "lanes": {
                    lane: {
                        "state": "capturing",
                        "device_epoch": 1,
                        "dropped_frames": 0,
                        "discontinuities": 0,
                        "failure_code": None,
                    }
                    for lane in ("microphone", "system")
                },
            }
            try:
                status, _ = _json_request(
                    f"{self._base_url}/api/live/sessions/{urllib.parse.quote(self._session_id)}/heartbeat",
                    method="POST",
                    payload=payload,
                    bearer=self._bearer,
                    timeout_seconds=self._interval_seconds,
                )
                self.statuses.append(status)
                if status != 200:
                    self.error = f"heartbeat returned HTTP {status}"
                    return
            except ProbeError as error:
                self.error = str(error)
                return
            self._stop.wait(self._interval_seconds)


def _wait_for_descriptor(base_url: str, process: subprocess.Popen[bytes], timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise ProbeError("local route probe exited during startup")
        try:
            status, body = _json_request(f"{base_url}/api/live/descriptor", timeout_seconds=2.0)
        except ProbeError:
            time.sleep(0.2)
            continue
        if status == 200 and isinstance(body, dict) and isinstance(body.get("descriptor"), dict):
            return body["descriptor"]
        time.sleep(0.2)
    raise ProbeError("local route probe did not expose a descriptor before the startup deadline")


def _stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def _run(args: argparse.Namespace) -> dict[str, Any]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    clip = fixture["clips"][0]
    audio_path = ROOT / fixture["audio"]["path"]
    if _sha256(audio_path) != fixture["audio"]["sha256"]:
        raise ProbeError("hash-pinned human-speech fixture drifted")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    head_revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    records: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "schema": "moss-w2-remote-vllm-route-seam.v1",
        "question": "Can one local production live-route runtime produce a canonical result through the read-only remote vLLM endpoint without a local HF model?",
        "head_revision": head_revision,
        "manifest_source_revision": manifest.get("source_revision"),
        "manifest_matches_head": manifest.get("source_revision") == head_revision,
        "vllm_base_url": args.vllm_base_url,
        "vllm_model": args.vllm_model,
        "fixture": {"path": str(audio_path.relative_to(ROOT)), "sha256": _sha256(audio_path), "clip_id": clip["id"]},
        "helper_lease_seconds": args.live_helper_lease_seconds,
        "heartbeat_interval_seconds": args.live_helper_lease_seconds / 4.0,
        "requests": records,
        "does_not_establish": [
            "the W2 1/2/4/8-session matrix or its 600-second soak",
            "G4 or G5",
            "GPU memory, utilisation, OOM/errors, or vLLM active/queued counts",
            "a source-revision-correct measurement when manifest_matches_head is false",
        ],
    }
    models = _require_200(
        "remote_vllm_models",
        _json_request(f"{args.vllm_base_url.rstrip('/')}/models", timeout_seconds=args.request_timeout_seconds),
        records,
    )
    model_ids = [item.get("id") for item in models.get("data", []) if isinstance(item, dict)] if isinstance(models, dict) else []
    result["remote_vllm_model_ids"] = model_ids
    if args.vllm_model not in model_ids:
        raise ProbeError("configured vLLM model is absent from /v1/models")

    port = args.port or 19000 + (uuid.uuid4().int % 1000)
    base_url = f"http://127.0.0.1:{port}"
    process: subprocess.Popen[bytes] | None = None
    heartbeat: _Heartbeat | None = None
    try:
        command = [
            sys.executable,
            str(SERVER_PATH),
            "--live-provider-manifest",
            str(args.manifest),
            "--vllm-base-url",
            args.vllm_base_url,
            "--vllm-model",
            args.vllm_model,
            "--vllm-timeout-seconds",
            str(args.request_timeout_seconds),
            "--live-helper-lease-seconds",
            str(args.live_helper_lease_seconds),
            "--port",
            str(port),
        ]
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        descriptor = _wait_for_descriptor(base_url, process, args.startup_timeout_seconds)
        result["local_descriptor"] = {
            key: descriptor[key]
            for key in ("source_revision", "provider_name", "provider_revision", "sample_rate", "frame_samples")
        }
        bootstrap = _require_200("local_bootstrap", _json_request(f"{base_url}/prototype/bootstrap"), records)
        bearer = bootstrap.get("capture_bearer") if isinstance(bootstrap, dict) else None
        if not isinstance(bearer, str) or not bearer:
            raise ProbeError("local bootstrap did not issue capture authority")
        result["capture_bearer_length"] = len(bearer)
        session = _require_200(
            "local_create_session",
            _json_request(f"{base_url}/api/live/sessions", method="POST", payload={"echo_mode": "headphones"}, bearer=bearer),
            records,
        )
        session_id = session.get("id") if isinstance(session, dict) else None
        view_bearer = session.get("view_token") if isinstance(session, dict) else None
        if not isinstance(session_id, str) or not isinstance(view_bearer, str):
            raise ProbeError("local session creation did not issue session authority")
        result["session_id"] = session_id
        heartbeat = _Heartbeat(base_url=base_url, session_id=session_id, bearer=bearer, lease_seconds=args.live_helper_lease_seconds)
        heartbeat.start()
        frame_samples = int(descriptor["frame_samples"])
        sample_rate = int(descriptor["sample_rate"])
        # The VAD closes a max-sized span only once it has observed audio beyond that
        # boundary. Two descriptor-derived spans avoid assuming that a particular speech
        # transition happens at the hard-cap edge, while remaining a one-canonical-span seam
        # probe rather than a duration or concurrency measurement.
        pair_count = 2 * math.ceil(int(descriptor["bounds"]["hard_cap_samples"]) / frame_samples)
        result["frame_pairs_attempted_per_lane"] = pair_count
        capture_started_ns = time.time_ns()
        with wave.open(str(audio_path), "rb") as source:
            expected_shape = (fixture["audio"]["channels"], fixture["audio"]["sample_width_bytes"], sample_rate)
            observed_shape = (source.getnchannels(), source.getsampwidth(), source.getframerate())
            if observed_shape != expected_shape:
                raise ProbeError(f"fixture shape {observed_shape} does not match {expected_shape}")
            source.setpos(int(clip["start_seconds"] * sample_rate))
            for sequence in range(pair_count):
                pcm = source.readframes(frame_samples)
                if len(pcm) != frame_samples * 2:
                    raise ProbeError("fixture ended before one descriptor hard-cap span")
                for lane in ("microphone", "system"):
                    payload = {
                        "lane": lane,
                        "sequence": sequence,
                        "capture_timestamp_ns": capture_started_ns
                        + sequence * frame_samples * 1_000_000_000 // sample_rate,
                        "device_epoch": 1,
                        "silent": not any(pcm),
                        "discontinuity": False,
                        "sample_rate": sample_rate,
                        "sample_count": frame_samples,
                        "pcm_base64": base64.b64encode(pcm).decode("ascii"),
                    }
                    _require_200(
                        f"frame_{sequence}_{lane}",
                        _json_request(
                            f"{base_url}/api/live/sessions/{urllib.parse.quote(session_id)}/frames",
                            method="POST",
                            payload=payload,
                            bearer=bearer,
                            timeout_seconds=args.request_timeout_seconds,
                        ),
                        records,
                    )
        deadline = time.monotonic() + args.canonical_timeout_seconds
        events: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            response = _require_200(
                "local_events",
                _json_request(f"{base_url}/api/live/sessions/{urllib.parse.quote(session_id)}/events?since_seq=0", bearer=view_bearer),
                records,
            )
            events = [event for event in response.get("events", []) if isinstance(event, dict) and event.get("kind") == "canonical_processed"]
            if events:
                break
            time.sleep(0.5)
        if not events:
            raise ProbeError("no canonical_processed event before the canonical timeout")
        result["canonical_processed_event_count"] = len(events)
        result["canonical_processed_committed_samples"] = [event.get("payload", {}).get("committed_samples") for event in events]
        if heartbeat.error is not None:
            raise ProbeError(heartbeat.error)
        stop_response = _json_request(
            f"{base_url}/api/live/sessions/{urllib.parse.quote(session_id)}/stop",
            method="POST",
            payload={"deadline": 90},
            bearer=bearer,
            timeout_seconds=110,
        )
        stopped = _require_200("local_stop", stop_response, records)
        result["stop_http_status"] = stop_response[0]
        result["stop_terminal_status"] = stopped.get("status") if isinstance(stopped, dict) else None
        result["heartbeat_statuses"] = heartbeat.statuses
        result["route_seam_passes"] = True
        result["qualifies_w2"] = False
        return result
    finally:
        if heartbeat is not None:
            heartbeat.close()
            result.setdefault("heartbeat_statuses", heartbeat.statuses)
            if heartbeat.error is not None:
                result.setdefault("heartbeat_error", heartbeat.error)
        _stop_process(process)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--vllm-base-url", required=True)
    parser.add_argument("--vllm-model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int)
    parser.add_argument("--live-helper-lease-seconds", type=float, required=True)
    parser.add_argument("--startup-timeout-seconds", type=float, default=30.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=120.0)
    parser.add_argument("--canonical-timeout-seconds", type=float, default=120.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.live_helper_lease_seconds <= 0:
        raise SystemExit("--live-helper-lease-seconds must be positive")
    result: dict[str, Any]
    try:
        result = _run(args)
    except ProbeError as error:
        result = {"schema": "moss-w2-remote-vllm-route-seam.v1", "route_seam_passes": False, "error": str(error)}
        _atomic_json(args.output, result)
        print(json.dumps(result, indent=2, sort_keys=True))
        raise SystemExit(1) from error
    _atomic_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
