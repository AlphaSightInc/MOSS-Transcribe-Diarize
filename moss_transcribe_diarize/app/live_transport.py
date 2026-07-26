from __future__ import annotations

import asyncio
import base64
import binascii
import time
from dataclasses import dataclass
from typing import Any

from starlette.requests import Request

from .live_auth import (
    CapturePrincipal,
    LiveAccessError,
    LiveAccessRegistry,
    LivePeer,
)
from .live_ingest import (
    LiveV2EpochDiscontinuityRequiredError,
    LiveV2LaneCapacityError,
    LiveV2StaleDeviceEpochError,
)
from .live_lane_contract import (
    LiveLane,
    LiveV2Ack,
    LiveV2Frame,
    LiveV2ObsoleteClientError,
    LiveV2OutOfOrderFrameError,
    LiveV2PrunedReplayError,
    negotiate_v2_protocol,
)
from .live_helper_presence import (
    HelperHeartbeat,
    HelperPresenceConflict,
    HelperPresenceRegistry,
)
from .live_helper_failure import LiveHelperFailureCoordinator
from .live_mixer import (
    LiveCompatibilityMixerRegistry,
    LiveMixIntegrityError,
    LiveMixSourceMissingError,
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
from .live_v2_session import LiveV2SessionRegistry, LiveV2SessionTerminalError


def attach_live_routes(
    app,
    runtime: LiveServiceRuntime,
    access: LiveAccessRegistry,
    *,
    live_helper_lease_seconds: float,
) -> None:
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    v2_sessions = LiveV2SessionRegistry(
        max_retained_samples=runtime.descriptor.bounds.max_retained_samples
    )
    v2_mixers = LiveCompatibilityMixerRegistry()
    helper_presence = HelperPresenceRegistry()
    helper_failures = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=live_helper_lease_seconds,
        v2_sessions=v2_sessions,
        v2_mixers=v2_mixers,
        helper_presence=helper_presence,
        access=access,
        abort_mono=runtime.abort,
    )
    app.state.live_v2_sessions = v2_sessions
    app.state.live_v2_mixers = v2_mixers
    app.state.live_helper_presence = helper_presence
    app.state.live_helper_failures = helper_failures

    @app.get("/api/live/descriptor")
    def live_descriptor(
        request: Request,
        client_min_protocol_version: int | None = None,
        client_max_protocol_version: int | None = None,
    ):
        try:
            access.authorize(
                _peer_from_request(request),
                None,
                "descriptor",
                None,
                now=_request_now(),
            )
            return _descriptor_payload(
                runtime,
                client_min_protocol_version=client_min_protocol_version,
                client_max_protocol_version=client_max_protocol_version,
            )
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except LiveV2ObsoleteClientError as exc:
            status, payload = live_v2_obsolete_client_response(exc)
            return JSONResponse(payload, status_code=status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/live/pairing-codes")
    def issue_live_pairing(request: Request):
        try:
            grant = access.issue_pairing(_peer_from_request(request), now=_request_now())
            return {"pairing_payload": grant.pairing_payload, "expires_at": grant.expires_at}
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.post("/api/live/pairings")
    async def exchange_live_pairing(request: Request):
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError("pairing request must be a JSON object.")
            credential = access.exchange_pairing(
                _peer_from_request(request),
                str(payload.get("pairing_payload") or ""),
                device_id=str(payload.get("device_id") or ""),
                now=_request_now(),
            )
            return {
                "device_id": credential.device_id,
                "device_token": credential.device_token,
                "scope": credential.scope,
            }
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/live/sessions")
    def create_live_session(request: Request):
        try:
            decision = access.authorize(
                _peer_from_request(request),
                _bearer_from_request(request),
                "create",
                None,
                now=_request_now(),
            )
            if not isinstance(decision.principal, CapturePrincipal):
                raise HTTPException(status_code=403, detail="capture authority is required.")
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        created = runtime.create()
        try:
            view = access.bind_session(decision.principal, created.session_id, now=_request_now())
            v2_sessions.create(created.session_id)
            v2_mixers.create(created.session_id)
        except Exception:
            access.release_session(created.session_id)
            raise
        return {
            "id": created.session_id,
            "owner_device_id": view.owner_device_id,
            "view_token": view.view_token,
            "view_expires_at": view.expires_at,
            "descriptor": created.descriptor.to_dict(),
            "snapshot": created.snapshot.to_dict(),
        }

    @app.post("/api/live/sessions/{session_id}/frames")
    async def accept_live_frame(session_id: str, request: Request):
        try:
            access.authorize(
                _peer_from_request(request),
                _bearer_from_request(request),
                "frame",
                session_id,
                now=_request_now(),
            )
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
                snapshot = runtime.snapshot(session_id)
                if snapshot is None:
                    raise KeyError(session_id)
                if snapshot.session.status != "active":
                    raise LiveSessionClosed(f"live session is {snapshot.session.status}.")
                v2_session = v2_sessions.get(session_id)
                ack = v2_session.accept(frame.v2_frame)
                mixed = v2_mixers.get(session_id).admit_available(
                    session_id,
                    v2_session,
                    runtime,
                    final=False,
                )
                snapshot = runtime.snapshot(session_id)
                if snapshot is None:
                    raise KeyError(session_id)
                result = _TransportAcceptResult(
                    ack=ack,
                    queued_item_ids=() if mixed is None else mixed.queued_item_ids,
                    snapshot_version=snapshot.session.version,
                )
            return {
                "ack": _jsonable(_ack_for_transport(result.ack, lane=frame.lane)),
                "queued_item_ids": list(result.queued_item_ids),
                "snapshot_version": result.snapshot_version,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except (
            LiveV2EpochDiscontinuityRequiredError,
            LiveV2LaneCapacityError,
            LiveV2OutOfOrderFrameError,
            LiveV2PrunedReplayError,
            LiveV2StaleDeviceEpochError,
        ) as exc:
            status, conflict = live_v2_ingress_failure_response(exc)
            conflict["snapshot"] = _snapshot_payload(runtime, session_id)
            conflict["v2_session"] = _v2_snapshot_payload(v2_sessions, session_id)
            return JSONResponse(conflict, status_code=status)
        except LiveSessionBackpressure as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=429,
            )
        except LiveSessionClosed as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LiveV2SessionTerminalError as exc:
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

    @app.post("/api/live/sessions/{session_id}/heartbeat")
    async def accept_live_helper_heartbeat(session_id: str, request: Request):
        return await _accept_live_helper_heartbeat(
            request,
            session_id,
            access=access,
            helper_presence=helper_presence,
            helper_failures=helper_failures,
        )

    @app.get("/api/live/sessions/{session_id}/snapshot")
    def live_snapshot(request: Request, session_id: str, since_version: int | None = None):
        try:
            access.authorize(
                _peer_from_request(request),
                _bearer_from_request(request),
                "snapshot",
                session_id,
                now=_request_now(),
            )
            return _snapshot_response(
                runtime,
                v2_sessions,
                helper_presence,
                session_id,
                since_version=since_version,
            )
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/live/sessions/{session_id}/events")
    def live_events(request: Request, session_id: str, since_seq: int = 0):
        try:
            access.authorize(
                _peer_from_request(request),
                _bearer_from_request(request),
                "events",
                session_id,
                now=_request_now(),
            )
            events = runtime.events(session_id, since_seq=since_seq)
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"events": [event.to_dict() for event in events]}

    @app.post("/api/live/sessions/{session_id}/stop")
    async def stop_live_session(session_id: str, request: Request):
        release_v2_on_error = False
        try:
            access.authorize(
                _peer_from_request(request),
                _bearer_from_request(request),
                "stop",
                session_id,
                now=_request_now(),
            )
            payload = await _optional_json(request)
            deadline = float(payload.get("deadline", 0.0))
            loop = asyncio.get_running_loop()
            end_time = loop.time() + max(0.0, deadline)
            try:
                v2_session = v2_sessions.get(session_id)
            except KeyError:
                v2_session = None
            v2_snapshot = None
            if v2_session is not None:
                v2_snapshot = await v2_session.stop(0.0)
                if v2_snapshot.status == "closing":
                    v2_mixers.get(session_id).admit_available(
                        session_id,
                        v2_session,
                        runtime,
                        final=True,
                    )
                    v2_snapshot = await v2_session.stop(max(0.0, end_time - loop.time()))
                if v2_snapshot.status == "closing":
                    status, failure = live_v2_unconsumed_frames_response()
                    failure["snapshot"] = _snapshot_payload(runtime, session_id)
                    failure["v2_session"] = v2_snapshot.to_dict()
                    return JSONResponse(failure, status_code=status)
                if v2_snapshot.status == "failed":
                    v2_sessions.release(session_id)
                    v2_mixers.release(session_id)
                    helper_failures.release(session_id)
                    helper_presence.release(session_id)
                    access.release_session(session_id)
                    status, failure = live_v2_terminal_failure_response(v2_snapshot.terminal_reason)
                    failure["snapshot"] = _snapshot_payload(runtime, session_id)
                    failure["v2_session"] = v2_snapshot.to_dict()
                    return JSONResponse(failure, status_code=status)
                release_v2_on_error = True
            deadline = max(0.0, end_time - loop.time())
            stopped = await runtime.stop(session_id, deadline)
            v2_sessions.release(session_id)
            v2_mixers.release(session_id)
            helper_failures.release(session_id)
            helper_presence.release(session_id)
            access.release_session(session_id)
            release_v2_on_error = False
            response = {"snapshot": stopped.to_dict()}
            if v2_snapshot is not None:
                response["v2_session"] = v2_snapshot.to_dict()
            return response
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except TimeoutError as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=409,
            )
        except (LiveSessionClosed, LiveSessionFailed) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LiveV2SessionTerminalError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except LiveMixIntegrityError as exc:
            status, failure = live_v2_mix_failure_response(exc)
            failure["snapshot"] = _snapshot_payload(runtime, session_id)
            failure["v2_session"] = _v2_snapshot_payload(v2_sessions, session_id)
            if isinstance(exc, LiveMixSourceMissingError):
                v2_mixers.release(session_id)
            return JSONResponse(failure, status_code=status)
        except LiveServiceError as exc:
            return JSONResponse(
                {"detail": str(exc), "failure": exc.failure.to_dict(), "snapshot": _snapshot_payload(runtime, session_id)},
                status_code=_failure_status(exc),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if release_v2_on_error:
                v2_sessions.release(session_id)
                v2_mixers.release(session_id)
                helper_failures.release(session_id)
                helper_presence.release(session_id)

    @app.post("/api/live/sessions/{session_id}/abort")
    async def abort_live_session(session_id: str, request: Request):
        try:
            access.authorize(
                _peer_from_request(request),
                _bearer_from_request(request),
                "abort",
                session_id,
                now=_request_now(),
            )
            payload = await _optional_json(request)
            reason = str(payload.get("reason") or "aborted")
            snapshot = await runtime.abort(session_id, reason)
            try:
                v2_session = v2_sessions.get(session_id)
            except KeyError:
                v2_session = None
            if v2_session is not None:
                try:
                    v2_session.abort(reason)
                except LiveV2SessionTerminalError:
                    pass
                v2_sessions.release(session_id)
                v2_mixers.release(session_id)
            helper_failures.release(session_id)
            helper_presence.release(session_id)
            access.release_session(session_id)
            return {"snapshot": snapshot.to_dict()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    @app.delete("/api/live/devices/{device_id}")
    async def revoke_live_device(request: Request, device_id: str):
        try:
            revoked = access.revoke_device(_peer_from_request(request), device_id, now=_request_now())
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        for session_id in revoked.session_ids:
            try:
                await runtime.abort(session_id, "device revoked")
            except Exception:
                pass
            try:
                v2_sessions.get(session_id).abort("device revoked")
            except (KeyError, LiveV2SessionTerminalError):
                pass
            v2_sessions.release(session_id)
            v2_mixers.release(session_id)
            helper_failures.release(session_id)
            helper_presence.release(session_id)
            access.release_session(session_id)
        return {"device_id": revoked.device_id, "session_ids": list(revoked.session_ids)}


@dataclass(frozen=True, slots=True)
class _TransportFrame:
    audio_frame: AudioFrame
    lane: LiveLane | None = None
    v2_frame: LiveV2Frame | None = None


@dataclass(frozen=True, slots=True)
class _TransportAcceptResult:
    ack: FrameAck | LiveV2Ack
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


def _peer_from_request(request: Request) -> LivePeer:
    client = request.client
    host = "" if client is None else client.host
    return LivePeer(host=host, scheme=str(request.scope.get("scheme") or "http"))


def _bearer_from_request(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


async def _accept_live_helper_heartbeat(
    request: Request,
    session_id: str,
    *,
    access: LiveAccessRegistry,
    helper_presence: HelperPresenceRegistry,
    helper_failures: LiveHelperFailureCoordinator,
):
    from fastapi.responses import JSONResponse

    try:
        access.authorize(
            _peer_from_request(request),
            _bearer_from_request(request),
            "heartbeat",
            session_id,
            now=_request_now(),
        )
        heartbeat = HelperHeartbeat.from_dict(await request.json())
        snapshot = helper_presence.observe(session_id, heartbeat)
        await helper_failures.observe(session_id, snapshot)
        return JSONResponse({"helper_presence": snapshot.to_dict()})
    except KeyError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=404)
    except LiveAccessError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)
    except HelperPresenceConflict as exc:
        return JSONResponse({"detail": str(exc)}, status_code=409)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


def _request_now() -> float:
    return time.time()


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


def _snapshot_response(
    runtime: LiveServiceRuntime,
    v2_sessions: LiveV2SessionRegistry,
    helper_presence: HelperPresenceRegistry,
    session_id: str,
    *,
    since_version: int | None = None,
) -> dict[str, Any]:
    snapshot = runtime.snapshot(session_id, since_version=since_version)
    return {
        "snapshot": None if snapshot is None else snapshot.to_dict(),
        "unchanged": snapshot is None,
        "v2_session": _v2_snapshot_payload(v2_sessions, session_id),
        "helper_presence": _helper_presence_payload(helper_presence, session_id),
    }


def _snapshot_payload(runtime: LiveServiceRuntime, session_id: str) -> dict[str, Any] | None:
    try:
        snapshot = runtime.snapshot(session_id)
    except KeyError:
        return None
    return None if snapshot is None else snapshot.to_dict()


def _v2_snapshot_payload(
    v2_sessions: LiveV2SessionRegistry,
    session_id: str,
) -> dict[str, Any] | None:
    try:
        return v2_sessions.get(session_id).snapshot().to_dict()
    except KeyError:
        return None


def _helper_presence_payload(
    helper_presence: HelperPresenceRegistry,
    session_id: str,
) -> dict[str, Any] | None:
    snapshot = helper_presence.snapshot(session_id)
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
    exc: LiveV2OutOfOrderFrameError | LiveV2PrunedReplayError,
) -> tuple[int, dict[str, Any]]:
    if isinstance(exc, LiveV2OutOfOrderFrameError):
        failure = {
            "code": "v2_out_of_order_frame",
            "lane": exc.lane.value,
            "expected_sequence": exc.expected_sequence,
            "received_sequence": exc.received_sequence,
        }
    else:
        failure = {
            "code": "v2_pruned_replay",
            "lane": exc.lane.value,
            "sequence": exc.sequence,
            "pruned_through_sequence": exc.pruned_through_sequence,
        }
    return 409, {"detail": str(exc), "failure": failure}


def live_v2_ingress_failure_response(
    exc: (
        LiveV2EpochDiscontinuityRequiredError
        | LiveV2LaneCapacityError
        | LiveV2OutOfOrderFrameError
        | LiveV2PrunedReplayError
        | LiveV2StaleDeviceEpochError
    ),
) -> tuple[int, dict[str, Any]]:
    if isinstance(exc, (LiveV2OutOfOrderFrameError, LiveV2PrunedReplayError)):
        return live_v2_replay_conflict_response(exc)
    if isinstance(exc, LiveV2LaneCapacityError):
        failure = {
            "code": "v2_lane_retention_capacity_reached",
            "lane": exc.lane.value,
            "max_retained_samples": exc.max_retained_samples,
            "retained_samples": exc.retained_samples,
            "frame_sample_count": exc.frame_sample_count,
        }
        return 429, {"detail": str(exc), "failure": failure}
    if isinstance(exc, LiveV2EpochDiscontinuityRequiredError):
        code = "v2_epoch_discontinuity_required"
    else:
        code = "v2_stale_device_epoch"
    failure = {
        "code": code,
        "lane": exc.lane.value,
        "sequence": exc.sequence,
        "current_device_epoch": exc.current_device_epoch,
        "received_device_epoch": exc.received_device_epoch,
    }
    return 409, {"detail": str(exc), "failure": failure}


def live_v2_unconsumed_frames_response() -> tuple[int, dict[str, Any]]:
    return (
        409,
        {
            "detail": "v2 lane frames remain retained for the future mixer.",
            "failure": {"code": "v2_unconsumed_lane_frames"},
        },
    )


def live_v2_terminal_failure_response(reason: str | None) -> tuple[int, dict[str, Any]]:
    return (
        409,
        {
            "detail": "v2 lane session failed before clean stop.",
            "failure": {"code": "v2_stop_accounting_mismatch", "reason": reason},
        },
    )


def live_v2_mix_failure_response(exc: LiveMixIntegrityError) -> tuple[int, dict[str, Any]]:
    code = "v2_mix_source_missing" if isinstance(exc, LiveMixSourceMissingError) else "v2_mix_integrity"
    return 409, {"detail": str(exc), "failure": {"code": code}}


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
