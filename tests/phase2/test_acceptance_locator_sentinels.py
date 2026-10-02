from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright, expect

from moss_transcribe_diarize.app.phase2 import Meeting, _workspace_html
from moss_transcribe_diarize.phase2_acceptance_browser import _meeting_opener
from moss_transcribe_diarize.phase2_acceptance_external import FixedAccountCampaign, ExternalMeasurementError

ROOT = Path(__file__).resolve().parents[2]


def test_boot_removes_server_meeting_fallback_and_keeps_locator_unique():
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            meeting = Meeting('audit-meeting', 'file', 'Audit title', 'completed', 1,
                              transcript={'segments': [{'id': 'seg_0001', 'start': 0, 'end': 1,
                                                         'speaker': 'S01', 'text': 'Local passage'}]})
            html = _workspace_html(SimpleNamespace(display_name='Audit'), [meeting], live_enabled=True)
            page = browser.new_page()
            # Summaries need a Gemini key in browser settings (I-1, K9); seed one so Refresh is enabled.
            page.add_init_script("""localStorage.setItem('moss.settings.v2',
                JSON.stringify({summary: {vendor: 'gemini', apiKey: 'test-key'}}))""")
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path == '/api/meetings/audit-meeting':
                    r.fulfill(json=meeting.to_dict())
                else:
                    r.fulfill(json={'meetings': [meeting.to_dict()], 'voiceprints': [], 'summary': None})
            page.route('**/*', route)
            page.goto('http://audit.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            opener = _meeting_opener(page, meeting.meeting_id)
            assert page.get_by_text('Meeting history', exact=True).count() == 2
            assert page.locator('[data-open-meeting="audit-meeting"]').count() == 1
            assert opener.count() == 1
            summary_tab = page.get_by_role('tab', name='Summary', exact=True)
            expect(summary_tab).to_have_count(1)
            # Finish the initial read before publishing the newer summary event below.
            with page.expect_response(lambda response: urlsplit(response.url).path == '/api/meetings/audit-meeting/summary') as initial_summary:
                opener.click()
            initial_summary.value.finished()
            summary_tab.click()
            expect(page.get_by_label('Summary', exact=True)).to_be_visible()
            refresh = page.get_by_label('Summary', exact=True).get_by_role('button', name='Refresh')
            expect(refresh).to_have_count(1)
            expect(refresh).to_be_enabled()
            page.evaluate("""() => document.dispatchEvent(new CustomEvent('llm_status', {
                detail: {meeting_id: 'audit-meeting', artifact: {
                    state: 'current', attempt_id: 'summary-a', source_version: 1, artifact_version: 1,
                    error_code: null, document: {summary: 'Saved summary', topics: [], details: [],
                        speaker_background: [], data_references: []}
                }}
            }))""")
            expect(page.get_by_text('Saved summary')).to_be_visible()
            page.get_by_role('tab', name='Transcript', exact=True).click()
            expect(page.get_by_label('Summary', exact=True)).to_be_hidden()
            page.get_by_role('region', name='Meeting history', exact=True).get_by_role('tab', name='Voiceprints', exact=True).click()
            # Round 3: the meeting search and its Refresh belong to the Sessions tab only.
            assert page.get_by_role('button', name='Refresh', exact=True).count() == 1
            history = page.get_by_role('region', name='Meeting history', exact=True)
            history.get_by_role('tab', name='Sessions', exact=True).click()
            history.locator('.history-panel-actions').get_by_role('button', name='Refresh', exact=True).click()

            phone = browser.new_page(viewport={'width': 400, 'height': 900})
            phone.route('**/*', route)
            phone.goto('http://audit.test')
            phone.locator('[data-history-boot="ready"]').wait_for()
            _meeting_opener(phone, meeting.meeting_id).click()
            # The inline action lives in the gutter; it cannot narrow Q5 passage text.
            text_widths = phone.locator('.utt-content:has(.utt-reassign)').first.evaluate("""content => {
                const text = content.querySelector('.utt-text');
                const action = content.querySelector('.utt-reassign');
                const before = text.getBoundingClientRect().width;
                action.style.display = 'none';
                const after = text.getBoundingClientRect().width;
                action.style.display = '';
                return [before, after];
            }""")
            assert text_widths[0] == text_widths[1]
            phone.get_by_role('button', name='Reassign passage', exact=True).click()
            expect(phone.locator('#passage-speaker-title')).to_be_visible()
            assert phone.locator('#tr-body').evaluate('(el) => el.scrollWidth <= el.clientWidth')
            phone.get_by_role('dialog', name='Reassign passage').get_by_role('button', name='Cancel').click()
            phone.get_by_role('tab', name='Summary', exact=True).click()
            expect(phone.get_by_label('Summary', exact=True)).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            phone.get_by_role('tab', name='Transcript', exact=True).click()
            expect(phone.get_by_label('Summary', exact=True)).to_be_hidden()
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        finally:
            browser.close()


def test_summary_collector_waits_for_delayed_meeting_selection():
    first = Meeting('first-meeting', 'file', 'First meeting', 'completed', 1,
                    transcript={'segments': []})
    second = Meeting('second-meeting', 'file', 'Second meeting', 'completed', 1,
                     transcript={'segments': []})
    meetings = [first, second]
    html = _workspace_html(SimpleNamespace(display_name='Audit'), meetings, live_enabled=True)
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 720})
            page.set_default_timeout(3000)
            page.add_init_script("""(() => {
                const originalFetch = window.fetch;
                window.fetch = async (...args) => {
                    const url = typeof args[0] === 'string' ? args[0] : args[0].url;
                    if (new URL(url, location.href).pathname === '/api/meetings/second-meeting') {
                        await new Promise(resolve => setTimeout(resolve, 150));
                    }
                    return originalFetch(...args);
                };
            })()""")

            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path == '/api/meetings/second-meeting':
                    r.fulfill(json=second.to_dict())
                elif path == '/api/meetings/first-meeting':
                    r.fulfill(json=first.to_dict())
                else:
                    r.fulfill(json={'meetings': [m.to_dict() for m in meetings], 'voiceprints': [], 'summary': None})

            page.route('**/*', route)
            page.goto('http://audit.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            _meeting_opener(page, first.meeting_id).click()
            page.get_by_role('tab', name='Summary', exact=True).click()
            expect(page.get_by_text('First meeting', exact=True).first).to_be_visible()
            _meeting_opener(page, second.meeting_id).click()
            expect(page.get_by_label('Summary', exact=True)).to_be_visible()
            expect(page.get_by_text('Second meeting', exact=True).first).to_be_visible()
        finally:
            browser.close()


@pytest.mark.parametrize('width,height', [(1440, 900), (1280, 800), (400, 900)])
def test_summary_entry_does_not_cover_upload_or_navigation(width, height):
    meeting = Meeting('audit-meeting', 'file', 'Audit title', 'completed', 1,
                      transcript={'segments': []})
    html = _workspace_html(SimpleNamespace(display_name='Audit'), [meeting], live_enabled=True)
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={'width': width, 'height': height})

            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                else:
                    r.fulfill(json={'meetings': [meeting.to_dict()], 'voiceprints': [], 'summary': None})

            page.route('**/*', route)
            page.goto('http://audit.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            summary_tab = page.get_by_role('tab', name='Summary', exact=True)
            summary = summary_tab.bounding_box()
            assert summary is not None
            assert summary_tab.evaluate(
                '(el) => getComputedStyle(el).position') != 'fixed'

            def overlap(other):
                if other is None:
                    return 0
                return max(0, min(summary['x'] + summary['width'], other['x'] + other['width']) - max(summary['x'], other['x'])) * max(
                    0, min(summary['y'] + summary['height'], other['y'] + other['height']) - max(summary['y'], other['y']))

            page.get_by_role('button', name='File', exact=True).click()
            upload = page.get_by_role('button', name='Start file transcription').bounding_box()
            nav = page.get_by_role('navigation', name='Workspace').bounding_box()
            assert overlap(upload) == 0
            assert overlap(nav) == 0
        finally:
            browser.close()


@pytest.mark.parametrize('width,height', [(1280, 720), (1440, 900)])
def test_every_meeting_card_is_clickable_at_g9_viewport(width, height):
    meetings = [Meeting(f'card-{index}', 'file', f'Meeting {index}', 'completed',
                        1789700400000 - index * 60000, transcript={'segments': []})
                for index in range(6)]
    by_id = {meeting.meeting_id: meeting for meeting in meetings}
    html = _workspace_html(SimpleNamespace(display_name='Audit'), meetings, live_enabled=True)
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={'width': width, 'height': height})

            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = ROOT / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path.startswith('/api/meetings/') and path.split('/')[3] in by_id:
                    r.fulfill(json=by_id[path.split('/')[3]].to_dict())
                else:
                    r.fulfill(json={'meetings': [meeting.to_dict() for meeting in meetings],
                                    'voiceprints': [], 'summary': None})

            page.route('**/*', route)
            failed = []
            for meeting in meetings:
                page.goto('http://audit.test')
                page.locator('[data-history-boot="ready"]').wait_for()
                expect(page.locator('.account-history-panel [data-open-meeting]')).to_have_count(len(meetings))
                card = page.locator(f'.account-history-panel [data-open-meeting="{meeting.meeting_id}"]')
                try:
                    card.click(timeout=1500)
                    expect(card).to_have_attribute('aria-pressed', 'true', timeout=1500)
                except (PlaywrightTimeoutError, AssertionError):
                    failed.append(meeting.meeting_id)
            assert not failed, f'Cards blocked at {width}x{height}: {failed}'
        finally:
            browser.close()


@pytest.mark.parametrize('retains_title', [True, False])
def test_audio_sentinel_installs_title_and_checks_owner_readback(monkeypatch, tmp_path, retains_title):
    from moss_transcribe_diarize import phase2_acceptance_external as external
    campaign = FixedAccountCampaign(candidate_sha='a'*40, config={
        'repo_root': str(ROOT), 'campaign_work_dir': str(tmp_path)})
    state = {'id': 'audio-meeting', 'status': 'completed', 'title': None}
    calls = []
    class Client:
        def json(self, method, route, expected, **kwargs):
            calls.append((method, route))
            if method == 'PUT' and retains_title:
                state['title'] = kwargs['json']['title']
            return dict(state), None
        def request(self, method, route):
            assert state['title'] == 'account-audio-sentinel-a'
            return SimpleNamespace(status_code=200, content=b'mp3 evidence')
    client = Client()
    campaign._clients['a'] = client
    monkeypatch.setattr(external, '_wav_pcm_clip', lambda *args: b'\0\0'*160)
    monkeypatch.setattr(campaign, '_submit_file_for', lambda *args: 'audio-meeting')
    monkeypatch.setattr(campaign, '_await_meeting_terminal_for', lambda *args: dict(state))
    if retains_title:
        assert campaign._seed_audio_sentinel('a', 0)[0] == 'audio-meeting'
        assert calls == [('PUT', '/api/meetings/audio-meeting/title'), ('GET', '/api/meetings/audio-meeting')]
    else:
        with pytest.raises(ExternalMeasurementError, match='audio sentinel title is absent'):
            campaign._seed_audio_sentinel('a', 0)
