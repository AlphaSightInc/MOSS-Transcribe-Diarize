"""Genuine browser capture lifecycle; public WAV streams replace physical devices only."""
import os,json,sys,time,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from run import capture,VIEWPORTS
from playwright.sync_api import sync_playwright
from tests.phase2.browser_support import browser_executable
from tests.e2e.verify_demo_lanes import reference_inputs
OUT=Path(os.environ.get('WP24_EVIDENCE_ROOT',str(ROOT/'evidence/mvpfix/wp24')));TMP=ROOT/'.wp24';BASE='https://127.0.0.1:17884'
def main():
    out=OUT/'live-browser';out.mkdir(exist_ok=True);records=[]
    for lane,row in reference_inputs(.03).items():
        with wave.open(str(TMP/f'{lane}.wav'),'wb') as dst:
            dst.setparams((1,2,16000,0,'NONE','not compressed'));dst.writeframes(row['pcm'])
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(browser_executable(p)),args=['--autoplay-policy=no-user-gesture-required','--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream','--use-file-for-fake-audio-capture='+str(TMP/'microphone.wav')])
        ctx=browser.new_context(ignore_https_errors=True,viewport={'width':1440,'height':900},permissions=['microphone'])
        ctx.request.post(BASE+'/api/workspace/bootstrap');page=ctx.new_page()
        page.route('**/wp24-system.wav',lambda r:r.fulfill(path=str(TMP/'system.wav'),content_type='audio/wav'))
        page.route('**/wp24-microphone.wav',lambda r:r.fulfill(path=str(TMP/'microphone.wav'),content_type='audio/wav'))
        page.goto(BASE);page.locator('[data-history-boot="ready"]').wait_for()
        page.evaluate('''() => {const publicStream=async(lane)=>{
          const context=new AudioContext();await context.resume();
          const buffer=await context.decodeAudioData(await (await fetch('/wp24-'+lane+'.wav')).arrayBuffer());
          const source=context.createBufferSource();source.buffer=buffer;source.loop=true;
          const dest=context.createMediaStreamDestination();source.connect(dest);source.start();
          window.wp24Media??=[];window.wp24Media.push({context,source});return dest.stream;
        };navigator.mediaDevices.getDisplayMedia=()=>publicStream('system');navigator.mediaDevices.getUserMedia=()=>publicStream('microphone');}''')
        page.get_by_label('Listening setup').select_option('headphones')
        page.get_by_role('button',name='Enable microphone',exact=True).click()
        page.wait_for_function("document.querySelector('.capture-status').textContent.startsWith('Microphone connected')")
        page.get_by_role('button',name='Share audio',exact=True).click()
        page.wait_for_timeout(3000)
        print(page.locator('.capture-supervisor').inner_text(),flush=True)
        page.get_by_role('button',name='Start capture',exact=True).click(timeout=20000)
        page.locator('.utt-lane',has_text='Microphone').first.wait_for(timeout=60000);page.locator('.utt-lane',has_text='System').first.wait_for(timeout=60000)
        for v in VIEWPORTS:
            page.set_viewport_size({'width':v[0],'height':v[1]});capture(page,out,'browser-active-overlap','Real browser CaptureClient → real vLLM. WebAudio fake microphone + display streams carry public human speech; no injected transcript.',records)
        # Hold only the Stop response to preserve the genuine stopping state at all widths.
        pending=[];page.route('**/api/live/sessions/*/stop',lambda r:pending.append(r))
        page.get_by_role('button',name='Stop and finalize',exact=True).click()
        for v in VIEWPORTS:
            page.set_viewport_size({'width':v[0],'height':v[1]});capture(page,out,'browser-stop-finalizing','Actual Stop action; response dispatch held for screenshots. Production local drain runs unchanged.',records)
        for r in pending:r.continue_()
        page.get_by_role('button',name='Reset capture',exact=True).wait_for(timeout=120000)
        for v in VIEWPORTS:
            page.set_viewport_size({'width':v[0],'height':v[1]});capture(page,out,'browser-final','Actual browser Stop → terminal completion with real decoder',records)
        meetings=ctx.request.get(BASE+'/api/meetings').json()['meetings']
        (OUT/'browser-live-source.json').write_text(json.dumps({'meetings':meetings,'provenance':'Real browser capture with public WAV fake devices; real decoder'},indent=2)+'\n')
        browser.close()
    (out/'records.json').write_text(json.dumps(records,indent=2)+'\n')
if __name__=='__main__':main()
