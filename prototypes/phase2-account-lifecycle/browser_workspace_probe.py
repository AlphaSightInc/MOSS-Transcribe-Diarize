"""THROWAWAY: can one browser bootstrap a durable private workspace without input?

Run from the worktree root with its Python dependencies:
  PYTHONPATH=. python prototypes/phase2-account-lifecycle/browser_workspace_probe.py

Absorbed onto the real production HTTP, bootstrap JavaScript, schema and meeting handles.
Two real persistent Chrome profiles, muted/headless; no capture or audio playback.
Scratch SQLite and browser state are removed by TemporaryDirectory. Host SQLite is
reported explicitly; this is NOT pinned-Linux-runtime or production-TLS qualification.
"""
from __future__ import annotations

import asyncio
import json
import socket
import sqlite3
import tempfile
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import uvicorn
from playwright.async_api import async_playwright

from moss_transcribe_diarize.app import phase2


@asynccontextmanager
async def running(database, port=0, *, file_runner=None):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    port = listener.getsockname()[1]
    app = phase2.create_phase2_app(
        database_path=database, file_runner=file_runner,
        file_work_root=database.parent / "file-work",
    )

    @app.middleware("http")
    async def delayed_cookie(request, call_next):
        response = await call_next(request)
        if request.url.path == "/api/workspace/bootstrap":
            await asyncio.sleep(.05)  # Fault injection, not a production threshold.
            if getattr(app.state, "probe_drop_cookie", False):
                del response.headers["set-cookie"]
        return response
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
    task = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        for _ in range(500):
            if server.started:
                break
            if task.done():
                await task
                raise RuntimeError("Prototype server did not start")
            await asyncio.sleep(.01)
        yield app, port
    finally:
        server.should_exit = True
        await task
        listener.close()


async def open_workspace(page, origin):
    await page.goto(origin)
    await page.locator("[data-workspace-name]").wait_for()
    return await page.evaluate("async () => (await (await fetch('/api/auth/session')).json()).workspace_id")


async def probe(root):
    # Same semantic-test accommodation as tests/phase2/conftest.py; print reality.
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    database = root / "PROTOTYPE-wipe-me.sqlite3"
    evidence = {"sqlite": sqlite3.sqlite_version, "headless_muted": True}
    async with async_playwright() as browser:
        async def profile(name):
            return await browser.chromium.launch_persistent_context(
                str(root / name), headless=True, channel="chrome", args=["--mute-audio"],
            )

        a, b = await profile("profile-a"), await profile("profile-b")
        try:
            async with running(database) as (app, port):
                origin = f"http://localhost:{port}"
                a1, a2, b1 = await a.new_page(), await a.new_page(), await b.new_page()
                owners = await asyncio.gather(*(open_workspace(p, origin) for p in (a1, a2, b1)))
                evidence["two_tabs_one_workspace"] = owners[0] == owners[1]
                evidence["second_profile_isolated"] = owners[2] != owners[0]
                credential = next(c["value"] for c in await a.cookies() if c["name"] == phase2.SESSION_COOKIE)
                store = app.state.phase2_store
                owner = await store.account_for_session(credential)
                handle = await store.workspace(owner).create_meeting("file")
                await handle.commit_transcript({"segments": [{"text": "silent sentinel"}]})
                await handle.finish("completed")
                meeting_id = handle.meeting_id
                evidence["foreign_meeting_status"] = await b1.evaluate(
                    "async id => (await fetch('/api/meetings/'+id)).status", meeting_id
                )
                evidence["javascript_cannot_read_cookie"] = await a1.evaluate("document.cookie === ''")
                cookies = await a.cookies()
                c = next(c for c in cookies if c["name"] == phase2.SESSION_COOKIE)
                evidence["cookie_flags"] = {k: c[k] for k in ("httpOnly", "secure", "sameSite")}
                evidence["old_owner_columns_removed"] = "account_allowlist" not in await app.state.phase2_store.table_names()
                control = await profile("no-lock-control")
                try:
                    observed_ids = []
                    async def remove_lock(route):
                        response = await route.fetch()
                        body = (await response.text()).replace(
                            "navigator.locks.request('moss-workspace-bootstrap', async () => {",
                            "(async () => {",
                        ).replace("  });\n  location.replace", "  })();\n  location.replace")
                        await route.fulfill(response=response, body=body)

                    async def observe(route):
                        response = await route.fetch()
                        observed_ids.append((await response.json())["workspace_id"])
                        await route.fulfill(response=response)

                    await control.route(origin + "/", remove_lock)
                    await control.route(origin + "/api/workspace/bootstrap", observe)
                    pages = [await control.new_page(), await control.new_page()]
                    await asyncio.gather(*(open_workspace(p, origin) for p in pages))
                    evidence["without_lock_workspace_count"] = len(set(observed_ids))
                finally:
                    await control.close()
                blocked = await profile("cookie-roundtrip-failure")
                try:
                    app.state.probe_drop_cookie = True
                    page = await blocked.new_page()
                    await page.goto(origin)
                    await page.get_by_text("Allow cookies for this site, then reload.", exact=True).wait_for()
                    evidence["failed_cookie_roundtrip_blocks_ui"] = await page.locator("[data-workspace-name]").count() == 0
                finally:
                    app.state.probe_drop_cookie = False
                    await blocked.close()
                unsupported = await profile("unsupported-locks")
                try:
                    page = await unsupported.new_page()
                    await page.add_init_script("Object.defineProperty(navigator, 'locks', {value: undefined})")
                    await page.goto(origin)
                    await page.get_by_text("Use Chrome with trusted HTTPS to open this workspace.", exact=True).wait_for()
                    evidence["unsupported_locks_blocks_ui"] = await page.locator("[data-workspace-name]").count() == 0
                finally:
                    await unsupported.close()
                print(json.dumps({"stage": "bootstrap", **evidence}), flush=True)
            await a.close()
            a = await profile("profile-a")
            async with running(database, port):
                page = await a.new_page()
                returned = await open_workspace(page, origin)
                history = await page.evaluate("async () => (await fetch('/api/meetings')).json()")
                evidence["browser_and_server_restart_same_workspace"] = returned == owners[0]
                evidence["restart_saved_meeting"] = history["meetings"][0]["id"] == meeting_id
                await a.clear_cookies()
                evidence["lost_cookie_mutation_status"] = await page.evaluate(
                    "async id => (await fetch('/api/meetings/'+id+'/title', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify({title:'must not write'})})).status", meeting_id
                )
                new_owner = await open_workspace(page, origin)
                evidence["new_visit_new_workspace"] = new_owner != returned
                await a.add_cookies([{**c, "value": "invalid-credential"}])
                evidence["invalid_cookie_bootstrap_status"] = await page.evaluate(
                    "async () => (await fetch('/api/workspace/bootstrap',{method:'POST'})).status"
                )
        finally:
            await a.close()
            await b.close()
    expected = {
        "two_tabs_one_workspace": True, "second_profile_isolated": True,
        "foreign_meeting_status": 404, "javascript_cannot_read_cookie": True,
        "old_owner_columns_removed": True, "browser_and_server_restart_same_workspace": True,
        "restart_saved_meeting": True, "lost_cookie_mutation_status": 401,
        "new_visit_new_workspace": True, "invalid_cookie_bootstrap_status": 401,
        "without_lock_workspace_count": 2,
        "failed_cookie_roundtrip_blocks_ui": True,
        "unsupported_locks_blocks_ui": True,
    }
    evidence["passed"] = all(evidence.get(k) == v for k, v in expected.items())
    evidence["checks"] = len(expected)
    print(json.dumps({"stage": "final", **evidence}, indent=2), flush=True)
    if not evidence["passed"]:
        raise SystemExit(1)


async def collector_probe(root):
    """Exercise the actual G2 collector with only TLS and inference stubbed.

    This is a local collector-semantics probe. It MUST NOT supply deployed evidence:
    production TLS is not trusted here and this runner does not establish speech quality.
    """
    from moss_transcribe_diarize.phase2_acceptance_browser import BrowserCampaign, BrowserMeasurementError

    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    fixture = root / "collector.wav"
    with wave.open(str(fixture), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\0\0" * 16000)

    class Runner:
        model_path = "semantic-probe-only"

        def transcribe(self, path, **kwargs):
            return SimpleNamespace(text="[0][S01]saved collector sentinel[1]")

    async with running(root / "collector.sqlite3", file_runner=Runner()) as (app, port):
        campaign = BrowserCampaign(
            {"https_origin": "https://localhost", "file_fixture": str(fixture),
             "chrome_binary": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"},
            repo=Path.cwd(), work=root,
        )
        campaign.origin = f"http://localhost:{port}"
        loop = asyncio.get_running_loop()

        def control(command, _unused):
            assert command == "accounts.list"
            return asyncio.run_coroutine_threadsafe(app.state.phase2_store.list_accounts(), loop).result(10)

        with patch("moss_transcribe_diarize.phase2_acceptance_browser._trusted_tls_identity", return_value={"trusted": False}):
            result = await asyncio.to_thread(campaign.browser_workspace_identity, control)
        expected = {
            "first_tabs": 2, "created_workspaces": 2, "same_profile_owner": True,
            "first_tab_lock_contention_observed": True,
            "profiles_isolated": True, "foreign_meeting_status": 404,
            "mutation_without_cookie_status": 401, "invalid_cookie_bootstrap_status": 401,
            "cross_origin_status": 403, "browser_restart_session_survived": True,
            "history_survived_restart": True, "nonempty_saved_history": True,
        }
        assert all(result.get(key) == value for key, value in expected.items()), result
        assert result["tls_trusted_without_interstitial"] is False
        print(json.dumps({"collector_semantics": "pass", "checks": len(expected), "deployed_qualification": False}), flush=True)
        original_html = phase2._bootstrap_html
        def without_lock(*, unavailable):
            return original_html(unavailable=unavailable).replace(
                "navigator.locks.request('moss-workspace-bootstrap', async () => {",
                "(async () => {",
            ).replace("  });\n  location.replace", "  })();\n  location.replace")
        rejected = False
        with patch("moss_transcribe_diarize.phase2_acceptance_browser._trusted_tls_identity", return_value={"trusted": False}), patch.object(phase2, "_bootstrap_html", without_lock):
            try:
                await asyncio.to_thread(campaign.browser_workspace_identity, control)
            except BrowserMeasurementError as exc:
                assert str(exc) == "First tabs did not serialize bootstrap"
                rejected = True
        assert rejected
        print(json.dumps({"collector_removed_lock_mutation": "rejected", "deployed_qualification": False}), flush=True)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-browser-prototype-") as scratch:
        asyncio.run(probe(Path(scratch)))
        asyncio.run(collector_probe(Path(scratch)))
