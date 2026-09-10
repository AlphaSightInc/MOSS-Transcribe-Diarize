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
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from playwright.async_api import async_playwright

from moss_transcribe_diarize.app import phase2


@asynccontextmanager
async def running(database, port=0):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    port = listener.getsockname()[1]
    app = phase2.create_phase2_app(database_path=database)

    @app.middleware("http")
    async def delayed_cookie(request, call_next):
        response = await call_next(request)
        if request.url.path == "/api/workspace/bootstrap":
            await asyncio.sleep(.05)  # Fault injection, not a production threshold.
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
    }
    evidence["passed"] = all(evidence.get(k) == v for k, v in expected.items())
    evidence["checks"] = len(expected)
    print(json.dumps({"stage": "final", **evidence}, indent=2), flush=True)
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-browser-prototype-") as scratch:
        asyncio.run(probe(Path(scratch)))
