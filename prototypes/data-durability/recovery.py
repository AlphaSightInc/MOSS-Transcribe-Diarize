"""PROTOTYPE — ACTIVE backup, TERM, same-document recovery, fresh-path cold start.
Browser devices simulated with public speech; HTTP, encoder, ASR, DB and audio real.
"""
import json, shutil, sqlite3, time, subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright
from journeys import ROOT,SCRATCH,OUT,BASE,CORPUS,start,stop,rows,copy_state,browser_executable,SESSION_COOKIE

def setup(page):
    reset=page.get_by_role('button',name='Reset capture',exact=True)
    if reset.count(): reset.click()
    page.get_by_label('Listening setup',exact=True).select_option('headphones')
    page.get_by_role('button',name='Enable microphone',exact=True).click()
    page.wait_for_function('document.querySelector(".capture-status")?.textContent.includes("Microphone connected")')
    page.get_by_role('button',name='Share audio',exact=True).click()
    page.get_by_role('button',name='Start capture',exact=True).click()
    page.wait_for_function('document.querySelector("[data-capture-phase]")?.getAttribute("data-capture-phase")==="active"')

def api(page,path): return page.evaluate('async p=>{const r=await fetch(p);return r.json()}',path)

def segments(m):return (m.get('transcript') or {}).get('segments',[])

def main():
    state=SCRATCH/'recovery-final'; state.mkdir()
    result={}; proc,c,seconds=start(state,budget=35)
    result['cold_boot']={'startup_first_http_seconds':seconds,'fresh_path':True}
    try:
        c.post('/api/workspace/bootstrap').raise_for_status(); t=time.monotonic(); d=c.get('/api/live/descriptor'); result['cold_boot']['descriptor_seconds']=time.monotonic()-t;result['cold_boot']['descriptor_status']=d.status_code
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=str(browser_executable(p)),headless=True,args=['--use-fake-device-for-media-stream','--auto-accept-camera-and-microphone-capture',f'--use-file-for-fake-audio-capture={CORPUS}'])
            context=browser.new_context(ignore_https_errors=True,permissions=['microphone']);context.set_default_timeout(20000)
            context.add_init_script('navigator.mediaDevices.getDisplayMedia=()=>navigator.mediaDevices.getUserMedia({audio:true});window.__wp31Document=crypto.randomUUID()')
            page=context.new_page();page.goto(BASE);page.locator('[data-boot="ready"]').wait_for();token=page.evaluate('window.__wp31Document')
            setup(page)
            mid=api(page,'/api/meetings')['meetings'][0]['id']
            deadline=time.monotonic()+22
            while time.monotonic()<deadline:
                page.wait_for_timeout(500)
                m=api(page,'/api/meetings/'+mid)
                if segments(m):break
            result['before_term']={'status':m['status'],'segments':len(segments(m)),'transcript_version':m.get('transcript_version')}
            # Capture remains ACTIVE with browser ingress and background commits continuing.
            active=SCRATCH/'active-backup-final'; copy_state(state,active)
            before=rows(active/'phase2.sqlite')
            result['active_backup']={'integrity':sqlite3.connect(active/'phase2.sqlite').execute('PRAGMA integrity_check').fetchone()[0],'copied_meetings':len(before['meetings']),'copied_transcripts':len(before['meeting_transcripts']),'wal_copied':(active/'phase2.sqlite-wal').exists(),'contract':'single observed hot copy; not an atomic DB-plus-audio guarantee'}
            frozen=api(page,'/api/meetings/'+mid);result['before_term']['segments']=len(segments(frozen))
            stop(proc);c.close();proc=None
            proc,c,seconds=start(state,budget=35);result['restart_seconds']=seconds
            for cookie in context.cookies():
                if cookie['name']==SESSION_COOKIE:c.cookies.set(SESSION_COOKIE,cookie['value'])
            recovered=c.get('/api/meetings/'+mid).json()
            audio=c.get('/api/meetings/'+mid+'/audio/download')
            audio_path=SCRATCH/'recovered.mp3';audio_path.write_bytes(audio.content)
            decodable=subprocess.run(['ffmpeg','-v','error','-i',str(audio_path),'-f','null','-'],capture_output=True).returncode==0 if audio.status_code==200 else False
            # Durable transcript should preserve at least the acknowledged segment records.
            saved=segments(recovered);prior=segments(frozen)
            result['restart']={'status':recovered['status'],'committed_before':len(prior),'committed_after':len(saved),'acknowledged_segments_preserved':all(s in saved for s in prior),'audio_state':(recovered.get('audio') or {}).get('state'),'audio_http':audio.status_code,'audio_bytes':len(audio.content),'audio_decodable':decodable}
            page.wait_for_function('["terminal","error"].includes(document.querySelector("[data-capture-phase]")?.getAttribute("data-capture-phase"))',timeout=30000)
            result['client']={'phase_after_restart':page.locator('[data-capture-phase]').get_attribute('data-capture-phase'),'same_document':page.evaluate('window.__wp31Document')==token}
            setup(page);page.wait_for_timeout(8000)
            mids={m['id'] for m in api(page,'/api/meetings')['meetings']};new=(mids-{mid}).pop()
            page.get_by_role('button',name='Stop and finalize',exact=True).click()
            page.wait_for_function('document.querySelector("[data-capture-phase]")?.getAttribute("data-capture-phase")==="terminal"',timeout=60000)
            next_m=api(page,'/api/meetings/'+new)
            result['client'].update(new_status=next_m['status'],new_segments=len(segments(next_m)),same_document_after_new=page.evaluate('window.__wp31Document')==token)
            context.close();browser.close()
    finally:
        if proc is not None:stop(proc)
        c.close();(OUT/'recovery.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    # Restore the ACTIVE copy through production startup recovery without contacting ASR.
    from fastapi.testclient import TestClient
    from probe import app
    with TestClient(app(active),base_url='https://moss.test') as client:
        restored=rows(active/'phase2.sqlite')
        result['active_backup']['restored_interrupted']=all(m['status']=='interrupted' for m in restored['meetings'])
        result['active_backup']['transcript_rows_preserved']=before['meeting_transcripts']==restored['meeting_transcripts']
        result['active_backup']['audio_states']=[m['state'] for m in restored['meeting_audio']]
        result['active_backup']['audio_resolves']=all((active/'meeting-audio'/a['relative_path']).is_file() for a in restored['meeting_audio'] if a['state'] in ('available','partial'))
    (OUT/'recovery.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)

if __name__=='__main__':main()
