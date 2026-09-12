"""Capture browser timeout facts before page teardown, without recording page content."""
from __future__ import annotations

import json
from pathlib import Path
from playwright.sync_api import Locator, TimeoutError as PlaywrightTimeout

# Keep boxes/colors, but hide every text source, form value and media surface.
CONTENT_FREE_STYLE = """
*, *::before, *::after { color: transparent !important; text-shadow: none !important;
  -webkit-text-fill-color: transparent !important; background-image: none !important; }
*::before, *::after { content: none !important; }
input, textarea, select, img, svg, canvas, video, iframe, object, embed {
  visibility: hidden !important;
}
"""
BOOT_STATE = """() => Object.fromEntries(
 ['data-auth-state','data-boot','data-history-boot'].map(name =>
 [name, [...document.querySelectorAll('['+name+']')].map(e => e.getAttribute(name))]))"""
FINAL_TAIL_READY = """tail => {
 const pane = document.querySelector('#tr-body');
 return !!pane && !pane.querySelector('.utt[data-state="provisional"]') &&
 [...pane.querySelectorAll('.utt[data-state="final"] .utt-text')]
   .some(e => e.textContent.includes(tail));
}"""


class BrowserTimeoutEvidence:
    def __init__(self, root: Path, predicate: str, register=None):
        self.root = root
        self.predicate = predicate
        self.register = register or (lambda path: None)
        self.sequence = 0

    def page(self, page, stage):
        return EvidencePage(page, self, stage)

    def retain(self, page, stage, operation, target, exc):
        if hasattr(exc, 'browser_timeout'):
            return
        self.sequence += 1
        relative = Path('browser-timeouts') / f'{self.predicate}-{self.sequence:02d}'
        detail = {'predicate': self.predicate, 'stage': stage, 'operation': operation,
                  'target': target, 'page_url': page.url, 'attributes': None,
                  'screenshot': None, 'screenshot_kind': 'content-free-layout'}
        # Attach first: an evidence-collection failure must not replace the original timeout.
        exc.browser_timeout = detail
        try:
            detail['attributes'] = page.evaluate(BOOT_STATE)
        except Exception as error:
            detail['attributes_error'] = type(error).__name__
        try:
            png = relative.with_suffix('.png')
            destination = self.root / png
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            page.screenshot(path=str(destination), style=CONTENT_FREE_STYLE, timeout=2000)
            destination.chmod(0o600)
            self.register(png)
            detail['screenshot'] = 'artifacts/' + png.as_posix()
        except Exception as error:
            detail['screenshot_error'] = type(error).__name__
        try:
            record = relative.with_suffix('.json')
            path = self.root / record
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_text(json.dumps(detail, indent=2)+'\n')
            path.chmod(0o600)
            self.register(record)
        except Exception as error:
            detail['record_error'] = type(error).__name__


class EvidencePage:
    """Forward unchanged sync calls; catch explicit waits and locator auto-waits alike."""
    def __init__(self, page, evidence, stage):
        self.raw_page, self.evidence, self.stage = page, evidence, stage

    def __getattr__(self, name):
        value = getattr(self.raw_page, name)
        if not callable(value):
            return value
        def call(*args, **kwargs):
            target = str(args[0]) if args and name in {
                'wait_for_selector','wait_for_function','evaluate','eval_on_selector',
                'goto','wait_for_load_state'} else name
            return self.invoke(name, target, value, *args, **kwargs)
        return call

    def invoke(self, operation, target, function, *args, **kwargs):
        try:
            result = function(*args, **kwargs)
        except PlaywrightTimeout as exc:
            self.evidence.retain(self.raw_page, self.stage, operation, target, exc)
            raise
        if isinstance(result, Locator):
            return EvidenceLocator(result, self)
        if operation.startswith('expect_'):
            return EvidenceExpectation(result, self, operation)
        return result


class EvidenceLocator:
    def __init__(self, locator, page):
        self.raw_locator, self.page = locator, page

    def __getattr__(self, name):
        # Playwright's actual selector includes the entire locator chain, not DOM content.
        target = self.raw_locator._impl_obj._selector
        value = self.page.invoke(name, target, getattr, self.raw_locator, name)
        if callable(value):
            return lambda *args, **kwargs: self.page.invoke(name, target, value, *args, **kwargs)
        return value


class EvidenceExpectation:
    def __init__(self, context, page, operation):
        self.context, self.page, self.operation = context, page, operation

    def __enter__(self):
        return self.page.invoke(self.operation, self.operation, self.context.__enter__)

    def __exit__(self, *args):
        return self.page.invoke(self.operation, self.operation, self.context.__exit__, *args)


def wait_for_final_tail(page, tail):
    page.wait_for_function(FINAL_TAIL_READY, arg=tail)


class BackgroundPolling:
    """Only completed requests issued within the measured hidden interval count."""
    def __init__(self, meeting_id):
        self.route = f'/api/live/sessions/{meeting_id}/'
        self.hidden = False
        self.pending = set()
        self.completed = 0

    def begin(self):
        self.hidden = True

    def issued(self, request):
        if self.hidden and self.route in request.url:
            self.pending.add(request)

    def finished(self, request):
        if request in self.pending:
            self.pending.remove(request)
            self.completed += 1


class AsyncEvidencePage(EvidencePage):
    """Same evidence boundary for the async G9 subprocess probe."""
    def invoke(self, operation, target, function, *args, **kwargs):
        import inspect
        from playwright.async_api import Locator as AsyncLocator
        if inspect.iscoroutinefunction(function):
            async def call():
                try:
                    return await function(*args, **kwargs)
                except PlaywrightTimeout as exc:
                    await retain_async_timeout(self, operation, target, exc)
                    raise
            return call()
        result = function(*args, **kwargs)
        if isinstance(result, AsyncLocator):
            return EvidenceLocator(result, self)
        return result


async def retain_async_timeout(observed, operation, target, exc):
    if hasattr(exc, 'browser_timeout'):
        return
    evidence, page = observed.evidence, observed.raw_page
    evidence.sequence += 1
    relative = Path('browser-timeouts') / f'{evidence.predicate}-{evidence.sequence:02d}'
    detail = {'predicate': evidence.predicate, 'stage': observed.stage, 'operation': operation,
              'target': target, 'page_url': page.url, 'attributes': None,
              'screenshot': None, 'screenshot_kind': 'content-free-layout'}
    exc.browser_timeout = detail
    try:
        detail['attributes'] = await page.evaluate(BOOT_STATE)
    except Exception as error:
        detail['attributes_error'] = type(error).__name__
    try:
        png = relative.with_suffix('.png')
        destination = evidence.root / png
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        await page.screenshot(path=str(destination), style=CONTENT_FREE_STYLE, timeout=2000)
        destination.chmod(0o600)
        evidence.register(png)
        detail['screenshot'] = 'artifacts/' + png.as_posix()
    except Exception as error:
        detail['screenshot_error'] = type(error).__name__
    try:
        record = relative.with_suffix('.json')
        path = evidence.root / record
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(json.dumps(detail, indent=2)+'\n')
        path.chmod(0o600)
        evidence.register(record)
    except Exception as error:
        detail['record_error'] = type(error).__name__
