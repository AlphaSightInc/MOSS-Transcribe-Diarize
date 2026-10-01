from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from moss_transcribe_diarize.app.phase2 import REFINEMENT_RUNNING_MARKER, create_phase2_app
from moss_transcribe_diarize.app.phase2_summary import DEFAULT_SUMMARY_PROMPT, MeetingSummaries
from moss_transcribe_diarize.app.phase2_llm import GeminiSummaryGenerator


RESULT = {"summary": "A grounded result.", "topics": [{"title": "Useful title", "description": "A supported mechanism."}],
          "details": [], "speaker_background": [], "data_references": []}
USAGE = {"model": "gemini-3.5-flash-lite", "input_tokens": 100, "output_tokens": 25,
         "cost_usd": 0.0000925}
TRANSCRIPT = {"segments": [{"start": 0, "end": 4, "speaker": "Alex", "text": "Owner A only."}]}
PROVIDER = {"vendor": "gemini", "model": "gemini-3.5-flash-lite", "api_key": "user-key"}


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
    result = asyncio.run(GeminiSummaryGenerator()(
        TRANSCRIPT, model="gemini-3.5-flash-lite", language="French", prompt="Brief",
        api_key="local-key"))
    assert result == (RESULT, USAGE)
    assert seen["key_passed"] and seen["closed"]
    assert "Owner A only." in seen["contents"]
    assert "Write the final briefing in French." in seen["config"].system_instruction
    asyncio.run(GeminiSummaryGenerator()(
        TRANSCRIPT, model="gemini-3.5-flash-lite", language=" ", prompt="Brief", api_key="local-key"))
    # Auto (blank) language: answer in the transcript's language, not the English prompt's.
    assert seen["config"].system_instruction == (
        "Brief\nWrite every string value in the transcript's dominant language; do not translate it.")


def test_server_summary_generates_from_exact_final_version_and_saves(tmp_path: Path):
    calls = []

    async def generate(document, *, model, language, prompt, api_key):
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
        assert client.post(path, json={"source_version": 2, "provider": PROVIDER}).status_code == 409
        response = client.post(path, json={"source_version": 1, "provider": PROVIDER})
        assert response.status_code == 200, response.text
        assert response.json()["document"] == RESULT
        assert response.json()["usage"] == USAGE
        assert calls[0][0] == TRANSCRIPT
        assert calls[0][1:3] == ("gemini-3.5-flash-lite", "")
        assert calls[0][3] == DEFAULT_SUMMARY_PROMPT
        assert client.get(f"/api/meetings/{meeting_id}/summary").json()["summary"]["document"] == RESULT
        assert "usage" not in client.get(f"/api/meetings/{meeting_id}/summary").json()["summary"]
        assert client.get(f"/api/meetings/{meeting_id}").json()["title"] == "Useful title"


def test_server_summary_options_owner_and_one_inflight(tmp_path: Path):
    entered, release = Event(), Event()
    calls = []

    async def generate(document, *, model, language, prompt, api_key):
        calls.append((model, language, prompt, api_key))
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
        assert client.post(path, json={"source_version": 1, "api_key": "wrong",
                                       "provider": PROVIDER}).status_code == 400
        assert client.post(path, json={"source_version": 1, "provider": {
            **PROVIDER, "vendor": "openai_compatible"}}).status_code == 400
        assert client.post(path, json={"source_version": 1, "provider": {
            **PROVIDER, "extra": 1}}).status_code == 400
        for missing in ({}, {"provider": {**PROVIDER, "api_key": ""}},
                        {"provider": {"vendor": "gemini", "model": "gemini-3.8-flash"}}):
            refused = client.post(path, json={"source_version": 1, **missing})
            assert refused.status_code == 400
            assert refused.json()["detail"] == {"code": "api_key_required"}
        assert calls == []
        assert client.post(path, json={"source_version": 1, "language": "French", "prompt": "Brief",
                                       "provider": {**PROVIDER, "model": "gemini-3.8-flash"}}).status_code == 200
        assert calls[0] == ("gemini-3.8-flash", "French", "Brief", "user-key")
        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(client.post, path, json={"source_version": 1, "provider": PROVIDER})
            assert entered.wait(5)
            assert client.post(path, json={"source_version": 1, "provider": PROVIDER}).status_code == 429
            release.set()
            assert first.result(timeout=5).status_code == 200
        client.cookies.clear()
        client.post("/api/workspace/bootstrap")
        assert client.post(path, json={"source_version": 1, "provider": PROVIDER}).status_code == 404


def test_live_summary_is_ephemeral_and_requires_forty_words(tmp_path: Path):
    seen = []

    async def generate(document, *, model, language, prompt, api_key):
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
        assert client.post(path, json={"provider": PROVIDER}).status_code == 409
        row.text = words
        response = client.post(path, json={"provider": PROVIDER})
        assert response.status_code == 200, response.text
        assert response.json()["summary"] == RESULT
        assert response.json()["usage"] == USAGE
        assert response.json()["source"] == {"committed_samples": 64000, "text_revision_version": 3}
        assert seen[0]["segments"][0]["text"] == words
        # Chinese has no spaces: 40 ideographs are 40 words, not one.
        row.text = "我们" * 19 + "好"
        assert client.post(path, json={"provider": PROVIDER}).status_code == 409
        row.text = "我们" * 20
        assert client.post(path, json={"provider": PROVIDER}).status_code == 200
        assert client.get(f"/api/meetings/{meeting_id}/summary").json() == {"summary": None}
        client.cookies.clear()
        client.post("/api/workspace/bootstrap")
        assert client.post(path, json={"provider": PROVIDER}).status_code == 404


def test_server_rejects_invalid_model_result_without_persisting_it(tmp_path: Path):
    async def invalid(_document, *, model, language, prompt, api_key):
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
        response = client.post(f"{path}/server", json={"source_version": 1, "provider": PROVIDER})
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
    async def fail(_document, *, model, language, prompt, api_key):
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
        response = client.post(f"{path}/server", json={"source_version": 1, "provider": PROVIDER})
        assert response.status_code == status
        assert response.json()["detail"] == {"code": code}
        assert "transcript must not appear" not in response.text
        saved = client.get(path).json()["summary"]
        assert saved["state"] == "failed" and saved["document"] is None


@pytest.mark.parametrize("outcome", ["success", "provider_error", "invalid_result"])
def test_server_cancel_during_generation_keeps_cancelled_artifact(tmp_path: Path, outcome):
    entered, release = Event(), Event()

    async def generate(_document, *, model, language, prompt, api_key):
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
            pending = pool.submit(client.post, f"{path}/server", json={"source_version": 1, "provider": PROVIDER})
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


@pytest.mark.parametrize("start_next_while_held", [False, True])
def test_refinement_supersedes_held_summary_and_next_version_succeeds(
    tmp_path: Path, start_next_while_held: bool,
):
    entered, release = Event(), Event()
    calls = []

    async def generate(document, *, model, language, prompt, api_key):
        calls.append(document)
        if len(calls) == 1:
            entered.set()
            await asyncio.to_thread(release.wait, 5)
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test", raise_server_exceptions=False) as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("live")
            assert await handle.finish_with_transcript(
                TRANSCRIPT, "completed", notice=REFINEMENT_RUNNING_MARKER) == 1
            return handle

        handle = client.portal.call(seed)
        path = f"/api/meetings/{handle.meeting_id}/summary"
        improved = {"segments": [{"start": 0, "end": 4, "speaker": "Alex",
                                  "text": "Improved owner speech."}]}
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, f"{path}/server", json={"source_version": 1, "provider": PROVIDER})
            try:
                assert entered.wait(5)
                assert client.get(path).json()["summary"]["state"] == "generating"
                assert client.portal.call(handle.settle_refinement, improved) == 2
                if start_next_while_held:
                    next_response = client.post(f"{path}/server", json={"source_version": 2, "provider": PROVIDER})
                    assert next_response.status_code == 200, next_response.text
            finally:
                release.set()
            response = pending.result(timeout=5)
        assert response.status_code == 409
        assert response.json() == {"code": "summary_source_changed"}
        if not start_next_while_held:
            stale = client.get(path).json()["summary"]
            assert stale["state"] == "failed"
            assert stale["error_code"] == "source_changed"
            assert stale["source_version"] == 1
            assert stale["document"] is None
            next_response = client.post(f"{path}/server", json={"source_version": 2, "provider": PROVIDER})
        assert next_response.status_code == 200, next_response.text
        assert next_response.json()["source_version"] == 2
        assert next_response.json()["artifact_version"] == 2
        assert calls == [TRANSCRIPT, improved]


def test_speaker_renames_during_a_summary_after_clean_up_do_not_fail_it(tmp_path: Path):
    """D1 (issue #15): a rename bumps the version but is no new clean-up result."""
    entered, release = Event(), Event()

    async def generate(document, *, model, language, prompt, api_key):
        entered.set()
        await asyncio.to_thread(release.wait, 5)
        return RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test", raise_server_exceptions=False) as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")
        spoken = {"segments": [{"start": 0, "end": 4, "speaker": "Speaker 1",
                                "speaker_entity_id": "speaker-0001", "text": "Owner A only."}]}

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("live")
            await handle.finish_with_transcript(spoken, "completed", notice=REFINEMENT_RUNNING_MARKER)
            assert await handle.settle_refinement(spoken) == 2
            return handle

        handle = client.portal.call(seed)
        path = f"/api/meetings/{handle.meeting_id}"
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(client.post, f"{path}/summary/server",
                                  json={"source_version": 2, "provider": PROVIDER})
            try:
                assert entered.wait(5)
                for label in ("Alex", "Alexander", "Al"):
                    named = client.put(f"{path}/speakers/speaker-0001/name",
                                       json={"label": label, "save_voiceprint": False})
                    assert named.status_code == 200, named.text
            finally:
                release.set()
            response = pending.result(timeout=5)
        assert response.status_code == 200, response.text
        saved = client.get(f"{path}/summary").json()["summary"]
        assert (saved["state"], saved["source_version"], saved["error_code"]) == ("current", 2, None)
        assert client.get(path).json()["transcript_version"] == 5


def test_server_cancel_between_start_and_generating_is_controlled(tmp_path: Path, monkeypatch):
    async def generate(_document, *, model, language, prompt, api_key):
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
        response = client.post(f"{path}/server", json={"source_version": 1, "provider": PROVIDER})
        assert response.status_code == 409
        assert response.json()["detail"] == {"code": "summary_cancelled"}
        assert client.get(path).json()["summary"]["state"] == "cancelled"


def test_server_retries_malformed_json_and_reports_summed_usage(tmp_path: Path):
    from moss_transcribe_diarize.app.phase2_llm import InvalidSummaryOutput
    calls = []

    async def flaky(_document, *, model, language, prompt, api_key):
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
        response = client.post(f"/api/meetings/{meeting_id}/summary/server", json={"source_version": 1, "provider": PROVIDER})
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
        asyncio.run(GeminiSummaryGenerator()(TRANSCRIPT, model="gemini-3.5-flash-lite",
                                              language="", prompt="P", api_key="test-key"))
    assert caught.value.usage["input_tokens"] == 100


# A summary names people as its generator was given them; the artifact keeps those names by speaker id
# so the browser can show the names the speakers carry now (round 5: a rename never regenerates).
NAMED_TRANSCRIPT = {"segments": [
    {"id": "a", "start": 0, "end": 2, "speaker_entity_id": "speaker-0001", "speaker": "Speaker 1",
     "source_lane": "system", "text": "Hello from the shared tab."},
    {"id": "b", "start": 2, "end": 4, "speaker_entity_id": "local-1", "speaker": "You",
     "source_lane": "microphone", "text": "Hello from the microphone."},
    {"id": "c", "start": 4, "end": 6, "speaker": "S03", "text": "A row saved before speaker ids."},
]}
NAMED_RESULT = {"summary": "Speaker 1 greeted You.", "topics": [], "details": [],
                "speaker_background": ["Speaker 1: host"], "data_references": []}
GIVEN_NAMES = {"speaker-0001": "Speaker 1", "local-1": "You", "S03": "S03"}


def _named_meeting(app, client):
    client.post("/api/workspace/bootstrap")
    credential = client.cookies.get("__Host-moss_session")

    async def seed():
        store = app.state.phase2_store
        account = await store.account_for_session(credential)
        handle = await store.workspace(account).create_meeting("live")
        await handle.finish_with_transcript(NAMED_TRANSCRIPT, "completed")
        return handle.meeting_id

    return client.portal.call(seed)


def test_final_summary_keeps_the_names_its_generator_was_given_through_renames(tmp_path: Path):
    calls = []

    async def generate(document, *, model, language, prompt, api_key):
        calls.append([row["speaker"] for row in document["segments"]])
        return NAMED_RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        meeting_id = _named_meeting(app, client)
        path = f"/api/meetings/{meeting_id}/summary"
        created = client.post(f"{path}/server", json={"source_version": 1, "provider": PROVIDER})
        assert created.status_code == 200, created.text
        assert calls == [["Speaker 1", "You", "S03"]]
        assert created.json()["speaker_names"] == GIVEN_NAMES
        assert client.get(path).json()["summary"]["speaker_names"] == GIVEN_NAMES
        # Speaker 1 -> Alice -> Bob: the stored summary and its names stay as generated, and no
        # rename asks the model again; only the transcript carries the new name.
        for label in ("Alice", "Bob"):
            named = client.put(f"/api/meetings/{meeting_id}/speakers/speaker-0001/name",
                               json={"label": label, "save_voiceprint": False})
            assert named.status_code == 200, named.text
            saved = client.get(path).json()["summary"]
            assert saved["state"] == "current" and saved["document"] == NAMED_RESULT
            assert saved["speaker_names"] == GIVEN_NAMES
        assert len(calls) == 1
        rows = client.get(f"/api/meetings/{meeting_id}").json()["transcript"]["segments"]
        assert [row["speaker"] for row in rows] == ["Bob", "You", "S03"]
        # Refresh is the user's choice; a new summary records the names it was given then.
        version = client.get(f"/api/meetings/{meeting_id}").json()["transcript_version"]
        again = client.post(f"{path}/server", json={"source_version": version, "provider": PROVIDER})
        assert again.status_code == 200, again.text
        assert again.json()["speaker_names"] == {**GIVEN_NAMES, "speaker-0001": "Bob"}


def test_browser_generated_summary_records_names_and_an_older_artifact_reads_without_them(tmp_path: Path):
    import json

    app = create_phase2_app(database_path=tmp_path / "db")
    with TestClient(app, base_url="https://moss.test") as client:
        meeting_id = _named_meeting(app, client)
        path = f"/api/meetings/{meeting_id}/summary"
        attempt = client.post(path, json={"source_version": 1}).json()
        assert attempt["speaker_names"] == GIVEN_NAMES
        client.put(f"{path}/{attempt['attempt_id']}", json={"state": "generating"})
        done = client.put(f"{path}/{attempt['attempt_id']}", json={"state": "current", "document": NAMED_RESULT})
        assert done.status_code == 200 and done.json()["speaker_names"] == GIVEN_NAMES

        async def forget_names():
            # What every summary saved before this change looks like in the database.
            store = app.state.phase2_store
            async with store._mutation():
                await store._connection.execute(
                    "UPDATE llm_artifacts SET provenance_json=? WHERE meeting_id=?",
                    (json.dumps({key: done.json()[key] for key in
                                 ("attempt_id", "source_version", "artifact_version", "error_code")}), meeting_id))

        client.portal.call(forget_names)
        older = client.get(path).json()["summary"]
        assert older["state"] == "current" and older["document"] == NAMED_RESULT
        assert "speaker_names" not in older


def test_live_summary_reports_the_names_its_generator_was_given(tmp_path: Path):
    async def generate(document, *, model, language, prompt, api_key):
        return NAMED_RESULT, USAGE

    app = create_phase2_app(database_path=tmp_path / "db", summary_generator=generate)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")

        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            return (await store.workspace(account).create_meeting("live")).meeting_id

        meeting_id = client.portal.call(seed)
        words = " ".join(f"word{i}" for i in range(40))
        rows = [SimpleNamespace(start_sample=0, end_sample=64000, canonical_speaker=speaker,
                                source_lane=lane, text=words)
                for speaker, lane in (("speaker-0001", "system"), ("speaker-0002", "system"),
                                      ("local-1", "microphone"), (None, "system"))]
        session = SimpleNamespace(
            status="active", committed_samples=64000, text_revision_version=3,
            identity_snapshot=SimpleNamespace(canonical_speakers=("speaker-0001", "speaker-0002", "local-1")),
            effective_transcript=rows)
        snapshot = SimpleNamespace(session=session, descriptor=SimpleNamespace(sample_rate=16000))
        # A voiceprint or the user named the second shared voice before this summary.
        binding = SimpleNamespace(public_snapshot=snapshot, speaker_labels={"speaker-0002": "王芳"})
        app.state.phase2_live = SimpleNamespace(open=lambda *_args, **_kwargs: binding)
        response = client.post(f"/api/meetings/{meeting_id}/summary/live", json={"provider": PROVIDER})
        assert response.status_code == 200, response.text
        # Speech nobody is attributed to went to the generator under its token.
        assert response.json()["speaker_names"] == {
            "speaker-0001": "Speaker 1", "speaker-0002": "王芳", "local-1": "You", "S00": "S00"}
