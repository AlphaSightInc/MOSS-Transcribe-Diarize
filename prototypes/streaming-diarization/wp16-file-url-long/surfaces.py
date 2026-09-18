"""Reopen prior meetings to correct probe selector/bootstrap errors; no new decode."""
import asyncio,json
from pathlib import Path
from playwright.async_api import async_playwright
from tests.phase2.browser_support import browser_executable
async def main():
 rows=[]
 async with async_playwright() as p:
  b=await p.chromium.launch(executable_path=str(browser_executable(p)))
  foreign=await b.new_context(ignore_https_errors=True); f=await foreign.new_page(); await f.goto('https://127.0.0.1:17876'); await f.locator('[data-history-boot="ready"]').wait_for()
  for file in sorted(Path('evidence/mvpfix/wp16').glob('*.json')):
   row=json.loads(file.read_text())
   if not isinstance(row,dict): continue
   tag=row.get('case'); mid=row.get('meeting_id')
   if not mid: continue
   c=await b.new_context(ignore_https_errors=True,storage_state=f'.wp16runtime/{tag}.state.json'); page=await c.new_page(); await page.goto('https://127.0.0.1:17876'); await page.locator('[data-history-boot="ready"]').wait_for()
   button=page.locator(f'[data-open-meeting="{mid}"]'); history=await button.inner_text(); await button.click(); await asyncio.sleep(.2)
   reason=row.get('failure_reason') or row.get('notice'); header=await page.locator('.topbar').inner_text()
   status=await f.evaluate('async id => (await fetch(`/api/meetings/${id}`)).status',mid)
   result=dict(case=tag,meeting_id=mid,history_reason=reason is None or reason in history,header_reason=reason is None or reason in header,foreign_read_status=status)
   print(json.dumps(result),flush=True); rows.append(result); await c.close()
  await b.close()
 Path('evidence/mvpfix/wp16/surface-recheck.json').write_text(json.dumps(rows,indent=2)+'\n')
asyncio.run(main())
