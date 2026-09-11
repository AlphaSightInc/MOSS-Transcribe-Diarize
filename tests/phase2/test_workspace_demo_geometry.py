"""Header and pane geometry remain equal to 887e76a0, using both built bundles."""
import subprocess
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright, expect
from moss_transcribe_diarize.app.phase2 import _workspace_html, Meeting

ROOT = Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('viewport', [{'width': 1280, 'height': 800}, {'width': 390, 'height': 844}])
def test_header_and_pane_dimensions_survive_demo_changes(viewport):
    meeting = Meeting('demo-file', 'file', 'A long customer meeting title ' * 12, 'completed', 1,
                      transcript={'segments': [{'start': 0, 'end': 1, 'speaker': 'S01', 'text': 'Demo words'}]})
    html = _workspace_html(SimpleNamespace(display_name='Demo'), [meeting], live_enabled=True)
    dimensions = []
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            for baseline in (True, False):
                page = browser.new_page(viewport=viewport)
                def route(r):
                    path = urlsplit(r.request.url).path
                    if path == '/': r.fulfill(body=html, content_type='text/html')
                    elif path.startswith('/static/'):
                        relative = 'moss_transcribe_diarize/app/frontend_assets/' + path.removeprefix('/static/')
                        asset = ROOT / relative
                        if not asset.is_file(): r.fulfill(status=404)
                        elif baseline and path in ('/static/app.js', '/static/styles.css'):
                            r.fulfill(body=subprocess.check_output(['git', 'show', f'887e76a0:{relative}'], cwd=ROOT),
                                      content_type='text/javascript' if path.endswith('.js') else 'text/css')
                        else: r.fulfill(path=str(asset))
                    elif path == '/api/meetings/demo-file': r.fulfill(json=meeting.to_dict())
                    else: r.fulfill(json={'meetings': [meeting.to_dict()], 'voiceprints': [], 'summary': None})
                page.route('**/*', route)
                page.goto('http://demo.test')
                page.locator('[data-history-boot="ready"]').wait_for()
                if not baseline:
                    expect(page.locator('.topbar .session-title')).to_have_text('MOSS')
                page.get_by_role('region', name='Meeting history', exact=True).locator('[data-open-meeting="demo-file"]').click()
                expect(page.locator('#tr-body')).to_contain_text('Demo words')
                if not baseline:
                    expect(page.locator('.topbar .session-title')).to_have_text(meeting.title)
                    expect(page.locator('.topbar .session-chip')).to_have_text('File / URL')
                    assert page.locator('#transcript-panel').bounding_box()['y'] < viewport['height']
                # Same extraction used by fidelity: outer shell removed, fixed application viewport.
                page.evaluate("""() => {
                    const app = document.querySelector('#app > .app');
                    document.body.replaceChildren(app); document.body.className = '';
                    Object.assign(app.style, {position:'fixed', inset:'0', width:'100vw', height:'100vh'});
                }""")
                page.evaluate('document.fonts.ready')
                dimensions.append(page.evaluate("""() => ['.topbar', '#transcript-panel'].map(selector => {
                    const r = document.querySelector(selector).getBoundingClientRect();
                    return {width:r.width, height:r.height};
                })"""))
                page.close()
        finally: browser.close()
    assert dimensions[0] == dimensions[1]
