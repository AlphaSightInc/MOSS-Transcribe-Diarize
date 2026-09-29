import asyncio
import wave
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive
from moss_transcribe_diarize.app.phase2_speaker_identity import AccountSpeakerIdentity
from tests.phase2.test_manual_speaker_voiceprints import provision


def wav_file(path: Path) -> Path:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(bytes(6 * 32000))
    return path


def test_completed_live_enrolls_only_nonoverlapping_saved_rows(tmp_path):
    async def exercise():
        store, workspace, _ = await provision(tmp_path / "identity.sqlite")
        archive = MeetingAudioArchive(tmp_path / "meetings")
        observed = []

        def live_evidence(path, segments):
            assert path.exists()
            observed.append([(row["start"], row["end"]) for row in segments])
            seconds = sum(row["end"] - row["start"] for row in segments)
            return SimpleNamespace(centroid=(1.0, 0.0), sample_seconds=seconds,
                                   provisional=False, embedder_id="wespeaker:pinned")

        identity = AccountSpeakerIdentity(store, None, audio_archive=archive,
                                          live_evidence=live_evidence)
        try:
            meeting = await workspace.create_meeting("live")
            await meeting.publish_audio(archive, wav_file(tmp_path / "saved.wav"))
            await meeting.finish_with_transcript({"segments": [
                {"start": 0.0, "end": 3.0, "speaker": "A", "speaker_entity_id": "speaker-0001", "source_lane": "system", "text": "one"},
                {"start": 1.0, "end": 2.0, "speaker": "B", "speaker_entity_id": "speaker-0002", "source_lane": "microphone", "text": "two"},
                {"start": 4.0, "end": 5.0, "speaker": "A", "speaker_entity_id": "speaker-0001", "source_lane": "system", "text": "three"},
            ]}, "completed")
            named = await identity.bank(workspace).name_speaker(meeting, "speaker-0001", "Alex")
            assert named.enrollment == "enrolled"
            assert observed == [[(0.0, 1.0), (2.0, 3.0), (4.0, 5.0)]]
            assert (await identity.bank(workspace).list_voiceprints())[0].embedder_id == "wespeaker:pinned"
        finally:
            await store.close()

    asyncio.run(exercise())


def test_completed_live_refuses_less_than_two_unoverlapped_seconds(tmp_path):
    async def exercise():
        store, workspace, _ = await provision(tmp_path / "identity.sqlite")
        archive = MeetingAudioArchive(tmp_path / "meetings")
        calls = []

        def live_evidence(_path, segments):
            calls.append(segments)
            return None

        identity = AccountSpeakerIdentity(store, None, audio_archive=archive,
                                          live_evidence=live_evidence)
        try:
            meeting = await workspace.create_meeting("live")
            await meeting.publish_audio(archive, wav_file(tmp_path / "saved.wav"))
            await meeting.finish_with_transcript({"segments": [
                {"start": 0.0, "end": 2.0, "speaker": "A", "speaker_entity_id": "speaker-0001", "text": "one"},
                {"start": .5, "end": 1.5, "speaker": "B", "speaker_entity_id": "speaker-0002", "text": "two"},
            ]}, "completed")
            named = await identity.bank(workspace).name_speaker(meeting, "speaker-0001", "Alex")
            assert named.enrollment == "unavailable"
            assert calls == []
            assert await identity.bank(workspace).list_voiceprints() == []
        finally:
            await store.close()

    asyncio.run(exercise())
