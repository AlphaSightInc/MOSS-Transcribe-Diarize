"""Round-11 failures: actual hidden state and registered G9 ownership."""
from types import SimpleNamespace

import pytest
from playwright.sync_api import sync_playwright

from moss_transcribe_diarize.phase2_browser_visibility import unfocused_driver
from moss_transcribe_diarize.phase2_browser_evidence import BackgroundPolling
from moss_transcribe_diarize import phase2_acceptance_summary as summary
from tests.phase2.browser_support import require_browser


def test_headless_background_uses_real_hidden_state_and_post_hidden_requests():
    with unfocused_driver(),sync_playwright() as p:
        browser=p.chromium.launch(executable_path=str(require_browser(p)),headless=True,
            ignore_default_args=['--disable-background-timer-throttling','--disable-backgrounding-occluded-windows','--disable-renderer-backgrounding'])
        try:
            context=browser.new_context();page=context.new_page()
            page.route('**/*',lambda route:route.fulfill(content_type='text/html',body='<script>setInterval(()=>fetch("/api/live/sessions/owned/snapshot"),100)</script>'))
            page.goto('https://fixture.test/')
            polling=BackgroundPolling('owned')
            page.on('request',polling.issued);page.on('requestfinished',polling.finished)
            other=context.new_page();other.goto('about:blank');other.bring_to_front()
            page.wait_for_function('document.visibilityState === "hidden"')
            polling.begin();page.wait_for_timeout(2500)
            assert page.evaluate('document.visibilityState')=='hidden'
            assert polling.completed>0
        finally:browser.close()


def test_g9_registers_second_session_with_owner_before_seeding(tmp_path,monkeypatch):
    class ReachedFile(Exception): pass
    calls=[];registry={}
    class Client:
        def json(self,method,path,status,**kwargs):
            if method=='POST' and path=='/api/live/sessions': return {'id':'unregistered'},None
            if path.endswith('/stop'): calls.append(('stop',path));return {},None
            return {'status':'completed','transcript':{'segments':[{'speaker':'Qualification speaker'}]}},None
        def request(self,*args,**kwargs): calls.append(('abort',args))
    def create(owner):
        registry['owned-second']=owner;calls.append(('create',owner));return 'owned-second'
    def seed(owner,ident,index):
        assert registry[ident]==owner=='b'
        calls.append(('seed',owner,ident,index))
    def file(*args):raise ReachedFile()
    campaign=SimpleNamespace(artifact_root=tmp_path,_safe_artifacts=set(),origin='https://fixture.test',
        _summary_voiceprint_meeting='first',a=Client(),b=Client(),_new_live_id=create,
        _seed_live_transcript=seed,_submit_file_for=file,_text=lambda key:'fixture.wav')
    monkeypatch.setattr(summary,'_trusted_tls_identity',lambda origin:{'trusted':True})
    with pytest.raises(ReachedFile):summary.measure_browser_summary(campaign)
    assert calls==[('create','b'),('seed','b','owned-second',1),('stop','/api/live/sessions/owned-second/stop')]


def test_unfocused_driver_copies_read_only_installation(tmp_path,monkeypatch):
    from pathlib import Path
    from playwright._impl import _transport
    source=tmp_path/'installed-package'
    (source/'lib').mkdir(parents=True)
    cli=source/'cli.js';cli.write_text('// fixture driver entrypoint\n')
    bundle=source/'lib/coreBundle.js'
    original_text='this._client.send("Emulation.setFocusEmulationEnabled", { enabled: true })'
    bundle.write_text(original_text)
    original=lambda: ('node',str(cli))
    monkeypatch.setattr(_transport,'compute_driver_executable',original)
    for path in (cli,bundle):path.chmod(0o444)
    for path in (source/'lib',source):path.chmod(0o555)
    try:
        with unfocused_driver():
            _,copied_cli=_transport.compute_driver_executable()
            copied_root=Path(copied_cli).parent
            copied_bundle=copied_root/'lib/coreBundle.js'
            assert copied_root != source
            assert 'enabled: false' in copied_bundle.read_text()
            assert copied_bundle.stat().st_mode & 0o200
            assert bundle.read_text()==original_text
            assert bundle.stat().st_mode & 0o222 == 0
            assert source.stat().st_mode & 0o222 == 0
        assert not copied_root.exists()
        assert _transport.compute_driver_executable is original
    finally:
        for path in (source,source/'lib'):path.chmod(0o755)
        for path in (cli,bundle):path.chmod(0o644)


def test_reload_history_observer_reopens_ephemeral_view_without_capture_controls():
    from moss_transcribe_diarize.phase2_acceptance_browser import _reload_history_observer

    class Page:
        phase = 'viewing'
        calls = []
        stop_visible = False

        def reload(self, **kwargs):
            assert kwargs == {'wait_until': 'networkidle'}
            self.phase = 'idle'
            self.calls.append('reload')

        def wait_for_selector(self, selector):
            self.calls.append(selector)
            if 'read-only' in selector:
                assert self.phase == 'viewing', 'ephemeral history observer must be reopened'
            if 'idle' in selector:
                assert self.phase == 'idle'

        def get_by_role(self, role, **kwargs):
            assert role == 'region' and kwargs == {'name': 'Meeting history', 'exact': True}
            return self

        def locator(self, selector):
            if 'data-open-meeting' in selector:
                assert selector == '[data-open-meeting="owned"]'
                return SimpleNamespace(click=self.open)
            assert selector == '[data-capture-phase="viewing"]'
            return SimpleNamespace(count=lambda: int(self.phase == 'viewing'))

        def open(self):
            self.calls.append('open-owned')
            self.phase = 'viewing'

        def get_by_text(self, text):
            assert text == 'Stop and finalize'
            return SimpleNamespace(count=lambda: int(self.stop_visible))

    page = Page()
    assert _reload_history_observer(page, 'owned')
    assert page.calls == ['reload', '[data-history-boot="ready"]',
                          '[data-capture-phase="idle"]', 'open-owned',
                          '[data-observer-mode="read-only"]']
    page.stop_visible = True
    assert not _reload_history_observer(page, 'owned')
