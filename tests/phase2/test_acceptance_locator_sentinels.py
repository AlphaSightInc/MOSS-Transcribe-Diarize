from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import sync_playwright, expect

from moss_transcribe_diarize.app.phase2 import Meeting, _workspace_html
from moss_transcribe_diarize.phase2_acceptance_browser import _meeting_opener
from moss_transcribe_diarize.phase2_acceptance_summary import _summary_action, open_completed_summary
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
            assert page.get_by_role('region', name='Final summary', exact=True).count() == 0
            open_completed_summary(page, meeting.meeting_id)
            expect(page.get_by_role('main', name='Summary view')).to_have_count(1)
            expect(page.get_by_role('button', name='Back to meeting')).to_have_count(1)
            # Use the acceptance predicate's actual selector against the built UI.
            action = _summary_action(page)
            expect(action).to_have_count(1)
            expect(action).to_have_text('Generate summary')
            expect(action).to_be_enabled()
            for state, label in [('failed', 'Retry summary'), ('current', 'Regenerate summary'),
                                 ('cancelled', 'Retry summary')]:
                page.evaluate("""state => document.dispatchEvent(new CustomEvent('llm_status', {
                    detail: {meeting_id: 'audit-meeting', artifact: {
                        state, attempt_id: 'summary-a', source_version: 1, artifact_version: 1,
                        error_code: null, document: state === 'current' ? {
                            summary: 'Saved summary', topics: [], details: [],
                            speaker_background: [], data_references: []
                        } : null
                    }}
                }))""", state)
                expect(action).to_have_count(1)
                expect(action).to_have_text(label)
                expect(action).to_be_enabled()
            # Wording is not part of the predicate contract.
            action.evaluate("button => button.textContent = 'Different wording'")
            expect(_summary_action(page)).to_have_count(1)

            # G9 changes meetings while this page is open; its helper must return first.
            open_completed_summary(page, meeting.meeting_id)
            expect(page.get_by_role('main', name='Summary view')).to_have_count(1)
            page.get_by_role('button', name='Back to meeting').click()
            page.get_by_role('region', name='Meeting history', exact=True).get_by_role('tab', name='Voiceprints', exact=True).click()
            assert page.get_by_role('button', name='Refresh', exact=True).count() == 2
            history = page.get_by_role('region', name='Meeting history', exact=True)
            history.locator('.history-panel-actions').get_by_role('button', name='Refresh', exact=True).click()

            phone = browser.new_page(viewport={'width': 400, 'height': 900})
            phone.route('**/*', route)
            phone.goto('http://audit.test')
            phone.locator('[data-history-boot="ready"]').wait_for()
            _meeting_opener(phone, meeting.meeting_id).click()
            phone.get_by_role('button', name='Reassign passage', exact=True).click()
            expect(phone.locator('#passage-speaker-title')).to_be_visible()
            phone.get_by_role('dialog', name='Reassign passage').get_by_role('button', name='Cancel').click()
            phone.get_by_role('button', name='Open summary', exact=True).click()
            expect(phone.get_by_role('main', name='Summary view')).to_be_visible()
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            phone.get_by_role('button', name='Back to meeting').click()
            expect(phone.get_by_role('main', name='Summary view')).to_have_count(0)
            assert phone.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
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
