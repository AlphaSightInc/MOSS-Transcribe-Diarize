"""Product bundle + actual worklet in real Chrome; fake provider and protocol only."""
import asyncio
import json
import math
import struct
import subprocess
import sys
import threading
import time
import wave
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests/phase2'), str(ROOT / 'tests/gemini'), str(ROOT / 'tests')]
import uvicorn
from fastapi.responses import HTMLResponse, FileResponse
from playwright.sync_api import sync_playwright
from test_owner_bound_live_meeting import provision, make_app
from test_gemini_live_runtime import descriptor
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime, ScriptedGeminiEngine
from protocol import ResumeProtocol

EV = Path('/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-client')
PORT = 18986
URL = f'https://127.0.0.1:{PORT}'
TITLE = 'P74 RC synthetic tab'
INIT = r"""(() => {
  window.measurement = {loadedAt: Date.now(), frames: [], resumes: [], errors: [], clicks: [], media: []};
  const log = measurement;
  document.addEventListener('click', e => log.clicks.push(e.target.closest('button')?.textContent || e.target.tagName), true);
  const f = window.fetch.bind(window);
  window.fetch = async (url, init) => {
    const r = await f(url, init);
    if (String(url).endsWith('/frames')) {
      const b = JSON.parse(init.body); delete b.pcm_base64;
      log.frames.push({...b, status: r.status, at: Date.now(), header: init.headers['X-Moss-Capture-Instance']});
    }
    if (String(url).endsWith('/resume')) log.resumes.push({request: JSON.parse(init.body), status: r.status, response: await r.clone().json()});
    return r;
  };
  const gum = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async c => { log.media.push({api:'microphone', c, active:navigator.userActivation.isActive}); return gum(c); };
  const gdm = navigator.mediaDevices.getDisplayMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getDisplayMedia = c => {
    const active = navigator.userActivation.isActive;
    const row = {api:'display', active, focused:document.hasFocus()}; log.media.push(row);
    // Chrome's chooser automation bypasses activation. Inject the contract's refusal only on reload
    // so the real graph/UI can measure its silent-lane branch, without certifying a native picker.
    if (sessionStorage.getItem('lt:session:reattach') && !log.clicks.some(v => v.includes('Share tab audio again'))) {
      row.result='injected refusal'; return Promise.reject(new DOMException('contract: gesture required', 'NotAllowedError'));
    }
    return gdm(c).then(stream => { row.result = "accepted"; row.tracks=stream.getTracks().map(t=>({kind:t.kind, settings:t.getSettings()})); return stream; }, error => {row.error=error.name+": "+error.message; throw error;});
  };
  localStorage.setItem('moss.settings.v2', JSON.stringify({transcription:{vendor:'gemini', apiKey:'offline-prototype-stub'}, summary:{vendor:'off'}, general:{cleanupAfterStop:false}}));
  localStorage.setItem('lt:ui:controlPanelCollapsed', 'false');
})()"""


def main():
    subprocess.run(['/opt/homebrew/bin/npm', '--prefix', str(ROOT / 'frontend'), 'run', 'build', '--', '--outDir', str(EV / 'bundle')],
        check=True, capture_output=True)
    directory = EV / ('chrome-' + time.strftime('%Y%m%d-%H%M%S'))
    directory.mkdir(parents=True)
    database = directory / 'meeting.sqlite'
    cookies = asyncio.run(provision(database))
    def runtime():
        d = descriptor(tape_bytes=16 * 1024 * 1024)
        d = replace(d, frame_samples=8000, bounds=replace(d.bounds, max_retained_samples=960000, max_events=1024))
        return GeminiLiveRuntime(descriptor=d, engine_factory=lambda _sid, pub, _usage, _settings:
            ScriptedGeminiEngine(pub, batches=[], terminal=()), tape_storage_root=directory / 'tapes')
    app = make_app(database, lease_seconds=120, live_runtime_factory=runtime)
    offset = [0]
    protocol = ResumeProtocol(app, 'S2', lambda: time.monotonic_ns() + offset[0])
    with wave.open(str(directory / 'mic.wav'), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(struct.pack('<16000h', *(int(3000 * math.sin(i * 2 * math.pi * 330 / 16000)) for i in range(16000))) * 60)
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(directory / 'tls-key.pem'),
        '-out', str(directory / 'tls-cert.pem'), '-days', '1', '-subj', '/CN=127.0.0.1'], check=True, capture_output=True)
    @app.get('/rc/')
    async def page_html():
        return HTMLResponse('<!doctype html><meta charset="utf-8"><title>P74 RC product</title><meta name="moss-worklet-url" content="/rc/worklet.js">'
            '<link rel="stylesheet" href="/rc/styles.css"><div id="app"></div><script type="module" src="/rc/app.js"></script>')
    @app.get('/rc/app.js')
    async def bundle(): return FileResponse(EV / 'bundle/app.js', media_type='application/javascript')
    @app.get('/rc/styles.css')
    async def styles(): return FileResponse(EV / 'bundle/styles.css', media_type='text/css')
    @app.get('/rc/worklet.js')
    async def worklet(): return FileResponse(ROOT / 'frontend/public/worklets/lane-framer.js', media_type='application/javascript')
    @app.get('/rc/tone.wav')
    async def tone(): return FileResponse(directory / 'mic.wav', media_type='audio/wav')
    @app.get('/rc/source')
    async def source(): return HTMLResponse(f'<!doctype html><title>{TITLE}</title><button id="play">Play synthetic tone</button>'
        '<audio id="tone" src="/rc/tone.wav" loop></audio>'
        '<script>document.getElementById("play").onclick=()=>document.getElementById("tone").play();</script>')
    @app.get('/rc/away')
    async def away(): return HTMLResponse('<!doctype html><title>Capture page away</title>away')
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=PORT, ssl_keyfile=str(directory / 'tls-key.pem'),
        ssl_certfile=str(directory / 'tls-cert.pem'), log_level='error'))
    thread = threading.Thread(target=server.run, daemon=True); thread.start()
    result = {'cases': {}, 'product_root': str(ROOT), 'protocol': 'copied prototype S2 adapted to binding JSON/3 s freshness/120 s',
        'display_refusal': 'injected only for gestureless reload; auto-select flag bypasses native gesture requirement', 'evidence': str(directory)}
    browser = None
    try:
        for _ in range(100):
            if server.started: break
            time.sleep(.05)
        assert server.started
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless=True,
                ignore_default_args=['--mute-audio'], args=['--use-fake-device-for-media-stream', '--auto-accept-camera-and-microphone-capture',
                f'--auto-select-tab-capture-source-by-title={TITLE}', f'--use-file-for-fake-audio-capture={directory / "mic.wav"}'])
            result['chrome_version'] = browser.version
            ctx = browser.new_context(ignore_https_errors=True, viewport={'width':1440,'height':1000})
            ctx.grant_permissions(['microphone'], origin=URL)
            ctx.add_cookies([{'name':'__Host-moss_session','value':cookies['a'],'domain':'127.0.0.1','path':'/','secure':True,'httpOnly':True,'sameSite':'Lax'}])
            ctx.add_init_script(INIT)
            src = ctx.new_page(); src.goto(URL+'/rc/source'); src.click('#play')
            def start(system=False):
                page = ctx.new_page(); page.add_init_script(f"localStorage.setItem('lt:capture:sources',JSON.stringify({{system:{str(system).lower()},microphone:true}}))")
                page.goto(URL+'/rc/'); page.get_by_role('button',name='Start recording',exact=True).click()
                page.wait_for_function('measurement.frames.filter(f=>f.status===200).length >= 12', timeout=15000)
                return page
            def capture(page, name):
                value = page.evaluate('measurement')
                (directory/f'{name}.json').write_text(json.dumps(value,indent=2))
                page.screenshot(path=str(directory/f'{name}.png'))
                return value
            # A/B: immediate reload. The contract itself requires a refusal while heartbeat is fresh.
            for code, system in [('a_microphone',False),('b_tab_microphone',True)]:
                page = start(system); old = page.evaluate("JSON.parse(sessionStorage.getItem('lt:session:reattach'))")
                page.reload()
                # No JS evaluation until automatic acquisition/adoption has completed: Playwright
                # evaluate/wait_for_function can supply transient activation.
                page.wait_for_timeout(4000)
                immediate = capture(page, code+'-immediate')
                cell = {'stored_before':old,'immediate':immediate,'zero_click_gate': bool(any(f['status']==200 for f in immediate['frames'])),
                    'first_accepted_frame_seconds': next(((f['at']-immediate['loadedAt'])/1000 for f in immediate['frames'] if f['status']==200),None)}
                if not cell['zero_click_gate']:
                    # Retain the failure, then measure explicit contract fallback; do not score this as a zero-click pass.
                    page.get_by_role('button',name='Resume recording here',exact=True).click()
                    page.wait_for_function('measurement.frames.filter(f=>f.status===200).length >= 12', timeout=15000)
                    cell['explicit_fallback'] = capture(page, code+'-explicit')
                # A real same-tab reload after navigation spends >3 s away is within lease and automatically eligible.
                page.goto(URL+'/rc/away'); page.wait_for_timeout(3200); page.goto(URL+'/rc/')
                page.wait_for_timeout(4000)
                eligible = capture(page, code+'-eligible')
                cell['eligible_after_3s'] = eligible
                cell['eligible_clicks'] = len(eligible['clicks'])
                cell['eligible_media_activation'] = [m['active'] for m in eligible['media']]
                assert sum(f['status']==200 for f in eligible['frames']) >= 12, eligible
                cell['eligible_first_frame_seconds'] = next((f['at']-eligible['loadedAt'])/1000 for f in eligible['frames'] if f['status']==200)
                cell['same_meeting'] = page.evaluate("JSON.parse(sessionStorage.getItem('lt:session:reattach')).sessionId") == old['sessionId']
                if system:
                    cell['share_button'] = page.get_by_role('button',name='Share tab audio again',exact=True).count()
                    (directory / 'partial.json').write_text(json.dumps({**result, 'current_case':cell},indent=2))
                    page.bring_to_front()
                    page.get_by_role('button',name='Share tab audio again',exact=True).click()
                    try:
                        page.wait_for_function("measurement.frames.some(f=>f.lane==='system' && f.device_epoch===4 && f.status===200)",timeout=15000)
                    except Exception as error:
                        cell['share_error'] = repr(error)
                        cell['share_diagnostic'] = page.evaluate('({measurement, text:document.body.textContent})')
                    cell['source_audio_state'] = src.evaluate("({paused:tone.paused,t:tone.currentTime})")
                    cell['one_share_click'] = capture(page, code+'-shared')
                    cell['tab_audio_non_silent'] = any(f['lane']=='system' and not f['silent'] and f['status']==200 for f in cell['one_share_click']['frames'])
                result['cases'][code] = cell
                (directory/'partial.json').write_text(json.dumps(result,indent=2))
                page.get_by_role('button',name='Stop recording',exact=True).click(); page.wait_for_timeout(500); page.close()
            # C: synthetic clock advance past lease, no 125-second real-time wait.
            page = start(); offset[0] += 125_000_000_000; page.reload(); page.wait_for_timeout(4000)
            page.wait_for_function("document.body.textContent.includes('Recording stopped: connection lost.')",timeout=15000)
            result['cases']['c_expired_125s'] = capture(page,'c-expired'); page.close()
            offset[0] = 0
            # D: duplicated tab gets identical tab record, while original continues heartbeats.
            page = start(); saved = page.evaluate("sessionStorage.getItem('lt:session:reattach')")
            duplicate = ctx.new_page(); duplicate.add_init_script(f"sessionStorage.setItem('lt:session:reattach',{json.dumps(saved)})")
            duplicate.goto(URL+'/rc/'); duplicate.wait_for_timeout(4000); duplicate.wait_for_function("document.body.textContent.includes('Resume recording here')",timeout=15000)
            result['cases']['d_duplicate'] = capture(duplicate,'d-duplicate')
            result['cases']['d_duplicate']['original_frames_after'] = page.evaluate('measurement.frames.length')
            page.get_by_role('button',name='Stop recording',exact=True).click(); page.wait_for_timeout(500)
            duplicate.close(); page.close(); src.close(); browser.close(); browser=None
    except Exception as error:
        result['harness_error'] = repr(error)
        if browser:
            for i, page in enumerate(browser.contexts[0].pages):
                try:
                    result[f'failure_page_{i}'] = {'text':page.inner_text('body'),'state':page.evaluate('window.measurement')}
                    page.screenshot(path=str(directory/f'failure-{i}.png'))
                except Exception: pass
        raise
    finally:
        if browser:
            try: browser.close()
            except Exception: pass
        server.should_exit=True; thread.join(timeout=10)
        result['local_server_stopped'] = not thread.is_alive()
        (directory/'result.json').write_text(json.dumps(result,indent=2))
        (EV/'CHROME-LATEST.txt').write_text(str(directory)+'\n')
        print(json.dumps(result,indent=2),flush=True)

if __name__ == '__main__': main()
