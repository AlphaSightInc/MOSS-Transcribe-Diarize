"""Retained E2E output cannot contain product data or browser credentials."""
import asyncio
import json
from types import SimpleNamespace

from tests.e2e.verify_workspace import Harness, retained_metadata, write


def test_metadata_retains_counts_status_ids_but_no_bodies_or_names(tmp_path):
    secret = 'PRIVATE-TRANSCRIPT-COOKIE-KEY'
    data = {'rows': {'4': {'status':'PASS', 'seconds':1.5, 'ok':True}},
            'meetings':{'live':'opaque-id'}, 'name':secret, 'error':secret,
            'url':'https://person:secret@example.invalid/?key='+secret,
            'body':{'choices':[{'message':{'content':secret}}]},
            'messages':[{'content':secret}], 'transcript':{'segments':[{'text':secret}]},
            'cookies':[{'value':secret}], 'embedding':[.1,.2], 'audio':[1,2,3],
            'unexpected':{'message':secret}, 'exception':'TimeoutError'}
    write(tmp_path/'result.json',data)
    result=json.loads((tmp_path/'result.json').read_text())
    assert result['rows']['4']==data['rows']['4']
    assert result['meetings']['live']=='opaque-id'
    assert result['exception']=='TimeoutError'
    assert not any(k in result for k in ('body','messages','transcript','cookies','embedding','audio'))
    assert secret not in (tmp_path/'result.json').read_text()
    assert 'example.invalid' not in (tmp_path/'result.json').read_text()


def test_relay_response_is_not_read_or_written_and_screenshot_is_excluded(tmp_path):
    harness=Harness(SimpleNamespace(output=str(tmp_path/'evidence'),base='https://example.invalid'))
    class Response:
        url='https://example.invalid/api/llm/chat/completions'
        status=200
        request=SimpleNamespace(method='POST')
        async def json(self):
            raise AssertionError('Response body must not be retained')
    class Page:
        async def screenshot(self, **kwargs):
            raise AssertionError('Raw screenshot must not be retained')
    harness.page=Page()
    try:
        asyncio.run(harness.response(Response()))
        assert asyncio.run(harness.snapshot(4)) is None
        assert list(harness.out.iterdir())==[harness.out/'network.jsonl']
        assert harness.private.parent != harness.out
        entry=json.loads((harness.out/'network.jsonl').read_text())
        assert entry['status']==200 and entry['method']=='POST'
    finally:
        harness.network.close()
        harness._private.cleanup()
