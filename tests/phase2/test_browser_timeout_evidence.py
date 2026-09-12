"""Retain browser failure facts without weakening waits or leaking page contents."""
import importlib.util
import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from moss_transcribe_diarize.phase2_browser_evidence import (
    BrowserTimeoutEvidence, BackgroundPolling, CONTENT_FREE_STYLE,
    FINAL_TAIL_READY, wait_for_final_tail,
)
from moss_transcribe_diarize.phase2_acceptance_measure import _failure_details, _snapshot_campaign_artifacts
from tests.phase2.browser_support import require_browser

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(require_browser(p)))
        try:
            page = browser.new_page(viewport={'width':400,'height':300})
            page.set_default_timeout(200)  # Tests only; production defaults stay unchanged.
            page.set_content('<main data-auth-state="signed-in" data-boot="loading"><p>PRIVATE TRANSCRIPT</p><input value="SECRET KEY"></main>')
            yield page
        finally:
            browser.close()


@pytest.mark.parametrize('predicate,stage,kind,target', [
    ('account_product_regression','background.enter-hidden','function',"() => false"),
    ('transcript_pane_fidelity','candidate.workspace-ready','selector','[data-boot="ready"]'),
    ('browser_final_summary','summary.configure.a.retry','locator','[aria-label="Provider HTTPS URL"]'),
    ('transcript_pane_fidelity','reference.prepare','selector','.main'),
])
def test_timeout_fields_raw_record_and_content_free_artifact(page,tmp_path,monkeypatch,predicate,stage,kind,target):
    # Assert the real writer supplies the mask and that it conceals text/form values
    # in both captures; PNG compression, focus and browser painting are not evidence.
    capture = page.screenshot
    masks = []
    def checked_capture(**kwargs):
        assert kwargs['style'] == CONTENT_FREE_STYLE
        style = page.add_style_tag(content=kwargs['style'])
        try:
            mask = page.locator('p').evaluate("""e => {
                const s = getComputedStyle(e);
                return [s.color, s.webkitTextFillColor, s.textShadow];
            }""")
            assert mask == ['rgba(0, 0, 0, 0)', 'rgba(0, 0, 0, 0)', 'none']
            assert page.locator('input').evaluate("e => getComputedStyle(e).visibility") == 'hidden'
            masks.append(mask)
            return capture(**kwargs)
        finally:
            style.evaluate('e => e.remove()')
    monkeypatch.setattr(page, 'screenshot', checked_capture)
    registered=set()
    evidence=BrowserTimeoutEvidence(tmp_path,predicate,registered.add)
    observed=evidence.page(page,stage)
    with pytest.raises(PlaywrightTimeout) as caught:
        if kind=='function': observed.wait_for_function(target)
        elif kind=='selector': observed.wait_for_selector(target)
        else: observed.locator(target).fill('DO NOT RETAIN THIS')
    detail=_failure_details(caught.value,{})['browser_timeout']
    assert detail['predicate']==predicate and detail['stage']==stage
    assert detail['target']==detail['operation']
    assert detail['page_scheme']=='about' and 'page_url' not in detail
    assert detail['attributes']=={'data-auth-state':['signed-in'],'data-boot':['loading'],'data-history-boot':[]}
    screenshot=tmp_path/detail['screenshot'].removeprefix('artifacts/')
    assert screenshot.is_file()
    assert 'PRIVATE' not in json.dumps(detail) and 'DO NOT RETAIN' not in json.dumps(detail)
    first=screenshot.read_bytes()
    page.locator('p').evaluate("e=>e.textContent='DIFFERENT PRIVATE WORDS'")
    page.locator('input').fill('DIFFERENT SECRET')
    second = page.screenshot(style=CONTENT_FREE_STYLE)
    from io import BytesIO
    from PIL import Image
    assert Image.open(BytesIO(first)).size == Image.open(BytesIO(second)).size == (400, 300)
    assert len(masks) == 2
    from types import SimpleNamespace
    campaign=SimpleNamespace(safe_artifacts=tuple(registered),artifact_root=tmp_path)
    raw=tmp_path/'raw';raw.mkdir()
    copied=_snapshot_campaign_artifacts(campaign,raw)
    assert screenshot.relative_to(tmp_path).as_posix() in copied
    assert (raw/detail['screenshot']).read_bytes()==first


def test_final_tail_rejects_draft_confirmed_and_late_preview(page,tmp_path):
    observed=BrowserTimeoutEvidence(tmp_path,'transcript_pane_fidelity').page(page,'candidate.final-tail')
    page.set_content('<div id="tr-body"><article class="utt" data-state="provisional"><p class="utt-text">fixture tail</p></article></div>')
    with pytest.raises(PlaywrightTimeout): wait_for_final_tail(observed,'fixture tail')
    assert not page.evaluate(FINAL_TAIL_READY,'fixture tail')
    page.locator('.utt').evaluate("e=>e.dataset.state='confirmed'")
    assert not page.evaluate(FINAL_TAIL_READY,'fixture tail')
    page.locator('.utt').evaluate("e=>e.dataset.state='final'")
    wait_for_final_tail(observed,'fixture tail')
    page.locator('#tr-body').evaluate("e=>e.insertAdjacentHTML('beforeend','<article class=utt data-state=provisional>new draft</article>')")
    with pytest.raises(PlaywrightTimeout): wait_for_final_tail(observed,'fixture tail')
    page.locator('[data-state=provisional]').evaluate('e=>e.remove()')
    wait_for_final_tail(observed,'fixture tail')


def test_foreground_completions_satisfy_old_counter_but_not_hidden_counter():
    class Request:
        url='https://example.test/api/live/sessions/meeting/snapshot'
    early, inflight, hidden=Request(),Request(),Request()
    old_count=0
    counter=BackgroundPolling('meeting')
    counter.issued(early);counter.finished(early)
    old_count+=1  # Exact old callback: any requestfinished on this URL increments.
    counter.issued(inflight)
    counter.begin()
    counter.finished(inflight);old_count+=1
    assert old_count>0 and counter.completed==0
    counter.issued(hidden);counter.finished(hidden)
    assert counter.completed==1


def test_reference_prepare_retains_exact_wait_before_teardown(page,tmp_path):
    spec=importlib.util.spec_from_file_location('reference_timeout_probe',ROOT/'tests/reference_ui_screenshot_diff.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    observed=BrowserTimeoutEvidence(tmp_path,'transcript_pane_fidelity').page(page,'reference.prepare')
    with pytest.raises(PlaywrightTimeout) as caught:
        module.prepare_page(observed,[{'text':'private fixture'}],is_reference=True)
    assert caught.value.browser_timeout['target']=='wait_for_selector'
    assert caught.value.browser_timeout['stage']=='reference.prepare'


def test_summary_selector_auto_wait_retains_target_without_form_values(page,tmp_path):
    from moss_transcribe_diarize.phase2_acceptance_summary import configure_external_summary
    page.set_content('<section aria-label="Browser AI settings"><form><select aria-label="Provider"><option>External HTTPS provider</option></select></form></section>')
    observed=BrowserTimeoutEvidence(tmp_path,'browser_final_summary').page(page,'summary.configure.a.retry')
    with pytest.raises(PlaywrightTimeout) as caught:
        configure_external_summary(observed,endpoint='https://private.test',model='private-model',api_key='private-key',prompt='private-prompt')
    detail=caught.value.browser_timeout
    assert detail['target']=='fill' and detail['operation']=='fill'
    assert 'private-key' not in json.dumps(detail) and 'private.test' not in json.dumps(detail)


def test_async_provider_timeout_survives_subprocess_boundary(tmp_path):
    import asyncio
    import subprocess
    from types import SimpleNamespace
    from playwright.async_api import async_playwright
    from moss_transcribe_diarize.phase2_browser_evidence import AsyncEvidencePage
    from moss_transcribe_diarize.phase2_acceptance_summary import retain_provider_probe_timeout

    async def run():
        async with async_playwright() as p:
            browser=await p.chromium.launch(executable_path=str(require_browser(p)))
            try:
                page=await browser.new_page()
                await page.set_content('<main data-boot="ready">PRIVATE RESULT</main>')
                page.set_default_timeout(200)
                writer=BrowserTimeoutEvidence(tmp_path,'browser_final_summary-relay')
                observed=AsyncEvidencePage(page,writer,'provider-probe.relay')
                with pytest.raises(PlaywrightTimeout) as caught:
                    await observed.locator('[data-summary-state="current"]').wait_for()
                assert caught.value.browser_timeout['target']=='wait_for'
            finally:
                await browser.close()
    asyncio.run(run())
    campaign=SimpleNamespace(artifact_root=tmp_path,_safe_artifacts=set())
    error=subprocess.CalledProcessError(1,['python','final_browser_probe.py'])
    retain_provider_probe_timeout(campaign,error)
    detail=_failure_details(error,{})['browser_timeout']
    assert detail['stage']=='provider-probe.relay'
    assert detail['attributes']['data-boot']==['ready']
    assert len(campaign._safe_artifacts)==2
    assert (tmp_path/detail['screenshot'].removeprefix('artifacts/')).is_file()


def test_evidence_failure_does_not_replace_original_timeout(page,tmp_path,monkeypatch):
    def unavailable(**kwargs): raise RuntimeError('SCREENSHOT CONTENT MUST NOT LEAK')
    monkeypatch.setattr(page,'screenshot',unavailable)
    observed=BrowserTimeoutEvidence(tmp_path,'account_product_regression').page(page,'background.enter-hidden')
    with pytest.raises(PlaywrightTimeout) as caught:
        observed.wait_for_function('() => false')
    detail=caught.value.browser_timeout
    assert detail['screenshot'] is None and detail['screenshot_error']=='RuntimeError'
    assert 'CONTENT MUST NOT LEAK' not in json.dumps(detail)


def test_cleanup_error_preserves_original_timeout_details():
    try:
        original=PlaywrightTimeout('Page.wait_for_function: Timeout 30000ms')
        original.browser_timeout={'stage':'background.enter-hidden','target':"document.visibilityState === 'hidden'"}
        try:
            raise original
        finally:
            raise RuntimeError('cleanup failed')
    except RuntimeError as error:
        assert _failure_details(error,{})['browser_timeout']==original.browser_timeout


def test_download_event_timeout_is_retained(page,tmp_path):
    page.set_content('<button>Download</button>')
    observed=BrowserTimeoutEvidence(tmp_path,'account_product_regression').page(page,'export.download')
    with pytest.raises(PlaywrightTimeout) as caught:
        with observed.expect_download(timeout=200):
            observed.get_by_role('button',name='Download').click()
    assert caught.value.browser_timeout['operation']=='expect_download'
    assert caught.value.browser_timeout['stage']=='export.download'


def test_reference_boot_stub_supplies_pinned_health_calibration(page):
    """6a8d0c1f App.bootstrap awaits getHealth before setting data-boot=ready."""
    spec = importlib.util.spec_from_file_location(
        'reference_boot_probe', ROOT / 'tests/reference_ui_screenshot_diff.py'
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install_reference_api_stub(page)
    page.route('http://reference.test/', lambda route: route.fulfill(
        content_type='text/html', body='<main></main>'
    ))
    page.goto('http://reference.test/')
    result = page.evaluate('''async () => {
      const response = await fetch('/api/health');
      const health = await response.json();
      const unknown = await fetch('/api/not-a-fixture');
      return {status: response.status, calibration: health.calibration_profile,
              unknown: unknown.status};
    }''')
    assert result['status'] == 200
    assert result['calibration'] == {
        'live_refined_overlay_enabled': False,
        'live_refined_osf_enabled': False,
        'live_refined_insertion_mode': 'off',
    }
    assert result['unknown'] == 404


def test_timeout_metadata_never_retains_navigation_or_text_locator(tmp_path):
    """No browser binary needed: exercise the actual diagnostic writer boundary."""
    class Page:
        url = 'https://person:cookie@example.test/private-name?key=SECRET#TRANSCRIPT'
        def evaluate(self, expression):
            return {'data-auth-state': ['signed-in'], 'data-boot': ['ready'], 'data-history-boot': []}
        def screenshot(self, **kwargs):
            raise RuntimeError('screenshot unavailable')
    error = PlaywrightTimeout('Locator.wait_for: unexpected value PRIVATE_TRANSCRIPT')
    writer = BrowserTimeoutEvidence(tmp_path, 'browser_final_summary')
    writer.retain(Page(), 'summary.wait-state.current', 'wait_for',
                  'internal:text="PRIVATE_TRANSCRIPT"', error)
    detail = json.loads(next(tmp_path.rglob('*.json')).read_text())
    assert detail['target'] == 'wait_for' and detail['page_scheme'] == 'https'
    assert all(secret not in json.dumps(detail) for secret in
               ('person', 'cookie', 'example.test', 'private-name', 'SECRET', 'TRANSCRIPT'))


def test_failure_projection_drops_unquoted_page_text_http_body_and_os_paths():
    from moss_transcribe_diarize.phase2_acceptance_replay import AccountReplayTransportFailure
    errors = [PlaywrightTimeout('unexpected value PRIVATE_TRANSCRIPT'),
              AccountReplayTransportFailure('upstream PRIVATE_RESPONSE', http_status=502),
              OSError(2, 'missing', '/Users/PRIVATE_NAME/PRIVATE_RECORDING.wav')]
    for error in errors:
        detail = _failure_details(error, {})
        assert detail['failure_type'] == type(error).__name__
        assert 'PRIVATE' not in json.dumps(detail)
    assert _failure_details(errors[1], {})['http_status'] == 502
    assert _failure_details(errors[2], {})['errno'] == 2


def test_product_regression_download_context_preserves_event_value(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from playwright.sync_api import Download
    artifact = tmp_path / 'transcript.srt'
    artifact.write_text('fixture export')
    item = Mock(spec=Download)
    item.suggested_filename = 'transcript.srt'
    item.path.return_value = str(artifact)
    event = SimpleNamespace(value=item)
    class Context:
        def __enter__(self): return event
        def __exit__(self, *args): return None
    page = BrowserTimeoutEvidence(tmp_path, 'account_product_regression').page(
        SimpleNamespace(expect_download=lambda: Context()), 'export.workspace')
    with page.expect_download() as download:
        pass
    # Exact consumer contract at measure_product's export loop, not just __exit__.
    assert download is event
    assert isinstance(download.value, Download)
    assert download.value.suggested_filename.endswith('.srt')
    assert Path(download.value.path()).stat().st_size > 0


def test_download_context_does_not_suppress_consumer_errors(tmp_path):
    from types import SimpleNamespace
    class Context:
        def __enter__(self): return SimpleNamespace(value=None)
        def __exit__(self, *args): return None
    observed = BrowserTimeoutEvidence(tmp_path, 'account_product_regression').page(
        SimpleNamespace(expect_download=lambda: Context()), 'export.workspace')
    with pytest.raises(AssertionError, match='download consumer failed'):
        with observed.expect_download():
            raise AssertionError('download consumer failed')


def test_real_product_export_download_value(page,tmp_path):
    from playwright.sync_api import Download
    page.set_content('<a download="transcript.srt" href="data:text/plain,fixture">SubRip (.srt)</a>')
    observed = BrowserTimeoutEvidence(tmp_path, 'account_product_regression').page(page, 'export.workspace')
    with observed.expect_download() as pending:
        observed.get_by_role('link',name='SubRip (.srt)').click()
    assert isinstance(pending.value, Download)
    assert pending.value.suggested_filename.endswith('.srt')
    assert Path(pending.value.path()).stat().st_size > 0
