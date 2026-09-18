"""Real sparse file; exercise disk-based admission without consuming its body."""
import asyncio,json,shutil,time
from pathlib import Path
from playwright.async_api import async_playwright
from tests.phase2.browser_support import browser_executable
async def main():
 root=Path('.wp16runtime'); path=root/'media/over-capacity.wav'
 free=shutil.disk_usage(root).free; reserve=512*1024*1024; size=(free-reserve)//2+1024*1024
 with path.open('wb') as out: out.truncate(size)
 row=dict(free_bytes=free,reserve_bytes=reserve,file_bytes=size,allocated_bytes=path.stat().st_blocks*512,rule='required_free = 2 * Content-Length + 512 MiB',fixed_upload_limit=None)
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path=str(browser_executable(p)))
  c=await b.new_context(ignore_https_errors=True); page=await c.new_page(); await page.goto('https://127.0.0.1:17876'); await page.locator('[data-history-boot="ready"]').wait_for()
  await page.locator('input[name="file"]').set_input_files(str(path)); started=time.monotonic()
  failures=[]; posts=[]; page.on('requestfailed',lambda request:failures.append(request.failure)); page.on('request',lambda request:posts.append(request.url.rsplit('/',1)[-1]) if request.method=='POST' else None)
  try:
   async with page.expect_response(lambda r:r.url.endswith('/api/meetings/file/admission'),timeout=20000) as pending:
    await page.get_by_role('button',name='Transcribe files and URLs',exact=True).click()
   response=await pending.value; row.update(status=response.status,body=await response.json(),elapsed=time.monotonic()-started,content_length=response.request.headers.get('content-length'))
  except Exception as exc:
   row.update(probe_error=type(exc).__name__,elapsed=time.monotonic()-started,request_failures=failures)
  await asyncio.sleep(.2); row['ui']=await page.locator('[data-file-upload="results"]').inner_text()
  row['post_routes']=posts
  row['meetings']=await page.evaluate('async()=> (await (await fetch("/api/meetings")).json()).meetings.length')
  await b.close()
 path.unlink(); print(json.dumps(row,indent=2)); Path('evidence/mvpfix/wp16/oversize.json').write_text(json.dumps(row,indent=2)+'\n')
asyncio.run(main())
