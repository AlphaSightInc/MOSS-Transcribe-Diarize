"""Real browser -> separate HTTPS fake provider, overlapping real Live capacity.

No paid provider, browser interception, time acceleration, injected product state or
certificate bypass. The fake endpoint runs on loopback with the candidate hostname's
trusted certificate. Only content-free observations leave this measurement process.
"""
from __future__ import annotations

from .phase2_acceptance_replay import ACCEPTANCE_STOP_DEADLINE_SECONDS

import json
import re
import ssl
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

from .phase2_acceptance import _validate_capacity
from .phase2_acceptance_browser import _add_cookie, _trusted_tls_identity, _meeting_opener
from .phase2_acceptance_completion import validate_completion_observation


def select_external_summary_provider(region):
    """Shared selector for sync predicates and async probes (await the latter).

    Playwright sync returns the selected values; async returns an awaitable.
    Keep the provider label and choice here so both callers follow the same path.
    """
    return region.get_by_label("Provider", exact=True).select_option(label="External HTTPS provider")


def configure_external_summary(page, *, endpoint, model, api_key, prompt, timeout="2400"):
    """Choose the external path explicitly even when server relay models exist."""
    region = page.get_by_role("region", name="Browser AI settings", exact=True)
    if region.locator("form").count() == 0:
        region.get_by_role("button", name=re.compile(r"^Optional AI summaries · ")).click()
    select_external_summary_provider(region)
    for label, value in (("Provider HTTPS URL", endpoint), ("Model", model),
                         ("API key (optional)", api_key), ("Final-summary prompt", prompt),
                         ("Request timeout (seconds)", timeout)):
        region.get_by_label(label, exact=True).fill(value)
    region.get_by_role("button", name="Save on this browser", exact=True).click()


def _summary_action(page):
    return page.get_by_role("region", name="Final summary", exact=True).get_by_test_id("final-summary-generate")


class SummaryProbeProvider:
    """Fixed fake provider with real CORS, delivery errors and held responses."""
    def __init__(self, *, origin: str, certificate: Path | None = None, key: Path | None = None):
        self.origin = origin
        self.calls: list[dict] = []
        self.preflights: list[dict] = []
        self.release = threading.Event()
        self.release_cancel = threading.Event()
        self.lock = threading.Lock()
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_OPTIONS(self):
                with owner.lock: owner.preflights.append({"path": self.path, "origin": self.headers.get("Origin"), "headers": self.headers.get("Access-Control-Request-Headers", "")})
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", owner.origin)
                self.send_header("Access-Control-Allow-Methods", "POST")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.end_headers()
            def do_POST(self):
                row = {"path": self.path, "body": self.rfile.read(int(self.headers.get("Content-Length", "0"))),
                       "headers": dict(self.headers), "started": time.monotonic_ns(), "finished": None}
                with owner.lock: owner.calls.append(row)
                mode = self.path.split("/")[1]
                if mode == "hold": owner.release.wait(2400)
                if mode == "cancel": owner.release_cancel.wait(2400)
                code = 503 if mode in {"retry", "retrycancel"} else 200
                value = {"summary": "Qualification summary", "topics": [{"title": "Qualification topic", "description": "Controlled structural fixture"}],
                         "details": [], "speaker_background": [], "data_references": []}
                content = "invalid raw JSON" if mode == "invalid" else json.dumps(value)
                encoded = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
                try:
                    self.send_response(code)
                    self.send_header("Access-Control-Allow-Origin", owner.origin)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers(); self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
                finally: row["finished"] = time.monotonic_ns()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.scheme = "https" if certificate else "http"
        if certificate:
            tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            tls.load_cert_chain(certificate, key)
            self.server.socket = tls.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *_):
        self.release.set(); self.release_cancel.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def endpoint(self, mode: str) -> str:
        return f"{self.scheme}://{urlsplit(self.origin).hostname}:{self.server.server_port}/{mode}/v1"

    def requests(self, mode: str):
        with self.lock: return [row for row in self.calls if row["path"].startswith(f"/{mode}/")]


def measure_browser_summary(campaign):
    origin = campaign.origin.rstrip("/")
    tls = _trusted_tls_identity(origin)  # No certificate exceptions permitted.
    host = urlsplit(origin).hostname
    first = getattr(campaign, "_summary_voiceprint_meeting", None)
    if not isinstance(first, str): raise RuntimeError("G9 requires the actual completed Wave-2 named Meeting")
    a = campaign.a
    primary, _ = a.json("GET", f"/api/meetings/{first}", 200)
    if not any(s["speaker"] == "Qualification speaker" for s in primary["transcript"]["segments"]):
        raise RuntimeError("G9 source lacks actual Wave-2 display labels")
    b_created, _ = campaign.b.json("POST", "/api/live/sessions", 201, json={"echo_mode": "speakers"})
    second = b_created["id"]
    try:
        campaign._seed_live_transcript("b", second, 1)
        campaign.b.json("POST", f"/api/live/sessions/{second}/stop", 200, json={"deadline": ACCEPTANCE_STOP_DEADLINE_SECONDS})
    except BaseException:
        campaign.b.request("POST", f"/api/live/sessions/{second}/abort", json={})
        raise
    secondary, _ = campaign.b.json("GET", f"/api/meetings/{second}", 200)
    third = campaign._submit_file_for(a, Path(campaign._text("file_fixture")))
    third_source = campaign._await_meeting_terminal_for(a, third)
    if any(m["status"] != "completed" for m in (primary, secondary, third_source)):
        raise RuntimeError("G9 sources must contain real finalized speech")
    a.json("PUT", f"/api/meetings/{first}/title", 200, json={"title": "Owner qualification title"})
    checks = {"trusted_tls": tls["trusted"] is True}
    moss_writes = []
    moss_write_routes = []
    observed_events = []
    load = type(campaign)(candidate_sha=campaign.candidate_sha, config={**campaign.config, "campaign_work_dir": str(campaign.artifact_root / "summary-load")})
    capacity = None
    try:
        with SummaryProbeProvider(origin=origin, certificate=Path(campaign._text("summary_probe_cert")), key=Path(campaign._text("summary_probe_key"))) as provider:
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=campaign._text("chrome_binary"), headless=True,
                    args=["--mute-audio", f"--host-resolver-rules=MAP {host} 127.0.0.1"])
                contexts = [browser.new_context() for _ in range(2)]
                pages = []
                try:
                    for index, context in enumerate(contexts):
                        _add_cookie(context, origin, Path(campaign._text(f"account_{'a' if index == 0 else 'b'}_cookie_file")))
                        page = context.new_page(); pages.append(page)
                        def observe_request(request):
                            if request.url.startswith(origin + "/api/") and request.method != "GET":
                                moss_writes.append(request.post_data or "")
                                moss_write_routes.append((request.url, request.post_data or ""))
                        page.on("request", observe_request)
                        page.goto(origin)
                        page.locator('[data-history-boot="ready"]').wait_for()
                        page.evaluate("window.__summaryEvents=[]; for (const name of ['llm_status','llm_summary_update']) document.addEventListener(name, e=>window.__summaryEvents.push({type:name,state:e.detail.artifact?.state}));")

                    def select(page, meeting):
                        page.get_by_role("region", name="Meeting history", exact=True).get_by_role("button", name="Refresh", exact=True).click()
                        _meeting_opener(page, meeting).click()
                        page.get_by_role("region", name="Final summary", exact=True).wait_for()
                    def configure(page, owner, mode):
                        configure_external_summary(page, endpoint=provider.endpoint(mode), model=f"g9-model-{owner}",
                            api_key=f"g9-private-key-{owner}", prompt=f"g9-private-prompt-{owner}")
                    def start(page):
                        region = page.get_by_role("region", name="Final summary", exact=True)
                        previous_attempt = region.get_attribute("data-summary-attempt")
                        _summary_action(page).click()
                        page.wait_for_function("previous => { const id=document.querySelector('[data-summary-state]')?.dataset.summaryAttempt; return id && id !== previous; }", arg=previous_attempt)
                    def state(page, wanted, timeout=30000):
                        page.locator(f'[data-summary-state="{wanted}"]').wait_for(timeout=timeout)
                    def count(mode, number, page):
                        deadline = time.monotonic() + 30
                        while len(provider.requests(mode)) < number and time.monotonic() < deadline: page.wait_for_timeout(100)
                        if len(provider.requests(mode)) != number: raise RuntimeError("Provider request count mismatch")

                    configure(pages[0], "a", "history"); configure(pages[1], "b", "history")
                    select(pages[0], first); select(pages[1], second)
                    for page in pages: page.wait_for_load_state("networkidle")
                    checks["history_does_not_infer"] = len(provider.calls) == 0
                    configure(pages[0], "a", "retry"); start(pages[0]); state(pages[0], "failed", 500000)
                    retries = provider.requests("retry")
                    checks["four_identical_deliveries"] = len(retries) == 4 and len({row["body"] for row in retries}) == 1
                    retry_times = [row["started"] / 1e9 for row in retries]
                    checks["retry_intervals"] = len(retry_times) == 4 and all(retry_times[i + 1] - retry_times[i] >= delay for i, delay in enumerate((60, 120, 240)))

                    configure(pages[0], "a", "invalid"); start(pages[0]); state(pages[0], "failed")
                    configure(pages[0], "a", "retrycancel"); start(pages[0]); state(pages[0], "retry_wait")
                    pages[0].get_by_role("button", name="Cancel summary", exact=True).click(); state(pages[0], "cancelled")
                    configure(pages[0], "a", "cancel"); start(pages[0]); count("cancel", 1, pages[0])
                    pages[0].get_by_role("button", name="Cancel summary", exact=True).click(); state(pages[0], "cancelled")
                    provider.release_cancel.set()
                    deadline = time.monotonic() + 30
                    while provider.requests("cancel")[0]["finished"] is None and time.monotonic() < deadline:
                        pages[0].wait_for_timeout(100)
                    if provider.requests("cancel")[0]["finished"] is None: raise RuntimeError("Held cancelled response did not settle")
                    cancelled = a.json("GET", f"/api/meetings/{first}/summary", 200)[0]["summary"]
                    checks["cancel_late_result"] = cancelled["state"] == "cancelled" and cancelled["document"] is None

                    configure(pages[0], "a", "hold"); start(pages[0]); count("hold", 1, pages[0])
                    select(pages[0], third); start(pages[0]); state(pages[0], "queued")
                    checks["serial_worker"] = len(provider.requests("hold")) == 1
                    configure(pages[1], "b", "hold"); start(pages[1]); count("hold", 2, pages[1])
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        future = pool.submit(load.four_session_capacity)
                        while not future.done(): pages[0].wait_for_timeout(1000)
                        capacity = future.result()
                    held = provider.requests("hold")
                    interval = capacity["campaign_interval"]
                    checks["load_overlaps_provider"] = len(held) == 2 and all(row["started"] <= interval["started_monotonic_ns"] and row["finished"] is None for row in held)
                    checks["speech_capacity_unchanged"] = _validate_capacity({"raw": capacity})
                    checks["invalid_output_no_repair"] = len(provider.requests("invalid")) == 1
                    checks["cancel_retry_wait"] = len(provider.requests("retrycancel")) == 1
                    checks["history_does_not_infer"] = checks["history_does_not_infer"] and len(provider.requests("history")) == 0
                    checks["cancel_late_result"] = checks["cancel_late_result"] and not any(
                        url.endswith(f"/summary/{cancelled['attempt_id']}") and json.loads(body).get("state") == "current" for url, body in moss_write_routes)
                    provider.release.set()
                    state(pages[0], "current"); state(pages[1], "current")
                    count("hold", 3, pages[0])

                    expected = {}
                    for owner, sources in (("a", (primary, third_source)), ("b", (secondary,))):
                        expected[owner] = [{"segments": [{key: row[key] for key in ("start", "end", "speaker", "text")} for row in source["transcript"]["segments"]]} for source in sources]
                    payload_ok = True
                    for row in provider.calls:
                        body = json.loads(row["body"])
                        owner = "a" if body.get("model") == "g9-model-a" else "b"
                        payload_ok = payload_ok and set(body) == {"model", "stream", "messages", "max_tokens"} and body["stream"] is False and body["max_tokens"] >= 2048
                        payload_ok = payload_ok and body["messages"][0] == {"role": "system", "content": f"g9-private-prompt-{owner}"}
                        payload_ok = payload_ok and body["messages"][1]["role"] == "user" and json.loads(body["messages"][1]["content"]) in expected[owner]
                    checks["owner_payloads_only"] = payload_ok
                    checks["no_ambient_credentials"] = all(not any(name.lower() in {"cookie", "referer"} for name in row["headers"]) for row in provider.calls)
                    checks["real_cors_preflight"] = bool(provider.preflights) and all(row["origin"] == origin and "authorization" in row["headers"].lower() for row in provider.preflights)
                    checks["no_settings_to_moss"] = not any(value in "\n".join(moss_writes) for value in ("g9-private-key-", "g9-private-prompt-", "g9-model-", provider.endpoint("hold")))
                    final = [a.json("GET", f"/api/meetings/{id}/summary", 200)[0]["summary"] for id in (first, third)]
                    final.append(campaign.b.json("GET", f"/api/meetings/{second}/summary", 200)[0]["summary"])
                    checks["durable_results"] = all(row["state"] == "current" and row["document"]["summary"] == "Qualification summary" for row in final)
                    checks["manual_title_preserved"] = a.json("GET", f"/api/meetings/{first}", 200)[0]["title"] == "Owner qualification title"
                    foreign = [campaign.b.request("GET", f"/api/meetings/{first}/summary").status_code,
                        campaign.b.request("POST", f"/api/meetings/{first}/summary", json={"source_version": primary["transcript_version"]}).status_code,
                        campaign.b.request("PUT", f"/api/meetings/{first}/summary/{final[0]['attempt_id']}", json={"state": "cancelled"}).status_code]
                    checks["foreign_routes_refused"] = foreign == [404, 404, 404]
                    observed_events = [page.evaluate("window.__summaryEvents") for page in pages]
                    flattened = [event for events in observed_events for event in events]
                    checks["lifecycle_events"] = {"queued", "generating", "retry_wait", "failed", "cancelled", "current"} <= {event.get("state") for event in flattened if event.get("type") == "llm_status"} and any(event.get("type") == "llm_summary_update" for event in flattened)
                finally:
                    browser.close()
    finally:
        load.close()
        campaign._safe_artifacts.update(Path("summary-load") / path for path in load.safe_artifacts)
        for client, meeting in ((a, first), (a, third), (campaign.b, second)):
            value, _ = client.json("GET", f"/api/meetings/{meeting}/summary", 200)
            attempt = value.get("summary")
            if isinstance(attempt, dict) and attempt.get("state") in {"queued", "generating", "retry_wait"}:
                client.json("PUT", f"/api/meetings/{meeting}/summary/{attempt['attempt_id']}", 200, json={"state": "cancelled"})
    # Host qualification runs the same real-browser relay scenario as the deterministic
    # probe, on a scratch app configured solely with a loopback fake upstream. This
    # verifies candidate relay code without modifying the staged server's environment.
    relay_output = campaign.artifact_root / "summary-provider-paths.json"
    subprocess.run([sys.executable, "prototypes/client-configured-llm/final_browser_probe.py",
        "--chrome-binary", campaign._text("chrome_binary"), "--output", str(relay_output)],
        cwd=campaign._text("repo_root"), check=True, capture_output=True, timeout=120)
    paths = json.loads(relay_output.read_text())
    campaign._safe_artifacts.add(Path("summary-provider-paths.json"))
    from .phase2_acceptance_completion import validate_relay_summary_observation
    checks["relay_path_qualified"] = validate_relay_summary_observation(paths.get("relay"))
    raw = {"checks": checks, "capacity": capacity, "retry_deliveries": retry_times,
           "events": observed_events, "provider_requests": len(provider.calls), "tls": tls, "relay": paths["relay"]}
    if not validate_completion_observation("browser_final_summary", raw): raise RuntimeError("Browser summary privacy/lifecycle/load qualification failed")
    return raw
