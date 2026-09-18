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
            page.locator('input[name="file"]').set_input_files([
                {'name': 'one.wav', 'mimeType': 'audio/wav', 'buffer': b'one'},
                {'name': 'two.wav', 'mimeType': 'audio/wav', 'buffer': b'two'},
            ])
            page.locator('textarea[name="urls"]').fill('https://media.test/http-failure\nhttps://media.test/good')
            page.get_by_role('button', name='Transcribe files and URLs', exact=True).click()
            expect(page.locator('[data-file-upload="status"]')).to_contain_text('2 accepted; 2 need attention.')
            expect(page.locator('[data-file-upload="results"] li')).to_have_count(4)
            expect(page.locator('[data-file-upload="results"]')).to_contain_text('Unsupported media URL')
            expect(page.locator('[data-file-upload="results"]')).to_contain_text('history before retrying')
            return {'calls': calls, 'created': page.evaluate('window.created'),
                    'status': page.locator('[data-file-upload="status"]').inner_text()}
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
        "status": "2 accepted; 2 need attention. Accepted work continues on the server.",
        "created": ["accepted-1", "accepted-4"],
    }
