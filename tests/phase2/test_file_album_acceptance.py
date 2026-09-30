"""A4: real File task -> album -> save/reopen/export/rename/enrollment.
Fake perfect voice vectors remove acoustic uncertainty; real WAV/MP3 archive path.
"""
import asyncio
import json
import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner
from test_owner_bound_file_meeting import provision, session, wav_bytes, await_terminal


class Encoder:
    descriptor={'provider':'test'}
    spec=SimpleNamespace(provider='test',revision='one',state_sha256='test')
    def embed(self,path,intervals):
        return [1.,0.] if intervals[0][0] % 120 < 30 else [0.,1.]
    def embed_intervals(self,path,intervals):
        return [self.embed(path,[interval]) for interval in intervals]


class Decoder:
    model_path='test'
    def transcribe(self,audio_path,**kwargs):
        return TranscriptionResult('[20][S01]alpha words[25][40][S02]beta words[45]',
                                   1,1,0.,'test',str(audio_path),'greedy',None)


def test_file_album_save_restart_exports_rename_enroll_and_private_bank(tmp_path):
    database=tmp_path/'m.sqlite'
    sessions=asyncio.run(provision(database))
    config=SimpleNamespace(identity_config=dict(max_speakers=16,min_match_score=.35,min_match_margin=.1),identity_provider=dict(min_segment_samples=8000))
    def app():
        runner=WindowedRunner(Decoder(),identity_resolver=AlbumIdentityResolver(config=config,encoder=Encoder()))
        return create_phase2_app(database_path=database,file_runner=runner,file_work_root=tmp_path/'file-work')
    with TestClient(app(),base_url='https://moss.test') as client:
        session(client,sessions['sub-a'])
        response=client.post('/api/meetings/file',files={'file':('test.wav',wav_bytes(frames=360*16000),'audio/wav')})
        assert response.status_code==201,response.text
        mid=response.json()['id']; meeting=await_terminal(client,mid,'completed')
        assert len(meeting['transcript']['segments'])==6
        assert [s['speaker'] for s in meeting['transcript']['segments']]==['Speaker 1','Speaker 2']*3
        assert [s['speaker_entity_id'] for s in meeting['transcript']['segments']]==['S01','S02']*3
        before=[(s['start'],s['end'],s['text']) for s in meeting['transcript']['segments']]
    with TestClient(app(),base_url='https://moss.test') as client:
        session(client,sessions['sub-a-second'])
        assert client.get(f'/api/meetings/{mid}').json()['transcript']==meeting['transcript']
        for label in ('Alice','Alice renamed'):
            named=client.put(f'/api/meetings/{mid}/speakers/S01/name',json={'label':label})
            assert named.status_code==200,named.text
            assert named.json()['enrollment']=='enrolled'
            rows=client.get(f'/api/meetings/{mid}').json()['transcript']['segments']
            assert [(s['start'],s['end'],s['text']) for s in rows]==before
            assert [s['speaker'] for s in rows]==[label,'Speaker 2']*3
            assert [s['speaker_entity_id'] for s in rows]==['S01','S02']*3
            bank=client.get('/api/voiceprints').json()['voiceprints']
            assert len(bank)==1 and bank[0]['sample_count']==1 and bank[0]['label']==label
        if output := os.environ.get('WP19_SAVED_FIXTURE'):
            Path(output).write_text(json.dumps(client.get(f'/api/meetings/{mid}').json(),indent=2)+'\n')
        session(client,sessions['sub-b'])
        assert client.get('/api/voiceprints').json()['voiceprints']==[]
        assert client.put(f'/api/meetings/{mid}/speakers/S01/name',json={'label':'Foreign'}).status_code==404
