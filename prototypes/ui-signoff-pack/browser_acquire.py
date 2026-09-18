"""Actual browser setup/file submission states; fake microphone explicitly identified."""
import os,json,sys,time,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from run import capture,VIEWPORTS
from playwright.sync_api import sync_playwright
from tests.phase2.browser_support import browser_executable
OUT=Path(os.environ.get('WP24_EVIDENCE_ROOT',str(ROOT/'evidence/mvpfix/wp24')));TMP=ROOT/'.wp24';BASE='https://127.0.0.1:17884'
def main():
    out=OUT/'browser';out.mkdir(exist_ok=True);records=[]
    corpus=Path('/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/audio.wav')
    with wave.open(str(corpus)) as src, wave.open(str(TMP/'public-12s.wav'),'wb') as dst:
        dst.setparams(src.getparams());dst.writeframes(src.readframes(12*16000))
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(browser_executable(p)),args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
        for v in VIEWPORTS:
            ctx=browser.new_context(ignore_https_errors=True,viewport={'width':v[0],'height':v[1]},permissions=['microphone'])
            ctx.request.post(BASE+'/api/workspace/bootstrap')
            page=ctx.new_page();page.goto(BASE);page.locator('[data-history-boot="ready"]').wait_for()
            capture(page,out,'real-empty-workspace','Actual isolated stack, fresh browser workspace',records)
            page.get_by_role('button',name='Enable microphone',exact=True).click()
            page.get_by_role('button',name='Share audio',exact=True).wait_for()
            capture(page,out,'mic-enabled','Actual stack; Chromium fake microphone device, not physical hardware',records)
            page.evaluate("() => { navigator.mediaDevices.getDisplayMedia=()=>new Promise(()=>{}); }")
            page.get_by_role('button',name='Share audio',exact=True).click()
            capture(page,out,'share-picker-pending','Actual setup; fake unresolved getDisplayMedia request. Native OS picker is NOT captured in headless Chromium.',records)
            ctx.close()
        ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':900})
        ctx.request.post(BASE+'/api/workspace/bootstrap');page=ctx.new_page();page.goto(BASE);page.locator('[data-history-boot="ready"]').wait_for()
        # Pause request dispatch only to expose real native uploading copy, without fabricating response.
        pending=[]
        page.route('**/api/meetings/file',lambda r:pending.append(r))
        page.locator('input[type=file]').set_input_files(str(TMP/'public-12s.wav'))
        page.get_by_role('button',name='Transcribe files and URLs',exact=True).click()
        page.wait_for_function("document.querySelector('[data-file-upload=results]').textContent.includes('Submitting')")
        for v in VIEWPORTS:
            page.set_viewport_size({'width':v[0],'height':v[1]});capture(page,out,'file-upload-progress','Actual file upload held before dispatch to observe progress copy; 12-second public corpus',records)
        for r in pending:r.continue_()
        page.wait_for_timeout(200)
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            meetings=ctx.request.get(BASE+'/api/meetings').json()['meetings']
            if meetings and meetings[0]['status']!='active':break
            page.wait_for_timeout(500)
        saved=meetings[0];assert saved['status']=='completed',saved
        (OUT/'file-source.json').write_text(json.dumps(dict(saved=saved,provenance='Actual browser multipart upload; 12s public Bill Ackman corpus; real vLLM; final saved response'),indent=2)+'\n')
        print(json.dumps({'file_status':saved['status'],'segments':len(saved['transcript']['segments'])}),flush=True)
        browser.close()
    (out/'records.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':main()
