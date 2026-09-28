"""Real browser/workspace/relay flow with an in-process fake upstream; no host operations.

PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/relay_browser_probe.py
Print content-free checks only. Scratch SQLite, muted headless Chrome, no model calls.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

import httpx
from playwright.async_api import async_playwright
from moss_transcribe_diarize.app import phase2

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("workspace_bench", ROOT / "prototypes/phase2-account-lifecycle/browser_workspace_probe.py")
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
CONFIG = json.dumps([
    {"name": "primary", "base_url": "http://localhost:1234/v1", "models": ["primary-model"]},
    {"name": "fallback", "base_url": "http://localhost:1235/v1", "models": ["fallback-model"]},
])


async def run(root):
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    calls = []
    def upstream(request):
        model = json.loads(request.content)["model"]
        calls.append({"model": model, "cookie_forwarded": "cookie" in request.headers})
        document = {"summary": "Relay worked", "topics": [], "details": [], "speaker_background": [], "data_references": []}
        return httpx.Response(200, json={"choices": [{"message": {
            "reasoning_content": "Controlled reasoning", "content": "" if model == "primary-model" else json.dumps(document)}}]})
    with patch.dict(os.environ, {"MOSS_LLM_UPSTREAMS": CONFIG}):
        async with bench.running(root / "probe.sqlite3") as (app, port):
            app.state.llm_relay.transport = httpx.MockTransport(upstream)
            async with async_playwright() as p:
                browser = await p.chromium.launch(channel="chrome", headless=True, args=["--mute-audio"])
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await bench.open_workspace(page, f"http://localhost:{port}")
                    checks = {"default_relay_configured": True, "discovery_does_not_infer": not calls}
                    cookie = next(c["value"] for c in await context.cookies() if c["name"] == phase2.SESSION_COOKIE)
                    store = app.state.phase2_store
                    account = await store.account_for_session(cookie)
                    meeting = await store.workspace(account).create_meeting("file")
                    await meeting.commit_transcript({"segments": [{"start": 0, "end": 1, "speaker": "Alex", "text": "Synthetic probe speech"}]}, terminal=True)
                    await page.locator('[data-history-boot="ready"]').wait_for()
                    await page.get_by_role("button", name="Refresh", exact=True).click()
                    await page.locator(f'[data-open-meeting="{meeting.meeting_id}"]').click()
                    await page.locator(f'[data-open-meeting="{meeting.meeting_id}"][aria-pressed="true"]').wait_for()
                    await page.get_by_role("button", name="Open summary", exact=True).click()
                    await page.get_by_role("button", name="Optional AI summaries · configured", exact=True).click()
                    await page.get_by_label("Relay model", exact=True).wait_for()
                    checks["two_models_and_no_key"] = await page.get_by_label("Relay model", exact=True).locator("option").count() == 2 and await page.get_by_label("API key (optional)", exact=True).count() == 0
                    await page.get_by_test_id("final-summary-generate").click()
                    await page.locator('[data-summary-state="current"]').wait_for(timeout=10000)
                    checks["one_fallback"] = [c["model"] for c in calls] == ["primary-model", "primary-model", "fallback-model"]
                    checks["status_names_model"] = "fallback-model" in await page.locator('[aria-label="Final summary"] [role="status"]').inner_text()
                    checks["cookie_not_forwarded"] = not any(c["cookie_forwarded"] for c in calls)
                    response = await page.evaluate("async id => (await (await fetch('/api/meetings/'+id+'/summary')).json()).summary", meeting.meeting_id)
                    checks["validated_result_persisted"] = response["state"] == "current" and response["document"]["summary"] == "Relay worked"
                    print(json.dumps({"checks": checks, "passed": sum(checks.values()), "total": len(checks),
                                      "upstream": "in-process fake; no model/network", "sqlite": sqlite3.sqlite_version}, indent=2))
                    if not all(checks.values()): raise SystemExit(1)
                finally:
                    await browser.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-relay-browser-") as directory:
        asyncio.run(run(Path(directory)))
