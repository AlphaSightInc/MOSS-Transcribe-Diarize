"""Synthetic SQLite probe; no servers, audio, provider or key access."""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from fastapi.testclient import TestClient
from moss_transcribe_diarize.app.phase2 import AccountRevoked, create_phase2_app

async def probe(app, credential):
    store = app.state.phase2_store
    account = await store.account_for_session(credential)
    handle = await store.workspace(account).create_meeting("file")
    original = {"segments": [{"id": "seg_0001", "speaker_entity_id": "person-a",
                             "speaker": "Alex", "start": 0., "end": 1., "text": "original"}]}
    await handle.commit_transcript(original, terminal=True)
    edited = json.loads(json.dumps(original))
    edited["segments"][0].update(text="corrected", original_text="original", edited=True)
    if "--product" in sys.argv:
        result = await handle.edit_passage_text("seg_0001", "corrected")
        print(json.dumps({"product_edit_response": result.to_dict()}, indent=2))
    else:
        async with store._mutation():
            await store._connection.execute(
                "UPDATE meeting_transcripts SET document_json=?, version=version+1 WHERE meeting_id=?",
                (json.dumps(edited), handle.meeting_id))
    blocked = []
    for name, operation in [
        ("rolling", handle.commit_transcript(original)),
        ("terminal", handle.finish_with_transcript(original, "completed")),
        ("refinement", handle.settle_refinement(original)),
    ]:
        try:
            await operation
        except AccountRevoked:
            blocked.append(name)
    state = (await handle.snapshot()).to_dict()
    print(json.dumps({"blocked_publishers": blocked, "state": state}, ensure_ascii=False, indent=2))
    assert blocked == ["rolling", "terminal", "refinement"]
    assert state["transcript"] == edited and state["transcript_version"] == 2
    return handle.meeting_id

with tempfile.TemporaryDirectory(prefix="p75-es-") as directory:
    database = Path(directory) / "state.sqlite"
    app = create_phase2_app(database_path=database)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        credential = client.cookies.get("__Host-moss_session")
        meeting_id = client.portal.call(probe, app, credential)
    with TestClient(create_phase2_app(database_path=database), base_url="https://moss.test") as client:
        client.cookies.set("__Host-moss_session", credential)
        state = client.get(f"/api/meetings/{meeting_id}").json()
        print(json.dumps({"restart_state": state}, ensure_ascii=False, indent=2))
        assert state["transcript"]["segments"][0]["text"] == "corrected"
    print("PASS: 3/3 late publishers blocked; 1/1 restart retained edit.")
