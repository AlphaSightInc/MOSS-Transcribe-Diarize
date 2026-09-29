from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import socket
import subprocess
import threading
import time
from urllib.request import urlopen

import httpx
import pytest
from fastapi.responses import RedirectResponse
import uvicorn
import websockets

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript
from moss_transcribe_diarize.app.live_endpoint import (
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)
from moss_transcribe_diarize.app.live_helper_presence import HELPER_HEALTH_SCHEMA
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
    LiveServiceRuntime,
    hash_config,
)
from moss_transcribe_diarize.app.live_session import (
    LIVE_SAMPLE_RATE,
    AudioFrame,
    FrozenSpan,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
)
from moss_transcribe_diarize.app.phase2 import (
    Phase2Store,
    create_phase2_app,
)


def _chrome() -> Path:
    from playwright.sync_api import sync_playwright
    from tests.phase2.browser_support import require_browser
    with sync_playwright() as p:
        return require_browser(p)


from tests.phase2.workspace_reachability_fixtures import _runtime, _heartbeat, _v2_frame


class _ChromePage:
    def __init__(self, process: subprocess.Popen[str], debugger_port: int):
        self.process = process
        self.debugger_port = debugger_port
        self.socket = None
        self._message_id = 0

    @classmethod
    async def launch(
        cls,
        *,
        chrome: Path,
        profile: Path,
        url: str,
        width: int,
        height: int,
        mobile: bool = False,
    ) -> "_ChromePage":
        debugger_port = _free_port()
        process = subprocess.Popen(
            [
                str(chrome),
                "--headless=new",
                "--mute-audio",
                "--no-sandbox",
                "--disable-gpu",
                "--ignore-certificate-errors",
                "--remote-allow-origins=*",
                f"--remote-debugging-port={debugger_port}",
                f"--user-data-dir={profile}",
                f"--window-size={width},{height}",
                url,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        page = cls(process, debugger_port)
        try:
            endpoint = await page._debugger_endpoint()
            page.socket = await websockets.connect(endpoint, origin="http://127.0.0.1")
            await page.command("Page.enable")
            await page.command("Network.enable")
            if mobile:
                await page.command(
                    "Emulation.setDeviceMetricsOverride",
                    {
                        "width": width,
                        "height": height,
                        "deviceScaleFactor": 1,
                        "mobile": True,
                        "screenWidth": width,
                        "screenHeight": height,
                    },
                )
                await page.command(
                    "Network.setUserAgentOverride",
                    {
                        "userAgent": (
                            "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/138.0.0.0 Mobile Safari/537.36"
                        )
                    },
                )
                await page.command("Page.reload", {"ignoreCache": True})
            return page
        except BaseException:
            page.close()
            raise

    async def _debugger_endpoint(self) -> str:
        deadline = time.monotonic() + 8
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise AssertionError("Chrome exited before exposing its debugger endpoint.")
            try:
                with urlopen(
                    f"http://127.0.0.1:{self.debugger_port}/json/list", timeout=0.5
                ) as response:
                    targets = json.load(response)
                page = next(target for target in targets if target.get("type") == "page")
                return page["webSocketDebuggerUrl"]
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(0.05)
        raise AssertionError(f"Chrome debugger unavailable: {last_error}")

    async def command(self, method: str, params: dict[str, object] | None = None) -> dict[str, object]:
        assert self.socket is not None
        self._message_id += 1
        message_id = self._message_id
        await self.socket.send(json.dumps({"id": message_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.socket.recv())
            if message.get("id") != message_id:
                continue
            if "error" in message:
                raise AssertionError(f"CDP {method} failed: {message['error']}")
            return message.get("result", {})

    async def evaluate(self, expression: str) -> object:
        response = await self.command(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
        )
        result = response["result"]
        if "exceptionDetails" in response:
            raise AssertionError(response["exceptionDetails"])
        return result.get("value")

    async def wait(self, expression: str, *, timeout: float = 8.0) -> object:
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            last = await self.evaluate(f"Boolean({expression})")
            if last:
                return last
            await asyncio.sleep(0.05)
        raise AssertionError(f"Browser condition timed out: {expression}; last={last!r}")

    async def cookies(self, url: str) -> list[dict[str, object]]:
        result = await self.command("Network.getCookies", {"urls": [url]})
        return result["cookies"]

    async def reload(self) -> None:
        await self.command("Page.reload", {"ignoreCache": True})

    def close(self) -> None:
        if self.socket is not None:
            try:
                asyncio.get_running_loop().create_task(self.socket.close())
            except RuntimeError:
                pass
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _certificate(tmp_path: Path) -> tuple[Path, Path]:
    certificate = tmp_path / "certificate.pem"
    private_key = tmp_path / "private-key.pem"
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return certificate, private_key


def _start_server(app, certificate: Path, private_key: Path):
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="critical",
            ssl_certfile=str(certificate),
            ssl_keyfile=str(private_key),
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline and not server.started:
        if not thread.is_alive():
            raise AssertionError("Phase-2 browser server exited during startup.")
        time.sleep(0.02)
    assert server.started
    return server, thread, f"https://127.0.0.1:{port}"


def _stop_server(server: uvicorn.Server, thread: threading.Thread) -> None:
    server.should_exit = True
    thread.join(timeout=8)
    assert not thread.is_alive()


def _create_active_meeting(base_url: str) -> tuple[httpx.Client, str]:
    client = httpx.Client(base_url=base_url, verify=False, follow_redirects=True)
    response = client.post("/api/workspace/bootstrap")
    assert response.status_code == 200
    created = client.post("/api/live/sessions", json={"echo_mode": "speakers"})
    assert created.status_code == 201
    meeting_id = created.json()["id"]
    assert client.post(
        f"/api/live/sessions/{meeting_id}/heartbeat", json=_heartbeat()
    ).status_code == 200
    for sequence in range(3):
        for lane in ("system", "microphone"):
            assert client.post(
                f"/api/live/sessions/{meeting_id}/frames",
                json=_v2_frame(sequence, lane),
            ).status_code == 200
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        snapshot = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()
        if snapshot["snapshot"]["session"]["effective_transcript"]:
            return client, meeting_id
        time.sleep(0.02)
    raise AssertionError("Active browser Meeting did not publish its transcript.")


def test_real_bundle_same_workspace_views_converge_and_remain_read_only(
    tmp_path: Path,
) -> None:
    chrome = _chrome()
    assert (
        Path(__file__).resolve().parents[2]
        / "moss_transcribe_diarize/app/frontend_assets/app.js"
    ).is_file()
    database = tmp_path / "moss.sqlite3"
    app = create_phase2_app(
        database_path=database,
        live_runtime_factory=_runtime,
        live_helper_lease_seconds=30,
    )
    certificate, private_key = _certificate(tmp_path)
    server, thread, base_url = _start_server(app, certificate, private_key)
    controller = None
    try:
        controller, meeting_id = _create_active_meeting(base_url)
        async def unavailable_audio_fixture():
            store = await Phase2Store.open(database)
            try:
                owner = await store.account_for_session(controller.cookies["__Host-moss_session"])
                handle = await store.workspace(owner).create_meeting("file")
                await handle.record_audio_unavailable()
                await handle.finish("failed")
            finally:
                await store.close()

        # Active Live audio has no final state yet. Exercise the unavailable label
        # with a separate terminal meeting that actually has unavailable audio.
        asyncio.run(unavailable_audio_fixture())
        measured = asyncio.run(
            _exercise_two_browsers(
                chrome=chrome,
                tmp_path=tmp_path,
                base_url=base_url,
                meeting_id=meeting_id,
                credential=controller.cookies["__Host-moss_session"],
            )
        )
        assert measured["distinct_sessions"] is False
        assert measured["desktop_order"] == ["live", "history", "voiceprints"]
        assert measured["mobile_order"] == ["live", "history", "voiceprints"]
        assert measured["desktop_history_visible"] is True
        assert measured["mobile_history_visible"] is True
        assert measured["mobile_inner_width"] <= 768
        assert measured["mobile_screen_width"] == 390
        assert measured["mobile_media"] is True
        assert measured["mobile_user_agent"] is True
        assert measured["viewport_meta"] is True
        assert measured["audio_unavailable_visible"] is True
        assert measured["rename_dialog_accessible"] is True
        assert measured["escape_restored_focus"] is True
        assert measured["both_observed_words"] is True
        assert measured["title_converged"] is True
        assert measured["reload_read_only"] is True
        assert measured["reattach_stored"] is None
    finally:
        if controller is not None:
            controller.close()
        _stop_server(server, thread)


async def _exercise_two_browsers(
    *,
    chrome: Path,
    tmp_path: Path,
    base_url: str,
    meeting_id: str,
    credential: str,
) -> dict[str, object]:
    first = await _ChromePage.launch(
        chrome=chrome,
        profile=tmp_path / "chrome-first",
        url="about:blank",
        width=1280,
        height=720,
    )
    second = await _ChromePage.launch(
        chrome=chrome,
        profile=tmp_path / "chrome-second",
        url="about:blank",
        width=390,
        height=844,
        mobile=True,
    )
    try:
        # Seed the same browser credential into desktop/mobile rendering fixtures.
        # Separate-profile privacy is tested by browser_workspace_probe.py.
        for page in (first, second):
            await page.command("Network.setCookie", {
                "name": "__Host-moss_session", "value": credential, "url": base_url,
                "path": "/", "secure": True, "httpOnly": True, "sameSite": "Lax",
            })
            await page.command("Page.navigate", {"url": base_url})
        ready = "document.querySelector('[data-auth-state=\"signed-in\"]') && document.querySelector('[data-boot=\"ready\"]')"
        await first.wait(ready)
        await second.wait(ready)
        card = (
            f"document.querySelector('.account-history-panel "
            f"[data-open-meeting=\"{meeting_id}\"]')"
        )
        await first.wait(card)
        await second.wait(card)

        first_cookie = next(
            cookie for cookie in await first.cookies(base_url)
            if cookie["name"] == "__Host-moss_session"
        )
        second_cookie = next(
            cookie for cookie in await second.cookies(base_url)
            if cookie["name"] == "__Host-moss_session"
        )

        await first.evaluate(f"{card}.click()")
        await second.evaluate(f"{card}.click()")
        observed = (
            "document.querySelector('[data-observer-mode=\"read-only\"]') && "
            "document.querySelector('#tr-body')?.textContent.includes('Observed live words')"
        )
        await first.wait(observed)
        await second.wait(observed)

        await first.evaluate(
            f"(() => {{ const button = [...document.querySelector('[data-meeting-card=\"{meeting_id}\"]').querySelectorAll('button')]"
            ".find(candidate => candidate.textContent.trim() === 'Rename'); "
            "button.focus(); button.click(); return true; })()"
        )
        await first.wait("document.querySelector('dialog.history-dialog[open]')")
        rename_dialog_accessible = await first.evaluate(
            "(() => { const dialog = document.querySelector('dialog.history-dialog[open]'); "
            "const input = document.querySelector('[aria-label=\"Meeting title\"]'); "
            "return dialog?.getAttribute('role') === 'dialog' && "
            "dialog?.getAttribute('aria-modal') === 'true' && "
            "dialog?.getAttribute('aria-labelledby') === 'rename-meeting-title' && "
            "document.activeElement === input; })()"
        )
        await first.command(
            "Input.dispatchKeyEvent",
            {
                "type": "rawKeyDown",
                "key": "Escape",
                "code": "Escape",
                "windowsVirtualKeyCode": 27,
                "nativeVirtualKeyCode": 27,
            },
        )
        await first.command(
            "Input.dispatchKeyEvent",
            {
                "type": "keyUp",
                "key": "Escape",
                "code": "Escape",
                "windowsVirtualKeyCode": 27,
                "nativeVirtualKeyCode": 27,
            },
        )
        await first.wait("!document.querySelector('dialog.history-dialog')")
        await first.wait(
            "document.activeElement?.textContent.trim() === 'Rename'"
        )
        escape_restored_focus = True
        await first.evaluate(
            f"(() => {{ const button = [...document.querySelector('[data-meeting-card=\"{meeting_id}\"]').querySelectorAll('button')]"
            ".find(candidate => candidate.textContent.trim() === 'Rename'); "
            "button.focus(); button.click(); return true; })()"
        )
        await first.wait("document.querySelector('dialog.history-dialog[open]')")
        await first.evaluate(
            "(() => { const input = document.querySelector('[aria-label=\"Meeting title\"]'); "
            "input.value = 'Shared customer review'; "
            "input.dispatchEvent(new Event('input', {bubbles: true})); return true; })()"
        )
        await first.wait("!document.querySelector('.history-dialog button[type=\"submit\"]').disabled")
        await first.evaluate("document.querySelector('.history-dialog button[type=\"submit\"]').click()")
        renamed = (
            f"document.querySelector('[data-meeting-card=\"{meeting_id}\"]')?.textContent"
            ".includes('Shared customer review')"
        )
        await first.wait(renamed)
        await second.evaluate(
            "document.querySelector('.history-panel-actions button').click()"
        )
        await second.wait(renamed)

        desktop_layout = await _measure_layout(first)
        mobile_layout = await _measure_layout(second)

        await second.reload()
        await second.wait(ready)
        await second.wait(card)
        reload_read_only = await second.evaluate(
            "document.querySelector('[data-capture-phase=\"idle\"]') !== null && "
            "[...document.querySelectorAll('button')].some(button => button.textContent.trim() === 'Enable microphone')"
        )
        reattach_stored = await second.evaluate("sessionStorage.getItem('lt:session:reattach')")
        return {
            "distinct_sessions": first_cookie["value"] != second_cookie["value"],
            "desktop_order": desktop_layout["order"],
            "mobile_order": mobile_layout["order"],
            "desktop_history_visible": desktop_layout["historyVisible"],
            "mobile_history_visible": mobile_layout["historyVisible"],
            "mobile_inner_width": mobile_layout["innerWidth"],
            "mobile_screen_width": mobile_layout["screenWidth"],
            "mobile_media": mobile_layout["mobileMedia"],
            "mobile_user_agent": mobile_layout["mobileUserAgent"],
            "viewport_meta": mobile_layout["viewportMeta"],
            "audio_unavailable_visible": await second.evaluate(
                "document.querySelector('[data-audio-unavailable]')?.textContent.trim() === "
                "'Audio unavailable'"
            ),
            "rename_dialog_accessible": rename_dialog_accessible,
            "escape_restored_focus": escape_restored_focus,
            "both_observed_words": True,
            "title_converged": True,
            "reload_read_only": reload_read_only,
            "reattach_stored": reattach_stored,
        }
    finally:
        first.close()
        second.close()


async def _measure_layout(page: _ChromePage) -> dict[str, object]:
    return await page.evaluate(
        "(() => { const sections = [...document.querySelectorAll('[data-workspace-section]')]; "
        "const history = document.querySelector('[data-workspace-section=\"history\"]'); "
        "history.scrollIntoView({block: 'end'}); const box = history.getBoundingClientRect(); "
        "return {order: sections.map(section => section.dataset.workspaceSection), "
        "historyVisible: box.top < innerHeight && box.bottom > 0, innerWidth, "
        "screenWidth: screen.width, mobileMedia: matchMedia('(max-width: 768px)').matches, "
        "mobileUserAgent: navigator.userAgent.includes('Mobile'), "
        "viewportMeta: document.querySelector('meta[name=\"viewport\"]')?.content === "
        "'width=device-width, initial-scale=1'}; })()"
    )
