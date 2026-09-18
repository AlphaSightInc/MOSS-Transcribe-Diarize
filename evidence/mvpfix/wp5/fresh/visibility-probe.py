"""Throwaway WP5 probe: can native CDP controls make a headless page hidden?
Primitives: native page visibility, focus override, lifecycle command.
Invariant: no visibility-property overrides; no decoder, product, or shared state.
Falsifier of the current blocker: document.hidden becomes true.
One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. TMPDIR="$PWD/runs/wp5" <COMMON Python> evidence/mvpfix/wp5/fresh/visibility-probe.py
"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright
from tests.phase2.browser_support import browser_executable

async def main():
    out=Path('evidence/mvpfix/wp5/fresh/visibility-probe.json')
    assert not out.exists()
    result={'question':'Can native CDP focus/lifecycle controls unblock actual hidden-page measurement?', 'decoder_requests':0, 'spoofed_visibility':False, 'headless':True, 'samples':[]}
    async with async_playwright() as p:
        ignored=['--disable-backgrounding-occluded-windows','--disable-renderer-backgrounding','--disable-background-timer-throttling']
        result['removed_default_args']=ignored
        browser=await p.chromium.launch(executable_path=str(browser_executable(p)),channel='chromium',headless=True,ignore_default_args=ignored)
        try:
            result['browser_version']=browser.version
            context=await browser.new_context()
            page=await context.new_page()
            await page.goto('data:text/html,<title>WP5 visibility probe</title>native visibility')
            await page.evaluate("window.wp5events=[]; document.addEventListener('visibilitychange',()=>wp5events.push({hidden:document.hidden,visibility:document.visibilityState}))")
            cdp=await context.new_cdp_session(page)
            async def sample(action, error=None):
                await asyncio.sleep(.3)
                state=await page.evaluate('({hidden:document.hidden,visibility:document.visibilityState,focus:document.hasFocus(),events:window.wp5events})')
                result['samples'].append({'action':action,'error':error,**state})
                print(json.dumps(result['samples'][-1]),flush=True)
            await sample('initial')
            other=await context.new_page()
            await other.goto('data:text/html,<title>WP5 other tab</title>other')
            await other.bring_to_front()
            await sample('other-tab-front-background-disabling-flags-removed')
            for enabled in (True,False):
                await cdp.send('Emulation.setFocusEmulationEnabled',{'enabled':enabled})
                await other.bring_to_front()
                await sample('Emulation.setFocusEmulationEnabled '+str(enabled))
            error=None
            try:
                await cdp.send('Page.setWebLifecycleState',{'state':'hidden'})
            except Exception as exc:
                error=str(exc)
            await sample('Page.setWebLifecycleState hidden',error)
            result['hidden_observations']=sum(s['hidden'] for s in result['samples'])
            result['observations']=len(result['samples'])
            result['configuration_unblocked']=bool(result['hidden_observations'])
            result['case3_verdict']='BLOCKED' if not result['configuration_unblocked'] else 'UNMEASURED: hidden capability established; full capture case not run'
            await context.close()
        finally:
            await browser.close()
    result['browser_closed']=True
    out.write_text(json.dumps(result,indent=2)+'\n')

asyncio.run(main())
