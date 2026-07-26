from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_live_api import (
    LIVE_AUTH_FINGERPRINT,
    AuthorizedLiveClient,
    frame_payload,
    make_live_runtime,
)


BASE_INDEX_SHA256 = "aaa308fa135e8e29ed1d96e9b9417952959c9c0218f783ddd4b62ff249a6e43d"
EXPECTED_LIVE_API = {
    ("GET", "/api/live/descriptor"),
    ("POST", "/api/live/pairing-codes"),
    ("POST", "/api/live/pairings"),
    ("POST", "/api/live/sessions"),
    ("POST", "/api/live/sessions/{session_id}/frames"),
    ("POST", "/api/live/sessions/{session_id}/heartbeat"),
    ("GET", "/api/live/sessions/{session_id}/snapshot"),
    ("GET", "/api/live/sessions/{session_id}/events"),
    ("POST", "/api/live/sessions/{session_id}/stop"),
    ("POST", "/api/live/sessions/{session_id}/abort"),
    ("DELETE", "/api/live/devices/{device_id}"),
}


def _make_live_app(tmpdir: str | Path):
    from moss_transcribe_diarize.app.server import create_app

    return create_app(
        model_path="fake-model",
        runs_dir=tmpdir,
        live_enabled=True,
        live_runtime_factory=lambda: make_live_runtime(max_retained_samples=16),
        live_auth_state_path=Path(tmpdir) / "live-auth.json",
        live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
        live_helper_lease_seconds=30.0,
    )


def _live_api_routes(app) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for route in app.routes:
        if not route.path.startswith("/api/live"):
            continue
        for method in route.methods or ():
            if method not in {"HEAD", "OPTIONS"}:
                routes.add((method, route.path))
    return routes


def _paired_live_client(app) -> AuthorizedLiveClient:
    from fastapi.testclient import TestClient

    local = TestClient(
        app,
        base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    lan = TestClient(
        app,
        base_url="https://moss.lan",
        client=("192.168.68.20", 50001),
    )
    issued = local.post("/api/live/pairing-codes")
    paired = lan.post(
        "/api/live/pairings",
        json={"device_id": "portal-device", "pairing_payload": issued.json()["pairing_payload"]},
    )
    if issued.status_code != 200 or paired.status_code != 200:
        raise AssertionError("live pairing failed")
    return AuthorizedLiveClient(app, paired.json()["device_token"])


class LivePortalRouteTest(unittest.TestCase):
    def test_live_portal_is_absent_by_default_and_batch_root_is_byte_exact(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(model_path="fake-model", runs_dir=tmpdir)
            client = TestClient(app)

            portal = client.get("/live")
            batch = client.get("/")

            self.assertEqual(portal.status_code, 404)
            self.assertEqual(batch.status_code, 200)
            self.assertEqual(batch.headers.get("cache-control"), "no-store")
            self.assertEqual(hashlib.sha256(batch.content).hexdigest(), BASE_INDEX_SHA256)

    def test_live_portal_is_enabled_no_store_and_does_not_add_live_api_routes(self):
        from fastapi.testclient import TestClient
        from moss_transcribe_diarize.app.server import create_app

        with tempfile.TemporaryDirectory() as tmpdir:
            app = create_app(
                model_path="fake-model",
                runs_dir=tmpdir,
                live_enabled=True,
                live_runtime_factory=lambda: make_live_runtime(max_retained_samples=16),
                live_auth_state_path=Path(tmpdir) / "live-auth.json",
                live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
                live_helper_lease_seconds=30.0,
            )
            client = TestClient(app)

            portal = client.get("/live")

            self.assertEqual(portal.status_code, 200)
            self.assertEqual(portal.headers.get("cache-control"), "no-store")
            self.assertTrue(portal.headers.get("content-type", "").startswith("text/html"))
            self.assertIn('id="livePortal"', portal.text)
            self.assertEqual(_live_api_routes(app), EXPECTED_LIVE_API)

    def test_live_portal_document_uses_manual_memory_only_authority_shell(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            app = _make_live_app(tmpdir)
            html = TestClient(app).get("/live").text
            lower = html.lower()

            self.assertIn('id="sessionId"', html)
            self.assertIn('id="viewToken"', html)
            self.assertIn('type="password"', html)
            self.assertIn('autocomplete="off"', html)
            self.assertIn("Authorization", html)
            self.assertIn("Bearer ", html)
            self.assertIn("/api/live/sessions/", html)
            self.assertIn("since_version", html)
            self.assertIn("since_seq", html)
            self.assertIn("disconnected", html)
            self.assertIn("reconnecting", html)
            self.assertNotIn("localhost", lower)
            self.assertNotIn("127.0.0.1", lower)
            self.assertNotIn("websocket", lower)
            self.assertNotIn("eventsource", lower)
            self.assertNotIn("localstorage", lower)
            self.assertNotIn("sessionstorage", lower)
            self.assertNotIn("document.cookie", lower)
            self.assertNotIn(".innerHTML", html)
            self.assertEqual(
                set(re.findall(r"""/api/live/[^\s"'`]+""", html)),
                {
                    "/api/live/sessions/${encodeURIComponent(sessionId)}/snapshot?since_version=${snapshotVersion}",
                    "/api/live/sessions/${encodeURIComponent(sessionId)}/events?since_seq=${eventSequence}",
                    "/api/live/sessions/${encodeURIComponent(sessionId)}/stop",
                    "/api/live/sessions/${encodeURIComponent(sessionId)}/abort",
                },
            )

    def test_live_portal_stop_deadline_drains_real_pending_work(self):
        from moss_transcribe_diarize.app.server import create_app

        for deadline, expected_status, expected_state in (
            (0.0, 409, "active"),
            (5.0, 200, "closed"),
        ):
            with self.subTest(deadline=deadline), tempfile.TemporaryDirectory() as tmpdir:
                app = create_app(
                    model_path="fake-model",
                    runs_dir=tmpdir,
                    live_enabled=True,
                    live_runtime_factory=lambda: make_live_runtime(
                        max_retained_samples=8,
                        speech=(True,),
                    ),
                    live_auth_state_path=Path(tmpdir) / "live-auth.json",
                    live_server_cert_sha256=LIVE_AUTH_FINGERPRINT,
                    live_helper_lease_seconds=30.0,
                )
                client = _paired_live_client(app)
                session_id = client.post("/api/live/sessions").json()["id"]
                accepted = client.post(
                    f"/api/live/sessions/{session_id}/frames",
                    json=frame_payload(0, 4),
                )
                stopped = client.post(
                    f"/api/live/sessions/{session_id}/stop",
                    json={"deadline": deadline},
                )

                self.assertEqual(accepted.status_code, 200)
                self.assertEqual(stopped.status_code, expected_status)
                self.assertEqual(stopped.json()["snapshot"]["session"]["status"], expected_state)
                if deadline > 0:
                    self.assertEqual(stopped.json()["snapshot"]["session"]["accounted_samples"], 4)

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_browser_contract_polls_renders_controls_and_stops(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_browser_contract_probe(html)

        first_snapshot, first_events, second_snapshot, second_events = probe["pollRequests"]
        self.assertEqual(first_snapshot["method"], "GET")
        self.assertIn("/api/live/sessions/portal-session%2Falpha/snapshot?since_version=0", first_snapshot["url"])
        self.assertEqual(first_snapshot["headers"]["Authorization"], "Bearer portal-view-secret")
        self.assertEqual(first_snapshot["cache"], "no-store")
        self.assertEqual(first_snapshot["credentials"], "same-origin")
        self.assertIn("/api/live/sessions/portal-session%2Falpha/events?since_seq=0", first_events["url"])
        self.assertEqual(first_events["headers"]["Authorization"], "Bearer portal-view-secret")
        self.assertIn("since_version=2", second_snapshot["url"])
        self.assertIn("since_seq=3", second_events["url"])
        for request in probe["pollRequests"] + probe["controlRequests"]:
            self.assertNotIn("portal-view-secret", request["url"])
        self.assertEqual(probe["eventRows"], ["seq: 1 | kind: opened | snapshot: 2", "seq: 3 | kind: partial | snapshot: 2", "seq: 4 | kind: commit | snapshot: 4"])
        self.assertIn("hello <script>", probe["transcriptBeforeControls"])
        self.assertEqual(
            probe["statusDetailAfterSecondPoll"],
            "\n".join(
                (
                    "state: active",
                    "version: 4",
                    "accepted samples: 12",
                    "accounted samples: 12",
                    "retained samples: 2",
                    "pending work: 0",
                )
            ),
        )
        self.assertNotIn("portal-view-secret", probe["domText"])
        self.assertNotIn("portal-session/alpha", probe["domText"])
        self.assertEqual(probe["inputsAfterConnect"], {"session": "", "token": ""})

        stop_request, abort_request = probe["controlRequests"]
        self.assertIn("/api/live/sessions/portal-session%2Falpha/stop", stop_request["url"])
        self.assertEqual(stop_request["method"], "POST")
        self.assertEqual(stop_request["headers"]["Authorization"], "Bearer portal-view-secret")
        self.assertEqual(json.loads(stop_request["body"]), {"deadline": 5.0})
        self.assertIn("/api/live/sessions/portal-session%2Falpha/abort", abort_request["url"])
        self.assertEqual(abort_request["method"], "POST")
        self.assertEqual(abort_request["headers"]["Authorization"], "Bearer portal-view-secret")
        self.assertEqual(json.loads(abort_request["body"]), {"reason": "operator abort"})
        self.assertEqual(probe["terminalState"], "aborted")
        self.assertEqual(probe["connectionState"], "disconnected")
        self.assertTrue(probe["stopDisabledAfterTerminal"])
        self.assertEqual(probe["activeTimersAfterTerminal"], 0)

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_browser_contract_retries_without_cursor_gap_or_overlap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_retry_contract_probe(html)

        self.assertEqual(len(probe["requests"]), 3)
        self.assertIn("since_version=0", probe["requests"][0]["url"])
        self.assertIn("since_version=0", probe["requests"][1]["url"])
        self.assertIn("since_seq=0", probe["requests"][2]["url"])
        self.assertEqual(probe["retryDelays"], [0, 500])
        self.assertEqual(probe["maxPendingTimers"], 1)
        self.assertEqual(probe["statusAfterFailure"], "Reconnecting: malformed snapshot session")
        self.assertEqual(probe["connectionAfterClosed"], "disconnected")
        self.assertEqual(probe["requestsAfterTerminalTimer"], 3)

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_connect_and_control_failure_banners_do_not_echo_authority(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_control_failure_contract_probe(html)

        self.assertEqual(probe["statusAfterConnect"], "Waiting for first server snapshot.")
        self.assertEqual(probe["statusAfterFailure"], "stop failed: closing")
        self.assertNotIn("failure-session", probe["statusAfterConnect"] + probe["statusAfterFailure"])
        self.assertNotIn("failure-token", probe["statusAfterConnect"] + probe["statusAfterFailure"])
        self.assertNotIn("failure-token", probe["controlRequest"]["url"])

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_poll_and_control_use_independent_cancellation(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        overlap = _run_overlap_contract_probe(html)
        self.assertFalse(overlap["pollAbortedAfterControl"])
        self.assertEqual(overlap["controlStatus"], "closing")
        self.assertNotIn("Reconnecting", overlap["statusAfterControl"])

        disconnected = _run_disconnect_overlap_contract_probe(html)
        self.assertTrue(disconnected["pollAborted"])
        self.assertTrue(disconnected["controlAborted"])
        self.assertEqual(disconnected["connectionState"], "disconnected")

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_poll_timeout_aborts_and_recovers_with_bounded_retry(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_timeout_contract_probe(html)

        self.assertTrue(probe["hungRequestAborted"])
        self.assertEqual(probe["statusAfterTimeout"], "Reconnecting: request timed out")
        self.assertIn(500, probe["timerDelays"])
        self.assertEqual(probe["requestCount"], 3)
        self.assertEqual(probe["connectionState"], "disconnected")


def test_live_portal_caplog_and_root_logging_do_not_emit_authority_or_audio_secrets(caplog, capsys):
    from fastapi.testclient import TestClient

    secrets = (
        "portal-session-secret",
        "portal-view-token-secret",
        "portal-pairing-payload-secret",
        "portal-device-credential-secret",
        "portal transcript should not log",
        "raw-pcm-secret-bytes",
    )
    caplog.set_level(logging.DEBUG)
    logging.getLogger().warning("caplog root probe")
    logging.getLogger("moss_transcribe_diarize.app.live_portal").warning("caplog module probe")
    assert "caplog root probe" in caplog.text
    assert "caplog module probe" in caplog.text
    caplog.clear()
    capsys.readouterr()

    with tempfile.TemporaryDirectory() as tmpdir:
        app = _make_live_app(tmpdir)
        client = TestClient(app)
        response = client.get(
            "/live",
            headers={
                "Authorization": f"Bearer {secrets[1]}",
                "X-Portal-Session-Probe": secrets[0],
                "X-Portal-Pairing-Probe": secrets[2],
                "X-Portal-Device-Probe": secrets[3],
                "X-Portal-Transcript-Probe": secrets[4],
                "X-Portal-Pcm-Probe": secrets[5],
            },
        )

    assert response.status_code == 200
    captured = capsys.readouterr()
    emitted = caplog.text + captured.out + captured.err
    for secret in secrets:
        assert secret not in emitted


def _extract_portal_script(html: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    if len(scripts) != 1:
        raise AssertionError(f"expected one inline portal script, found {len(scripts)}")
    return scripts[0]


def _run_node_probe(html: str, scenario: str) -> dict:
    script = _extract_portal_script(html)
    node_program = f"""
const portalScript = {json.dumps(script)};
const scenario = {json.dumps(scenario)};

function makeClassList(initial) {{
  const classes = new Set(initial || []);
  return {{
    classes,
    toggle(name, force) {{
      if (force) {{
        classes.add(name);
      }} else {{
        classes.delete(name);
      }}
    }},
    remove(name) {{
      classes.delete(name);
    }},
    contains(name) {{
      return classes.has(name);
    }},
  }};
}}

function makeNode(id) {{
  const node = {{
    id,
    value: "",
    disabled: false,
    listeners: {{}},
    childNodes: [],
    children: [],
    classList: makeClassList(["empty"]),
    addEventListener(type, handler) {{
      this.listeners[type] = handler;
    }},
    appendChild(child) {{
      const incoming = child.childNodes || [child];
      for (const item of incoming) {{
        this.childNodes.push(item);
        this.children.push(item);
      }}
      this._text = this.childNodes.map((item) => item.textContent || "").join("");
    }},
  }};
  Object.defineProperty(node, "textContent", {{
    get() {{
      return this._text || "";
    }},
    set(value) {{
      this._text = value == null ? "" : String(value);
      this.childNodes = [];
      this.children = [];
    }},
  }});
  return node;
}}

function installPortal(responses) {{
  const nodes = {{}};
  const requests = [];
  const timers = [];
  const clearedTimers = new Set();
  const timerDelays = [];
  let nextTimerId = 1;
  let maxPendingTimers = 0;
  const storageWrites = [];
  const windowListeners = {{}};
  const document = {{
    getElementById(id) {{
      if (!nodes[id]) {{
        nodes[id] = makeNode(id);
      }}
      return nodes[id];
    }},
    createDocumentFragment() {{
      return {{
        childNodes: [],
        appendChild(node) {{
          this.childNodes.push(node);
        }},
      }};
    }},
    createElement(id) {{
      return makeNode(id);
    }},
  }};
  const window = {{
    addEventListener(type, handler) {{
      windowListeners[type] = handler;
    }},
    setTimeout(handler, delay) {{
      const timer = {{ id: nextTimerId, handler, delay }};
      nextTimerId += 1;
      timers.push(timer);
      timerDelays.push(delay);
      maxPendingTimers = Math.max(maxPendingTimers, timers.filter((item) => !clearedTimers.has(item.id)).length);
      return timer.id;
    }},
    clearTimeout(id) {{
      clearedTimers.add(id);
    }},
  }};
  const storage = new Proxy({{}}, {{
    set(target, key, value) {{
      storageWrites.push([String(key), String(value)]);
      target[key] = value;
      return true;
    }},
  }});
  global.document = document;
  global.window = window;
  global.clearTimeout = window.clearTimeout;
  global.localStorage = storage;
  global.sessionStorage = storage;
  global.fetch = async (url, options) => {{
    const request = {{
      url: String(url),
      method: options && options.method ? options.method : "GET",
      headers: options && options.headers ? options.headers : {{}},
      body: options && options.body ? options.body : null,
      cache: options && options.cache,
      credentials: options && options.credentials,
      aborted: Boolean(options && options.signal && options.signal.aborted),
    }};
    requests.push(request);
    const next = responses.shift();
    if (!next) {{
      throw new Error("no fake response queued");
    }}
    if (next.hang) {{
      return await new Promise((resolve, reject) => {{
        const abort = () => {{
          request.aborted = true;
          reject(new DOMException("request aborted", "AbortError"));
        }};
        if (options && options.signal && options.signal.aborted) {{
          abort();
        }} else if (options && options.signal) {{
          options.signal.addEventListener("abort", abort, {{ once: true }});
        }}
      }});
    }}
    if (next.throwMessage) {{
      throw new Error(next.throwMessage);
    }}
    return {{
      ok: next.ok !== false,
      status: next.status || 200,
      json: async () => {{
        if (next.jsonError) {{
          throw new Error(next.jsonError);
        }}
        return next.payload;
      }},
    }};
  }};
  eval(portalScript);
  async function flush() {{
    for (let index = 0; index < 30; index += 1) {{
      await Promise.resolve();
    }}
  }}
  async function runNextTimer() {{
    while (timers.length && clearedTimers.has(timers[0].id)) {{
      timers.shift();
    }}
    const timer = timers.shift();
    if (!timer) {{
      throw new Error("expected scheduled timer");
    }}
    if (!clearedTimers.has(timer.id)) {{
      timer.handler();
    }}
    await flush();
  }}
  return {{ nodes, requests, timers, timerDelays, storageWrites, windowListeners, runNextTimer, flush, maxPendingTimers: () => maxPendingTimers, activeTimerCount: () => timers.filter((item) => !clearedTimers.has(item.id)).length }};
}}

const snapshots = {{
  active2: {{ snapshot: {{ session: {{ status: "active", version: 2, accepted_samples: 10, accounted_samples: 8, retained_samples: 4, committed: [{{ transcript: "hello <script>" }}], provisional: {{ transcript: "draft & safe" }} }}, pending_work_items: 1 }} }},
  active4: {{ snapshot: {{ session: {{ status: "active", version: 4, accepted_samples: 12, accounted_samples: 12, retained_samples: 2, committed: [{{ transcript: "hello <script>" }}], provisional: null }}, pending_work_items: 0 }} }},
  closing5: {{ snapshot: {{ session: {{ status: "closing", version: 5, accepted_samples: 12, accounted_samples: 12, retained_samples: 0, committed: [], provisional: null }}, pending_work_items: 0 }} }},
  aborted6: {{ snapshot: {{ session: {{ status: "aborted", version: 6, accepted_samples: 12, accounted_samples: 12, retained_samples: 0, committed: [], provisional: null, failure_reason: "operator abort" }}, terminal_failure: {{ kind: "operator", code: "abort", detail: "typed failure" }}, pending_work_items: 0 }} }},
  closed7: {{ snapshot: {{ session: {{ status: "closed", version: 7, accepted_samples: 0, accounted_samples: 0, retained_samples: 0, committed: [], provisional: null }}, pending_work_items: 0 }} }},
}};

async function runHappy() {{
  const env = installPortal([
    {{ payload: snapshots.active2 }},
    {{ payload: {{ events: [{{ seq: 1, kind: "opened", snapshot_version: 2 }}, {{ seq: 1, kind: "opened", snapshot_version: 2 }}, {{ seq: 3, kind: "partial", snapshot_version: 2 }}] }} }},
    {{ payload: snapshots.active4 }},
    {{ payload: {{ events: [{{ seq: 3, kind: "partial", snapshot_version: 2 }}, {{ seq: 4, kind: "commit", snapshot_version: 4 }}] }} }},
    {{ payload: snapshots.closing5 }},
    {{ payload: snapshots.aborted6 }},
  ]);
  env.nodes.sessionId.value = "portal-session/alpha";
  env.nodes.viewToken.value = "portal-view-secret";
  env.nodes.connectButton.listeners.click();
  const inputsAfterConnect = {{ session: env.nodes.sessionId.value, token: env.nodes.viewToken.value }};
  await env.runNextTimer();
  await env.runNextTimer();
  const pollRequests = env.requests.slice();
  const transcriptBeforeControls = env.nodes.transcript.textContent;
  const statusDetailAfterSecondPoll = env.nodes.statusDetail.textContent;
  env.nodes.stopButton.listeners.click();
  await env.flush();
  env.nodes.abortButton.listeners.click();
  await env.flush();
  const controlRequests = env.requests.slice(pollRequests.length);
  const domText = Object.values(env.nodes).map((node) => node.textContent).join("\\n");
  const eventRows = env.nodes.events.children.map((node) => node.textContent);
  const result = {{
    pollRequests,
    controlRequests,
    eventRows,
    transcriptBeforeControls,
    statusDetailAfterSecondPoll,
    domText,
    inputsAfterConnect,
    terminalState: env.nodes.serverState.textContent,
    connectionState: env.nodes.connectionState.textContent,
    stopDisabledAfterTerminal: env.nodes.stopButton.disabled,
    activeTimersAfterTerminal: env.activeTimerCount(),
    storageWrites: env.storageWrites,
  }};
  console.log(JSON.stringify(result));
}}

async function runRetry() {{
  const env = installPortal([
    {{ payload: {{ snapshot: {{ session: {{ status: "nonsense", version: 5, committed: [], provisional: null }} }} }} }},
    {{ payload: snapshots.closed7 }},
    {{ payload: {{ events: [] }} }},
    {{ payload: snapshots.closed7 }},
  ]);
  env.nodes.sessionId.value = "retry-session";
  env.nodes.viewToken.value = "retry-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  const statusAfterFailure = env.nodes.statusDetail.textContent;
  await env.runNextTimer();
  const connectionAfterClosed = env.nodes.connectionState.textContent;
  if (env.activeTimerCount()) {{
    await env.runNextTimer();
  }}
  const result = {{
    requests: env.requests,
    retryDelays: env.timerDelays.filter((delay) => delay < 10000),
    maxPendingTimers: env.maxPendingTimers(),
    statusAfterFailure,
    connectionAfterClosed,
    requestsAfterTerminalTimer: env.requests.length,
    storageWrites: env.storageWrites,
  }};
  console.log(JSON.stringify(result));
}}

async function runControlFailure() {{
  const env = installPortal([
    {{ ok: false, status: 409, payload: {{ failure: {{ code: "closing" }} }} }},
  ]);
  env.nodes.sessionId.value = "failure-session";
  env.nodes.viewToken.value = "failure-token";
  env.nodes.connectButton.listeners.click();
  const statusAfterConnect = env.nodes.statusDetail.textContent;
  env.nodes.stopButton.listeners.click();
  await env.flush();
  console.log(JSON.stringify({{
    statusAfterConnect,
    statusAfterFailure: env.nodes.statusDetail.textContent,
    controlRequest: env.requests[0],
  }}));
}}

async function runOverlap() {{
  const env = installPortal([
    {{ hang: true }},
    {{ payload: snapshots.closing5 }},
  ]);
  env.nodes.sessionId.value = "overlap-session";
  env.nodes.viewToken.value = "overlap-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  env.nodes.stopButton.listeners.click();
  await env.flush();
  const result = {{
    pollAbortedAfterControl: env.requests[0].aborted,
    controlStatus: env.nodes.serverState.textContent,
    statusAfterControl: env.nodes.statusDetail.textContent,
  }};
  env.nodes.disconnectButton.listeners.click();
  await env.flush();
  console.log(JSON.stringify(result));
}}

async function runDisconnectOverlap() {{
  const env = installPortal([
    {{ hang: true }},
    {{ hang: true }},
  ]);
  env.nodes.sessionId.value = "disconnect-session";
  env.nodes.viewToken.value = "disconnect-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  env.nodes.stopButton.listeners.click();
  await env.flush();
  env.nodes.disconnectButton.listeners.click();
  await env.flush();
  console.log(JSON.stringify({{
    pollAborted: env.requests[0].aborted,
    controlAborted: env.requests[1].aborted,
    connectionState: env.nodes.connectionState.textContent,
  }}));
}}

async function runTimeout() {{
  const env = installPortal([
    {{ hang: true }},
    {{ payload: snapshots.closed7 }},
    {{ payload: {{ events: [] }} }},
  ]);
  env.nodes.sessionId.value = "timeout-session";
  env.nodes.viewToken.value = "timeout-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  await env.runNextTimer();
  const statusAfterTimeout = env.nodes.statusDetail.textContent;
  await env.runNextTimer();
  console.log(JSON.stringify({{
    hungRequestAborted: env.requests[0].aborted,
    statusAfterTimeout,
    timerDelays: env.timerDelays,
    requestCount: env.requests.length,
    connectionState: env.nodes.connectionState.textContent,
  }}));
}}

const scenarios = {{
  happy: runHappy,
  retry: runRetry,
  controlFailure: runControlFailure,
  overlap: runOverlap,
  disconnectOverlap: runDisconnectOverlap,
  timeout: runTimeout,
}};
scenarios[scenario]().catch((error) => {{
  console.error(error && error.stack ? error.stack : String(error));
  process.exit(1);
}});
"""
    completed = subprocess.run(
        [shutil.which("node") or "node"],
        input=node_program,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)


def _run_browser_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "happy")


def _run_retry_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "retry")


def _run_control_failure_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "controlFailure")


def _run_overlap_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "overlap")


def _run_disconnect_overlap_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "disconnectOverlap")


def _run_timeout_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "timeout")
