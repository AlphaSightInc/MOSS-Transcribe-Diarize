"""Header and pane geometry remain equal to 887e76a0, using both built bundles."""
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
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport=viewport)
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/': r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path == '/api/meetings/demo-file': r.fulfill(json=meeting.to_dict())
                else: r.fulfill(json={'meetings': [meeting.to_dict()], 'voiceprints': [], 'summary': None})
            page.route('**/*', route)
            page.goto('http://demo.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            expect(page.locator('.topbar .session-title')).to_have_text('aiSight - LiveTranscribe')
            page.get_by_role('region', name='Meeting history', exact=True).locator('[data-open-meeting="demo-file"]').click()
            expect(page.locator('#tr-body')).to_contain_text('Demo words')
            expect(page.locator('.topbar .session-title')).to_have_text(meeting.title)
            expect(page.locator('.topbar .session-chip')).to_have_text('File / URL')
            assert page.locator('#transcript-panel').bounding_box()['y'] < viewport['height']
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            # Measure the app in a fixed viewport, independent of the account shell.
            page.evaluate("""() => {
                const app = document.querySelector('#app > .app');
                document.body.replaceChildren(app); document.body.className = '';
                Object.assign(app.style, {position:'fixed', inset:'0', width:'100vw', height:'100vh'});
            }""")
            page.evaluate('document.fonts.ready')
            header, transcript = page.evaluate("""() => ['.topbar', '#transcript-panel'].map(selector => {
                const r = document.querySelector(selector).getBoundingClientRect();
                return {width:r.width, height:r.height};
            })""")
        finally: browser.close()
    assert 0 < header['width'] <= viewport['width']
    assert 40 <= header['height'] <= 120
    assert 0 < transcript['width'] <= viewport['width']
    assert transcript['height'] >= 240


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 900}, {'width': 1280, 'height': 800}])
def test_voiceprint_tab_does_not_disturb_desktop_workspace(viewport):
    html = _workspace_html(SimpleNamespace(display_name='Demo'), [], live_enabled=True)
    voiceprints = [
        {'id': f'voiceprint-{index}', 'label': f'Speaker {index}', 'sample_count': index + 1,
         'compatibility': 'compatible'}
        for index in range(10)
    ]
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport=viewport)
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/': r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path == '/api/voiceprints': r.fulfill(json={'voiceprints': voiceprints})
                else: r.fulfill(json={'meetings': [], 'voiceprints': voiceprints, 'summary': None})
            page.route('**/*', route)
            page.goto('http://demo.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            history = page.get_by_role('region', name='Meeting history', exact=True)
            page.get_by_role('button', name='URL', exact=True).click()
            sessions = page.evaluate("""() => {
                const box = selector => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {top: rect.top, height: rect.height};
                };
                return {control: box('.control-panel'), transcript: box('.transcript-shell')};
            }""")
            history.get_by_role('tab', name='Voiceprints', exact=True).click()
            expect(page.locator('.voiceprint-list li')).to_have_count(10)
            voiceprints_view = page.evaluate("""() => {
                const box = selector => {
                    const rect = document.querySelector(selector).getBoundingClientRect();
                    return {top: rect.top, height: rect.height};
                };
                const voiceprints = document.querySelector('[data-workspace-section="voiceprints"]');
                const history = document.querySelector('.history-panel');
                const captionElement = document.querySelector('label[for="meeting-url"]');
                const caption = captionElement.getBoundingClientRect();
                const captionStyle = getComputedStyle(captionElement);
                return {
                    viewportHeight: innerHeight,
                    documentHeight: document.documentElement.scrollHeight,
                    control: box('.control-panel'),
                    transcript: box('.transcript-shell'),
                    history: box('.history-panel'),
                    voiceprintsInsideHistory: history.contains(voiceprints),
                    caption: {width: caption.width, height: caption.height,
                              display: captionStyle.display, visibility: captionStyle.visibility},
                };
            }""")
            history.get_by_role('tab', name='Sessions', exact=True).click()
            refresh = history.get_by_role('button', name='Refresh', exact=True)
            with page.expect_response(lambda response: urlsplit(response.url).path == '/api/meetings'):
                refresh.click()
            history.get_by_role('tab', name='Voiceprints', exact=True).click()
            expect(page.locator('.voiceprint-list li')).to_have_count(10)
        finally:
            browser.close()
    assert voiceprints_view['documentHeight'] <= voiceprints_view['viewportHeight']
    assert voiceprints_view['voiceprintsInsideHistory'] is True
    for panel in ('control', 'transcript'):
        for dimension in ('top', 'height'):
            assert abs(sessions[panel][dimension] - voiceprints_view[panel][dimension]) <= 2
    for panel in ('control', 'transcript', 'history'):
        assert voiceprints_view[panel]['height'] >= 240
        assert voiceprints_view[panel]['top'] < voiceprints_view['viewportHeight']
    assert voiceprints_view['caption']['width'] > 1
    assert voiceprints_view['caption']['height'] > 1
    assert voiceprints_view['caption']['display'] != 'none'
    assert voiceprints_view['caption']['visibility'] == 'visible'


SHELL_GEOMETRY = """() => {
    const box = e => { const r = e.getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, cy: r.top + r.height / 2, w: r.width, h: r.height}; };
    const shown = e => { const r = e.getBoundingClientRect(); return r.width > 2 && r.height > 2; };
    const q = s => box(document.querySelector(s));
    return {
        viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        chrome: [...document.querySelectorAll('main[data-auth-state] > header, [data-workspace="account"] > h1, .phase2-workspace-heading')]
            .filter(shown).map(e => e.textContent.trim()),
        // A visually hidden container clips its children, so visibility is judged on the container.
        links: shown(document.querySelector('.workspace-nav'))
            ? [...document.querySelectorAll('.workspace-nav a')].map(e => ({text: e.textContent.trim(), ...box(e)})) : [],
        cards: ['.top-status', '.settings-trigger', '.control-panel', '.transcript-shell', '.account-history-panel'].map(q),
        status: q('.top-status'), gear: q('.settings-trigger'), transcript: q('.transcript-shell'),
        control: q('.control-panel'), history: q('.account-history-panel'),
    };
}"""

SETTINGS_GEOMETRY = """() => {
    const box = e => { const r = e.getBoundingClientRect(); return {top: r.top, h: r.height, cy: r.top + r.height / 2}; };
    const select = document.querySelector('.settings-modal select');
    const text = document.querySelector('.settings-modal input[type="text"]');
    const rolling = document.querySelector('input[aria-label="Rolling summary"]');
    const wait = document.querySelector('input[aria-label="Wait after each summary (s)"]');
    return {appearance: getComputedStyle(select).appearance, chevron: getComputedStyle(select).backgroundImage,
        select: box(select), text: box(text), rolling: box(rolling), wait: box(wait),
        rollingLabel: box(rolling.closest('label').querySelector('.field-label')),
        waitLabel: box(wait.closest('label').querySelector('.field-label'))};
}"""


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 900}, {'width': 1280, 'height': 800},
                                      {'width': 400, 'height': 860}])
def test_shell_chrome_settings_placement_and_settings_fields(viewport):
    """P4: no account name / page title / section headings; phone jump links and cards keep a 16 px gutter.
    P6: desktop Settings sits in the top bar above History, level with the status pill, off the transcript card.
    P7/P8: Settings selects use the app chevron; Rolling summary lines up with Wait after each summary."""
    html = _workspace_html(SimpleNamespace(display_name='Open workspace'), [], live_enabled=True)
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport=viewport)
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/': r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                else: r.fulfill(json={'meetings': [], 'voiceprints': [], 'summary': None})
            page.route('**/*', route)
            page.goto('http://demo.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            page.evaluate('document.fonts.ready')
            shell = page.evaluate(SHELL_GEOMETRY)
            page.get_by_role('button', name='Settings', exact=True).click()
            page.get_by_role('dialog').get_by_role('tab', name='Summary', exact=True).click()
            fields = page.evaluate(SETTINGS_GEOMETRY)
        finally:
            browser.close()
    width = viewport['width']
    assert shell['scrollWidth'] <= width
    assert shell['chrome'] == []
    if width <= 768:
        assert [link['text'] for link in shell['links']] == ['Live', 'Meeting history']
        for item in shell['links'] + shell['cards']:
            assert item['left'] >= 16 and item['right'] <= width - 16, (item, shell)
    else:
        assert shell['links'] == []
        gear, status, transcript, history = shell['gear'], shell['status'], shell['transcript'], shell['history']
        assert gear['left'] >= transcript['right'] or gear['bottom'] <= transcript['top'], shell
        assert history['left'] <= gear['left'] and gear['right'] <= history['right'] + 1, shell
        assert gear['bottom'] <= history['top'], shell
        assert abs(gear['cy'] - status['cy']) <= 1, shell
        assert abs(history['top'] - shell['control']['top']) <= 1, shell
    assert fields['appearance'] == 'none' and 'linear-gradient' in fields['chevron'], fields
    assert abs(fields['select']['h'] - fields['text']['h']) <= 1, fields
    if width > 1024:  # two columns: the checkbox field shares a row with Wait after each summary
        assert abs(fields['rollingLabel']['top'] - fields['waitLabel']['top']) <= 1, fields
        assert abs(fields['rolling']['cy'] - fields['wait']['cy']) <= 1, fields
