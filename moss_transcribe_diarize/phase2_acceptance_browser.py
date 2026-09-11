"""Fixed Chrome measurements for deployed Account acceptance.

The operator supplies Chrome/profile locations and Account session files.  This module owns every
navigation, selector, assertion, and fidelity comparison; no profile-defined script or assertion
can qualify a gate.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import ssl
import stat
import subprocess
import time
import tempfile
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from .app.phase2 import SESSION_COOKIE


class BrowserMeasurementError(RuntimeError):
    pass


REFERENCE_HEAD = "6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70"
ACCEPTED_FAILURE_URL = "https://127.0.0.1:1/phase2-acceptance-failure"


def _meeting_opener(page, meeting_id):
    """Select the interactive card, excluding server-rendered fallback cards."""
    return page.get_by_role("region", name="Meeting history", exact=True).locator(
        f'[data-open-meeting="{meeting_id}"]'
    )


def _trusted_tls_identity(origin: str) -> dict[str, object]:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname:
        raise BrowserMeasurementError("Workspace origin must use HTTPS")
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=15) as raw:
            with ssl.create_default_context().wrap_socket(
                raw, server_hostname=parsed.hostname
            ) as secured:
                certificate = secured.getpeercert()
    except (OSError, ssl.SSLError) as exc:
        raise BrowserMeasurementError("Workspace origin TLS is not trusted") from exc
    subject = ",".join(
        f"{key}={value}"
        for group in certificate.get("subject", ())
        for key, value in group
    )
    sans = sorted(value for _kind, value in certificate.get("subjectAltName", ()))
    expiry = certificate.get("notAfter")
    if not subject or not sans or not isinstance(expiry, str) or not expiry:
        raise BrowserMeasurementError("Workspace origin TLS identity is incomplete")
    return {
        "trusted": True,
        "subject": subject,
        "subject_alt_names": sans,
        "not_after": expiry,
    }


def _text(config: Mapping[str, object], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value:
        raise BrowserMeasurementError(f"browser prerequisite absent: {key}")
    return value


def _cookie(path: Path) -> str:
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise BrowserMeasurementError("Account cookie file must be mode 0600")
    value = path.read_text(encoding="utf-8").strip()
    if not value or "\n" in value or "\r" in value:
        raise BrowserMeasurementError("Account cookie file must contain one value")
    return value


def _add_cookie(context: BrowserContext, origin: str, cookie_file: Path) -> None:
    context.add_cookies(
        [
            {
                "name": SESSION_COOKIE,
                "value": _cookie(cookie_file),
                "url": origin,
                "secure": True,
                "httpOnly": True,
                "sameSite": "Lax",
            }
        ]
    )


def _wait_workspace(page: Page, origin: str) -> None:
    page.goto(origin, wait_until="networkidle")
    page.wait_for_selector('[data-auth-state="signed-in"]')
    page.wait_for_selector('[data-boot="ready"]')


def _load_reference_harness(repo: Path):
    path = repo / "tests" / "reference_ui_screenshot_diff.py"
    spec = importlib.util.spec_from_file_location("moss_phase2_reference_ui", path)
    if spec is None or spec.loader is None:
        raise BrowserMeasurementError("reference UI harness is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BrowserCampaign:
    def __init__(self, config: Mapping[str, object], *, repo: Path, work: Path) -> None:
        self.config = config
        self.repo = repo
        self.work = work
        self.origin = _text(config, "https_origin").rstrip("/")
        if not self.origin.startswith("https://"):
            raise BrowserMeasurementError("browser campaign requires trusted HTTPS")
        self.chrome = Path(_text(config, "chrome_binary")).expanduser().resolve()
        if not self.chrome.is_file():
            raise BrowserMeasurementError("Chrome executable is unavailable")

    def browser_workspace_identity(self, control: Any) -> dict[str, object]:
        """Measure input-free first visits, isolation and nonempty history continuity."""

        tls = _trusted_tls_identity(self.origin)
        fixture = Path(_text(self.config, "file_fixture")).expanduser()
        if not fixture.is_file():
            raise BrowserMeasurementError("Workspace probe requires real speech input")
        before = control("accounts.list", None)
        if not isinstance(before, list):
            raise BrowserMeasurementError("Workspace inventory is unavailable")
        with tempfile.TemporaryDirectory(prefix="workspace-identity-", dir=self.work) as scratch:
            with sync_playwright() as playwright:
                def launch(name: str):
                    return playwright.chromium.launch_persistent_context(
                        str(Path(scratch) / name), executable_path=str(self.chrome),
                        headless=True, args=["--mute-audio"],
                    )

                first, second = launch("first"), launch("second")
                try:
                    held = []
                    first.route("**/api/workspace/bootstrap", lambda route: held.append(route))
                    pages = [first.new_page(), first.new_page()]
                    for page in pages:
                        page.goto(self.origin, wait_until="commit")
                        page.wait_for_selector('[data-auth-state="bootstrap"]')
                    deadline = time.monotonic() + 10
                    contention = False
                    while time.monotonic() < deadline:
                        # Query actual browser lock state, not DOM readiness: one initializer
                        # must hold the lock while the second is already waiting for it.
                        contention = pages[0].evaluate("""async () => {
                          const state = await navigator.locks.query();
                          const named = items => items.filter(x => x.name === 'moss-workspace-bootstrap');
                          return named(state.held).length === 1 && named(state.pending).length === 1;
                        }""")
                        if len(held) > 1 or (contention and len(held) == 1):
                            break
                        pages[0].wait_for_timeout(10)
                    if len(held) != 1 or not contention:
                        for route in held:
                            route.abort()
                        first.unroute("**/api/workspace/bootstrap")
                        raise BrowserMeasurementError("First tabs did not serialize bootstrap")
                    held[0].continue_()
                    first.unroute("**/api/workspace/bootstrap")
                    for page in pages:
                        page.wait_for_selector('[data-auth-state="signed-in"]')
                    owners = [
                        page.evaluate("async () => (await (await fetch('/api/auth/session')).json()).workspace_id")
                        for page in pages
                    ]
                    peer_page = second.new_page()
                    peer_page.goto(self.origin, wait_until="domcontentloaded")
                    peer_page.wait_for_selector('[data-auth-state="signed-in"]')
                    peer_id = peer_page.evaluate(
                        "async () => (await (await fetch('/api/auth/session')).json()).workspace_id"
                    )
                    cookie = next(c for c in first.cookies(self.origin) if c["name"] == SESSION_COOKIE)
                    peer_cookie = next(c for c in second.cookies(self.origin) if c["name"] == SESSION_COOKIE)
                    cookie_contract = {
                        "cookie_secure": cookie["secure"],
                        "cookie_http_only": cookie["httpOnly"],
                        "cookie_same_site": cookie["sameSite"],
                        "javascript_cannot_read_cookie": pages[0].evaluate("document.cookie === ''"),
                    }
                    # Nonempty saved history, not equality of two empty lists.
                    created = first.request.post(
                        self.origin + "/api/meetings/file",
                        multipart={"file": {"name": fixture.name, "mimeType": "audio/wav", "buffer": fixture.read_bytes()}},
                    )
                    if created.status != 201:
                        raise BrowserMeasurementError("Workspace history fixture was not accepted")
                    meeting_id = created.json()["id"]
                    deadline = time.monotonic() + 600
                    saved = None
                    while time.monotonic() < deadline:
                        response = first.request.get(self.origin + "/api/meetings/" + meeting_id)
                        if response.status != 200:
                            raise BrowserMeasurementError("Workspace history fixture became inaccessible")
                        saved = response.json()
                        if saved["status"] != "active":
                            break
                        pages[0].wait_for_timeout(100)
                    if not saved or saved["status"] != "completed" or not saved.get("transcript", {}).get("segments"):
                        raise BrowserMeasurementError("Workspace history fixture has no completed speech")
                    foreign_status = second.request.get(self.origin + "/api/meetings/" + meeting_id).status
                    cross_origin_status = first.request.post(
                        self.origin + "/api/workspace/bootstrap",
                        headers={"Origin": "https://foreign.invalid"},
                    ).status
                    second.clear_cookies()
                    missing_status = second.request.put(
                        self.origin + "/api/meetings/" + meeting_id + "/title",
                        data={"title": "must not write"},
                    ).status
                    second.add_cookies([{**peer_cookie, "value": "invalid-workspace-credential"}])
                    invalid_status = second.request.post(self.origin + "/api/workspace/bootstrap").status
                finally:
                    first.close()
                    second.close()

                restarted = launch("first")
                try:
                    page = restarted.new_page()
                    page.goto(self.origin, wait_until="domcontentloaded")
                    page.wait_for_selector('[data-auth-state="signed-in"]')
                    returned = restarted.request.get(self.origin + "/api/auth/session")
                    restored = restarted.request.get(self.origin + "/api/meetings/" + meeting_id)
                    same_owner = returned.status == 200 and returned.json().get("workspace_id") == owners[0]
                    history_survived = restored.status == 200 and restored.json() == saved
                finally:
                    restarted.close()
        after = control("accounts.list", None)
        if not isinstance(after, list):
            raise BrowserMeasurementError("Final workspace inventory is unavailable")
        return {
            "workspace_url": self.origin + "/",
            "first_tabs": 2,
            "first_tab_lock_contention_observed": contention,
            "created_workspaces": len(after) - len(before),
            "same_profile_owner": owners[0] == owners[1],
            "profiles_isolated": peer_id != owners[0],
            "foreign_meeting_status": foreign_status,
            "mutation_without_cookie_status": missing_status,
            "invalid_cookie_bootstrap_status": invalid_status,
            "cross_origin_status": cross_origin_status,
            "tls_trusted_without_interstitial": tls["trusted"],
            "tls_identity": tls,
            "browser_restart_session_survived": same_owner,
            "history_survived_restart": history_survived,
            "nonempty_saved_history": True,
            "cookie_contract": cookie_contract,
        }

    def product_regression(
        self, meeting_id: str, export_meeting_id: str
    ) -> dict[str, object]:
        """Exercise the committed bundle at its deployed origin, including background observation."""

        suites: list[dict[str, object]] = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(self.chrome), headless=True)
            try:
                context = browser.new_context(viewport={"width": 1440, "height": 900})
                _add_cookie(
                    context,
                    self.origin,
                    Path(_text(self.config, "account_a_cookie_file")).expanduser(),
                )
                page = context.new_page()
                _wait_workspace(page, self.origin)
                checks = [
                    page.locator('[data-workspace-section="file"]').count() == 1,
                    page.locator('[data-workspace-section="live"]').count() == 1,
                    page.locator('[data-workspace-section="history"]').count() == 1,
                    page.locator('[aria-label="Meeting history"]').count() == 1,
                    page.locator('#transcript-panel').count() == 1,
                ]
                order = page.eval_on_selector_all(
                    "[data-workspace-section]",
                    "items => items.map(item => item.getAttribute('data-workspace-section'))",
                )
                checks.append(order == ["file", "live", "history", "voiceprints"])
                suites.append(_suite("desktop-semantic-accessibility", checks))

                active = _meeting_opener(page, meeting_id)
                active_count = active.count()
                if active_count != 1:
                    raise BrowserMeasurementError(
                        f"active observer Meeting expected 1 interactive history card; observed {active_count}"
                    )
                poll_requests = 0

                def observed(request: Any) -> None:
                    nonlocal poll_requests
                    if f"/api/live/sessions/{meeting_id}/" in request.url:
                        poll_requests += 1

                page.on("requestfinished", observed)
                active.click()
                page.wait_for_selector('[data-observer-mode="read-only"]')
                foreground = page.locator('[data-capture-phase="viewing"]').count() == 1
                other = context.new_page()
                other.goto("about:blank")
                other.bring_to_front()
                page.wait_for_function("document.visibilityState === 'hidden'")
                hidden_state = page.evaluate("document.visibilityState") == "hidden"
                time.sleep(2.5)
                background_polled = poll_requests > 0
                page.bring_to_front()
                page.reload(wait_until="networkidle")
                page.wait_for_selector('[data-observer-mode="read-only"]')
                reload_read_only = (
                    page.locator('[data-capture-phase="viewing"]').count() == 1
                    and page.get_by_text("Stop and finalize").count() == 0
                )
                suites.append(
                    _suite(
                        "active-background-observer",
                        [foreground, hidden_state, background_polled, reload_read_only],
                    )
                )
                context.close()

                mobile = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    screen={"width": 390, "height": 844},
                    is_mobile=True,
                    device_scale_factor=1,
                )
                _add_cookie(
                    mobile,
                    self.origin,
                    Path(_text(self.config, "account_a_cookie_file")).expanduser(),
                )
                mobile_page = mobile.new_page()
                _wait_workspace(mobile_page, self.origin)
                mobile_checks = [
                    mobile_page.evaluate("innerWidth") == 390,
                    mobile_page.evaluate("matchMedia('(max-width: 768px)').matches") is True,
                    mobile_page.locator('[data-workspace-section="history"]').is_visible(),
                    mobile_page.evaluate(
                        "document.documentElement.scrollHeight > document.documentElement.clientHeight"
                    )
                    is True,
                ]
                suites.append(_suite("mobile-reachability", mobile_checks))
                mobile.close()

                export_context = browser.new_context(viewport={"width": 1280, "height": 800})
                _add_cookie(
                    export_context,
                    self.origin,
                    Path(_text(self.config, "account_a_cookie_file")).expanduser(),
                )
                export_page = export_context.new_page()
                _wait_workspace(export_page, self.origin)
                _meeting_opener(export_page, export_meeting_id).click()
                export_page.wait_for_selector('#transcript-panel')
                export_checks: list[bool] = []
                for label, suffix in (
                    ("Markdown (.md)", ".md"),
                    ("Plain text (.txt)", ".txt"),
                    ("JSON (.json)", ".json"),
                    ("SubRip (.srt)", ".srt"),
                    ("WebVTT (.vtt)", ".vtt"),
                ):
                    export_page.get_by_title("Export transcript").click()
                    with export_page.expect_download() as download:
                        export_page.get_by_role("menuitem", name=label).click()
                    item = download.value
                    downloaded = item.path()
                    export_checks.append(
                        item.suggested_filename.endswith(suffix)
                        and downloaded is not None
                        and Path(downloaded).stat().st_size > 0
                    )
                suites.append(_suite("history-export", export_checks))
                export_context.close()
            finally:
                browser.close()
        return {"suites": suites}

    def submit_file_url_batch(
        self, file_fixture: Path, url_fixture: str
    ) -> dict[str, object]:
        """Drive the shipped multi-file/newline-URL form and close one accepted browser."""

        payload = file_fixture.read_bytes()
        if not payload:
            raise BrowserMeasurementError("File fixture is empty")

        def open_context(browser: Browser) -> BrowserContext:
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            _add_cookie(
                context,
                self.origin,
                Path(_text(self.config, "account_a_cookie_file")).expanduser(),
            )
            return context

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(self.chrome), headless=True
            )
            try:
                context = open_context(browser)
                page = context.new_page()
                _wait_workspace(page, self.origin)
                observed: list[dict[str, object]] = []

                def record(response: Any) -> None:
                    path = response.request.url.removeprefix(self.origin)
                    if response.request.method != "POST" or path not in {
                        "/api/meetings/file",
                        "/api/meetings/url",
                    }:
                        return
                    try:
                        body = response.json()
                    except Exception:
                        body = None
                    observed.append(
                        {
                            "path": path,
                            "status": response.status,
                            "input_kind": (
                                "file"
                                if path == "/api/meetings/file"
                                else (
                                    "accepted_failure"
                                    if response.request.post_data_json.get("url")
                                    == ACCEPTED_FAILURE_URL
                                    else (
                                        "invalid"
                                        if response.request.post_data_json.get("url")
                                        == "not-a-supported-url"
                                        else "url"
                                    )
                                )
                            ),
                            "meeting_id": body.get("id")
                            if isinstance(body, dict)
                            else None,
                        }
                    )

                page.on("response", record)
                page.locator('input[name="file"]').set_input_files(
                    [
                        {"name": "batch-a.wav", "mimeType": "audio/wav", "buffer": payload},
                        {"name": "batch-b.wav", "mimeType": "audio/wav", "buffer": payload},
                    ]
                )
                page.locator('textarea[name="urls"]').fill(
                    f"{url_fixture}\n{ACCEPTED_FAILURE_URL}\nnot-a-supported-url\n{url_fixture}"
                )
                page.get_by_role("button", name="Transcribe files and URLs").click()
                deadline = time.monotonic() + 120
                while len(observed) < 6 and time.monotonic() < deadline:
                    page.wait_for_timeout(100)
                context.close()
                if len(observed) != 6:
                    raise BrowserMeasurementError("batch form did not issue six submissions")

                detached_context = open_context(browser)
                detached_page = detached_context.new_page()
                _wait_workspace(detached_page, self.origin)
                detached: list[dict[str, object]] = []

                def record_detached(response: Any) -> None:
                    if (
                        response.request.method == "POST"
                        and response.request.url.removeprefix(self.origin)
                        == "/api/meetings/file"
                    ):
                        try:
                            body = response.json()
                        except Exception:
                            body = None
                        detached.append(
                            {
                                "status": response.status,
                                "meeting_id": body.get("id")
                                if isinstance(body, dict)
                                else None,
                            }
                        )

                detached_page.on("response", record_detached)
                detached_page.locator('input[name="file"]').set_input_files(
                    {"name": "detached.wav", "mimeType": "audio/wav", "buffer": payload}
                )
                detached_page.get_by_role(
                    "button", name="Transcribe files and URLs"
                ).click()
                deadline = time.monotonic() + 120
                while not detached and time.monotonic() < deadline:
                    detached_page.wait_for_timeout(100)
                detached_context.close()
                if len(detached) != 1:
                    raise BrowserMeasurementError("detached File was not accepted once")
            finally:
                browser.close()

        accepted = [
            item for item in observed if item["status"] == 201 and item["meeting_id"]
        ]
        failed = [item for item in observed if item["status"] != 201]
        if len(accepted) != 5 or len(failed) != 1 or failed[0]["status"] not in {400, 422}:
            raise BrowserMeasurementError("batch acceptance/failure counts differ")
        if detached[0]["status"] != 201 or not detached[0]["meeting_id"]:
            raise BrowserMeasurementError("detached File was not durably accepted")
        return {
            "ordered": observed,
            "detached": detached[0],
        }

    def transcript_fidelity(self, meeting: Mapping[str, object]) -> dict[str, object]:
        transcript = meeting.get("transcript")
        segments = transcript.get("segments") if isinstance(transcript, Mapping) else None
        if not isinstance(segments, list) or not segments:
            raise BrowserMeasurementError("fidelity requires one durable nonempty transcript")
        fixture = [
            {
                "start": item.get("start"),
                "end": item.get("end"),
                "text": item.get("text"),
                "speaker": item.get("speaker"),
                "speaker_entity_id": f"speaker-{item.get('speaker')}",
                "display_name": item.get("speaker"),
                "confidence": 1.0,
                "state": "final",
                "segment_id": item.get("id", f"segment-{index}"),
            }
            for index, item in enumerate(segments)
            if isinstance(item, Mapping) and isinstance(item.get("text"), str)
        ]
        if not fixture:
            raise BrowserMeasurementError("fidelity transcript has no renderable segments")
        meeting_id = meeting.get("id")
        if not isinstance(meeting_id, str):
            raise BrowserMeasurementError("fidelity Meeting ID is absent")
        harness = _load_reference_harness(self.repo)
        config = harness.load_json(self.repo / "tests/fixtures/reference_ui_screenshot_diff.json")
        reference_root = Path(_text(self.config, "live_transcribe_reference")).expanduser().resolve()
        head = subprocess.run(
            ("git", "-C", str(reference_root), "rev-parse", "HEAD"),
            check=False,
            capture_output=True,
            text=True,
        )
        status = subprocess.run(
            ("git", "-C", str(reference_root), "status", "--porcelain=v1"),
            check=False,
            capture_output=True,
            text=True,
        )
        if (
            head.returncode
            or status.returncode
            or head.stdout.strip() != REFERENCE_HEAD
            or status.stdout.strip()
        ):
            raise BrowserMeasurementError("LiveTranscribe reference identity drifted")
        output = self.work / "fidelity"
        os.mkdir(output, mode=0o700)
        reference_port = harness.unused_local_port()
        reference_server = harness.start_vite(
            reference_root, reference_port, output / "reference-vite.log"
        )
        try:
            harness.wait_for_server(f"http://127.0.0.1:{reference_port}/", reference_server)
            with sync_playwright() as playwright:
                browser: Browser = playwright.chromium.launch(
                    executable_path=str(self.chrome), headless=True
                )
                try:
                    results: list[dict[str, object]] = []
                    for viewport in config["viewports"]:
                        reference_context = browser.new_context(
                            viewport=viewport, device_scale_factor=1
                        )
                        candidate_context = browser.new_context(
                            viewport=viewport, device_scale_factor=1
                        )
                        _add_cookie(
                            candidate_context,
                            self.origin,
                            Path(_text(self.config, "account_a_cookie_file")).expanduser(),
                        )
                        try:
                            reference_page = reference_context.new_page()
                            candidate_page = candidate_context.new_page()
                            harness.install_reference_api_stub(reference_page)
                            reference_page.goto(
                                f"http://127.0.0.1:{reference_port}/", wait_until="networkidle"
                            )
                            candidate_page.goto(self.origin, wait_until="networkidle")
                            harness.prepare_page(reference_page, fixture, is_reference=True)
                            candidate_page.wait_for_selector('[data-auth-state="signed-in"]')
                            candidate_page.wait_for_selector('[data-boot="ready"]')
                            _meeting_opener(candidate_page, meeting_id).click()
                            candidate_page.wait_for_function(
                                "tail => document.querySelector('#tr-body')?.textContent.includes(tail)",
                                arg=fixture[-1]["text"],
                            )
                            candidate_page.evaluate(
                                """() => {
                                  const app = document.querySelector('#app > .app');
                                  if (!app) throw new Error('Account bundle did not mount');
                                  document.body.replaceChildren(app);
                                  document.body.className = '';
                                  Object.assign(app.style, {position:'fixed', inset:'0', width:'100vw', height:'100vh'});
                                }"""
                            )
                            harness.wait_for_visual_settle(reference_page)
                            harness.wait_for_visual_settle(candidate_page)
                            label = f"{viewport['width']}x{viewport['height']}"
                            reference_path = output / f"reference-{label}.png"
                            candidate_path = output / f"candidate-{label}.png"
                            mask_path = output / f"difference-mask-{label}.png"
                            reference_page.locator("#transcript-panel").screenshot(
                                path=str(reference_path)
                            )
                            candidate_page.locator("#transcript-panel").screenshot(
                                path=str(candidate_path)
                            )
                            measured = harness.compare_viewport(
                                reference_path,
                                candidate_path,
                                mask_path,
                                config,
                                [],
                                reference_page,
                                candidate_page,
                            )
                            results.append(
                                {
                                    "width": viewport["width"],
                                    "height": viewport["height"],
                                    "total_difference": measured[
                                        "different_pixel_percent"
                                    ]
                                    / 100.0,
                                    "largest_connected_difference": measured[
                                        "largest_four_connected_region_percent"
                                    ]
                                    / 100.0,
                                    "pane_width": measured["viewport"]["width"],
                                    "pane_height": measured["viewport"]["height"],
                                }
                            )
                        finally:
                            reference_context.close()
                            candidate_context.close()
                finally:
                    browser.close()
        finally:
            harness.stop_process(reference_server)
        return {
            "viewports": results,
            "reference_identity": {"head": REFERENCE_HEAD, "clean": True},
        }


def _suite(name: str, checks: list[bool]) -> dict[str, object]:
    passed = sum(bool(item) for item in checks)
    return {
        "name": name,
        "collected": len(checks),
        "executed": len(checks),
        "passed": passed,
        "failed": len(checks) - passed,
        "skipped": 0,
        "unmeasured": 0,
    }


__all__ = ["BrowserCampaign", "BrowserMeasurementError"]
