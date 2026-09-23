"""PROTOTYPE / standing WP5 browser bench. Real product, isolated scratch persistence.
Question: which adversarial sequences violate lifecycle/durability contracts?
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/browser-stress/run.py all
Start stack.py on 17865 and own decoder forward 18105 first. No microphone evidence.
"""
from __future__ import annotations
import argparse, asyncio, functools, http.server, json, os, re, shutil, signal, sqlite3, subprocess, sys, tempfile, threading, time
from difflib import SequenceMatcher
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tests.e2e.verify_workspace import Harness, QuietHandler
from tests.e2e.export_oracle import compare_export
from tests.phase2.browser_support import browser_executable
from playwright.async_api import async_playwright
CORPUS=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s')
TRANSCRIPT_EXPORT_FORMATS=('md','txt','json','srt','vtt')
PREDICATES={
1:'Two Stop events within 200ms yield one terminal meeting, no UI error.',
2:'Stop at 1s before text yields terminal truth and permits a new capture.',
3:'Actual hidden tab for 60s keeps accepted frames and text advancing.',
4:'3s and 20s live-route outages recover or visibly fail; lease closes abandoned work.',
5:'Reshare replaces track, frames continue, exactly one meeting.',
6:'Reload leaves same history row terminal after 30s lease; no active orphan.',
7:'Same-profile tabs converge to unique identical meeting IDs.',
8:'MP3 and long name succeed; invalid/empty files visibly fail; two uploads complete.',
9:'Unreachable, 404, non-media URLs visibly explain failure.',
10:'Five oracle-equal exports from live and file; audio decodes; interrupted download retries.',
11:'Rename updates all selected-speaker labels, enrolls voiceprint, persists through reload/export.',
12:'60 history fixtures render after reload at 400px, two Refresh controls, no overflow.',
13:'No-provider summary is disabled or explains setup, with zero provider POSTs.',
14:'Own idle server restart preserves credential, history and transcripts.',
15:'Actual headed hidden tab for 60s advances frames and words, restores, completes.',
16:'25s outage recovers without losing acknowledged content; 35s expires truthfully and permits new capture.'}


def retain_case_10_artifacts(out, mode, meeting, exports):
    if set(exports)!=set(TRANSCRIPT_EXPORT_FORMATS):
        raise ValueError('Case 10 requires exactly five transcript exports')
    target=Path(out)/'case-10-artifacts'/mode
    target.mkdir(parents=True,exist_ok=True)
    (target/'meeting.json').write_text(json.dumps(meeting,indent=2)+'\n')
    for fmt in TRANSCRIPT_EXPORT_FORMATS:
        path=exports[fmt]
        shutil.copyfile(path,target/f'transcript.{fmt}')


class Bench(Harness):
    def __init__(self,out,base='https://127.0.0.1:17865',microphone_file=None,headed=False,lease_seconds=(25,35),runtime=None):
        super().__init__(SimpleNamespace(output=out,base=base))
        self.runtime=runtime;self.stack_proc=None
        self.microphone_file=microphone_file;self.headed=headed;self.lease_seconds=lease_seconds
        self.errors=[];self.failures=[];self.frames=[];self.posts=[];self.results={};self.case=0
    def attach(self,page):
        super().attach(page)
        page.on('pageerror',lambda e:self.errors.append(str(e)))
        page.on('console',lambda m:self.errors.append(m.text) if m.type=='error' else None)
        page.on('requestfailed',lambda r:self.failures.append({'path':urlsplit(r.url).path,'failure':r.failure}))
        page.on('request',lambda r:self.posts.append(urlsplit(r.url).path) if r.method=='POST' else None)
        page.on('response',lambda r:self.frames.append({'t':time.monotonic(),'status':r.status,'lane':(r.request.post_data_json or {}).get('lane'),'sequence':(r.request.post_data_json or {}).get('sequence')}) if urlsplit(r.url).path.endswith('/frames') else None)
        return page
    async def state_at(self,action):
        rows=(await self.api('/api/meetings'))['body'].get('meetings',[])
        snapshots=[]
        for row in rows:
            if row['mode']!='live':continue
            value=await self.api('/api/live/sessions/'+row['id']+'/snapshot')
            snap=value['body'].get('snapshot') or {}
            sess=snap.get('session') or {}
            snapshots.append({'id':row['id'],'http':value['status'],'session':{k:v for k,v in sess.items() if isinstance(v,(int,float,bool)) or k in ('status','finalization_status')},'fields':list(snap)})
        record={'case':self.case,'action':action,'t':time.monotonic(),'phase':await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase'),'history':[{'id':r['id'],'status':r['status'],'mode':r['mode']} for r in rows], 'rendered_rows':await self.page.locator('.account-history-panel [data-meeting-card]').count(),'transcript_words':sum(len(t.split()) for t in await self.page.locator('.utt-text').all_text_contents()),'snapshots':snapshots,'console_errors':self.errors,'network_failures':self.failures,'accepted_frames':sum(f['status']==200 for f in self.frames)}
        with (self.out/'states.jsonl').open('a') as f:f.write(json.dumps(record)+'\n')
        print(json.dumps(record),flush=True)
        return record
    async def fresh(self):
        if self.page:await self.page.close()
        self.page=self.attach(await self.context.new_page());await self.open()
    async def setup_live(self):
        await self.page.bring_to_front()
        await self.source.evaluate('document.querySelector("audio").currentTime=0')
        await self.page.get_by_label('Listening setup',exact=True).select_option('headphones')
        await self.page.get_by_role('button',name='Enable microphone',exact=True).click()
        await self.page.wait_for_function('document.querySelector(".capture-status")?.textContent.includes("Microphone connected")')
        await self.page.get_by_role('button',name='Share audio',exact=True).click()
        await self.page.get_by_role('button',name='Start capture',exact=True).wait_for(timeout=20000)
    async def begin(self):
        await self.fresh();await self.setup_live();ident=await self.start_live('live');await self.state_at('start');return ident
    async def stop(self,ident):
        btn=self.page.get_by_role('button',name='Stop and finalize',exact=True)
        if await btn.count() and await btn.is_enabled():await btn.click()
        meeting=await self.terminal(ident,90);await self.state_at('stop-terminal');return meeting
    async def case_live(self,n):
        ident=await self.begin(); data={'meeting':ident}
        if n==1:
            await asyncio.sleep(8)
            times=await self.page.get_by_role('button',name='Stop and finalize',exact=True).evaluate('(b)=>{const t=[performance.now()];b.click();t.push(performance.now());b.click();return t}')
            m=await self.terminal(ident,90)
            await self.page.locator('[data-capture-phase=terminal]').wait_for(timeout=30000)
            s=await self.state_at('double-stop');data.update(click_gap_ms=times[1]-times[0],terminal_status=m['status'],ok=m['status']=='completed' and s['phase']=='terminal' and 'failed' not in (await self.page.locator('.capture-status').inner_text()).lower())
        elif n==2:
            await asyncio.sleep(max(0,1-(time.monotonic()-self.started)))
            data['stop_at_seconds']=time.monotonic()-self.started;data['words_before_stop']=await self.page.locator('.utt-text').count()
            m=await self.stop(ident); await self.page.get_by_role('button',name='Reset capture',exact=True).click();await self.state_at('reset')
            await self.setup_live();second=await self.start_live('recovery');await self.state_at('new-capture-same-page');await asyncio.sleep(1);second_meeting=await self.stop(second)
            data.update(terminal_status=m['status'],recovery_status=second_meeting['status'],ok=m['status'] in ('completed','failed','interrupted') and second_meeting['status']=='completed')
        elif n==3:
            await asyncio.sleep(8);before=await self.state_at('before-background');await self.source.bring_to_front()
            hidden=await self.page.evaluate('document.hidden');start=time.monotonic();await asyncio.sleep(60)
            after=await self.state_at('after-background');accepted=[f['t'] for f in self.frames if f['status']==200 and f['t']>=start]
            gaps=[b-a for a,b in zip(accepted,accepted[1:])]
            data.update(hidden=hidden,blocked=None if hidden else 'Headless Chromium remained visible; hidden-tab behavior unmeasured',seconds=time.monotonic()-start,frames=len(accepted),max_gap=max(gaps,default=None),word_delta=after['transcript_words']-before['transcript_words'])
            await self.page.bring_to_front();await self.stop(ident);data['ok']=hidden and len(accepted)>0 and data['word_delta']>0
        elif n==5:
            await asyncio.sleep(8);before=len(self.frames);await self.page.get_by_role('button',name='Reshare audio',exact=True).click();await self.state_at('reshare');await asyncio.sleep(8)
            data['frames_after_reshare']=len(self.frames)-before;m=await self.stop(ident);data['ok']=data['frames_after_reshare']>0 and m['status']=='completed'
        elif n==6:
            await asyncio.sleep(8);await self.page.reload();await self.open();await self.state_at('reload');m=await self.terminal(ident,65);await self.state_at('lease-terminal');data.update(terminal_status=m['status'],ok=m['status']=='interrupted')
        return data
    async def outage(self):
        variants=[]
        for seconds in (3,20):
            ident=await self.begin();await asyncio.sleep(8)
            async def drop(route):await route.abort('internetdisconnected')
            await self.page.route('**/api/live/**',drop);await asyncio.sleep(seconds);await self.page.unroute('**/api/live/**',drop)
            restored=time.monotonic();await self.state_at(f'network-restored-{seconds}');await asyncio.sleep(8)
            phase=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase');status=await self.page.locator('.capture-status').inner_text()
            recovered=any(f['status']==200 and f['t']>restored for f in self.frames)
            m=await self.stop(ident);variants.append({'seconds':seconds,'recovered_frames':recovered,'phase':phase,'visible_status':status,'terminal':m['status'],'ok':recovered or (phase=='terminal' and any(x in status.lower() for x in ('fail','lost','error','disconnect')))})
        return {'variants':variants,'ok':all(v['ok'] for v in variants)}
    async def hidden_headed(self):
        """WP14 prototype: observe native visibility; never spoof browser state."""
        ident=await self.begin();await asyncio.sleep(8)
        before=await self.state_at('before-hidden');attempts=[]
        cdp=await self.context.new_cdp_session(self.page)
        window=await cdp.send('Browser.getWindowForTarget')
        await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'minimized'}})
        await asyncio.sleep(1)
        hidden=await self.page.evaluate('document.hidden')
        attempts.append({'method':'minimize','hidden':hidden})
        other=None
        if not hidden:
            other=await self.context.new_page();await other.goto('about:blank');await other.bring_to_front();await asyncio.sleep(1)
            hidden=await self.page.evaluate('document.hidden');attempts.append({'method':'second-tab-front','hidden':hidden})
        start=time.monotonic();samples=[]
        if hidden:
            for _ in range(60):
                samples.append({'elapsed':time.monotonic()-start,'hidden':await self.page.evaluate('document.hidden')})
                await asyncio.sleep(1)
        end=time.monotonic();after=await self.state_at('after-hidden')
        cadence={}
        for lane in ('system','microphone'):
            times=[f['t'] for f in self.frames if f['status']==200 and f['lane']==lane and start<=f['t']<=end]
            points=[start,*times,end]
            cadence[lane]={'frames':len(times),'max_gap_seconds':max(b-a for a,b in zip(points,points[1:]))}
        await cdp.send('Browser.setWindowBounds',{'windowId':window['windowId'],'bounds':{'windowState':'normal'}})
        if other:await other.close()
        await self.page.bring_to_front();await asyncio.sleep(3)
        restored=await self.state_at('restored-visible');m=await self.stop(ident);await cdp.detach()
        recovery={lane:sum(f['status']==200 and f['lane']==lane and f['t']>end for f in self.frames) for lane in cadence}
        return {'attempts':attempts,'visibility_samples':samples,'hidden_seconds':end-start,'cadence':cadence,
                'word_delta':after['transcript_words']-before['transcript_words'],'recovery_frames':recovery,
                'restored_visible':not await self.page.evaluate('document.hidden'),'terminal':m['status'],
                'blocked':None if hidden else 'Neither native minimization nor another foreground tab yielded document.hidden',
                'ok':hidden and all(s['hidden'] for s in samples) and end-start>=60 and all(v['frames']>0 for v in cadence.values()) and after['transcript_words']>before['transcript_words'] and all(recovery.values()) and m['status']=='completed'}

    async def lease_outages(self):
        """WP14 prototype: real client, route outages spanning the configured lease."""
        variants=[]
        for seconds in self.lease_seconds:
            ident=await self.begin();await asyncio.sleep(10)
            before=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body']['snapshot']['session']
            rows=before.get('effective_transcript') or []
            acknowledged=[(c['span_id'],c['transcript']) for c in before.get('committed',[])]
            words=lambda rows:re.findall(r"[a-z0-9]+",' '.join(r.get('text','') for r in rows).lower())
            old_words=words(rows);blocked=[]
            async def drop(route):
                blocked.append({'elapsed':time.monotonic()-start,'route':urlsplit(route.request.url).path.rsplit('/',1)[-1]})
                await route.abort('internetdisconnected')
            start=time.monotonic();await self.page.route('**/api/live/**',drop)
            try:await asyncio.sleep(seconds)
            finally:await self.page.unroute('**/api/live/**',drop)
            restored=time.monotonic();await self.state_at(f'lease-restored-{seconds}')
            await asyncio.sleep(10)
            phase=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')
            status=await self.page.locator('.capture-status').inner_text()
            resumed={lane:any(f['status']==200 and f['lane']==lane and f['t']>restored for f in self.frames) for lane in ('system','microphone')}
            stop_started=time.monotonic();m=await self.stop(ident)
            stop_seconds=time.monotonic()-stop_started
            final=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body']['snapshot']['session']
            new_words=words((m.get('transcript') or {}).get('segments',[]))
            matcher=SequenceMatcher(None,old_words,new_words,autojunk=False)
            retained=sum(match.size for match in matcher.get_matching_blocks())
            v={'seconds':seconds,'actual_seconds':restored-start,'meeting':ident,'blocked_requests':len(blocked),
               'blocked_routes':sorted({r['route'] for r in blocked}),'phase_after_restore':phase,'ui_status':status,
               'resumed_frames':resumed,'terminal':m['status'],'failure_reason':final.get('failure_reason'),
               'accepted_samples_before':before.get('accepted_samples'),'accepted_samples_after':final.get('accepted_samples'),
               'published_words_before':len(old_words),'stop_seconds':stop_seconds,
               'acknowledged_commits_before':len(acknowledged),'acknowledged_commits_preserved':acknowledged==[(c['span_id'],c['transcript']) for c in final.get('committed',[])][:len(acknowledged)],'saved_words_after':len(new_words),'ordered_words_retained':retained,
               'words_removed_or_revised':len(old_words)-retained}
            if seconds==25:
                v['ok']=all(resumed.values()) and phase=='active' and m['status']=='completed' and v['acknowledged_commits_preserved'] and len(acknowledged)>0 and len(old_words)>0
            else:
                explained='Recording interrupted' in status and 'Reset capture' in status
                v['truthful_failure']=m['status'] in ('failed','interrupted') and phase=='terminal' and explained
                # Same document; no reload or replacement page hides broken reset.
                await self.page.locator('[data-capture-phase=terminal]').wait_for(timeout=30000)
                await self.page.get_by_role('button',name='Reset capture',exact=True).click()
                await self.setup_live();second=await self.start_live('lease-recovery');await asyncio.sleep(3)
                recovery=await self.stop(second);v['new_capture_status']=recovery['status']
                v['ok']=v['truthful_failure'] and recovery['status']=='completed'
            variants.append(v);print('LEASE_VARIANT',json.dumps(v),flush=True)
        return {'variants':variants,'ok':all(v['ok'] for v in variants)}

    async def tabs(self):
        other=self.attach(await self.context.new_page());await other.goto(self.args.base);await other.locator('[data-history-boot="ready"]').wait_for()
        a=(await self.api('/api/meetings'))['body']['meetings'];b=await other.evaluate('fetch("/api/meetings").then(r=>r.json()).then(v=>v.meetings)')
        ids=lambda rows:sorted(r['id'] for r in rows)
        await self.state_at('second-tab');await other.close();return {'rows':len(a),'ok':ids(a)==ids(b) and len(ids(a))==len(set(ids(a)))}
    async def upload(self,files=None,url=None):
        await self.page.locator('input[type=file]').set_input_files(files or [])
        await self.page.locator('textarea[name=urls]').fill(url or '')
        before={r['id'] for r in (await self.api('/api/meetings'))['body']['meetings']}
        await self.page.get_by_role('button',name='Transcribe files and URLs',exact=True).click();await asyncio.sleep(1)
        new=[r for r in (await self.api('/api/meetings'))['body']['meetings'] if r['id'] not in before]
        done=[await self.terminal(r['id'],100) for r in new]
        await self.state_at('upload-terminal')
        await asyncio.sleep(2)  # Existing upload follower polls every 1.5s.
        visible=' '.join(await self.page.locator('[data-file-upload=results] li span').all_text_contents())
        return done,visible
    async def concurrent_uploads(self):
        pages=[self.attach(await self.context.new_page()) for _ in range(2)]
        async def prepare(page):
            await page.goto(self.args.base);await page.locator('[data-boot="ready"]').wait_for()
            await page.locator('input[type=file]').set_input_files(str(self.mp3))
        await asyncio.gather(*(prepare(page) for page in pages))
        starts=[]
        async def submit(page):
            async with page.expect_response(lambda r:urlsplit(r.url).path=='/api/meetings/file' and r.request.method=='POST') as pending:
                starts.append(time.monotonic())
                await page.get_by_role('button',name='Transcribe files and URLs',exact=True).click()
            response=await pending.value
            assert response.status==201
            return (await response.json())['id']
        try:
            ids=await asyncio.gather(*(submit(page) for page in pages))
            self.concurrent_start_gap_ms=abs(starts[1]-starts[0])*1000
            done=[await self.terminal(ident,100) for ident in ids]
            await asyncio.sleep(2)
            visible=' '.join([' '.join(await page.locator('[data-file-upload=results] li span').all_text_contents()) for page in pages])
            await self.state_at('concurrent-two-tab-uploads')
            return done,visible
        finally:
            for page in pages:await page.close()
    async def files(self):
        outcomes=[]
        for name,payload,good in [('mp3',str(self.mp3),True),('non-audio',{'name':'not-audio.txt','mimeType':'text/plain','buffer':b'not audio'},False),('empty',{'name':'empty.mp3','mimeType':'audio/mpeg','buffer':b''},False),('long-name',{'name':'a'*240+'.mp3','mimeType':'audio/mpeg','buffer':self.mp3.read_bytes()},True),('concurrent',[{'name':'first.mp3','mimeType':'audio/mpeg','buffer':self.mp3.read_bytes()},{'name':'second.mp3','mimeType':'audio/mpeg','buffer':self.mp3.read_bytes()}],True)]:
            done,visible=await self.concurrent_uploads() if name=='concurrent' else await self.upload(payload)
            if good and done:self.state['meetings']['file']=done[0]['id']
            states=[r['status'] for r in done];reason=bool(visible) and visible != 'Processing failed. Open the meeting to inspect its saved result.' and any(x in visible.lower() for x in ('invalid','empty','not supported','failed','could not','cannot','error','must','unsupported'))
            outcomes.append({'variant':name,'statuses':states,'visible_reason':reason,'ui_message':visible,'ok':len(done)==(2 if name=='concurrent' else 1) and all(s=='completed' for s in states) if good else reason and all(s!='active' for s in states)})
        return {'variants':outcomes,'concurrent_start_gap_ms':self.concurrent_start_gap_ms,'ok':all(r['ok'] for r in outcomes)}
    async def urls(self):
        outcomes=[]
        for label,url in [('unreachable','http://127.0.0.1:1/no.mp3'),('404',self.media+'/missing.mp3'),('non-media',self.media+'/source.html')]:
            done,visible=await self.upload(url=url)
            reason=any(x in visible.lower() for x in ('unsupported','error:','unreachable','404','connection refused','resolve','not accepted:',
                'url media could not be acquired','the url returned a web page instead of direct media'))
            outcomes.append({'variant':label,'statuses':[r['status'] for r in done],'visible_reason':reason,'ui_message':visible,'ok':reason and all(r['status']!='active' for r in done)})
        return {'variants':outcomes,'ok':all(r['ok'] for r in outcomes)}
    async def downloads(self):
        outcomes=[]
        rows=(await self.api('/api/meetings'))['body']['meetings']
        for mode in ('live','file'):
            ident=next((r['id'] for r in rows if r['mode']==mode and r['status']=='completed'),None)
            assert ident,f'No completed {mode} fixture'
            await self.select(ident)
            meeting=(await self.api('/api/meetings/'+ident))['body']
            lanes=sorted({s.get('source_lane') for s in (meeting.get('transcript') or {}).get('segments',[]) if s.get('source_lane')})
            if mode=='live' and self.microphone_file:
                assert lanes==['microphone','system'],f'Expected two speech lanes, got {lanes}'
            exports={}
            for fmt in TRANSCRIPT_EXPORT_FORMATS:
                path=await self.export(fmt,mode)
                exports[fmt]=path
                outcomes.append({'mode':mode,'format':fmt,'bytes':path.stat().st_size,'lanes':lanes,**compare_export(fmt,path.read_text(),meeting)})
            retain_case_10_artifacts(self.out,mode,meeting,exports)
            url=f'/api/meetings/{ident}/audio/download'
            # Streaming browser fetch cancellation, then full retry and ffmpeg decode.
            cdp=await self.context.new_cdp_session(self.page)
            await cdp.send('Network.enable')
            await cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':0,'downloadThroughput':8192,'uploadThroughput':-1})
            cancelled=await self.page.evaluate('''async url=>{const c=new AbortController();const r=await fetch(url,{signal:c.signal});const reader=r.body.getReader();const first=await reader.read();c.abort();return {status:r.status,first_bytes:first.value?.length||0};}''',url)
            await cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':0,'downloadThroughput':-1,'uploadThroughput':-1});await cdp.detach()
            async with self.page.expect_download() as pending:
                await self.page.locator(f'.account-history-panel [data-meeting-card="{ident}"] [data-audio-download]').click()
            download=await pending.value;path=self.private/(mode+'-audio.mp3');await download.save_as(path)
            download_failure=await download.failure()
            expected=((await self.api('/api/meetings/'+ident))['body'].get('audio') or {}).get('byte_count')
            decoded=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True)
            outcomes.append({'mode':mode,'audio_bytes':path.stat().st_size,'expected_bytes':expected,'cancelled_after':cancelled['first_bytes'],'retry_failure':download_failure,'ok':download_failure is None and decoded.returncode==0 and path.stat().st_size==expected and 0<cancelled['first_bytes']<path.stat().st_size})
        await self.state_at('exports-audio');return {'checks':outcomes,'ok':all(r['ok'] for r in outcomes)}
    async def names(self):
        ident=await self.begin();await self.page.locator('.legend-chip:not([disabled])').first.wait_for(timeout=45000);await asyncio.sleep(5)
        await self.page.locator('.legend-chip:not([disabled])').first.click();await self.page.get_by_label('Display name',exact=True).fill('WP5 Speaker')
        await self.page.get_by_label('Save voiceprint',exact=True).check()
        async with self.page.expect_response(lambda r:'/speakers/' in r.url and r.request.method=='PUT') as pending:
            await self.page.get_by_role('button',name='Save name',exact=True).click()
        response=await pending.value;body=await response.json();await self.state_at('rename-enroll');await self.stop(ident);await self.page.reload();await self.open();await self.select(ident)
        json_export=(await self.export('json','names')).read_text()
        export=json.loads(json_export);matched=[t for t in export['turns'] if t['speaker_entity_id']==body.get('speaker_id')]
        meeting=(await self.api('/api/meetings/'+ident))['body']
        export_checks={fmt:compare_export(fmt,json_export if fmt=='json' else (await self.export(fmt,'renamed-'+fmt)).read_text(),meeting) for fmt in ('md','txt','json','srt','vtt')}
        labels=await self.page.locator('.utt-speaker-label,.legend-chip-name').all_text_contents()
        await self.page.get_by_role('region',name='Meeting history',exact=True).get_by_role('tab',name='Voiceprints',exact=True).click()
        await self.page.locator('[data-voiceprint-id]').filter(has_text='WP5 Speaker').first.wait_for()
        saved=await self.page.locator('[data-voiceprint-id]').filter(has_text='WP5 Speaker').count()
        await self.state_at('saved-voiceprint-after-reload')
        await self.page.get_by_role('region',name='Meeting history',exact=True).get_by_role('tab',name='Sessions',exact=True).click()
        return {'export_checks':export_checks,'voiceprints_after_reload':saved,'http':response.status,'enrollment':body.get('enrollment'),'matched_turns':len(matched),'labels_persisted':'WP5 Speaker' in labels,'ok':all(r['ok'] for r in export_checks.values()) and response.ok and bool(matched) and all(t['speaker_label']=='WP5 Speaker' for t in matched) and 'WP5 Speaker' in labels and body.get('enrollment') in ('enrolled','already_enrolled')}
    async def scale(self):
        # Explicit scratch DB fixture only: no decoder calls, no claim of 60 captures.
        rows=(await self.api('/api/meetings'))['body']['meetings'];ident=rows[0]['id']
        con=sqlite3.connect(self.runtime.state/'phase2.sqlite' if self.runtime else ROOT/'runs/wp5/state/phase2.sqlite')
        account=con.execute('SELECT account_id FROM meetings WHERE meeting_id=?',(ident,)).fetchone()[0]
        for i in range(max(0,60-len(rows))):
            con.execute("INSERT INTO meetings(account_id,meeting_id,mode,title,title_source,status,created_at_ms,updated_at_ms) VALUES(?,?, 'file',?,'automatic','failed',?,?)",(account,f'wp5-scale-{i}',f'WP5 fixture {i}',int(time.time()*1000),int(time.time()*1000)))
        con.commit();con.close();await self.page.reload();await self.open();await self.page.set_viewport_size({'width':400,'height':900});await self.page.get_by_role('link',name='Meeting history',exact=True).click()
        rendered=await self.page.locator('.account-history-panel [data-meeting-card]').count();await self.page.get_by_role('region',name='Meeting history',exact=True).get_by_role('tab',name='Voiceprints',exact=True).click();refresh=await self.page.get_by_role('button',name='Refresh',exact=True).count();width=await self.page.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');await self.state_at('60-fixtures-phone');await self.page.get_by_role('region',name='Meeting history',exact=True).get_by_role('tab',name='Sessions',exact=True).click()
        return {'rendered':rendered,'refresh':refresh,'sessions_refresh_including_hidden':await self.page.get_by_role('button',name='Refresh',exact=True,include_hidden=True).count(),**width,'ok':rendered==60 and refresh==2 and width['scroll']<=400}
    async def no_summary(self):
        rows=(await self.api('/api/meetings'))['body']['meetings'];ident=next(r['id'] for r in rows if r['status']=='completed');await self.select(ident)
        models=(await self.api('/api/llm/models'))['body'];assert not models.get('data'), 'Expected unconfigured relay'
        await self.page.get_by_test_id('final-summary-generate').click();await asyncio.sleep(.5)
        explained=await self.page.get_by_text('Configure Optional AI summaries above, then start your summary.',exact=True).is_visible();paid=[p for p in self.posts if 'chat/completions' in p]
        await self.state_at('no-provider-summary');return {'explained':explained,'provider_posts':len(paid),'ok':explained and not paid}
    async def restart(self):
        before=(await self.api('/api/meetings'))['body']['meetings'];cookies=await self.context.cookies();docs={r['id']:(await self.api('/api/meetings/'+r['id']))['body'].get('transcript') for r in before}
        # Restart only the stack launched by this bench, preserving state and runtime arguments.
        await self.page.close()
        if self.stack_proc is None:
            raise RuntimeError('Restart requires --stack-port and owned stack')
        self.stack_proc.terminate()
        await asyncio.to_thread(self.stack_proc.wait, 60)
        self.stack_log.close()
        self.start_stack()
        for _ in range(60):
            try:
                response=await self.context.request.get(self.args.base+'/');
                if response.ok:break
            except Exception:pass
            await asyncio.sleep(.5)
        self.page=self.attach(await self.context.new_page());await self.open();after=(await self.api('/api/meetings'))['body']['meetings'];newdocs={r['id']:(await self.api('/api/meetings/'+r['id']))['body'].get('transcript') for r in after};cookie_values=lambda values: sorted((c['name'],c['value'],c['domain'],c['path']) for c in values);same=cookie_values(await self.context.cookies())==cookie_values(cookies);await self.state_at('server-restart')
        return {'before':len(before),'after':len(after),'cookies_equal':same,'transcripts_equal':docs==newdocs,'ok':before==after and same and docs==newdocs}
    def start_stack(self):
        args=self.runtime
        self.stack_log=(args.state.parent/'server.log').open('ab')
        self.stack_proc=subprocess.Popen([sys.executable,'prototypes/streaming-diarization/draft-lane/run_local_stack.py',
            '--state',str(args.state),'--cert',str(args.cert),'--key',str(args.key),'--port',str(args.stack_port),
            '--manifest',str(args.manifest),'--vllm-base-url',args.decoder_url],cwd=ROOT,stdout=self.stack_log,stderr=subprocess.STDOUT)

    async def run_cases(self,cases):
        self.wav=CORPUS/'audio.wav';self.mp3=self.private/'source.mp3'
        subprocess.run(['ffmpeg','-v','error','-i',str(self.wav),'-t','12','-ac','1','-ar','16000',str(self.mp3)],check=True)
        (self.private/'source.wav').symlink_to(self.wav);(self.private/'source.html').write_text('<title>MOSS E2E Audio Source</title><audio src="source.wav" controls autoplay loop></audio>')
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(QuietHandler,directory=str(self.private)));threading.Thread(target=server.serve_forever,daemon=True).start();self.media=f'http://127.0.0.1:{server.server_port}'
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=str(browser_executable(p)),channel='chromium',headless=not self.headed,ignore_default_args=['--mute-audio']+(['--disable-backgrounding-occluded-windows','--disable-renderer-backgrounding','--disable-background-timer-throttling'] if self.headed else []),args=['--use-fake-device-for-media-stream','--auto-accept-camera-and-microphone-capture','--auto-select-tab-capture-source-by-title=MOSS E2E Audio Source','--autoplay-policy=no-user-gesture-required']+([f'--use-file-for-fake-audio-capture={self.microphone_file}'] if self.microphone_file else []))
            self.context=await browser.new_context(ignore_https_errors=True,accept_downloads=True,viewport={'width':1440,'height':1100});self.context.set_default_timeout(12000)
            self.page=self.attach(await self.context.new_page());self.source=await self.context.new_page();await self.source.goto(self.media+'/source.html');await self.source.locator('audio').evaluate('a=>a.play()');await self.open()
            try:
                for n in cases:
                    self.case=n;self.row=n;start=time.monotonic();self.errors=[];self.failures=[]
                    try:
                        fn={4:self.outage,7:self.tabs,8:self.files,9:self.urls,10:self.downloads,11:self.names,12:self.scale,13:self.no_summary,14:self.restart,15:self.hidden_headed,16:self.lease_outages}.get(n)
                        result=await fn() if fn else await self.case_live(n)
                        result['status']='BLOCKED' if result.get('blocked') else 'PASS' if result.get('ok') else 'FAIL'
                    except Exception as exc:
                        result={'status':'FAIL','exception':type(exc).__name__,'error':str(exc)[:1800]}
                    result.update(seconds=round(time.monotonic()-start,3),predicate=PREDICATES[n],console_errors=self.errors,network_failures=self.failures)
                    try:
                        await self.state_at('case-end')
                        shot=f'case-{n:02d}.png';await self.page.screenshot(path=str(self.out/shot),mask=[self.page.locator('.utt-text,.utt-speaker-label,.legend-chip-name,.history-card-title,[data-final-summary],input,textarea')]);result['screenshot']=shot
                    except Exception as exc:result['screenshot_error']=type(exc).__name__
                    self.results[str(n)]=result;(self.out/'campaign-results.json').write_text(json.dumps(self.results,indent=2)+'\n');print('RESULT',n,json.dumps(result),flush=True)
                    # No abandoned active work overlaps the next case.
                    if n in (1,2,3,4,5,6,11,15,16):
                        try:
                            ident=getattr(self,'last_live_meeting',None)
                            if ident:
                                m=(await self.api('/api/meetings/'+ident))['body']
                                if m.get('status')=='active':
                                    await self.page.close();self.page=self.attach(await self.context.new_page());await self.open();await self.terminal(ident,65)
                        except Exception:pass
                return int(any(r['status']!='PASS' for r in self.results.values()))
            finally:
                await self.context.close();await browser.close();server.shutdown();self.network.close();self._private.cleanup()


def main():
    os.environ.setdefault('TMPDIR',str(ROOT/'runs/wp5'))
    Path(os.environ['TMPDIR']).mkdir(parents=True,exist_ok=True)
    tempfile.tempdir=os.environ['TMPDIR']
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case')
    parser.add_argument('--output','--out',dest='output',default='evidence/mvpfix/wp5/base')
    parser.add_argument('--base',default='https://127.0.0.1:17865')
    parser.add_argument('--microphone-file',type=Path)
    parser.add_argument('--headed',action='store_true')
    parser.add_argument('--lease-seconds',type=int,nargs='+',choices=(25,35),default=[25,35])
    parser.add_argument('--stack-port',type=int)
    parser.add_argument('--state',type=Path,default=Path('runs/wp5/state'))
    parser.add_argument('--cert',type=Path,default=Path('runs/wp5/cert.pem'))
    parser.add_argument('--key',type=Path,default=Path('runs/wp5/key.pem'))
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--decoder-url',default='http://127.0.0.1:18105/v1')
    args=parser.parse_args()
    if args.stack_port in (7861,7862):parser.error('private stack port required')
    cases=list(range(1,17)) if args.case=='all' else [int(x) for x in args.case.split(',')]
    bench=Bench(args.output,args.base,args.microphone_file,args.headed,args.lease_seconds,args)
    try:
        if args.stack_port:
            if not args.manifest:parser.error('--manifest required with owned stack')
            bench.start_stack()
            import ssl,urllib.request
            for _ in range(120):
                if bench.stack_proc.poll() is not None:raise RuntimeError('Owned stack failed to start')
                try:
                    urllib.request.urlopen(args.base,context=ssl._create_unverified_context(),timeout=2).close()
                    break
                except OSError:time.sleep(1)
            else:raise RuntimeError('Owned stack readiness timeout')
        return asyncio.run(bench.run_cases(cases))
    finally:
        if bench.stack_proc:
            bench.stack_proc.terminate()
            try:bench.stack_proc.wait(timeout=30)
            except subprocess.TimeoutExpired:bench.stack_proc.kill();bench.stack_proc.wait()
            bench.stack_log.close()
if __name__=='__main__':raise SystemExit(main())
