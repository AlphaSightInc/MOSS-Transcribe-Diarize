"""Reported incomplete media/output must remain visible after saving/reopening."""
import asyncio
from pathlib import Path
import subprocess
from types import SimpleNamespace
import wave

import pytest

from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive
from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks


@pytest.mark.parametrize('case', ['healthy', 'truncated_media', 'decoder_cap'])
def test_reported_truncation_survives_saved_meeting(tmp_path, case):
    async def run():
        root = tmp_path / 'file-work'
        directory = root / 'input'
        directory.mkdir(parents=True)
        wav = directory / 'source.wav'
        with wave.open(str(wav), 'wb') as out:
            out.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\x10\x00\xf0\xff' * (8000 * 12))
        source = directory / 'PRIVATE-name.mp3'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(wav), str(source)], check=True)
        if case == 'truncated_media':
            data = source.read_bytes()
            source.write_bytes(data[:int(len(data) * .6)])
        class Runner:
            def transcribe(self, *args, **kwargs):
                return SimpleNamespace(text='[0][S01]saved words[1]',
                                       possibly_truncated=case == 'decoder_cap')
        store = await Phase2Store.open(tmp_path / 'state.sqlite3')
        account, cookie = await store.bootstrap_browser(None)
        handle = await store.workspace(account).create_meeting('file')
        tasks = FileMeetingTasks(Runner(), root, audio_archive=MeetingAudioArchive(tmp_path / 'audio'))
        await tasks._run(handle, source, asyncio.Event())
        record = (await handle.snapshot()).to_dict()
        assert record['status'] == 'completed'
        expected = {
            'healthy': None,
            'truncated_media': 'The media decoder reported incomplete audio. This transcript may cover only part of the recording.',
            'decoder_cap': 'The speech decoder reached its output limit. This transcript may be incomplete.',
        }[case]
        assert record.get('notice') == expected
        assert 'PRIVATE' not in (record.get('notice') or '')
        assert record['transcript']['segments'][0]['text'] == 'saved words'
        await store.close()
        reopened = await Phase2Store.open(tmp_path / 'state.sqlite3')
        account, _ = await reopened.bootstrap_browser(cookie)
        rows = await reopened.workspace(account).list_meetings()
        assert rows[0].to_dict().get('notice') == expected
        await reopened.close()
    asyncio.run(run())
