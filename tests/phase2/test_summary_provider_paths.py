"""Optional-browser G9 regressions; required evaluator tests remain browser-free."""
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

from moss_transcribe_diarize.phase2_acceptance_summary import configure_external_summary
from tests.phase2.browser_support import require_browser

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("summary_paths_probe", ROOT / "prototypes/client-configured-llm/final_browser_probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_deployed_predicate_selects_external_when_relay_is_default(tmp_path):
    def browser_check(origin, chrome):
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=chrome, headless=True)
            try:
                page = browser.new_page()
                page.goto(origin)
                page.locator('[data-history-boot="ready"]').wait_for()
                region = page.get_by_role("region", name="Browser AI settings", exact=True)
                region.get_by_role("button").click()
                assert region.get_by_label("Provider", exact=True).input_value() == "relay"
                assert region.get_by_label("Provider HTTPS URL", exact=True).count() == 0
                configure_external_summary(page, endpoint="https://example.test/v1", model="external-test",
                    api_key="test-key", prompt="test-prompt")
                assert region.get_by_label("Provider", exact=True).input_value() == "external"
                assert region.get_by_label("Provider HTTPS URL", exact=True).input_value() == "https://example.test/v1"
                assert region.get_by_label("Model", exact=True).input_value() == "external-test"
            finally:
                browser.close()

    async def run():
        async with async_playwright() as p:
            chrome = str(require_browser(p))
        config = json.dumps([{"name": "Test relay", "base_url": "http://127.0.0.1:1/v1", "models": ["test-model"]}])
        async with probe.bench.running(tmp_path / "predicate.sqlite", llm_upstreams=config) as (_, port):
            await asyncio.to_thread(browser_check, f"http://localhost:{port}", chrome)
    asyncio.run(run())


def test_real_browser_external_and_relay_paths_with_fake_upstreams(tmp_path):
    async def run():
        async with async_playwright() as p:
            chrome = str(require_browser(p))
        return await probe.run(tmp_path, chrome)
    result = asyncio.run(run())
    assert result["passed"] == result["total"]
    assert result["relay"]["upstream_requests"] == 1
    assert all(result["relay"]["checks"].values())


def test_deterministic_probe_selection_with_relay_models_present(tmp_path):
    async def run():
        async with async_playwright() as p:
            chrome = str(require_browser(p))
            config = json.dumps([{"name": "Selection fixture", "base_url": "http://127.0.0.1:1/v1", "models": ["relay-model"]}])
            async with probe.bench.running(tmp_path / "async-selection.sqlite", llm_upstreams=config) as (_, port):
                browser = await p.chromium.launch(executable_path=chrome, headless=True)
                try:
                    page = await browser.new_page()
                    await page.goto(f"http://localhost:{port}")
                    await page.locator('[data-history-boot="ready"]').wait_for()
                    region = page.get_by_role("region", name="Browser AI settings", exact=True)
                    await region.get_by_role("button").click()
                    assert await region.get_by_label("Provider", exact=True).input_value() == "relay"
                    assert await region.get_by_label("Provider HTTPS URL", exact=True).count() == 0
                    # Invoke the exact helper imported by the deterministic probe.
                    await probe.select_external_summary_provider(region)
                    await region.get_by_label("Provider HTTPS URL", exact=True).fill("https://example.test/v1")
                    assert await region.get_by_label("Provider", exact=True).input_value() == "external"
                    assert await region.get_by_label("Provider HTTPS URL", exact=True).input_value() == "https://example.test/v1"
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
                pending=asyncio.create_task(probe.regenerate_summary(page,'owned'))
                # Reproduce the host shape: the old artifact arrives after previous=None.
                await page.wait_for_function("previous => { const el=document.querySelector('[data-summary-state]'); return el.dataset.summaryState === 'current' && el.dataset.summaryAttempt !== previous; }",arg=None)
                assert await page.locator('section').get_attribute('data-summary-attempt')=='old-attempt'
                assert not pending.done(), 'Old artifact released the new-attempt wait'
                await pending
                assert await page.locator('section').get_attribute('data-summary-attempt')=='new-attempt'
            finally: await browser.close()
    asyncio.run(run())
