"""Opt-in live relay bench: patched app + real Chrome + configured tailnet models.

PYTHONPATH=. .venv/bin/python prototypes/client-configured-llm/thinking_browser_probe.py --output /tmp/moss-thinking-browser
Creates only disposable app/browser state; does not operate the running host stack.
Uses an explicit private transcript input; makes one summary attempt per configured model.
"""
import argparse
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from unittest.mock import patch

from playwright.async_api import async_playwright
from moss_transcribe_diarize.app import phase2
from tests.phase2.browser_support import browser_executable, BrowserExecutableMissing

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('workspace_bench', ROOT / 'prototypes/phase2-account-lifecycle/browser_workspace_probe.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
CONFIG = [
    {'name': 'macstudio', 'base_url': 'http://macstudio.tailnet.aisight.us:1234/v1', 'models': ['qwen/qwen3.6-35b-a3b']},
    {'name': 'rtx4090', 'base_url': 'http://ga0-rtx4090.tailnet.aisight.us:1235/v1', 'models': ['qwen38-27b-mtp']},
]


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')


async def run(root, output, source_path):
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    source = json.loads(source_path.read_text())
    segments = [{k: s[k] for k in ('start', 'end', 'speaker', 'text')} for s in source['transcript']['segments']]
    with patch.dict(os.environ, {'MOSS_LLM_UPSTREAMS': json.dumps(CONFIG)}):
        async with bench.running(root / 'probe.sqlite3') as (app, port):
            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=str(browser_executable(p)), channel='chromium', headless=True)
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await bench.open_workspace(page, f'http://localhost:{port}')
                    await page.get_by_role('button', name='Optional AI summaries · configured', exact=True).click()
                    cookie = next(c['value'] for c in await context.cookies() if c['name'] == phase2.SESSION_COOKIE)
                    account = await app.state.phase2_store.account_for_session(cookie)
                    meeting = await app.state.phase2_store.workspace(account).create_meeting('file')
                    await meeting.commit_transcript({'segments': segments}, terminal=True)
                    await page.locator('[data-history-boot="ready"]').wait_for()
                    await page.get_by_role('button', name='Refresh', exact=True).click()
                    await page.locator(f'.account-history-panel [data-open-meeting="{meeting.meeting_id}"]').click()
                    results = []
                    for upstream in CONFIG:
                        name, model = upstream['name'], upstream['models'][0]
                        await page.get_by_label('Relay model', exact=True).select_option(model)
                        await page.get_by_role('button', name='Restore default prompt', exact=True).click()
                        await page.get_by_role('button', name='Save on this browser', exact=True).click()
                        async with page.expect_response(lambda r: r.url.endswith('/api/llm/chat/completions'), timeout=190000) as relay_response:
                            async with page.expect_response(lambda r: r.url.endswith(f'/api/meetings/{meeting.meeting_id}/summary') and r.request.method == 'POST') as accepted_response:
                                await page.get_by_test_id('final-summary-generate').click()
                            accepted = await (await accepted_response.value).json()
                        relay = await relay_response.value
                        # Bind to this attempt, never a previous current artifact.
                        attempt = accepted['attempt_id']
                        await page.locator(f'[data-summary-attempt="{attempt}"][data-summary-state="current"], [data-summary-attempt="{attempt}"][data-summary-state="failed"]').wait_for(timeout=10000)
                        artifact = await page.evaluate("async id => (await (await fetch('/api/meetings/'+id+'/summary')).json()).summary", meeting.meeting_id)
                        checks = {'http_200': relay.status == 200, 'current': artifact['state'] == 'current',
                                  'budget_2048': relay.request.post_data_json['max_tokens'] == 2048,
                                  'exact_transcript': json.loads(relay.request.post_data_json['messages'][1]['content']) == {'segments': segments},
                                  'current_default_prompt': relay.request.post_data_json['messages'][0]['content'] == (ROOT / 'frontend/src/lib/final-summary-prompt.txt').read_text()}
                        results.append({'model': model, 'checks': checks})
                        print(json.dumps(results[-1]), flush=True)
                    write(output / 'browser-results.json', {'results': results, 'sqlite': sqlite3.sqlite_version, 'browser': browser.version, 'stack': 'disposable patched production app; real tailnet upstreams'})
                    assert all(all(r['checks'].values()) for r in results)
                finally:
                    await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True, help='Private transcript JSON; never retained in evidence')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix='moss-thinking-browser-') as root:
            asyncio.run(run(Path(root), args.output, args.source))
    except BrowserExecutableMissing as exc:
        print(type(exc).__name__)
        raise SystemExit(77)
