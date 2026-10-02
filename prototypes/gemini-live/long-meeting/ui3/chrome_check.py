"""UI3 real product routes + real Chrome. Local synthetic speech; no providers."""
from __future__ import annotations
import asyncio
import json
import math
import struct
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import uvicorn
from playwright.sync_api import sync_playwright, expect
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiLiveRuntime, ScriptedGeminiEngine, GeminiBase, GeminiSegment,
)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceDescriptor, LiveServiceBounds, LiveServiceConfigHashes, hash_config,
)

EV = Path('/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/ui3')
CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
PORT = 18986


def main():
    state = EV / f'chrome-state-{time.time_ns()}'
    state.mkdir(parents=True)
    descriptor = LiveServiceDescriptor(
        source_revision='f9d13595', provider_name='gemini', provider_revision='ui3-scripted',
        provider_manifest_hash=hash_config({}),
        config_hashes=LiveServiceConfigHashes.from_parts(endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4, max_retained_samples=32000,
                                 max_identity_speakers=8, max_events=64, max_tape_bytes=100000000), frame_samples=8000,
    )
    count = 0
    def engine(_id, publish, _usage, _settings=None):
        nonlocal count
        count += 1
        segment = GeminiSegment(0, 16000, f'Synthetic session {count}', 'speaker-1', 'system')
        return ScriptedGeminiEngine(publish, batches=[(GeminiBase(16000, (segment,)),)], terminal=(segment,))
    runtime = GeminiLiveRuntime(descriptor=descriptor, tape_storage_root=state / 'tapes', engine_factory=engine)
    def no_summary(*args, **kwargs):
        raise AssertionError('Summary provider forbidden in UI3 Chrome check')
    app = create_phase2_app(database_path=state / 'phase2.sqlite3', file_work_root=state / 'file-work',
                            meeting_audio_root=state / 'audio', live_runtime_factory=lambda: runtime,
                            live_helper_lease_seconds=120, open_workspace=True, llm_upstreams='[]',
                            summary_generator=no_summary)
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, log_level='error', access_log=False))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    result = {'base': 'f9d13595', 'provider_calls': 0, 'port': PORT, 'state': str(state)}
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Local server failed to start')
            time.sleep(.05)
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=CHROME, headless=True)
            context = browser.new_context(viewport={'width': 1440, 'height': 1000})
            context.add_init_script("localStorage.setItem('moss.settings.v2', JSON.stringify({summary:{vendor:'off'},general:{cleanupAfterStop:false}}))")
            external = []
            def route(request):
                if urlsplit(request.request.url).hostname != '127.0.0.1':
                    external.append(request.request.url)
                    request.abort()
                else:
                    request.continue_()
            context.route('**/*', route)
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{PORT}/')
            page.wait_for_selector('[data-history-boot="ready"]')
            # One second of synthetic tone through the actual frame and Stop routes.
            import base64
            pcm = b''.join(struct.pack('<h', int(1000 * math.sin(i * 2 * math.pi * 220 / 16000))) for i in range(16000))
            ids = []
            for _ in range(3):
                mid = page.evaluate('''async ({pcm}) => {
                    const call = async (url, body) => {
                        const r = await fetch(url, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                        const j = await r.json(); if (!r.ok) throw new Error(JSON.stringify(j)); return j;
                    };
                    const created = await call('/api/live/sessions', {engine_settings:{transcription:{vendor:'gemini',api_key:'offline-scripted'},cleanup_after_stop:false}});
                    const id = created.id;
                    for (const lane of ['system','microphone']) await call('/api/live/sessions/'+id+'/frames', {
                        lane, sequence:0, capture_timestamp_ns:0, device_epoch:0, discontinuity:false, silent:false, sample_count:16000, sample_rate:16000,
                        pcm_base64:lane==='system'?pcm:btoa(String.fromCharCode(...new Uint8Array(32000)))
                    });
                    await call('/api/live/sessions/'+id+'/stop', {deadline:2});
                    return id;
                }''', {'pcm': base64.b64encode(pcm).decode()})
                ids.append(mid)
            page.reload()
            history = page.locator('.history-panel')
            expect(history.locator('[data-meeting-card]')).to_have_count(3)
            result['created'] = ids
            card = history.locator('[data-meeting-card]').first
            target = card.get_attribute('data-meeting-card')
            card.hover()
            expect(card.get_by_role('button', name='Delete session', exact=True)).to_be_visible()
            history.screenshot(path=str(EV / '01-card-trash.png'))
            card.get_by_role('button', name='Delete session', exact=True).click()
            expect(card.locator('[data-delete-confirm]')).to_contain_text('Delete this session? Its transcript, audio and summary are removed.')
            history.screenshot(path=str(EV / '02-inline-confirm.png'))
            card.get_by_role('button', name='Cancel', exact=True).click()
            card.get_by_role('button', name='Delete session', exact=True).click()
            page.keyboard.press('Escape')
            expect(card.locator('[data-delete-confirm]')).to_have_count(0)
            card.locator('[data-open-meeting]').click()
            expect(page.locator('#tr-body')).to_contain_text('Synthetic session')
            card.get_by_role('button', name='Delete session', exact=True).click()
            card.get_by_role('button', name='Delete', exact=True).click()
            expect(history.locator('[data-meeting-card]')).to_have_count(2)
            expect(page.locator('#tr-body')).not_to_contain_text('Synthetic session')
            history.get_by_role('button', name='Delete All', exact=True).click()
            expect(history.locator('[data-delete-confirm]')).to_contain_text('Delete all 2 sessions?')
            history.screenshot(path=str(EV / '03-delete-all-confirm.png'))
            history.get_by_role('button', name='Delete All 2 Sessions', exact=True).click()
            expect(history.locator('[data-meeting-card]')).to_have_count(0)
            expect(history).to_contain_text('No meetings yet.')
            expect(history.get_by_role('button', name='Delete All', exact=True)).to_be_disabled()
            history.screenshot(path=str(EV / '04-empty-panel.png'))
            page.reload()
            expect(history.locator('[data-meeting-card]')).to_have_count(0)
            result.update(deleted_one=target, remaining_after_one=2, remaining_after_all=0,
                          empty_after_reload=True, chrome=browser.version, errors=errors, external_requests=external)
            assert not errors and not external
            context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        result['server_stopped'] = not thread.is_alive()
        (EV / 'chrome-result.json').write_text(json.dumps(result, indent=2) + '\n')
    assert result['server_stopped']
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
