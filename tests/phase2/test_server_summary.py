from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.phase2_summary import DEFAULT_SUMMARY_PROMPT, MeetingSummaries
from moss_transcribe_diarize.app.phase2_llm import GeminiSummaryGenerator


RESULT = {"summary": "A grounded result.", "topics": [{"title": "Useful title", "description": "A supported mechanism."}],
          "details": [], "speaker_background": [], "data_references": []}
USAGE = {"model": "gemini-3.5-flash-lite", "input_tokens": 100, "output_tokens": 25,
         "cost_usd": 0.0000925}
TRANSCRIPT = {"segments": [{"start": 0, "end": 4, "speaker": "Alex", "text": "Owner A only."}]}


def test_server_prompt_matches_browser_default():
    root = Path(__file__).resolve().parents[2]
    assert DEFAULT_SUMMARY_PROMPT == (root / "frontend/src/lib/final-summary-prompt.txt").read_text(encoding="utf-8")


def test_gemini_generator_sends_transcript_as_user_content_and_closes_client(monkeypatch):
    from google import genai
    import json

    seen = {}

    class FakeModels:
        async def generate_content(self, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(text=json.dumps(RESULT), usage_metadata=SimpleNamespace(
                prompt_token_count=100, candidates_token_count=20, thoughts_token_count=5))

    class FakeAsyncClient:
        models = FakeModels()

        async def aclose(self):
            seen["closed"] = True

    class FakeClient:
        aio = FakeAsyncClient()

        def __init__(self, *, api_key):
            seen["key_passed"] = api_key == "local-key"

    monkeypatch.setattr(genai, "Client", FakeClient)
    result = asyncio.run(GeminiSummaryGenerator("local-key")(
        TRANSCRIPT, model="gemini-3.5-flash-lite", language="French", prompt="Brief"))
    assert result == (RESULT, USAGE)
    assert seen["key_passed"] and seen["closed"]
    assert "Owner A only." in seen["contents"]
    assert "Write the final briefing in French." in seen["config"].system_instruction


def test_server_summary_generates_from_exact_final_version_and_saves(tmp_path: Path):
    calls = []

    async def generate(document, *, model, language, prompt):
        calls.append((document, model, language, prompt))
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        path = f"/api/meetings/{meeting_id}/summary/server"
        assert client.post(path, json={"source_version": 2}).status_code == 409
        response = client.post(path, json={"source_version": 1})
        assert response.status_code == 200, response.text
        assert response.json()["document"] == RESULT
        assert response.json()["usage"] == USAGE
        assert calls[0][0] == TRANSCRIPT
        assert calls[0][1:3] == ("gemini-3.5-flash-lite", "")
        assert "GOAL" in calls[0][3]
        assert client.get(f"/api/meetings/{meeting_id}/summary").json()["summary"]["document"] == RESULT
        assert "usage" not in client.get(f"/api/meetings/{meeting_id}/summary").json()["summary"]
        assert client.get(f"/api/meetings/{meeting_id}").json()["title"] == "Useful title"


def test_server_summary_options_owner_and_one_inflight(tmp_path: Path):
    entered, release = Event(), Event()
    calls = []

    async def generate(document, *, model, language, prompt):
        calls.append((model, language, prompt))
        if len(calls) == 2:
            entered.set()
            await asyncio.to_thread(release.wait, 5)
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        path = f"/api/meetings/{meeting_id}/summary/server"
        assert client.post(path, json={"source_version": 1, "model": "unknown"}).status_code == 400
        assert client.post(path, json={"source_version": 1, "api_key": "wrong"}).status_code == 400
        assert client.post(path, json={"source_version": 1, "model": "gemini-3.8-flash", "language": "French", "prompt": "Brief"}).status_code == 200
        assert calls[0] == ("gemini-3.8-flash", "French", "Brief")
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(client.post, path, json={"source_version": 1})
            assert entered.wait(5)
            assert client.post(path, json={"source_version": 1}).status_code == 429
            release.set()
            assert first.result(timeout=5).status_code == 200
        client.cookies.clear()
        client.post("/api/workspace/bootstrap")
        assert client.post(path, json={"source_version": 1}).status_code == 404


def test_live_summary_is_ephemeral_and_requires_forty_words(tmp_path: Path):
    seen = []

    async def generate(document, *, model, language, prompt):
        seen.append(document)
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("live")
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        words = " ".join(f"word{i}" for i in range(40))
        row = SimpleNamespace(start_sample=0, end_sample=64000, canonical_speaker=None,
                              source_lane="system", text="short")
        session = SimpleNamespace(status="active", committed_samples=64000, text_revision_version=3,
                                  identity_snapshot=SimpleNamespace(canonical_speakers=()),
                                  effective_transcript=[row])
        snapshot = SimpleNamespace(session=session, descriptor=SimpleNamespace(sample_rate=16000))
        binding = SimpleNamespace(public_snapshot=snapshot, speaker_labels={})
        app.state.phase2_live = SimpleNamespace(open=lambda *_args, **_kwargs: binding)
        path = f"/api/meetings/{meeting_id}/summary/live"
        assert client.post(path, json={}).status_code == 409
        row.text = words
        response = client.post(path, json={})
        assert response.status_code == 200, response.text
        assert response.json()["summary"] == RESULT
        assert response.json()["usage"] == USAGE
        assert response.json()["source"] == {"committed_samples": 64000, "text_revision_version": 3}
        assert seen[0]["segments"][0]["text"] == words
        assert client.get(f"/api/meetings/{meeting_id}/summary").json() == {"summary": None}
        client.cookies.clear()
        client.post("/api/workspace/bootstrap")
        assert client.post(path, json={}).status_code == 404


def test_server_rejects_invalid_model_result_without_persisting_it(tmp_path: Path):
    async def invalid(_document, *, model, language, prompt):
        return {"summary": "missing four fields"}, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=invalid)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        path = f"/api/meetings/{meeting_id}/summary"
        response = client.post(f"{path}/server", json={"source_version": 1})
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "invalid_summary"
        saved = client.get(path).json()["summary"]
        assert saved["state"] == "failed" and saved["document"] is None
        assert saved["error_code"] == "invalid_output"


@pytest.mark.parametrize("failure,status,code", [
    (TimeoutError, 504, "summary_timeout"),
    (RuntimeError, 502, "summary_provider_error"),
])
def test_server_maps_generation_failure_to_content_free_error(tmp_path: Path, failure, status, code):
    async def fail(_document, *, model, language, prompt):
        raise failure("transcript must not appear in response")

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=fail)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        path = f"/api/meetings/{meeting_id}/summary"
        response = client.post(f"{path}/server", json={"source_version": 1})
        assert response.status_code == status
        assert response.json()["detail"] == {"code": code}
        assert "transcript must not appear" not in response.text
        saved = client.get(path).json()["summary"]
        assert saved["state"] == "failed" and saved["document"] is None


@pytest.mark.parametrize("outcome", ["success", "provider_error", "invalid_result"])
def test_server_cancel_during_generation_keeps_cancelled_artifact(tmp_path: Path, outcome):
    entered, release = Event(), Event()

    async def generate(_document, *, model, language, prompt):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        if outcome == "provider_error":
            raise RuntimeError("private transcript text")
        if outcome == "invalid_result":
            return {"summary": "missing fields"}, USAGE
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test", raise_server_exceptions=False) as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        path = f"/api/meetings/{meeting_id}/summary"
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, f"{path}/server", json={"source_version": 1})
            assert entered.wait(5)
            attempt = client.get(path).json()["summary"]
            assert attempt["state"] == "generating"
            cancelled = client.put(f"{path}/{attempt['attempt_id']}", json={"state": "cancelled"})
            assert cancelled.status_code == 200
            release.set()
            response = pending.result(timeout=5)
        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "summary_cancelled"}
        saved = client.get(path).json()["summary"]
        assert saved["state"] == "cancelled" and saved["document"] is None


def test_server_cancel_between_start_and_generating_is_controlled(tmp_path: Path, monkeypatch):
    async def generate(_document, *, model, language, prompt):
        raise AssertionError("generator should not start after cancellation")

    original_update = MeetingSummaries.update

    async def cancel_before_generating(self, attempt_id, state, **kwargs):
        if state == "generating":
            await original_update(self, attempt_id, "cancelled")
        return await original_update(self, attempt_id, state, **kwargs)

    monkeypatch.setattr(MeetingSummaries, "update", cancel_before_generating)
    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test", raise_server_exceptions=False) as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        path = f"/api/meetings/{meeting_id}/summary"
        response = client.post(f"{path}/server", json={"source_version": 1})
        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "summary_cancelled"}
        assert client.get(path).json()["summary"]["state"] == "cancelled"


def test_server_retries_malformed_json_and_reports_summed_usage(tmp_path: Path):
    from moss_transcribe_diarize.app.phase2_llm import InvalidSummaryOutput
    calls = []

    async def flaky(_document, *, model, language, prompt):
        calls.append(model)
        if len(calls) == 1:
            raise InvalidSummaryOutput(USAGE)
        if len(calls) == 2:
            return {"summary": "missing four fields"}, USAGE
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=flaky)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id

        meeting_id = client.portal.call(seed)
        response = client.post(f"/api/meetings/{meeting_id}/summary/server", json={"source_version": 1})
        assert response.status_code == 200, response.text
        assert len(calls) == 3
        assert response.json()["document"] == RESULT
        assert response.json()["usage"] == {"model": USAGE["model"], "input_tokens": 300,
                                             "output_tokens": 75, "cost_usd": pytest.approx(3 * USAGE["cost_usd"])}


def test_gemini_generator_raises_invalid_output_with_usage_on_malformed_json(monkeypatch):
    from moss_transcribe_diarize.app.phase2_llm import InvalidSummaryOutput

    class Models:
        async def generate_content(self, **_kwargs):
            return SimpleNamespace(text='{"summary": "cut', usage_metadata=SimpleNamespace(
                prompt_token_count=100, candidates_token_count=25, thoughts_token_count=0))

    class Client:
        def __init__(self, **_kwargs):
            self.aio = SimpleNamespace(models=Models(), aclose=self.aclose)

        async def aclose(self):
            pass

    monkeypatch.setattr("google.genai.Client", Client)
    with pytest.raises(InvalidSummaryOutput) as caught:
        asyncio.run(GeminiSummaryGenerator("test-key")(TRANSCRIPT, model="gemini-3.5-flash-lite",
                                                        language="", prompt="P"))
    assert caught.value.usage["input_tokens"] == 100
