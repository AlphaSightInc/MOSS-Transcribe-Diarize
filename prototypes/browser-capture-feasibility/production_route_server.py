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


def build_app(
    *,
    model_path: Path | None = None,
    live_provider_manifest: Path | None = None,
):
    from fastapi.responses import FileResponse, JSONResponse

    helpers = _test_live_api_module()
    scratch = tempfile.TemporaryDirectory(prefix="moss-browser-route-probe-")
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
    if model_path is None and live_provider_manifest is None:
        runtime_factory = lambda: _ReadPathFixtureRuntime(
            helpers.make_live_runtime(
                max_retained_samples=320_000,
                max_frame_samples=6_400,
                speech=(True, False) * 10_000,
            )
        )
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
        runtime_factory = build_live_runtime_factory(config, runner)
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
    app.state.prototype_telemetry = {
        "lanes": {},
        "phases": [],
        "probes": [],
        "renders": [],
        "heartbeats": [],
    }
    app.state.prototype_lock = threading.Lock()

    @app.get("/capture-harness")
    def capture_harness():
        return FileResponse(HERE / "capture_pipeline_page.html", media_type="text/html")

    @app.get("/framer_worklet.js")
    def framer_worklet():
        return FileResponse(HERE / "framer_worklet.js", media_type="text/javascript")

    @app.get("/prototype/bootstrap")
    def prototype_bootstrap():
        return JSONResponse(
            {"capture_bearer": app.state.prototype_capture_bearer},
            headers={"Cache-Control": "no-store"},
        )

    @app.post("/prototype/telemetry")
    async def prototype_telemetry(request: Request):
        body = await request.json()
        lane, sequence = body.get("lane"), body.get("sequence")
        if lane not in ("system", "microphone") or not isinstance(sequence, int):
            return JSONResponse({"error": "bad telemetry identity"}, status_code=400)
        with app.state.prototype_lock:
            app.state.prototype_telemetry["lanes"].setdefault(lane, {})[str(sequence)] = body
        return {}

    @app.post("/prototype/phase")
    async def prototype_phase(request: Request):
        body = await request.json()
        with app.state.prototype_lock:
            app.state.prototype_telemetry["phases"].append(body)
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
        hidden_frames = {
            lane: [
                record
                for record in records.values()
                if record.get("client_visibility") == "hidden"
            ]
            for lane, records in telemetry["lanes"].items()
        }
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
                    list(telemetry["lanes"][lane].values()),
                    "hidden",
                    time_key="client_wall_ms",
                )
                for lane in hidden_frames
            },
            "visible_frame_cadence": {
                lane: _visibility_cadence(
                    list(records.values()),
                    "visible",
                    time_key="client_wall_ms",
                )
                for lane, records in telemetry["lanes"].items()
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
