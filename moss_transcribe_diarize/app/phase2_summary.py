"""Owner-bound final artifacts and transient server Gemini summaries."""
from __future__ import annotations

import json
import math
import re
import secrets
from pathlib import Path
from typing import Any
from starlette.requests import Request
from starlette.responses import JSONResponse

from .phase2 import AccountRevoked, MeetingHandle, _now_ms, _refined_version, readable_transcript
from .gemini_api_key import gemini_api_key

ACTIVE = {"queued", "generating", "retry_wait"}
ERRORS = {"delivery_failed", "invalid_output", "request_rejected", "browser_worker_lost", "server_restarted", "source_changed"}
# Standard paid text rates in USD per 1M tokens: https://ai.google.dev/gemini-api/docs/pricing
# The 3.8 Flash introductory rates apply through 2026-12-31.
SUMMARY_PRICES = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.8-flash": (0.75, 3.75),
}
DEFAULT_SUMMARY_MODEL = "gemini-3.8-flash"
DEFAULT_SUMMARY_PROMPT = Path(__file__).with_name("final_summary_prompt.txt").read_text(encoding="utf-8")
SUMMARY_ATTEMPTS = 3


def _add_usage(total, usage):
    if usage is None:
        return total
    if total is None:
        return dict(usage)
    cost = (None if total["cost_usd"] is None or usage["cost_usd"] is None
            else total["cost_usd"] + usage["cost_usd"])
    return {"model": usage["model"], "cost_usd": cost,
            **{key: total[key] + usage[key] for key in ("input_tokens", "output_tokens")}}


# Chinese is written without spaces, so each ideograph counts as a word; split() made a 5-minute,
# 10-row Chinese transcript 13 "words", below the live 40-word minimum.
_WORD = re.compile(r"[\u3400-\u9fff]|[^\s\u3400-\u9fff]+")


def transcript_words(document) -> int:
    return sum(len(_WORD.findall(str(row["text"]))) for row in document["segments"])


def speaker_names(document) -> dict[str, str]:
    """The name each speaker id carries in the transcript handed to a summary generator.

    A summary is prose that mentions people by these names. A later rename changes the transcript
    but never regenerates the summary (issue #15), so the names are kept with it, by speaker id,
    and the browser shows each mention under the name that id carries now. A row without a
    speaker id (saved before ids existed, or live speech nobody is attributed to) is identified
    by its speaker token, as naming identifies it.
    """
    names = {}
    for row in document["segments"]:
        name = row.get("speaker")
        speaker = row.get("speaker_entity_id", name)
        if isinstance(name, str) and name.strip() and isinstance(speaker, str):
            names[speaker] = name
    return names


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
            """SELECT m.status,t.version,t.document_json,o.notice FROM meetings m
            JOIN accounts a ON a.account_id=m.account_id AND a.enabled=1 AND a.authority_generation=?
            LEFT JOIN meeting_transcripts t ON t.account_id=m.account_id AND t.meeting_id=m.meeting_id
            LEFT JOIN meeting_outcomes o ON o.account_id=m.account_id AND o.meeting_id=m.meeting_id
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
        if "speaker_names" in value:  # absent on a summary saved before round 5; it reads as stored
            metadata["speaker_names"] = value["speaker_names"]
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
        value, _ = await self.start_server(source_version)
        return value

    async def start_server(self, source_version: int):
        async with self.store._mutation():
            source = await self._source()
            if source["status"] != "completed" or source["version"] != source_version or not source["document_json"]:
                raise SummaryConflict("A finalized transcript at this version is required.")
            document = json.loads(source["document_json"])
            if not any(str(s.get("text", "")).strip() for s in document.get("segments", [])):
                raise SummaryConflict("There is no finalized speech to summarize.")
            previous = await self._read()
            if (previous is not None and previous["state"] in ACTIVE
                    and previous["source_version"] >= source_version):
                raise SummaryConflict("A summary attempt is already active. Cancel it before retrying.")
            value = {"state": "queued", "document": None, "attempt_id": secrets.token_urlsafe(18),
                     "source_version": source_version, "artifact_version": 1 if previous is None else previous["artifact_version"] + 1,
                     "error_code": None, "speaker_names": speaker_names(document)}
            await self._write(value)
            return value, readable_transcript({k: v for k, v in document.items()
                                                if k not in {"interruptions", "interruption_lines"}})

    async def update(self, attempt_id: str, state: str, *, document=None, error_code=None):
        source_changed = False
        async with self.store._mutation():
            source = await self._source()
            value = await self._read()
            if value is None or value["attempt_id"] != attempt_id or value["state"] not in ACTIVE:
                raise SummaryConflict("Summary attempt is no longer active.")
            # D1 (issue #15): only a clean-up result outdates an attempt. A rename or passage
            # correction meanwhile bumps the version but keeps the words it summarized.
            refined = _refined_version(source["notice"])
            if source["status"] != "completed" or (refined is not None and refined > value["source_version"]):
                value.update(state="failed", error_code="source_changed")
                await self._write(value)
                source_changed = True
            else:
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
        if source_changed:
            raise SummaryConflict("Final transcript version changed.")


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


def attach_summary_routes(app, require_account, generator=None):
    from fastapi import HTTPException
    from .phase2_live import LiveMeetingNotFound, _transcript_document

    app.state.summary_generator = generator
    app.state.summary_inflight = set()

    async def summary_handle(request, meeting_id):
        account = await require_account(request)
        handle = await request.app.state.phase2_store.workspace(account).open_meeting(meeting_id)
        if handle is None:
            raise HTTPException(404, "Meeting not found.")
        return MeetingSummaries(handle)

    async def options(request, *, final=False):
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "Invalid summary request.") from None
        allowed = {"model", "language", "prompt", "provider"} | ({"source_version"} if final else set())
        if (not isinstance(body, dict) or set(body) - allowed
                or any(not isinstance(body[key], str) for key in ("model", "language", "prompt") if key in body)
                or (final and (type(body.get("source_version")) is not int))):
            raise HTTPException(400, "Invalid summary options.")
        # An entered Gemini key takes precedence over the operator fallback.
        provider = body.get("provider")
        if provider is None:
            raise HTTPException(400, {"code": "api_key_required"})
        if (not isinstance(provider, dict) or set(provider) - {"vendor", "model", "api_key"}
                or any(provider.get(key) is not None and not isinstance(provider[key], str)
                       for key in ("vendor", "model", "api_key"))):
            raise HTTPException(400, "Invalid summary provider.")
        if provider.get("vendor", "gemini") != "gemini":
            raise HTTPException(400, "Server summaries use Gemini; OpenAI-compatible summaries run in the browser.")
        api_key = gemini_api_key(provider.get("api_key"))
        if not api_key:
            raise HTTPException(400, {"code": "api_key_required"})
        model = ((provider.get("model") or "").strip() or (body.get("model") or "").strip()
                 or DEFAULT_SUMMARY_MODEL)
        return {**{key: body[key] for key in body if key != "provider"},
                "model": model, "api_key": api_key}

    async def generate(request, document, body):
        # Flash-lite occasionally returns malformed or out-of-contract JSON (long60: 1 of 2 calls);
        # like LiveTranscribe, retry a bounded number of times and report the summed usage.
        service = request.app.state.summary_generator
        if service is None:
            raise HTTPException(503, {"code": "summary_unavailable"})
        duration = max((float(row["end"]) for row in document["segments"]), default=0)
        spent = None
        for _attempt in range(SUMMARY_ATTEMPTS):
            try:
                result, usage = await service(document, model=body["model"],
                                              language=body.get("language", ""),
                                              prompt=body.get("prompt", DEFAULT_SUMMARY_PROMPT),
                                              api_key=body["api_key"])
            except TimeoutError:
                raise HTTPException(504, {"code": "summary_timeout"}) from None
            except ValueError as exc:
                spent = _add_usage(spent, getattr(exc, "usage", None))
                continue
            except Exception:
                raise HTTPException(502, {"code": "summary_provider_error"}) from None
            spent = _add_usage(spent, usage)
            try:
                return validate_summary(result, duration), spent
            except ValueError:
                continue
        raise HTTPException(502, {"code": "invalid_summary"})

    def claim(request, meeting_id, source_version=None):
        inflight = request.app.state.summary_inflight
        key = (meeting_id, source_version)
        if any(existing_id == meeting_id and
               (source_version is None or existing_version is None or
                existing_version == source_version)
               for existing_id, existing_version in inflight):
            raise HTTPException(429, {"code": "summary_in_flight"})
        inflight.add(key)
        return key

    @app.post("/api/meetings/{meeting_id}/summary/live")
    async def live_summary(meeting_id: str, request: Request):
        await summary_handle(request, meeting_id)
        body = await options(request)
        live = getattr(request.app.state, "phase2_live", None)
        if live is None:
            raise HTTPException(409, "No active live transcript.")
        account = await require_account(request)
        try:
            binding = live.open(account, "", meeting_id, mutation=False)
        except LiveMeetingNotFound:
            raise HTTPException(409, "No active live transcript.") from None
        snapshot = binding.public_snapshot
        if snapshot is None or snapshot.session.status != "active":
            raise HTTPException(409, "No active live transcript.")
        document = _transcript_document(snapshot, binding.speaker_labels)
        if transcript_words(document) < 40:
            raise HTTPException(409, "At least 40 transcript words are required.")
        claim_key = claim(request, meeting_id)
        try:
            result, usage = await generate(request, document, body)
            duration = max((float(row["end"]) for row in document["segments"]), default=0)
            try:
                result = validate_summary(result, duration)
            except ValueError:
                raise HTTPException(502, {"code": "invalid_summary"}) from None
            return {"summary": result, "source": {
                "committed_samples": snapshot.session.committed_samples,
                "text_revision_version": snapshot.session.text_revision_version},
                "speaker_names": speaker_names(document),
                "generated_at_ms": _now_ms(), "usage": usage}
        finally:
            request.app.state.summary_inflight.discard(claim_key)

    @app.post("/api/meetings/{meeting_id}/summary/server")
    async def server_summary(meeting_id: str, request: Request):
        summary = await summary_handle(request, meeting_id)
        body = await options(request, final=True)
        if request.app.state.summary_generator is None:
            raise HTTPException(503, {"code": "summary_unavailable"})
        claim_key = claim(request, meeting_id, body["source_version"])
        try:
            async def attempt_conflict(attempt_id):
                current = await summary.read()
                if (current is not None and
                        ((current["attempt_id"] == attempt_id and
                          current["error_code"] == "source_changed") or
                         current["source_version"] > attempt["source_version"])):
                    return JSONResponse({"code": "summary_source_changed"}, status_code=409)
                code = ("summary_cancelled" if current is not None
                        and current["attempt_id"] == attempt_id and current["state"] == "cancelled"
                        else "summary_conflict")
                raise HTTPException(409, {"code": code})

            try:
                attempt, document = await summary.start_server(body["source_version"])
            except SummaryConflict as exc:
                if "already active" in str(exc):
                    raise HTTPException(429, {"code": "summary_in_flight"}) from exc
                raise HTTPException(409, str(exc)) from exc
            attempt_id = attempt["attempt_id"]
            try:
                await summary.update(attempt_id, "generating")
            except SummaryConflict:
                return await attempt_conflict(attempt_id)
            try:
                result, usage = await generate(request, document, body)
            except HTTPException as exc:
                code = "invalid_output" if exc.status_code == 502 and exc.detail == {"code": "invalid_summary"} else "delivery_failed"
                try:
                    await summary.update(attempt_id, "failed", error_code=code)
                except SummaryConflict:
                    return await attempt_conflict(attempt_id)
                raise
            try:
                artifact = await summary.update(attempt_id, "current", document=result)
            except SummaryConflict:
                return await attempt_conflict(attempt_id)
            except ValueError:
                try:
                    await summary.update(attempt_id, "failed", error_code="invalid_output")
                except SummaryConflict:
                    return await attempt_conflict(attempt_id)
                raise HTTPException(502, {"code": "invalid_summary"}) from None
            return {**artifact, "usage": usage}
        finally:
            request.app.state.summary_inflight.discard(claim_key)

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
