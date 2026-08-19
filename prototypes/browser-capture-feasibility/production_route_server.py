#!/usr/bin/env python3
"""PROTOTYPE: run the browser harness through the real local live HTTP routes.

Question: can real Chrome create a production live session, admit exact v2
two-lane frames, and poll/render its production snapshot and event streams with
render-then-advance cursors, including through a manifest-admitted real model?

Run: PYTHONDONTWRITEBYTECODE=1 python3 \
  prototypes/browser-capture-feasibility/production_route_server.py
Then open http://127.0.0.1:8899/capture-harness?autostart=1 in Chrome.

By default the provider is deterministic and does not run a model. Pass both
``--model`` and ``--live-provider-manifest`` to exercise the production ModelRunner
through the manifest-admitted live provider bundle instead. Alternatively, pass
``--vllm-base-url``, ``--vllm-model``, and ``--live-provider-manifest`` to exercise
the same bundle through the production remote VllmRunner. The latter keeps model
execution on the read-only provider host while this process owns the live routes.
The ephemeral capture credential is available only from a loopback prototype route
and is never printed or persisted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import os
import queue
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PORT = 8899
LIVE_HELPER_LEASE_SECONDS = 2.0
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.app.live_auth import LiveAccessRegistry, LivePeer
from moss_transcribe_diarize.app.live_session import ProvisionalSuffix
from moss_transcribe_diarize.app.server import create_app
from starlette.requests import Request


class _ReadPathFixtureRuntime:
    """Expose one labelled provisional tail through the real snapshot route.

    The deterministic test runtime produces canonical commits but has no provisional
    inference scheduler. This wrapper changes only snapshot presentation so Chrome can
    measure the T-02 merge branch without pretending it came from model inference.
    """

    def __init__(self, runtime):
        self._runtime = runtime

    def __getattr__(self, name):
        return getattr(self._runtime, name)

    def snapshot(self, session_id: str, since_version: int | None = None):
        snapshot = self._runtime.snapshot(session_id, since_version=since_version)
        if snapshot is None or not snapshot.session.committed:
            return snapshot
        session = replace(
            snapshot.session,
            provisional=ProvisionalSuffix(
                generation=1,
                start_sample=snapshot.session.committed_samples,
                end_sample=snapshot.session.accepted_samples,
                transcript="[0][S02]synthetic provisional tail[0.25]",
            ),
        )
        return replace(snapshot, session=session)


def _test_live_api_module():
    path = REPO_ROOT / "tests" / "test_live_api.py"
    spec = importlib.util.spec_from_file_location("prototype_test_live_api", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load deterministic runtime helpers from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def _visibility_cadence(records: list[dict], visibility: str, *, time_key: str) -> dict:
    selected = [record for record in records if record.get("client_visibility") == visibility]
    adjacent_deltas = [
        right[time_key] - left[time_key]
        for left, right in zip(records, records[1:])
        if left.get("client_visibility") == visibility
        and right.get("client_visibility") == visibility
    ]
    return {
        "count": len(selected),
        "duration_ms": sum(adjacent_deltas),
        "delta_ms": {
            "p50": _percentile(adjacent_deltas, 0.50),
            "p95": _percentile(adjacent_deltas, 0.95),
            "max": max(adjacent_deltas) if adjacent_deltas else None,
        },
    }


class _CanonicalEventLogDrain:
    """Acknowledge that every earlier event is durable without closing the writer."""

    def __init__(self):
        self.completed = threading.Event()


class _CanonicalEventLogWriter:
    """Append raw measurement events off the canonical runtime publication path."""

    _FSYNC_INTERVAL_SECONDS = 5.0

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        self._handle = path.open("a", encoding="utf-8")
        self._queue: queue.Queue[object] = queue.Queue()
        self._stats_lock = threading.Lock()
        self._closed = False
        self._enqueued = 0
        self._enqueue_elapsed_ns = 0
        self._write_elapsed_ns = 0
        self._fsync_elapsed_ns = 0
        self._fsync_count = 0
        self._max_queue_depth = 0
        self._writer = threading.Thread(target=self._run, name="canonical-event-log", daemon=True)
        self._writer.start()

    def append(self, record: dict) -> None:
        """Serialize cheaply in the caller, then leave file I/O to the writer thread."""
        started = time.perf_counter_ns()
        serialized = json.dumps(record, sort_keys=True) + "\n"
        self._queue.put(serialized)
        elapsed = time.perf_counter_ns() - started
        with self._stats_lock:
            self._enqueued += 1
            self._enqueue_elapsed_ns += elapsed
            self._max_queue_depth = max(self._max_queue_depth, self._queue.qsize())

    def _sync(self) -> None:
        started = time.perf_counter_ns()
        self._handle.flush()
        os.fsync(self._handle.fileno())
        elapsed = time.perf_counter_ns() - started
        with self._stats_lock:
            self._fsync_elapsed_ns += elapsed
            self._fsync_count += 1

    def _run(self) -> None:
        last_sync = time.monotonic()
        while True:
            item = self._queue.get()
            if item is None:
                break
            if isinstance(item, _CanonicalEventLogDrain):
                # Queue ordering makes all earlier events durable before the
                # evaluator is allowed to read. Keep the writer alive so later
                # measurement phases can append to the same log.
                self._sync()
                item.completed.set()
                last_sync = time.monotonic()
                continue
            if not isinstance(item, str):
                raise RuntimeError(f"unsupported canonical event-log item {item!r}")
            started = time.perf_counter_ns()
            self._handle.write(item)
            elapsed = time.perf_counter_ns() - started
            with self._stats_lock:
                self._write_elapsed_ns += elapsed
            if time.monotonic() - last_sync >= self._FSYNC_INTERVAL_SECONDS:
                self._sync()
                last_sync = time.monotonic()
        self._sync()
        self._handle.close()

    def stats(self) -> dict:
        with self._stats_lock:
            return {
                "schema": "moss-canonical-event-log-overhead.v1",
                "event_count": self._enqueued,
                "enqueue_elapsed_ns": self._enqueue_elapsed_ns,
                "write_elapsed_ns": self._write_elapsed_ns,
                "fsync_elapsed_ns": self._fsync_elapsed_ns,
                "fsync_count": self._fsync_count,
                "max_pending_writer_records": self._max_queue_depth,
                "fsync_interval_seconds": self._FSYNC_INTERVAL_SECONDS,
            }

    def drain(self, *, timeout_seconds: float) -> bool:
        """Wait for a writer-owned durable boundary without accepting partial reads."""
        if timeout_seconds <= 0:
            raise ValueError("canonical event-log drain timeout must be positive")
        if self._closed or not self._writer.is_alive():
            return False
        barrier = _CanonicalEventLogDrain()
        self._queue.put(barrier)
        return barrier.completed.wait(timeout_seconds)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._queue.put(None)
        self._writer.join()


def _instrument_commit_times(
    runtime,
    commit_wall_ns: dict[tuple[str, int], int],
    lock: threading.Lock,
    *,
    event_log: _CanonicalEventLogWriter | None = None,
):
    """Timestamp publication and retain the complete canonical scheduling lifecycle.

    ``canonical_processed`` alone cannot establish the preregistered fairness
    predicate: sessions may legitimately emit different numbers of spans as VAD
    closes them. The measurement log therefore records queue, dispatch-start,
    and publication events in runtime order. The writer remains off the
    publication path; it receives one compact metadata record after the runtime
    has recorded its own event.
    """
    record_event = runtime._record_event

    def measured_record_event(state, kind, payload):
        record_event(state, kind, payload)
        record = None
        with lock:
            if kind == "canonical_processed" and payload.get("submitted"):
                commit_wall_ns.setdefault(
                    (state.session_id, int(payload["span_id"])),
                    time.time_ns(),
                )
            if event_log is not None and kind in {
                "canonical_queued",
                "canonical_started",
                "canonical_processed",
            }:
                measured_payload = dict(payload)
                if kind == "canonical_processed" and payload.get("submitted"):
                    session = getattr(state, "session", None)
                    snapshot = session.snapshot() if session is not None else None
                    span_id = payload.get("span_id")
                    for commit in getattr(snapshot, "committed", ()):
                        if getattr(commit, "span_id", None) != span_id:
                            continue
                        transcript = getattr(commit, "revised_transcript", None) or getattr(
                            commit, "transcript", None
                        )
                        if isinstance(transcript, str):
                            measured_payload["rendered_transcript"] = transcript
                        break
                record = {
                    "schema": "moss-live-canonical-dispatch-observation.v2",
                    "observed_wall_ns": time.time_ns(),
                    "session_id": state.session_id,
                    "kind": kind,
                    "payload": measured_payload,
                }
        if record is not None:
            event_log.append(record)

    runtime._record_event = measured_record_event
    return runtime


def _commit_to_render_summary(
    session_id: str,
    telemetry: dict,
    commit_wall_ns: dict[tuple[str, int], int],
) -> dict:
    first_render_ms: dict[int, int] = {}
    queue_depths: list[int] = []
    for render in telemetry["renders"]:
        if render.get("session_id") != session_id or render.get("outcome") != "rendered":
            continue
        rendered_wall_ms = render.get("rendered_wall_ms")
        if not isinstance(rendered_wall_ms, int):
            continue
        for span_id in render.get("committed_span_ids", []):
            if isinstance(span_id, int):
                first_render_ms.setdefault(span_id, rendered_wall_ms)
        pending = render.get("pending_work_items")
        if isinstance(pending, int):
            queue_depths.append(pending)
    raw = []
    for (committed_session_id, span_id), committed_ns in commit_wall_ns.items():
        if committed_session_id != session_id or span_id not in first_render_ms:
            continue
        raw.append(
            {
                "span_id": span_id,
                "committed_wall_ns": committed_ns,
                "first_rendered_wall_ms": first_render_ms[span_id],
                "latency_ms": max(0, first_render_ms[span_id] - committed_ns // 1_000_000),
            }
        )
    latencies = [record["latency_ms"] for record in raw]
    return {
        "count": len(raw),
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
        "max_ms": max(latencies) if latencies else None,
        "max_observed_pending_work_items": max(queue_depths) if queue_depths else None,
        "raw": sorted(raw, key=lambda record: record["span_id"]),
    }


def build_app(
    *,
    model_path: Path | str | None = None,
    live_provider_manifest: Path | None = None,
    vllm_base_url: str | None = None,
    vllm_model: str | None = None,
    vllm_timeout_seconds: float = 600.0,
    live_helper_lease_seconds: float = LIVE_HELPER_LEASE_SECONDS,
    runtime_factory_override=None,
    canonical_event_log: Path | None = None,
):
    from fastapi.responses import FileResponse, JSONResponse

    if vllm_base_url is not None:
        if live_provider_manifest is None:
            raise ValueError("--vllm-base-url requires --live-provider-manifest")
        if not vllm_model and model_path is None:
            raise ValueError("--vllm-base-url requires --vllm-model or --model")
    elif vllm_model is not None:
        raise ValueError("--vllm-model requires --vllm-base-url")
    if live_helper_lease_seconds <= 0:
        raise ValueError("--live-helper-lease-seconds must be positive")

    helpers = _test_live_api_module()
    scratch = tempfile.TemporaryDirectory(prefix="moss-browser-route-probe-")
    measurement_lock = threading.Lock()
    commit_wall_ns: dict[tuple[str, int], int] = {}
    canonical_event_writer = (
        None if canonical_event_log is None else _CanonicalEventLogWriter(canonical_event_log)
    )
    registry = LiveAccessRegistry(
        state_path=Path(scratch.name) / "live-auth.json",
        server_cert_sha256="ab" * 32,
    )
    grant = registry.issue_pairing(LivePeer("127.0.0.1", "http"), now=0.0)
    credential = registry.exchange_pairing(
        LivePeer("192.168.68.20", "https"),
        grant.pairing_payload,
        device_id="browser-route-probe",
        now=1.0,
    )
    if runtime_factory_override is not None:
        runtime_factory = runtime_factory_override
        provider_scope = "real production routes with a probe-supplied deterministic runtime; no model inference"
    elif model_path is None and live_provider_manifest is None:
        def runtime_factory():
            runtime = helpers.make_live_runtime(
                max_retained_samples=320_000,
                max_frame_samples=6_400,
                speech=(True, False) * 10_000,
            )
            _instrument_commit_times(
                runtime,
                commit_wall_ns,
                measurement_lock,
                event_log=canonical_event_writer,
            )
            return _ReadPathFixtureRuntime(runtime)

        provider_scope = (
            "real production routes with deterministic fake provider; committed text is runtime output; "
            "provisional text is an explicit read-path fixture; no model inference"
        )
    elif vllm_base_url is not None and live_provider_manifest is not None:
        from moss_transcribe_diarize.app.live_provider_bundle import (
            LiveProviderBundleConfig,
            build_live_runtime_factory,
        )
        from moss_transcribe_diarize.app.vllm_runner import VllmRunner

        config = LiveProviderBundleConfig.from_manifest(live_provider_manifest)
        runner = VllmRunner(
            base_url=vllm_base_url,
            model=vllm_model or str(model_path),
            timeout=vllm_timeout_seconds,
        )
        base_runtime_factory = build_live_runtime_factory(config, runner)

        def runtime_factory():
            return _instrument_commit_times(
                base_runtime_factory(),
                commit_wall_ns,
                measurement_lock,
                event_log=canonical_event_writer,
            )

        provider_scope = (
            "real production routes with manifest-admitted live provider bundle and remote "
            "production VllmRunner; the provider host receives inference requests only; "
            "system lane is synthetic and does not prove display capture"
        )
    elif model_path is not None and live_provider_manifest is not None:
        from moss_transcribe_diarize.app.live_provider_bundle import (
            LiveProviderBundleConfig,
            build_live_runtime_factory,
        )
        from moss_transcribe_diarize.app.model_runner import ModelRunner

        config = LiveProviderBundleConfig.from_manifest(live_provider_manifest)
        runner = ModelRunner(model_path, device="auto", dtype="bf16")
        base_runtime_factory = build_live_runtime_factory(config, runner)

        def runtime_factory():
            return _instrument_commit_times(
                base_runtime_factory(),
                commit_wall_ns,
                measurement_lock,
                event_log=canonical_event_writer,
            )

        provider_scope = (
            "real production routes with manifest-admitted live provider bundle and local "
            "production ModelRunner; system lane is synthetic and does not prove display capture"
        )
    else:
        raise ValueError("--model and --live-provider-manifest must be supplied together")

    app = create_app(
        model_path="fake-model",
        runs_dir=Path(scratch.name) / "runs",
        live_enabled=True,
        live_access_registry=registry,
        live_helper_lease_seconds=live_helper_lease_seconds,
        live_runtime_factory=runtime_factory,
    )
    app.state.prototype_scratch = scratch
    app.state.prototype_capture_bearer = credential.device_token
    app.state.prototype_provider_scope = provider_scope
    app.state.prototype_commit_wall_ns = commit_wall_ns
    app.state.prototype_canonical_event_writer = canonical_event_writer
    app.state.prototype_telemetry = {
        "accepted_frames": [],
        "lanes": {},
        "contract_probes": [],
        "phases": [],
        "probes": [],
        "renders": [],
        "heartbeats": [],
        "live_requests": [],
    }
    app.state.prototype_lock = threading.Lock()

    @app.middleware("http")
    async def record_strict_v2_frame_acceptance(request: Request, call_next):
        """Record route outcomes without persisting headers or request bodies."""
        parts = request.url.path.split("/")
        frame = None
        route = None
        session_id = None
        if request.method == "POST" and request.url.path == "/api/live/sessions":
            route = "create"
        elif len(parts) == 6 and parts[:4] == ["", "api", "live", "sessions"]:
            session_id = parts[4]
            route = {
                ("POST", "frames"): "frame",
                ("POST", "heartbeat"): "heartbeat",
                ("POST", "stop"): "stop",
                ("POST", "abort"): "abort",
                ("GET", "snapshot"): "snapshot",
                ("GET", "events"): "events",
            }.get((request.method, parts[5]))
        if (
            request.method == "POST"
            and len(parts) == 6
            and parts[:4] == ["", "api", "live", "sessions"]
            and parts[5] == "frames"
        ):
            try:
                payload = await request.json()
            except (json.JSONDecodeError, UnicodeDecodeError):
                payload = None
            if (
                isinstance(payload, dict)
                and payload.get("lane") in ("system", "microphone")
                and isinstance(payload.get("sequence"), int)
                and isinstance(payload.get("sample_count"), int)
                and isinstance(payload.get("sample_rate"), int)
                and isinstance(payload.get("device_epoch"), int)
            ):
                frame = {
                    "session_id": parts[4],
                    "lane": payload["lane"],
                    "sequence": payload["sequence"],
                    "sample_count": payload["sample_count"],
                    "sample_rate": payload["sample_rate"],
                    "device_epoch": payload["device_epoch"],
                }

        response = await call_next(request)
        if route is not None:
            cursor_name = "since_version" if route == "snapshot" else "since_seq" if route == "events" else None
            raw_cursor = request.query_params.get(cursor_name) if cursor_name is not None else None
            try:
                cursor = int(raw_cursor) if raw_cursor is not None else None
            except ValueError:
                cursor = None
            with app.state.prototype_lock:
                app.state.prototype_telemetry["live_requests"].append(
                    {
                        "route": route,
                        "session_id": session_id,
                        "status": response.status_code,
                        "wall_ms": round(time.time() * 1_000),
                        # The reload probe needs the two public replay cursors, but never
                        # records a bearer, request body, or arbitrary query value.
                        "cursor": cursor,
                    }
                )
        if frame is not None and response.status_code == 200:
            with app.state.prototype_lock:
                app.state.prototype_telemetry["accepted_frames"].append(
                    {**frame, "route_accepted_wall_ms": round(time.time() * 1_000)}
                )
        return response

    @app.get("/capture-harness")
    def capture_harness():
        return FileResponse(HERE / "capture_pipeline_page.html", media_type="text/html")

    @app.get("/framer_worklet.js")
    def framer_worklet():
        return FileResponse(HERE / "framer_worklet.js", media_type="text/javascript")

    @app.get("/prototype/bootstrap")
    def prototype_bootstrap():
        return JSONResponse(
            {
                "capture_bearer": app.state.prototype_capture_bearer,
                "device_id": credential.device_id,
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/prototype/measurement-instrumentation")
    def prototype_measurement_instrumentation():
        writer = app.state.prototype_canonical_event_writer
        return {"event_log": None if writer is None else writer.stats()}

    @app.post("/prototype/measurement-event-log/drain")
    async def prototype_measurement_event_log_drain(request: Request):
        """Expose a bounded writer-owned read barrier to the local measurement runner."""
        writer = app.state.prototype_canonical_event_writer
        if writer is None:
            return JSONResponse({"error": "canonical event log is disabled"}, status_code=409)
        try:
            body = await request.json()
            timeout_seconds = body.get("timeout_seconds")
        except (json.JSONDecodeError, AttributeError):
            return JSONResponse({"error": "drain request must be a JSON object"}, status_code=400)
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            return JSONResponse({"error": "timeout_seconds must be a positive finite number"}, status_code=400)
        drained = writer.drain(timeout_seconds=float(timeout_seconds))
        payload = {"drained": drained, "event_log": writer.stats()}
        return JSONResponse(payload, status_code=200 if drained else 503)

    @app.post("/prototype/telemetry")
    async def prototype_telemetry(request: Request):
        body = await request.json()
        lane, sequence, client_id = body.get("lane"), body.get("sequence"), body.get("client_id")
        if (
            lane not in ("system", "microphone")
            or not isinstance(sequence, int)
            or not isinstance(client_id, str)
            or not client_id
        ):
            return JSONResponse({"error": "bad telemetry identity"}, status_code=400)
        with app.state.prototype_lock:
            key = f"{client_id}:{sequence}"
            app.state.prototype_telemetry["lanes"].setdefault(lane, {})[key] = body
        return {}

    @app.post("/prototype/phase")
    async def prototype_phase(request: Request):
        body = await request.json()
        with app.state.prototype_lock:
            app.state.prototype_telemetry["phases"].append(body)
        return {}

    @app.post("/prototype/contract-probe")
    async def prototype_contract_probe(request: Request):
        body = await request.json()
        with app.state.prototype_lock:
            app.state.prototype_telemetry["contract_probes"].append(body)
        return {}

    @app.post("/prototype/heartbeat-telemetry")
    async def prototype_heartbeat_telemetry(request: Request):
        body = await request.json()
        with app.state.prototype_lock:
            app.state.prototype_telemetry["heartbeats"].append(body)
        return {}

    @app.post("/prototype/probes")
    async def prototype_probes(request: Request):
        body = await request.json()
        with app.state.prototype_lock:
            app.state.prototype_telemetry["probes"] = body.get("probes", [])
        return {}

    @app.post("/prototype/render-state")
    async def prototype_render_state(request: Request):
        body = await request.json()
        with app.state.prototype_lock:
            app.state.prototype_telemetry["renders"].append(body)
        return {}

    @app.get("/prototype/verdict")
    def prototype_verdict(session_id: str = "api-session"):
        with app.state.prototype_lock:
            telemetry = json.loads(json.dumps(app.state.prototype_telemetry))
        with measurement_lock:
            commit_times = dict(app.state.prototype_commit_wall_ns)
        try:
            v2 = app.state.live_v2_sessions.get(session_id).snapshot().to_dict()
            runtime = app.state.live_runtime.snapshot(session_id).to_dict()
        except KeyError:
            v2 = runtime = None
        helper_presence = app.state.live_helper_presence.snapshot(session_id)
        return {
            "scope": app.state.prototype_provider_scope,
            "session_id": session_id if v2 is not None else None,
            "live_helper_lease_seconds": LIVE_HELPER_LEASE_SECONDS,
            "descriptor": app.state.live_runtime.descriptor.to_dict(),
            "v2_session": v2,
            "runtime_snapshot": runtime,
            "helper_presence": None if helper_presence is None else helper_presence.to_dict(),
            "commit_to_render": _commit_to_render_summary(session_id, telemetry, commit_times),
            "telemetry": telemetry,
        }

    @app.get("/prototype/g7-verdict")
    def prototype_g7_verdict(session_id: str = "api-session"):
        with app.state.prototype_lock:
            telemetry = json.loads(json.dumps(app.state.prototype_telemetry))
        heartbeats = telemetry["heartbeats"]
        hidden_heartbeats = [
            record for record in heartbeats if record.get("client_visibility") == "hidden"
        ]
        def admitted_frames(visibility: str) -> dict[str, list[dict]]:
            selected = {"system": [], "microphone": []}
            for accepted in telemetry["accepted_frames"]:
                if accepted["session_id"] != session_id:
                    continue
                emitted = next(
                    (
                        record
                        for record in telemetry["lanes"].get(accepted["lane"], {}).values()
                        if record.get("session_id") == session_id
                        and record.get("wire_sequence") == accepted["sequence"]
                        and record.get("client_visibility") == visibility
                    ),
                    None,
                )
                if emitted is not None:
                    selected[accepted["lane"]].append(
                        {
                            **accepted,
                            "emitted_sequence": emitted["sequence"],
                            "client_visibility": emitted["client_visibility"],
                            "client_wall_ms": emitted["client_wall_ms"],
                            "client_rms": emitted["client_rms"],
                            "quanta": emitted["quanta"],
                        }
                    )
            return selected

        hidden_frames = admitted_frames("hidden")
        visible_frames = admitted_frames("visible")
        try:
            v2 = app.state.live_v2_sessions.get(session_id).snapshot().to_dict()
        except KeyError:
            v2 = None
        helper_presence = app.state.live_helper_presence.snapshot(session_id)
        heartbeat_sequences = [record["sequence"] for record in heartbeats]
        heartbeat_gaps = [
            [left, right]
            for left, right in zip(heartbeat_sequences, heartbeat_sequences[1:])
            if right != left + 1
        ]
        hidden_cadence = _visibility_cadence(
            heartbeats,
            "hidden",
            time_key="started_wall_ms",
        )
        visible_cadence = _visibility_cadence(
            heartbeats,
            "visible",
            time_key="started_wall_ms",
        )
        hidden_max_delta = hidden_cadence["delta_ms"]["max"]
        return {
            "scope": app.state.prototype_provider_scope,
            "live_helper_lease_seconds": LIVE_HELPER_LEASE_SECONDS,
            "session_active_after_hidden_phase": v2 is not None and v2["status"] == "active",
            "heartbeat_summary": {
                "total": len(heartbeats),
                "http_status_counts": {
                    str(status): sum(record["status"] == status for record in heartbeats)
                    for status in sorted({record["status"] for record in heartbeats})
                },
                "sequence_gaps": heartbeat_gaps,
                "hidden": hidden_cadence,
                "visible": visible_cadence,
                "hidden_max_delta_below_lease": (
                    hidden_max_delta is not None
                    and hidden_max_delta < LIVE_HELPER_LEASE_SECONDS * 1_000
                ),
            },
            "hidden_frame_cadence": {
                lane: _visibility_cadence(
                    records,
                    "hidden",
                    time_key="route_accepted_wall_ms",
                )
                for lane, records in hidden_frames.items()
            },
            "visible_frame_cadence": {
                lane: _visibility_cadence(
                    records,
                    "visible",
                    time_key="route_accepted_wall_ms",
                )
                for lane, records in visible_frames.items()
            },
            "v2_session": v2,
            "helper_presence": None if helper_presence is None else helper_presence.to_dict(),
            "visibility_phases": [
                phase
                for phase in telemetry["phases"]
                if str(phase.get("phase", "")).startswith("visibility-")
            ],
            "raw_hidden_heartbeats": hidden_heartbeats,
            "raw_hidden_frames": hidden_frames,
            "raw_strict_v2_frame_acceptances": [
                accepted
                for accepted in telemetry["accepted_frames"]
                if accepted["session_id"] == session_id
            ],
        }

    @app.post("/prototype/reset")
    def prototype_reset():
        return JSONResponse(
            {"error": "restart the one-session production-route probe to reset"},
            status_code=409,
        )

    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path)
    parser.add_argument("--live-provider-manifest", type=Path)
    parser.add_argument(
        "--vllm-base-url",
        help="OpenAI-compatible remote vLLM URL; requires --live-provider-manifest and a model name.",
    )
    parser.add_argument(
        "--vllm-model",
        help="Remote vLLM model name; defaults to --model when that argument is supplied.",
    )
    parser.add_argument(
        "--vllm-timeout-seconds",
        type=float,
        default=600.0,
        help="Per-span remote vLLM request timeout.",
    )
    parser.add_argument(
        "--live-helper-lease-seconds",
        type=float,
        default=LIVE_HELPER_LEASE_SECONDS,
        help="Explicit local helper-presence lease for this route probe.",
    )
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument(
        "--canonical-event-log",
        type=Path,
        help="append raw canonical queue/start/publication observations for a local measurement harness",
    )
    args = parser.parse_args()
    app = build_app(
        model_path=args.model,
        live_provider_manifest=args.live_provider_manifest,
        vllm_base_url=args.vllm_base_url,
        vllm_model=args.vllm_model,
        vllm_timeout_seconds=args.vllm_timeout_seconds,
        live_helper_lease_seconds=args.live_helper_lease_seconds,
        canonical_event_log=args.canonical_event_log,
    )
    print(f"PROTOTYPE production routes listening on http://127.0.0.1:{args.port}/capture-harness")
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", proxy_headers=False)
    finally:
        writer = app.state.prototype_canonical_event_writer
        if writer is not None:
            writer.close()


if __name__ == "__main__":
    main()
