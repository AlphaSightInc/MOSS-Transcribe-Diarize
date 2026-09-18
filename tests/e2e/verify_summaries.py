"""Final Summary through the real browser worker, per provider and transcript length.

verify_workspace.py row 9 summarizes only a 50 s clip. That is how a timestamp defect that
failed every realistic-length meeting went unnoticed: models turned float seconds into
invalid HH:MM:SS values (59.64 s -> "00:59:64") and the app rejected the summary. This test
drives the app's own settings UI and summary worker on a 50 s and a 180 s transcript, so
validation is exactly the app's.

Run: .venv/bin/python tests/e2e/verify_summaries.py
  MOSS_BASE              default https://127.0.0.1:17861 (self-signed TLS accepted only on loopback)
  MOSS_RELAY_MODEL       default qwen/qwen3.6-35b-a3b; skipped if the relay does not list it
  OPENROUTER_API_KEY     enables the external provider; never printed or retained
  MOSS_SUMMARY_ENDPOINT  default https://openrouter.ai/api/v1
  MOSS_SUMMARY_MODEL     default google/gemini-2.5-flash-lite
  TRIALS                 default 1
  MOSS_SUMMARY_PROVIDERS default relay,external; use external to check only the demo provider
Exit 0 = every attempted summary became current; 1 = one did not; 77 = nothing could be attempted.
The browser profile is ephemeral, so a supplied key does not outlive the run.

Known limitation, measured 2026-09-15 on 566024287cdd: the macstudio relay model
(qwen/qwen3.6-35b-a3b) still fails about a third of 180 s summaries (5 of 16) through its own
format compliance - it abbreviates timestamps to MM:SS ("01:32"), or writes 59 s as "00:59:00".
Gemini 2.5 Flash via OpenRouter, the demo provider, was current in 13 of 13 runs on 180 s
transcripts. A relay failure here is therefore real, not flakiness in this test.
"""
from __future__ import annotations
import json
import os
import ssl
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tests.phase2.browser_support import browser_executable  # noqa: E402

BASE = os.environ.get('MOSS_BASE', 'https://127.0.0.1:17861').rstrip('/')
LOOPBACK = urlsplit(BASE).hostname in {'127.0.0.1', '::1', 'localhost'}
CONTEXT = ssl._create_unverified_context() if LOOPBACK else None
CORPUS = REPO / 'evidence/live-policy-sweep-20260825/corpus'
TRANSCRIPTS = ('mono_javier_intro_50s', 'interview_adam_frank_180s')
RELAY_MODEL = os.environ.get('MOSS_RELAY_MODEL', 'qwen/qwen3.6-35b-a3b')
EXTERNAL_KEY = os.environ.get('OPENROUTER_API_KEY') or os.environ.get('MOSS_DEMO_OPENROUTER_API_KEY', '')
EXTERNAL_ENDPOINT = os.environ.get('MOSS_SUMMARY_ENDPOINT', 'https://openrouter.ai/api/v1')
EXTERNAL_MODEL = os.environ.get('MOSS_SUMMARY_MODEL', 'google/gemini-2.5-flash-lite')
TRIALS = int(os.environ.get('TRIALS', '1'))
PROVIDERS = {name.strip() for name in os.environ.get('MOSS_SUMMARY_PROVIDERS', 'relay,external').split(',') if name.strip()}

jar: dict[str, str] = {}


def api(method, path, raw=None, content_type='application/json'):
    headers = {'Content-Type': content_type}
    if jar:
        headers['Cookie'] = '; '.join(f'{k}={v}' for k, v in jar.items())
    request = urllib.request.Request(BASE + path, data=raw, method=method, headers=headers)
    with urllib.request.urlopen(request, context=CONTEXT, timeout=300) as response:
        for header in response.headers.get_all('Set-Cookie') or []:
            name, _, value = header.partition('=')
            jar[name] = value.split(';')[0]
        return json.loads(response.read() or b'{}')


def file_meeting(corpus):
    audio = (CORPUS / corpus / 'audio.wav').read_bytes()
    boundary = '----mosssummaries'
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{corpus}.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n').encode() + audio + f'\r\n--{boundary}--\r\n'.encode()
    meeting_id = api('POST', '/api/meetings/file', raw=body, content_type=f'multipart/form-data; boundary={boundary}')['id']
    started = time.monotonic()
    while time.monotonic() - started < 400:
        meeting = api('GET', f'/api/meetings/{meeting_id}')
        meeting = meeting.get('meeting') or meeting
        if meeting.get('status') in ('completed', 'failed'):
            return meeting_id, meeting.get('status')
        time.sleep(3)
    return meeting_id, 'timeout'


def main():
    from playwright.sync_api import sync_playwright
    for corpus in TRANSCRIPTS:
        if not (CORPUS / corpus / 'audio.wav').exists():
            print(f'  SKIP: corpus missing: {corpus}')
            return 77
    api('POST', '/api/workspace/bootstrap')
    providers = []
    listed = {row.get('id') for row in api('GET', '/api/llm/models').get('data', [])}
    if 'relay' not in PROVIDERS:
        print('  SKIP relay: not selected by MOSS_SUMMARY_PROVIDERS')
    elif RELAY_MODEL in listed:
        providers.append('relay')
    else:
        print(f'  SKIP relay: {RELAY_MODEL} is not listed by this server')
    if 'external' not in PROVIDERS:
        print('  SKIP external: not selected by MOSS_SUMMARY_PROVIDERS')
    elif EXTERNAL_KEY:
        providers.append('external')
    else:
        print('  SKIP external: OPENROUTER_API_KEY is not set')
    if not providers:
        return 77
    meetings = {corpus: file_meeting(corpus) for corpus in TRANSCRIPTS}
    for corpus, (_, status) in meetings.items():
        if status != 'completed':
            print(f'  FAIL: {corpus} transcription ended {status}')
            return 1

    outcomes = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_executable(), headless=True)
        context = browser.new_context(ignore_https_errors=LOOPBACK)
        context.add_cookies([{'name': k, 'value': v, 'url': BASE} for k, v in jar.items()])
        page = context.new_page()
        page.goto(BASE, wait_until='networkidle')
        page.locator('[data-history-boot="ready"]').wait_for(timeout=60000)
        # The versioned bundle is injected by the bootstrap script, so read it from the rendered DOM.
        bundles = [src for src in page.evaluate("() => [...document.querySelectorAll('script[src]')].map(s => s.src)") if 'app' in src]
        fixed = any('json_object' in urllib.request.urlopen(src, context=CONTEXT, timeout=30).read().decode(errors='ignore')
                    for src in bundles)
        print(f'  served bundle sends response_format to external providers: {fixed}')
        for provider in providers:
            for corpus, (meeting_id, _) in meetings.items():
                for trial in range(TRIALS):
                    page.locator('[aria-label="Meeting history"]').get_by_role('button', name='Refresh', exact=True).click()
                    page.locator(f'.account-history-panel [data-open-meeting="{meeting_id}"]').click()
                    page.wait_for_load_state('networkidle')
                    settings = page.locator('[aria-label="Browser AI settings"]').first
                    if not settings.get_by_label('Provider', exact=True).count():
                        settings.get_by_role('button').first.click()
                    settings.get_by_label('Provider', exact=True).select_option(provider)
                    if provider == 'external':
                        settings.get_by_label('Provider HTTPS URL', exact=True).fill(EXTERNAL_ENDPOINT)
                        settings.get_by_label('Model', exact=True).fill(EXTERNAL_MODEL)
                        settings.get_by_label('API key (optional)', exact=True).fill(EXTERNAL_KEY)
                    else:
                        settings.get_by_label('Relay model', exact=True).select_option(RELAY_MODEL)
                    settings.get_by_role('button', name='Save on this browser', exact=True).click()
                    generate = page.get_by_test_id('final-summary-generate')
                    generate.wait_for(timeout=30000)
                    started = time.monotonic()
                    with page.expect_response(lambda r: r.request.method == 'POST'
                                              and r.url.split('?')[0].endswith('/summary')) as pending:
                        generate.click()
                    attempt = pending.value.json().get('attempt_id')
                    page.locator(f'[data-summary-attempt="{attempt}"][data-summary-state="current"], '
                                 f'[data-summary-attempt="{attempt}"][data-summary-state="failed"]').wait_for(timeout=420000)
                    artifact = api('GET', f'/api/meetings/{meeting_id}/summary').get('summary') or {}
                    model = EXTERNAL_MODEL if provider == 'external' else RELAY_MODEL
                    outcomes.append(artifact.get('state') == 'current')
                    print(f"  {'PASS' if outcomes[-1] else 'FAIL'}  {provider:8s} {model:26s} {corpus:28s} "
                          f"#{trial} state={artifact.get('state')} error={artifact.get('error_code')} "
                          f"{time.monotonic() - started:.1f}s", flush=True)
        browser.close()
    print(f'\n  {sum(outcomes)}/{len(outcomes)} summaries current')
    return 0 if all(outcomes) else 1


if __name__ == '__main__':
    sys.exit(main())
