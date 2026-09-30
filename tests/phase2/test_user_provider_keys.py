"""Per-user provider keys at the HTTP boundary (plan r3 I-2, Q4): required, used, never kept."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from moss_transcribe_diarize.app.gemini_file_runner import GeminiFileRunner
from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase, GeminiLiveRuntime, GeminiRolling, GeminiSegment, ScriptedGeminiEngine)
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_span_bounds import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from test_owner_bound_file_meeting import await_terminal, provision, session

SAMPLE = Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"
SENTINEL = "sk-SENTINEL-7f3a9c-user-key"
RESULT = {"summary": "A grounded result.", "topics": [{"title": "Useful title", "description": "Why."}],
          "details": [], "speaker_background": [], "data_references": []}


class Diarizer:
    def diarize(self, pcm16, *, deadline, kind, diarize=True):
        return GeminiWords((GeminiWord("hello", "spk:1", 0, 3 * LIVE_SAMPLE_RATE),))


class Encoder:
    spec = SimpleNamespace(provider="wespeaker", revision="pinned", state_sha256="ab" * 32)


class Gate:
    def filter(self, pcm16, words):
        return words


class Evidence:
    def enrollment_observation(self, audio_path, segments):
        return None


class Acquirer:
    async def acquire(self, source_url: str, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "input.wav"
        path.write_bytes(SAMPLE.read_bytes())
        return path


def file_runner(jobs: list):
    return GeminiFileRunner(lambda transcription: jobs.append(transcription) or Diarizer(),
                            Encoder(), identity_resolver=Evidence(), word_gate=Gate(),
                            voiced_audio=lambda _pcm: True)


def test_file_and_url_routes_require_the_users_key_and_hand_it_to_the_job(tmp_path):
    sessions = asyncio.run(provision(tmp_path / "moss.sqlite"))
    jobs: list = []
    app = create_phase2_app(database_path=tmp_path / "moss.sqlite", file_runner=file_runner(jobs),
                            file_work_root=tmp_path / "file-work", url_acquirer=Acquirer())
    upload = {"file": (SAMPLE.name, SAMPLE.read_bytes(), "audio/wav")}
    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        for form in ({}, {"transcription": json.dumps({"vendor": "gemini", "api_key": " "})}):
            refused = client.post("/api/meetings/file", files=upload, data=form)
            assert refused.status_code == 400
            assert refused.json()["detail"] == {"code": "api_key_required"}
        for bad in ("not json", json.dumps({"api_key": "k", "extra": 1}),
                    json.dumps({"vendor": "openai_compatible", "model": "m"})):
            refused = client.post("/api/meetings/file", files=upload, data={"transcription": bad})
            assert refused.status_code == 400
            assert isinstance(refused.json()["detail"], str)
        refused = client.post("/api/meetings/url", json={"url": "https://media.example/a.wav"})
        assert refused.status_code == 400
        assert refused.json()["detail"] == {"code": "api_key_required"}
        assert client.get("/api/meetings").json()["meetings"] == []  # Refused before creation.

        compatible = {"vendor": "openai_compatible", "url": "http://127.0.0.1:18720/v1",
                      "model": "whisper-1", "api_key": None}
        created = client.post("/api/meetings/file", files=upload,
                              data={"transcription": json.dumps(compatible)})
        assert created.status_code == 201, created.text
        await_terminal(client, created.json()["id"], "completed")
        created = client.post("/api/meetings/url", json={
            "url": "https://media.example/a.wav",
            "transcription": {"vendor": "gemini", "model": "gemini-x", "api_key": "url-key"}})
        assert created.status_code == 201, created.text
        await_terminal(client, created.json()["id"], "completed")
    assert jobs == [compatible, {"vendor": "gemini", "url": None, "model": "gemini-x",
                                 "api_key": "url-key"}]


class FakeGeminiModels:
    def __init__(self, outcome):
        self.outcome = outcome
        self.seen = []

    async def get(self, *, model):
        self.seen.append(model)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return SimpleNamespace(name=f"models/{model}")


def gemini_client(monkeypatch, outcome):
    models = FakeGeminiModels(outcome)
    keys = []

    class Client:
        def __init__(self, *, api_key, **_kwargs):
            keys.append(api_key)

            async def aclose():
                pass
            self.aio = SimpleNamespace(models=models, aclose=aclose)

    monkeypatch.setattr("google.genai.Client", Client)
    return models, keys


def test_provider_test_route_checks_gemini_key_and_model(tmp_path, monkeypatch):
    from google.genai import errors
    app = create_phase2_app(database_path=tmp_path / "moss.sqlite")
    body = {"purpose": "transcription", "vendor": "gemini", "url": None, "model": "", "api_key": "k"}
    with TestClient(app, base_url="https://moss.test") as client:
        assert client.post("/api/providers/test", json=body).status_code == 401
        client.post("/api/workspace/bootstrap")
        models, keys = gemini_client(monkeypatch, None)
        assert client.post("/api/providers/test", json=body).json() == {"ok": True}
        assert client.post("/api/providers/test", json={**body, "purpose": "summary"}).json() == {"ok": True}
        assert models.seen == ["gemini-3.5-transcribe", "gemini-3.5-flash-lite"] and keys == ["k", "k"]
        for outcome, detail in (
                (errors.APIError(404, {"error": {"message": "gone", "status": "NOT_FOUND"}}),
                 "Gemini has no model named gemini-3.5-transcribe."),
                (errors.APIError(400, {"error": {"message": "API key not valid", "status": "INVALID_ARGUMENT"}}),
                 "Gemini rejected this API key."),
                (errors.APIError(503, {"error": {"message": "busy", "status": "UNAVAILABLE"}}),
                 "Gemini answered with an error (503)."),
                (OSError("offline"), "Could not reach Gemini.")):
            gemini_client(monkeypatch, outcome)
            assert client.post("/api/providers/test", json=body).json() == {"ok": False, "detail": detail}
        _, keys = gemini_client(monkeypatch, None)
        assert client.post("/api/providers/test", json={**body, "api_key": " "}).json() == {
            "ok": False, "detail": "Enter your Gemini API key."}
        assert keys == []
        for invalid in ([], {**body, "purpose": "other"}, {**body, "vendor": "moss"},
                        {**body, "extra": 1}, {**body, "api_key": 3}):
            assert client.post("/api/providers/test", json=invalid).status_code == 400


def test_provider_test_route_lists_openai_compatible_models(tmp_path):
    seen = []
    replies = {}

    def handler(request):
        seen.append((str(request.url), request.headers.get("authorization")))
        return replies["next"]

    app = create_phase2_app(database_path=tmp_path / "moss.sqlite")
    body = {"purpose": "transcription", "vendor": "openai_compatible",
            "url": "http://127.0.0.1:18720/v1/", "model": "whisper-1", "api_key": "local"}
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        app.state.provider_test_transport = httpx.MockTransport(handler)
        replies["next"] = httpx.Response(200, json={"data": [{"id": "whisper-1"}, {"id": "other"}]})
        assert client.post("/api/providers/test", json=body).json() == {"ok": True}
        assert seen == [("http://127.0.0.1:18720/v1/models", "Bearer local")]
        assert client.post("/api/providers/test", json={**body, "api_key": None}).json() == {"ok": True}
        assert seen[-1][1] is None  # The key is optional for this vendor.
        replies["next"] = httpx.Response(200, json={"data": [{"id": "other"}]})
        assert client.post("/api/providers/test", json=body).json() == {
            "ok": False, "detail": "The server does not list a model named whisper-1."}
        replies["next"] = httpx.Response(200, text="no list here")
        assert client.post("/api/providers/test", json=body).json() == {"ok": True}
        replies["next"] = httpx.Response(401, json={})
        assert client.post("/api/providers/test", json=body).json() == {
            "ok": False, "detail": "The server rejected this API key."}
        replies["next"] = httpx.Response(500, json={})
        assert client.post("/api/providers/test", json=body).json() == {
            "ok": False, "detail": "The server answered 500 for http://127.0.0.1:18720/v1/models."}

        def unreachable(request):
            raise httpx.ConnectError("refused", request=request)
        app.state.provider_test_transport = httpx.MockTransport(unreachable)
        assert client.post("/api/providers/test", json=body).json() == {
            "ok": False, "detail": "Could not reach the server."}
        for detail, change in (("Enter the server URL (http or https).", {"url": "ftp://x"}),
                               ("Enter the model name.", {"model": " "})):
            assert client.post("/api/providers/test", json={**body, **change}).json() == {
                "ok": False, "detail": detail}


def test_summary_with_an_unpriced_user_model_reports_tokens_without_cost(monkeypatch):
    from moss_transcribe_diarize.app.phase2_llm import GeminiSummaryGenerator

    class Models:
        async def generate_content(self, **_kwargs):
            return SimpleNamespace(text=json.dumps(RESULT), usage_metadata=SimpleNamespace(
                prompt_token_count=10, candidates_token_count=2, thoughts_token_count=None))

    class Client:
        def __init__(self, *, api_key):
            async def aclose():
                pass
            self.aio = SimpleNamespace(models=Models(), aclose=aclose)

    monkeypatch.setattr("google.genai.Client", Client)
    _, usage = asyncio.run(GeminiSummaryGenerator()(
        {"segments": []}, model="gemini-future", language="", prompt="P", api_key="k"))
    assert usage == {"model": "gemini-future", "input_tokens": 10, "output_tokens": 2,
                     "cost_usd": None}


class ScriptedMeeting(ScriptedGeminiEngine):
    """Forty-five rolling words, then an improved terminal pass after Stop."""

    published = 0

    def push_audio(self, start_sample, pcm16):
        self.end_sample = start_sample + len(pcm16) // 2
        if start_sample == 0:
            self._window(" ".join(f"word{i}" for i in range(45)))

    def _window(self, text):
        start, self.published = self.published, self.end_sample
        self._publish(GeminiBase(self.end_sample, ()))
        self._publish(GeminiRolling(start, self.end_sample, (GeminiSegment(
            start, self.end_sample, text, "speaker-0001", "system"),), revision_lanes=("system",)))

    async def drain_tail(self, deadline):
        if self.end_sample > self.published:
            self._window("tail")
        return True

    async def finish(self, tape):
        return (GeminiSegment(0, self.end_sample, "improved words", "terminal-a", "system"),)


def lane_frame(sequence: int, lane: str) -> dict[str, object]:
    return {"lane": lane, "sequence": sequence, "capture_timestamp_ns": sequence * 1_000_000_000,
            "device_epoch": 0, "sample_count": 16000, "sample_rate": LIVE_SAMPLE_RATE,
            "pcm_base64": base64.b64encode(
                (b"\x01\x00" if lane == "system" else b"\0\0") * 16000).decode("ascii"),
            "silent": False, "discontinuity": False}


def test_user_key_is_used_but_never_reaches_storage_diagnostics_or_logs(tmp_path, caplog, capsys):
    caplog.set_level(logging.DEBUG)
    database = tmp_path / "moss.sqlite"
    sessions = asyncio.run(provision(database))
    engine_keys, summary_keys, jobs, test_headers = [], [], [], []

    async def summarize(document, *, model, language, prompt, api_key):
        summary_keys.append(api_key)
        return RESULT, {"model": model, "input_tokens": 1, "output_tokens": 1, "cost_usd": None}

    descriptor = LiveServiceDescriptor(
        source_revision="test", provider_name="gemini", provider_revision="test",
        provider_manifest_hash="0" * 64,
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=16000, max_queue_depth=4,
                                 max_retained_samples=32000, max_identity_speakers=8,
                                 max_events=64, max_tape_bytes=160000), frame_samples=16000)
    runtime = GeminiLiveRuntime(
        descriptor=descriptor, tape_storage_root=tmp_path / "tapes",
        engine_factory=lambda _id, publish, _usage, settings: (
            engine_keys.append(settings["transcription"]["api_key"])
            or ScriptedMeeting(publish, batches=[], terminal=())))
    app = create_phase2_app(
        database_path=database, live_runtime_factory=lambda: runtime,
        live_helper_lease_seconds=30.0, meeting_audio_root=tmp_path / "meetings",
        file_runner=file_runner(jobs), file_work_root=tmp_path / "file-work",
        summary_generator=summarize)
    provider = {"vendor": "gemini", "model": "gemini-3.5-flash-lite", "api_key": SENTINEL}
    transcription = {"vendor": "gemini", "api_key": SENTINEL}
    responses: list[str] = []

    def keep(response):
        responses.append(response.text)
        return response

    with TestClient(app, base_url="https://moss.test") as client:
        session(client, sessions["sub-a"])
        # Refusals must not echo the key either.
        keep(client.post("/api/live/sessions", json={"engine_settings": {
            "transcription": transcription, "refresh_seconds": 0}}))
        keep(client.post("/api/meetings/file", files={"file": (SAMPLE.name, b"x", "audio/wav")},
                         data={"transcription": json.dumps({**transcription, "extra": 1})}))
        created = keep(client.post("/api/live/sessions", json={"engine_settings": {
            "transcription": transcription, "cleanup_after_stop": True}}))
        assert created.status_code == 201, created.text
        meeting_id = created.json()["id"]
        for sequence in range(3):
            for lane in ("system", "microphone"):
                keep(client.post(f"/api/live/sessions/{meeting_id}/frames",
                                 json=lane_frame(sequence, lane)))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            live = keep(client.post(f"/api/meetings/{meeting_id}/summary/live",
                                    json={"provider": provider}))
            if live.status_code == 200:
                break
            time.sleep(.02)
        assert live.status_code == 200, live.text
        snapshot = keep(client.get(f"/api/live/sessions/{meeting_id}/snapshot")).json()["snapshot"]
        assert snapshot["engine_diagnostics"]["engine_settings"]["transcription"]["api_key"] == "[redacted]"
        keep(client.get(f"/api/live/sessions/{meeting_id}/events?since_seq=-1"))
        keep(client.post(f"/api/live/sessions/{meeting_id}/stop", json={"deadline": 2}))
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            detail = keep(client.get(f"/api/meetings/{meeting_id}")).json()
            if detail["status"] == "completed" and detail.get("refinement_state") != "running":
                break
            time.sleep(.02)
        assert [row["text"] for row in detail["transcript"]["segments"]] == ["improved words"]
        server = keep(client.post(f"/api/meetings/{meeting_id}/summary/server", json={
            "source_version": detail["transcript_version"], "provider": provider}))
        assert server.status_code == 200, server.text

        uploaded = keep(client.post("/api/meetings/file",
                                    files={"file": (SAMPLE.name, SAMPLE.read_bytes(), "audio/wav")},
                                    data={"transcription": json.dumps(transcription)}))
        assert uploaded.status_code == 201, uploaded.text
        keep(client.get(f"/api/meetings/{await_terminal(client, uploaded.json()['id'], 'completed')['id']}"))

        def listing(request):
            test_headers.append(request.headers.get("authorization"))
            return httpx.Response(200, json={"data": [{"id": "whisper-1"}]})
        app.state.provider_test_transport = httpx.MockTransport(listing)
        assert keep(client.post("/api/providers/test", json={
            "purpose": "transcription", "vendor": "openai_compatible",
            "url": "http://127.0.0.1:18720/v1", "model": "whisper-1",
            "api_key": SENTINEL})).json() == {"ok": True}
        keep(client.get("/api/meetings"))

    # The key did its job in memory...
    assert engine_keys == [SENTINEL]
    assert summary_keys == [SENTINEL, SENTINEL]
    assert [job["api_key"] for job in jobs] == [SENTINEL]
    assert test_headers == [f"Bearer {SENTINEL}"]
    # ...and nothing durable or observable holds it: SQLite (+WAL), audio, work dirs,
    # tapes, every API response (diagnostics included), and every log line.
    stored = [path for path in tmp_path.rglob("*") if path.is_file()]
    assert any(path.name.startswith("moss.sqlite") for path in stored)
    assert [path for path in stored if SENTINEL.encode() in path.read_bytes()] == []
    assert [text for text in responses if SENTINEL in text] == []
    captured = capsys.readouterr()
    assert SENTINEL not in caplog.text + captured.out + captured.err
