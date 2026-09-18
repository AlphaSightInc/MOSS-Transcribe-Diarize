import asyncio
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from moss_transcribe_diarize.app.phase2_url import UrlMediaAcquirer

@pytest.mark.parametrize('case,expected', [
    ('403','acquisition_http_403'), ('404','acquisition_http_404'), ('timeout','acquisition_timeout'),
    ('unsupported','transcode_failed'), ('transcode','transcode_failed'), ('decoder','decode_failed'),
    ('malformed','decode_invalid'), ('unconfirmed_empty','decode_invalid'), ('no_speech',None),
])
def test_outcomes_are_safe_persistent_and_owner_bound(tmp_path, caplog, case, expected):
    async def run():
        database=tmp_path/'state.sqlite3'
        store=await Phase2Store.open(database)
        account,cookie=await store.bootstrap_browser(None)
        workspace=store.workspace(account)
        handle=await workspace.create_meeting('file')
        meeting_id=handle.meeting_id
        root=tmp_path/'file-work'; directory=root/'input'; directory.mkdir(parents=True)
        source=directory/'media';source.write_bytes(b'fixture')
        class Runner:
            def transcribe(self,*a,**kw):
                if case in ('decoder','unsupported','transcode'): raise RuntimeError('PRIVATE token https://user:secret@host')
                return SimpleNamespace(text='malformed PRIVATE' if case=='malformed' else '',
                       window_diagnostics=[{'condition':'speechless_window_empty'}] if case=='no_speech' else [])
        class Archive:
            def prepare_mix(self,*a,**kw): raise RuntimeError('PRIVATE container data')
        requests=[]
        def respond(request):
            requests.append(request)
            if case=='timeout': raise httpx.ReadTimeout('PRIVATE URL',request=request)
            return httpx.Response(int(case),request=request)
        tasks=FileMeetingTasks(Runner(), root,
              audio_archive=Archive() if case in ('unsupported','transcode') else None,
              url_acquirer=UrlMediaAcquirer(http_transport=httpx.MockTransport(respond)))
        if case in ('403','404','timeout'):
            await tasks._acquire_and_run(handle,'https://user:secret@media.test/file',directory,asyncio.Event())
            assert requests[0].headers['user-agent'].startswith('Mozilla/')
        else: await tasks._run(handle,source,asyncio.Event())
        record=(await handle.snapshot()).to_dict()
        assert record['status']==('failed' if expected else 'completed')
        assert record.get('failure_code')==expected
        if expected: assert record['failure_reason'] and 'PRIVATE' not in record['failure_reason'] and 'secret' not in record['failure_reason']
        else: assert record['notice']=='No speech detected.' and record['transcript']=={'segments':[]}
        other,_=await store.bootstrap_browser(None)
        assert await store.workspace(other).open_meeting(meeting_id) is None
        await store.close()
        store=await Phase2Store.open(database)
        account,_=await store.bootstrap_browser(cookie)
        assert (await store.workspace(account).list_meetings())[0].to_dict()==record
        await store.close()
    asyncio.run(run())
    assert 'PRIVATE' not in caplog.text and 'secret' not in caplog.text
    if expected: assert expected in caplog.text
