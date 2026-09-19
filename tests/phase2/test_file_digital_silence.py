"""Real media normalization and persisted File outcome; no shared decoder policy."""
import io
import time
import wave
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


def wav(pcm):
    output=io.BytesIO()
    with wave.open(output,'wb') as stream:
        stream.setparams((1,2,16000,0,'NONE','not compressed')); stream.writeframes(pcm)
    return output.getvalue()


@pytest.mark.parametrize('pcm,expected_calls', [
    (bytes(32000),0), (b'\1\0'*16000,1), (bytes(1048576)+b'\1\0',1),
], ids=['zero','one-bit-quiet','last-sample-after-chunk'])
def test_real_mix_dispatch_keeps_one_bit_signal(tmp_path,pcm,expected_calls):
    calls=[]
    class Runner:
        def transcribe(self,*a,**kw):
            calls.append(kw); return SimpleNamespace(text='[0][S01]speech[1]')
    source=tmp_path/'source.wav'; source.write_bytes(wav(pcm))
    archive=MeetingAudioArchive(tmp_path/'archive')
    tasks=FileMeetingTasks(Runner(),tmp_path/'file-work',audio_archive=archive)
    result,mix,notices=tasks._transcribe_from_one_mix(source,{'max_length':16384,'max_new_tokens':12000})
    assert notices == []
    assert len(calls)==expected_calls
    if expected_calls:
        assert calls==[{
            'max_length':16384,
            'max_new_tokens':12000,
            'checkpoint_dir':None,
        }]
        assert result.text=='[0][S01]speech[1]'
    else:
        assert result.text=='' and result.generated_tokens==0
        assert result.window_diagnostics[0]['detector']=='digital_zero'
    assert mix.is_file()


def test_silence_persists_notice_and_audio_while_empty_file_fails(tmp_path):
    class Runner:
        def transcribe(self,*a,**kw):
            raise AssertionError('invalid or zero media reached decoder')
    app=create_phase2_app(database_path=tmp_path/'state.sqlite',file_runner=Runner(),
        file_work_root=tmp_path/'file-work',meeting_audio_root=tmp_path/'audio')
    with TestClient(app, base_url="https://moss.test") as client:
        assert client.post("/api/workspace/bootstrap").status_code == 200
        for payload,expected in [(wav(bytes(32000)),'completed'),(b'','failed')]:
            response=client.post('/api/meetings/file',files={'file':('input.wav',payload,'audio/wav')})
            assert response.status_code==201
            mid=response.json()['id']
            for _ in range(100):
                result=client.get(f'/api/meetings/{mid}').json()
                if result['status']!='active': break
                time.sleep(.02)
            assert result['status']==expected
            history=client.get('/api/meetings').json()['meetings']
            saved=next(m for m in history if m['id']==mid)
            if expected=='completed':
                assert result['transcript']=={'segments':[]}
                assert result['notice']==saved['notice']=='No speech detected.'
                assert result['audio']['state']=='available'
                assert client.get(f'/api/meetings/{mid}/audio/download').status_code==200
            else:
                assert result['failure_code']=='transcode_failed'
                assert 'notice' not in result


def test_size_preflight_is_owner_bound_and_does_not_reserve_or_create(tmp_path,monkeypatch):
    from moss_transcribe_diarize.app import phase2_file
    app=create_phase2_app(database_path=tmp_path/'state.sqlite',file_runner=object(),
        file_work_root=tmp_path/'file-work',meeting_audio_root=tmp_path/'audio')
    reserve=phase2_file.UPLOAD_CAPACITY_RESERVE_BYTES
    with TestClient(app,base_url='https://moss.test') as client:
        assert client.post('/api/meetings/file/admission',json={'file_bytes':5}).status_code==401
        assert client.post('/api/workspace/bootstrap').status_code==200
        monkeypatch.setattr(phase2_file.shutil,'disk_usage',lambda _:SimpleNamespace(free=reserve+10))
        assert client.post('/api/meetings/file/admission',json={'file_bytes':5}).status_code==204
        denied=client.post('/api/meetings/file/admission',json={'file_bytes':6})
        assert denied.status_code==507 and denied.json()=={'detail':'Insufficient storage for upload.'}
        for payload in ({}, {'file_bytes':-1}, {'file_bytes':True}, {'file_bytes':'6'}, []):
            assert client.post('/api/meetings/file/admission',json=payload).status_code==400
        # Preflight success neither reserves space nor bypasses the real body check.
        actual=client.post('/api/meetings/file',files={'file':('media.wav',b'audio','audio/wav')})
        assert actual.status_code==507
        assert client.get('/api/meetings').json()['meetings']==[]
        assert not list((tmp_path/'file-work').iterdir())
