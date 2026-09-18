"""PROTOTYPE: browser File.size -> tiny request -> existing capacity policy.
Invariant: no source read, meeting creation or changed capacity threshold.
Falsifier: oversized real sparse File gets admitted, or small File refused.
"""
import asyncio,json,shutil,threading,time
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit,parse_qs
from playwright.async_api import async_playwright
from tests.phase2.browser_support import browser_executable
from moss_transcribe_diarize.app.phase2_file import admit_file_upload,FileUploadRejected
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def do_GET(self):
  size=int(parse_qs(urlsplit(self.path).query)['bytes'][0]); status=200; reason='admitted'
  try: admit_file_upload(SimpleNamespace(headers={'content-length':str(size)},_receive=None),Path('.wp16runtime/state/file-work'))
  except FileUploadRejected as e: status=e.status_code; reason=str(e)
  body=json.dumps(dict(reason=reason)).encode(); self.send_response(status); self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
async def main():
 server=ThreadingHTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=server.serve_forever); thread.start()
 huge=Path('.wp16runtime/media/preflight-large.wav'); size=(shutil.disk_usage(huge.parent).free-512*1024*1024)//2+1048576
 with huge.open('wb') as f:f.truncate(size)
 rows=[]
 try:
  async with async_playwright() as p:
   b=await p.chromium.launch(executable_path=str(browser_executable(p))); c=await b.new_context(ignore_https_errors=True); page=await c.new_page(); await page.goto('https://127.0.0.1:17876'); await page.locator('[data-history-boot="ready"]').wait_for()
   for path,status in [(Path('.wp16runtime/media/two.wav'),200),(huge,507)]:
    await page.locator('input[name="file"]').set_input_files(str(path)); start=time.monotonic()
    r=await page.evaluate('async port=>{let size=document.querySelector("input[name=file]").files[0].size;let r=await fetch(`http://127.0.0.1:${port}/?bytes=${size}`); return {file_bytes:size,status:r.status,body:await r.json()}}',server.server_port)
    r.update(elapsed=time.monotonic()-start,expected=status); print(json.dumps(r),flush=True); rows.append(r); assert r['status']==status
   await b.close()
 finally: huge.unlink();server.shutdown();server.server_close();thread.join()
 Path('evidence/mvpfix/wp16/preflight-prototype.json').write_text(json.dumps(rows,indent=2)+'\n')
asyncio.run(main())
