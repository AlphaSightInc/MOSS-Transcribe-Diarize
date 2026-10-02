"""P74-RM: actual root page, shipped assets, actual capture routes; no providers."""
import asyncio
import argparse
import importlib.util
import json
import math
import contextlib
import runpy
import struct
import subprocess
import sys
import threading
import time
import traceback
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
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime

spec = importlib.util.spec_from_file_location('offline_audio', ROOT / 'prototypes/gemini-live/long-meeting/resume/run.py')
sys.path.insert(0, str(ROOT / 'prototypes/gemini-live/long-meeting/resume'))
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)
EV = Path('/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/resume-merge')
STATUS = EV.parents[2] / 'status/P74-RM-STATUS.md'
PORT = 18987
URL = f'https://127.0.0.1:{PORT}'
TITLE = 'P74 RI synthetic tab'
INIT = r"""(() => {
  window.measurement = {loadedAt:Date.now(), frames:[], resumes:[], heartbeats:[], clicks:[], media:[], creates:[], errors:[], summaries:[]};
  window.measuredStreams=[];
  window.measuredWorklets=[];
  const Worklet=window.AudioWorkletNode;
  window.AudioWorkletNode=class extends Worklet {
    constructor(ctx,name,options){
      super(ctx,name,options);
      const w={ctx,lane:options.processorOptions.lane,frameSamples:options.processorOptions.frameSamples,frames:[]};
      measuredWorklets.push(w);
      this.port.addEventListener('message',e=>{if(e.data.type==='frame')w.frames.push({startFrame:e.data.startFrame,at:Date.now(),contextFrame:ctx.currentTime*ctx.sampleRate});});
      this.port.start();
    }
  };
  const m=measurement;
  document.addEventListener('click',e=>m.clicks.push({at:Date.now(),label:e.target.closest('button')?.textContent || e.target.tagName}),true);
  const f=window.fetch.bind(window);
  window.fetch=async (url,init)=>{
    const path=String(url), method=init?.method || 'GET';
    if(path.includes('/summary') && method==='POST')m.summaries.push({path,body:JSON.parse(init.body)});
    const r=await f(url,init);
    if(path.endsWith('/frames')) {const b=JSON.parse(init.body);delete b.pcm_base64;m.frames.push({...b,status:r.status,at:Date.now(),header:init.headers['X-Moss-Capture-Instance']});}
    if(path.endsWith('/heartbeat'))m.heartbeats.push({status:r.status,at:Date.now()});
    if(path.endsWith('/resume') && r.ok && !JSON.parse(init.body).automatic && window.requirePartialTakeover){
      // K only: real response delayed 250 ms after BOTH new worklets start, creating
      // a measured partial chunk before adoption; server/protocol/messages unchanged.
      for(let i=0;i<400 && measuredWorklets.filter(w=>w.ctx.state==='running').length<2;i++)await new Promise(r=>setTimeout(r,5));
      await new Promise(r=>setTimeout(r,250));
    }
    if(path.endsWith('/resume'))m.resumes.push({request:JSON.parse(init.body),status:r.status,response:await r.clone().json(),at:Date.now(),
      worklets:measuredWorklets.filter(w=>w.ctx.state==='running').map(w=>({lane:w.lane,frameSamples:w.frameSamples,contextFrame:w.ctx.currentTime*w.ctx.sampleRate,last:w.frames.at(-1)}))});
    if(path.endsWith('/api/live/sessions') && method==='POST')m.creates.push({status:r.status,body:await r.clone().json()});
    if(r.status>=400 && /\/(frames|heartbeat|stop|abort)$/.test(path))m.errors.push({path,status:r.status,body:await r.clone().json()});
    return r;
  };
  const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia=async c=>{m.media.push({api:'microphone',c,active:navigator.userActivation.isActive});const s=await gum(c);measuredStreams.push(s);return s;};
  const gdm=navigator.mediaDevices.getDisplayMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getDisplayMedia=c=>{
    const row={api:'display',active:navigator.userActivation.isActive};m.media.push(row);
    if(sessionStorage.getItem('lt:session:reattach') && !m.clicks.some(x=>x.label.includes('Share Tab Audio Again'))){row.result='injected gesture refusal';return Promise.reject(new DOMException('contract: gesture required','NotAllowedError'));}
    return gdm(c).then(s=>{row.result='accepted';row.tracks=s.getTracks().map(t=>({kind:t.kind,settings:t.getSettings()}));measuredStreams.push(s);return s;});
  };
  localStorage.setItem('moss.settings.v2',JSON.stringify({transcription:{vendor:'gemini',apiKey:'offline-prototype-stub'},summary:{vendor:'gemini',apiKey:'offline-prototype-stub',rolling:false},general:{cleanupAfterStop:false}}));
  localStorage.setItem('lt:ui:controlPanelCollapsed','false');
})();"""


def line(gap, rate):
    def clock(sample):
        s = sample // rate
        return f'{s//3600:02}:{s//60%60:02}:{s%60:02}'
    return f'([{clock(gap["start_sample"])}-{clock(gap["end_sample"])}] Recording Interrupted)'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cases',default='ABCDEFGHIJKL');selected=set(parser.parse_args().cases)
    assert selected <= set('ABCDEFGHIJKL')
    directory = EV / ('chrome-' + time.strftime('%Y%m%d-%H%M%S'))
    directory.mkdir(parents=True)
    h_cell=None
    if 'H' in selected:
        # The existing L1 runner, redirected only to this task's evidence root.
        sys.path.insert(0,str(ROOT/'prototypes/gemini-live/long-meeting/L1'))
        budget=runpy.run_path(str(ROOT/'prototypes/gemini-live/long-meeting/L1/run.py'),run_name='p74_budget')
        budget['main'].__globals__['EV']=directory
        saved_argv=sys.argv
        sys.argv=['L1/run.py','--mode','product','--port','18988','--label','H-product']
        try:
            with (directory/'H-output.log').open('w') as log, contextlib.redirect_stdout(log):
                budget['main']()
        finally:
            sys.argv=saved_argv
        h=json.loads((directory/'H-product.json').read_text())
        h_cell={'verdict':'PASS','brief':f'{h["completed"]:,} loop requests; {h["traffic"]["failed"]} failures; {h["wall_seconds"]:.3f} s','receipt':str(directory/'H-product.json'),'measurement':h}
    status_prefix = STATUS.read_text()
    cookies = asyncio.run(provision(directory / 'meeting.sqlite'))
    engines, summary_inputs, offset = [], [], [0]
    def runtime():
        d = descriptor(tape_bytes=16*1024*1024)
        d = replace(d, frame_samples=8000, bounds=replace(d.bounds,max_retained_samples=960000,max_events=1024))
        def factory(_sid, publish, _usage, _settings):
            e = bench.OfflineEngine(publish); engines.append(e); return e
        return GeminiLiveRuntime(descriptor=d,engine_factory=factory,tape_storage_root=directory/'tapes')
    app = make_app(directory/'meeting.sqlite',lease_seconds=120,live_runtime_factory=runtime)
    async def summary(document, **kwargs):
        summary_inputs.append({'document':document,'model':kwargs['model']})
        return {'summary':'Offline measured summary','topics':[],'details':[],'speaker_background':[],'data_references':[]}, None
    # Same injected generator seam used by Phase-2 tests; never construct a provider.
    app.state.summary_generator = summary
    with wave.open(str(directory/'mic.wav'),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
        wav.writeframes(struct.pack('<16000h',*(int(3000*math.sin(i*2*math.pi*330/16000)) for i in range(16000)))*90)
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(directory/'tls-key.pem'),'-out',str(directory/'tls-cert.pem'),'-days','1','-subj','/CN=127.0.0.1'],check=True,capture_output=True)
    @app.get('/ri/tone.wav')
    async def tone(): return FileResponse(directory/'mic.wav',media_type='audio/wav')
    @app.get('/ri/source')
    async def source(): return HTMLResponse(f'<title>{TITLE}</title><button id="play">Play tone</button><audio id="tone" src="/ri/tone.wav" loop></audio><script>play.onclick=()=>tone.play()</script>')
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=PORT,ssl_keyfile=str(directory/'tls-key.pem'),ssl_certfile=str(directory/'tls-cert.pem'),log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    result={'cases':{'H':h_cell} if h_cell else {},'sha':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'evidence':str(directory),'provider_calls':0,'built_assets':str(ROOT/'moss_transcribe_diarize/app/frontend_assets'),'server':'real Phase-2 app, no protocol replacement','lease_seconds':120,'C_clock':'presence/failure monotonic clock +125 s','display_refusal':'injected on gestureless return; native picker unmeasured'}
    browser=None
    def save():
        result['summary_generator_inputs']=summary_inputs
        (directory/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        (EV/'result.json').write_text(json.dumps(result,indent=2)+'\n')
        rows=[status_prefix.rstrip(), '', 'Fresh Chrome on candidate '+result['sha']+'; built assets from merged frontend, no provider calls.', '', '| Case | Result | Numbers / failure |','|---|---|---|']
        for code in sorted(selected):
            cell=result['cases'].get(code,{})
            rows.append(f'| {code} | {cell.get("verdict","PENDING")} | {cell.get("brief","")} |')
        rows += ['', 'Evidence: '+str(directory), 'Physical devices/native picker/provider/host remain UNMEASURED.']
        STATUS.write_text('\n'.join(rows)+'\n')
    try:
        for _ in range(200):
            if server.started: break
            time.sleep(.05)
        assert server.started
        # Controlled server clock only; all transport and lease logic remain product code.
        app.state.live_helper_presence._monotonic_ns=lambda:time.monotonic_ns()+offset[0]
        app.state.live_helper_failures._monotonic_ns=lambda:time.monotonic_ns()+offset[0]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True,ignore_default_args=['--mute-audio'],args=['--use-fake-device-for-media-stream','--auto-accept-camera-and-microphone-capture',f'--auto-select-tab-capture-source-by-title={TITLE}',f'--use-file-for-fake-audio-capture={directory/"mic.wav"}'])
            result['chrome']=browser.version
            def context(system=False):
                ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':1050},accept_downloads=True)
                ctx.grant_permissions(['microphone'],origin=URL)
                ctx.add_cookies([{'name':'__Host-moss_session','value':cookies['a'],'domain':'127.0.0.1','path':'/','secure':True,'httpOnly':True,'sameSite':'Lax'}])
                ctx.add_init_script(INIT)
                ctx.add_init_script(f"localStorage.setItem('lt:capture:sources',JSON.stringify({{system:{str(system).lower()},microphone:true}}))")
                # Refuse any unexpected external traffic before it can leave Chrome.
                ctx.route('**/*',lambda route:route.continue_() if route.request.url.startswith(URL) else route.abort())
                if system:
                    src=ctx.new_page();src.goto(URL+'/ri/source');src.click('#play')
                return ctx
            def observe(page, name):
                value=page.evaluate('({measurement,text:document.body.innerText,transcriptText:document.querySelector(".transcript-pane")?.innerText,transcriptGaps:[...document.querySelectorAll(".transcript-pane [data-recording-interruption]")].map(n=>n.innerText),worklets:measuredWorklets.map(w=>({lane:w.lane,frameSamples:w.frameSamples,contextFrame:w.ctx.currentTime*w.ctx.sampleRate,frames:w.frames})),tracks:measuredStreams.flatMap(s=>s.getTracks().map(t=>({kind:t.kind,state:t.readyState})))})')
                (directory/f'{name}.json').write_text(json.dumps(value,indent=2))
                page.screenshot(path=str(directory/f'{name}.png'),full_page=True)
                return value
            def get(page,path): return page.evaluate('async path=>(await fetch(path)).json()',path)
            def start(ctx, seconds=5):
                page=ctx.new_page();page.goto(URL+'/');page.get_by_role('button',name='Start Transcribing',exact=True).click()
                page.wait_for_timeout(seconds*1000)
                state=observe(page,'start-'+str(len(engines)))
                assert any(f['status']==200 for f in state['measurement']['frames']),state
                stored=page.evaluate("JSON.parse(sessionStorage.getItem('lt:session:reattach'))")
                return page,stored,state
            def resumed(page,code):
                page.reload();page.wait_for_timeout(7500)
                state=observe(page,code+'-reload')
                m=state['measurement'];frames=[f for f in m['frames'] if f['status']==200]
                cell={'observation':state,'clicks':len(m['clicks']),'first_accepted_frame_seconds':(frames[0]['at']-m['loadedAt'])/1000 if frames else None,'frames_accepted':len(frames)}
                assert frames and not m['clicks'],cell
                return cell
            def stop(page,sid):
                page.get_by_role('button',name='Stop Recording',exact=True).click()
                for _ in range(100):
                    meeting=get(page,f'/api/meetings/{sid}')
                    if meeting['status']=='completed': break
                    page.wait_for_timeout(100)
                assert meeting['status']=='completed',meeting
                page.wait_for_timeout(2500)
                return meeting
            def archive(sid):
                paths=list((directory/'meetings').glob(f'**/{sid}/audio.mp3'))
                assert len(paths)==1,paths
                pcm=subprocess.check_output(['ffmpeg','-v','error','-i',str(paths[0]),'-f','s16le','-ac','1','-ar','16000','-'])
                return {'path':str(paths[0]),'files':len(paths),'decoded_samples':len(pcm)//2,'seconds':len(pcm)/32000},pcm
            def document_views(page,sid,meeting,code,expected):
                doc=meeting['transcript'];gaps=doc.get('capture_interruptions',[])
                assert len(gaps)==expected,doc
                lines=[line(g,doc['sample_rate']) for g in gaps]
                view=observe(page,code+'-stopped-transcript')
                assert view['transcriptGaps']==lines,view
                # Open a fresh page so History is read from persisted product state.
                history=page.context.new_page();history.goto(URL+'/');history.wait_for_timeout(1500)
                card=history.locator(f'[data-meeting-card="{sid}"]')
                assert all(s in card.inner_text() for s in lines),card.inner_text()
                history.locator(f'[data-open-meeting="{sid}"]').click();history.wait_for_timeout(1000)
                history_state=observe(history,code+'-history')
                assert history_state['transcriptGaps']==lines,history_state
                downloads={}
                assert history.get_by_label('Export format').locator('option').all_text_contents()==['Markdown (.md)','Text (.txt)','Audio (.mp3)']
                for fmt in ['md','txt']:
                    history.get_by_label('Export format').select_option(fmt)
                    with history.expect_download() as download:
                        history.get_by_role('button',name='Save',exact=True).click()
                    path=directory/f'{code}-export.{fmt}';download.value.save_as(path)
                    text=path.read_text();downloads[fmt]={'path':str(path),'content':text}
                    assert all(text.count(s)==1 for s in lines),(fmt,text,lines)
                    assert [text.index(s) for s in lines]==sorted(text.index(s) for s in lines)
                    # The line must sit between the preceding and subsequent speech rows.
                    for s in lines:
                        before,after=text.split(s)
                        assert 'synthetic audible block' in before and 'synthetic audible block' in after,text
                a,pcm=archive(sid)
                snapshot=get(page,f'/api/live/sessions/{sid}/snapshot')
                mixed=snapshot['snapshot']['session']['accepted_samples']
                assert a['decoded_samples']==mixed,(a,mixed)
                gap_samples=sum(g['end_sample']-g['start_sample'] for g in gaps)
                a.update(mixed_samples=mixed,gap_seconds=gap_samples/16000,recorded_seconds=(mixed-gap_samples)/16000)
                for g in gaps:
                    interior=pcm[(g['start_sample']+1600)*2:(g['end_sample']-1600)*2]
                    assert not any(interior),g
                assert summary_inputs,summary_inputs
                source=summary_inputs[-1:]
                assert 'Recording Interrupted' not in json.dumps(source) and 'capture_interruptions' not in json.dumps(source),source
                browser_summary=page.evaluate('measurement.summaries')
                assert browser_summary and 'Recording Interrupted' not in json.dumps(browser_summary),browser_summary
                history.close()
                return {'saved_document':doc,'lines':lines,'live_transcript':view,'history':history_state,'exports':downloads,'audio':a,'summary_requests':browser_summary,'summary_source':source}
            # A/B/E/F: retain per-case failures and continue independent cases.
            for code,system,repeat in [('A',False,1),('B',True,1),('F',False,2)]:
                if code not in selected: continue
                ctx=context(system);cell={}
                try:
                    page,old,before=start(ctx,20 if code=='A' else 5);sid=old['sessionId']
                    cell.update(session_id=sid,before=before,resumes=[])
                    for i in range(repeat):
                        resumed_cell=resumed(page,code+str(i));cell['resumes'].append(resumed_cell)
                        assert page.evaluate("JSON.parse(sessionStorage.getItem('lt:session:reattach')).sessionId")==sid
                    cell.update(clicks=cell['resumes'][0]['clicks'],first_accepted_frame_seconds=cell['resumes'][0]['first_accepted_frame_seconds'],frames_accepted=cell['resumes'][0]['frames_accepted'])
                    if system:
                        m=cell['resumes'][0]['observation']['measurement']
                        assert all(f['silent'] for f in m['frames'] if f['lane']=='system' and f['status']==200),m
                        assert page.get_by_role('button',name='Share Tab Audio Again',exact=True).count()==1
                        observe(page,'B-silent-system')
                        page.bring_to_front();page.get_by_role('button',name='Share Tab Audio Again',exact=True).click();page.wait_for_timeout(2500)
                        share=observe(page,'B-shared');cell['share']=share
                        assert any(f['lane']=='system' and not f['silent'] and f['status']==200 for f in share['measurement']['frames']),share
                        cell['share_clicks']=sum('Share Tab Audio Again' in x['label'] for x in share['measurement']['clicks'])
                        assert cell['share_clicks']==1
                    # Capture live gap metadata before Stop, through actual snapshot/UI.
                    cell['live_snapshot']=get(page,f'/api/live/sessions/{sid}/snapshot')
                    meeting=stop(page,sid);cell['final_state']=meeting['status']
                    # E's archive/views verification is a separate gate for A and B.
                    result['cases'][code]={**cell,'verdict':'PASS','brief':f'0 clicks; {cell["first_accepted_frame_seconds"]:.3f} s; {cell["frames_accepted"]} frames; completed'}
                    save()
                    try:
                        views=document_views(page,sid,meeting,code,repeat)
                        result['cases'][code]['views']=views
                        if code in 'AB':
                            e=result['cases'].setdefault('E',{'verdict':'PASS','measurements':{}})
                            e['measurements'][code]=views;e['brief']='A/B stopped archive, views, MD/TXT, summary checks'
                    except Exception as exc:
                        fail={'verdict':'FAIL','error':repr(exc),'traceback':traceback.format_exc(),'meeting':meeting,'brief':str(exc)[:200]}
                        if code=='F':result['cases']['F'].update(fail)
                        else:result['cases'].setdefault('E',{'measurements':{}}).update(fail)
                except Exception as exc:
                    result['cases'][code]={**cell,'verdict':'FAIL','error':repr(exc),'traceback':traceback.format_exc(),'brief':str(exc)[:200]}
                finally:
                    ctx.close();save();print(json.dumps({'case':code,'verdict':result['cases'][code]['verdict'],'brief':result['cases'][code]['brief']}),flush=True)
            for code in ['C','D','I','K','G']:
                if code not in selected: continue
                ctx=context();cell={}
                try:
                    page,old,before=start(ctx);sid=old['sessionId'];cell.update(session_id=sid,before=before)
                    if code=='C':
                        offset[0]+=125_000_000_000;page.reload();page.wait_for_timeout(4500)
                        state=observe(page,'C-expired');meeting=get(page,f'/api/meetings/{sid}');m=state['measurement']
                        cell.update(observation=state,meeting=meeting,frames_accepted=sum(f['status']==200 for f in m['frames']),clicks=len(m['clicks']),first_accepted_frame_seconds=None,final_state=meeting['status'])
                        assert meeting['status']=='interrupted' and not m['frames'] and 'Recording stopped: connection lost.' in state['text'],cell
                        assert any(r['status']==409 and r['response'].get('code')=='resume_lease_expired' for r in m['resumes']),cell
                    elif code in ['D','I','K']:
                        saved=page.evaluate("sessionStorage.getItem('lt:session:reattach')");duplicate=ctx.new_page();duplicate.add_init_script(f"sessionStorage.setItem('lt:session:reattach',{json.dumps(saved)})")
                        duplicate.goto(URL+'/');duplicate.wait_for_timeout(9000)
                        viewer=observe(duplicate,code+'-duplicate');original=observe(page,code+'-original')
                        cell.update(duplicate=viewer,original=original,frames_accepted=len(viewer['measurement']['frames']),clicks=len(viewer['measurement']['clicks']),first_accepted_frame_seconds=None)
                        assert 'Resume Recording Here' in viewer['text'] and not viewer['measurement']['frames'],viewer
                        assert len(original['measurement']['frames'])>len(before['measurement']['frames']),original
                        if code in ['I','K']:
                            if code=='K':duplicate.evaluate('window.requirePartialTakeover=true')
                            duplicate.get_by_role('button',name='Resume Recording Here',exact=True).click();duplicate.wait_for_timeout(3000)
                            replaced=observe(page,code+'-replaced-original');new=observe(duplicate,code+'-new-writer');cell.update(replaced_original=replaced,new_writer=new)
                            assert any(e['body'].get('code',e['body'].get('detail',{}).get('code'))=='capture_replaced' for e in replaced['measurement']['errors']),replaced
                            assert replaced['tracks'] and all(t['state']=='ended' for t in replaced['tracks']),replaced
                            assert page.get_by_role('button',name='Detach',exact=True).count()==1 and page.get_by_role('button',name='Stop Recording',exact=True).count()==0,replaced
                            assert len(replaced['measurement']['creates'])==1,replaced
                            assert any(f['status']==200 for f in new['measurement']['frames']),new
                            assert not new['measurement']['creates'],new
                            assert not any(f['status']==400 for f in new['measurement']['frames']),new
                            if code=='K':
                                adoption=next(r for r in new['measurement']['resumes'] if r['status']==200)
                                partials=[]
                                for w in adoption['worklets']:
                                    actual_worklet=next(lane for lane in reversed(new['worklets']) if lane['lane']==w['lane'])
                                    next_start=w['last']['startFrame']+w['frameSamples'] if w.get('last') else actual_worklet['frames'][0]['startFrame']
                                    filled=w['contextFrame']-next_start
                                    assert 0 < filled < w['frameSamples'],w
                                    emitted=next(f for f in actual_worklet['frames'] if f['startFrame']==next_start)
                                    first=next(f for f in new['measurement']['frames'] if f['lane']==w['lane'])
                                    endpoint=adoption['response']['lanes'][w['lane']]['last_capture_end_timestamp_ns']
                                    assert first['capture_timestamp_ns'] >= endpoint,(first,endpoint)
                                    # The straddling worklet message exists, but the first POST starts after
                                    # adoption's clock, never at that pre-adoption partial start.
                                    assert first['capture_timestamp_ns'] >= adoption['response']['capture_now_ns']
                                    partials.append({'lane':w['lane'],'filled_samples_at_response':filled,
                                        'straddling_worklet_frame':emitted,'first_post':first,'old_accepted_endpoint_ns':endpoint})
                                cell['partial_chunk_receipts']=partials
                                cell['zero_400']=True
                            cell['explicit_takeover_clicks']=len(new['measurement']['clicks'])
                            cell['takeover_first_frame_seconds']=(next(f for f in new['measurement']['frames'] if f['status']==200)['at']-new['measurement']['loadedAt'])/1000
                            stop(duplicate,sid)
                        else:stop(page,sid)
                        cell['final_state']=get(page,f'/api/meetings/{sid}')['status']
                    else:
                        meeting=stop(page,sid);doc=meeting['transcript'];cell.update(meeting=meeting,final_state=meeting['status'],clicks=0,frames_accepted=len(before['measurement']['frames']),first_accepted_frame_seconds=None)
                        assert 'capture_interruptions' not in doc and 'sample_rate' not in doc,doc
                        state=observe(page,'G-no-reload');assert not state['transcriptGaps'],state
                        a,_=archive(sid);cell['audio']=a
                        assert len(engines)>0
                    cell.update(verdict='PASS',brief=f'{cell["clicks"]} clicks; {cell["frames_accepted"]} resumed frames; {cell["final_state"]}')
                except Exception as exc:
                    cell.update(verdict='FAIL',error=repr(exc),traceback=traceback.format_exc(),brief=str(exc)[:200])
                finally:
                    offset[0]=0;result['cases'][code]=cell;ctx.close();save();print(json.dumps({'case':code,'verdict':cell['verdict'],'brief':cell['brief']}),flush=True)
            if 'J' in selected:
                # J: reload after initial heartbeat, before either lane's first accepted frame.
                ctx=context();cell={}
                try:
                    page=ctx.new_page();page.goto(URL+'/')
                    page.get_by_role('button',name='Start Transcribing',exact=True).click()
                    page.wait_for_function("sessionStorage.getItem('lt:session:reattach') !== null")
                    old=page.evaluate("JSON.parse(sessionStorage.getItem('lt:session:reattach'))")
                    sid=old['sessionId']
                    before=page.evaluate('measurement')
                    assert not before['frames'],before
                    page.reload();page.wait_for_timeout(6500)
                    state=observe(page,'J-late-start');m=state['measurement']
                    assert any(f['status']==200 for f in m['frames']) and not m['clicks'],state
                    assert next(r for r in m['resumes'] if r['status']==200)['response']['interruption'] is None,m
                    meeting=stop(page,sid);final=observe(page,'J-stopped')
                    doc=meeting['transcript'];assert not doc.get('capture_interruptions') and not final['transcriptGaps'],doc
                    a,_=archive(sid)
                    frames=[f for f in final['measurement']['frames'] if f['status']==200]
                    assert len(frames)==len(final['measurement']['frames']),final
                    sent_by_lane={lane:sum(f['sample_count'] for f in frames if f['lane']==lane) for lane in ['system','microphone']}
                    mixed=get(page,f'/api/live/sessions/{sid}/snapshot')['snapshot']['session']['accepted_samples']
                    assert a['decoded_samples']==mixed==sent_by_lane['system']==sent_by_lane['microphone'],(a,mixed,sent_by_lane)
                    cell.update(verdict='PASS',brief=f'0 original frames; 0 gaps; {a["decoded_samples"]} saved = sent samples/lane',
                        session_id=sid,before=before,observation=state,final=final,meeting=meeting,audio=a,sent_samples_by_lane=sent_by_lane)
                except Exception as exc:
                    cell.update(verdict='FAIL',error=repr(exc),traceback=traceback.format_exc(),brief=str(exc)[:200])
                finally:
                    result['cases']['J']=cell;ctx.close();save();print(json.dumps({'case':'J','verdict':cell['verdict'],'brief':cell['brief']}),flush=True)
            if 'L' in selected:
                # L: durable text and section-speaker edits, real Markdown download, History deletion.
                ctx=context();cell={}
                try:
                    page,old,before=start(ctx);sid=old['sessionId'];cell.update(session_id=sid)
                    cell['resume']=resumed(page,'L')
                    meeting=stop(page,sid);doc=meeting['transcript'];gaps=doc['capture_interruptions']
                    passage=doc['segments'][-1]['id'];text='RM corrected section after reload'
                    pencil=page.locator(f'[data-edit-passage="{passage}"]');pencil.click()
                    page.get_by_label('Section text',exact=True).fill(text)
                    page.locator('.text-editor').get_by_role('button',name='Save',exact=True).click()
                    page.get_by_label('Section text',exact=True).wait_for(state='detached')
                    edited=get(page,f'/api/meetings/{sid}')
                    assert edited['transcript']['segments'][-1]['text']==text,edited
                    assert edited['transcript']['capture_interruptions']==gaps,edited
                    section=page.locator(f'[data-edit-passage="{passage}"]').locator('xpath=ancestor::article').locator('button.utt-speaker')
                    selected_ids=section.get_attribute('data-section-speaker').split(',')
                    section.click()
                    popup=page.get_by_role('dialog',name='Speaker',exact=True)
                    assert 'Recording Interrupted' not in popup.inner_text()
                    choice=popup.get_by_role('combobox',name='Speaker',exact=True)
                    if choice.get_attribute('aria-expanded')!='true':choice.click()
                    popup.get_by_role('textbox',name='New Speaker',exact=True).fill('RM Section Speaker')
                    popup.get_by_role('textbox',name='New Speaker',exact=True).press('Enter')
                    popup.get_by_role('button',name='Assign This Section',exact=True).click()
                    popup.wait_for(state='detached')
                    changed=get(page,f'/api/meetings/{sid}')
                    assert changed['transcript']['capture_interruptions']==gaps,changed
                    assert [s for s in changed['transcript']['segments'] if s['id'] not in selected_ids]==[s for s in doc['segments'] if s['id'] not in selected_ids],changed
                    assert all(s['speaker']=='RM Section Speaker' for s in changed['transcript']['segments'] if s['id'] in selected_ids),changed
                    chosen=changed['transcript']['segments'][-1]
                    assert (chosen['text'],chosen['edited'],chosen['speaker'])==(text,True,'RM Section Speaker'),chosen
                    assert changed['audio']==meeting['audio'],changed
                    state=observe(page,'L-edited-speaker')
                    lines=[line(g,doc['sample_rate']) for g in gaps]
                    assert state['transcriptGaps']==lines and text in state['transcriptText'],state
                    history=ctx.new_page();history.goto(URL+'/');history.wait_for_timeout(1500)
                    history.locator(f'[data-open-meeting="{sid}"]').click();history.wait_for_timeout(1000)
                    history_state=observe(history,'L-history-edited')
                    assert history_state['transcriptGaps']==lines and text in history_state['transcriptText'],history_state
                    history.get_by_label('Export format').select_option('md')
                    with history.expect_download() as download:
                        history.get_by_role('button',name='Save',exact=True).click()
                    export_path=directory/'L-edited-export.md';download.value.save_as(export_path);export=export_path.read_text()
                    assert text in export and 'RM Section Speaker' in export and all(export.count(s)==1 for s in lines),export
                    assert export.index(lines[-1]) < export.index(text),export
                    a,_=archive(sid)
                    card=history.locator(f'[data-meeting-card="{sid}"]')
                    card.get_by_role('button',name='Delete session',exact=True).click()
                    card.locator('[data-delete-submit]').click()
                    card.wait_for(state='detached')
                    history.wait_for_function('async sid=>(await fetch(`/api/meetings/${sid}`)).status===404',arg=sid)
                    assert not Path(a['path']).exists(),a
                    assert not history.locator('.transcript-pane [data-recording-interruption]').count()
                    cell.update(verdict='PASS',brief=f'{len(lines)} gap; 1 text edit; 1 section assignment; Markdown retained both; History delete removed archive, readback 404',
                        before=meeting,changed=changed,assigned_section_passage_ids=selected_ids,view=state,history=history_state,export={'path':str(export_path),'content':export},deleted_audio=a)
                except Exception as exc:
                    cell.update(verdict='FAIL',error=repr(exc),traceback=traceback.format_exc(),brief=str(exc)[:200])
                finally:
                    result['cases']['L']=cell;ctx.close();save();print(json.dumps({'case':'L','verdict':cell['verdict'],'brief':cell['brief']}),flush=True)
            browser.close();browser=None
    except Exception as exc:
        result['harness_error']=repr(exc);result['traceback']=traceback.format_exc()
    finally:
        if browser:browser.close()
        server.should_exit=True;thread.join(15);result['local_server_stopped']=not thread.is_alive()
        result['engine_count']=len(engines);save()
        result['chrome_gate_passed'] = selected <= result['cases'].keys() and all(result['cases'][code]['verdict']=='PASS' for code in selected) and result['local_server_stopped']
        save()
        print(json.dumps(result),flush=True)

if __name__=='__main__':main()
