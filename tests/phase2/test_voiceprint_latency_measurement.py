"""The E2E clock measures the visible name, not when the test runner wakes up."""
import asyncio
from types import SimpleNamespace

from playwright.async_api import async_playwright

from tests.e2e.verify_workspace import Harness, FIRST_ENROLLED_LABEL_BOUND_SECONDS
from tests.phase2.browser_support import require_browser


def test_name_latency_is_independent_of_observer_polling_delay(tmp_path):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=str(require_browser(p)), headless=True)
            try:
                page = await browser.new_page()
                html = '''<div data-boot="ready">Ready</div>
                  <section aria-label="Private voiceprints"><button>Voiceprints</button>
                    <div data-voiceprint-id="saved">E2E Rowan</div></section>
                  <button onclick="setTimeout(() => {
                    const label = document.createElement('span');
                    label.className = 'utt-speaker-label'; label.textContent = 'E2E Rowan';
                    document.body.append(label);
                  }, 200)">Start capture</button>'''
                await page.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html', body=html))
                await page.goto('https://measurement.test/')
                class Probe(Harness):
                    async def api(self, path):
                        return {"body": {"events": []}}
                    async def setup_live(self):
                        pass
                    async def start_live(self, key):
                        await self.page.get_by_role('button', name='Start capture', exact=True).click()
                        return 'controlled-meeting'
                probe = Probe(SimpleNamespace(output=str(tmp_path)))
                probe.page = page
                original_wait = page.wait_for_function
                async def late_reader(*args, **kwargs):
                    await asyncio.sleep(.8)
                    return await original_wait(*args, **kwargs)
                page.wait_for_function = late_reader
                try:
                    result = await probe.bank()
                    assert result['ok'] and result['bank_contains_name']
                    assert .18 <= result['recognition_seconds'] < .5
                    assert result['measurement'] == 'Start click to visible name DOM mutation'
                finally:
                    probe.network.close()
            finally:
                await browser.close()
    asyncio.run(run())


def test_enrolled_label_budget_derives_from_live_pipeline():
    # Preserve the 2.5s canonical cap; allow 1s processing and 0.5s frame/poll.
    assert FIRST_ENROLLED_LABEL_BOUND_SECONDS == 2.5 + 1.0 + .5
    assert 3.7007 <= FIRST_ENROLLED_LABEL_BOUND_SECONDS < 10.844687
