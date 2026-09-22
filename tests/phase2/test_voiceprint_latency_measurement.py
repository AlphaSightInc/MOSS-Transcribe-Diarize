"""The E2E clock measures the visible name, not when the test runner wakes up."""
import asyncio
import copy
import functools
import http.server
import json
from pathlib import Path
import threading
from types import SimpleNamespace

from playwright.async_api import async_playwright

from tests.e2e.verify_workspace import (
    Harness,
    FIRST_ENROLLED_LABEL_BOUND_SECONDS,
    ROW10_MAX_ATTEMPTS,
    project_row10_timing,
    write,
)
from tests.phase2.browser_support import require_browser


def test_fresh_row10_context_reopens_workspace_with_media_source(tmp_path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path.startswith('/api/meetings/'):
                body = b'{"status":"completed"}'
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            return super().do_GET()

    async def run():
        source = Path(__file__).parents[2] / 'evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav'
        (tmp_path / 'index.html').write_text(
            '<div data-auth-state="signed-in" data-boot="ready" data-history-boot="ready">Ready</div>'
        )
        (tmp_path / 'source.html').write_text('<audio src="source.wav" controls autoplay loop></audio>')
        (tmp_path / 'source.wav').symlink_to(source)
        server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), functools.partial(Handler, directory=str(tmp_path))
        )
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{server.server_port}'
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                executable_path=str(require_browser(p)), headless=True,
                ignore_default_args=['--mute-audio'], args=['--autoplay-policy=no-user-gesture-required'],
            )
            probe = Harness(SimpleNamespace(output=str(tmp_path / 'output'), base=base))
            try:
                probe.browser = browser
                probe._browser_context_options = {'accept_downloads': True, 'viewport': {'width': 1440, 'height': 1100}}
                probe.context = await browser.new_context(**probe._browser_context_options)
                probe.media = base
                probe.page = probe.attach(await probe.context.new_page())
                await probe.open()
                probe.source = await probe.context.new_page()
                await probe.source.goto(base + '/source.html')
                await probe.source.locator('audio').evaluate('a=>a.play()')
                await probe._fresh_row10_context()
                assert probe.page.url.startswith(base)
                assert probe.source.url == base + '/source.html'
                assert await probe.api('/api/meetings/prior') == {'status': 200, 'body': {'status': 'completed'}}
            finally:
                await probe.context.close()
                probe.network.close()
                probe._private.cleanup()
                await browser.close()
                server.shutdown()
                server.server_close()
    asyncio.run(run())


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
                    result = await probe.bank_attempt(1)
                    assert result['ok'] and result['bank_contains_name']
                    assert .18 <= result['recognition_seconds'] < .5
                    assert result['measurement'] == 'Start click to visible name DOM mutation'
                    projection = json.loads((tmp_path/'row-10-timing-attempt-1.json').read_text())
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
    # Preserve the 2.5s canonical cap; allow measured pipeline work plus polling.
    assert FIRST_ENROLLED_LABEL_BOUND_SECONDS == 2.5 + 1.5 + .5
    assert 4.5 == FIRST_ENROLLED_LABEL_BOUND_SECONDS < 10.844687


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
                    await probe.check(10, lambda: probe.bank_attempt(1))
                    row = probe.state['rows']['10']
                    assert row['status'] == 'FAIL'
                    assert 'exception' not in row
                    projection = json.loads((tmp_path/'row-10-timing-attempt-1.json').read_text())
                    assert projection['browser']['matched_ms'] is None
                    assert projection['attribution'] == 'INCOMPLETE'
                finally:
                    await probe.page.close()
                    probe.network.close()
            finally:
                await browser.close()
    asyncio.run(run())


def test_row10_attempt_loop_stops_at_first_pass_and_retains_only_attempts_run(tmp_path):
    async def run():
        harness = Harness(SimpleNamespace(output=str(tmp_path), base='https://measurement.test/'))
        prepared = []
        attempts = [
            {'ok': False, 'bank_contains_name': True, 'recognition_seconds': 4.51,
             'timing_attribution': 'INCOMPLETE', 'meeting': 'row10-a'},
            {'ok': True, 'bank_contains_name': True, 'recognition_seconds': 4.5,
             'timing_attribution': 'COMPLETE', 'meeting': 'row10-b'},
            {'ok': False, 'bank_contains_name': True, 'recognition_seconds': 9.0,
             'timing_attribution': 'INCOMPLETE', 'meeting': 'row10-c'},
        ]

        async def fresh_context():
            prepared.append(len(prepared) + 1)

        async def bank_attempt(number):
            return attempts[number - 1]

        harness._fresh_row10_context = fresh_context
        harness.bank_attempt = bank_attempt
        try:
            result = await harness.bank()
            assert result['ok'] is True
            assert [attempt['attempt'] for attempt in result['attempts']] == [1, 2]
            assert prepared == [1, 2]
            write(tmp_path/'retained-first-pass.json', result)
            retained = json.loads((tmp_path/'retained-first-pass.json').read_text())
            assert [attempt['timing_attribution'] for attempt in retained['attempts']] == ['INCOMPLETE', 'COMPLETE']
        finally:
            harness.network.close()
            harness._private.cleanup()
    asyncio.run(run())


def test_row10_five_recognition_misses_are_best_effort_and_retained(tmp_path):
    async def run():
        harness = Harness(SimpleNamespace(output=str(tmp_path), base='https://measurement.test/'))

        async def fresh_context():
            pass

        async def bank_attempt(number):
            return {
                'ok': False,
                'bank_contains_name': True,
                'recognition_seconds': 4.5 + number / 10,
                'timing_attribution': 'INCOMPLETE',
                'meeting': f'row10-{number}',
            }

        async def snapshot(*_args):
            return None

        harness._fresh_row10_context = fresh_context
        harness.bank_attempt = bank_attempt
        harness.snapshot = snapshot
        try:
            await harness.check(10, harness.bank)
            row = harness.state['rows']['10']
            assert row['status'] == 'BEST_EFFORT_FAIL'
            assert row['reason_code'] == 'all_five_recognition_attempts_missed_bound'
            assert [item['recognition_seconds'] for item in row['attempts']] == [4.6, 4.7, 4.8, 4.9, 5.0]
            write(tmp_path/'retained.json', row)
            retained = json.loads((tmp_path/'retained.json').read_text())
            assert retained['status'] == 'BEST_EFFORT_FAIL'
            assert [set(item) & {'recognition_seconds', 'timing_attribution', 'meeting'} for item in retained['attempts']] == [
                {'recognition_seconds', 'timing_attribution', 'meeting'}
            ] * ROW10_MAX_ATTEMPTS
        finally:
            harness.network.close()
            harness._private.cleanup()
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
