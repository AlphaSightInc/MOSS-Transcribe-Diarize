"""WP24 regressions: narrow outcome header and selected-history body-text contrast."""
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import pytest
from playwright.sync_api import sync_playwright
from moss_transcribe_diarize.app.phase2 import _workspace_html, Meeting
from tests.phase2.browser_support import require_browser

ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('width,height', [(1440,900),(1280,800),(400,844)])
@pytest.mark.parametrize('notice', [
    'Media could not be decoded. The format may be unsupported or damaged.',
    'The speech decoder reached its output limit. This transcript may be incomplete.',
])
def test_outcome_header_stays_inside_viewport_and_selected_copy_has_aa_contrast(width,height,notice):
    meeting=Meeting('review','file','Public corpus review','completed',1,transcript={'segments':[]},notice=notice)
    html=_workspace_html(SimpleNamespace(display_name='Review'),[],live_enabled=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page=browser.new_page(viewport={'width':width,'height':height})
            def route(r):
                path=urlsplit(r.request.url).path
                if path=='/':r.fulfill(body=html,content_type='text/html')
                elif path.startswith(('/static/','/fonts/')):
                    r.fulfill(path=str(ROOT/'moss_transcribe_diarize/app/frontend_assets'/path.removeprefix('/static/').lstrip('/')))
                elif path=='/api/meetings':r.fulfill(json={'meetings':[meeting.to_dict()]})
                elif path=='/api/meetings/review':r.fulfill(json=meeting.to_dict())
                else:r.fulfill(json={'summary':None,'voiceprints':[],'data':[]})
            page.route('**/*',route);page.goto('http://review.test')
            page.locator('[data-open-meeting="review"]').click();page.locator('.history-card.is-active').wait_for();page.evaluate('document.fonts.ready')
            result=page.evaluate('''() => {
                const status=document.querySelector('.top-status').getBoundingClientRect();
                const title=document.querySelector('.session-meta').getBoundingClientRect();
                const canvas=document.createElement('canvas');canvas.width=canvas.height=1;
                const ctx=canvas.getContext('2d');
                const rgba=s=>{ctx.clearRect(0,0,1,1);ctx.fillStyle=s;ctx.fillRect(0,0,1,1);return [...ctx.getImageData(0,0,1,1).data]};
                const lum=c=>c.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((a,x,i)=>a+x*[.2126,.7152,.0722][i],0);
                const ratios=[...document.querySelectorAll('.history-card.is-active .history-card-meta,.history-card.is-active .history-card-subtitle')].map(e=>{
                  const chain=[];for(let n=e;n;n=n.parentElement)chain.unshift(n);
                  let bg=[255,255,255];for(const n of chain){const c=rgba(getComputedStyle(n).backgroundColor),a=c[3]/255;bg=bg.map((v,i)=>c[i]*a+v*(1-a));}
                  const fg=rgba(getComputedStyle(e).color);return (Math.max(lum(fg),lum(bg))+.05)/(Math.min(lum(fg),lum(bg))+.05);
                });
                return {width:document.documentElement.scrollWidth,viewport:innerWidth,statusRight:status.right,titleLeft:title.left,titleRight:title.right,transcriptLeft:document.querySelector('.transcript-shell').getBoundingClientRect().left,ratios};
            }''')
            assert result['width']<=result['viewport'],result
            assert result['statusRight']<=result['titleLeft']+1,result
            assert result['titleRight']<=result['viewport'],result
            if width>1024: assert result['statusRight']<=result['transcriptLeft'],result
            assert len(result['ratios'])==2
            assert min(result['ratios'])>=4.5,result
        finally:browser.close()


def test_enabled_stop_button_text_has_aa_contrast():
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page=browser.new_page()
            page.set_content('<div class="control-panel"><button class="record-btn" data-action="stop"><span>Stop and finalize</span></button></div>')
            page.add_style_tag(path=str(ROOT/'moss_transcribe_diarize/app/frontend_assets/styles.css'))
            page.add_style_tag(content='button { transition: none !important; }')
            colors=page.locator('button').evaluate('e=>[getComputedStyle(e).color,getComputedStyle(e).backgroundColor]')
            import re
            def luminance(color):
                rgb=[int(v)/255 for v in re.findall(r'\d+',color)[:3]]
                return sum((v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)*weight for v,weight in zip(rgb,[.2126,.7152,.0722]))
            light,dark=sorted(map(luminance,colors),reverse=True)
            assert (light+.05)/(dark+.05)>=4.5,colors
        finally:browser.close()
