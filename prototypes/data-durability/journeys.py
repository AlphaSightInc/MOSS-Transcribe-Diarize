"""PROTOTYPE — real decoder + browser on copied stores, private payloads never retained."""
import base64, json, os, shutil, signal, sqlite3, subprocess, sys, time, wave
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright
from tests.phase2.browser_support import browser_executable
from tests.e2e.export_oracle import compare_export, expected_rows
from moss_transcribe_diarize.app.phase2 import SESSION_COOKIE
from probe import ROOT, SCRATCH, OUT, rows, copy_state
BASE='https://127.0.0.1:18132'
LABELS={'md':'Markdown (.md)','txt':'Plain text (.txt)','json':'JSON (.json)','srt':'SubRip (.srt)','vtt':'WebVTT (.vtt)'}
CORPUS=ROOT.parent/'MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/audio.wav'
with wave.open(str(CORPUS)) as wav: PCM=wav.readframes(wav.getnframes())

def start(state, budget=12, code_root=ROOT, port=18132):
    log=(state/'server.log').open('ab'); t=time.monotonic()
    proc=subprocess.Popen([sys.executable,str(code_root/'prototypes/streaming-diarization/draft-lane/run_local_stack.py'),'--state',str(state.relative_to(ROOT)),'--cert','.wp31/cert.pem','--key','.wp31/key.pem','--port',str(port),'--vllm-base-url','http://127.0.0.1:18131/v1','--max-requests',str(budget)],cwd=ROOT,stdout=log,stderr=log)
    c=httpx.Client(base_url=f'https://127.0.0.1:{port}',verify=False,timeout=90)
    for _ in range(120):
        if proc.poll() is not None: raise RuntimeError('server exited; private server.log')
        try:
            r=c.get('/api/auth/session')
            if r.status_code in (200,401): return proc,c,time.monotonic()-t
        except httpx.TransportError: pass
        time.sleep(.25)
    proc.terminate(); proc.wait(); raise RuntimeError('startup timed out')

def stop(proc):
    proc.send_signal(signal.SIGTERM)
    try: return proc.wait(timeout=45)
    except subprocess.TimeoutExpired:
        proc.kill(); proc.wait(); raise RuntimeError('TERM required KILL')

def feed(c, seconds=8):
    d=c.get('/api/live/descriptor').json()['descriptor']; fs=d['frame_samples']; rate=d['sample_rate']
    r=c.post('/api/live/sessions',json={'source_revision':d['source_revision']}); r.raise_for_status(); sid=r.json()['id']
    ep=time.time_ns(); n=int(seconds*rate/fs)
    for seq in range(n):
        health=dict(state='capturing',device_epoch=ep,dropped_frames=0,discontinuities=0,failure_code=None)
        c.post(f'/api/live/sessions/{sid}/heartbeat',json=dict(schema='moss-live-helper-health.v1',instance_id='wp31',sequence=seq,sent_monotonic_ns=time.monotonic_ns(),helper_version='wp31',state='capturing',lanes={'system':health,'microphone':dict(health)})).raise_for_status()
        for lane,chunk in [('system',PCM[seq*fs*2:(seq+1)*fs*2]),('microphone',b'\0'*(fs*2))]:
            c.post(f'/api/live/sessions/{sid}/frames',json=dict(lane=lane,sequence=seq,capture_timestamp_ns=ep+seq*int(fs/rate*1e9),device_epoch=ep,pcm_base64=base64.b64encode(chunk).decode(),sample_count=fs,sample_rate=rate,silent=False,discontinuity=False)).raise_for_status()
    return sid,n

def finish(c,sid):
    r=c.post(f'/api/live/sessions/{sid}/stop',json={'deadline':30}); r.raise_for_status()
    for _ in range(120):
        m=c.get('/api/meetings/'+sid).json()
        if m['status']!='active':return m
        time.sleep(.5)
    raise RuntimeError('stop timeout')

def verify_browser(browser,c,state,name):
    before=rows(state/'phase2.sqlite'); result=dict(meetings=0,rendered=0,lanes=0,formats=0,exports_passed=0,empty_disabled=0,failures=[])
    for a in before['accounts']:
        sessions=[s for s in before['sign_in_sessions'] if s['account_id']==a['account_id']]
        if not a['enabled'] or not sessions: continue
        cred=sessions[0]['session_id']; c.cookies.clear(); c.cookies.set(SESSION_COOKIE,cred)
        context=browser.new_context(ignore_https_errors=True,accept_downloads=True)
        context.add_cookies([{'name':SESSION_COOKIE,'value':cred,'url':BASE,'secure':True,'httpOnly':True,'sameSite':'Lax'}])
        page=context.new_page(); page.goto(BASE); page.locator('[data-history-boot="ready"]').wait_for(timeout=30000)
        meetings=c.get('/api/meetings').json()['meetings']
        for m in meetings:
            mid=m['id']; result['meetings']+=1
            page.locator(f'[data-open-meeting="{mid}"]').click()
            page.wait_for_function('(id)=>document.querySelector(`[data-open-meeting="${id}"]`)?.getAttribute("aria-pressed")==="true"',arg=mid)
            expected=expected_rows(m)
            if not expected:
                result['empty_disabled']+=page.get_by_role('button',name='Export transcript',exact=True).is_disabled(); continue
            page.wait_for_function('(n)=>document.querySelectorAll(".utt-text").length===n',arg=len(expected))
            rendered=page.locator('.utt').evaluate_all('(es)=>es.map(e=>({text:e.querySelector(".utt-text").textContent,label:e.querySelector(".utt-speaker-label").textContent,lane:e.getAttribute("data-source-lane"),badge:e.querySelector(".utt-lane")?.textContent??null}))')
            from moss_transcribe_diarize.lane_word_oracle import words
            result['rendered']+=all(words(r['text'])==e['tokens'] and r['label']==e['label'] for r,e in zip(rendered,expected))
            result['lanes']+=all(r['lane']==e['lane'] and (bool(r['badge'])==bool(e['lane'])) for r,e in zip(rendered,expected))
            for fmt,label in LABELS.items():
                page.get_by_role('button',name='Export transcript',exact=True).click()
                with page.expect_download() as event:page.get_by_role('menuitem',name=label,exact=True).click()
                path=SCRATCH/'download'; event.value.save_as(path)
                verdict=compare_export(fmt,path.read_text(),m); path.unlink()
                result['formats']+=1;result['exports_passed']+=verdict['ok']
                if not verdict['ok']:result['failures'].append({'meeting_index':result['meetings'],'format':fmt,'oracle':verdict})
        context.close()
    return result

def main():
    result={'stores':{}}
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(browser_executable(p)),headless=True)
        for name in json.loads((OUT/'prototype.json').read_text())['stores']:
            state=SCRATCH/'stores'/name
            if (state/'requests.jsonl').exists(): raise RuntimeError('refuse decoder rerun in same state')
            proc,c,startup=start(state)
            try:
                r=verify_browser(browser,c,state,name); r['startup_seconds']=startup
                old=c.get('/api/meetings').json()['meetings']; ids={m['id'] for m in old}
                sid,frames=feed(c); m=finish(c,sid)
                current=c.get('/api/meetings').json()['meetings']
                r['new_capture']={'frames_per_lane':frames,'status':m['status'],'segments':len((m.get('transcript') or {}).get('segments',[])),'old_and_new_coexist':{x['id'] for x in current}==ids|{sid}}
                r['ok']=r['rendered']+r['empty_disabled']==r['meetings'] and r['lanes']+r['empty_disabled']==r['meetings'] and r['formats']==r['exports_passed'] and m['status']=='completed' and r['new_capture']['segments']>0 and r['new_capture']['old_and_new_coexist']
            finally:
                c.close(); code=stop(proc)
            r['exit_code']=code;r['requests']=len((state/'requests.jsonl').read_text().splitlines()) if (state/'requests.jsonl').exists() else 0
            result['stores'][name]=r
            print(json.dumps({'case':name,**r}),flush=True); (OUT/'journeys.json').write_text(json.dumps(result,indent=2)+'\n')
        browser.close()

if __name__=='__main__':main()
