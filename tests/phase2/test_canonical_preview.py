"""Runtime lock -> owner-bound HTTP -> real reader, with identity held after decode."""
import asyncio
import json
from pathlib import Path
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient
from tests.phase2 import test_owner_bound_live_meeting as fixture


def read_snapshots(snapshots):
    result = subprocess.run(
        ['node', str(Path(__file__).with_name('canonical_preview_reader.cjs'))],
        input=json.dumps(snapshots), text=True, capture_output=True, check=True,
    )
    decoded = json.loads(result.stdout)
    assert decoded['errors'] == []
    return decoded['rows']


@pytest.mark.parametrize('ending', ['commit', 'uncertain', 'abort', 'stop'])
def test_decoded_preview_visible_before_identity_and_retired(tmp_path, ending):
    entered, release = threading.Event(), threading.Event()
    decode_calls = []

    class CountedDecoder(fixture.Decoder):
        def transcribe_pcm(self, **kwargs):
            decode_calls.append(kwargs['span'].id)
            return super().transcribe_pcm(**kwargs)

    class HeldIdentity(fixture.Identity):
        def prepare(self, **kwargs):
            entered.set()
            assert release.wait(5), 'identity not released'
            result = super().prepare(**kwargs)
            if ending == 'uncertain':
                from moss_transcribe_diarize.app.live_identity import BoundedCausalIdentityPreparer, LiveIdentityConfig
                class Ambiguous:
                    def score(self, **kwargs):
                        raise ValueError('controlled unavailable identity evidence')
                result = BoundedCausalIdentityPreparer(
                    config=LiveIdentityConfig(16, .35, .1), evidence_provider=Ambiguous(),
                ).prepare(**kwargs)
            return result

    database = tmp_path / 'accounts.sqlite3'
    sessions = asyncio.run(fixture.provision(database))
    app = fixture.make_app(database, identity_factory=HeldIdentity, decoder_factory=CountedDecoder)
    with TestClient(app, base_url='https://moss.test') as client:
        fixture.session(client, sessions['a'])
        meeting = client.post('/api/live/sessions').json()['id']
        other = client.post('/api/live/sessions').json()['id']
        try:
            runtime = app.state.phase2_live.runtime
            live_session = runtime._sessions[meeting].session
            publish = live_session.publish_provisional
            def locked_publish(**kwargs):
                assert runtime._lock._is_owned()
                return publish(**kwargs)
            live_session.publish_provisional = locked_publish
            fixture.feed_two_lane_span(client, meeting)
            assert entered.wait(5)
            before = fixture.wait_snapshot(client, meeting,
                lambda row: row['snapshot']['session']['provisional'] is not None)
            live = before['snapshot']['session']
            assert live['committed_samples'] == 0
            assert live['identity_snapshot']['canonical_speakers'] == []
            assert '[S00]owner live words' in live['provisional']['transcript']
            assert client.get(f'/api/live/sessions/{other}/snapshot').json()['snapshot']['session']['provisional'] is None
            # Mutation is serialized with frame/abort/commit, not a decoder-owned write.
            runtime = app.state.phase2_live.runtime
            preview_events = [e for e in runtime.events(meeting) if e.kind == 'canonical_preview']
            assert len(preview_events) == 1
            assert len(decode_calls) == 1
            if ending == 'abort':
                assert client.post(f'/api/live/sessions/{meeting}/abort').status_code == 200
                release.set()
                after = fixture.wait_snapshot(client, meeting,
                    lambda row: row['snapshot']['session']['status'] == 'aborted')
            elif ending == 'stop':
                # Stop must reach its drain while identity remains held, then finish normally.
                original_wait = runtime._wait_for_drain
                async def release_at_drain(state, *, end_time):
                    release.set()
                    return await original_wait(state, end_time=end_time)
                runtime._wait_for_drain = release_at_drain
                assert client.post(f'/api/live/sessions/{meeting}/stop', json={'deadline': 2}).status_code == 200
                after = fixture.wait_snapshot(client, meeting,
                    lambda row: row['snapshot']['session']['status'] == 'closed')
            else:
                release.set()
                after = fixture.wait_snapshot(client, meeting,
                    lambda row: row['snapshot']['session']['committed_samples'] > 0)
            if ending == 'commit':
                assert_built_reader([before, after])
            rows = read_snapshots([before, after])
            assert len(rows[0]) == 1 and rows[0][0]['state'] == 'provisional'
            assert all(row['state'] != 'provisional' for row in rows[1])
            if ending == 'abort':
                assert rows[1] == []
                assert after['snapshot']['session']['committed_samples'] == 0
            else:
                assert len(rows[1]) == (2 if ending == 'stop' else 1)
                assert all(row['text'] == 'owner live words' for row in rows[1])
                if ending == 'uncertain':
                    assert '[S00]' in after['snapshot']['session']['committed'][0]['transcript']
            events = [e for e in runtime.events(meeting) if e.kind == 'canonical_preview']
            assert len(events) == (2 if ending == 'stop' else 1)
            assert len({e.payload['span_id'] for e in events}) == len(events)
            assert len(decode_calls) == len(events)
        finally:
            release.set()


def test_decode_finishing_after_abort_cannot_publish_preview(tmp_path):
    entered, release = threading.Event(), threading.Event()
    database = tmp_path / 'accounts.sqlite3'
    sessions = asyncio.run(fixture.provision(database))
    app = fixture.make_app(database, decoder_factory=lambda: fixture.HeldDecoder(entered, release))
    with TestClient(app, base_url='https://moss.test') as client:
        fixture.session(client, sessions['a'])
        meeting = client.post('/api/live/sessions').json()['id']
        try:
            fixture.feed_two_lane_span(client, meeting)
            assert entered.wait(5)
            assert client.post(f'/api/live/sessions/{meeting}/abort').status_code == 200
        finally:
            release.set()
        runtime = app.state.phase2_live.runtime
        # Wait for actual late preparation to return before asserting no publication.
        for _ in range(100):
            if meeting not in runtime._in_flight_session_ids:
                break
            threading.Event().wait(.01)
        assert meeting not in runtime._in_flight_session_ids
        snapshot = runtime.snapshot(meeting)
        assert snapshot.session.provisional is None
        assert snapshot.session.committed_samples == 0
        assert not any(e.kind == 'canonical_preview' for e in runtime.events(meeting))


def assert_built_reader(snapshots):
    from types import SimpleNamespace
    from urllib.parse import urlsplit
    from playwright.sync_api import sync_playwright, expect
    from moss_transcribe_diarize.app.phase2 import _workspace_html
    root = Path(__file__).resolve().parents[2]
    assets = root / 'moss_transcribe_diarize/app/frontend_assets'
    source_map = json.loads((assets / 'app.js.map').read_text())
    index = next(i for i, name in enumerate(source_map['sources']) if name.endswith('/api/mossPoller.ts'))
    assert source_map['sourcesContent'][index] == (root / 'frontend/src/api/mossPoller.ts').read_text()
    chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
    with sync_playwright() as p:
        browser = p.chromium.launch(**({'executable_path': str(chrome)} if chrome.exists() else {}))
        try:
            page = browser.new_page()
            current = 0
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=_workspace_html(SimpleNamespace(display_name='Preview test'), [], live_enabled=True), content_type='text/html')
                elif path.startswith('/static/'):
                    asset = assets / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path.endswith('/snapshot'):
                    r.fulfill(json=snapshots[current])
                else:
                    r.fulfill(json={'events': [], 'meetings': [], 'voiceprints': [], 'summary': None})
            page.route('**/*', route)
            page.goto('http://preview.test')
            page.locator('[data-observer-mode]').wait_for()
            page.evaluate("id => document.dispatchEvent(new CustomEvent('moss:observe-live-meeting', {detail: {meetingId: id}}))", snapshots[0]['snapshot']['session_id'])
            expect(page.locator('.utt[data-state="provisional"]')).to_have_count(1)
            expect(page.locator('.utt')).to_contain_text('owner live words')
            current = 1
            expect(page.locator('.utt[data-state="confirmed"]')).to_have_count(1)
            expect(page.locator('.utt[data-state="provisional"]')).to_have_count(0)
            expect(page.locator('.utt')).to_have_count(1)
        finally:
            browser.close()
