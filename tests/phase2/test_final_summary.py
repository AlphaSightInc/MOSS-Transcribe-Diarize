from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import AccountRevoked, Phase2Store, create_phase2_app
from moss_transcribe_diarize.app.phase2_summary import MeetingSummaries, SummaryConflict, recover_summaries, validate_summary

RESULT = {"summary": "A grounded result.", "topics": [{"title": "Useful title", "description": "A supported mechanism."}],
          "details": [{"title": "Evidence", "description": "Supported", "timestamp": "00:00:03"}],
          "speaker_background": [], "data_references": []}
TRANSCRIPT = {"segments": [{"start": 0, "end": 4, "speaker": "Alex", "text": "Owner A only."}]}


def test_shipped_default_prompt_matches_accepted_v15():
    repo = Path(__file__).resolve().parents[2]
    assert (repo / "frontend/src/lib/final-summary-prompt.txt").read_bytes() == (repo / "prototypes/client-configured-llm/final-summary-prompt.txt").read_bytes()


@pytest.mark.parametrize("mutate", [
    lambda v: v.update(endpoint="private"), lambda v: v.update(summary="  "),
    lambda v: v.update(topics={}), lambda v: v["topics"][0].update(extra="x"),
    lambda v: v.update(speaker_background=[{}]), lambda v: v.update(data_references=[{"item": "x"}]),
    lambda v: v["details"][0].update(timestamp="00:00:05"),
    lambda v: v["details"][0].update(timestamp="00:60:00"),
    lambda v: v["details"][0].update(timestamp="0:00:00"),
])
def test_exact_summary_validator(mutate):
    assert validate_summary(copy.deepcopy(RESULT), 4) == RESULT
    invalid = copy.deepcopy(RESULT)
    mutate(invalid)
    with pytest.raises(ValueError):
        validate_summary(invalid, 4)


def test_attempt_concurrency_cancel_version_restart_and_private_persistence(tmp_path: Path):
    async def run():
        store = await Phase2Store.open(tmp_path / "db")
        try:
            account, _ = await store.bootstrap_browser(None)
            other, _ = await store.bootstrap_browser(None)
            workspace = store.workspace(account)
            handle = await workspace.create_meeting("file")
            summary = MeetingSummaries(handle)
            with pytest.raises(SummaryConflict): await summary.start(0)
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            assert await store.workspace(other).open_meeting(handle.meeting_id) is None
            results = await asyncio.gather(*(summary.start(1) for _ in range(32)), return_exceptions=True)
            assert sum(isinstance(v, dict) for v in results) == 1
            assert sum(isinstance(v, SummaryConflict) for v in results) == 31
            first = next(v for v in results if isinstance(v, dict))
            await summary.update(first["attempt_id"], "cancelled")
            second = await summary.start(1)
            assert second["artifact_version"] == 2
            with pytest.raises(SummaryConflict): await summary.update(first["attempt_id"], "current", document=RESULT)
            with pytest.raises(SummaryConflict): await summary.update(second["attempt_id"], "current", document=RESULT)
            await summary.update(second["attempt_id"], "generating")
            await summary.update(second["attempt_id"], "retry_wait")
            await summary.update(second["attempt_id"], "generating")
            await summary.update(second["attempt_id"], "current", document=RESULT)
            assert (await handle.snapshot()).title == "Useful title"
            assert (await handle.snapshot()).transcript == TRANSCRIPT
            await handle.rename("Owner's title")
            third = await summary.start(1)
            await summary.update(third["attempt_id"], "generating")
            await summary.update(third["attempt_id"], "current", document=RESULT)
            assert (await handle.snapshot()).title == "Owner's title"
            fourth = await summary.start(1)
            await recover_summaries(store)
            assert (await summary.read())["error_code"] == "server_restarted"
            with pytest.raises(SummaryConflict): await summary.update(fourth["attempt_id"], "generating")
            with pytest.raises(SummaryConflict): await summary.start(2)
            fifth = await summary.start(1)
            await store.revoke_account(account.account_id)
            with pytest.raises(AccountRevoked): await summary.update(fifth["attempt_id"], "generating")
            cursor = await store._connection.execute("SELECT provenance_json FROM llm_artifacts")
            metadata = json.loads((await cursor.fetchone())[0])
            assert set(metadata) == {"attempt_id", "source_version", "artifact_version", "error_code"}
            await cursor.close()
        finally:
            await store.close()
    asyncio.run(run())


def test_summary_http_requires_owner_and_never_accepts_provider_settings(tmp_path: Path):
    app = create_phase2_app(database_path=tmp_path / "db")
    with TestClient(app, base_url="https://moss.test") as client:
        assert client.post("/api/workspace/bootstrap").status_code == 200
        credential = client.cookies.get("__Host-moss_session")
        async def seed():
            store = app.state.phase2_store
            account = await store.account_for_session(credential)
            handle = await store.workspace(account).create_meeting("file")
            await handle.commit_transcript(TRANSCRIPT, terminal=True)
            return handle.meeting_id
        meeting = client.portal.call(seed)
        path = f"/api/meetings/{meeting}/summary"
        assert client.get(path).json() == {"summary": None}
        for key in ("endpoint", "model", "api_key", "prompt", "provenance"):
            assert client.post(path, json={"source_version": 1, key: "SECRET"}).status_code == 400
        first = client.post(path, json={"source_version": 1})
        assert first.status_code == 200, first.text
        attempt_path = f"{path}/{first.json()['attempt_id']}"
        assert client.put(attempt_path, json={"state": "generating", "model": "SECRET"}).status_code == 400
        assert client.put(attempt_path, json={"state": "generating"}).status_code == 200
        assert client.put(attempt_path, json={"state": "failed", "error_code": "SECRET"}).status_code == 400
        invalid = {**RESULT, "api_key": "SECRET"}
        assert client.put(attempt_path, json={"state": "current", "document": invalid}).status_code == 400
        assert client.put(attempt_path, json={"state": "current", "document": RESULT}).status_code == 200
        assert client.get(path).json()["summary"]["document"] == RESULT
        client.cookies.clear()
        assert client.get(path).status_code == 401
        assert client.post("/api/workspace/bootstrap").status_code == 200
        assert client.get(path).status_code == 404
        assert client.post(path, json={"source_version": 1}).status_code == 404
        assert client.put(attempt_path, json={"state": "cancelled"}).status_code == 404
