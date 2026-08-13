#!/usr/bin/env python3
"""PROTOTYPE: run the browser harness through the real local live HTTP routes.

Question: can real Chrome create a production live session, admit exact v2
two-lane frames, and poll/render its production snapshot and event streams with
render-then-advance cursors?

Run: PYTHONDONTWRITEBYTECODE=1 python3 \
  prototypes/browser-capture-feasibility/production_route_server.py
Then open http://127.0.0.1:8899/capture-harness?autostart=1 in Chrome.

The provider is deterministic and does not run a model. Its committed text is real
runtime output; a labelled provisional fixture exercises only that renderer branch.
This proves the browser, FastAPI route, auth, descriptor, v2 session, mixer, runtime
ingress, and authenticated read seams only.
The ephemeral capture credential is available only from a loopback prototype route
and is never printed or persisted.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
PORT = 8899
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


def build_app():
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
    app = create_app(
        model_path="fake-model",
        runs_dir=Path(scratch.name) / "runs",
        live_enabled=True,
        live_access_registry=registry,
        live_helper_lease_seconds=30.0,
        live_runtime_factory=lambda: _ReadPathFixtureRuntime(
            helpers.make_live_runtime(
                max_retained_samples=320_000,
                max_frame_samples=6_400,
                speech=(True, False) * 10_000,
            )
        ),
    )
    app.state.prototype_scratch = scratch
    app.state.prototype_capture_bearer = credential.device_token
    app.state.prototype_telemetry = {"lanes": {}, "phases": [], "probes": [], "renders": []}
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
    def prototype_verdict():
        session_id = "api-session"
        with app.state.prototype_lock:
            telemetry = json.loads(json.dumps(app.state.prototype_telemetry))
        try:
            v2 = app.state.live_v2_sessions.get(session_id).snapshot().to_dict()
            runtime = app.state.live_runtime.snapshot(session_id).to_dict()
        except KeyError:
            v2 = runtime = None
        return {
            "scope": (
                "real production routes with deterministic fake provider; committed text is runtime output; "
                "provisional text is an explicit read-path fixture; no model inference"
            ),
            "session_id": session_id if v2 is not None else None,
            "descriptor": app.state.live_runtime.descriptor.to_dict(),
            "v2_session": v2,
            "runtime_snapshot": runtime,
            "telemetry": telemetry,
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

    app = build_app()
    print(f"PROTOTYPE production routes listening on http://127.0.0.1:{PORT}/capture-harness")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning", proxy_headers=False)


if __name__ == "__main__":
    main()
