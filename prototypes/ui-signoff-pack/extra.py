"""Shared-mode copy, reference oracle, and native keyboard traversal evidence."""
import os,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
from run import *
def main():
    out=OUT/'extra';out.mkdir(exist_ok=True);records=[];keyboard=[]
    with sync_playwright() as p:
        b=p.chromium.launch(executable_path=str(browser_executable(p)))
        for v in VIEWPORTS:
            ctx=b.new_context(ignore_https_errors=True,viewport={'width':v[0],'height':v[1]});pg=ctx.new_page();pg.goto('https://127.0.0.1:17885');pg.locator('[data-history-boot="ready"]').wait_for()
            capture(pg,out,'shared-workspace-header','Actual open_workspace=True isolated instance, no cookie needed',records,copy_verdict='D3 DEFERRED: private-browser and history-access claims mismatch shared workspace')
            pg.get_by_role('tab',name='Voiceprints',exact=True).click();capture(pg,out,'shared-voiceprints','Actual open_workspace=True instance',records,copy_verdict='D3 DEFERRED: Private voiceprints / Private to this browser workspace mismatch shared ownership');ctx.close()
            pg=b.new_page(viewport={'width':v[0],'height':v[1]});pg.goto('http://127.0.0.1:17886');pg.wait_for_timeout(1500);pg.evaluate('document.fonts.ready');pg.screenshot(path=str(out/f'reference-{v[0]}x{v[1]}.png'),full_page=True);pg.close()
            live=json.loads((OUT/'live-source.json').read_text());pg=fixture_page(b,v,[live['saved']],voiceprints=live['voiceprints']);open_meeting(pg,live['saved']['id'])
            pg.locator('.legend-chip:not([disabled])').first.click();pg.locator('dialog[open] #speaker-name-input').wait_for();pg.wait_for_function("document.activeElement.id === 'speaker-name-input'");sequence=[]
            for _ in range(8):
                sequence.append(pg.evaluate('''() => {const e=document.activeElement;return {tag:e.tagName,id:e.id,name:e.getAttribute('aria-label')||e.innerText||e.labels?.[0]?.innerText||'',insideDialog:!!e.closest('dialog')}}'''));pg.keyboard.press('Tab')
            assert all(x['insideDialog'] or x['tag']=='BODY' for x in sequence),sequence
            # Chromium cycles through browser chrome (BODY active), not background controls.
            for x in sequence:
                if x['tag']=='BODY':x['name']='Browser chrome transition'
            pg.keyboard.press('Escape');pg.locator('dialog').wait_for(state='detached');pg.wait_for_timeout(100);restored=pg.evaluate("document.activeElement.matches('.legend-chip')")
            keyboard.append(dict(viewport=v,dialog_focus_cycle=sequence,focus_restored_to_trigger=restored));pg.close()
        b.close()
    (out/'records.json').write_text(json.dumps(records,indent=2)+'\n');(OUT/'keyboard.json').write_text(json.dumps(keyboard,indent=2)+'\n')
if __name__=='__main__':main()
