"""Real UI/decoder verification. One pass; no decoder mocks or automatic decoder retries.
Run: .venv/bin/python tests/e2e/verify_workspace.py --corpus /path/to/mono_javier_intro_50s --output /tmp/moss-e2e-20260911
Requires ffmpeg/ffprobe and Playwright Chrome/Chromium. Exit 77 = browser unavailable.
Artifacts may contain corpus speech; report/network metadata never include transcript bodies.
--rows resumes selected checks using saved test cookies/settings; completed rows 2/3/4 never rerun.
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
        self.state = json.loads((self.out/'results.json').read_text()) if (self.out/'results.json').exists() else {'rows': {}, 'meetings': {}}
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

    async def setup_live(self):
        await self.page.get_by_role('link',name='Live / Transcript & export',exact=True).click()
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
                ident=found[0]['id']; self.state['meetings'][key]=ident; write(self.out/'results.json',self.state); return ident
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
            meeting=(await self.api('/api/meetings/'+self.state['meetings'].get('enrollment_live',self.state['meetings']['live'])))['body']
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
        self.event({'download':path.name,'suggested_filename':download.suggested_filename,'bytes':path.stat().st_size})
        return path

    async def exports(self):
        ident=self.state['meetings'].get('live') or self.state['meetings']['file']; await self.select(ident)
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
        ident=self.state['meetings'].get('live') or self.state['meetings']['file']
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
        ident=self.state['meetings'].get('file') or self.state['meetings']['live']; await self.select(ident)
        meeting=(await self.api('/api/meetings/'+ident))['body']
        expected=await self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"] .history-card-title').inner_text()
        title=await self.page.locator('.session-title').inner_text(); mode=await self.page.locator('.session-chip').inner_text()
        box=await self.page.locator('#transcript-panel').bounding_box()
        visible=await self.page.locator('.session-meta').is_visible()
        geometry=await self.page.locator('.session-meta').bounding_box()
        return {'header_visible':visible,'header_box':geometry,'ok':visible and expected==title and mode==('Live' if meeting['mode']=='live' else 'File / URL') and box['y']>=-2 and box['y']<self.page.viewport_size['height'],
                'title_matches':expected==title,'mode':mode,'panel_box':box,'selected':ident}

    async def phone(self):
        ident=self.state['meetings'].get('live') or self.state['meetings'].get('file')
        if ident: await self.select(ident)
        await self.page.set_viewport_size({'width':400,'height':900})
        await self.page.get_by_role('link',name='Meeting history',exact=True).click()
        data=await self.page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth,historyY:document.querySelector("#workspace-history").getBoundingClientRect().y})')
        await self.page.get_by_role('link',name='Files & URLs',exact=True).click()
        data['file_y']=await self.page.locator('#workspace-file').evaluate('e=>e.getBoundingClientRect().y')
        data['ok']=data['scroll']<=data['width'] and -2<=data['historyY']<900 and -2<=data['file_y']<900
        return data

    async def bank(self):
        await self.page.reload(); await self.page.locator('[data-boot=ready]').wait_for()
        bank=self.page.locator('[aria-label="Private voiceprints"]'); await bank.get_by_role('button',name='Voiceprints',exact=True).click()
        await asyncio.sleep(.3)
        name=self.state.get('named','E2E Rowan'); enrolled=await bank.locator('[data-voiceprint-id]').filter(has_text=name).count()>0
        await self.snapshot(10,'-bank')
        await self.setup_live(); ident=await self.start_live('second_live')
        try:
            await self.page.locator('.utt-speaker-label').filter(has_text=name).first.wait_for(timeout=30000)
            latency=time.monotonic()-self.started
        except Exception: latency=None
        return {'ok':enrolled and latency is not None and latency<=3,'expected_name':name,'bank_contains_name':enrolled,'recognition_seconds':latency,'meeting':ident}

    async def interrupted(self):
        ident=self.state['meetings'].get('second_live') or self.state['meetings']['enrollment_live']
        await asyncio.sleep(max(0,12-(time.monotonic()-getattr(self,'started',0))))
        await self.snapshot(8,'-before-close')
        await self.page.close()  # Real capture-owner interruption; no server abort endpoint or host action.
        self.page=self.attach(await self.context.new_page()); await self.open()
        meeting=await self.terminal(ident,150)
        result=await self.audio(ident,True)
        result.update(meeting=ident,status_received=meeting['status']); result['ok'] &= meeting['status']=='interrupted'
        return result

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
            state_path=self.out/'browser-state.json'; self.resumed=state_path.exists()
            options=dict(headless=True,ignore_default_args=['--mute-audio'],downloads_path=str(self.out/'browser-downloads'),
                args=['--use-fake-device-for-media-stream','--auto-accept-camera-and-microphone-capture',f'--use-file-for-fake-audio-capture={self.wav}',
                      '--auto-select-tab-capture-source-by-title=MOSS E2E Audio Source','--autoplay-policy=no-user-gesture-required'])
            browser=await p.chromium.launch(executable_path=str(chrome),channel='chromium',**options)
            self.context=await browser.new_context(ignore_https_errors=True,accept_downloads=True,viewport={'width':1440,'height':1100},storage_state=str(state_path) if state_path.exists() else None)
            try:
                self.context.set_default_timeout(12000)
                if self.args.new_workspace:
                    await self.context.clear_cookies()
                    self.state.setdefault('previous_workspaces',[]).append(dict(self.state['meetings']))
                    self.state['meetings']={}
                self.page=self.attach(await self.context.new_page()); self.source=await self.context.new_page(); await self.source.goto(self.media+'/source.html')
                await self.source.locator('audio').evaluate('a=>a.play()'); await self.page.bring_to_front()
                rows=set(map(int,self.args.rows.split(','))) if self.args.rows else set(range(1,13))
                if 1 in rows: await self.check(1,self.bootstrap)
                else: await self.open()
                for n,fn in [(2,self.file),(3,lambda:self.file(True)),(4,self.live),(5,self.enrollment),(6,self.exports),(7,lambda:self.audio(self.state['meetings']['file'])),(9,self.summaries),(11,self.history),(12,self.phone),(10,self.bank),(8,self.interrupted)]:
                    if n in rows and not (n==5 and 4 in rows): await self.check(n,fn)
                for n in rows:
                    if str(n) not in self.state['rows']: self.state['rows'][str(n)]={'status':'FAIL','reason':'Prerequisite not reached'}
                write(self.out/'results.json',self.state)
                return int(any(r['status']!='PASS' for r in self.state['rows'].values()))
            finally:
                if self.pending: await asyncio.gather(*self.pending,return_exceptions=True)
                await self.context.close(); await browser.close(); server.shutdown(); self.network.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='https://127.0.0.1:17861')
    parser.add_argument('--new-workspace',action='store_true',help='Fresh test cookie after an external stack database reset; prior evidence retained')
    parser.add_argument('--corpus',required=True); parser.add_argument('--output',required=True); parser.add_argument('--rows')
    raise SystemExit(asyncio.run(Harness(parser.parse_args()).run()))
