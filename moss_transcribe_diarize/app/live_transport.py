from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import asdict
from typing import Any

from starlette.requests import Request

from .live_session import (
    AudioFrame,
    LIVE_SAMPLE_RATE,
    LiveSession,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
)


class LiveTransportSessions:
    def __init__(self, *, max_retained_samples: int, hard_cap_samples: int | None = None):
        if max_retained_samples <= 0:
            raise ValueError("live_max_retained_samples must be positive when live mode is enabled.")
        self.max_retained_samples = int(max_retained_samples)
        self.hard_cap_samples = None if hard_cap_samples is None else int(hard_cap_samples)
        self._sessions: dict[str, LiveSession] = {}

    def create(self) -> tuple[str, LiveSession]:
        session_id = uuid.uuid4().hex
        session = LiveSession(
            max_retained_samples=self.max_retained_samples,
            hard_cap_samples=self.hard_cap_samples,
        )
        self._sessions[session_id] = session
        return session_id, session

    def get(self, session_id: str) -> LiveSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown live session {session_id}") from exc


def attach_live_routes(app, live_sessions: LiveTransportSessions) -> None:
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    @app.post("/api/live/sessions")
    def create_live_session():
        session_id, session = live_sessions.create()
        return {"id": session_id, "snapshot": _snapshot_payload(session)}

    @app.post("/api/live/sessions/{session_id}/frames")
    async def accept_live_frame(session_id: str, request: Request):
        session = _lookup(live_sessions, session_id)
        try:
            payload = await request.json()
            frame = _frame_from_payload(payload)
            ack = session.accept_frame(frame)
            snapshot = session.snapshot()
            return {"ack": asdict(ack), "snapshot_version": snapshot.version}
        except LiveSessionBackpressure as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _snapshot_payload(session)},
                status_code=429,
            )
        except LiveSessionClosed as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            status_code = 409 if str(exc).startswith("expected frame sequence") else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc

    @app.get("/api/live/sessions/{session_id}/snapshot")
    def live_snapshot(session_id: str, since_version: int | None = None):
        session = _lookup(live_sessions, session_id)
        snapshot = session.snapshot()
        return {
            "snapshot": _snapshot_payload(session),
            "unchanged": since_version is not None and snapshot.version <= since_version,
        }

    @app.post("/api/live/sessions/{session_id}/stop")
    async def stop_live_session(session_id: str, request: Request):
        session = _lookup(live_sessions, session_id)
        try:
            payload = await _optional_json(request)
            deadline = float(payload.get("deadline", 0.0))
            return {"snapshot": _snapshot_dict(await session.stop(deadline))}
        except TimeoutError as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _snapshot_payload(session)},
                status_code=409,
            )
        except (LiveSessionClosed, LiveSessionFailed) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/live/sessions/{session_id}/abort")
    async def abort_live_session(session_id: str, request: Request):
        session = _lookup(live_sessions, session_id)
        payload = await _optional_json(request)
        reason = str(payload.get("reason") or "aborted")
        return {"snapshot": _snapshot_dict(await session.abort(reason))}


def _lookup(live_sessions: LiveTransportSessions, session_id: str) -> LiveSession:
    from fastapi import HTTPException

    try:
        return live_sessions.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def _optional_json(request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _frame_from_payload(payload: Any) -> AudioFrame:
    if not isinstance(payload, dict):
        raise ValueError("frame payload must be a JSON object.")
    try:
        pcm = base64.b64decode(str(payload["pcm_base64"]), validate=True)
        sample_count = int(payload["sample_count"])
        sequence = int(payload["sequence"])
        sample_rate = int(payload.get("sample_rate", LIVE_SAMPLE_RATE))
    except KeyError as exc:
        raise ValueError("frame payload missing required fields.") from exc
    except (binascii.Error, TypeError) as exc:
        raise ValueError("frame pcm_base64 must be valid base64.") from exc
    return AudioFrame(
        sequence=sequence,
        pcm=pcm,
        sample_count=sample_count,
        sample_rate=sample_rate,
    )


def _snapshot_payload(session: LiveSession) -> dict[str, Any]:
    return _snapshot_dict(session.snapshot())


def _snapshot_dict(snapshot) -> dict[str, Any]:
    return asdict(snapshot)
