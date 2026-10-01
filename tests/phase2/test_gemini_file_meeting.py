import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.gemini_file_runner import GeminiFileRunner
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from test_owner_bound_file_meeting import provision, session, await_terminal


def test_file_meeting_completes_and_enrolls_after_name(tmp_path):
    sessions = asyncio.run(provision(tmp_path / "meeting.sqlite"))
    sample = Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"

    class Diarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            assert kind == "terminal" and diarize
            return GeminiWords((GeminiWord("hello", "spk:1", 0, 3 * 16000),))

    class Encoder:
        spec = SimpleNamespace(provider="wespeaker", revision="pinned", state_sha256="ab" * 32)

    class Gate:
        def filter(self, pcm16, words):
            return words

    class Evidence:
        def enrollment_observation(self, audio_path, segments):
            assert audio_path.exists()
            assert [(row["start"], row["end"]) for row in segments] == [(0.0, 2.1)]
            return SimpleNamespace(centroid=(1.0, 0.0), sample_seconds=2.1,
                                   provisional=False, embedder_id="wespeaker:pinned")

    jobs = []
    runner = GeminiFileRunner(lambda transcription: jobs.append(transcription) or Diarizer(),
                              Encoder(), identity_resolver=Evidence(),
                              word_gate=Gate(), voiced_audio=lambda _pcm: True)
    app = create_phase2_app(database_path=tmp_path / "meeting.sqlite", file_runner=runner,
                            file_work_root=tmp_path / "file-work")
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        uploaded = client.post("/api/meetings/file", files={"file": (sample.name, sample.read_bytes(), "audio/wav")},
                               data={"transcription": '{"vendor": "gemini", "api_key": "user-key"}'})
        assert uploaded.status_code == 201, uploaded.text
        meeting = await_terminal(client, uploaded.json()["id"], "completed")
        assert meeting["transcript"]["segments"][0]["speaker"] == "Speaker 1"
        assert meeting["transcript"]["segments"][0]["speaker_entity_id"] == "S01"
        assert jobs == [{"vendor": "gemini", "url": None, "model": "gemini-3.5-transcribe",
                         "api_key": "user-key"}]
        named = client.put(f"/api/meetings/{meeting['id']}/speakers/S01/name", json={"label": "Alex"})
        assert named.status_code == 200, named.text
        # The fingerprint runs after the name is saved (issue #15).
        assert named.json()["enrollment"] == "pending"
        deadline = time.monotonic() + 5
        while not (voiceprints := client.get("/api/voiceprints").json()["voiceprints"]):
            assert time.monotonic() < deadline, "voiceprint was not enrolled"
            time.sleep(.02)
        assert [(v["label"], v["sample_count"]) for v in voiceprints] == [("Alex", 1)]


def test_file_meeting_saves_chinese_without_spaces_between_characters(tmp_path):
    # F1: File/URL shares the word join with Live; one Gemini word per Chinese character.
    sessions = asyncio.run(provision(tmp_path / "meeting.sqlite"))
    sample = Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"
    words = ["大", "家", "好，", "今", "天", "讨", "论", "API", "的", "进", "展。"]

    class Diarizer:
        def diarize(self, pcm16, *, deadline, kind, diarize=True):
            return GeminiWords(tuple(GeminiWord(text, "spk:1", index * 3200, index * 3200 + 3000)
                                     for index, text in enumerate(words)))

    class Encoder:
        spec = SimpleNamespace(provider="wespeaker", revision="pinned", state_sha256="ab" * 32)

    class Gate:
        def filter(self, pcm16, words):
            return words

    class Evidence:
        def enrollment_observation(self, audio_path, segments):
            return None

    runner = GeminiFileRunner(lambda _transcription: Diarizer(), Encoder(), identity_resolver=Evidence(),
                              word_gate=Gate(), voiced_audio=lambda _pcm: True)
    app = create_phase2_app(database_path=tmp_path / "meeting.sqlite", file_runner=runner,
                            file_work_root=tmp_path / "file-work")
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        uploaded = client.post("/api/meetings/file", files={"file": (sample.name, sample.read_bytes(), "audio/wav")},
                               data={"transcription": '{"vendor": "gemini", "api_key": "user-key"}'})
        assert uploaded.status_code == 201, uploaded.text
        meeting = await_terminal(client, uploaded.json()["id"], "completed")
        assert [row["text"] for row in meeting["transcript"]["segments"]] == ["大家好，今天讨论API的进展。"]
