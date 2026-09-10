"""THROWAWAY: can one browser bootstrap a durable private workspace without input?

Run from the worktree root with its Python dependencies:
  PYTHONPATH=. python prototypes/phase2-account-lifecycle/browser_workspace_probe.py

Real production meeting store/handles; proposed owner-table header and admission only.
Two real persistent Chrome profiles, muted/headless; no capture or audio playback.
Scratch SQLite and browser state are removed by TemporaryDirectory. Host SQLite is
reported explicitly; this is NOT pinned-Linux-runtime or production-TLS qualification.
"""
from __future__ import annotations

import asyncio
import json
import secrets
import socket
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from playwright.async_api import async_playwright

from moss_transcribe_diarize.app import phase2


OWNER_DDL = """CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    enabled INTEGER NOT NULL CHECK(enabled IN (0, 1)),
    authority_generation INTEGER NOT NULL,
    created_at_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class BrowserOwner:
    account_id: str
    display_name: str
    authority_generation: int


class PrototypeStore(phase2.Phase2Store):
    async def _initialize_schema(self):
        # Replace ONLY the proposed Google owner header. All meeting/audio/child
        # tables and every meeting operation remain the real production code.
        execute = self._connection.executescript

        async def proposed_schema(sql):
            start = sql.index("CREATE TABLE account_allowlist")
            end = sql.index("CREATE TABLE sign_in_sessions")
            return await execute(
                (sql[:start] + OWNER_DDL + sql[end:]).replace(
                    "PRAGMA user_version = 1;", "PRAGMA user_version = 2;"
                )
            )

        self._connection.executescript = proposed_schema
        try:
            await super()._initialize_schema()
        finally:
            self._connection.executescript = execute

    async def account_for_session(self, credential):
        if not credential:
            return None
        async with self._external_read():
            cursor = await self._connection.execute(
                """SELECT a.account_id, a.display_name, a.authority_generation
                   FROM accounts a JOIN sign_in_sessions s USING(account_id)
                   WHERE s.session_id=? AND a.enabled=1""",
                (credential,),
            )
            row = await cursor.fetchone()
            await cursor.close()
        return None if row is None else BrowserOwner(**dict(row))

    async def bootstrap(self, credential):
        if credential:
            owner = await self.account_for_session(credential)
            if owner is None:
                raise HTTPException(401, "Workspace credential is no longer valid.")
            return owner, credential
        owner = BrowserOwner(secrets.token_urlsafe(24), "This browser", 0)
        credential = secrets.token_urlsafe(32)
        now = phase2._now_ms()
        async with self._mutation():
            await self._connection.execute(
                "INSERT INTO accounts VALUES (?, ?, 1, 0, ?, ?)",
                (owner.account_id, owner.display_name, now, now),
            )
            await self._connection.execute(
                "INSERT INTO sign_in_sessions VALUES (?, ?, ?)",
                (credential, owner.account_id, now),
            )
        return owner, credential


BOOTSTRAP_JS = """async () => {
  return await navigator.locks.request('moss-workspace-bootstrap', async () => {
    let current = await fetch('/api/auth/session', {cache: 'no-store'});
    if (current.status === 401) {
      const created = await fetch('/api/workspace/bootstrap', {method: 'POST'});
      if (!created.ok) throw new Error('Bootstrap refused');
      current = await fetch('/api/auth/session', {cache: 'no-store'});
    }
    if (!current.ok) throw new Error('Cookies are required');
    const value = await current.json();
    window.owner = value.workspace_id;
    return value.workspace_id;
  });
} """


def application(database):
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = await PrototypeStore.open(database)
        try:
            yield
        finally:
            await app.state.store.close()

    app = FastAPI(lifespan=lifespan)

    async def owner(request):
        value = await app.state.store.account_for_session(
            request.cookies.get(phase2.SESSION_COOKIE)
        )
        if value is None:
            raise HTTPException(401, "Workspace unavailable")
        return value

    @app.get("/")
    async def root():
        return HTMLResponse("<!doctype html><title>Quiet workspace prototype</title>")

    @app.get("/api/auth/session")
    async def session(request: Request):
        return {"workspace_id": (await owner(request)).account_id}

    @app.post("/api/workspace/bootstrap")
    async def bootstrap(request: Request):
        value, credential = await app.state.store.bootstrap(
            request.cookies.get(phase2.SESSION_COOKIE)
        )
        # Delayed cookie delivery attacks first-tab initialization; not a product threshold.
        await asyncio.sleep(.05)
        response = JSONResponse({"workspace_id": value.account_id})
        response.set_cookie(
            phase2.SESSION_COOKIE, credential, secure=True, httponly=True,
            samesite="lax", path="/", max_age=phase2.SESSION_COOKIE_MAX_AGE,
        )
        return response

    @app.post("/api/meetings")
    async def create(request: Request):
        workspace = app.state.store.workspace(await owner(request))
        handle = await workspace.create_meeting("file")
        await handle.commit_transcript({"segments": [{"text": "silent sentinel"}]})
        await handle.finish("completed")
        return (await handle.snapshot()).to_dict()

    @app.get("/api/meetings")
    async def history(request: Request):
        workspace = app.state.store.workspace(await owner(request))
        return {"meetings": [m.to_dict() for m in await workspace.list_meetings()]}

    @app.get("/api/meetings/{meeting_id}")
    async def meeting(meeting_id: str, request: Request):
        handle = await app.state.store.workspace(await owner(request)).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(404, "Meeting unavailable")
        return (await handle.snapshot()).to_dict()

    return app


@asynccontextmanager
async def running(database, port=0):
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", port))
    port = listener.getsockname()[1]
    app = application(database)
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


async def probe(root):
    # Same semantic-test accommodation as tests/phase2/conftest.py; print reality.
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    phase2.SCHEMA_VERSION = 2
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
                await asyncio.gather(*(p.goto(origin) for p in (a1, a2, b1)))
                owners = await asyncio.gather(*(p.evaluate(BOOTSTRAP_JS) for p in (a1, a2, b1)))
                evidence["two_tabs_one_workspace"] = owners[0] == owners[1]
                evidence["second_profile_isolated"] = owners[2] != owners[0]
                created = await a1.evaluate("async () => (await fetch('/api/meetings',{method:'POST'})).json()")
                meeting_id = created["id"]
                evidence["foreign_meeting_status"] = await b1.evaluate(
                    "async id => (await fetch('/api/meetings/'+id)).status", meeting_id
                )
                evidence["javascript_cannot_read_cookie"] = await a1.evaluate("document.cookie === ''")
                cookies = await a.cookies()
                c = next(c for c in cookies if c["name"] == phase2.SESSION_COOKIE)
                evidence["cookie_flags"] = {k: c[k] for k in ("httpOnly", "secure", "sameSite")}
                evidence["old_owner_columns_removed"] = "account_allowlist" not in await app.state.store.table_names()
                control = await profile("no-lock-control")
                try:
                    pages = [await control.new_page(), await control.new_page()]
                    await asyncio.gather(*(p.goto(origin) for p in pages))
                    no_lock = BOOTSTRAP_JS.replace(
                        "navigator.locks.request('moss-workspace-bootstrap', async () => {",
                        "(async () => {",
                    ).replace("  });", "  })();")
                    split = await asyncio.gather(*(p.evaluate(no_lock) for p in pages))
                    evidence["without_lock_workspace_count"] = len(set(split))
                finally:
                    await control.close()
                print(json.dumps({"stage": "bootstrap", **evidence}), flush=True)
            await a.close()
            a = await profile("profile-a")
            async with running(database, port):
                page = await a.new_page()
                await page.goto(origin)
                returned = await page.evaluate(BOOTSTRAP_JS)
                history = await page.evaluate("async () => (await fetch('/api/meetings')).json()")
                evidence["browser_and_server_restart_same_workspace"] = returned == owners[0]
                evidence["restart_saved_meeting"] = history["meetings"][0]["id"] == meeting_id
                await a.clear_cookies()
                evidence["lost_cookie_mutation_status"] = await page.evaluate(
                    "async () => (await fetch('/api/meetings',{method:'POST'})).status"
                )
                new_owner = await page.evaluate(BOOTSTRAP_JS)
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
