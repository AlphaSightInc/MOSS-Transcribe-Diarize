"""PROTOTYPE — current -> base 37979e53 -> current on the same copied state."""
import json,shutil
from playwright.sync_api import sync_playwright
import journeys
from journeys import ROOT,SCRATCH,OUT,rows,copy_state,start,stop,browser_executable,verify_browser

def main():
    state=SCRATCH/'rollback';copy_state(SCRATCH/'idle-backups/lead-perlane',state)
    base=SCRATCH/'base'; launcher='prototypes/streaming-diarization/draft-lane/run_local_stack.py'
    (base/launcher).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/launcher,base/launcher)
    journeys.BASE='https://127.0.0.1:18133'
    result={}; initial=rows(state/'phase2.sqlite')
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(browser_executable(p)),headless=True)
        for name,code_root in [('integrated_before',ROOT),('base_37979e53',base),('integrated_after',ROOT)]:
            proc,c,latency=start(state,budget=0,code_root=code_root,port=18133)
            try:
                r=verify_browser(browser,c,state,name);r['startup_seconds']=latency;r['all_rows_unchanged']=initial==rows(state/'phase2.sqlite');result[name]=r
            except Exception as e:result[name]={'exception':type(e).__name__,'all_rows_unchanged':initial==rows(state/'phase2.sqlite')}
            finally:stop(proc);c.close()
            (OUT/'rollback.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({name:result[name]}),flush=True)
        browser.close()

if __name__=='__main__':main()
