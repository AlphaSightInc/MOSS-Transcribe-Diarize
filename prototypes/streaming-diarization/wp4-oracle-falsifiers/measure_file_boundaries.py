"""PROTOTYPE — exercise real FileMeetingTasks with isolated injected stage outcomes.
One command: PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/streaming-diarization/wp4-oracle-falsifiers/measure_file_boundaries.py
Question: can the File boundary distinguish acquisition, transcode, decoder failure,
and no speech? Falsifier: stages collapse or malformed decode equals no speech.
Scratch files remain inside the assigned worktree and are deleted automatically.
"""
import asyncio
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks

class Handle:
    meeting_id = 'prototype'; owner_key = ('prototype', 1)
    def __init__(self): self.state = dict(status='active', transcript=None)
    async def finish(self, status): self.state['status'] = status
    async def commit_transcript(self, document): self.state['transcript'] = document
    async def record_audio_unavailable(self): self.state['audio'] = 'unavailable'
    async def publish_audio(self, archive, path): self.state['audio'] = 'available'

class Runner:
    def __init__(self, text='', failure=None): self.text, self.failure = text, failure
    def transcribe(self, path, **kw):
        if self.failure: raise self.failure
        return SimpleNamespace(text=self.text)

class Archive:
    def prepare_mix(self, source, destination): raise RuntimeError('fixture transcode error')

class Acquirer:
    def __init__(self, code): self.code = code
    async def acquire(self, *args): raise RuntimeError(self.code)

async def main():
    cases = ('403', '404', 'timeout', 'unsupported_container', 'transcode', 'decoder', 'no_speech', 'malformed_decoder')
    for case in cases:
        with tempfile.TemporaryDirectory(dir='evidence/mvpfix/wp4', prefix='PROTOTYPE-') as temp:
            root=Path(temp)/'file-work'; directory=root/'case'; directory.mkdir(parents=True)
            source=directory/'input.media'; source.write_bytes(b'fixture')
            handle=Handle()
            runner=Runner(text='unparseable output' if case=='malformed_decoder' else '',
                          failure=RuntimeError('fixture decoder error') if case in ('decoder','unsupported_container') else None)
            tasks=FileMeetingTasks(runner, root, audio_archive=Archive() if case=='transcode' else None,
                                   url_acquirer=Acquirer(case))
            if case in ('403','404','timeout'):
                await tasks._acquire_and_run(handle, 'https://fixture.invalid/media', directory, asyncio.Event())
            else:
                await tasks._run(handle, source, asyncio.Event())
            document=handle.state.pop('transcript')
            print(json.dumps(dict(case=case, **handle.state, segments=None if document is None else len(document['segments']))))

if __name__=='__main__': asyncio.run(main())
