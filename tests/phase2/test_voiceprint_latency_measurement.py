"""The E2E clock measures the visible name, not when the test runner wakes up."""
import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

from playwright.async_api import async_playwright

from tests.e2e.verify_workspace import Harness, FIRST_ENROLLED_LABEL_BOUND_SECONDS, project_row10_timing
from tests.phase2.browser_support import require_browser


def test_name_latency_is_independent_of_observer_polling_delay(tmp_path):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=str(require_browser(p)), headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                html = '''<div data-auth-state="signed-in" data-boot="ready" data-history-boot="ready">Ready</div>
                  <section aria-label="Meeting history"><button role="tab">Voiceprints</button></section>
                  <section aria-label="Private voiceprints">
                    <div data-voiceprint-id="saved">E2E Rowan</div></section>
                  <button onclick="setTimeout(() => {
                    const label = document.createElement('span');
                    label.className = 'utt-speaker-label'; label.textContent = 'E2E Rowan';
                    document.body.append(label);
                  }, 200)">Start capture</button>'''
                async def route(route):
                    if route.request.url.endswith('/snapshot'):
                        await route.fulfill(status=200, content_type='application/json', body='{"snapshot":{"session":{"version":7}}}')
                    else:
                        await route.fulfill(status=200, content_type='text/html', body=html)
                await context.route('**/*', route)
                await page.goto('https://measurement.test/')
                class Probe(Harness):
                    def attach(self, page):
                        page = super().attach(page)
                        original_wait = page.wait_for_function
                        async def late_reader(*args, **kwargs):
                            await asyncio.sleep(.8)
                            return await original_wait(*args, **kwargs)
                        page.wait_for_function = late_reader
                        return page
                    async def api(self, path):
                        return {"body": {"events": []}}
                    async def setup_live(self):
                        pass
                    async def start_live(self, key):
                        await self.page.get_by_role('button', name='Start capture', exact=True).click()
                        await self.page.evaluate("fetch('/api/live/sessions/controlled-meeting/snapshot').then(r => r.json())")
                        return 'controlled-meeting'
                probe = Probe(SimpleNamespace(output=str(tmp_path), base="https://measurement.test/"))
                probe.page = page
                probe.context = context
                try:
                    result = await probe.bank()
                    assert result['ok'] and result['bank_contains_name']
                    assert .18 <= result['recognition_seconds'] < .5
                    assert result['measurement'] == 'Start click to visible name DOM mutation'
                    projection = json.loads((tmp_path/'row-10-timing.json').read_text())
                    assert projection['attribution'] == 'INCOMPLETE'
                    assert projection['browser']['elapsed_seconds'] is not None
                    assert projection['browser']['snapshot_version'] == 7
                finally:
                    await probe.page.close()
                    probe.network.close()
            finally:
                await browser.close()
    asyncio.run(run())


def test_enrolled_label_budget_derives_from_live_pipeline():
    # Preserve the 2.5s canonical cap; allow 1s processing and 0.5s frame/poll.
    assert FIRST_ENROLLED_LABEL_BOUND_SECONDS == 2.5 + 1.0 + .5
    assert 3.7007 <= FIRST_ENROLLED_LABEL_BOUND_SECONDS < 10.844687


def test_name_latency_timeout_writes_incomplete_projection(tmp_path):
    async def run():
        async with async_playwright() as p:
            browser = await p.chromium.launch(executable_path=str(require_browser(p)), headless=True)
            try:
                context = await browser.new_context()
                page = await context.new_page()
                html = '''<div data-auth-state="signed-in" data-boot="ready" data-history-boot="ready">Ready</div>
                  <section aria-label="Meeting history"><button role="tab">Voiceprints</button></section>
                  <section aria-label="Private voiceprints"><div data-voiceprint-id="saved">E2E Rowan</div></section>
                  <button>Start capture</button>'''
                async def route(route):
                    if route.request.url.endswith('/snapshot'):
                        await route.fulfill(status=200, content_type='application/json', body='{"snapshot":{"session":{"version":7}}}')
                    else:
                        await route.fulfill(status=200, content_type='text/html', body=html)
                await context.route('**/*', route)
                await page.goto('https://measurement.test/')
                class Probe(Harness):
                    def attach(self, page):
                        page = super().attach(page)
                        async def timeout(*args, **kwargs):
                            raise TimeoutError()
                        page.wait_for_function = timeout
                        return page
                    async def api(self, path):
                        return {'body': {'events': []}}
                    async def setup_live(self):
                        pass
                    async def start_live(self, key):
                        await self.page.get_by_role('button', name='Start capture', exact=True).click()
                        await self.page.evaluate("fetch('/api/live/sessions/controlled-meeting/snapshot').then(r => r.json())")
                        return 'controlled-meeting'
                probe = Probe(SimpleNamespace(output=str(tmp_path), base='https://measurement.test/'))
                probe.page = page
                probe.context = context
                try:
                    await probe.check(10, probe.bank)
                    row = probe.state['rows']['10']
                    assert row['status'] == 'FAIL'
                    assert 'exception' not in row
                    projection = json.loads((tmp_path/'row-10-timing.json').read_text())
                    assert projection['browser']['matched_ms'] is None
                    assert projection['attribution'] == 'INCOMPLETE'
                finally:
                    await probe.page.close()
                    probe.network.close()
            finally:
                await browser.close()
    asyncio.run(run())


def test_row10_timing_projection_is_content_free_and_marks_missing_stages():
    audit = json.loads((Path(__file__).parents[2]/'docs/audits/row10-recognition-events-20260912.json').read_text())
    timing = {'started': 0.0, 'matched': 10844.687167, 'meeting_id': 'row10-audit'}
    projection = project_row10_timing(audit, timing)
    assert projection['decode']['queue_wait_seconds'] == 0.000173667
    assert projection['decode']['processing_elapsed_seconds'] == 7.438577042
    assert projection['decode']['decode_elapsed_seconds'] == 7.068335624877363

    injected = copy.deepcopy(audit)
    for event in injected:
        event['payload'].update({'transcript': 'NEVER_RETAIN_TRANSCRIPT', 'name': 'NEVER_RETAIN_NAME',
                                 'headers': 'NEVER_RETAIN_HEADERS', 'body': 'NEVER_RETAIN_BODY'})
    assert 'NEVER_RETAIN' not in json.dumps(project_row10_timing(injected, timing))

    missing_queue = [event for event in audit if event['kind'] != 'canonical_queued']
    incomplete = project_row10_timing(missing_queue, timing)
    assert incomplete['canonical_queue']['seq'] is None
    assert incomplete['attribution'] == 'INCOMPLETE'
