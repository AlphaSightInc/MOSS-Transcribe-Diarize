"""Real UI/decoder verification. One pass; no decoder mocks or automatic decoder retries.
Run: .venv/bin/python tests/e2e/verify_workspace.py --corpus /path/to/mono_javier_intro_50s --output /tmp/moss-e2e-20260911
Requires ffmpeg/ffprobe and Playwright Chrome/Chromium. Exit 77 = browser unavailable.
Artifacts may contain corpus speech; report/network metadata never include transcript bodies.
--rows selects checks in a fresh workspace. Evidence output must be empty.
System TLS trust is the default; local self-signed TLS requires an explicit loopback-only flag.
"""
from __future__ import annotations
import argparse
import asyncio
import functools
import http.server
import json
import re
import subprocess
import threading
import time
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.phase2.browser_support import browser_executable, BrowserExecutableMissing


# First eligible canonical span (2.5s) + decode/identity allowance (1.0s)
# + capture-frame/publication polling allowance (0.5s). This is an empirical
# regression budget, not a worst-case inference guarantee. Start click precedes
# captured speech, so our clock is a conservative upper bound from speech onset.
FIRST_ENROLLED_LABEL_BOUND_SECONDS = 2.5 + 1.0 + 0.5


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))


def wer(reference, hypothesis):
    def words(s): return re.findall(r"[a-z0-9]+", s.lower())
    a, b = words(reference), words(hypothesis)
    last = list(range(len(b)+1))
    for i, x in enumerate(a, 1):
        current = [i]
        for j, y in enumerate(b, 1):
            current.append(min(current[-1]+1, last[j]+1, last[j-1]+(x != y)))
        last = current
    return {'reference_words': len(a), 'hypothesis_words': len(b), 'edits': last[-1], 'wer': last[-1]/max(1, len(a))}


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass


class Harness:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.output).resolve(); self.out.mkdir(parents=True, exist_ok=True)
        if any(self.out.iterdir()):
            raise ValueError('Use an empty --output directory; existing evidence and browser state are never reused')
        self.state = {'rows': {}, 'meetings': {}, 'base': args.base}
        self.row = 0; self.seq = 0; self.page = None
        self.network = (self.out/'network.jsonl').open('a')
        self.pending = set()

    def event(self, value):
        self.network.write(json.dumps({'t': time.time(), 'row': self.row, **value})+'\n'); self.network.flush()

    async def response(self, response):
        request = response.request
        item = {'method': request.method, 'path': urlsplit(response.url).path, 'status': response.status}
        if item['path'].endswith('/chat/completions'):
            try: item['model'] = request.post_data_json.get('model')
            except Exception: pass
            try:
                body=await response.json()
                self.seq+=1
                path=self.out/f'relay-response-{int(time.time())}-{self.seq}.json'
                write(path,body)
                item['response_artifact']=path.name
                if not response.ok: item['reason_code']=body.get('detail')
            except Exception: pass
        self.event(item)

    def attach(self, page):
        def response(r):
            task = asyncio.create_task(self.response(r)); self.pending.add(task); task.add_done_callback(self.pending.discard)
        page.on('response', response)
        page.on('close',lambda: self.event({'page_closed':True}))
        page.on('crash',lambda: self.event({'page_crashed':True}))
        page.on('requestfailed', lambda r: self.event({'path': urlsplit(r.url).path, 'failure': r.failure}))
        page.on('websocket', lambda ws: self.event({'websocket': urlsplit(ws.url).path}))
        # Observe only the time/count of visible text; no replacement of product APIs.
        return page

    async def api(self, path):
        return await self.page.evaluate('async p => { const r=await fetch(p); return {status:r.status, body:await r.json()}; }', path)

    async def snapshot(self, n, extra=''):
        path = self.out/f'row-{n:02d}{extra}.png'
        await self.page.screenshot(path=str(path), full_page=True)
        return path.name

    async def check(self, n, fn):
        if n in (2,3,4) and str(n) in self.state['rows'] and (n != 4 or 'live' in self.state['meetings']):
            print(f'ROW {n}: retained previous attempt; no decoder rerun', flush=True); return
        previous_row=self.row; self.row=n; start=time.monotonic(); data={}
        try:
            data=await fn() or {}
            status='PASS' if data.get('ok', True) else 'FAIL'
        except Exception as exc:
            status='FAIL'
            # Locator/errors only; no response/prompt text.
            data={'error': str(exc)[:1600], 'exception': type(exc).__name__}
        try: data['screenshot']=await self.snapshot(n)
        except Exception: data['screenshot']=None
        data.update(status=status, seconds=round(time.monotonic()-start,3), network='network.jsonl', row=n)
        self.state['rows'][str(n)]=data
        write(self.out/f'row-{n:02d}.json',data); write(self.out/'results.json', self.state)
        print(f'ROW {n}: {status} '+json.dumps(data),flush=True)
        if not self.page.is_closed():
            await self.context.storage_state(path=str(self.out/'browser-state.json'))
            (self.out/'browser-state.json').chmod(0o600)
        self.row=previous_row
        if n==12: await self.page.set_viewport_size({'width':1440,'height':1100})

    async def open(self):
        await self.page.goto(self.args.base)
        await self.page.locator('[data-auth-state="signed-in"]').wait_for(timeout=30000)
        await self.page.locator('[data-boot="ready"]').wait_for()
        await self.page.locator('[data-history-boot="ready"]').wait_for()

    async def bootstrap(self):
        await self.open()
        return {'signed_in':True,'boot_ready':True,'fresh_profile':not self.resumed}

    async def terminal(self, ident, timeout=240):
        stop=time.monotonic()+timeout
        while time.monotonic()<stop:
            result=await self.api('/api/meetings/'+ident)
            if result['status']==200 and result['body']['status']!='active':
                write(self.out/f'meeting-{ident}.json',result['body']); return result['body']
            await asyncio.sleep(1)
        raise AssertionError(f'meeting {ident} still active after {timeout}s')

    async def select(self, ident):
        await self.page.locator('[aria-label="Meeting history"]').get_by_role('button',name='Refresh',exact=True).click()
        await self.page.locator(f'.account-history-panel [data-open-meeting="{ident}"]').click()
        await self.page.wait_for_function('document.querySelectorAll(".utt-text").length > 0')

    async def file(self, url=False):
        await self.page.locator('input[type=file]').set_input_files([] if url else str(self.mp3))
        await self.page.locator('textarea[name=urls]').fill(self.media+'/source.mp3' if url else '')
        path='/api/meetings/url' if url else '/api/meetings/file'
        async with self.page.expect_response(lambda r: urlsplit(r.url).path==path and r.request.method=='POST') as pending:
            await self.page.get_by_role('button',name='Transcribe files and URLs',exact=True).click()
        response=await pending.value; value=await response.json()
        assert response.status in (200,201,202), f'submission HTTP {response.status}'
        ident=value['id']; self.state['meetings']['url' if url else 'file']=ident; write(self.out/'results.json',self.state)
        meeting=await self.terminal(ident)
        await self.select(ident)
        segments=(meeting.get('transcript') or {}).get('segments',[])
        metric=wer(self.reference,' '.join(s['text'] for s in segments))
        labels=sorted({s.get('speaker','') for s in segments if s.get('speaker')})
        return {'ok':meeting['status']=='completed' and bool(segments) and bool(labels) and metric['wer']<=.15,
                'meeting':ident,'status_received':meeting['status'],'segments':len(segments),'speaker_count':len(labels),**metric,
                'artifact':f'meeting-{ident}.json'}

    async def wait_before_reset(self, timeout=30):
        """Server completion can precede UI terminal; require both before Reset.

        Thirty seconds is the existing row-14 UI terminal budget. Do not start a
        new meeting on timeout, even if the previous meeting appears in history.
        """
        phase=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')
        if phase not in ('stopping','terminal'): return
        ident=getattr(self,'last_live_meeting',None)
        evidence={'meeting':ident,'phase':phase,'timeout_seconds':timeout}
        path=self.out/f'row-{self.row:02d}-before-reset.json'
        async def ready():
            while True:
                snapshot=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body'].get('snapshot') or {}
                session=snapshot.get('session') or {}
                meeting=(await self.api(f'/api/meetings/{ident}'))['body']
                evidence.update(snapshot_status=session.get('status'),finalization_status=session.get('finalization_status'),
                                history_status=meeting.get('status'),
                                phase=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase'))
                durable=(session.get('status')=='closed' and session.get('finalization_status')=='final') or meeting.get('status')=='completed'
                if durable and evidence['phase']=='terminal': return
                await asyncio.sleep(.25)
        try:
            assert ident, 'Previous live meeting ID unavailable before Reset capture'
            await asyncio.wait_for(ready(),timeout=timeout)
            evidence['ready']=True
        except Exception as exc:
            evidence.update(ready=False,reason=f'{type(exc).__name__}: previous meeting did not reach durable completion and UI terminal before Reset')
            raise AssertionError(json.dumps(evidence)) from exc
        finally:
            write(path,evidence)
            self.event({"before_reset":evidence})

    async def setup_live(self, *, foreground=True):
        if foreground:
            await self.page.bring_to_front()
        await self.page.get_by_role('link',name='Live / Transcript & export',exact=True).click()
        await self.wait_before_reset()
        reset=self.page.get_by_role('button',name='Reset capture',exact=True)
        if await reset.count(): await reset.click()
        await self.source.evaluate('document.querySelector("audio").currentTime=0')
        await self.page.get_by_label('Listening setup',exact=True).select_option('headphones')
        await self.page.get_by_role('button',name='Enable microphone',exact=True).click()
        await self.page.wait_for_function('document.querySelector(".capture-status")?.textContent.includes("Microphone connected")')
        await self.page.get_by_role('button',name='Share audio',exact=True).click()
        self.event({'source_audio': await self.source.locator('audio').evaluate('a=>({paused:a.paused,currentTime:a.currentTime,volume:a.volume,muted:a.muted,readyState:a.readyState})')})
        await self.page.get_by_role('button',name='Start capture',exact=True).wait_for(timeout=20000)
        # Capture the pre-start lane evidence before any session is submitted.
        meters=await self.page.locator('.capture-meter-track').evaluate_all('(els)=>els.map(e=>e.getAttribute("aria-label"))')
        self.event({'capture_meters':meters})
        return meters

    async def start_live(self, key):
        before=(await self.api('/api/meetings'))['body']['meetings']; ids={m['id'] for m in before}
        self.started=time.monotonic()
        await self.page.get_by_role('button',name='Start capture',exact=True).click()
        for _ in range(30):
            rows=(await self.api('/api/meetings'))['body']['meetings']
            found=[m for m in rows if m['id'] not in ids and m['mode']=='live']
            if found:
                ident=found[0]['id']; self.last_live_meeting=ident; self.state['meetings'][key]=ident; write(self.out/'results.json',self.state); return ident
            await asyncio.sleep(.2)
        raise AssertionError('No live meeting admitted within 6 seconds')

    async def rename(self):
        outcomes=[]
        for selector,name in [('.utt[data-state=confirmed] .utt-speaker:not([disabled]), .utt[data-state=final] .utt-speaker:not([disabled])','E2E Rowan'),('.legend-chip:not([disabled])','E2E Morgan')]:
            button=self.page.locator(selector).first
            await button.wait_for(timeout=75000); old=await button.inner_text()
            await button.click(); await self.page.get_by_label('Display name',exact=True).fill(name)
            async with self.page.expect_response(lambda r: '/speakers/' in r.url and r.request.method=='PUT') as ack:
                await self.page.get_by_role('button',name='Save name',exact=True).click()
            response=await ack.value; body=await response.json()
            self.state['named']=name; write(self.out/'results.json',self.state)
            await self.page.locator('dialog[open]').wait_for(state='hidden')
            await asyncio.sleep(.3)
            labels=await self.page.locator('.utt-speaker-label, .legend-chip-name').all_text_contents()
            meeting=(await self.api('/api/meetings/'+(self.state['meetings'].get('enrollment_live') or self.state['meetings']['live'])))['body']
            segments=(meeting.get('transcript') or {}).get('segments',[])
            selected=[s for s in segments if s.get('speaker_entity_id')==body.get('speaker_id')]
            self.event({'rename_ack':{'name':name,'http':response.status,'speaker_id':body.get('speaker_id'),'enrollment':body.get('enrollment')}})
            await self.snapshot(5,f'-ack-{len(outcomes)+1}')
            outcomes.append({'name':name,'http':response.status,'speaker_id':body.get('speaker_id'),'enrollment':body.get('enrollment'),
                'rows_legend_updated':name in labels and old.strip() not in labels,
                'history_updated':bool(selected) and all(s['speaker']==name for s in selected),
                'export_updated':None})
            await self.snapshot(5,f'-rename-{len(outcomes)}')
        self.state['named']='E2E Morgan'
        return {'ok':all(x['http']==200 and x['rows_legend_updated'] and x['history_updated'] for x in outcomes),'renames':outcomes}

    async def enrollment(self):
        # Recovery of a naming probe that initially clicked provisional speech too early.
        # This is a separate naming fixture, never a repeat of row 4's latency measurement.
        await self.setup_live()
        ident=await self.start_live('enrollment_live')
        result=await self.rename()
        result['meeting']=ident
        await self.page.get_by_role('button',name='Stop and finalize',exact=True).click()
        await self.terminal(ident,240)
        return await self.finish_rename(result)

    async def finish_rename(self, result):
        # Same page, no reload; download after Stop; no product reload or injected state.
        path=await self.export('json','renamed-export')
        turns=json.loads(path.read_text())['turns']
        final=result['renames'][-1]
        matched=[t for t in turns if t['speaker_entity_id']==final['speaker_id']]
        final['export_updated']=bool(matched) and all(t['speaker_label']==final['name'] for t in matched)
        result['export_after_stop_without_reload']=final['export_updated']
        result['export']=path.name
        result['ok'] &= final['export_updated']
        return result

    async def live(self):
        meters=await self.setup_live(); ident=await self.start_live('live')
        try:
            await self.page.locator('.utt-text').first.wait_for(timeout=35000)
            first=time.monotonic()-self.started
        except Exception: first=None
        await self.snapshot(4,'-first-text')
        try:
            renamed=await self.rename()
            renamed['meeting']=ident
        except Exception as exc:
            renamed={'ok':False,'error':str(exc)[:1000]}
        await asyncio.sleep(max(0,18-(time.monotonic()-self.started)))
        stop=time.monotonic()
        await self.page.get_by_role('button',name='Stop and finalize',exact=True).click()
        meeting=await self.terminal(ident,240)
        stop_seconds=time.monotonic()-stop
        async def names_and_export():
            return await self.finish_rename(renamed) if renamed.get('renames') else renamed
        await self.check(5,names_and_export)
        await self.select(ident)
        segments=(meeting.get('transcript') or {}).get('segments',[])
        return {'ok':first is not None and first<=4 and meeting['status']=='completed' and bool(segments),'first_visible_seconds':first,
                'stop_to_terminal_seconds':stop_seconds,'meeting':ident,'status_received':meeting['status'],'segments':len(segments),
                'meters':meters,'artifact':f'meeting-{ident}.json'}

    async def export(self, fmt, prefix='export'):
        labels={'md':'Markdown (.md)','txt':'Plain text (.txt)','json':'JSON (.json)','srt':'SubRip (.srt)','vtt':'WebVTT (.vtt)'}
        await self.page.get_by_role('button',name='Export transcript',exact=True).click()
        async with self.page.expect_download() as pending:
            await self.page.get_by_role('menuitem',name=labels[fmt],exact=True).click()
        download=await pending.value; path=self.out/f'{prefix}.{fmt}'; await download.save_as(path)
        self.last_export_filename=download.suggested_filename
        self.event({'download':path.name,'suggested_filename':download.suggested_filename,'bytes':path.stat().st_size})
        return path

    async def exports(self):
        ident=self.state['meetings'].get('live') or self.state['meetings'].get('file') or self.state['meetings'].get('url')
        if not ident:
            assert not self.args.rows & {2,3,4}, 'Selected transcript-producing row did not create a meeting'
            disabled=await self.page.get_by_role('button',name='Export transcript',exact=True).is_disabled()
            return {'ok':disabled, 'scope':'empty_workspace', 'export_disabled':disabled, 'populated_export_not_exercised':True}
        await self.select(ident)
        results={}
        for fmt in ('md','txt','json','srt','vtt'):
            path=await self.export(fmt); text=path.read_text(); result={'bytes':path.stat().st_size,'artifact':path.name,'ok':bool(text.strip())}
            if fmt=='json':
                body=json.loads(text); result['turns']=len(body['turns']); result['ok'] &= bool(body['turns']) and json.loads(json.dumps(body))==body
            if fmt in ('srt','vtt'):
                cues=re.findall(r'(\d\d:\d\d:\d\d[.,]\d{3}) --> (\d\d:\d\d:\d\d[.,]\d{3})\n([^\n]+)',text)
                def seconds(t):
                    h,m,s=t.replace(',','.').split(':'); return int(h)*3600+int(m)*60+float(s)
                result.update(cues=len(cues),monotonic=all(seconds(a)<seconds(b) for a,b,_ in cues) and all(seconds(cues[i][0])<=seconds(cues[i+1][0]) for i in range(len(cues)-1)),speaker_prefixes=all(':' in s for _,_,s in cues))
                result['ok'] &= bool(cues) and result['monotonic'] and result['speaker_prefixes'] and (fmt!='vtt' or text.startswith('WEBVTT'))
            results[fmt]=result
        return {'ok':all(r['ok'] for r in results.values()),'formats':results}

    async def audio(self, ident, partial=False):
        await self.page.locator('[aria-label="Meeting history"]').get_by_role('button',name='Refresh',exact=True).click()
        link=self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"] [data-audio-download]')
        async with self.page.expect_download() as pending: await link.click()
        download=await pending.value; path=self.out/('interrupted.partial.mp3' if partial else 'download.mp3'); await download.save_as(path)
        data=probe(path); duration=float(data['format']['duration']); write(path.with_suffix('.ffprobe.json'),data)
        subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True)
        expected=float(probe(self.wav)['format']['duration'])
        return {'ok':data['streams'][0]['codec_name']=='mp3' and (download.suggested_filename.endswith('.partial.mp3') if partial else abs(duration-expected)/expected<=.05),
                'filename':download.suggested_filename,'duration':duration,'source_duration':expected,'artifact':path.name,'decodable':True}

    async def summaries(self):
        models=(await self.api('/api/llm/models'))['body']['data']
        if not models: return {'ok':False,'reason':'No configured relay models'}
        ident=self.state['meetings'].get('live') or self.state['meetings'].get('file') or self.state['meetings']['url']
        await self.select(ident)
        cancel=self.page.get_by_role('button',name='Cancel summary',exact=True)
        if await cancel.count():
            await cancel.click()  # Resume after a closed prior worker tab; explicit UI cancellation.
            self.event({'orphan_summary_cancelled':True})
        settings=self.page.locator('[aria-label="Browser AI settings"]')
        if not await settings.get_by_label('Relay model',exact=True).count(): await settings.get_by_role('button').first.click()
        attempts=[]
        for model in models[:2]:
            await settings.get_by_label('Relay model',exact=True).select_option(model['id'])
            await settings.get_by_role('button',name='Save on this browser',exact=True).click()
            async with self.page.expect_response(lambda r: r.request.method=='POST' and urlsplit(r.url).path.endswith('/summary')) as pending:
                await self.page.get_by_test_id('final-summary-generate').click()
            accepted=await (await pending.value).json()
            await self.page.locator(f'[data-summary-attempt="{accepted["attempt_id"]}"][data-summary-state="current"], [data-summary-attempt="{accepted["attempt_id"]}"][data-summary-state="failed"]').wait_for(timeout=390000)
            summary=(await self.api('/api/meetings/'+ident+'/summary'))['body']['summary']
            status=await self.page.locator('[aria-label="Final summary"] [role=status]').inner_text()
            path=self.out/f'summary-{model["upstream"]}.json'; write(path,summary)
            attempts.append({'requested_model':model['id'],'state':summary['state'],'error_code':summary.get('error_code'),
                'status_names_requested_model':model['id'] in status,'rendered':await self.page.locator('[data-final-summary]').count()>0,'artifact':path.name})
            await self.snapshot(9,'-'+model['upstream'])
        return {'ok':len(attempts)==2 and all(a['state']=='current' and a['status_names_requested_model'] and a['rendered'] for a in attempts),'attempts':attempts,
                'fallback_note':'Both configured models exercised directly; natural 502 fallback recorded if produced, never injected.'}

    async def history(self):
        ident=self.state['meetings'].get('file') or self.state['meetings'].get('live') or self.state['meetings'].get('url')
        if not ident:
            assert not self.args.rows & {2,3,4}, 'Selected transcript-producing row did not create a meeting'
            meetings=await self.api('/api/meetings')
            write(self.out/'empty-history.json',meetings)
            empty=await self.page.get_by_role('region',name='Meeting history',exact=True).get_by_text('No meetings yet.',exact=True).is_visible()
            return {'ok':empty and meetings['status']==200 and meetings['body']['meetings']==[], 'scope':'empty_workspace', 'empty_message_visible':empty, 'artifact':'empty-history.json', 'selected_header_not_exercised':True}
        await self.select(ident)
        meeting=(await self.api('/api/meetings/'+ident))['body']
        expected=await self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"] .history-card-title').inner_text()
        title=await self.page.locator('.session-title').inner_text(); mode=await self.page.locator('.session-chip').inner_text()
        box=await self.page.locator('#transcript-panel').bounding_box()
        visible=await self.page.locator('.session-meta').is_visible()
        geometry=await self.page.locator('.session-meta').bounding_box()
        return {'header_visible':visible,'header_box':geometry,'ok':visible and expected==title and mode==('Live' if meeting['mode']=='live' else 'File / URL') and box['y']>=-2 and box['y']<self.page.viewport_size['height'],
                'title_matches':expected==title,'mode':mode,'panel_box':box,'selected':ident}

    async def phone(self):
        ident=self.state['meetings'].get('live') or self.state['meetings'].get('file') or self.state['meetings'].get('url')
        if ident: await self.select(ident)
        await self.page.set_viewport_size({'width':400,'height':900})
        await self.page.get_by_role('link',name='Meeting history',exact=True).click()
        data=await self.page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,historyY:document.querySelector("#workspace-history").getBoundingClientRect().y})')
        await self.page.get_by_role('link',name='Files & URLs',exact=True).click()
        data['file_y']=await self.page.locator('#workspace-file').evaluate('e=>e.getBoundingClientRect().y')
        data['ok']=data['scroll']<=data['width'] and -2<=data['historyY']<900 and -2<=data['file_y']<900
        return data

    async def bank(self):
        # Independent capture fixture: a reused capture document can reject tab sharing
        # with InvalidStateError after Stop (retained in the original E2E audit).
        await self.page.close()
        self.page=self.attach(await self.context.new_page())
        await self.open()
        bank=self.page.locator('[aria-label="Private voiceprints"]'); await bank.get_by_role('button',name='Voiceprints',exact=True).click()
        await asyncio.sleep(.3)
        name=self.state.get('named','E2E Rowan'); enrolled=await bank.locator('[data-voiceprint-id]').filter(has_text=name).count()>0
        await self.snapshot(10,'-bank')
        await self.setup_live()
        # Timestamp the DOM mutation itself; locator retries add up to a polling interval.
        await self.page.evaluate('''name => {
          const result = window.__mossVoiceMatchTiming = {started: null, matched: null};
          const clicked = event => {
            if (event.target.closest('button')?.textContent.trim() === 'Start capture') {
              result.started = performance.now(); document.removeEventListener('click', clicked, true);
            }
          };
          document.addEventListener('click', clicked, true);
          const observer = new MutationObserver(() => {
            if (result.started === null) return;
            const found = [...document.querySelectorAll('.utt-speaker-label')]
              .some(el => el.getClientRects().length && el.textContent.includes(name));
            if (found) { result.matched = performance.now(); observer.disconnect(); }
          });
          observer.observe(document.body, {subtree:true, childList:true, characterData:true, attributes:true});
          window.__mossVoiceMatchCleanup = () => { observer.disconnect(); document.removeEventListener('click', clicked, true); };
        }''', name)
        ident=await self.start_live('second_live')
        try:
            await self.page.wait_for_function('window.__mossVoiceMatchTiming.matched !== null', timeout=30000)
            timing=await self.page.evaluate('window.__mossVoiceMatchTiming')
            latency=(timing['matched']-timing['started'])/1000
        except Exception: latency=None
        finally: await self.page.evaluate('window.__mossVoiceMatchCleanup()')
        trace='row-10-decoder-events.json'
        write(self.out/trace, (await self.api('/api/live/sessions/'+ident+'/events'))['body'])
        return {'ok':enrolled and latency is not None and latency<=FIRST_ENROLLED_LABEL_BOUND_SECONDS,'bound_seconds':FIRST_ENROLLED_LABEL_BOUND_SECONDS,'decoder_trace':trace,'expected_name':name,'bank_contains_name':enrolled,'recognition_seconds':latency,'measurement':'Start click to visible name DOM mutation','meeting':ident}

    async def interrupted(self):
        ident=self.state['meetings'].get('second_live')
        assert ident, 'Row 8 blocked: row 10 did not create a second live capture'
        await asyncio.sleep(max(0,12-(time.monotonic()-getattr(self,'started',0))))
        await self.snapshot(8,'-before-close')
        await self.page.close()  # Real capture-owner interruption; no server abort endpoint or host action.
        self.page=self.attach(await self.context.new_page()); await self.open()
        meeting=await self.terminal(ident,150)
        result=await self.audio(ident,True)
        result.update(meeting=ident,status_received=meeting['status']); result['ok'] &= meeting['status']=='interrupted'
        return result

    async def network_outages(self):
        """Row 13: real two-lane capture through short and long origin outages."""
        variants=[]
        origin=urlsplit(self.args.base)
        for seconds in (3,20):
            # Independent capture setups. Never navigate/reload within an outage case.
            await self.page.close()
            self.page=self.attach(await self.context.new_page())
            await self.open()
            trace=[]; tasks=set(); blocked=[]; restored=None
            def is_origin(url):
                parsed=urlsplit(url)
                return (parsed.scheme,parsed.netloc)==(origin.scheme,origin.netloc)
            async def observe(response):
                request=response.request; path=urlsplit(request.url).path
                if not is_origin(request.url): return
                entry={'t':time.monotonic(),'path':path,'status':response.status}
                if path.endswith(('/frames','/heartbeat')):
                    payload=request.post_data_json
                    entry.update({k:payload[k] for k in ('lane','sequence','device_epoch','capture_timestamp_ns','discontinuity') if k in payload})
                if path.endswith(('/frames','/snapshot','/heartbeat')):
                    try:
                        body=await asyncio.wait_for(response.json(),timeout=3)
                        entry['failure']=body.get('failure',body.get('detail')) if not response.ok else None
                        snapshot=body.get('snapshot') or {}; session=snapshot.get('session') or {}
                        entry.update(version=session.get('version'),committed=session.get('committed_samples'),unchanged=body.get('unchanged'))
                    except Exception: pass
                    trace.append(entry)
            def listener(response):
                task=asyncio.create_task(observe(response));tasks.add(task);task.add_done_callback(tasks.discard)
            async def drop(route):
                if is_origin(route.request.url):
                    blocked.append({'t':time.monotonic(),'path':urlsplit(route.request.url).path})
                    await route.abort('internetdisconnected')
                else: await route.continue_()
            self.page.on('response',listener)
            result={'outage_seconds':seconds}
            try:
                await self.setup_live();ident=await self.start_live(f'outage_{seconds}')
                result['meeting']=ident
                await self.page.wait_for_function('document.querySelectorAll(".utt-text").length > 0',timeout=35000)
                await asyncio.sleep(2)
                before=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body']['snapshot']['session']
                result['before']={k:before.get(k) for k in ('status','version','accepted_samples','committed_samples')}
                # Observe actual text changes without retaining spoken words or reloading.
                await self.page.evaluate('''() => {
                    window.__outageTextChanges=0;
                    const panel=document.querySelector('#transcript-panel');
                    let previous=panel.textContent;
                    window.__outageObserver=new MutationObserver(()=>{
                        const next=panel.textContent;
                        if(next!==previous){window.__outageTextChanges++;previous=next;}
                    });
                    window.__outageObserver.observe(panel,{subtree:true,childList:true,characterData:true});
                }''')
                started=time.monotonic()
                await self.context.route('**/*',drop)
                try: await asyncio.sleep(seconds)
                finally:
                    restored=time.monotonic()
                    result['phase_during_outage']=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')
                    await self.context.unroute('**/*',drop)
                result['restored_monotonic']=restored
                result['actual_outage_seconds']=restored-started
                result['blocked_requests']=len(blocked)
                result['origin_outage_verified']=all(any(x['path'].endswith('/'+route) for x in blocked) for route in ('frames','heartbeat','snapshot'))
                result['blocked_routes']=sorted({x['path'].rsplit('/',1)[-1] for x in blocked})
                await self.page.evaluate('window.__outageTextChanges=0')
                # Allow backlog drain and reader backoff; do not reload or recreate capture.
                for _ in range(30):
                    if all(any(x['t']>=restored and x['path'].endswith('/frames') and x.get('lane')==lane and x['status']==200 for x in trace) for lane in ('microphone','system')) and await self.page.evaluate('window.__outageTextChanges>0'):
                        break
                    if await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')=='terminal': break
                    await asyncio.sleep(1)
                result['phase_after_restore']=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')
                result['ui_status']=await self.page.locator('.capture-status').inner_text()
                result['text_changes_after_restore']=await self.page.evaluate('window.__outageTextChanges')
                result['frames_resumed']=all(any(x['t']>=restored and x['path'].endswith('/frames') and x.get('lane')==lane and x['status']==200 for x in trace) for lane in ('microphone','system'))
                result['first_frame_recovery_seconds']={lane:min((x['t']-restored for x in trace if x['t']>=restored and x['path'].endswith('/frames') and x.get('lane')==lane and x['status']==200),default=None) for lane in ('microphone','system')}
                result['first_snapshot_recovery_seconds']=min((x['t']-restored for x in trace if x['t']>=restored and x['path'].endswith('/snapshot') and x['status']==200),default=None)
                result['heartbeat_resumed']=any(x['t']>=restored and x['path'].endswith('/heartbeat') and x['status']==200 for x in trace)
                heartbeat_times=sorted(x['t'] for x in trace if x['path'].endswith('/heartbeat') and x['status']==200)
                result['maximum_heartbeat_gap_seconds']=max((b-a for a,b in zip(heartbeat_times,heartbeat_times[1:])),default=None)
                result['polling_resumed']=any(x['t']>=restored and x['path'].endswith('/snapshot') and x['status']==200 for x in trace)
                result['sequence_continuity']={}
                for lane in ('microphone','system'):
                    frames=[x for x in trace if x['path'].endswith('/frames') and x.get('lane')==lane and x['status']==200]
                    result['sequence_continuity'][lane]=bool(frames) and all(b['sequence'] in (a['sequence'],a['sequence']+1) and b['device_epoch']==a['device_epoch'] and (b['sequence']==a['sequence'] or b['capture_timestamp_ns']>a['capture_timestamp_ns']) for a,b in zip(frames,frames[1:]))
                result['frame_errors']=[x['failure'] for x in trace if x['path'].endswith('/frames') and x['status']==409]
                stop=self.page.get_by_role('button',name='Stop and finalize',exact=True)
                if await stop.count(): await stop.click()
                meeting=await self.terminal(ident,240)
                live=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body'].get('snapshot') or {}
                session=live.get('session') or {}
                result.update(status_received=meeting['status'],finalization_status=session.get('finalization_status'),failure_reason=session.get('failure_reason'))
                await self.page.locator('[aria-label="Meeting history"]').get_by_role('button',name='Refresh',exact=True).click()
                card=self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"]')
                result['history_preserved']=await card.count()==1
                async with self.page.expect_download() as pending: await card.locator('[data-audio-download]').click()
                download=await pending.value;path=self.out/f'outage-{seconds}.mp3';await download.save_as(path)
                duration=float(probe(path)['format']['duration'])
                subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True)
                result.update(audio_seconds=duration,audio_preserved=duration>0,partial_audio=download.suggested_filename.endswith('.partial.mp3'))
                survived=(result['phase_during_outage']=='active' and result['phase_after_restore']=='active' and result['frames_resumed'] and result['heartbeat_resumed'] and result['polling_resumed'] and result['text_changes_after_restore']>0 and all(result['sequence_continuity'].values()) and not result['frame_errors'] and meeting['status']=='completed' and result['finalization_status']=='final')
                graceful=(result['phase_after_restore']=='terminal' and bool(result['ui_status']) and result['ui_status']!='Failed to fetch' and 'Retrying' not in result['ui_status'] and meeting['status']!='active' and result['partial_audio'])
                result['recovery_feedback_clear']='Failed to fetch' not in result['ui_status'] and 'Retrying' not in result['ui_status']
                result['ok']=result['origin_outage_verified'] and (not survived or result['recovery_feedback_clear']) and result['history_preserved'] and result['audio_preserved'] and (survived or (seconds==20 and graceful))
                result['outcome']='survived' if survived else 'graceful_terminal' if graceful else 'failed'
            except Exception as exc:
                result.update(ok=False,error=str(exc)[:1600],exception=type(exc).__name__)
            finally:
                write(self.out/f'row-13-{seconds}s.json',result)
                await self.context.unroute('**/*',drop)
                self.page.remove_listener('response',listener)
                if tasks:
                    done,pending=await asyncio.wait(tasks,timeout=4)
                    for task in pending: task.cancel()
                    if pending: result.update(ok=False,trace_error='response observation did not finish')
                await self.page.evaluate('window.__outageObserver?.disconnect()')
                write(self.out/f'row-13-{seconds}s-trace.json',{'responses':trace,'blocked':blocked})
                write(self.out/f'row-13-{seconds}s.json',result)
                variants.append(result)
                await self.snapshot(13,f'-{seconds}s')
        return {'ok':all(v['ok'] for v in variants),'variants':variants}

    async def consecutive_meetings(self):
        """Row 14: three real captures in one document, no reload or replacement page."""
        await self.page.evaluate('window.__repeatDocument = "same-document"')
        cycles=[]
        for index in range(1,4):
            result={'cycle':index}
            try:
                assert await self.page.evaluate('window.__repeatDocument') == 'same-document'
                # Do not use Playwright foregrounding to hide native repeat-capture failures.
                await self.setup_live(foreground=False)
                result['pane_empty_before_start']=await self.page.locator('.utt-text').count()==0
                assert result['pane_empty_before_start'], 'Previous meeting transcript survived Reset capture'
                ident=await self.start_live(f'repeat_{index}')
                result['meeting']=ident
                await self.page.wait_for_function('document.querySelectorAll(".utt-text").length > 0',timeout=35000)
                await asyncio.sleep(max(0,8-(time.monotonic()-self.started)))
                result['active_phase']=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')
                await self.page.get_by_role('button',name='Stop and finalize',exact=True).click()
                meeting=await self.terminal(ident,240)
                await self.page.locator('[data-capture-phase="terminal"]').wait_for(timeout=30000)
                snapshot=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body']['snapshot']['session']
                events=(await self.api(f'/api/live/sessions/{ident}/events'))['body']
                write(self.out/f'row-14-cycle-{index}-events.json',events)
                first_frame=next(e for e in events['events'] if e['kind']=='frame_accepted')
                result['first_frame_sequence']=first_frame['payload']['sequence']
                await self.page.locator('[aria-label="Meeting history"]').get_by_role('button',name='Refresh',exact=True).click()
                history=await self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"]').count()==1
                # Verify the displayed export belongs to this capture, not the prior one.
                export=await self.export('json',f'row-14-cycle-{index}')
                exported=json.loads(export.read_text())
                result.update(status_received=meeting['status'],finalization_status=snapshot.get('finalization_status'),
                              history_present=history,export=export.name,export_filename=self.last_export_filename,
                              terminal_phase=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase'),
                              screenshot=await self.snapshot(14,f'-cycle-{index}'))
                result['ok']=(meeting['status']=='completed' and snapshot.get('finalization_status')=='final'
                              and history and result['first_frame_sequence']==0 and result['active_phase']=='active' and self.last_export_filename.startswith(f'transcript-{ident}-') and bool(exported.get('turns')))
            finally:
                cycles.append(result)
                write(self.out/'row-14-cycles.json',cycles)
        ids=[c['meeting'] for c in cycles]
        retained=all([await self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"]').count()==1 for ident in ids])
        return {'ok':all(c['ok'] for c in cycles) and len(set(ids))==3 and retained,
                'same_document':True,'all_in_history':retained,'cycles':cycles}

    async def run(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            write(self.out/'skip.json',{'status':'SKIP','reason':'Playwright not installed'}); return 77
        async with async_playwright() as p:
            try:
                chrome=browser_executable(p)
            except BrowserExecutableMissing as exc:
                write(self.out/'skip.json',{'status':'SKIP','reason':str(exc)})
                self.network.close()
                return 77
            server=None
            options=dict(headless=True,downloads_path=str(self.out/'browser-downloads'))
            if self.args.corpus:
                self.wav=(Path(self.args.corpus)/'audio.wav').resolve()
                self.reference=' '.join(json.loads(s)['text'] for s in (Path(self.args.corpus)/'reference.jsonl').read_text().splitlines())
                self.mp3=self.out/'source.mp3'
                if not self.mp3.exists(): subprocess.run(['ffmpeg','-v','error','-i',str(self.wav),'-ac','1','-ar','16000','-codec:a','libmp3lame',str(self.mp3)],check=True)
                # A separate real browser tab supplies shared audio; no media API replacement.
                (self.out/'source.html').write_text('<title>MOSS E2E Audio Source</title><audio src="source.wav" controls autoplay loop></audio>')
                wavlink=self.out/'source.wav'
                if not wavlink.exists(): wavlink.symlink_to(self.wav)
                server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(self.out)))
                threading.Thread(target=server.serve_forever,daemon=True).start(); self.media=f'http://127.0.0.1:{server.server_port}'
                options.update(ignore_default_args=['--mute-audio'],args=['--use-fake-device-for-media-stream','--auto-accept-camera-and-microphone-capture',f'--use-file-for-fake-audio-capture={self.wav}','--auto-select-tab-capture-source-by-title=MOSS E2E Audio Source','--autoplay-policy=no-user-gesture-required'])
            self.resumed=False
            browser=await p.chromium.launch(executable_path=str(chrome),channel='chromium',**options)
            self.context=await browser.new_context(ignore_https_errors=self.args.allow_local_self_signed,accept_downloads=True,viewport={'width':1440,'height':1100})
            try:
                self.context.set_default_timeout(12000)
                self.page=self.attach(await self.context.new_page())
                if server:
                    self.source=await self.context.new_page(); await self.source.goto(self.media+'/source.html')
                    await self.source.locator('audio').evaluate('a=>a.play()'); await self.page.bring_to_front()
                rows=self.args.rows
                if 1 in rows: await self.check(1,self.bootstrap)
                else: await self.open()
                for n,fn in [(2,self.file),(3,lambda:self.file(True)),(4,self.live),(5,self.enrollment),(6,self.exports),(7,lambda:self.audio(self.state['meetings']['file'])),(9,self.summaries),(11,self.history),(12,self.phone),(10,self.bank),(8,self.interrupted),(13,self.network_outages),(14,self.consecutive_meetings)]:
                    if n in rows and not (n==5 and 4 in rows): await self.check(n,fn)
                for n in rows:
                    if str(n) not in self.state['rows']: self.state['rows'][str(n)]={'status':'FAIL','reason':'Prerequisite not reached'}
                write(self.out/'results.json',self.state)
                return int(any(r['status']!='PASS' for r in self.state['rows'].values()))
            finally:
                if self.pending: await asyncio.gather(*self.pending,return_exceptions=True)
                await self.context.close(); await browser.close()
                if server: server.shutdown()
                self.network.close()


def parse_args(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='https://127.0.0.1:17861')
    parser.add_argument('--new-workspace',action='store_true',help=argparse.SUPPRESS)  # Every run is now fresh.
    parser.add_argument('--allow-local-self-signed',action='store_true',help='Bypass TLS only for an isolated loopback test stack')
    parser.add_argument('--corpus',help='Directory containing audio.wav and reference.jsonl; required for audio rows')
    parser.add_argument('--output',required=True,help='New or empty evidence directory')
    parser.add_argument('--rows',default=','.join(map(str,range(1,15))),help='Comma-separated row numbers 1–14; prerequisites must also be selected')
    args=parser.parse_args(argv)
    try:
        args.rows=set(map(int,args.rows.split(',')))
        if not args.rows or not args.rows<=set(range(1,15)): raise ValueError()
    except ValueError: parser.error('--rows must contain numbers 1–14')
    origin=urlsplit(args.base)
    if origin.scheme not in ('http','https') or not origin.hostname or origin.username or origin.password:
        parser.error('--base must be an HTTP(S) origin without credentials')
    if args.allow_local_self_signed and origin.hostname not in ('localhost','127.0.0.1','::1'):
        parser.error('--allow-local-self-signed is restricted to loopback')
    if args.rows-{1,6,11,12} and not args.corpus:
        parser.error('--corpus is required for audio rows')
    for row,required in {5:{4},7:{2},8:{4,10},10:{4}}.items():
        if row in args.rows and not required<=args.rows: parser.error(f'Row {row} requires rows {sorted(required)}')
    if 9 in args.rows and not args.rows & {2,3,4}:
        parser.error('Row 9 requires a transcript from row 2, 3, or 4')
    return args


def summary(state, rows):
    statuses=[(n,state['rows'].get(str(n),{}).get('status','FAIL')) for n in sorted(rows)]
    passed=sum(status=='PASS' for _,status in statuses)
    return ' | '.join(f'{n}:{status}' for n,status in statuses)+f' | total {passed}/{len(rows)} PASS, {len(rows)-passed} FAIL'


def main(argv=None):
    args=parse_args(argv)
    harness=Harness(args)
    try:
        return asyncio.run(harness.run())
    finally:
        print(summary(harness.state,args.rows),flush=True)


if __name__=='__main__':
    raise SystemExit(main())
