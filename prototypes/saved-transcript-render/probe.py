"""THROWAWAY saved-transcript browser rendering probe. Do not run during shared capacity work.

Question: can the real built UI render and search the tail of a 201-minute saved
transcript without dropping passages or incurring an unmeasured browser failure?

Run after capacity is released:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python prototypes/saved-transcript-render/probe.py
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

from moss_transcribe_diarize.app.phase2 import _workspace_html
from playwright.sync_api import expect, sync_playwright
from tests.phase2.browser_support import browser_executable


ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'moss_transcribe_diarize/app/frontend_assets'
DEFAULT_OUTPUT = ROOT / 'evidence/mvpfix/wp25/saved-transcript-render'
CASES = (
    ('5min', 5, 120),
    ('30min', 30, 720),
    ('201min', 201, 4824),
)
TIMEOUT_MS = 180_000


def fixture(case: str, minutes: int, passages: int):
    seconds_per_passage = minutes * 60 / passages
    assert seconds_per_passage == 2.5
    tail_token = f'TAIL{passages}SENTINEL'
    tail_text = f'Public tail {tail_token} keeps every final word exactly retained.'
    public_suffix = (' Public transcript words stay deterministic while the real browser lays out every saved passage'
                     ' without decoder, microphone, private data, or hidden grouping.')
    segments = []
    for index in range(passages):
        person = index % 2
        segments.append({
            'id': f'seg_{index + 1:04d}',
            'start': index * seconds_per_passage,
            'end': (index + 1) * seconds_per_passage,
            'speaker': 'Public Alice' if person == 0 else 'Public Blair',
            'speaker_entity_id': f'person-{person + 1}',
            'source_lane': 'system',
            'text': tail_text if index == passages - 1 else f'Public passage {index + 1:04d} rendering control words.{public_suffix}',
        })
    meeting = {
        'id': f'saved-render-{case}',
        'mode': 'file',
        'title': f'Public {minutes} minute rendering fixture',
        'title_source': 'manual',
        'status': 'completed',
        'created_at_ms': 1_789_700_400_000,
        'transcript': {'segments': segments},
        'transcript_version': 1,
        'audio': None,
        'needs_review': False,
    }
    return meeting, tail_token, tail_text


def install_routes(page, meeting):
    html = _workspace_html(SimpleNamespace(display_name='Public rendering probe'), [], live_enabled=True)

    def route(request):
        path = urlsplit(request.request.url).path
        if path == '/':
            request.fulfill(body=html, content_type='text/html')
        elif path.startswith(('/static/', '/fonts/')):
            asset = ASSETS / path.removeprefix('/static/').lstrip('/')
            request.fulfill(path=str(asset)) if asset.is_file() else request.fulfill(status=404)
        elif path == '/api/meetings':
            request.fulfill(json={'meetings': [meeting]})
        elif path == f"/api/meetings/{meeting['id']}":
            request.fulfill(json=meeting)
        elif path == '/api/voiceprints':
            request.fulfill(json={'voiceprints': []})
        elif path == '/api/llm/models':
            request.fulfill(json={'data': []})
        elif path.endswith('/summary'):
            request.fulfill(json={'summary': None})
        else:
            request.fulfill(json={})

    page.route('**/*', route)


def measure(browser, output: Path, case: str, minutes: int, passages: int):
    meeting, tail_token, tail_text = fixture(case, minutes, passages)
    case_output = output / case
    case_output.mkdir()
    snapshot = json.dumps(meeting, indent=2) + '\n'
    (case_output / 'meeting.json').write_text(snapshot)
    errors = []
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.set_default_timeout(TIMEOUT_MS)
    page.on('pageerror', lambda error: errors.append({'kind': 'pageerror', 'text': str(error)}))
    page.on('console', lambda message: errors.append({'kind': 'console', 'text': message.text}) if message.type == 'error' else None)
    page.on('requestfailed', lambda request: errors.append({'kind': 'requestfailed', 'path': urlsplit(request.url).path}))
    install_routes(page, meeting)
    started = time.perf_counter()
    page.goto(f'http://saved-transcript.test/?case={case}', wait_until='domcontentloaded')
    page.locator('[data-history-boot="ready"]').wait_for()
    page.locator(f'[data-open-meeting="{meeting["id"]}"]').click()
    page.wait_for_function(
        'expected => document.querySelectorAll("#tr-body .utt").length === expected',
        arg=passages,
    )
    rows = page.locator('#tr-body .utt')
    last = rows.last
    last.scroll_into_view_if_needed()
    expect(last).to_be_in_viewport(timeout=TIMEOUT_MS)
    load_to_tail_visible_ms = round((time.perf_counter() - started) * 1000, 3)
    tail_before_search = last.locator('.utt-text').text_content()
    page.screenshot(path=str(case_output / 'tail-visible.png'))

    page.get_by_role('button', name='Find', exact=True).click()
    search_started = time.perf_counter()
    page.locator('#transcript-find-input').fill(tail_token)
    expect(page.locator('.tr-find-meta')).to_have_text('1 of 1 matches', timeout=TIMEOUT_MS)
    expect(page.locator('.tr-search-match.is-active')).to_have_text(tail_token, timeout=TIMEOUT_MS)
    expect(last).to_be_in_viewport(timeout=TIMEOUT_MS)
    search_tail_ms = round((time.perf_counter() - search_started) * 1000, 3)
    tail_after_search = last.locator('.utt-text').text_content()
    rendered_after_search = rows.count()
    page.screenshot(path=str(case_output / 'search-tail.png'))
    result = {
        'case': case,
        'minutes': minutes,
        'source_passages': passages,
        'snapshot_bytes': len(snapshot.encode()),
        'rendered_passages': rows.count(),
        'rendered_after_search': rendered_after_search,
        'load_to_tail_visible_ms': load_to_tail_visible_ms,
        'search_tail_ms': search_tail_ms,
        'tail_token': tail_token,
        'expected_tail_words': tail_text,
        'tail_before_search': tail_before_search,
        'tail_after_search': tail_after_search,
        'browser_errors': errors,
    }
    result['status'] = 'PASS' if (
        result['rendered_passages'] == passages
        and rendered_after_search == passages
        and tail_before_search == tail_text
        and tail_after_search == tail_text
        and not errors
    ) else 'FAIL'
    page.close()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error('Use an empty output directory; evidence is never overwritten')
    result = {
        'prototype': 'saved-transcript-render',
        'status': 'RUNNING',
        'candidate_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'built_assets': str(ASSETS.relative_to(ROOT)),
        'viewport': {'width': 1440, 'height': 900},
        'timing_contract': 'Measured only; no acceptance threshold has been authorized.',
        'cases': [],
    }
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=str(browser_executable(playwright)), headless=True)
        result['browser_version'] = browser.version
        try:
            for spec in CASES:
                try:
                    row = measure(browser, output, *spec)
                except Exception as error:
                    row = {
                        'case': spec[0],
                        'minutes': spec[1],
                        'source_passages': spec[2],
                        'status': 'FAIL',
                        'exception': type(error).__name__,
                        'error': str(error),
                    }
                result['cases'].append(row)
                (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
                print(json.dumps(row), flush=True)
        finally:
            browser.close()
    result['status'] = 'PASS' if all(row['status'] == 'PASS' for row in result['cases']) else 'FAIL'
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
