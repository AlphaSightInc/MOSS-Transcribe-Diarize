from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request

from .live_lane_contract import (
    LiveLane,
    LiveV2Ack,
    LiveV2Frame,
    LiveV2ObsoleteClientError,
    LiveV2OutOfOrderFrameError,
    LiveV2PriorAckReplayStore,
    LiveV2PrunedReplayError,
    LiveV2ReplayStoreFullError,
    negotiate_v2_protocol,
)
from .live_service_runtime import (
    LiveServiceError,
    LiveServiceFailureKind,
    LiveServiceRuntime,
)
from .live_session import (
    AudioFrame,
    FrameAck,
    LIVE_SAMPLE_RATE,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
)


def attach_live_routes(app, runtime: LiveServiceRuntime) -> None:
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    v2_replay_stores: dict[str, LiveV2PriorAckReplayStore] = {}

    @app.get("/api/live/descriptor")
    def live_descriptor(client_min_protocol_version: int | None = None, client_max_protocol_version: int | None = None):
        try:
            return _descriptor_payload(
                runtime,
                client_min_protocol_version=client_min_protocol_version,
                client_max_protocol_version=client_max_protocol_version,
            )
        except LiveV2ObsoleteClientError as exc:
            status, payload = live_v2_obsolete_client_response(exc)
            return JSONResponse(payload, status_code=status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/live/sessions")
    def create_live_session():
        created = runtime.create()
        v2_replay_stores[created.session_id] = LiveV2PriorAckReplayStore(
            max_retained_acks=runtime.descriptor.bounds.max_events
        )
        return {
            "id": created.session_id,
            "descriptor": created.descriptor.to_dict(),
            "snapshot": created.snapshot.to_dict(),
        }

    @app.post("/api/live/sessions/{session_id}/frames")
    async def accept_live_frame(session_id: str, request: Request):
        try:
            payload = await request.json()
            frame = _frame_from_payload(payload)
            if frame.v2_frame is None:
                accepted = runtime.accept_frame(session_id, frame.audio_frame)
                result = _TransportAcceptResult(
                    ack=accepted.ack,
                    queued_item_ids=accepted.queued_item_ids,
                    snapshot_version=accepted.snapshot.session.version,
                )
            else:
                result = _accept_v2_frame(
                    runtime,
                    v2_replay_stores[session_id],
                    session_id=session_id,
                    frame=frame.v2_frame,
                )
            return {
                "ack": _jsonable(_ack_for_transport(result.ack, lane=frame.lane)),
                "queued_item_ids": list(result.queued_item_ids),
                "snapshot_version": result.snapshot_version,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (LiveV2OutOfOrderFrameError, LiveV2PrunedReplayError, LiveV2ReplayStoreFullError) as exc:
            status, conflict = live_v2_replay_conflict_response(exc)
            conflict["snapshot"] = _snapshot_payload(runtime, session_id)
            return JSONResponse(conflict, status_code=status)
        except LiveSessionBackpressure as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=429,
            )
        except LiveSessionClosed as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            status_code = 409 if str(exc).startswith("expected frame sequence") else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except LiveServiceError as exc:
            status_code = _failure_status(exc)
            return JSONResponse(
                {"detail": str(exc), "failure": exc.failure.to_dict(), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=status_code,
            )

    @app.get("/api/live/sessions/{session_id}/snapshot")
    def live_snapshot(session_id: str, since_version: int | None = None):
        try:
            snapshot = runtime.snapshot(session_id, since_version=since_version)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "snapshot": None if snapshot is None else snapshot.to_dict(),
            "unchanged": snapshot is None,
        }

    @app.get("/api/live/sessions/{session_id}/events")
    def live_events(session_id: str, since_seq: int = 0):
        try:
            events = runtime.events(session_id, since_seq=since_seq)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"events": [event.to_dict() for event in events]}

    @app.post("/api/live/sessions/{session_id}/stop")
    async def stop_live_session(session_id: str, request: Request):
        try:
            payload = await _optional_json(request)
            deadline = float(payload.get("deadline", 0.0))
            return {"snapshot": (await runtime.stop(session_id, deadline)).to_dict()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TimeoutError as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=409,
            )
        except (LiveSessionClosed, LiveSessionFailed) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LiveServiceError as exc:
            return JSONResponse(
                {"detail": str(exc), "failure": exc.failure.to_dict(), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=_failure_status(exc),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/live/sessions/{session_id}/abort")
    async def abort_live_session(session_id: str, request: Request):
        try:
            payload = await _optional_json(request)
            reason = str(payload.get("reason") or "aborted")
            return {"snapshot": (await runtime.abort(session_id, reason)).to_dict()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc


@dataclass(frozen=True, slots=True)
class _TransportFrame:
    audio_frame: AudioFrame
    lane: LiveLane | None = None
    v2_frame: LiveV2Frame | None = None


@dataclass(frozen=True, slots=True)
class _TransportAcceptResult:
    ack: FrameAck
    queued_item_ids: tuple[int, ...]
    snapshot_version: int


async def _optional_json(request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _descriptor_payload(
    runtime: LiveServiceRuntime,
    *,
    client_min_protocol_version: int | None,
    client_max_protocol_version: int | None,
) -> dict[str, Any]:
    payload = {"descriptor": runtime.descriptor.to_dict()}
    if client_min_protocol_version is None and client_max_protocol_version is None:
        return payload
    if client_min_protocol_version is None or client_max_protocol_version is None:
        raise ValueError("both client_min_protocol_version and client_max_protocol_version are required.")
    negotiated = negotiate_v2_protocol(
        client_min_protocol_version=client_min_protocol_version,
        client_max_protocol_version=client_max_protocol_version,
        server_descriptor=runtime.descriptor.live_protocol,
    )
    payload["negotiation"] = negotiated.to_dict()
    return payload


def _frame_from_payload(payload: Any) -> _TransportFrame:
    if not isinstance(payload, dict):
        raise ValueError("frame payload must be a JSON object.")
    if _is_v2_frame_payload(payload):
        frame = LiveV2Frame.from_dict(payload)
        return _TransportFrame(
            audio_frame=AudioFrame(
                sequence=frame.sequence,
                pcm=frame.pcm,
                sample_count=frame.sample_count,
                sample_rate=frame.sample_rate,
            ),
            lane=frame.lane,
            v2_frame=frame,
        )
    try:
        pcm = base64.b64decode(str(payload["pcm_base64"]), validate=True)
        sample_count = int(payload["sample_count"])
        sequence = int(payload["sequence"])
        sample_rate = int(payload.get("sample_rate", LIVE_SAMPLE_RATE))
    except KeyError as exc:
        raise ValueError("frame payload missing required fields.") from exc
    except (binascii.Error, TypeError) as exc:
        raise ValueError("frame pcm_base64 must be valid base64.") from exc
    return _TransportFrame(
        audio_frame=AudioFrame(
            sequence=sequence,
            pcm=pcm,
            sample_count=sample_count,
            sample_rate=sample_rate,
        ),
    )


def _is_v2_frame_payload(payload: dict[str, Any]) -> bool:
    return any(
        field in payload
        for field in (
            "lane",
            "capture_timestamp_ns",
            "device_epoch",
            "silent",
            "discontinuity",
        )
    )


def _ack_for_transport(ack, *, lane: LiveLane | None) -> Any:
    if lane is None:
        return ack
    return LiveV2Ack(
        lane=lane,
        sequence=ack.sequence,
        start_sample=ack.start_sample,
        end_sample=ack.end_sample,
        accepted_samples=ack.accepted_samples,
        retained_samples=ack.retained_samples,
        frozen_span_ids=ack.frozen_span_ids,
    )


def _accept_v2_frame(
    runtime: LiveServiceRuntime,
    replay_store: LiveV2PriorAckReplayStore,
    *,
    session_id: str,
    frame: LiveV2Frame,
) -> _TransportAcceptResult:
    accepted_result = None

    def accept_new(v2_frame: LiveV2Frame) -> LiveV2Ack:
        nonlocal accepted_result
        snapshot = runtime.snapshot(session_id)
        if snapshot is None:
            raise KeyError(session_id)
        accepted_result = runtime.accept_frame(
            session_id,
            AudioFrame(
                sequence=snapshot.session.next_frame_sequence,
                pcm=v2_frame.pcm,
                sample_count=v2_frame.sample_count,
                sample_rate=v2_frame.sample_rate,
            ),
        )
        ack = accepted_result.ack
        return LiveV2Ack(
            lane=v2_frame.lane,
            sequence=v2_frame.sequence,
            start_sample=ack.start_sample,
            end_sample=ack.end_sample,
            accepted_samples=ack.accepted_samples,
            retained_samples=ack.retained_samples,
            frozen_span_ids=ack.frozen_span_ids,
        )

    v2_ack = replay_store.accept(frame, accept_new)
    if accepted_result is None:
        snapshot = runtime.snapshot(session_id)
        if snapshot is None:
            raise KeyError(session_id)
        queued_item_ids = ()
        snapshot_version = snapshot.session.version
    else:
        queued_item_ids = accepted_result.queued_item_ids
        snapshot_version = accepted_result.snapshot.session.version
    return _TransportAcceptResult(
        ack=FrameAck(
            sequence=v2_ack.sequence,
            start_sample=v2_ack.start_sample,
            end_sample=v2_ack.end_sample,
            accepted_samples=v2_ack.accepted_samples,
            retained_samples=v2_ack.retained_samples,
            frozen_span_ids=v2_ack.frozen_span_ids,
        ),
        queued_item_ids=queued_item_ids,
        snapshot_version=snapshot_version,
    )


def _snapshot_payload(runtime: LiveServiceRuntime, session_id: str) -> dict[str, Any] | None:
    try:
        snapshot = runtime.snapshot(session_id)
    except KeyError:
        return None
    return None if snapshot is None else snapshot.to_dict()


def _failure_status(exc: LiveServiceError) -> int:
    if exc.failure.kind == LiveServiceFailureKind.TRANSPORT_PACING:
        return 429
    if exc.failure.kind == LiveServiceFailureKind.PROVIDER_CONFIG:
        return 503
    return 409


def live_v2_obsolete_client_response(exc: LiveV2ObsoleteClientError) -> tuple[int, dict[str, Any]]:
    return 426, {"detail": str(exc), "failure": exc.to_dict()}


def live_v2_replay_conflict_response(
    exc: LiveV2OutOfOrderFrameError | LiveV2PrunedReplayError | LiveV2ReplayStoreFullError,
) -> tuple[int, dict[str, Any]]:
    if isinstance(exc, LiveV2OutOfOrderFrameError):
        failure = {
            "code": "v2_out_of_order_frame",
            "lane": exc.lane.value,
            "expected_sequence": exc.expected_sequence,
            "received_sequence": exc.received_sequence,
        }
    elif isinstance(exc, LiveV2PrunedReplayError):
        failure = {
            "code": "v2_pruned_replay",
            "lane": exc.lane.value,
            "sequence": exc.sequence,
            "pruned_through_sequence": exc.pruned_through_sequence,
        }
    else:
        failure = {"code": "v2_replay_store_full"}
    return 409, {"detail": str(exc), "failure": failure}


def _jsonable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dataclass_fields__"):
        return {field: _jsonable(getattr(value, field)) for field in value.__dataclass_fields__}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value
