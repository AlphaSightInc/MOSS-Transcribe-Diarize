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
