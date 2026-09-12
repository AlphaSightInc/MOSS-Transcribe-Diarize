"""An acceptance-owned helper must outlive blocking non-live work."""
import asyncio
import threading
import time
from types import SimpleNamespace

import httpx

from moss_transcribe_diarize import phase2_acceptance_replay as replay
from moss_transcribe_diarize import phase2_acceptance_external as external


def test_replay_heartbeats_continue_during_wait_and_stop_with_session(tmp_path, monkeypatch):
    monkeypatch.setattr(replay, 'HELPER_HEARTBEAT_INTERVAL_SECONDS', .02, raising=False)
    cookie=tmp_path/'cookie';cookie.write_text('test-cookie');cookie.chmod(0o600)
    adapter=replay.AccountCookieLiveReplayService(base_url='https://moss.test',cookie_file=cookie)
    beats=[]
    def request(method,path,payload=None,**kwargs):
        if path=='/api/live/sessions':return {'id':'live','descriptor':{},'snapshot':{}}
        if path.endswith('/heartbeat'):
            beats.append(payload['sequence']);return {}
        return {'snapshot':{}}
    monkeypatch.setattr(adapter,'_json',request)
    monkeypatch.setattr(replay,'_descriptor_from_dict',lambda value:SimpleNamespace(frame_samples=8000))
    monkeypatch.setattr(replay,'_snapshot_from_dict',lambda value:value)
    try:
        adapter.create()
        # Eight scheduling periods with no frames, snapshot reads or caller heartbeats.
        threading.Event().wait(.16)
        assert len(beats)>=4, 'blocking work starved the owned helper lease'
        assert beats==list(range(len(beats)))
        asyncio.run(adapter.stop('live',5))
        stopped=len(beats);threading.Event().wait(.06)
        assert len(beats)==stopped
    finally:
        if hasattr(adapter,'close'):adapter.close()


def test_external_keeps_created_live_helper_alive_while_waiting_for_file(monkeypatch):
    monkeypatch.setattr(replay, 'HELPER_HEARTBEAT_INTERVAL_SECONDS', .02, raising=False)
    beats=[]
    class Client:
        def json(self,method,path,expected,**kwargs):
            if path=='/api/live/sessions':return {'id':'live'},None
            threading.Event().wait(.16)
            return {'status':'completed'},None
        def request(self,method,path,**kwargs):
            if path.endswith('/heartbeat'):beats.append(kwargs['json']['sequence'])
            return httpx.Response(200,json={})
        def close(self):pass
    campaign=external.FixedAccountCampaign(candidate_sha='test',config={})
    campaign._clients['a']=Client()
    try:
        assert campaign._live_id('a')=='live'
        campaign._await_meeting_terminal_for(campaign.a,'file',timeout=1)
        assert len(beats)>=4, 'waiting for a file starved the live helper lease'
        assert beats==list(range(len(beats)))
        campaign.cleanup()
        stopped=len(beats);threading.Event().wait(.06)
        assert len(beats)==stopped
    finally:campaign.close()


def test_periodic_and_explicit_heartbeats_share_one_serialized_stream(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from moss_transcribe_diarize.app.live_helper_presence import HelperHeartbeat,HelperPresenceRegistry
    monkeypatch.setattr(replay,'HELPER_HEARTBEAT_INTERVAL_SECONDS',.01)
    registry=HelperPresenceRegistry();sequences=[]
    def post(payload):
        registry.observe('meeting',HelperHeartbeat.from_dict(payload))
        sequences.append(payload['sequence'])
        time.sleep(.002)
    helper=replay.AcceptanceHelperLease(post)
    try:
        helper.start()
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _:helper.send(),range(16)))
        assert sequences==list(range(len(sequences)))
        assert helper.last_error is None
    finally:helper.close()


def test_ambiguous_heartbeat_ack_does_not_reuse_sequence_with_changed_payload():
    import pytest
    from moss_transcribe_diarize.app.live_helper_presence import HelperHeartbeat,HelperPresenceRegistry
    registry=HelperPresenceRegistry();sequences=[]
    def post(payload):
        registry.observe('meeting',HelperHeartbeat.from_dict(payload))
        sequences.append(payload['sequence'])
        if len(sequences)==1:
            raise replay.AccountReplayTransportFailure('lost response',http_status=None)
    helper=replay.AcceptanceHelperLease(post)
    try:
        with pytest.raises(replay.AccountReplayTransportFailure):helper.send()
        helper.send()
        assert sequences==[0,1]
    finally:helper.close()
