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
    ("DELETE", "/api/live/sessions/{session_id}/view"),
    ("DELETE", "/api/live/devices/{device_id}"),
}


REPO_ROOT = Path(__file__).resolve().parents[1]
# Every fact the IDEA-038 acceptance package holds at evidence tier `Missing`.
# The fence below requires the whole claim set in each document, not a token.
IDEA_038_MISSING_FACTS = (
    "secure automated browser handoff",
    "signing",
    "notarization",
    "TCC",
    "Keychain runtime",
    "real permission/device/tap behavior",
    "real lease value",
    "history/artifacts",
    "deployment",
    "60/300 evidence",
    "Windows production",
    "canary",
    "live enablement",
)
IDEA_038_REQUIRED_CLAIMS = (
    "5-second stop-drain",
    "10-second poll request timeout",
    "10-second control request timeout",
    "renderedEventOrder",
    "events DOM row count",
    "terminal snapshot or event, not durable portal history or artifacts",
    "remain Missing",
)
IDEA_038_REJECTED_CERTIFICATIONS = (
    r"certif",
    r"production proof",
    r"sufficient",
    r"prove[sd]?\s+(signing|notarization|TCC|deployment|enablement|production)",
    r"ready for (production|deployment|notarization)",
)


def _flatten(lines) -> str:
    return " ".join(" ".join(lines).split())


def _context_idea_038_claim_block() -> str:
    lines = (REPO_ROOT / "CONTEXT.md").read_text(encoding="utf-8").splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if line.startswith("- **Local portal/helper integration (IDEA-038)**")
    ]
    if len(starts) != 1:
        raise AssertionError(f"expected one IDEA-038 CONTEXT.md entry, found {len(starts)}")
    end = starts[0] + 1
    while end < len(lines) and not lines[end].startswith("- "):
        end += 1
    return _flatten(lines[starts[0]:end])


def _adr_idea_038_claim_block() -> str:
    text = (REPO_ROOT / "docs/adr/0001-live-v2-json-http-contract.md").read_text(encoding="utf-8")
    paragraphs = [block for block in text.split("\n\n") if block.startswith("IDEA-038 ")]
    if len(paragraphs) != 1:
        raise AssertionError(f"expected one IDEA-038 ADR paragraph, found {len(paragraphs)}")
    return _flatten(paragraphs[0].splitlines())


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
            self.assertIn('role="status"', html)
            self.assertIn('aria-live="polite"', html)
            self.assertIn("controlRequestTimeoutMs = 10000", html)
            self.assertIn("maxRenderedEvents = 200", html)
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
                    "helper: capturing",
                    "helper sequence: 2",
                    "helper microphone: failed | epoch: 1 | dropped: 3 | discontinuities: 1 | code: permission_denied",
                    "helper system: capturing | epoch: 1 | dropped: 0 | discontinuities: 0",
                    "v2 status: active",
                    "v2 microphone: failed | next: 2 | accepted: 8 | accounted: 4 | failed: 4 | retained: 0 | epoch: 1 | code: permission_denied",
                    "v2 system: active | next: 2 | accepted: 8 | accounted: 8 | failed: 0 | retained: 0 | epoch: 1",
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
        self.assertEqual(probe["storageWrites"], [])

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_browser_contract_retries_without_cursor_gap_or_overlap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_retry_contract_probe(html)

        self.assertEqual(len(probe["requests"]), 4)
        self.assertIn("since_version=0", probe["requests"][0]["url"])
        self.assertIn("since_seq=0", probe["requests"][1]["url"])
        self.assertIn("since_version=0", probe["requests"][2]["url"])
        self.assertIn("since_seq=0", probe["requests"][3]["url"])
        self.assertEqual(probe["retryDelays"], [0, 500])
        self.assertEqual(
            probe["maxPendingTimers"],
            2,
            "the concurrent snapshot/events pair has one bounded timeout per request",
        )
        self.assertEqual(probe["statusAfterFailure"], "Reconnecting: malformed snapshot session")
        self.assertEqual(probe["connectionAfterClosed"], "disconnected")
        self.assertEqual(probe["requestsAfterTerminalTimer"], 4)
        self.assertEqual(probe["storageWrites"], [])

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_shows_a_corrected_speaker_without_changing_the_words(self):
        """ADR-0002's living document, at the only place a reader ever sees one.

        A span published under one speaker and corrected by a retrospective sweep must read
        as the corrected speaker -- and must read as *the same words*, because a rewriter
        that could alter speech would be a worse defect than the mislabelling it fixes. The
        revision count appears only once something has actually been corrected: a meeting
        whose live labels stood has nothing to say about revisions, and saying "0" invites a
        reader to wonder what went wrong.
        """

        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_label_revision_contract_probe(html)

        self.assertEqual(probe["transcriptBefore"], "[0][S01]who said this[1]")
        self.assertEqual(probe["transcriptAfter"], "[0][S03]who said this[1]")
        self.assertNotIn("label revisions", probe["statusBefore"])
        self.assertIn("label revisions: 1", probe["statusAfter"].splitlines())

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
        self.assertTrue(disconnected["eventsAborted"])
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
        self.assertEqual(probe["requestCount"], 4)
        self.assertEqual(probe["connectionState"], "disconnected")

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_failed_concurrent_fetch_aborts_its_sibling_before_retry(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_concurrent_failure_contract_probe(html)

        self.assertTrue(probe["eventsSiblingAborted"])
        self.assertEqual(probe["status"], "Reconnecting: snapshot unavailable")
        self.assertEqual(probe["retryDelays"], [0, 500])

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_control_timeout_uses_independent_10_second_abort(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_control_timeout_contract_probe(html)

        self.assertTrue(probe["controlAborted"])
        self.assertEqual(probe["requestCount"], 1)
        self.assertEqual(probe["pendingPollTimers"], [0])
        self.assertEqual(probe["statusAfterTimeout"], "stop failed: request timed out")
        self.assertEqual(probe["controlTimerDelays"], [10000])

    @unittest.skipUnless(shutil.which("node"), "node is required for browser-contract probe")
    def test_live_portal_event_identity_order_and_dom_share_one_cap(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        probe = _run_event_retention_contract_probe(html)

        self.assertEqual(probe["rowCount"], 200)
        self.assertEqual(probe["firstRow"], "seq: 7 | kind: replay | snapshot: 4")
        self.assertEqual(probe["lastRow"], "seq: 206 | kind: tail | snapshot: 4")
        self.assertEqual(probe["seq200Rows"], 1)
        self.assertIn("since_seq=205", probe["secondEventsUrl"])
        # Identity, order and DOM are three separately enforced bounds: losing
        # any one of them must fail on its own, not only in combination.
        self.assertEqual(probe["cap"], 200)
        self.assertEqual(probe["identitySize"], 200)
        self.assertEqual(probe["orderLength"], 200)
        self.assertEqual(probe["domRowCount"], 200)
        self.assertEqual(probe["domRowCount"], probe["rowCount"])

    def test_live_portal_poll_cadence_and_the_app_render_bound_are_one_number(self):
        """The PRD's user-visible latency is measured as `committedP95 + renderBound`, and the
        render bound's leading term is the app's *restatement* of this page's poll cadence. The app
        schedules nothing from its copy and this page reads nothing from the app's, so the two can
        drift apart in either direction with every other assertion still green: move the Swift
        constant alone and a gated number improves with no change to what a reader waits; move this
        one alone and a reader gains time the gate never records. Fail on either.
        """
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text
        script = _extract_portal_script(html)

        served = re.findall(r"const pollDelayMs = (\d+);", script)
        self.assertEqual(len(served), 1, "the served portal must declare its poll cadence once")
        served_ms = float(served[0])

        # A constant nothing reads would satisfy the equality below while the page polled at any
        # rate at all, so the cadence has to be what actually schedules the next cycle.
        self.assertIn("schedulePoll(pollDelayMs)", script)
        self.assertIn(
            "await Promise.all([",
            script,
            "snapshot and events must start together so the browser pays the slower fetch, not both",
        )
        self.assertNotIn(
            "const snapshotPayload = await fetchPollJson",
            script,
            "the old serial first fetch would delay every events request behind snapshot latency",
        )

        swift = (
            REPO_ROOT / "macos/MOSSCapture/Sources/MOSSCaptureCore/CaptureLatencyProbe.swift"
        ).read_text(encoding="utf-8")
        declared = re.findall(r"portalCycleSeconds: Double = ([0-9.]+)", swift)
        self.assertEqual(len(declared), 1, "the app must declare the portal cycle once")
        self.assertEqual(
            float(declared[0]) * 1000.0,
            served_ms,
            "the app's reported render bound and the portal's actual poll schedule disagree: "
            f"portalCycleSeconds={declared[0]} s vs pollDelayMs={served[0]} ms",
        )

        # And the term must still reach the sum: a literal substituted for the constant would keep
        # the two declarations equal while the reported bound stopped describing this page.
        self.assertIn(
            "max(snapshotP95, eventsP95)",
            swift,
            "the concurrent browser pays the slower p95 fetch once, not the serial sum",
        )

    def test_idea_038_context_and_adr_keep_portal_constants_and_evidence_tier_missing(self):
        from fastapi.testclient import TestClient

        with tempfile.TemporaryDirectory() as tmpdir:
            html = TestClient(_make_live_app(tmpdir)).get("/live").text

        # The documented constants are the ones the portal actually ships.
        self.assertIn("stopDrainDeadlineSeconds = 5.0", html)
        self.assertIn("pollRequestTimeoutMs = 10000", html)
        self.assertIn("controlRequestTimeoutMs = 10000", html)
        self.assertIn("maxRenderedEvents = 200", html)

        blocks = {
            "CONTEXT.md": _context_idea_038_claim_block(),
            "ADR-0001": _adr_idea_038_claim_block(),
        }
        for name, block in blocks.items():
            with self.subTest(document=name):
                for claim in IDEA_038_REQUIRED_CLAIMS:
                    self.assertIn(claim, block, f"{name} dropped the claim {claim!r}")
                for fact in IDEA_038_MISSING_FACTS:
                    self.assertIn(fact, block, f"{name} dropped the Missing fact {fact!r}")
                for pattern in IDEA_038_REJECTED_CERTIFICATIONS:
                    self.assertIsNone(
                        re.search(pattern, block, flags=re.IGNORECASE),
                        f"{name} certifies evidence this slice does not produce: {pattern!r}",
                    )


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
      const incoming = child.childNodes && child.childNodes.length ? child.childNodes : [child];
      for (const item of incoming) {{
        this.childNodes.push(item);
        this.children.push(item);
      }}
      this._text = this.childNodes.map((item) => item.textContent || "").join("");
    }},
    removeChild(child) {{
      const nodeIndex = this.childNodes.indexOf(child);
      if (nodeIndex >= 0) {{
        this.childNodes.splice(nodeIndex, 1);
      }}
      const childIndex = this.children.indexOf(child);
      if (childIndex >= 0) {{
        this.children.splice(childIndex, 1);
      }}
      this._text = this.childNodes.map((item) => item.textContent || "").join("");
      return child;
    }},
  }};
  Object.defineProperty(node, "firstChild", {{
    get() {{
      return this.childNodes.length ? this.childNodes[0] : null;
    }},
  }});
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
  Object.defineProperty(document, "cookie", {{
    get() {{
      return "";
    }},
    set(value) {{
      storageWrites.push(["document.cookie", String(value)]);
    }},
  }});
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
  async function runTimerWithDelay(delay) {{
    const index = timers.findIndex((timer) => timer.delay === delay && !clearedTimers.has(timer.id));
    if (index < 0) {{
      throw new Error(`expected scheduled timer with delay ${{delay}}`);
    }}
    const timer = timers.splice(index, 1)[0];
    timer.handler();
    await flush();
  }}
  return {{ nodes, requests, timers, timerDelays, storageWrites, windowListeners, runNextTimer, runTimerWithDelay, flush, maxPendingTimers: () => maxPendingTimers, activeTimerCount: () => timers.filter((item) => !clearedTimers.has(item.id)).length }};
}}

function helperPresence(state, sequence) {{
  return {{
    schema: "moss-live-helper-health.v1",
    instance_id: "helper-instance",
    sequence,
    sent_monotonic_ns: sequence * 100,
    last_seen_monotonic_ns: sequence * 100 + 1,
    helper_version: "test-helper",
    state,
    lanes: {{
      microphone: {{ state: "failed", device_epoch: 1, dropped_frames: 3, discontinuities: 1, failure_code: "permission_denied" }},
      system: {{ state: "capturing", device_epoch: 1, dropped_frames: 0, discontinuities: 0, failure_code: null }},
    }},
  }};
}}

function v2Session(status) {{
  return {{
    status,
    terminal_reason: null,
    lanes: {{
      microphone: {{ lane: "microphone", next_sequence: 2, accepted_samples: 8, accounted_samples: 4, failed_samples: 4, retained_samples: 0, current_device_epoch: 1, pruned_through_sequence: 1, health: "failed", failure_code: "permission_denied" }},
      system: {{ lane: "system", next_sequence: 2, accepted_samples: 8, accounted_samples: 8, failed_samples: 0, retained_samples: 0, current_device_epoch: 1, pruned_through_sequence: 1, health: "active", failure_code: null }},
    }},
  }};
}}

const snapshots = {{
  active2: {{ snapshot: {{ session: {{ status: "active", version: 2, accepted_samples: 10, accounted_samples: 8, retained_samples: 4, committed: [{{ transcript: "hello <script>" }}], provisional: {{ transcript: "draft & safe" }} }}, pending_work_items: 1 }}, helper_presence: helperPresence("capturing", 1), v2_session: v2Session("active") }},
  active4: {{ snapshot: {{ session: {{ status: "active", version: 4, accepted_samples: 12, accounted_samples: 12, retained_samples: 2, committed: [{{ transcript: "hello <script>" }}], provisional: null }}, pending_work_items: 0 }}, helper_presence: helperPresence("capturing", 2), v2_session: v2Session("active") }},
  closing5: {{ snapshot: {{ session: {{ status: "closing", version: 5, accepted_samples: 12, accounted_samples: 12, retained_samples: 0, committed: [], provisional: null }}, pending_work_items: 0 }}, helper_presence: helperPresence("capturing", 3), v2_session: v2Session("closing") }},
  aborted6: {{ snapshot: {{ session: {{ status: "aborted", version: 6, accepted_samples: 12, accounted_samples: 12, retained_samples: 0, committed: [], provisional: null, failure_reason: "operator abort" }}, terminal_failure: {{ kind: "operator", code: "abort", detail: "typed failure" }}, pending_work_items: 0 }}, helper_presence: null, v2_session: v2Session("aborted") }},
  closed7: {{ snapshot: {{ session: {{ status: "closed", version: 7, accepted_samples: 0, accounted_samples: 0, retained_samples: 0, committed: [], provisional: null }}, pending_work_items: 0 }}, helper_presence: null, v2_session: null }},
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
    {{ payload: {{ events: [] }} }},
    {{ payload: snapshots.closed7 }},
    {{ payload: {{ events: [] }} }},
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

async function runLabelRevision() {{
  // One span, published under S01 and later corrected to S03 by a retrospective sweep. The
  // words are byte-identical in both fields; only the label differs, which is the whole
  // claim a living document makes.
  const committedFirst = [
    {{ transcript: "[0][S01]who said this[1]", revised_transcript: null }},
    {{ transcript: "", revised_transcript: null }},
  ];
  const committedRevised = [
    {{ transcript: "[0][S01]who said this[1]", revised_transcript: "[0][S03]who said this[1]" }},
    {{ transcript: "", revised_transcript: null }},
  ];
  const env = installPortal([
    {{ payload: {{ snapshot: {{ session: {{ status: "active", version: 2, accepted_samples: 10, accounted_samples: 10, retained_samples: 0, committed: committedFirst, provisional: null, label_revision_version: 0 }}, pending_work_items: 0 }} }} }},
    {{ payload: {{ events: [] }} }},
    {{ payload: {{ snapshot: {{ session: {{ status: "active", version: 3, accepted_samples: 10, accounted_samples: 10, retained_samples: 0, committed: committedRevised, provisional: null, label_revision_version: 1 }}, pending_work_items: 0 }} }} }},
    {{ payload: {{ events: [] }} }},
  ]);
  env.nodes.sessionId.value = "revision-session";
  env.nodes.viewToken.value = "revision-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  const transcriptBefore = env.nodes.transcript.textContent;
  const statusBefore = env.nodes.statusDetail.textContent;
  await env.runNextTimer();
  console.log(JSON.stringify({{
    transcriptBefore,
    statusBefore,
    transcriptAfter: env.nodes.transcript.textContent,
    statusAfter: env.nodes.statusDetail.textContent,
  }}));
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
    {{ payload: {{ events: [] }} }},
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
    eventsAborted: env.requests[1].aborted,
    controlAborted: env.requests[2].aborted,
    connectionState: env.nodes.connectionState.textContent,
  }}));
}}

async function runTimeout() {{
  const env = installPortal([
    {{ hang: true }},
    {{ payload: {{ events: [] }} }},
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

async function runConcurrentFailure() {{
  const env = installPortal([
    {{ throwMessage: "snapshot unavailable" }},
    {{ hang: true }},
  ]);
  env.nodes.sessionId.value = "concurrent-failure-session";
  env.nodes.viewToken.value = "concurrent-failure-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  await env.flush();
  console.log(JSON.stringify({{
    eventsSiblingAborted: env.requests[1].aborted,
    status: env.nodes.statusDetail.textContent,
    retryDelays: env.timerDelays.filter((delay) => delay < 10000),
  }}));
}}

async function runControlTimeout() {{
  const env = installPortal([
    {{ hang: true }},
    {{ hang: true }},
  ]);
  env.nodes.sessionId.value = "control-timeout-session";
  env.nodes.viewToken.value = "control-timeout-token";
  env.nodes.connectButton.listeners.click();
  env.nodes.stopButton.listeners.click();
  await env.flush();
  await env.runTimerWithDelay(10000);
  await env.flush();
  console.log(JSON.stringify({{
    controlAborted: env.requests[0].aborted,
    requestCount: env.requests.length,
    pendingPollTimers: env.timers.filter((timer) => timer.delay === 0).map((timer) => timer.delay),
    statusAfterTimeout: env.nodes.statusDetail.textContent,
    controlTimerDelays: env.timerDelays.filter((delay) => delay === 10000),
  }}));
}}

async function runEventRetention() {{
  const manyEvents = Array.from({{ length: 205 }}, (_, index) => {{
    const seq = index + 1;
    return {{ seq, kind: "replay", snapshot_version: 4 }};
  }});
  const env = installPortal([
    {{ payload: snapshots.active2 }},
    {{ payload: {{ events: manyEvents }} }},
    {{ payload: snapshots.active4 }},
    {{ payload: {{ events: [{{ seq: 200, kind: "replay", snapshot_version: 4 }}, {{ seq: 206, kind: "tail", snapshot_version: 4 }}] }} }},
  ]);
  env.nodes.sessionId.value = "retention-session";
  env.nodes.viewToken.value = "retention-token";
  env.nodes.connectButton.listeners.click();
  await env.runNextTimer();
  await env.runNextTimer();
  const rows = env.nodes.events.children.map((node) => node.textContent);
  const bounds = window.mossLivePortal.renderedEventBounds();
  console.log(JSON.stringify({{
    rowCount: rows.length,
    firstRow: rows[0],
    lastRow: rows[rows.length - 1],
    seq200Rows: rows.filter((row) => row.startsWith("seq: 200 ")).length,
    secondEventsUrl: env.requests[3].url,
    cap: bounds.cap,
    identitySize: bounds.identity,
    orderLength: bounds.order,
    domRowCount: bounds.dom,
  }}));
}}

const scenarios = {{
  happy: runHappy,
  retry: runRetry,
  labelRevision: runLabelRevision,
  controlFailure: runControlFailure,
  overlap: runOverlap,
  disconnectOverlap: runDisconnectOverlap,
  timeout: runTimeout,
  concurrentFailure: runConcurrentFailure,
  controlTimeout: runControlTimeout,
  eventRetention: runEventRetention,
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


def _run_label_revision_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "labelRevision")


def _run_control_failure_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "controlFailure")


def _run_overlap_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "overlap")


def _run_disconnect_overlap_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "disconnectOverlap")


def _run_timeout_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "timeout")


def _run_concurrent_failure_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "concurrentFailure")


def _run_control_timeout_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "controlTimeout")


def _run_event_retention_contract_probe(html: str) -> dict:
    return _run_node_probe(html, "eventRetention")
