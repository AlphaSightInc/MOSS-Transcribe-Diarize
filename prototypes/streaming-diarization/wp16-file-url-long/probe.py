"""PROTOTYPE: real browser file/URL state -> durable saved result, failure and exports.
Run: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> <this-file> CASE [CASE ...]
Cases: long.wav long.mp3 long.m4a empty.wav text.mp3 truncated.mp3 silence.wav two.wav
       direct youtube commons missing html hang concurrent
State is scratch-only except compact evidence; no mocked product requests.
"""
import argparse, asyncio, json, os, re, sys, time
from pathlib import Path
import httpx
from playwright.async_api import async_playwright
from tests.phase2.browser_support import browser_executable
from tests.e2e.export_oracle import compare_export
from moss_transcribe_diarize.lane_word_oracle import words, distance
ROOT=Path('.wp16runtime'); EVID=Path('evidence/mvpfix/wp16'); BASE='https://127.0.0.1:17876'
METRICS='http://127.0.0.1:18116/metrics'
ALLOW_CONTENTION=False
URLS={'direct':'https://127.0.0.1:17877/short.mp3','youtube':'https://www.youtube.com/watch?v=UNP03fDSj1U',
'commons':'https://upload.wikimedia.org/wikipedia/commons/5/52/En-us-hello.ogg',
'missing':'https://127.0.0.1:17877/not-present.wav','html':'https://127.0.0.1:17877/index.html','hang':'http://127.0.0.1:17878/hang'}
def emit(row):
    print(json.dumps(row),flush=True)
    with (EVID/'events.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
async def fetch(page,path):
    return await page.evaluate('async p => {let r=await fetch(p); return {status:r.status,body:await r.json()}}',path)
async def run_case(browser,name,tag=None):
    tag=tag or name
    context=await browser.new_context(ignore_https_errors=True,accept_downloads=True)
    page=await context.new_page(); page.set_default_timeout(20000)
    await page.goto(BASE); await page.locator('[data-history-boot="ready"]').wait_for()
    statepath=ROOT/(tag+'.state.json'); await context.storage_state(path=str(statepath))
    row=dict(case=tag,source=name,duration_seconds=1800 if name.startswith('long.') else None)
    started=time.monotonic(); row['started_monotonic']=started
    async with httpx.AsyncClient() as client:
        metrics=(await client.get(METRICS)).text
        row['queue_before']=[s for s in metrics.splitlines() if s.startswith(('vllm:num_requests_running{','vllm:num_requests_waiting{'))]
    if any(float(s.rsplit(' ',1)[1])>0 for s in row['queue_before'] if 'num_requests_waiting{' in s):
        emit(dict(case=tag,action='queue_busy',metrics=row['queue_before']))
        if not ALLOW_CONTENTION:raise RuntimeError('Shared GPU queue busy; reschedule')
    if name in URLS: await page.locator('textarea[name="urls"]').fill(URLS[name]); endpoint='/api/meetings/url'
    else: await page.locator('input[name="file"]').set_input_files(str(ROOT/'media'/name)); endpoint='/api/meetings/file'
    async with page.expect_response(lambda r:r.url.endswith(endpoint) and r.request.method=='POST',timeout=120000) as accepted:
        await page.get_by_role('button',name='Transcribe files and URLs',exact=True).click()
    response=await accepted.value; initial=await response.json()
    row.update(http_status=response.status,accepted_seconds=time.monotonic()-started)
    if 'id' not in initial:
        row.update(refusal=initial,meeting_created=False); emit(row); await context.close(); return row
    mid=initial['id']; row['meeting_id']=mid
    emit(dict(case=tag,action='accepted',elapsed=row['accepted_seconds'],status=initial['status'],id=mid))
    last=None
    while True:
        result=await fetch(page,f'/api/meetings/{mid}'); meeting=result['body']
        state=(meeting['status'],meeting.get('failure_code'),meeting.get('notice'))
        if state!=last:
            emit(dict(case=tag,action='state',elapsed=time.monotonic()-started,status=state[0],failure_code=state[1],notice=state[2]))
            row.setdefault('first_status_seconds',time.monotonic()-started); last=state
        if meeting['status']!='active': break
        if time.monotonic()-started>7200: raise TimeoutError(tag)
        await asyncio.sleep(2)
    row.update(elapsed_seconds=time.monotonic()-started,status=meeting['status'],failure_code=meeting.get('failure_code'),failure_reason=meeting.get('failure_reason'),notice=meeting.get('notice'),audio=meeting.get('audio'))
    (ROOT/(tag+'.meeting.json')).write_text(json.dumps(meeting))
    segments=(meeting.get('transcript') or {}).get('segments',[])
    row.update(segments=len(segments),saved_words=sum(len(words(s['text'])) for s in segments),speakers=len({s.get('speaker_entity_id') or s['speaker'] for s in segments}),last_segment_end=max((s['end'] for s in segments),default=None))
    await page.reload(); await page.locator('[data-history-boot="ready"]').wait_for()
    await page.locator(f'[data-open-meeting="{mid}"]').wait_for()
    history=await page.locator(f'[data-open-meeting="{mid}"]').inner_text()
    await page.locator(f'[data-open-meeting="{mid}"]').click()
    await asyncio.sleep(.5)
    reason=row['failure_reason'] or row['notice']
    row['history_reason']=reason is None or reason in history
    header=await page.locator('.topbar').inner_text()
    row['header_reason']=reason is None or reason in header
    row['reason_content_free']=reason is None or not any(x in reason for x in ('http:','https:','/Users/','/private/','127.0.0.1'))
    row['reload_status']=(await fetch(page,f'/api/meetings/{mid}'))['body']['status']
    exports={}
    if segments:
        for fmt,label in [('md','Markdown (.md)'),('txt','Text (.txt)')]:
            await page.get_by_role('button',name='Export transcript',exact=True).click()
            async with page.expect_download() as pending: await page.get_by_role('menuitem',name=label,exact=True).click()
            download=await pending.value; path=ROOT/f'{tag}.{fmt}'; await download.save_as(str(path))
            exports[fmt]=compare_export(fmt,path.read_text(),meeting)
    row['exports']=exports
    audio=page.locator(f'.history-card:has([data-open-meeting="{mid}"]) [data-audio-download]')
    row['mp3_link']=await audio.count()>0
    if row['mp3_link']:
        async with page.expect_download() as pending: await audio.click()
        dl=await pending.value; path=ROOT/f'{tag}.download.mp3'; await dl.save_as(str(path)); row['mp3_bytes']=path.stat().st_size
    foreign=await browser.new_context(ignore_https_errors=True)
    other=await foreign.new_page(); await other.goto(BASE); await other.locator('[data-history-boot="ready"]').wait_for()
    row['foreign_read_status']=(await fetch(other,f'/api/meetings/{mid}'))['status']; await foreign.close()
    (EVID/(tag+'.json')).write_text(json.dumps(row,indent=2)+'\n'); emit(row)
    await context.close(); return row
async def main(cases):
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=str(browser_executable(p)))
        try:
            for name in cases:
                if name=='concurrent': await asyncio.gather(run_case(browser,'long.wav','concurrent-a'),run_case(browser,'long.wav','concurrent-b'))
                else: await run_case(browser,name)
        finally: await browser.close()
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cases',nargs='+')
    parser.add_argument('--base',default=BASE)
    parser.add_argument('--decoder-url',default='http://127.0.0.1:18116')
    parser.add_argument('--out',type=Path,default=EVID)
    parser.add_argument('--scratch',type=Path,default=ROOT)
    parser.add_argument('--source-base',default='https://127.0.0.1:17877')
    parser.add_argument('--hang-base',default='http://127.0.0.1:17878')
    parser.add_argument('--allow-contention',action='store_true')
    args=parser.parse_args()
    ROOT,EVID,BASE,METRICS=args.scratch,args.out,args.base,args.decoder_url.rstrip('/')+'/metrics'
    ALLOW_CONTENTION=args.allow_contention
    ROOT.mkdir(parents=True,exist_ok=True);EVID.mkdir(parents=True,exist_ok=True)
    for name in ('direct','missing','html'):URLS[name]=args.source_base+'/'+URLS[name].rsplit('/',1)[1]
    URLS['hang']=args.hang_base+'/hang'
    asyncio.run(main(args.cases))
