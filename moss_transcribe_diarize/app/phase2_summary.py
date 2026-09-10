"""Owner-bound final results, never provider configuration or inference."""
from __future__ import annotations

import json
import math
import re
import secrets
from typing import Any
from starlette.requests import Request

from .phase2 import AccountRevoked, MeetingHandle, _now_ms

ACTIVE = {"queued", "generating", "retry_wait"}
ERRORS = {"delivery_failed", "invalid_output", "request_rejected", "browser_worker_lost", "server_restarted"}


class SummaryConflict(ValueError):
    pass


def validate_summary(value: Any, duration: float) -> dict[str, object]:
    """The same exact V15 shape enforced before storage and in the browser."""
    fields = {"summary", "topics", "details", "speaker_background", "data_references"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Summary must contain exactly the five final-summary fields.")
    if not isinstance(value["summary"], str) or not value["summary"].strip():
        raise ValueError("Summary must not be empty.")
    for name, keys in (("topics", {"title", "description"}),
                       ("details", {"title", "description", "timestamp"}),
                       ("data_references", {"item", "value", "context"})):
        if not isinstance(value[name], list):
            raise ValueError(f"{name} must be an array.")
        for item in value[name]:
            if not isinstance(item, dict) or set(item) != keys or not all(isinstance(v, str) for v in item.values()):
                raise ValueError(f"Invalid {name} entry.")
            if name == "details":
                stamp = item["timestamp"]
                if re.fullmatch(r"\d{2}:[0-5]\d:[0-5]\d", stamp, flags=re.ASCII) is None:
                    raise ValueError("Invalid detail timestamp.")
                h, m, s = map(int, stamp.split(":"))
                if h * 3600 + m * 60 + s > duration:
                    raise ValueError("Detail timestamp exceeds transcript duration.")
    if not isinstance(value["speaker_background"], list) or not all(isinstance(v, str) for v in value["speaker_background"]):
        raise ValueError("speaker_background must be an array of strings.")
    return value


class MeetingSummaries:
    def __init__(self, handle: MeetingHandle):
        self.handle = handle
        self.store = handle._store

    async def _source(self):
        # Called inside the store's serialized read/mutation, never nested locks.
        account, generation = self.handle.owner_key
        cursor = await self.store._connection.execute(
            """SELECT m.status,t.version,t.document_json FROM meetings m
            JOIN accounts a ON a.account_id=m.account_id AND a.enabled=1 AND a.authority_generation=?
            LEFT JOIN meeting_transcripts t ON t.account_id=m.account_id AND t.meeting_id=m.meeting_id
            WHERE m.account_id=? AND m.meeting_id=?""",
            (generation, account, self.handle.meeting_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            raise AccountRevoked("Meeting authority is unavailable.")
        return row

    async def _read(self):
        cursor = await self.store._connection.execute(
            "SELECT state,document_json,provenance_json FROM llm_artifacts WHERE account_id=? AND meeting_id=? AND artifact_id='final_summary'",
            (self.handle.owner_key[0], self.handle.meeting_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return {"state": row["state"], "document": json.loads(row["document_json"]) if row["document_json"] else None,
                **json.loads(row["provenance_json"])}

    async def read(self):
        async with self.store._external_read():
            await self._source()
            return await self._read()

    async def _write(self, value):
        now = _now_ms()
        metadata = {k: value[k] for k in ("attempt_id", "source_version", "artifact_version", "error_code")}
        await self.store._connection.execute(
            """INSERT INTO llm_artifacts VALUES (?,?,'final_summary','final_summary',?,?,?,?,?)
            ON CONFLICT(account_id,meeting_id,artifact_id) DO UPDATE SET
            state=excluded.state,document_json=excluded.document_json,
            provenance_json=excluded.provenance_json,updated_at_ms=excluded.updated_at_ms""",
            (self.handle.owner_key[0], self.handle.meeting_id, value["state"],
             json.dumps(value["document"], ensure_ascii=False) if value["document"] is not None else None,
             json.dumps(metadata), now, now),
        )

    async def start(self, source_version: int):
        async with self.store._mutation():
            source = await self._source()
            if source["status"] != "completed" or source["version"] != source_version or not source["document_json"]:
                raise SummaryConflict("A finalized transcript at this version is required.")
            document = json.loads(source["document_json"])
            if not any(str(s.get("text", "")).strip() for s in document.get("segments", [])):
                raise SummaryConflict("There is no finalized speech to summarize.")
            previous = await self._read()
            if previous is not None and previous["state"] in ACTIVE:
                raise SummaryConflict("A summary attempt is already active. Cancel it before retrying.")
            value = {"state": "queued", "document": None, "attempt_id": secrets.token_urlsafe(18),
                     "source_version": source_version, "artifact_version": 1 if previous is None else previous["artifact_version"] + 1,
                     "error_code": None}
            await self._write(value)
            return value

    async def update(self, attempt_id: str, state: str, *, document=None, error_code=None):
        async with self.store._mutation():
            source = await self._source()
            value = await self._read()
            if value is None or value["attempt_id"] != attempt_id or value["state"] not in ACTIVE:
                raise SummaryConflict("Summary attempt is no longer active.")
            if source["status"] != "completed" or source["version"] != value["source_version"]:
                raise SummaryConflict("Final transcript version changed.")
            allowed = {"queued": {"generating", "failed", "cancelled"},
                       "generating": {"retry_wait", "current", "failed", "cancelled"},
                       "retry_wait": {"generating", "failed", "cancelled"}}
            if state not in allowed[value["state"]]:
                raise SummaryConflict("Invalid summary state transition.")
            if state == "current":
                segments = json.loads(source["document_json"]).get("segments", [])
                ends = [float(s.get("end", 0)) for s in segments]
                duration = max((n for n in ends if math.isfinite(n)), default=0)
                value["document"] = validate_summary(document, duration)
            elif document is not None:
                raise ValueError("Only a current result may include a document.")
            if state == "failed" and (not isinstance(error_code, str) or error_code not in ERRORS):
                raise ValueError("A recognized failure code is required.")
            if state != "failed" and error_code is not None:
                raise ValueError("Failure codes belong only to failed attempts.")
            value.update(state=state, error_code=error_code)
            await self._write(value)
            if state == "current" and value["document"]["topics"]:
                title = value["document"]["topics"][0]["title"].strip()
                if title:
                    await self.store._connection.execute(
                        "UPDATE meetings SET title=?,updated_at_ms=? WHERE account_id=? AND meeting_id=? AND title_source='automatic'",
                        (title, _now_ms(), self.handle.owner_key[0], self.handle.meeting_id),
                    )
            return value


async def recover_summaries(store):
    """No browser inference survives a server restart as an authoritative worker."""
    async with store._mutation():
        cursor = await store._connection.execute(
            "SELECT account_id,meeting_id,artifact_id,provenance_json FROM llm_artifacts WHERE state IN ('queued','generating','retry_wait') AND kind='final_summary'"
        )
        rows = await cursor.fetchall()
        await cursor.close()
        for row in rows:
            metadata = json.loads(row["provenance_json"])
            metadata["error_code"] = "server_restarted"
            await store._connection.execute(
                "UPDATE llm_artifacts SET state='failed',provenance_json=?,updated_at_ms=? WHERE account_id=? AND meeting_id=? AND artifact_id=?",
                (json.dumps(metadata), _now_ms(), row["account_id"], row["meeting_id"], row["artifact_id"]),
            )


def attach_summary_routes(app, require_account):
    from fastapi import HTTPException

    async def summary_handle(request, meeting_id):
        account = await require_account(request)
        handle = await request.app.state.phase2_store.workspace(account).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(404, "Meeting not found.")
        return MeetingSummaries(handle)

    @app.get("/api/meetings/{meeting_id}/summary")
    async def read_summary(meeting_id: str, request: Request):
        return {"summary": await (await summary_handle(request, meeting_id)).read()}

    @app.post("/api/meetings/{meeting_id}/summary")
    async def start_summary(meeting_id: str, request: Request):
        handle = await summary_handle(request, meeting_id)
        try:
            body = await request.json()
            if not isinstance(body, dict) or set(body) != {"source_version"} or type(body["source_version"]) is not int:
                raise ValueError("Only source_version is accepted.")
            return await handle.start(body["source_version"])
        except SummaryConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.put("/api/meetings/{meeting_id}/summary/{attempt_id}")
    async def update_summary(meeting_id: str, attempt_id: str, request: Request):
        handle = await summary_handle(request, meeting_id)
        try:
            body = await request.json()
            if not isinstance(body, dict) or not {"state"} <= set(body) <= {"state", "document", "error_code"} or not isinstance(body["state"], str):
                raise ValueError("Only summary state, result and failure code are accepted.")
            return await handle.update(attempt_id, **body)
        except SummaryConflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
