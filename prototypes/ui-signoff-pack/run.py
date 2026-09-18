"""PROTOTYPE absorbed as WP24 capture bench. No product state or policy added.
Question: does each reachable state render truthfully and legibly at three viewports?
Primitives: source state (truth), viewport (constraint), rendered DOM/PNG (observation).
Invariant: unchanged built assets; never call fidelity gate; provenance on every capture.
Falsifier: misleading copy, unnamed controls, AA failure, or inaccessible clipped content.
Tool decision: Chromium measures actual rendering; saved source envelopes replay rare states
without further decoder calls. Replay demonstrates presentation, not fresh backend execution.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/ui-signoff-pack/run.py
"""
import argparse, copy, json, sys, time, os, shutil
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright
from tests.phase2.browser_support import browser_executable
from moss_transcribe_diarize.app.phase2 import _workspace_html, Meeting
OUT=Path(os.environ.get('WP24_EVIDENCE_ROOT',str(ROOT/'evidence/mvpfix/wp24'))); VIEWPORTS=[(1440,900),(1280,800),(400,844)]
AUDIT=(Path(__file__).with_name('audit.js')).read_text()

def capture(page,out,state,origin,records,*,copy_verdict='Copy agrees with supplied state; fixture provenance does not verify the backend cause'):
    page.evaluate('document.fonts.ready');page.wait_for_timeout(100)
    v=page.viewport_size; name=f"{state}-{v['width']}x{v['height']}"
    page.screenshot(path=str(out/f'{name}.png'),full_page=True)
    result=page.evaluate(AUDIT)
    ax=page.context.new_cdp_session(page); tree=ax.send('Accessibility.getFullAXTree')['nodes'];ax.detach()
    interactive={'button','link','textbox','combobox','checkbox','tab','menuitem','spinbutton','searchbox'}
    result['missing_accessible_names']=[{'role':n.get('role',{}).get('value'),'backend_node':n.get('backendDOMNodeId')} for n in tree if not n.get('ignored') and n.get('role',{}).get('value') in interactive and not n.get('name',{}).get('value')]
    result.update(state=state,viewport=v,screenshot=name+'.png',provenance=origin,copy_verdict=copy_verdict)
    (out/f'{name}.txt').write_text(result['visible_copy']+'\n')
    records.append(result)
    print(json.dumps({'state':state,'width':v['width'],'horizontal_scroll':result['horizontal_scroll'],'unnamed':len(result['missing_accessible_names']),'contrast_failures':len([x for x in result['contrast'] if x['result']=='fail'])}),flush=True)

def meeting_fixture(id='fixture',**kw):
    return dict(id=id,mode='file',title='Public corpus review',title_source='manual',status='completed',created_at_ms=1789700400000,transcript={'segments':[]},transcript_version=1,audio=None,**kw)

def fixture_page(browser,v,meetings,*,snapshot=None,voiceprints=None,summary=None,reattach=None):
    page=browser.new_page(viewport={'width':v[0],'height':v[1]})
    html=_workspace_html(SimpleNamespace(display_name='WP24 review workspace'),[],live_enabled=True)
    def route(r):
        path=urlsplit(r.request.url).path
        if path=='/':r.fulfill(body=html,content_type='text/html')
        elif path.startswith(('/static/','/fonts/')):
            asset=ROOT/'moss_transcribe_diarize/app/frontend_assets'/path.removeprefix('/static/').lstrip('/')
            r.fulfill(path=str(asset)) if asset.is_file() else r.fulfill(status=404)
        elif path=='/api/meetings':r.fulfill(json={'meetings':meetings})
        elif path=='/api/voiceprints':r.fulfill(json=voiceprints or {'voiceprints':[]})
        elif path=='/api/llm/models':r.fulfill(json={'data':[]})
        elif path.endswith('/summary'):r.fulfill(json={'summary':summary})
        elif path.endswith('/snapshot'):r.fulfill(json=snapshot or {})
        elif '/events' in path:r.fulfill(json={'events':[],'last_sequence':0})
        elif path.startswith('/api/meetings/'):
            obj=next((x for x in meetings if x['id']==path.split('/')[3]),meetings[0] if meetings else {})
            r.fulfill(json=obj)
        else:r.fulfill(json={})
    page.route('**/*',route)
    if reattach:page.add_init_script('sessionStorage.setItem("lt:session:reattach",'+json.dumps(json.dumps({'sessionId':reattach}))+')')
    page.goto('http://wp24.test');page.locator('[data-history-boot="ready"]').wait_for()
    return page

def open_meeting(page,id):
    page.locator(f'[data-open-meeting="{id}"]').click();page.wait_for_timeout(200)

def write_index(out,records):
    grouped={}
    for r in records:grouped.setdefault(r['state'],[]).append(r)
    assert len(grouped)==52, sorted(grouped)
    assert all(len(rows)==3 for rows in grouped.values())
    lines=['# WP24 owner sign-off checklist','','52 states × 3 viewports. Owner acceptance remains pending.',
           'Real sources, replay, and fixtures are labelled. Native OS picker is not observable in headless Chromium.',
           'See [audit](../AUDIT.md) for fixes, deferred findings, measurement limits and keyboard results.','',
           '| Owner | State | 1440×900 | 1280×800 | 400×844 | Provenance |',
           '|---|---|---|---|---|---|']
    for state,rows in grouped.items():
        links=[]
        for r in rows:links.append(f"[PNG]({r['screenshot']}) / [copy]({r['screenshot'].replace('.png','.txt')})")
        lines.append('| [ ] | '+state+' | '+' | '.join(links)+' | '+rows[0]['provenance']+' |')
    lines+=['',f"Captures: {len(records)}. Metadata: [pack.json](pack.json).",'',
            'Reference oracle screenshots: [1440](../extra/reference-1440x900.png), [1280](../extra/reference-1280x800.png), [400](../extra/reference-400x844.png).',
            'The operator-reserved shell fidelity gate was not run. No visual acceptance is inferred from automated checks.']
    (out/'index.md').write_text('\n'.join(lines)+'\n')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=OUT/'pack');ap.add_argument('--initial',action='store_true');args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True);records=[]
    live=json.loads((OUT/'live-source.json').read_text()) if (OUT/'live-source.json').exists() else None
    file=json.loads((OUT/'file-source.json').read_text()) if (OUT/'file-source.json').exists() else None
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(browser_executable(p)),args=['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream'])
        for v in VIEWPORTS:
            page=fixture_page(browser,v,[])
            capture(page,out,'empty-workspace','Real integrated HTML/assets; empty API fixture',records)
            page.get_by_label('Listening').select_option('headphones')
            capture(page,out,'listening-headphones','Native control, no capture device started',records)
            page.get_by_label('Listening').select_option('speakers')
            capture(page,out,'listening-speakers','Native control, no capture device started',records)
            page.close()
            if args.initial:continue
            if live:
                saved=live['saved'];page=fixture_page(browser,v,[saved],voiceprints=live['voiceprints']);open_meeting(page,saved['id'])
                capture(page,out,'live-final','Replayed genuine vLLM saved meeting: '+live['provenance'],records)
                page.get_by_role('button',name='Export transcript',exact=True).click()
                capture(page,out,'exports-menu','Genuine saved transcript; native export menu',records);page.keyboard.press('Escape')
                page.locator('.legend-chip:not([disabled])').first.click()
                capture(page,out,'speaker-rename-save-voiceprint','Native dialog on genuine saved meeting; voiceprint save affordance',records,copy_verdict='Corrected: naming applies throughout this meeting, including saved meetings. Shared privacy copy remains D3-deferred.')
                page.get_by_role('button',name='Cancel',exact=True).click()
                page.get_by_role('tab',name='Voiceprints',exact=True).click();page.wait_for_timeout(200)
                capture(page,out,'voiceprint-bank','Replayed bank created through real enrollment API',records)
                page.get_by_role('tab',name='Sessions',exact=True).click()
                page.locator('.history-card-actions').first.get_by_role('button',name='Rename',exact=True).click()
                capture(page,out,'meeting-rename','Native dialog on genuine saved meeting',records);page.close()
                snaps=live['snapshots']; active=[s for s in snaps if s['snapshot']['session']['status']=='active']
                # Choose retained production envelopes by actual state, never invent transcript rows.
                for state,select in [('active-two-lanes',lambda s:s['snapshot']['session']['status']=='active' and len({r.get('source_lane') for r in s['snapshot']['session'].get('effective_transcript',[])})==2),('provisional-rows',lambda s:bool(s['snapshot']['session'].get('provisional') or s['snapshot']['session'].get('draft'))),('finalizing',lambda s:s['snapshot']['session'].get('finalization_status')=='running')]:
                    found=[s for s in snaps if select(s)]
                    if not found:
                        print(json.dumps({'missing_state':state}),flush=True);continue
                    s=found[-1];page=fixture_page(browser,v,[saved],snapshot=s,reattach=saved['id']);page.wait_for_timeout(400)
                    capture(page,out,state,'Replayed unmodified production snapshot from real overlap capture',records);page.close()
            if file:
                saved=file['saved'];page=fixture_page(browser,v,[saved]);open_meeting(page,saved['id'])
                capture(page,out,'file-final','Replayed genuine file upload and vLLM decode',records)
                page.get_by_role('button',name='Generate summary',exact=True).click()
                capture(page,out,'summary-unconfigured','Native no-provider explanation on genuine file meeting',records)
                page.get_by_role('button',name='Optional AI summaries · off',exact=True).click()
                capture(page,out,'summary-settings','Native external-provider settings',records)
                page.get_by_label('Provider HTTPS URL',exact=True).fill('https://provider.invalid/v1');page.get_by_label('Model',exact=True).fill('review-fake-model')
                capture(page,out,'summary-provider-no-key','Native settings with provider/model but empty optional key; no provider request',records)
                page.close()
                for state in ['queued','generating','retry_wait','current','failed','cancelled']:
                    artifact=dict(state=state,attempt_id='wp24-fake-summary',source_version=saved['transcript_version'],artifact_version=1,error_code='provider_unavailable' if state=='failed' else None,document=dict(summary='FAKE ENDPOINT REVIEW: the public interview discusses investment decisions.',topics=[],details=[],speaker_background=[],data_references=[]) if state=='current' else None)
                    page=fixture_page(browser,v,[saved],summary=artifact);open_meeting(page,saved['id']);page.wait_for_timeout(200)
                    capture(page,out,'summary-'+state,'Explicit fake summary endpoint response; presentation only',records);page.close()
            interrupted_path=OUT/'interrupted-source.json'
            if interrupted_path.exists():
                data=json.loads(interrupted_path.read_text());page=fixture_page(browser,v,[data['saved']],snapshot=data['snapshot'],reattach=data['saved']['id']);page.wait_for_timeout(400)
                capture(page,out,'interrupted-lease-expiry',data['provenance']+' Unmodified snapshot replay.',records);page.close()
            failures=json.loads((Path(__file__).with_name('failures.json')).read_text())
            for code,reason in failures.items():
                m=meeting_fixture(id=code);m.update(status='failed',failure_code=code if code in {'acquisition_timeout','acquisition_http_403','acquisition_http_404','transcode_failed','decode_failed','decode_invalid','storage_failed'} else 'acquisition_failed',failure_reason=reason)
                page=fixture_page(browser,v,[m]);open_meeting(page,m['id']);capture(page,out,'failure-'+code,'Explicit API fixture from production failure mapping; failure NOT induced',records);page.close()
            for state,notice in [('no-speech','No speech detected.'),('truncation','The speech decoder reached its output limit. This transcript may be incomplete.')]:
                m=copy.deepcopy(file['saved'] if file else meeting_fixture());m['notice']=notice
                if state=='no-speech':m['transcript']={'segments':[]}
                page=fixture_page(browser,v,[m]);open_meeting(page,m['id']);capture(page,out,state,'Explicit outcome fixture using exact production notice; condition NOT induced',records);page.close()
            for state in ['available','partial','unavailable']:
                m=copy.deepcopy(file['saved'] if file else meeting_fixture());m['audio']=dict(state=state,relative_path='review.mp3' if state!='unavailable' else None,byte_count=100,duration_ms=1000,format='mp3',sample_rate_hz=16000,channels=1,bit_rate_bps=48000)
                page=fixture_page(browser,v,[m]);capture(page,out,'audio-'+state,'Explicit audio-state fixture; download contents not validated by this screenshot',records);page.close()
            rows=[]
            for i in range(60):
                m=copy.deepcopy(file['saved'] if file else meeting_fixture());m.update(id=f'history-{i}',title=f'Review meeting {i+1:02d}',created_at_ms=1789700400000-i*60000);rows.append(m)
            page=fixture_page(browser,v,rows);capture(page,out,'history-60','60 explicit history fixtures; real public transcript reused',records)
            page.get_by_role('tab',name='Voiceprints',exact=True).click();capture(page,out,'history-to-voiceprints','Native tab transition from 60-row fixture',records);page.close()
        browser.close()
    for folder in ('browser','live-browser','extra'):
        extra=OUT/folder/'records.json'
        if extra.exists():
            for record in json.loads(extra.read_text()):
                records.append(record)
                for suffix in ('.png','.txt'):
                    filename=Path(record['screenshot']).with_suffix(suffix).name
                    shutil.copyfile(extra.parent/filename,out/filename)
    (out/'pack.json').write_text(json.dumps({'viewports':VIEWPORTS,'captures':records},indent=2)+'\n')
    write_index(out,records)

if __name__=='__main__':
    if '--regenerate' in sys.argv:
        from regenerate import main as regenerate
        regenerate()
    else:main()
