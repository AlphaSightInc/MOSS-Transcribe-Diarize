"""Optional-browser G9 regressions; required evaluator tests remain browser-free."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

from playwright.async_api import async_playwright, expect as async_expect

from moss_transcribe_diarize.app import phase2
from tests.phase2.browser_support import require_browser

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("summary_paths_probe", ROOT / "prototypes/client-configured-llm/final_browser_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


async def open_selected_summary(page, context, app):
    cookie = next(c["value"] for c in await context.cookies() if c["name"] == phase2.SESSION_COOKIE)
    account = await app.state.phase2_store.account_for_session(cookie)
    handle = await app.state.phase2_store.workspace(account).create_meeting("file")
    await handle.commit_transcript({"segments": [{"start": 0, "end": 1,
        "speaker": "S01", "text": "Local summary fixture"}]}, terminal=True)
    await page.get_by_role("region", name="Meeting history", exact=True).get_by_role("button", name="Refresh", exact=True).click()
    await page.locator(f'[data-open-meeting="{handle.meeting_id}"]').click()
    await page.locator(f'[data-open-meeting="{handle.meeting_id}"][aria-pressed="true"]').wait_for()
    await page.get_by_role("tab", name="Summary", exact=True).click()
    await page.get_by_label("Summary", exact=True).wait_for()
    await page.get_by_role("button", name="Settings", exact=True).click()
    await page.get_by_role("dialog", name="Settings", exact=True).wait_for()


def test_deployed_predicate_selects_external_when_relay_is_default(tmp_path):
    async def browser_check(origin, chrome, app):
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=chrome, headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(origin)
                await page.locator('[data-history-boot="ready"]').wait_for()
                await open_selected_summary(page, context, app)
                region = page.get_by_role("dialog", name="Settings", exact=True)
                await region.get_by_role("tab", name="Summary", exact=True).click()
                await async_expect(region.get_by_label("Summary vendor", exact=True)).to_have_value("gemini")
                assert await region.get_by_label("Summary URL", exact=True).count() == 0
                await probe.select_external_summary_provider(region)
                await region.get_by_label("Summary URL", exact=True).fill("https://example.test/v1")
                await region.get_by_label("Summary model", exact=True).fill("external-test")
                assert await region.get_by_label("Summary vendor", exact=True).input_value() == "openai_compatible"
                assert await region.get_by_label("Summary URL", exact=True).input_value() == "https://example.test/v1"
                assert await region.get_by_label("Summary model", exact=True).input_value() == "external-test"
            finally:
                await browser.close()

    async def run():
        async with async_playwright() as p:
            chrome = str(require_browser(p))
        config = json.dumps([{"name": "Test relay", "base_url": "http://127.0.0.1:1/v1", "models": ["test-model"]}])
        async with probe.running_summary_workspace(tmp_path / "predicate.sqlite", llm_upstreams=config) as (app, port):
            await browser_check(f"http://localhost:{port}", chrome, app)
    asyncio.run(run())


def test_real_browser_external_and_relay_paths_with_fake_upstreams(tmp_path):
    async def run():
        async with async_playwright() as p:
            chrome = str(require_browser(p))
        return await probe.run(tmp_path, chrome)
    result = asyncio.run(run())
    assert result["passed"] == result["total"]
    assert result["real_preflight_and_post"] is True
    assert result["two_durable_results_no_provider_metadata"] is True


def test_deterministic_probe_selection_with_relay_models_present(tmp_path):
    async def run():
        async with async_playwright() as p:
            chrome = str(require_browser(p))
            config = json.dumps([{"name": "Selection fixture", "base_url": "http://127.0.0.1:1/v1", "models": ["relay-model"]}])
            async with probe.running_summary_workspace(tmp_path / "async-selection.sqlite", llm_upstreams=config) as (app, port):
                browser = await p.chromium.launch(executable_path=chrome, headless=True)
                try:
                    page = await browser.new_page()
                    await page.goto(f"http://localhost:{port}")
                    await page.locator('[data-history-boot="ready"]').wait_for()
                    await open_selected_summary(page, page.context, app)
                    region = page.get_by_role("dialog", name="Settings", exact=True)
                    await region.get_by_role("tab", name="Summary", exact=True).click()
                    await async_expect(region.get_by_label("Summary vendor", exact=True)).to_have_value("gemini")
                    assert await region.get_by_label("Summary URL", exact=True).count() == 0
                    # Invoke the exact helper imported by the deterministic probe.
                    await probe.select_external_summary_provider(region)
                    await region.get_by_label("Summary URL", exact=True).fill("https://example.test/v1")
                    assert await region.get_by_label("Summary vendor", exact=True).input_value() == "openai_compatible"
                    assert await region.get_by_label("Summary URL", exact=True).input_value() == "https://example.test/v1"
                finally:
                    await browser.close()
    asyncio.run(run())


def test_relay_wait_rejects_old_current_artifact_during_new_attempt(tmp_path):
    async def run():
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=str(require_browser(p)),headless=True)
            try:
                page=await browser.new_page()
                async def route(request):
                    if request.request.method=='POST':
                        await asyncio.sleep(.2)
                        await request.fulfill(json={'attempt_id':'new-attempt'})
                    else:
                        await request.fulfill(content_type='text/html',body='''<section data-summary-state="off"></section>
                        <button data-testid="final-summary-generate" onclick="
                          const el=document.querySelector('section');
                          el.dataset.summaryState='current'; el.dataset.summaryAttempt='old-attempt';
                          fetch('/api/meetings/owned/summary',{method:'POST'}).then(()=>setTimeout(()=>{
                            el.dataset.summaryAttempt='new-attempt';
                          },200));">Generate</button>''')
                await page.route('**/*',route)
                await page.goto('https://fixture.test/')
                observed = probe.AsyncEvidencePage(
                    page, probe.BrowserTimeoutEvidence(tmp_path, 'browser_final_summary'),
                    'summary.generate')
                pending=asyncio.create_task(probe.regenerate_summary(observed,'owned'))
                # Reproduce the host shape: the old artifact arrives after previous=None.
                await page.wait_for_function("previous => { const el=document.querySelector('[data-summary-state]'); return el.dataset.summaryState === 'current' && el.dataset.summaryAttempt !== previous; }",arg=None)
                assert await page.locator('section').get_attribute('data-summary-attempt')=='old-attempt'
                assert not pending.done(), 'Old artifact released the new-attempt wait'
                await pending
                assert await page.locator('section').get_attribute('data-summary-attempt')=='new-attempt'
            finally: await browser.close()
    asyncio.run(run())
