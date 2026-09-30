import asyncio
import threading
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
            assert named.enrollment == "pending"
            await identity.shutdown()  # joins the fingerprint that runs after naming returns
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


async def _saved_meeting(workspace, archive, tmp_path, *, mode="live"):
    meeting = await workspace.create_meeting(mode)
    await meeting.publish_audio(archive, wav_file(tmp_path / "saved.wav"))
    await meeting.finish_with_transcript({"segments": [
        {"start": 0.0, "end": 3.0, "speaker": "A", "speaker_entity_id": "speaker-0001", "text": "one"},
        {"start": 4.0, "end": 5.0, "speaker": "B", "speaker_entity_id": "speaker-0002", "text": "two"},
    ]}, "completed")
    return meeting


def test_saved_rename_returns_before_the_fingerprint_and_frees_the_bank_lock(tmp_path):
    """Issue #15: fingerprinting a long saved meeting took minutes inside the request and
    held the Account-wide identity lock, stalling every Live publication meanwhile."""
    async def exercise():
        store, workspace, _ = await provision(tmp_path / "identity.sqlite")
        archive = MeetingAudioArchive(tmp_path / "meetings")
        release, calls = threading.Event(), []

        def live_evidence(_path, segments):
            calls.append(segments)
            assert release.wait(10)
            return SimpleNamespace(centroid=(1.0, 0.0), sample_seconds=3.0,
                                   provisional=False, embedder_id="wespeaker:pinned")

        identity = AccountSpeakerIdentity(store, None, audio_archive=archive,
                                          live_evidence=live_evidence)
        bank = identity.bank(workspace)
        try:
            meeting = await _saved_meeting(workspace, archive, tmp_path)
            named = await asyncio.wait_for(bank.name_speaker(meeting, "speaker-0001", "Alex"), 2)
            assert named.enrollment == "pending"
            rows = (await meeting.snapshot()).transcript["segments"]
            assert [row["speaker"] for row in rows] == ["Alex", "B"]
            # Renaming again while the fingerprint runs neither waits nor fingerprints twice.
            again = await asyncio.wait_for(bank.name_speaker(meeting, "speaker-0001", "Alexander"), 2)
            assert again.enrollment == "pending"
            async with asyncio.timeout(2):
                async with identity.publication(meeting, ()):
                    pass
            assert await bank.list_voiceprints() == []
            release.set()
            await identity.shutdown()
            assert len(calls) == 1
            assert [(v.label, v.sample_count) for v in await bank.list_voiceprints()] == [("Alexander", 1)]
        finally:
            release.set()
            await store.close()

    asyncio.run(exercise())


def test_saved_rename_without_voiceprint_cancels_a_running_fingerprint(tmp_path):
    async def exercise():
        store, workspace, _ = await provision(tmp_path / "identity.sqlite")
        archive = MeetingAudioArchive(tmp_path / "meetings")
        release = threading.Event()

        def live_evidence(_path, _segments):
            assert release.wait(10)
            return SimpleNamespace(centroid=(1.0, 0.0), sample_seconds=3.0,
                                   provisional=False, embedder_id="wespeaker:pinned")

        identity = AccountSpeakerIdentity(store, None, audio_archive=archive,
                                          live_evidence=live_evidence)
        bank = identity.bank(workspace)
        try:
            meeting = await _saved_meeting(workspace, archive, tmp_path)
            await asyncio.wait_for(bank.name_speaker(meeting, "speaker-0001", "Alex"), 2)
            plain = await asyncio.wait_for(
                bank.name_speaker(meeting, "speaker-0001", "Bo", save_voiceprint=False), 2)
            assert plain.enrollment == "not_requested"
            release.set()
            await identity.shutdown()
            assert await bank.list_voiceprints() == []
            assert identity.pending_count == 0
        finally:
            release.set()
            await store.close()

    asyncio.run(exercise())


def test_saved_file_rename_refuses_under_two_seconds_without_fingerprinting(tmp_path):
    async def exercise():
        store, workspace, _ = await provision(tmp_path / "identity.sqlite")
        archive = MeetingAudioArchive(tmp_path / "meetings")
        calls = []
        identity = AccountSpeakerIdentity(store, None, audio_archive=archive,
                                          file_evidence=lambda *args: calls.append(args))
        try:
            meeting = await _saved_meeting(workspace, archive, tmp_path, mode="file")
            named = await identity.bank(workspace).name_speaker(meeting, "speaker-0002", "Bo")
            assert named.enrollment == "unavailable"
            await identity.shutdown()
            assert calls == []
        finally:
            await store.close()

    asyncio.run(exercise())
