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
