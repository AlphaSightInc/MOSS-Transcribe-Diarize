#!/usr/bin/env python3
"""Run the preregistered local CPU/HF G4/G5 measurement without GPU claims.

This is a measurement harness, not product code. It starts one loopback FastAPI process
through the production live routes, uses only hash-pinned human speech, and leaves raw
arrays durable as the run progresses. `--preflight` is read-only apart from its output
artifact; the normal command re-finalizes the *local* provider manifest for the current
checkout before it starts the locally-owned service.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import signal
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
CONTRACT_PATH = Path(__file__).with_name("cpu_hf_local_preregistration.json")
FIXTURE_PATH = Path(__file__).with_name("cpu_hf_local_fixture.json")
SERVER_PATH = ROOT / "prototypes/browser-capture-feasibility/production_route_server.py"
FINALIZER_PATH = ROOT / "ops/finalize-live-provider-manifest.py"
DEFAULT_DEPLOYED_DESCRIPTOR_URL = (
    "https://ga0-alienware-rtx4070ti.tailnet.aisight.us:7861/api/live/descriptor"
)


class MeasurementError(RuntimeError):
    """A prerequisite or a gate predicate failed; the raw output remains useful."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise MeasurementError(f"{path} must contain one JSON object")
    return value


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _type7(values: list[float], probability: float) -> float | None:
    """Linear Type-7 quantile, stated explicitly in the frozen contract."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * probability
    lower = math.floor(index)
    upper = math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def _canonical_lifecycle_fairness(
    events: list[dict[str, Any]], session_ids: set[str], *, maximum_skew: int
) -> dict[str, Any]:
    """Evaluate dispatches only while the compared sessions are queued together.

    A session with no queued work is not eligible for the next canonical dispatch.
    Counting it against a peer that still has work mistakes unequal VAD/span output
    for round-robin starvation. The v2 measurement log captures the runtime's
    queued -> started -> processed lifecycle, allowing a pairwise counter to reset
    whenever either member ceases to be ready.

    This is deliberately a verifier, not scheduler policy: malformed or old
    ``canonical_processed``-only evidence fails closed instead of yielding a
    deceptively precise skew number.
    """
    queued_items = {session_id: set() for session_id in session_ids}
    started_items = {session_id: set() for session_id in session_ids}
    pair_counts: dict[tuple[str, str], dict[str, int]] = {}
    maximum_observed_skew = 0
    contended_pair_dispatch_observations = 0
    lifecycle_counts = {
        kind: 0
        for kind in ("canonical_queued", "canonical_started", "canonical_processed")
    }
    errors: list[str] = []

    def active_pairs() -> set[tuple[str, str]]:
        ready = sorted(session_id for session_id, items in queued_items.items() if items)
        return {
            (left, right)
            for index, left in enumerate(ready)
            for right in ready[index + 1 :]
        }

    def reconcile_pairs() -> None:
        active = active_pairs()
        for pair in tuple(pair_counts):
            if pair not in active:
                del pair_counts[pair]
        for pair in active:
            pair_counts.setdefault(pair, {pair[0]: 0, pair[1]: 0})

    for index, event in enumerate(events):
        session_id = event.get("session_id")
        kind = event.get("kind")
        payload = event.get("payload")
        if session_id not in session_ids:
            continue
        if kind not in lifecycle_counts:
            errors.append(f"event {index} has unsupported canonical lifecycle kind {kind!r}")
            continue
        lifecycle_counts[kind] += 1
        if not isinstance(payload, dict) or not isinstance(payload.get("item_id"), int):
            errors.append(f"event {index} lacks an integer canonical item_id")
            continue
        item_id = payload["item_id"]
        if kind == "canonical_queued":
            if item_id in queued_items[session_id] or item_id in started_items[session_id]:
                errors.append(f"event {index} queues duplicate item {session_id}/{item_id}")
                continue
            queued_items[session_id].add(item_id)
            reconcile_pairs()
            continue
        if kind == "canonical_started":
            reconcile_pairs()
            if item_id not in queued_items[session_id]:
                errors.append(f"event {index} starts unqueued item {session_id}/{item_id}")
                continue
            for pair, counts in pair_counts.items():
                if session_id not in pair:
                    continue
                contended_pair_dispatch_observations += 1
                counts[session_id] += 1
                maximum_observed_skew = max(
                    maximum_observed_skew,
                    abs(counts[pair[0]] - counts[pair[1]]),
                )
            queued_items[session_id].remove(item_id)
            started_items[session_id].add(item_id)
            reconcile_pairs()
            continue
        if item_id not in started_items[session_id]:
            errors.append(f"event {index} processes unstarted item {session_id}/{item_id}")

    for session_id, items in queued_items.items():
        if items:
            errors.append(f"run ended with queued canonical items for {session_id}")
    for kind, count in lifecycle_counts.items():
        if count == 0:
            errors.append(f"lifecycle evidence has no {kind} events")
    return {
        "method": "pairwise dispatch skew over each continuous jointly-ready interval",
        "lifecycle_event_counts": lifecycle_counts,
        "contended_pair_dispatch_observations": contended_pair_dispatch_observations,
        "maximum_contended_pair_dispatch_skew": maximum_observed_skew,
        "fairness_gate": maximum_skew,
        "errors": errors,
        "passes": not errors and maximum_observed_skew <= maximum_skew,
    }


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    bearer: str | None = None,
    insecure_tls: bool = False,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    context = ssl._create_unverified_context() if insecure_tls else None
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds, context=context) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "status": response.status,
                "json": json.loads(body) if body else None,
                "body": body,
            }
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            decoded: Any = json.loads(body)
        except json.JSONDecodeError:
            decoded = None
        return {"status": error.code, "json": decoded, "body": body}
    except urllib.error.URLError as error:
        raise MeasurementError(f"request failed for {url}: {error.reason}") from error


def _descriptor_fields(descriptor: dict[str, Any]) -> dict[str, Any]:
    try:
        bounds = descriptor["bounds"]
        return {
            "sample_rate": descriptor["sample_rate"],
            "frame_samples": descriptor["frame_samples"],
            "hard_cap_samples": bounds["hard_cap_samples"],
            "max_events": bounds["max_events"],
            "max_frame_samples": bounds["max_frame_samples"],
            "max_identity_speakers": bounds["max_identity_speakers"],
            "max_queue_depth": bounds["max_queue_depth"],
            "max_retained_samples": bounds["max_retained_samples"],
            "stop_drain_deadline_seconds": bounds["stop_drain_deadline_seconds"],
        }
    except (KeyError, TypeError) as error:
        raise MeasurementError("descriptor is missing a required deployed-bound field") from error


def _process_tree_rss_bytes(root_pid: int) -> int:
    """Measure the owned FastAPI process tree only; Darwin ps reports RSS in KiB."""
    output = subprocess.check_output(
        ["ps", "-axo", "pid=,ppid=,rss="], text=True, encoding="utf-8"
    )
    rows: dict[int, tuple[int, int]] = {}
    for raw in output.splitlines():
        parts = raw.split()
        if len(parts) != 3:
            continue
        pid, parent, rss = (int(part) for part in parts)
        rows[pid] = (parent, rss)
    pending = [root_pid]
    included: set[int] = set()
    while pending:
        pid = pending.pop()
        if pid in included or pid not in rows:
            continue
        included.add(pid)
        pending.extend(child for child, (parent, _) in rows.items() if parent == pid)
    return sum(rows[pid][1] for pid in included) * 1024


def _wav_clip(fixture: dict[str, Any], clip: dict[str, Any]) -> bytes:
    audio = fixture["audio"]
    path = ROOT / audio["path"]
    if _sha256(path) != audio["sha256"]:
        raise MeasurementError("human-speech fixture hash drifted")
    with wave.open(str(path), "rb") as source:
        shape = (source.getnchannels(), source.getsampwidth(), source.getframerate())
        expected = (audio["channels"], audio["sample_width_bytes"], audio["sample_rate"])
        if shape != expected:
            raise MeasurementError(f"human-speech fixture has shape {shape}, expected {expected}")
        start = int(clip["start_seconds"] * audio["sample_rate"])
        end = int(clip["end_seconds"] * audio["sample_rate"])
        if start < 0 or end <= start or end > source.getnframes():
            raise MeasurementError(f"invalid clip bounds for {clip['id']}")
        source.setpos(start)
        return source.readframes(end - start)


def _wrapped_frame(pcm: bytes, *, sequence: int, frame_samples: int) -> bytes:
    total_samples = len(pcm) // 2
    start = (sequence * frame_samples) % total_samples
    if start + frame_samples <= total_samples:
        return pcm[start * 2 : (start + frame_samples) * 2]
    left = pcm[start * 2 :]
    right_samples = frame_samples - (total_samples - start)
    return left + pcm[: right_samples * 2]


_UNEXPECTED_FRAME_EXEMPLARS_PER_BUCKET = 3


def _frame_payload_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep request metadata and a PCM fingerprint, never the PCM itself."""
    encoded_pcm = payload.get("pcm_base64")
    if not isinstance(encoded_pcm, str):
        raise MeasurementError("measurement frame payload lacks pcm_base64")
    pcm = base64.b64decode(encoded_pcm, validate=True)
    return {
        "lane": payload["lane"],
        "sequence": payload["sequence"],
        "capture_timestamp_ns": payload["capture_timestamp_ns"],
        "device_epoch": payload["device_epoch"],
        "silent": payload["silent"],
        "discontinuity": payload["discontinuity"],
        "sample_rate": payload["sample_rate"],
        "sample_count": payload["sample_count"],
        "pcm_len": len(pcm),
        "pcm_sha256_prefix": hashlib.sha256(pcm).hexdigest()[:16],
    }


def _frame_response_evidence(response: dict[str, Any]) -> dict[str, Any]:
    body = response.get("json")
    body = body if isinstance(body, dict) else {}
    failure = body.get("failure")
    failure = failure if isinstance(failure, dict) else {}
    error_code = failure.get("code")
    return {
        "http_status": response["status"],
        "error_code": error_code if isinstance(error_code, str) and error_code else "unspecified",
        "detail": body.get("detail") if isinstance(body.get("detail"), str) else None,
        "retryable": failure.get("retryable") if isinstance(failure.get("retryable"), bool) else None,
        "failure_detail": failure.get("detail") if isinstance(failure.get("detail"), dict) else None,
    }


def _new_unexpected_frame_results() -> dict[str, Any]:
    return {"total_count": 0, "buckets": []}


def _record_unexpected_frame_result(results: dict[str, Any], failure: dict[str, Any]) -> None:
    """Aggregate repeated frame failures without allowing raw PCM to bloat evidence."""
    attempted = failure["attempted"]
    failed_attempt = attempted[-1]
    failed_frame = _frame_payload_evidence(failed_attempt["payload"])
    failed_response = _frame_response_evidence(failed_attempt["response"])
    key = (failed_response["http_status"], failed_response["error_code"], failed_frame["lane"])
    buckets = results["buckets"]
    bucket = next(
        (
            candidate
            for candidate in buckets
            if (candidate["http_status"], candidate["error_code"], candidate["lane"]) == key
        ),
        None,
    )
    if bucket is None:
        bucket = {
            "http_status": key[0],
            "error_code": key[1],
            "lane": key[2],
            "count": 0,
            "first_exemplars": [],
            "last_exemplars": [],
        }
        buckets.append(bucket)
    exemplar = {
        "session_id": failure["session_id"],
        "sequence": failure["sequence"],
        "attempted": [
            {
                "frame": _frame_payload_evidence(attempt["payload"]),
                "response": _frame_response_evidence(attempt["response"]),
            }
            for attempt in attempted
        ],
    }
    results["total_count"] += 1
    bucket["count"] += 1
    if len(bucket["first_exemplars"]) < _UNEXPECTED_FRAME_EXEMPLARS_PER_BUCKET:
        bucket["first_exemplars"].append(exemplar)
    bucket["last_exemplars"].append(exemplar)
    del bucket["last_exemplars"][:-_UNEXPECTED_FRAME_EXEMPLARS_PER_BUCKET]


@dataclass
class SessionRun:
    session_id: str
    capture_bearer: str = field(repr=False)
    view_bearer: str = field(repr=False)
    fixture_id: str = ""
    expected_marker: str = ""
    pcm: bytes = field(repr=False, default=b"")
    sequence: int = 0
    event_cursor: int = 0
    snapshot_version: int = 0
    frame_end_wall_ns: dict[int, int] = field(default_factory=dict)
    frames: list[dict[str, Any]] = field(default_factory=list)
    heartbeats: list[dict[str, Any]] = field(default_factory=list)
    rss_samples: list[dict[str, Any]] = field(default_factory=list)
    observer: dict[str, Any] = field(
        default_factory=lambda: {"events": [], "snapshots": [], "latency_seconds": [], "text": {}}
    )
    reconnects: list[dict[str, Any]] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "fixture_id": self.fixture_id,
            "expected_marker": self.expected_marker,
            "next_sequence": self.sequence,
            "frame_end_wall_ns": self.frame_end_wall_ns,
            "frames": self.frames,
            "heartbeats": self.heartbeats,
            "rss_samples": self.rss_samples,
            "observer": self.observer,
            "reconnects": self.reconnects,
        }


class Measurement:
    def __init__(self, args: argparse.Namespace, contract: dict[str, Any], fixture: dict[str, Any]):
        self.args = args
        self.contract = contract
        self.fixture = fixture
        self.output = args.output
        self.state_path = self.output / "run-state.json"
        self.event_log = self.output / "canonical-processed.jsonl"
        self.service_log = self.output / "service.log"
        self.service: subprocess.Popen[bytes] | None = None
        self.base_url = f"http://127.0.0.1:{args.port}"
        self.local_descriptor: dict[str, Any] | None = None
        self.deployed_descriptor: dict[str, Any] | None = None
        self.rss_warm_idle: int | None = None
        self.phases: list[dict[str, Any]] = []
        self.active: dict[str, SessionRun] = {}
        self.started_wall_ns = time.time_ns()

    def state(self, *, terminal: str | None = None, error: str | None = None) -> dict[str, Any]:
        return {
            "schema": "moss-cpu-hf-local-concurrency-measurement.v1",
            "contract_sha256": _sha256(CONTRACT_PATH),
            "fixture_sha256": _sha256(FIXTURE_PATH),
            "latency_label": self.contract["scope"]["latency_label"],
            "required_negative_statement": self.contract["evidence_requirements"][
                "required_negative_statement"
            ],
            "started_wall_ns": self.started_wall_ns,
            "updated_wall_ns": time.time_ns(),
            "head_revision": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "deployed_descriptor": self.deployed_descriptor,
            "local_descriptor": self.local_descriptor,
            "warm_idle_process_tree_rss_bytes": self.rss_warm_idle,
            "phases": self.phases,
            "active_sessions": {key: session.public() for key, session in self.active.items()},
            "terminal": terminal,
            "error": error,
        }

    def persist(self, *, terminal: str | None = None, error: str | None = None) -> None:
        _atomic_json(self.state_path, self.state(terminal=terminal, error=error))

    def preflight(self) -> dict[str, Any]:
        if self.contract["run_started"] is not False:
            raise MeasurementError("contract says a measurement already started; refuse to overwrite it")
        if self.contract["production_path"]["stub_results_qualify"] is not False:
            raise MeasurementError("contract must reject stub results")
        if not self.args.model.is_dir():
            raise MeasurementError(f"model directory is absent: {self.args.model}")
        for required in (self.args.model / "config.json", self.args.manifest, self.args.provisional_manifest):
            if not required.is_file():
                raise MeasurementError(f"required local input is absent: {required}")
        fixture_audio = ROOT / self.fixture["audio"]["path"]
        _wav_clip(self.fixture, self.fixture["clips"][0])
        _wav_clip(self.fixture, self.fixture["clips"][1])
        response = _request_json(
            self.args.deployed_descriptor_url,
            insecure_tls=self.args.deployed_descriptor_url.startswith("https://"),
        )
        if response["status"] != 200 or not isinstance(response["json"], dict):
            raise MeasurementError("read-only deployed descriptor did not return HTTP 200 JSON")
        descriptor = response["json"].get("descriptor")
        if not isinstance(descriptor, dict):
            raise MeasurementError("deployed descriptor response has no descriptor object")
        self.deployed_descriptor = descriptor
        source_revision = _read_json(self.args.manifest).get("source_revision")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        result = {
            "preflight": "PASS",
            "contract_sha256": _sha256(CONTRACT_PATH),
            "fixture_path": str(fixture_audio.relative_to(ROOT)),
            "fixture_sha256": _sha256(fixture_audio),
            "fixture_clip_ids": [clip["id"] for clip in self.fixture["clips"]],
            "deployed_bound_fields": _descriptor_fields(descriptor),
            "manifest_source_revision_before_run": source_revision,
            "head_revision": head,
            "manifest_will_be_refinalized_before_run": source_revision != head,
            "gpu_claims_permitted": False,
        }
        self.persist(terminal="preflight", error=None)
        _atomic_json(self.output / "preflight.json", result)
        return result

    def finalize_manifest(self) -> None:
        if self.deployed_descriptor is None:
            raise MeasurementError("fetch the deployed descriptor before finalizing a local manifest")
        deployed = _descriptor_fields(self.deployed_descriptor)
        provisional = _read_json(self.args.provisional_manifest)
        identity = provisional.get("identity_config")
        provider = provisional.get("identity_provider")
        if not isinstance(identity, dict) or not isinstance(provider, dict):
            raise MeasurementError("provisional manifest lacks the calibrated identity configuration")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        backup = self.output / "manifest-before-refinalization.json"
        backup.write_bytes(self.args.manifest.read_bytes())
        command = [
            str(FINALIZER_PATH),
            "--input", str(self.args.provisional_manifest),
            "--output", str(self.args.manifest),
            "--source-revision", head,
            "--hard-cap-samples", str(deployed["hard_cap_samples"]),
            "--max-retained-samples", str(deployed["max_retained_samples"]),
            "--frame-samples", str(deployed["frame_samples"]),
            "--min-match-score", str(identity["min_match_score"]),
            "--min-match-margin", str(identity["min_match_margin"]),
            "--album-admission-seconds", str(provider["album_admission_seconds"]),
            "--birth-min-seconds", str(provider["birth_min_seconds"]),
        ]
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
        (self.output / "manifest-finalization.txt").write_text(
            "$ " + " ".join(command) + "\n" + completed.stdout + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise MeasurementError("local manifest finalization failed")
        finalized = _read_json(self.args.manifest)
        if finalized.get("source_revision") != head:
            raise MeasurementError("finalizer did not bind the local manifest to the current checkout")

    def start_service(self) -> str:
        if self.deployed_descriptor is None:
            raise MeasurementError("preflight must run before service start")
        self.event_log.write_text("", encoding="utf-8")
        log_handle = self.service_log.open("wb")
        command = [
            sys.executable,
            str(SERVER_PATH),
            "--model", str(self.args.model),
            "--live-provider-manifest", str(self.args.manifest),
            "--canonical-event-log", str(self.event_log),
            "--port", str(self.args.port),
        ]
        self.service = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.monotonic() + self.args.startup_timeout_seconds
        while time.monotonic() < deadline:
            if self.service.poll() is not None:
                raise MeasurementError("local service exited during startup; see service.log")
            try:
                response = _request_json(f"{self.base_url}/api/live/descriptor", timeout_seconds=2.0)
            except MeasurementError:
                time.sleep(0.2)
                continue
            if response["status"] == 200 and isinstance(response["json"], dict):
                descriptor = response["json"].get("descriptor")
                if isinstance(descriptor, dict):
                    self.local_descriptor = descriptor
                    break
            time.sleep(0.2)
        if self.local_descriptor is None:
            raise MeasurementError("local service did not expose its descriptor before the startup deadline")
        if _descriptor_fields(self.local_descriptor) != _descriptor_fields(self.deployed_descriptor):
            raise MeasurementError("local and read-only deployed descriptor bounds differ; refuse capture")
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if self.local_descriptor.get("source_revision") != head:
            raise MeasurementError("local descriptor source_revision is not the current checkout")
        bootstrap = _request_json(f"{self.base_url}/prototype/bootstrap")
        if bootstrap["status"] != 200 or not isinstance(bootstrap["json"], dict):
            raise MeasurementError("local measurement bootstrap did not provide capture authority")
        bearer = bootstrap["json"].get("capture_bearer")
        if not isinstance(bearer, str) or not bearer:
            raise MeasurementError("local measurement capture authority is absent")
        self.rss_warm_idle = _process_tree_rss_bytes(self.service.pid)
        self.persist()
        return bearer

    def create_session(self, *, bearer: str, clip: dict[str, Any]) -> SessionRun:
        response = _request_json(
            f"{self.base_url}/api/live/sessions",
            method="POST",
            payload={"echo_mode": "headphones"},
            bearer=bearer,
        )
        payload = response["json"]
        if response["status"] != 200 or not isinstance(payload, dict):
            raise MeasurementError(f"session creation failed with HTTP {response['status']}")
        session_id, view = payload.get("id"), payload.get("view_token")
        if not isinstance(session_id, str) or not isinstance(view, str):
            raise MeasurementError("session creation response lacks session authority")
        return SessionRun(
            session_id=session_id,
            capture_bearer=bearer,
            view_bearer=view,
            fixture_id=str(clip["id"]),
            expected_marker=str(clip["expected_marker"]),
            pcm=_wav_clip(self.fixture, clip),
        )

    def heartbeat(self, session: SessionRun) -> None:
        sequence = len(session.heartbeats)
        payload = {
            "schema": "moss-live-helper-health.v1",
            "instance_id": f"w2-{session.session_id}",
            "sequence": sequence,
            "sent_monotonic_ns": time.monotonic_ns(),
            "helper_version": "cpu-hf-local-concurrency-v1",
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
        response = _request_json(
            f"{self.base_url}/api/live/sessions/{urllib.parse.quote(session.session_id)}/heartbeat",
            method="POST",
            payload=payload,
            bearer=session.capture_bearer,
        )
        session.heartbeats.append({"sequence": sequence, "status": response["status"], "wall_ns": time.time_ns()})

    def frame_payload(self, session: SessionRun, lane: str, sequence: int) -> dict[str, Any]:
        if self.local_descriptor is None:
            raise MeasurementError("local descriptor unavailable")
        frame_samples = int(self.local_descriptor["frame_samples"])
        pcm = _wrapped_frame(session.pcm, sequence=sequence, frame_samples=frame_samples)
        return {
            "lane": lane,
            "sequence": sequence,
            "capture_timestamp_ns": self.started_wall_ns + sequence * frame_samples * 1_000_000_000 // int(self.local_descriptor["sample_rate"]),
            "device_epoch": 1,
            "silent": not any(pcm),
            "discontinuity": False,
            "sample_rate": self.local_descriptor["sample_rate"],
            "sample_count": frame_samples,
            "pcm_base64": base64.b64encode(pcm).decode("ascii"),
        }

    def post_frame(self, session: SessionRun, payload: dict[str, Any]) -> dict[str, Any]:
        response = _request_json(
            f"{self.base_url}/api/live/sessions/{urllib.parse.quote(session.session_id)}/frames",
            method="POST",
            payload=payload,
            bearer=session.capture_bearer,
        )
        detail = None
        if isinstance(response["json"], dict):
            detail = response["json"].get("detail")
        record = {
            "lane": payload["lane"],
            "sequence": payload["sequence"],
            "status": response["status"],
            "detail": detail,
            "wall_ns": time.time_ns(),
        }
        session.frames.append(record)
        return {"response": response, "record": record}

    def send_pair(self, session: SessionRun) -> tuple[bool, dict[str, Any] | None]:
        sequence = session.sequence
        attempted: list[dict[str, Any]] = []
        for lane in ("microphone", "system"):
            payload = self.frame_payload(session, lane, sequence)
            outcome = self.post_frame(session, payload)
            attempted.append({"payload": payload, **outcome})
            if outcome["response"]["status"] != 200:
                return False, {"session_id": session.session_id, "sequence": sequence, "attempted": attempted}
        assert self.local_descriptor is not None
        end_sample = (sequence + 1) * int(self.local_descriptor["frame_samples"])
        session.frame_end_wall_ns[end_sample] = time.time_ns()
        session.sequence += 1
        return True, None

    def poll(self, session: SessionRun) -> None:
        quoted = urllib.parse.quote(session.session_id)
        snapshot = _request_json(
            f"{self.base_url}/api/live/sessions/{quoted}/snapshot?since_version={session.snapshot_version}",
            bearer=session.view_bearer,
        )
        events = _request_json(
            f"{self.base_url}/api/live/sessions/{quoted}/events?since_seq={session.event_cursor}",
            bearer=session.view_bearer,
        )
        observed_ns = time.time_ns()
        snapshot_record = {"status": snapshot["status"], "requested_since_version": session.snapshot_version, "wall_ns": observed_ns}
        if snapshot["status"] == 200 and isinstance(snapshot["json"], dict):
            current = snapshot["json"].get("snapshot")
            if isinstance(current, dict):
                current_session = current.get("session")
                if isinstance(current_session, dict):
                    version = current_session.get("version")
                    if isinstance(version, int):
                        session.snapshot_version = version
                    commits = current_session.get("committed")
                    if isinstance(commits, list):
                        snapshot_record["committed_span_ids"] = []
                        snapshot_record["pending_work_items"] = current.get("pending_work_items")
                        for commit in commits:
                            if not isinstance(commit, dict) or not isinstance(commit.get("span_id"), int):
                                continue
                            span_id = commit["span_id"]
                            text = commit.get("revised_transcript") or commit.get("transcript")
                            if isinstance(text, str):
                                session.observer["text"][str(span_id)] = text
                            snapshot_record["committed_span_ids"].append(span_id)
        session.observer["snapshots"].append(snapshot_record)
        event_record = {"status": events["status"], "requested_since_seq": session.event_cursor, "wall_ns": observed_ns}
        if events["status"] == 200 and isinstance(events["json"], dict):
            delivered = events["json"].get("events")
            if isinstance(delivered, list):
                event_record["events"] = delivered
                for event in delivered:
                    if not isinstance(event, dict) or not isinstance(event.get("seq"), int):
                        continue
                    session.event_cursor = max(session.event_cursor, event["seq"])
                    if event.get("kind") == "canonical_processed":
                        payload = event.get("payload")
                        if isinstance(payload, dict) and payload.get("submitted"):
                            committed = payload.get("committed_samples")
                            origin = session.frame_end_wall_ns.get(committed)
                            if isinstance(origin, int):
                                session.observer["latency_seconds"].append((observed_ns - origin) / 1_000_000_000)
        session.observer["events"].append(event_record)
        if self.service is not None:
            session.rss_samples.append({"wall_ns": observed_ns, "bytes": _process_tree_rss_bytes(self.service.pid)})

    def reconnect_observer(self, session: SessionRun) -> None:
        session.reconnects.append(
            {
                "prior_snapshot_version": session.snapshot_version,
                "prior_event_cursor": session.event_cursor,
                "wall_ns": time.time_ns(),
            }
        )
        self.poll(session)

    def stop(self, session: SessionRun) -> dict[str, Any]:
        response = _request_json(
            f"{self.base_url}/api/live/sessions/{urllib.parse.quote(session.session_id)}/stop",
            method="POST",
            payload={"deadline": self.args.stop_deadline_seconds},
            bearer=session.capture_bearer,
            timeout_seconds=self.args.stop_deadline_seconds + 15,
        )
        return {"session_id": session.session_id, "status": response["status"], "body": response["json"]}

    def instrumentation_overhead(self) -> dict[str, Any]:
        response = _request_json(f"{self.base_url}/prototype/measurement-instrumentation")
        if response["status"] != 200 or not isinstance(response["json"], dict):
            return {"status": response["status"], "available": False}
        return {"status": response["status"], "available": True, **response["json"]}

    def _canonical_lifecycle_events(self, session_ids: set[str]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        if not self.event_log.is_file():
            return events
        for line in self.event_log.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event.get("session_id") in session_ids:
                events.append(event)
        return events

    def run_normal_phase(self, *, name: str, session_count: int, duration_seconds: int) -> dict[str, Any]:
        bearer = self.capture_bearer
        clips = self.fixture["clips"]
        sessions = [self.create_session(bearer=bearer, clip=clips[index % len(clips)]) for index in range(session_count)]
        self.active = {session.session_id: session for session in sessions}
        phase: dict[str, Any] = {
            "name": name,
            "kind": "normal",
            "session_count": session_count,
            "duration_seconds": duration_seconds,
            "sessions": [session.session_id for session in sessions],
            "started_wall_ns": time.time_ns(),
            "unexpected_frame_results": _new_unexpected_frame_results(),
        }
        deadline = time.monotonic() + duration_seconds
        tick = time.monotonic()
        reconnect_done = False
        while time.monotonic() < deadline:
            for session in sessions:
                self.heartbeat(session)
                accepted, failure = self.send_pair(session)
                if not accepted and failure is not None:
                    _record_unexpected_frame_result(phase["unexpected_frame_results"], failure)
            for session in sessions:
                self.poll(session)
            if not reconnect_done and time.monotonic() >= deadline - duration_seconds / 2:
                for session in sessions:
                    self.reconnect_observer(session)
                reconnect_done = True
            self.persist()
            tick += self.contract["production_path"]["ingress_cadence_seconds"]
            time.sleep(max(0.0, tick - time.monotonic()))
        for session in sessions:
            self.poll(session)
        phase["stops"] = [self.stop(session) for session in sessions]
        phase["canonical_event_log_instrumentation"] = self.instrumentation_overhead()
        phase["ended_wall_ns"] = time.time_ns()
        phase["evaluation"] = self.evaluate_normal_phase(phase, sessions)
        self.phases.append(phase)
        self.persist()
        self.active = {}
        return phase

    def evaluate_normal_phase(self, phase: dict[str, Any], sessions: list[SessionRun]) -> dict[str, Any]:
        latency_gate = self.contract["gates"]["latency"]["maximum_per_session_p95_transcript_lag_seconds"]
        memory_gate = self.contract["gates"]["memory"]["maximum_process_tree_rss_increase_bytes_over_warm_idle"]
        session_ids = {session.session_id for session in sessions}
        lifecycle = self._canonical_lifecycle_events(session_ids)
        dispatch = [
            event
            for event in lifecycle
            if event.get("kind") == "canonical_processed"
            and isinstance(event.get("payload"), dict)
            and event["payload"].get("submitted")
        ]
        counts = {session.session_id: 0 for session in sessions}
        completed_prefix_skew = 0
        for event in dispatch:
            counts[event["session_id"]] += 1
            completed_prefix_skew = max(completed_prefix_skew, max(counts.values()) - min(counts.values()))
        fairness_gate = self.contract["gates"]["fairness"][
            "maximum_dispatch_count_skew_for_continuously_ready_sessions"
        ]
        fairness = _canonical_lifecycle_fairness(
            lifecycle,
            session_ids,
            maximum_skew=fairness_gate,
        )
        marker_checks: dict[str, dict[str, bool]] = {}
        per_session_latency: dict[str, dict[str, float | int | None]] = {}
        rss: list[int] = []
        for session in sessions:
            text = "\n".join(session.observer["text"].values()).casefold()
            own = session.expected_marker.casefold()
            foreign = [other.expected_marker.casefold() for other in sessions if other.session_id != session.session_id]
            marker_checks[session.session_id] = {
                "own_marker_present": own in text,
                "foreign_markers_absent": all(marker not in text for marker in foreign),
                "observer_reconnected": bool(session.reconnects),
            }
            samples = session.observer["latency_seconds"]
            per_session_latency[session.session_id] = {
                "count": len(samples),
                "p50": _type7(samples, 0.5),
                "p95": _type7(samples, 0.95),
                "max": max(samples) if samples else None,
            }
            rss.extend(sample["bytes"] for sample in session.rss_samples)
        p95s = [entry["p95"] for entry in per_session_latency.values() if isinstance(entry["p95"], float)]
        max_p95 = max(p95s) if p95s else None
        decode_rtfs = [
            event["payload"]["canonical_decode_rtf"]
            for event in dispatch
            if isinstance(event.get("payload"), dict)
            and isinstance(event["payload"].get("canonical_decode_rtf"), (int, float))
        ]
        max_rss = max(rss) if rss else None
        rss_growth = None if max_rss is None or self.rss_warm_idle is None else max_rss - self.rss_warm_idle
        log_text = self.service_log.read_text(encoding="utf-8", errors="replace").casefold() if self.service_log.exists() else ""
        oom_count = sum(log_text.count(token) for token in ("out of memory", "oom", "accelerator error"))
        stops_closed = all(stop["status"] == 200 for stop in phase["stops"])
        return {
            "latency_label": self.contract["scope"]["latency_label"],
            "per_session_latency_seconds": per_session_latency,
            "maximum_session_p95_seconds": max_p95,
            "latency_gate_seconds": latency_gate,
            "maximum_session_p95_passes": max_p95 is not None and max_p95 <= latency_gate,
            "prior_two_session_cpu_p95_seconds": 0.248,
            "local_cpu_hf_decode_real_time_factor": {
                "count": len(decode_rtfs),
                "p50": _type7(decode_rtfs, 0.5),
                "p95": _type7(decode_rtfs, 0.95),
                "max": max(decode_rtfs) if decode_rtfs else None,
            },
            "marker_checks": marker_checks,
            "dispatch_order": [event["session_id"] for event in dispatch],
            "dispatch_counts": counts,
            "completed_dispatch_prefix_skew_diagnostic": completed_prefix_skew,
            "canonical_lifecycle_fairness": fairness,
            "rss_warm_idle_bytes": self.rss_warm_idle,
            "maximum_process_tree_rss_bytes": max_rss,
            "rss_growth_bytes": rss_growth,
            "rss_growth_gate_bytes": memory_gate,
            "oom_or_accelerator_error_count": oom_count,
            "stops_closed": stops_closed,
            "passes": (
                max_p95 is not None
                and max_p95 <= latency_gate
                and fairness["passes"]
                and rss_growth is not None
                and rss_growth <= memory_gate
                and oom_count == 0
                and stops_closed
                and phase["unexpected_frame_results"]["total_count"] == 0
                and all(all(check.values()) for check in marker_checks.values())
            ),
        }

    def run_overload_phase(self) -> dict[str, Any]:
        bearer = self.capture_bearer
        saturated = self.create_session(bearer=bearer, clip=self.fixture["clips"][0])
        peer = self.create_session(bearer=bearer, clip=self.fixture["clips"][1])
        self.active = {saturated.session_id: saturated, peer.session_id: peer}
        self.heartbeat(saturated)
        self.heartbeat(peer)
        assert self.local_descriptor is not None
        bounds = _descriptor_fields(self.local_descriptor)
        frames_per_span = math.ceil(bounds["hard_cap_samples"] / bounds["frame_samples"])
        maximum_pairs = bounds["max_queue_depth"] * frames_per_span * 2 + frames_per_span
        refusal: dict[str, Any] | None = None
        for _ in range(maximum_pairs):
            accepted, failed = self.send_pair(saturated)
            if not accepted:
                refusal = failed
                break
        if refusal is None:
            raise MeasurementError("overload did not reach a v2 refusal inside the descriptor-derived limit")
        peer_accepted, peer_failure = self.send_pair(peer)
        refused = refusal["attempted"][-1]
        retry_statuses: list[int] = []
        retry_payload = refused["payload"]
        retry_response: dict[str, Any] | None = None
        deadline = time.monotonic() + self.args.overload_retry_timeout_seconds
        while time.monotonic() < deadline:
            self.heartbeat(saturated)
            self.heartbeat(peer)
            self.poll(saturated)
            self.poll(peer)
            retry_response = self.post_frame(saturated, retry_payload)["response"]
            retry_statuses.append(retry_response["status"])
            if retry_response["status"] == 200:
                break
            time.sleep(0.25)
        for session in (saturated, peer):
            self.poll(session)
        phase = {
            "name": "overload",
            "kind": "overload",
            "sessions": [saturated.session_id, peer.session_id],
            "refusal": {"lane": retry_payload["lane"], "sequence": retry_payload["sequence"], "status": refused["response"]["status"]},
            "peer_accepted": peer_accepted,
            "peer_failure": peer_failure,
            "retry_statuses": retry_statuses,
            "stops": [self.stop(session) for session in (saturated, peer)],
            "canonical_event_log_instrumentation": self.instrumentation_overhead(),
        }
        saturated_frames = [record for record in saturated.frames if record["status"] == 429]
        phase["evaluation"] = {
            "retryable_v2_429_observed": bool(saturated_frames),
            "peer_accepted_while_saturated": peer_accepted,
            "refused_frame_retried_successfully": retry_response is not None and retry_response["status"] == 200,
            "saturated_session_stop_closed": phase["stops"][0]["status"] == 200,
            "peer_session_stop_closed": phase["stops"][1]["status"] == 200,
        }
        phase["evaluation"]["passes"] = all(phase["evaluation"].values())
        self.phases.append(phase)
        self.persist()
        self.active = {}
        return phase

    @property
    def capture_bearer(self) -> str:
        if not hasattr(self, "_capture_bearer"):
            raise MeasurementError("local capture authority is unavailable")
        return self._capture_bearer

    def run(self) -> dict[str, Any]:
        self.preflight()
        self.finalize_manifest()
        self._capture_bearer = self.start_service()
        matrix = self.contract["matrix"]
        screens = [
            self.run_normal_phase(
                name=f"screen-{count}",
                session_count=count,
                duration_seconds=matrix["screening_measurement_seconds"],
            )
            for count in matrix["screening_session_counts"]
        ]
        passing = [phase for phase in screens if phase["evaluation"]["passes"]]
        soak = None
        if passing:
            chosen = max(phase["session_count"] for phase in passing)
            soak = self.run_normal_phase(
                name="chosen-bound-soak",
                session_count=chosen,
                duration_seconds=matrix["chosen_bound_soak_seconds"],
            )
        overload = self.run_overload_phase()
        verdict = {
            "chosen_normal_session_bound": None if not passing else max(phase["session_count"] for phase in passing),
            "screening_passes": [phase["session_count"] for phase in passing],
            "soak_passes": soak is not None and soak["evaluation"]["passes"],
            "overload_passes": overload["evaluation"]["passes"],
            "qualifies_local_g4_g5_portions": bool(passing) and soak is not None and soak["evaluation"]["passes"] and overload["evaluation"]["passes"],
            "does_not_establish": self.contract["scope"]["does_not_establish"],
        }
        self.phases.append({"name": "verdict", "kind": "verdict", "value": verdict})
        self.persist(terminal="completed")
        _atomic_json(self.output / "verdict.json", verdict)
        return verdict

    def cleanup(self) -> None:
        if self.service is None or self.service.poll() is not None:
            return
        os.killpg(self.service.pid, signal.SIGTERM)
        try:
            self.service.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(self.service.pid, signal.SIGKILL)
            self.service.wait(timeout=10)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provisional-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployed-descriptor-url", default=DEFAULT_DEPLOYED_DESCRIPTOR_URL)
    parser.add_argument("--port", type=int, default=8899)
    parser.add_argument("--startup-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--stop-deadline-seconds", type=float, default=90.0)
    parser.add_argument("--overload-retry-timeout-seconds", type=float, default=90.0)
    parser.add_argument("--preflight", action="store_true", help="verify all immutable inputs without starting a service")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    contract = _read_json(CONTRACT_PATH)
    fixture = _read_json(FIXTURE_PATH)
    measurement = Measurement(args, contract, fixture)
    try:
        if args.preflight:
            print(json.dumps(measurement.preflight(), indent=2, sort_keys=True))
            return
        print(json.dumps(measurement.run(), indent=2, sort_keys=True))
    except MeasurementError as error:
        measurement.persist(terminal="blocked-or-failed", error=str(error))
        raise SystemExit(f"MEASUREMENT REFUSED: {error}") from error
    finally:
        measurement.cleanup()


if __name__ == "__main__":
    main()
