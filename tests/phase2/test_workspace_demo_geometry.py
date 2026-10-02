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
            page.get_by_role('button', name='YouTube', exact=True).click()
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


COLLAPSE_GEOMETRY = """() => {
    const box = s => { const r = document.querySelector(s).getBoundingClientRect();
        return {left: r.left, right: r.right, top: r.top, bottom: r.bottom, w: r.width, h: r.height,
                cx: r.left + r.width / 2, cy: r.top + r.height / 2}; };
    // Nothing (the transcript card, a neighbour) may paint over the control's centre.
    const uncovered = s => { const b = box(s); const hit = document.elementFromPoint(b.cx, b.cy);
        return !!hit && document.querySelector(s).contains(hit); };
    const shown = s => [...document.querySelectorAll(s)].filter(e => e.getClientRects().length > 0).length;
    return {viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        control: box('.control-panel'), transcript: box('.transcript-shell'), legend: box('#legend'),
        history: box('.account-history-panel'), status: box('.top-status'), gear: box('.settings-trigger'),
        statusUncovered: uncovered('.top-status'), gearUncovered: uncovered('.settings-trigger'),
        titleRows: document.querySelectorAll('.tr-head, .tr-title').length,
        toggles: shown('.collapse-btn'), historyTabs: shown('.history-tabs'),
        controlBody: shown('.control-panel .panel-body'), historyBody: shown('.account-history-panel .panel-body')};
}"""


def _open_workspace(p, viewport, init_script=None):
    from tests.phase2.browser_support import require_browser
    browser = p.chromium.launch(executable_path=str(require_browser(p)))
    page = browser.new_page(viewport=viewport)
    if init_script:
        page.add_init_script(init_script)
    html = _workspace_html(SimpleNamespace(display_name='Open workspace'), [], live_enabled=True)
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
    return browser, page


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 900}, {'width': 1280, 'height': 800}])
def test_side_panels_collapse_to_rails_and_are_remembered(viewport):
    """#8: each side panel folds into a 48 px rail and the transcript card takes the freed width; the status
    pill stays over Controls and Settings over History, uncovered, in every combination; the choice survives
    a reload. #9: the card has no title row -- it starts at the speaker legend."""
    settle = 400  # the rail transition is 0.28 s
    with sync_playwright() as p:
        browser, page = _open_workspace(p, viewport)
        try:
            states = {(False, False): page.evaluate(COLLAPSE_GEOMETRY)}
            for label, state in [('Collapse controls', (True, False)), ('Collapse history', (True, True)),
                                 ('Expand controls', (False, True))]:
                page.get_by_role('button', name=label, exact=True).click()
                page.wait_for_timeout(settle)
                states[state] = page.evaluate(COLLAPSE_GEOMETRY)
            page.reload()
            page.locator('[data-history-boot="ready"]').wait_for()
            page.wait_for_timeout(settle)
            reloaded = page.evaluate(COLLAPSE_GEOMETRY)
            page.locator('.account-history-panel .panel-title-rail').click()
            page.wait_for_timeout(settle)
            reopened = page.evaluate(COLLAPSE_GEOMETRY)
        finally:
            browser.close()
    expanded = states[(False, False)]
    side = expanded['control']['w']
    assert expanded['titleRows'] == 0 and abs(expanded['legend']['top'] - expanded['transcript']['top']) <= 1, expanded
    for (left, right), shell in states.items():
        assert shell['scrollWidth'] <= shell['viewport'], shell
        assert shell['statusUncovered'] and shell['gearUncovered'], shell
        assert abs(shell['control']['w'] - (48 if left else side)) <= 1, shell
        assert abs(shell['history']['w'] - (48 if right else side)) <= 1, shell
        assert abs(shell['transcript']['w'] - expanded['transcript']['w'] - (side - 48) * (left + right)) <= 1, shell
        assert shell['control']['left'] - 1 <= shell['status']['left'] and shell['status']['right'] <= shell['control']['right'] + 1, shell
        assert shell['history']['left'] - 1 <= shell['gear']['left'] and shell['gear']['right'] <= shell['history']['right'] + 1, shell
        assert shell['gear']['bottom'] <= shell['history']['top'] and abs(shell['history']['top'] - shell['control']['top']) <= 1, shell
        assert shell['controlBody'] == (0 if left else 1) and shell['historyBody'] == (0 if right else 1), shell
    for key in ('control', 'transcript', 'history'):
        assert abs(reloaded[key]['w'] - states[(False, True)][key]['w']) <= 1, (reloaded, states[(False, True)])
        assert abs(reopened[key]['w'] - expanded[key]['w']) <= 1, (reopened, expanded)


def test_phone_layout_ignores_a_remembered_collapse():
    """#8 is desktop only: stacked panels stay open with no toggles, even when this browser remembers both
    panels collapsed."""
    remembered = ("localStorage.setItem('lt:ui:controlPanelCollapsed', 'true');"
                  "localStorage.setItem('lt:ui:historyPanelCollapsed', 'true');")
    with sync_playwright() as p:
        browser, page = _open_workspace(p, {'width': 400, 'height': 860}, remembered)
        try:
            shell = page.evaluate(COLLAPSE_GEOMETRY)
            collapsed = page.locator('.control-panel.collapsed, .account-history-panel.collapsed').count()
        finally:
            browser.close()
    assert collapsed == 2  # the remembered state applies; the stacked layout neutralises it
    assert shell['scrollWidth'] <= shell['viewport'], shell
    assert shell['toggles'] == 0 and shell['titleRows'] == 0, shell
    assert shell['controlBody'] == 1 and shell['historyBody'] == 1 and shell['historyTabs'] == 1, shell
    for key in ('control', 'transcript', 'history'):
        assert shell[key]['left'] >= 16 and shell[key]['right'] <= 400 - 16, shell
        assert shell[key]['w'] >= 400 - 32 - 1, shell


SOURCE_ROWS = """() => {
    const lines = e => { const range = document.createRange(); range.selectNodeContents(e);
        return new Set([...range.getClientRects()].map(r => Math.round(r.top))).size; };
    const panel = document.querySelector('.control-panel').getBoundingClientRect();
    return {viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth,
        rows: [...document.querySelectorAll('.capture-sources .source-row')].map(row => {
            const cell = row.querySelector('.check-row').getBoundingClientRect();
            const text = row.querySelector('.check-row span'), name = text.getBoundingClientRect();
            return {label: text.textContent, lines: lines(text), box: row.querySelector('input').getBoundingClientRect().width,
                    left: cell.left, cell: cell.right, name: name.right, row: row.getBoundingClientRect().right,
                    panelLeft: panel.left, panelRight: panel.right};
        })};
}"""


@pytest.mark.parametrize('viewport', [{'width': 1440, 'height': 900}, {'width': 400, 'height': 800}])
def test_source_names_keep_one_line_and_their_own_column(viewport):
    """Round 5: the system source reads "System Sound Output". On desktop and on a 400 px phone each name
    keeps one line and a full-size box inside the label column, leaving the level meter's column free,
    and the page does not scroll sideways."""
    with sync_playwright() as p:
        browser, page = _open_workspace(p, viewport)
        try:
            page.locator('.capture-sources').scroll_into_view_if_needed()
            sources = page.evaluate(SOURCE_ROWS)
            for box in page.locator('.capture-sources input[type=checkbox]').all():
                box.uncheck()
            tooltip = page.locator('.record-btn[data-action="start"]').get_attribute('title')
        finally:
            browser.close()
    assert sources['scrollWidth'] <= viewport['width'], sources
    assert [row['label'] for row in sources['rows']] == ['System Sound Output', 'Microphone']
    for row in sources['rows']:
        assert row['lines'] == 1 and row['box'] == 16, sources
        assert row['name'] <= row['cell'] <= row['row'] - 60, sources  # the meter keeps at least 60 px
        assert row['panelLeft'] <= row['left'] and row['row'] <= row['panelRight'], sources
    assert tooltip == 'Tick System Sound Output or Microphone.'
