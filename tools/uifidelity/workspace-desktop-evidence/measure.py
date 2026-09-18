import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright
from moss_transcribe_diarize.app.phase2 import _workspace_html, Meeting
from tests.phase2.browser_support import require_browser

root = Path.cwd()
out = root / 'tools/uifidelity/workspace-desktop-evidence'
meeting = Meeting('layout-demo', 'file', 'Workspace layout review', 'completed', 1,
    transcript={'segments': [{'start': 0, 'end': 1, 'speaker': 'S01', 'text': 'Workspace layout review.'}]})
html = _workspace_html(SimpleNamespace(display_name='Layout review'), [meeting], live_enabled=True)
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path=str(require_browser(p)))
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    def route(r):
        path = urlsplit(r.request.url).path
        if path == '/':
            r.fulfill(body=html, content_type='text/html')
        elif path.startswith('/static/'):
            asset = root / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
            r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
        elif path == '/api/meetings/layout-demo':
            r.fulfill(json=meeting.to_dict())
        else:
            r.fulfill(json={'meetings': [meeting.to_dict()], 'voiceprints': [], 'summary': None})
    page.route('**/*', route)
    page.goto('http://workspace.test/')
    page.locator('[data-history-boot="ready"]').wait_for()
    page.evaluate('document.fonts.ready')
    result = page.evaluate('''() => ({
        viewport: [innerWidth, innerHeight],
        scrollHeight: document.documentElement.scrollHeight,
        bodyScrollHeight: document.body.scrollHeight,
        viewportMeta: document.querySelector('meta[name="viewport"]').content,
        panels: [...document.querySelectorAll('[data-workspace-section]')].map(el => ({
            section: el.dataset.workspaceSection, ...el.getBoundingClientRect().toJSON()
        })),
        history: document.querySelector('.account-history-panel').getBoundingClientRect().toJSON()
    })''')
    page.screenshot(path=str(out / 'workspace-1440x900.png'), full_page=True)
    (out / 'geometry.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    browser.close()
