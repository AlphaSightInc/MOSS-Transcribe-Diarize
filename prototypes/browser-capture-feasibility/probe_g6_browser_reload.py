#!/usr/bin/env python3
"""Exercise the real ControlPanel's G6 reload path in Chrome.

Question: can Chrome start the shipped Preact ControlPanel from deterministic fake
media streams, navigate while the session is active, and reattach its read-only
transcript view without preserving the capture bearer or issuing Stop?  Does that
new poller reconstruct every committed transcript item exactly once?

Run (after ``cd frontend && npm ci`` when this worktree has no ignored
``node_modules``):

  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
    prototypes/browser-capture-feasibility/probe_g6_browser_reload.py \
    --output evidence/phase1/y6-browser-reload/iteration-3-live-reload.json

The backend binds only the fixed loopback proxy target (127.0.0.1:8090) and
refuses to run if it is already occupied. Vite receives ``--base /`` because
its production ``/static/`` base is itself proxied to that backend; the override
keeps the development document and source modules on Vite while preserving the
production ``/api`` proxy. Both lanes are in-page oscillator MediaStreams, so this
probe never invokes or automates a permission or display picker. There is no model
inference or deployed host.
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from probe_recreate_session import _ChromePage, _chrome_binary, _stop_process_group
from production_route_server import build_app


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
FRONTEND_DIR = REPO_ROOT / "frontend"
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8090
REATTACH_STORAGE_KEY = "lt:session:reattach"


class _ProbeFailure(RuntimeError):
    """An assertion failure whose details are safe to record in the raw artifact."""

    def __init__(self, message: str, details: dict):
        super().__init__(message)
        self.details = details


def _json(url: str) -> dict:
    with urlopen(url, timeout=3) as response:
        return json.loads(response.read().decode("utf-8"))


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((BACKEND_HOST, 0))
        return int(sock.getsockname()[1])


def _require_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((BACKEND_HOST, port))
        except OSError as error:
            raise RuntimeError(
                f"refusing to reuse {BACKEND_HOST}:{port}; the Vite proxy target must be owned by this probe"
            ) from error


def _start_backend(app):
    import uvicorn

    _require_port_available(BACKEND_PORT)
    base_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}"
    server = uvicorn.Server(
        uvicorn.Config(app, host=BACKEND_HOST, port=BACKEND_PORT, log_level="warning", access_log=False)
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
    raise RuntimeError("deterministic production-route backend did not start")


def _stop_backend(app, server, thread) -> None:
    server.should_exit = True
    thread.join(timeout=5)
    app.state.prototype_scratch.cleanup()


def _vite_binary() -> Path:
    binary = FRONTEND_DIR / "node_modules" / ".bin" / "vite"
    if not binary.is_file():
        raise RuntimeError(
            f"Vite is unavailable at {binary}; install the lockfile dependencies with "
            "(cd frontend && npm ci) before running this probe"
        )
    return binary


def _start_vite() -> tuple[str, subprocess.Popen[str]]:
    port = _free_loopback_port()
    process = subprocess.Popen(
        [
            str(_vite_binary()),
            "--host",
            BACKEND_HOST,
            "--port",
            str(port),
            "--strictPort",
            "--base",
            "/",
        ],
        cwd=FRONTEND_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    base_url = f"http://{BACKEND_HOST}:{port}"
    app_url = f"{base_url}/"
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(f"Vite exited before becoming ready ({process.returncode}): {output[-2000:]}")
        try:
            with urlopen(app_url, timeout=1) as response:
                if response.status == 200:
                    return app_url, process
        except Exception:
            time.sleep(0.05)
    _stop_process_group(process)
    raise RuntimeError("Vite did not become ready")


def _control_state(page: _ChromePage) -> dict:
    state = page.evaluate(
        f"""(() => {{
          const panel = document.querySelector('.capture-supervisor');
          const status = document.querySelector('.capture-status');
          const bearer = document.querySelector('#capture-bearer');
          const storage = (() => {{
            try {{ return window.sessionStorage; }} catch {{ return null; }}
          }})();
          const saved = storage?.getItem({REATTACH_STORAGE_KEY!r}) ?? null;
          let reattachFields = [];
          try {{
            const value = JSON.parse(saved ?? 'null');
            if (value && typeof value === 'object' && !Array.isArray(value)) {{
              reattachFields = Object.keys(value).sort();
            }}
          }} catch {{
            reattachFields = ['<malformed>'];
          }}
          return {{
            phase: panel?.getAttribute('data-capture-phase') ?? null,
            statusLine: status?.textContent ?? null,
            storageKeys: storage ? Object.keys(storage).sort() : [],
            reattachFields,
            bearerInputHasValue: Boolean(bearer && bearer.value),
            mediaDebug: window.__mossG6MediaDebug ?? null,
          }};
        }})()"""
    )
    if not isinstance(state, dict):
        raise RuntimeError(f"ControlPanel state is not an object: {state!r}")
    return state


def _wait_for_mount(page: _ChromePage) -> dict:
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        state = _control_state(page)
        if state.get("phase") is not None:
            return state
        time.sleep(0.05)
    raise RuntimeError("actual ControlPanel did not mount in Chrome")


def _wait_for_phase(page: _ChromePage, expected: str, *, timeout_seconds: float = 12.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = _control_state(page)
        if last.get("phase") == expected:
            return last
        time.sleep(0.05)
    raise RuntimeError(f"ControlPanel did not reach {expected!r}; last={last!r}")


def _wait_for_status(page: _ChromePage, expected: str, *, timeout_seconds: float = 12.0) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last = None
    while time.monotonic() < deadline:
        last = _control_state(page)
        if last.get("statusLine") == expected:
            return last
        time.sleep(0.05)
    raise RuntimeError(f"ControlPanel did not report {expected!r}; last={last!r}")


def _click_button(page: _ChromePage, text: str) -> None:
    clicked = page.evaluate(
        f"""(() => {{
          const button = [...document.querySelectorAll('button')].find(
            (candidate) => candidate.textContent?.trim() === {text!r}
          );
          if (!button || button.disabled) return false;
          button.click();
          return true;
        }})()"""
    )
    if clicked is not True:
        raise RuntimeError(f"could not click enabled ControlPanel button {text!r}")


def _set_capture_bearer(page: _ChromePage, capture_bearer: str) -> None:
    updated = page.evaluate(
        f"""(() => {{
          const input = document.querySelector('#capture-bearer');
          if (!(input instanceof HTMLInputElement)) return false;
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
          if (!setter) return false;
          setter.call(input, {capture_bearer!r});
          input.dispatchEvent(new InputEvent('input', {{bubbles: true, inputType: 'insertText'}}));
          return input.value.length > 0;
        }})()"""
    )
    if updated is not True:
        raise RuntimeError("could not enter the in-memory capture bearer")


def _install_synthetic_system_media(page: _ChromePage) -> None:
    installed = page.evaluate(
        """(() => {
          const mediaDevices = navigator.mediaDevices;
          if (!mediaDevices?.getDisplayMedia) return false;
          const debug = {microphone: null, system: null, workletMessages: 0, workletNodes: [], laneRms: {}};
          window.__mossG6MediaDebug = debug;
          const NativeAudioWorkletNode = window.AudioWorkletNode;
          window.AudioWorkletNode = class InstrumentedAudioWorkletNode extends NativeAudioWorkletNode {
            constructor(...args) {
              super(...args);
              debug.workletNodes.push({name: args[1], contextState: this.context.state});
              this.port.addEventListener('message', (event) => {
                debug.workletMessages += 1;
                const data = event.data;
                const samples = data?.samples;
                if (!(samples instanceof Float32Array) || typeof data?.lane !== 'string') return;
                let sumSquares = 0;
                for (const sample of samples) sumSquares += sample * sample;
                const rms = Math.sqrt(sumSquares / samples.length);
                const prior = debug.laneRms[data.lane] ?? {count: 0, max: 0};
                debug.laneRms[data.lane] = {count: prior.count + 1, max: Math.max(prior.max, rms)};
              });
            }
          };
          const generators = [];
          async function syntheticStream(lane, frequency) {
            const context = new AudioContext({sampleRate: 48000});
            const oscillator = context.createOscillator();
            const gain = context.createGain();
            const destination = context.createMediaStreamDestination();
            oscillator.frequency.value = frequency;
            gain.gain.value = 0.2;
            oscillator.connect(gain).connect(destination);
            oscillator.start();
            await context.resume();
            generators.push({context, oscillator});
            const track = destination.stream.getAudioTracks()[0];
            debug[lane] = {
              source: 'oscillator',
              calls: generators.length,
              contextState: context.state,
              trackReadyState: track?.readyState ?? null,
            };
            return destination.stream;
          }
          Object.defineProperty(mediaDevices, 'getUserMedia', {
            configurable: true,
            value: async () => syntheticStream('microphone', 440),
          });
          Object.defineProperty(mediaDevices, 'getDisplayMedia', {
            configurable: true,
            value: async () => syntheticStream('system', 997),
          });
          return true;
        })()"""
    )
    if installed is not True:
        raise RuntimeError("could not install the no-picker synthetic system source")


def _reattach_record(page: _ChromePage, *, capture_bearer: str) -> dict:
    record = page.evaluate(
        f"""(() => {{
          const raw = sessionStorage.getItem({REATTACH_STORAGE_KEY!r});
          const value = raw === null ? null : JSON.parse(raw);
          return {{
            sessionId: value?.sessionId ?? null,
            viewTokenPresent: typeof value?.viewToken === 'string' && value.viewToken.length > 0,
            recordFields: value && typeof value === 'object' ? Object.keys(value).sort() : [],
            captureBearerAbsent: !Object.values(sessionStorage).some((item) => item.includes({capture_bearer!r})),
          }};
        }})()"""
    )
    if not isinstance(record, dict) or not isinstance(record.get("sessionId"), str):
        raise RuntimeError(f"missing tab-scoped reattach record: {record!r}")
    return record


def _server_status(page: _ChromePage, session_id: str) -> dict:
    status = page.evaluate(
        f"""(async () => {{
          const raw = sessionStorage.getItem({REATTACH_STORAGE_KEY!r});
          const record = raw === null ? null : JSON.parse(raw);
          if (!record?.viewToken) return null;
          const response = await fetch('/api/live/sessions/' + encodeURIComponent({session_id!r}) + '/snapshot', {{
            headers: {{Authorization: 'Bearer ' + record.viewToken}}, cache: 'no-store'
          }});
          const body = await response.json();
          return {{
            status: response.status,
            capturePhase: body.capture_phase ?? null,
            statusLine: body.status_line ?? null,
            snapshotStatus: body.snapshot?.session?.status ?? null,
          }};
        }})()"""
    )
    if not isinstance(status, dict):
        raise RuntimeError(f"read-only snapshot response is not an object: {status!r}")
    return status


def _frontend_transcript_state(page: _ChromePage) -> dict:
    """Read the actual Vite module singleton that drives the rendered transcript.

    DOM turns intentionally coalesce adjacent segments, so inspecting their text alone
    cannot distinguish two source items from one.  The Preact singleton is the exact
    state ``TranscriptPane`` renders; importing the already-loaded Vite module lets the
    probe retain the real browser/poller path while recording stable item identities.
    """
    state = page.evaluate(
        """(async () => {
          const session = await import('/src/state/session.ts');
          const items = session.sessionTranscriptItems.value.map((item) => ({
            id: item.id,
            segmentId: item.segment_id,
            state: item.state,
          }));
          return {
            items,
            renderedTurnCount: document.querySelectorAll('.tr-body .utt').length,
          };
        })()"""
    )
    if not isinstance(state, dict) or not isinstance(state.get("items"), list):
        raise RuntimeError(f"frontend transcript state is not inspectable: {state!r}")
    return state


def _server_cursors(page: _ChromePage, session_id: str) -> dict:
    """Read public snapshot/event cursor facts through the saved view authority.

    No secret leaves Chrome: this only returns versions, event sequences, and committed
    span ids.  The requests deliberately start at the public origin cursors so the probe
    can compare the same server history immediately before and after navigation.
    """
    cursors = page.evaluate(
        f"""(async () => {{
          const raw = sessionStorage.getItem({REATTACH_STORAGE_KEY!r});
          const record = raw === null ? null : JSON.parse(raw);
          if (!record?.viewToken) return null;
          const root = '/api/live/sessions/' + encodeURIComponent({session_id!r});
          const [snapshotResponse, eventsResponse] = await Promise.all([
            fetch(root + '/snapshot?since_version=0', {{
              headers: {{Authorization: 'Bearer ' + record.viewToken}}, cache: 'no-store'
            }}),
            fetch(root + '/events?since_seq=-1', {{
              headers: {{Authorization: 'Bearer ' + record.viewToken}}, cache: 'no-store'
            }}),
          ]);
          const [snapshotBody, eventsBody] = await Promise.all([
            snapshotResponse.json(), eventsResponse.json()
          ]);
          const session = snapshotBody?.snapshot?.session;
          const events = Array.isArray(eventsBody?.events) ? eventsBody.events : [];
          return {{
            snapshotStatus: snapshotResponse.status,
            eventsStatus: eventsResponse.status,
            snapshotVersion: session?.version ?? null,
            committedSpanIds: Array.isArray(session?.committed)
              ? session.committed.map((commit) => commit?.span_id).filter(Number.isInteger)
              : [],
            eventSequences: events.map((event) => event?.seq).filter(Number.isInteger),
          }};
        }})()"""
    )
    if not isinstance(cursors, dict):
        raise RuntimeError(f"server cursor read is not an object: {cursors!r}")
    return cursors


def _committed_item_ids(frontend: dict) -> list[str]:
    items = frontend.get("items")
    if not isinstance(items, list):
        return []
    return [
        item["id"]
        for item in items
        if isinstance(item, dict)
        and item.get("state") != "provisional"
        and isinstance(item.get("id"), str)
        and item["id"]
    ]


def _committed_span_ids(frontend: dict) -> set[int]:
    """Recover the server span identity encoded in the frontend's stable segment id."""
    spans = set()
    items = frontend.get("items")
    if not isinstance(items, list):
        return spans
    for item in items:
        if not isinstance(item, dict) or item.get("state") == "provisional":
            continue
        segment_id = item.get("segmentId")
        if not isinstance(segment_id, str):
            continue
        span, separator, _ = segment_id.partition(":")
        if separator and span.isdecimal():
            spans.add(int(span))
    return spans


def _wait_for_committed_render(page: _ChromePage, session_id: str) -> tuple[dict, dict]:
    """Wait for the real poller to render at least one committed item before reload."""
    deadline = time.monotonic() + 12.0
    last = None
    while time.monotonic() < deadline:
        frontend = _frontend_transcript_state(page)
        cursors = _server_cursors(page, session_id)
        committed_ids = _committed_item_ids(frontend)
        if (
            committed_ids
            and frontend.get("renderedTurnCount", 0) > 0
            and cursors.get("snapshotStatus") == 200
            and cursors.get("eventsStatus") == 200
            and cursors.get("committedSpanIds")
            and _committed_span_ids(frontend) == set(cursors["committedSpanIds"])
        ):
            return frontend, cursors
        last = {"frontend": frontend, "cursors": cursors}
        time.sleep(0.05)
    raise RuntimeError(f"real poller did not render a committed item before reload: {last!r}")


def _wait_for_reloaded_continuity(
    page: _ChromePage,
    session_id: str,
    expected_item_ids: set[str],
) -> tuple[dict, dict]:
    """Wait until the new browser poller has rebuilt every pre-reload item."""
    deadline = time.monotonic() + 12.0
    last = None
    while time.monotonic() < deadline:
        frontend = _frontend_transcript_state(page)
        cursors = _server_cursors(page, session_id)
        rendered_ids = set(_committed_item_ids(frontend))
        if expected_item_ids.issubset(rendered_ids):
            return frontend, cursors
        last = {"frontend": frontend, "cursors": cursors}
        time.sleep(0.05)
    raise RuntimeError(f"reattached poller did not rebuild all pre-reload items: {last!r}")


def _server_verdict(backend_url: str, session_id: str) -> dict:
    return _json(f"{backend_url}/prototype/verdict?session_id={quote(session_id, safe='')}")


def _wait_for_post_reload_read(backend_url: str, session_id: str, reload_started_wall_ms: int) -> list[dict]:
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        verdict = _server_verdict(backend_url, session_id)
        requests = verdict.get("telemetry", {}).get("live_requests", [])
        if isinstance(requests, list):
            reads = [
                request
                for request in requests
                if request.get("route") in {"snapshot", "events"}
                and request.get("session_id") == session_id
                and request.get("wall_ms", 0) >= reload_started_wall_ms
            ]
            if reads:
                return reads
        time.sleep(0.05)
    return []


def _reload(page: _ChromePage) -> None:
    try:
        page.evaluate("window.location.reload(); undefined")
    except RuntimeError as error:
        # Navigation commonly destroys Runtime.evaluate's execution context before CDP
        # responds. The later mount wait, not this transport race, decides success.
        if "execution context" not in str(error).lower():
            raise


def _run(chrome_bin: str) -> dict:
    app = build_app()
    backend_url = None
    backend_server = None
    backend_thread = None
    vite_url = None
    vite = None
    page = None
    try:
        backend_url, backend_server, backend_thread = _start_backend(app)
        vite_url, vite = _start_vite()
        page = _ChromePage(
            chrome_bin=chrome_bin,
            url=vite_url,
            extra_args=("--autoplay-policy=no-user-gesture-required",),
        )
        mounted = _wait_for_mount(page)
        descriptor = page.evaluate(
            """fetch('/api/live/descriptor?client_min_protocol_version=2&client_max_protocol_version=2')
                .then(async (response) => ({status: response.status, body: await response.json()}))"""
        )
        if not isinstance(descriptor, dict):
            raise _ProbeFailure("descriptor proxy response was not an object", {"descriptor": descriptor})
        body = descriptor.get("body")
        if descriptor.get("status") != 200 or not isinstance(body, dict):
            raise _ProbeFailure("actual frontend could not reach production descriptor route", {"descriptor": descriptor})
        negotiated_descriptor = body.get("descriptor")
        if not isinstance(negotiated_descriptor, dict):
            raise _ProbeFailure("descriptor response lacked negotiated descriptor data", {"descriptor": descriptor})
        if (
            not isinstance(negotiated_descriptor.get("frame_samples"), int)
            or negotiated_descriptor["frame_samples"] <= 0
        ):
            raise _ProbeFailure("descriptor lacked a positive frame_samples geometry", {"descriptor": descriptor})
        if mounted.get("phase") != "idle":
            raise _ProbeFailure("fresh Chrome profile did not mount ControlPanel in idle state", {"mounted": mounted})
        if mounted.get("storageKeys"):
            raise _ProbeFailure("fresh Chrome profile unexpectedly had tab-scoped storage", {"mounted": mounted})

        bootstrap = _json(f"{backend_url}/prototype/bootstrap")
        capture_bearer = bootstrap.get("capture_bearer")
        if not isinstance(capture_bearer, str) or not capture_bearer:
            raise RuntimeError("local prototype did not provide an ephemeral capture bearer")
        _install_synthetic_system_media(page)
        _set_capture_bearer(page, capture_bearer)
        _click_button(page, "Enable microphone")
        _wait_for_phase(page, "configuring")
        _wait_for_status(page, "Microphone connected. Share a browser tab, window, or screen with audio.")
        _click_button(page, "Share audio")
        ready = _wait_for_phase(page, "ready")
        _click_button(page, "Start capture")
        active = _wait_for_phase(page, "active")
        reattach_before = _reattach_record(page, capture_bearer=capture_bearer)
        session_id = reattach_before["sessionId"]
        frontend_before_reload, cursors_before_reload = _wait_for_committed_render(page, session_id)
        server_before_reload = _server_status(page, session_id)

        reload_started_wall_ms = round(time.time() * 1_000)
        _reload(page)
        reattached = _wait_for_phase(page, "viewing")
        reattach_after = _reattach_record(page, capture_bearer=capture_bearer)
        post_reload_reads = _wait_for_post_reload_read(backend_url, session_id, reload_started_wall_ms)
        frontend_after_reload, cursors_after_reload = _wait_for_reloaded_continuity(
            page,
            session_id,
            set(_committed_item_ids(frontend_before_reload)),
        )
        server_after_reload = _server_status(page, session_id)
        verdict = _server_verdict(backend_url, session_id)
        requests = verdict.get("telemetry", {}).get("live_requests", [])
        if not isinstance(requests, list):
            raise RuntimeError("prototype verdict has no live request telemetry")
        stop_requests = [
            request
            for request in requests
            if request.get("route") == "stop" and request.get("session_id") == session_id
        ]
        pre_reload_poller_reads = [
            request
            for request in requests
            if request.get("route") in {"snapshot", "events"}
            and request.get("session_id") == session_id
            and request.get("wall_ms", 0) < reload_started_wall_ms
            and isinstance(request.get("cursor"), int)
        ]
        before_item_ids = _committed_item_ids(frontend_before_reload)
        after_item_ids = _committed_item_ids(frontend_after_reload)
        after_span_ids = _committed_span_ids(frontend_after_reload)
        authoritative_span_ids = cursors_after_reload.get("committedSpanIds")
        before_event_sequences = cursors_before_reload.get("eventSequences")
        after_event_sequences = cursors_after_reload.get("eventSequences")
        assertions = {
            "real_control_panel_started_one_session": active.get("phase") == "active",
            "same_session_is_retained_in_tab_storage": reattach_after.get("sessionId") == session_id,
            "only_view_credentials_are_stored": (
                reattach_before.get("recordFields") == ["sessionId", "viewToken"]
                and reattach_after.get("recordFields") == ["sessionId", "viewToken"]
                and reattach_after.get("viewTokenPresent") is True
            ),
            "capture_bearer_did_not_survive_reload": (
                reattach_before.get("captureBearerAbsent") is True
                and reattach_after.get("captureBearerAbsent") is True
                and reattached.get("bearerInputHasValue") is False
            ),
            "reload_enters_read_only_viewing": (
                reattached.get("phase") == "viewing"
                and reattached.get("statusLine") == "Transcript reattached. Browser capture stopped on reload."
            ),
            "server_received_no_stop_on_reload": not stop_requests,
            "session_remains_active_after_reload": server_after_reload.get("snapshotStatus") == "active",
            "server_authored_status_remains_readable": (
                server_before_reload.get("status") == 200
                and isinstance(server_before_reload.get("statusLine"), str)
                and bool(server_before_reload["statusLine"])
                and server_after_reload.get("status") == 200
                and isinstance(server_after_reload.get("statusLine"), str)
                and bool(server_after_reload["statusLine"])
            ),
            "reattached_poller_issued_read_only_requests": bool(post_reload_reads),
            "real_poller_rendered_committed_items_before_reload": bool(before_item_ids),
            "every_pre_reload_item_survives_reattach": set(before_item_ids).issubset(set(after_item_ids)),
            "reattached_state_has_no_duplicate_item_ids": len(after_item_ids) == len(set(after_item_ids)),
            "reattached_state_matches_authoritative_committed_spans": (
                isinstance(authoritative_span_ids, list)
                and after_span_ids == set(authoritative_span_ids)
            ),
            # Events are a bounded replay buffer, so an older retained window can roll
            # forward during navigation.  The durable transcript invariant is the
            # authoritative snapshot/item check above; here we prove that the event cursor
            # itself never regresses while allowing bounded-history eviction.
            "server_event_cursor_does_not_regress_across_reload": (
                isinstance(before_event_sequences, list)
                and isinstance(after_event_sequences, list)
                and bool(before_event_sequences)
                and bool(after_event_sequences)
                and before_event_sequences == sorted(set(before_event_sequences))
                and after_event_sequences == sorted(set(after_event_sequences))
                and max(after_event_sequences) >= max(before_event_sequences)
            ),
            "real_poller_used_snapshot_and_event_cursors_on_both_sides": (
                {request.get("route") for request in pre_reload_poller_reads} == {"snapshot", "events"}
                and {request.get("route") for request in post_reload_reads} == {"snapshot", "events"}
                and all(isinstance(request.get("cursor"), int) for request in post_reload_reads)
            ),
        }
        if not all(assertions.values()):
            raise _ProbeFailure(
                "minimum reload assertions failed",
                {
                    "mounted": mounted,
                    "ready": ready,
                    "active": active,
                    "reattached": reattached,
                    "session_id": session_id,
                    "reattach_before": reattach_before,
                    "reattach_after": reattach_after,
                    "server_before_reload": server_before_reload,
                    "server_after_reload": server_after_reload,
                    "frontend_before_reload": frontend_before_reload,
                    "frontend_after_reload": frontend_after_reload,
                    "cursors_before_reload": cursors_before_reload,
                    "cursors_after_reload": cursors_after_reload,
                    "pre_reload_poller_reads": pre_reload_poller_reads,
                    "post_reload_reads": post_reload_reads,
                    "stop_requests": stop_requests,
                    "assertions": assertions,
                },
            )
        return {
            "scope": (
                "real headless Chrome, actual Preact ControlPanel, local Vite proxy, and deterministic "
                "production routes; deterministic in-page fake microphone and system MediaStreams"
            ),
            "all_checks_passed": True,
            "backend": {"base_url": backend_url, "proxy_target": f"{BACKEND_HOST}:{BACKEND_PORT}"},
            "vite": {
                "base_url": vite_url,
                "dev_base_override": "/",
                "served_actual_control_panel": True,
            },
            "chrome": {
                "headless": True,
                "fresh_profile": True,
                "microphone": "in-page oscillator MediaStream returned from getUserMedia",
                "system_lane": "in-page oscillator MediaStream; getDisplayMedia picker was not invoked",
            },
            "mounted": mounted,
            "ready": ready,
            "active": active,
            "reattached": reattached,
            "session_id": session_id,
            "reattach_storage": {
                "key": REATTACH_STORAGE_KEY,
                "before": reattach_before,
                "after": reattach_after,
            },
            "server_status": {
                "before_reload": server_before_reload,
                "after_reload": server_after_reload,
            },
            "transcript_continuity": {
                "frontend_before_reload": frontend_before_reload,
                "frontend_after_reload": frontend_after_reload,
                "server_cursors_before_reload": cursors_before_reload,
                "server_cursors_after_reload": cursors_after_reload,
                "pre_reload_poller_reads": pre_reload_poller_reads,
            },
            "post_reload_read_only_requests": post_reload_reads,
            "stop_requests_for_session": stop_requests,
            "assertions": assertions,
            "descriptor": {
                "status": descriptor["status"],
                "frame_samples": negotiated_descriptor["frame_samples"],
            },
            "does_not_cover": [
                "browser's real permission prompt (media APIs are deterministic test doubles)",
                "display capture",
                "model inference",
                "a deployed host",
                "reload-after-terminal cleanup",
            ],
        }
    finally:
        if page is not None:
            page.close()
        if vite is not None:
            _stop_process_group(vite)
        if backend_server is not None and backend_thread is not None:
            _stop_backend(app, backend_server, backend_thread)
        else:
            app.state.prototype_scratch.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome-bin")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "evidence" / "phase1" / "y6-browser-reload" / "iteration-3-live-reload.json",
    )
    args = parser.parse_args()
    result = {
        "probe": "prototypes/browser-capture-feasibility/probe_g6_browser_reload.py",
        "started_at_unix_seconds": round(time.time(), 3),
    }
    try:
        result.update(_run(_chrome_binary(args.chrome_bin)))
    except _ProbeFailure as error:
        result.update({"all_checks_passed": False, "error": str(error), "details": error.details})
    except Exception as error:
        result.update({"all_checks_passed": False, "error": f"{type(error).__name__}: {error}"})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
