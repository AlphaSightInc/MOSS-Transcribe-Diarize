"""Optional built-bundle assertions; required API tests run without a browser."""
from pathlib import Path
from types import SimpleNamespace
from moss_transcribe_diarize.app.phase2 import _workspace_html


def execute_submission_script(workspace_html: str) -> dict[str, object]:
    """Exercise the shipped bundle after moving submission out of inline HTML."""
    from urllib.parse import urlsplit
    from playwright.sync_api import sync_playwright, expect
    root = Path(__file__).resolve().parents[2]
    calls = []
    with sync_playwright() as p:
        from tests.phase2.browser_support import require_browser
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page()
            page.add_init_script("window.created=[]; document.addEventListener('moss:meeting-created', e=>window.created.push(e.detail.meeting_id));")
            # K9: File/URL Start needs a Gemini key in the I-1 browser settings (plan-r3-ui I-1).
            page.add_init_script("localStorage.setItem('moss.settings.v2', JSON.stringify({transcription: {vendor: 'gemini', apiKey: 'test-key'}}));")
            def route(r):
                path = urlsplit(r.request.url).path
                if path == '/':
                    r.fulfill(body=workspace_html, content_type='text/html')
                elif path.startswith('/static/'):
                    asset = root / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
                    r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
                elif path == '/api/meetings/file/admission':
                    r.fulfill(status=204)
                elif r.request.method == 'POST' and path in ('/api/meetings/file', '/api/meetings/url'):
                    calls.append(path)
                    if len(calls) == 2: r.abort()
                    elif len(calls) == 3: r.fulfill(status=400, json={'detail': 'Unsupported media URL'})
                    else: r.fulfill(json={'id': f'accepted-{len(calls)}'})
                elif path.startswith('/api/meetings/'):
                    r.fulfill(json={'id': path.rsplit('/', 1)[-1], 'mode': 'file', 'title': 'Import',
                        'title_source': 'automatic', 'status': 'completed', 'created_at_ms': 1,
                        'transcript_version': 0, 'transcript': None, 'audio': None})
                else: r.fulfill(json={'meetings': [], 'voiceprints': []})
            page.route('**/*', route)
            page.goto('http://upload.test')
            page.locator('[data-history-boot="ready"]').wait_for()
            page.get_by_role('button', name='File', exact=True).click()
            page.locator('input[name="file"]').set_input_files([
                {'name': 'one.wav', 'mimeType': 'audio/wav', 'buffer': b'one'},
                {'name': 'two.wav', 'mimeType': 'audio/wav', 'buffer': b'two'},
            ])
            page.get_by_role('button', name='Start file transcription', exact=True).click()
            results = page.locator('[data-file-upload="results"]')
            expect(results.locator('li')).to_have_count(2)
            # Q6: rows keep only a failure with its reason and the "Open meeting" action.
            expect(results.get_by_role('button', name='Open meeting for one.wav')).to_have_count(1)
            expect(results.locator('li').nth(1)).to_contain_text('Not confirmed — check History before retrying.')
            file_status = page.locator('[data-file-upload="status"]').inner_text()
            page.get_by_role('button', name='URL', exact=True).click()
            url = page.locator('input[name="urls"]')
            url.fill('https://media.test/http-failure')
            page.get_by_role('button', name='Start URL transcription', exact=True).click()
            expect(page.locator('[data-file-upload="results"]')).to_contain_text('Not accepted: Unsupported media URL')
            url.fill('https://media.test/good')
            page.get_by_role('button', name='Start URL transcription', exact=True).click()
            expect(page.get_by_role('button', name='Open meeting for https://media.test/good')).to_have_count(1)
            expect(page.locator('[data-file-upload="results"]')).not_to_contain_text('Not accepted')
            return {'calls': calls, 'created': page.evaluate('window.created'),
                    'file_status': file_status,
                    'url_status': page.locator('[data-file-upload="status"]').inner_text()}
        finally:
            browser.close()


def test_mixed_file_url_form_reports_each_result_and_created_event():
    workspace = _workspace_html(SimpleNamespace(display_name='Upload test'), [], live_enabled=True)
    assert execute_submission_script(workspace) == {
        "calls": [
            "/api/meetings/file",
            "/api/meetings/file",
            "/api/meetings/url",
            "/api/meetings/url",
        ],
        "file_status": "",
        "url_status": "",
        "created": ["accepted-1", "accepted-4"],
    }


def test_file_and_url_start_is_separated_from_mode_like_live():
    """#12: the File/URL form wraps its sections, so Start lost the Mode divider Live has."""
    from urllib.parse import urlsplit
    from playwright.sync_api import sync_playwright
    from tests.phase2.browser_support import require_browser
    root = Path(__file__).resolve().parents[2]
    workspace = _workspace_html(SimpleNamespace(display_name='Layout test'), [], live_enabled=True)

    def route(r):
        path = urlsplit(r.request.url).path
        asset = root / 'moss_transcribe_diarize/app/frontend_assets' / path.removeprefix('/static/')
        if path == '/':
            r.fulfill(body=workspace, content_type='text/html')
        elif path.startswith('/static/'):
            r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
        else:
            r.fulfill(json={'meetings': [], 'voiceprints': []})

    gaps = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            for width in (1440, 400):
                page = browser.new_page(viewport={'width': width, 'height': 900})
                page.route('**/*', route)
                page.goto('http://layout.test')
                page.locator('[data-history-boot="ready"]').wait_for()
                for mode in ('Live', 'File', 'URL'):
                    page.get_by_role('button', name=mode, exact=True).click()
                    gaps[(width, mode)] = page.evaluate(
                        "() => document.querySelector('.record-btn').getBoundingClientRect().top"
                        " - document.querySelector('.mode-tabs').getBoundingClientRect().bottom")
                page.close()
        finally:
            browser.close()
    for width in (1440, 400):
        assert gaps[(width, 'Live')] >= 48, gaps
        assert gaps[(width, 'File')] == gaps[(width, 'URL')] == gaps[(width, 'Live')], gaps
