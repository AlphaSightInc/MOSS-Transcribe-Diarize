"""Inspect real saved names and downloaded exports; uses only isolated WP7 cookies."""
import asyncio,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from playwright.async_api import async_playwright
from tests.phase2.browser_support import browser_executable
from tests.e2e.verify_workspace import compare_export
BASE='https://127.0.0.1:17867';scratch=ROOT/'.wp7runtime';out=ROOT/'evidence/mvpfix/wp7'
async def main():
    record=json.loads((scratch/'enroll.json').read_text());ident=record['id']
    cookies=json.loads((scratch/'cookies.json').read_text())
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=str(browser_executable(p)),headless=True)
        try:
            ctx=await browser.new_context(ignore_https_errors=True,accept_downloads=True,viewport={'width':1440,'height':1100})
            await ctx.add_cookies([dict(name=k,value=v,url=BASE,secure=True,httpOnly=True) for k,v in cookies.items()])
            page=await ctx.new_page();await page.goto(BASE)
            await page.locator('[data-auth-state="signed-in"]').wait_for(timeout=30000)
            await page.locator('[data-history-boot="ready"]').wait_for()
            await page.locator(f'[data-open-meeting="{ident}"]').click()
            await page.wait_for_function('document.querySelectorAll(".utt-text").length > 0')
            labels=await page.locator('.utt-speaker-label').all_text_contents()
            history=await page.locator(f'[data-meeting-card="{ident}"]').inner_text()
            formats={}
            for fmt,label in [('md','Markdown (.md)'),('txt','Plain text (.txt)'),('json','JSON (.json)'),('srt','SubRip (.srt)'),('vtt','WebVTT (.vtt)')]:
                await page.get_by_role('button',name='Export transcript',exact=True).click()
                async with page.expect_download() as pending:await page.get_by_role('menuitem',name=label,exact=True).click()
                download=await pending.value;path=scratch/f'export.{fmt}';await download.save_as(path)
                formats[fmt]=compare_export(fmt,path.read_text(),record['saved'])
            await page.reload();await page.locator('[data-history-boot="ready"]').wait_for()
            await page.locator(f'[data-open-meeting="{ident}"]').click()
            await page.wait_for_function('document.querySelectorAll(".utt-text").length > 0')
            reloaded=await page.locator('.utt-speaker-label').all_text_contents()
            result=dict(labels=labels,reloaded_labels=reloaded,history_has_name='WP7 Adam' in history,
                name_persisted='WP7 Adam' in labels and 'WP7 Adam' in reloaded,formats=formats)
            (out/'browser-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
        finally:await browser.close()
asyncio.run(main())
