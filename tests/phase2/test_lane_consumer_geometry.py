"""Actual built transcript pane, corpus overlap, mobile and desktop widths."""
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import sync_playwright, expect
from moss_transcribe_diarize.app.phase2 import _workspace_html
from tests.phase2.browser_support import require_browser

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads((ROOT/'evidence/mvpfix/wp2/fixtures.json').read_text())['overlap']

@pytest.mark.parametrize('width', [390, 400, 1280])
def test_overlap_lane_badges_keep_chronology_and_fit_pane(width, tmp_path):
    meeting = dict(id='lanes', mode='live', title='Overlapping corpus', title_source='manual',
                   status='completed', created_at_ms=1, transcript=FIXTURE, transcript_version=1, audio=None)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={'width': width, 'height': 844})
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=_workspace_html(SimpleNamespace(display_name='Lane check'), [], live_enabled=True), content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT/'moss_transcribe_diarize/app/frontend_assets'/path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path == '/api/meetings/lanes': r.fulfill(json=meeting)
                else: r.fulfill(json={'meetings': [meeting], 'voiceprints': [], 'summary': None})
            page.route('**/*', route)
            page.goto('http://lane.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            page.get_by_role('region', name='Meeting history', exact=True).locator('[data-open-meeting="lanes"]').click()
            expect(page.locator('#tr-body .utt')).to_have_count(9)
            assert page.locator('#tr-body .utt').evaluate_all('(rows)=>rows.map(r=>r.dataset.sourceLane)') == [s['source_lane'] for s in FIXTURE['segments']]
            assert page.locator('#tr-body .utt-lane').all_text_contents() == ['System' if s['source_lane']=='system' else 'Microphone' for s in FIXTURE['segments']]
            expect(page.locator('.legend-chip')).to_have_count(4)
            page.get_by_role('region', name='Meeting history', exact=True).get_by_role('tab', name='Voiceprints', exact=True).click()
            expect(page.get_by_role('button', name='Refresh', exact=True)).to_have_count(2)
            assert page.locator('#tr-body').evaluate('(e)=>e.scrollWidth<=e.clientWidth')
            for text in (s['text'] for s in FIXTURE['segments']): expect(page.locator('#tr-body')).to_contain_text(text)
            page.locator('#transcript-panel').scroll_into_view_if_needed()
            page.screenshot(path=str(tmp_path / f'production-{width}.png'))
        finally: browser.close()
