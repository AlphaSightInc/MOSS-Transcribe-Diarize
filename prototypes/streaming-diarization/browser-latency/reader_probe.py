"""Real bundled reader, controlled readiness phases; no provider or database operations."""
import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from tests.phase2.browser_support import browser_executable
from moss_transcribe_diarize.app.phase2 import _workspace_html

def main():
 p=argparse.ArgumentParser();p.add_argument('--before',required=True);p.add_argument('--after',required=True);p.add_argument('--out',required=True);args=p.parse_args()
 results=[]
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=str(browser_executable(pw)))
  try:
   for arm,bundle in [('before',args.before),('after',args.after)]:
    for phase in (10,50,90,130,170,210,240):
     page=browser.new_page();page.add_init_script(path=str(Path(__file__).with_name('instrument.js')))
     ready_at=None
     def route(r):
      nonlocal ready_at
      path=urlsplit(r.request.url).path
      if path=='/':r.fulfill(body=_workspace_html(SimpleNamespace(display_name='Latency bench'),[],live_enabled=True),content_type='text/html')
      elif path=='/static/app.js':r.fulfill(path=bundle,content_type='application/javascript')
      elif path.startswith('/static/'):
       asset=ROOT/'moss_transcribe_diarize/app/frontend_assets'/path.removeprefix('/static/')
       r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
      elif path.endswith('/snapshot'):
       now=page.evaluate('performance.now()')
       if ready_at is None:ready_at=now+phase
       ready=now>=ready_at
       r.fulfill(json={'snapshot':{'session_id':'timed','descriptor':{'sample_rate':16000},
        'session':{'status':'active','version':2 if ready else 1,'committed_samples':16000 if ready else 0,
         'identity_snapshot':{'canonical_speakers':[]},'provisional':None,
         'committed':[{'span_id':0,'start_sample':0,'transcript':'[0][S00]fixture[1]','revised_transcript':None}] if ready else []}}})
      else:r.fulfill(json={'events':[],'meetings':[],'voiceprints':[],'summary':None})
     page.route('**/*',route);page.goto('http://latency.test');page.locator('[data-observer-mode]').wait_for()
     page.evaluate("document.dispatchEvent(new CustomEvent('moss:observe-live-meeting',{detail:{meetingId:'timed'}}))")
     page.wait_for_function("window.__mossTimings.some(r=>r.kind==='dom')")
     rows=page.evaluate('window.__mossTimings');dom=next(r['t'] for r in rows if r['kind']=='dom')
     snapshot=next(r['t'] for r in rows if r['kind']=='json' and r.get('committed')==16000)
     results.append(dict(arm=arm,phase_ms=phase,ready_to_dom_ms=round(dom-ready_at,3),snapshot_to_dom_ms=round(dom-snapshot,3)))
     page.close()
  finally:browser.close()
 Path(args.out).write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results))
if __name__=='__main__':main()
