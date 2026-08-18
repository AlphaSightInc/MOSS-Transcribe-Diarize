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
through the manifest-admitted live provider bundle instead.
The ephemeral capture credential is available only from a loopback prototype route
and is never printed or persisted.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
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


def _instrument_commit_times(runtime, commit_wall_ns: dict[tuple[str, int], int], lock: threading.Lock):
    """Timestamp canonical publication at the real runtime event seam."""
    record_event = runtime._record_event

    def measured_record_event(state, kind, payload):
        record_event(state, kind, payload)
        if kind == "canonical_processed" and payload.get("submitted"):
            with lock:
                commit_wall_ns.setdefault(
                    (state.session_id, int(payload["span_id"])),
                    time.time_ns(),
                )

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
    model_path: Path | None = None,
    live_provider_manifest: Path | None = None,
    runtime_factory_override=None,
):
    from fastapi.responses import FileResponse, JSONResponse

    helpers = _test_live_api_module()
    scratch = tempfile.TemporaryDirectory(prefix="moss-browser-route-probe-")
    measurement_lock = threading.Lock()
    commit_wall_ns: dict[tuple[str, int], int] = {}
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
            _instrument_commit_times(runtime, commit_wall_ns, measurement_lock)
            return _ReadPathFixtureRuntime(runtime)

        provider_scope = (
            "real production routes with deterministic fake provider; committed text is runtime output; "
            "provisional text is an explicit read-path fixture; no model inference"
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
                base_runtime_factory(), commit_wall_ns, measurement_lock
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
        live_helper_lease_seconds=LIVE_HELPER_LEASE_SECONDS,
        live_runtime_factory=runtime_factory,
    )
    app.state.prototype_scratch = scratch
    app.state.prototype_capture_bearer = credential.device_token
    app.state.prototype_provider_scope = provider_scope
    app.state.prototype_commit_wall_ns = commit_wall_ns
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
    args = parser.parse_args()
    app = build_app(
        model_path=args.model,
        live_provider_manifest=args.live_provider_manifest,
    )
    print(f"PROTOTYPE production routes listening on http://127.0.0.1:{PORT}/capture-harness")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning", proxy_headers=False)


if __name__ == "__main__":
    main()
