"""45s of genuine hidden-tab capture with Playwright's focus/timer overrides removed."""
import argparse,asyncio,importlib.util,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from driver import unfocused_driver
spec=importlib.util.spec_from_file_location('e2e',ROOT/'tests/e2e/verify_workspace.py')
e2e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e2e)

class BackgroundHarness(e2e.Harness):
    async def start_live(self,key):
        # Real tab capture can focus the shared source; return as a presenter would.
        await self.page.bring_to_front()
        await self.page.wait_for_function('document.visibilityState==="visible"')
        return await super().start_live(key)

    async def network_outages(self):
        # Reuse only the standalone harness's launch/account/capture plumbing. This is
        # a separately labelled background probe, not another network outage verdict.
        beats=[];frames=[]
        def response(r):
            if r.status==200 and r.url.endswith('/heartbeat'):beats.append(time.monotonic())
            if r.status==200 and r.url.endswith('/frames'):frames.append(time.monotonic())
        self.page.on('response',response)
        await self.setup_live();ident=await self.start_live('background')
        await self.page.wait_for_function('document.querySelectorAll(".utt-text").length>0',timeout=35000)
        await self.page.evaluate('''() => {
          window.__timerSamples=[];let last=performance.now();
          window.__timer=setInterval(()=>{let now=performance.now();window.__timerSamples.push(now-last);last=now;},100);
        }''')
        await self.source.bring_to_front()
        await self.page.wait_for_function('document.visibilityState==="hidden"')
        hidden_at=time.monotonic()
        await asyncio.sleep(45)
        still_hidden=await self.page.evaluate('document.visibilityState')
        phase=await self.page.locator('[data-capture-phase]').get_attribute('data-capture-phase')
        snapshot=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body']['snapshot']['session']
        shown_at=time.monotonic();await self.page.bring_to_front()
        timers=await self.page.evaluate('clearInterval(window.__timer);window.__timerSamples')
        hidden_beats=[t for t in beats if hidden_at<=t<=shown_at]
        result={'probe':'45s genuine hidden capture','meeting':ident,'hidden_seconds':shown_at-hidden_at,
                'visibility_after_wait':still_hidden,'phase_after_wait':phase,'session_status':snapshot['status'],
                'failure_reason':snapshot.get('failure_reason'),'heartbeat_responses_hidden':len(hidden_beats),
                'frame_responses_hidden':sum(hidden_at<=t<=shown_at for t in frames),
                'maximum_heartbeat_gap_seconds':max((b-a for a,b in zip(beats,beats[1:])),default=None),
                'timer_callbacks':len(timers),'timer_interval_ms_median':__import__('statistics').median(timers),
                'timer_interval_ms_max':max(timers),'focus_emulation':False,'background_throttling_disabled':False}
        (self.out/'background.json').write_text(json.dumps(result,indent=2)+'\n')
        if phase=='active':await self.page.get_by_role('button',name='Stop and finalize',exact=True).click()
        meeting=await self.terminal(ident,240)
        final=(await self.api(f'/api/live/sessions/{ident}/snapshot'))['body']['snapshot']['session']
        result.update(terminal_meeting=meeting['status'],finalization_status=final['finalization_status'])
        result['ok']=(still_hidden=='hidden' and phase=='active' and snapshot['status']=='active' and len(hidden_beats)>45 and result['maximum_heartbeat_gap_seconds']<30 and meeting['status']=='completed' and final['finalization_status']=='final')
        (self.out/'background.json').write_text(json.dumps(result,indent=2)+'\n')
        return result

async def run(args):
    from playwright.async_api import BrowserType
    original=BrowserType.launch
    async def launch(self,*a,**kw):
        kw['headless']=False
        kw['ignore_default_args']=['--mute-audio','--disable-background-timer-throttling',
                                  '--disable-backgrounding-occluded-windows','--disable-renderer-backgrounding']
        return await original(self,*a,**kw)
    BrowserType.launch=launch
    try:return await BackgroundHarness(args).run()
    finally:BrowserType.launch=original

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',default='https://127.0.0.1:17861');p.add_argument('--corpus',required=True);p.add_argument('--output',required=True)
    args=p.parse_args();args.rows='13';args.new_workspace=True
    with unfocused_driver():raise SystemExit(asyncio.run(run(args)))
