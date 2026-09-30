import asyncio
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
        assert meeting["transcript"]["segments"][0]["speaker"] == "S01"
        assert jobs == [{"vendor": "gemini", "url": None, "model": "gemini-3.5-transcribe",
                         "api_key": "user-key"}]
        named = client.put(f"/api/meetings/{meeting['id']}/speakers/S01/name", json={"label": "Alex"})
        assert named.status_code == 200, named.text
        assert named.json()["enrollment"] == "enrolled"
