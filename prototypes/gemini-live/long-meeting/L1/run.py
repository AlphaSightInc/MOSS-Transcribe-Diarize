"""Retained P74 real-path Chrome regression. No providers, no secrets, local state only."""
from __future__ import annotations
import argparse, json, subprocess, sys, threading, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
import uvicorn
from fastapi.responses import HTMLResponse, Response
from playwright.sync_api import sync_playwright
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiLiveRuntime, ScriptedGeminiEngine
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceDescriptor,LiveServiceBounds,LiveServiceConfigHashes,hash_config
EV=Path('/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/leak-fix')
HERE=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['baseline','C1','C2','C3','C4','product'],default='baseline');p.add_argument('--total',type=int,default=100002);p.add_argument('--port',type=int,default=18976);p.add_argument('--label');p.add_argument('--raw',action='store_true',default=True);p.add_argument('--observe-network',dest='raw',action='store_false');p.add_argument('--ui',action='store_true');a=p.parse_args()
    assert 18970<=a.port<=18989
    label=a.label or f'{a.mode}-{time.time_ns()}';state=EV/label;state.mkdir(parents=True,exist_ok=True)
    # One build of the actual module, with prototype-only C1 source transform if requested.
    transform='''{name:'p74-c1',enforce:'pre',transform(code,id){if(id.endsWith('/captureClient.ts')){if(!code.includes('return await fetch(input, { ...init, signal: controller.signal });'))throw new Error('C1 seam did not match');return code.replace('return await fetch(input, { ...init, signal: controller.signal });', `const response = await fetch(input, { ...init, signal: controller.signal });\n      const body = await response.arrayBuffer();\n      return new Response(response.body === null ? null : body, { status: response.status, statusText: response.statusText, headers: response.headers });`);}}}'''
    source=subprocess.check_output(['git','show','54fb5573:frontend/src/capture/captureClient.ts'],cwd=ROOT,text=True)
    pinned="{name:'p74-source',enforce:'pre',load(id){if(id.endsWith('/captureClient.ts'))return "+json.dumps(source)+";}}" if a.mode!='product' else ''
    plugins=','.join(x for x in [pinned,transform if a.mode in ['C1','C4'] else '', 'preact()'] if x)
    js=f"import {{build}} from './node_modules/vite/dist/node/index.js'; import preact from '@preact/preset-vite'; await build({{configFile:false,plugins:[{plugins}],resolve:{{alias:{{preact:{json.dumps(str(ROOT/'frontend/node_modules/preact'))}}}}},build:{{outDir:{json.dumps(str(state/'bundle'))},emptyOutDir:true,target:'es2022',rolldownOptions:{{input:{json.dumps(str(HERE/'page.ts'))},output:{{entryFileNames:'p74.js',codeSplitting:false}}}}}}}});"
    subprocess.run(['/opt/homebrew/bin/node','--input-type=module','-e',js],cwd=ROOT/'frontend',check=True,stdout=subprocess.DEVNULL)
    d=LiveServiceDescriptor(source_revision='54fb5573',provider_name='gemini',provider_revision='p74-scripted',provider_manifest_hash=hash_config({}),config_hashes=LiveServiceConfigHashes.from_parts(endpoint_config={},identity_config={},decoder_config={}),bounds=LiveServiceBounds(max_frame_samples=16000,max_queue_depth=4,max_retained_samples=32000,max_identity_speakers=8,max_events=64,max_tape_bytes=100000000),frame_samples=2)
    rt=GeminiLiveRuntime(descriptor=d,tape_storage_root=state/'tapes',engine_factory=lambda _id,publish,_usage,_settings=None:ScriptedGeminiEngine(publish,batches=[],terminal=()))
    app=create_phase2_app(database_path=state/'phase2.sqlite',file_work_root=state/'files',meeting_audio_root=state/'audio',live_runtime_factory=lambda:rt,live_helper_lease_seconds=120,open_workspace=True)
    if a.mode != 'product':
        @app.middleware('http')
        async def variant(request,call_next):
            r=await call_next(request)
            capture=request.method=='POST' and request.url.path.endswith(('/frames','/heartbeat'))
            if capture and a.mode in ['baseline','C1','C2']: r.headers['Cache-Control']='no-store'
            if capture and a.mode=='C2' and 200<=r.status_code<300:
                async for _ in r.body_iterator: pass
                headers=dict(r.headers);headers.pop('content-length',None);headers.pop('content-type',None)
                return Response(status_code=204,headers=headers)
            if capture and a.mode in ['C3','C4']:
                r.headers['Cache-Control']='no-cache'
            return r
    @app.get('/p74')
    async def page():return HTMLResponse('<!doctype html><title>P74 real path</title><pre>idle</pre><script type="module" src="/p74.js"></script>')
    @app.get('/p74.js')
    async def bundle():return Response((state/'bundle/p74.js').read_bytes(),media_type='application/javascript')
    server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=a.port,log_level='error',access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    try:
        deadline=time.monotonic()+20
        while not server.started:
            if time.monotonic()>deadline:raise RuntimeError('server did not start')
            time.sleep(.02)
        if a.raw:
            from raw_chrome import Chrome
            chrome=Chrome(state,18978,f'http://127.0.0.1:{a.port}/p74')
            try:
                page=chrome.page;cdp=chrome.page;bcdp=chrome.browser;cdp.send('Performance.enable')
                def memory():
                    cdp.send('HeapProfiler.collectGarbage')
                    metrics={x['name']:x['value'] for x in cdp.send('Performance.getMetrics')['metrics']}
                    pids=[x['id'] for x in bcdp.send('SystemInfo.getProcessInfo')['processInfo'] if x['type']=='renderer']
                    rss=[int(subprocess.check_output(['ps','-o','rss=','-p',str(pid)]).strip())/1024 for pid in pids]
                    return {'requests':page.evaluate('window.completed||0'),'heap_MB':metrics['JSHeapUsedSize']/1048576,'renderer_rss_MB':rss,'rss_total_MB':sum(rss),'capture_renderer_pid':chrome.renderer_pid,'capture_renderer_MB':int(subprocess.check_output(['ps','-o','rss=','-p',str(chrome.renderer_pid)]).strip())/1024}
                memories=[memory()];started=time.monotonic()
                while page.evaluate('window.completed||0')<a.total:
                    left=a.total-page.evaluate('window.completed||0')
                    result=page.evaluate('(n)=>run(n)',min(3000,left));memories.append(memory())
                    print(json.dumps({'mode':a.mode,**result,'memory':memories[-1]}),flush=True)
                    if result['firstFailure']:break
                traffic=page.evaluate('window.traffic')
                result.update(mode=a.mode,label=label,target=a.total,wall_seconds=time.monotonic()-started,memory=memories,traffic=traffic,first_responses=traffic['firstResponses'],chrome=chrome.version,probe=page.evaluate('probe()'),page_text=page.evaluate('document.querySelector("pre").textContent'),descriptor_frame_samples=2,provider_calls=0,checkout_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),capture_source='checkout' if a.mode=='product' else '54fb5573',server_snapshot=rt.snapshot(page.evaluate('window.client.session.id')).to_dict(),observer='Playwright disconnected; raw CDP Runtime/Performance only, Network disabled')
                if a.ui: result['product_ui']=page.evaluate('observeUi()')
                (EV/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
            finally:chrome.close()
        else:
            with sync_playwright() as pw:
                browser=pw.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
                page=browser.new_page();page.goto(f'http://127.0.0.1:{a.port}/p74');page.wait_for_function('typeof run === "function"')
                cdp=page.context.new_cdp_session(page);bcdp=browser.new_browser_cdp_session();cdp.send('Performance.enable')
                def memory():
                    cdp.send('HeapProfiler.collectGarbage')
                    metrics={x['name']:x['value'] for x in cdp.send('Performance.getMetrics')['metrics']}
                    pids=[x['id'] for x in bcdp.send('SystemInfo.getProcessInfo')['processInfo'] if x['type']=='renderer']
                    rss=[int(subprocess.check_output(['ps','-o','rss=','-p',str(pid)]).strip())/1024 for pid in pids]
                    return {'requests':page.evaluate('window.completed||0'),'heap_MB':metrics['JSHeapUsedSize']/1048576,'renderer_rss_MB':rss,'rss_total_MB':sum(rss)}
                memories=[memory()];result=None;started=time.monotonic();traffic={'frames':0,'heartbeat':0,'failed':0,'status':{}};first_http=[]
                def response(r):
                    route=r.url.rsplit('/',1)[-1]
                    if route in ('frames','heartbeat'):
                        traffic[route]+=1;key=str(r.status);traffic['status'][key]=traffic['status'].get(key,0)+1
                        if len(first_http)<2:first_http.append({'route':route,'status':r.status,'headers':r.headers})
                page.on('response',response)
                page.on('requestfailed',lambda r:traffic.update(failed=traffic['failed']+1))
                while page.evaluate('window.completed||0')<a.total:
                    left=a.total-page.evaluate('window.completed||0')
                    result=page.evaluate('(n)=>run(n)',min(3000,left));memories.append(memory())
                    print(json.dumps({'mode':a.mode,**result,'memory':memories[-1]}),flush=True)
                    if result['firstFailure']:break
                result.update(mode=a.mode,label=label,target=a.total,wall_seconds=time.monotonic()-started,memory=memories,traffic=traffic,first_responses=first_http,chrome=browser.version,probe=page.evaluate('probe()'),page_text=page.locator('pre').inner_text(),descriptor_frame_samples=2,provider_calls=0)
                (EV/f'{label}.json').write_text(json.dumps(result,indent=2)+'\n')
                
                try: page.screenshot(path=str(EV/f'{label}.png'),timeout=1000)
                except Exception as exc: (EV/f'{label}-screenshot.txt').write_text(str(exc))
                print(json.dumps(result),flush=True);browser.close()
    finally:
        server.should_exit=True;thread.join(15)
        if thread.is_alive():raise RuntimeError('server did not stop')
    if a.mode=='baseline':
        assert result['firstFailure'] and 16000 <= result['traffic'].get('firstFailed',{}).get('index',result['completed']) <= 17000, result
        assert result['wall_seconds']<180, result['wall_seconds']
        assert all('Failed to fetch' in str(v) for v in result['probe'].values()),result['probe']
    else:
        assert result['completed']>=a.total and result['firstFailure'] is None and result['traffic']['failed']==0, result
        assert set(result['traffic']['status'])=={'204' if a.mode=='C2' else '200'},result['traffic']
if __name__=='__main__':main()
