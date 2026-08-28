from __future__ import annotations

import asyncio
import base64
import binascii
import time
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from starlette.requests import Request

from .live_arbiter import InferenceArbiterBackpressure
from .live_auth import (
    CapturePrincipal,
    LiveAccessError,
    LiveAccessRegistry,
    LivePeer,
)
from .live_capture_status import (
    BROWSER_MICROPHONE_SILENT_STATUS_LINE,
    LiveCaptureHealthPolicy,
    LiveCaptureObservationRegistry,
    project_live_capture_status,
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
    LiveMixResult,
    LiveMixSourceMissingError,
)
from .live_service_runtime import (
    LiveServiceError,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceRuntime,
    LiveServiceSnapshot,
)
from .live_session import (
    AudioFrame,
    FrameAck,
    LIVE_SAMPLE_RATE,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
)
from .live_tape import LiveSessionTapeRecorder, LiveSessionTapeStore
from .live_v2_session import (
    LiveV2SessionRegistry,
    LiveV2SessionSnapshot,
    LiveV2SessionTerminalError,
)


@dataclass(frozen=True, slots=True)
class LiveTransportCreated:
    """Authority-specific creation result consumed by the shared transport."""

    session_id: str
    authority: object
    status_code: int
    response_fields: Mapping[str, object]
    arm_helper_lease: bool = False


@dataclass(frozen=True, slots=True)
class LiveTransportSnapshotView:
    """One adapter's public projection plus fields owned by that projection."""

    visible: LiveServiceSnapshot | None
    current: LiveServiceSnapshot | None
    fields: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LiveTransportEventView:
    events: tuple[LiveServiceEvent, ...]
    fields: Mapping[str, object]


class LiveTransportAdapter(Protocol):
    """The only authority/publication facts allowed outside the shared transport."""

    async def authorize(
        self,
        request: Request,
        operation: str,
        session_id: str | None,
    ) -> object: ...

    async def create(
        self,
        payload: Mapping[str, object],
        authority: object,
    ) -> LiveTransportCreated: ...

    def snapshot(
        self,
        authority: object,
        session_id: str,
        *,
        since_version: int | None,
    ) -> LiveTransportSnapshotView: ...

    def events(
        self,
        authority: object,
        session_id: str,
        *,
        since_seq: int,
    ) -> LiveTransportEventView: ...

    async def publication(
        self,
        authority: object,
        session_id: str,
        *,
        wait_for_durability: bool,
    ) -> LiveServiceSnapshot | None: ...

    def begin_stop(self, session_id: str) -> object | None: ...

    async def stop(
        self,
        authority: object,
        session_id: str,
        deadline: float,
        intent: object | None,
    ) -> LiveServiceSnapshot: ...

    def release_stop(self, intent: object | None) -> None: ...


class _LegacyLiveTransportAdapter:
    """Legacy bearer/pairing authority over the raw runtime publication."""

    def __init__(self, runtime: LiveServiceRuntime, access: LiveAccessRegistry) -> None:
        self.runtime = runtime
        self.access = access

    async def authorize(
        self,
        request: Request,
        operation: str,
        session_id: str | None,
    ) -> object:
        return self.access.authorize(
            _peer_from_request(request),
            None if operation == "descriptor" else _bearer_from_request(request),
            operation,
            session_id,
            now=_request_now(),
        )

    async def create(
        self,
        payload: Mapping[str, object],
        authority: object,
    ) -> LiveTransportCreated:
        decision = authority
        principal = getattr(decision, "principal", None)
        if not isinstance(principal, CapturePrincipal):
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="capture authority is required.")
        created = self.runtime.create(echo_mode=payload.get("echo_mode"))
        view = self.access.bind_session(principal, created.session_id, now=_request_now())
        return LiveTransportCreated(
            session_id=created.session_id,
            authority=decision,
            status_code=200,
            response_fields={
                "owner_device_id": view.owner_device_id,
                "view_token": view.view_token,
                "view_expires_at": view.expires_at,
            },
        )

    def snapshot(
        self,
        authority: object,
        session_id: str,
        *,
        since_version: int | None,
    ) -> LiveTransportSnapshotView:
        return LiveTransportSnapshotView(
            visible=self.runtime.snapshot(session_id, since_version=since_version),
            current=self.runtime.snapshot(session_id),
            fields={},
        )

    def events(
        self,
        authority: object,
        session_id: str,
        *,
        since_seq: int,
    ) -> LiveTransportEventView:
        events, observed_monotonic_ns = self.runtime._events_with_observation(
            session_id,
            since_seq=since_seq,
        )
        return LiveTransportEventView(
            events=events,
            fields={"runtime_observed_monotonic_ns": observed_monotonic_ns},
        )

    async def publication(
        self,
        authority: object,
        session_id: str,
        *,
        wait_for_durability: bool,
    ) -> LiveServiceSnapshot | None:
        return self.runtime.snapshot(session_id)

    async def stop(
        self,
        authority: object,
        session_id: str,
        deadline: float,
        intent: object | None,
    ) -> LiveServiceSnapshot:
        del authority, intent
        return await self.runtime.stop(session_id, deadline)

    def begin_stop(self, session_id: str) -> object | None:
        del session_id
        return None

    def release_stop(self, intent: object | None) -> None:
        del intent


def attach_live_routes(
    app,
    runtime: LiveServiceRuntime,
    access: LiveAccessRegistry | None,
    *,
    live_helper_lease_seconds: float,
    tape_store: LiveSessionTapeStore | None = None,
    transport_adapter: LiveTransportAdapter | None = None,
) -> None:
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    if (access is None) == (transport_adapter is None):
        raise ValueError("provide exactly one legacy access registry or transport adapter.")
    adapter: LiveTransportAdapter = (
        _LegacyLiveTransportAdapter(runtime, access)
        if transport_adapter is None and access is not None
        else transport_adapter
    )
    assert adapter is not None

    raw_v2_sessions = LiveV2SessionRegistry(
        max_retained_samples=runtime.descriptor.bounds.max_retained_samples
    )
    capture_observations = LiveCaptureObservationRegistry()
    v2_sessions = _ObservedLiveV2SessionRegistry(raw_v2_sessions, capture_observations)
    v2_mixers = LiveCompatibilityMixerRegistry(
        max_output_samples=runtime.descriptor.bounds.max_frame_samples
    )
    # The tape's lifecycle is the mixed track's lifecycle, so it is released wherever the
    # mixer is: once the mixer is gone no further mixed audio can exist for that session,
    # and a tape kept open past it could only accumulate lanes with no mixed track.
    tapes = LiveSessionTapeRecorder(tape_store)
    helper_presence = HelperPresenceRegistry()
    helper_failures = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=live_helper_lease_seconds,
        v2_sessions=v2_sessions,
        v2_mixers=v2_mixers,
        tapes=tapes,
        helper_presence=helper_presence,
        # Terminal cleanup releases media state, but the capture owner retains the tiny
        # authorization binding needed to read the final server-authored snapshot. The stop
        # and abort routes use the same contract; view grants still expire through the runtime
        # lifecycle resolver below.
        access=None,
        abort_mono=runtime.abort,
    )
    app.state.live_v2_sessions = v2_sessions
    app.state.live_capture_observations = capture_observations
    app.state.live_v2_mixers = v2_mixers
    app.state.live_tapes = tapes
    app.state.live_helper_presence = helper_presence
    app.state.live_helper_failures = helper_failures

    async def terminal_conflict_response(
        authority: object,
        session_id: str,
        exc: Exception,
    ):
        """Keep terminal 409s as readable, typed transport failures.

        Runtime terminal failures already have the canonical code, message, and detail on
        the snapshot.  Reusing that record prevents a later frame or Stop request from
        replacing the decoder's reason with an opaque HTTP status.  A cleanly closed
        session has no runtime failure record, so retain the same envelope shape with a
        stable terminal code and the route's existing server-authored detail.
        """
        published = await adapter.publication(
            authority,
            session_id,
            wait_for_durability=False,
        )
        snapshot = None if published is None else published.to_dict()
        terminal_failure = snapshot.get("terminal_failure") if snapshot is not None else None
        if isinstance(terminal_failure, Mapping):
            failure = dict(terminal_failure)
        else:
            failure = {
                "kind": "integrity",
                "code": (
                    "v2_session_terminal"
                    if isinstance(exc, LiveV2SessionTerminalError)
                    else "live_session_terminal"
                ),
                "message": str(exc) or "live session is terminal.",
                "retryable": False,
                "detail": {"error_type": exc.__class__.__name__},
            }
        response = {
            "detail": failure["message"],
            "failure": failure,
            "snapshot": snapshot,
            "v2_session": _v2_snapshot_payload(v2_sessions, session_id),
        }
        return JSONResponse(response, status_code=409)

    # ADR-0003 D6: the service reaps, at startup too. No session exists yet, so anything
    # under the declared root belongs to a process that is gone -- which is the only moment
    # a tape left by a crash can be reached at all.
    tapes.reap()

    def _session_status(session_id: str) -> str | None:
        try:
            snapshot = runtime.snapshot(session_id)
        except KeyError:
            return None
        if snapshot is None:
            return None
        # A runtime terminal failure - a stop that fails accounting, a helper lease
        # expiry - refuses every later frame while the mono session's own status is
        # still "active". Terminal is terminal for the viewer too.
        if snapshot.terminal_failure is not None:
            return "failed"
        return snapshot.session.status

    # View authority is derived from the runtime's own session status, not mirrored from
    # it: whatever ends the session - clean stop, abort, helper lease expiry, a failed
    # stop that never reaches an explicit release - revokes the view on the next request.
    if access is not None:
        access.bind_session_lifecycle(_session_status)

    @app.get("/api/live/descriptor")
    async def live_descriptor(
        request: Request,
        client_min_protocol_version: int | None = None,
        client_max_protocol_version: int | None = None,
    ):
        try:
            await adapter.authorize(request, "descriptor", None)
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

    def issue_live_pairing(request: Request):
        assert access is not None
        try:
            grant = access.issue_pairing(_peer_from_request(request), now=_request_now())
            return {"pairing_payload": grant.pairing_payload, "expires_at": grant.expires_at}
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    async def exchange_live_pairing(request: Request):
        assert access is not None
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

    if access is not None:
        app.add_api_route(
            "/api/live/pairing-codes",
            issue_live_pairing,
            methods=["POST"],
        )
        app.add_api_route(
            "/api/live/pairings",
            exchange_live_pairing,
            methods=["POST"],
        )

    @app.post("/api/live/sessions")
    async def create_live_session(request: Request):
        try:
            authority = await adapter.authorize(request, "create", None)
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        payload = await _optional_json(request)
        try:
            created = await adapter.create(payload, authority)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        try:
            v2_sessions.create(created.session_id)
            v2_mixers.create(created.session_id)
            tapes.create(created.session_id)
            if created.arm_helper_lease:
                helper_failures.arm(created.session_id)
        except Exception:
            if access is not None:
                access.release_session(created.session_id)
            raise
        published = await adapter.publication(
            created.authority,
            created.session_id,
            wait_for_durability=False,
        )
        if published is None:
            raise HTTPException(status_code=500, detail="Live session publication failed.")
        response = {
            "id": created.session_id,
            **created.response_fields,
            "descriptor": runtime.descriptor.to_dict(),
            "snapshot": published.to_dict(),
        }
        return JSONResponse(response, status_code=created.status_code)

    @app.post("/api/live/sessions/{session_id}/frames")
    async def accept_live_frame(session_id: str, request: Request):
        authority: object | None = None
        try:
            authority = await adapter.authorize(request, "frame", session_id)
            payload = await request.json()
            frame = _frame_from_payload(payload)
            if frame.v2_frame is None:
                accepted = runtime.accept_frame(session_id, frame.audio_frame)
                result = _TransportAcceptResult(
                    ack=accepted.ack,
                    queued_item_ids=accepted.queued_item_ids,
                )
            else:
                snapshot = runtime.snapshot(session_id)
                if snapshot is None:
                    raise KeyError(session_id)
                if snapshot.session.status != "active":
                    raise LiveSessionClosed(f"live session is {snapshot.session.status}.")
                v2_session = v2_sessions.get(session_id)
                ack = v2_session.accept(frame.v2_frame)
                capture_observations.observe_accepted(session_id, frame.v2_frame)
                tapes.append_lane_frame(session_id, frame.v2_frame)
                mixed = v2_mixers.get(session_id).admit_available(
                    session_id,
                    v2_session,
                    runtime,
                    final=False,
                    retryable_backpressure=True,
                )
                _tape_mixed(tapes, session_id, mixed)
                snapshot = runtime.snapshot(session_id)
                if snapshot is None:
                    raise KeyError(session_id)
                result = _TransportAcceptResult(
                    ack=ack,
                    queued_item_ids=() if mixed is None else mixed.queued_item_ids,
                )
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            return {
                "ack": _jsonable(_ack_for_transport(result.ack, lane=frame.lane)),
                "queued_item_ids": list(result.queued_item_ids),
                "snapshot_version": 0 if published is None else published.session.version,
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
            if isinstance(exc, LiveV2OutOfOrderFrameError):
                capture_observations.observe_sequence_rejection(session_id, exc.lane)
            elif isinstance(exc, LiveV2LaneCapacityError):
                capture_observations.observe_backpressure_rejection(session_id, exc.lane)
            status, conflict = live_v2_ingress_failure_response(exc)
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            conflict["snapshot"] = None if published is None else published.to_dict()
            conflict["v2_session"] = _v2_snapshot_payload(v2_sessions, session_id)
            return JSONResponse(conflict, status_code=status)
        except (InferenceArbiterBackpressure, LiveSessionBackpressure) as exc:
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            return JSONResponse(
                {
                    "detail": str(exc),
                    "snapshot": None if published is None else published.to_dict(),
                },
                status_code=429,
            )
        except LiveSessionClosed as exc:
            return await terminal_conflict_response(authority, session_id, exc)
        except LiveV2SessionTerminalError as exc:
            return await terminal_conflict_response(authority, session_id, exc)
        except ValueError as exc:
            status_code = 409 if str(exc).startswith("expected frame sequence") else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except LiveServiceError as exc:
            status_code = _failure_status(exc)
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            return JSONResponse(
                {
                    "detail": str(exc),
                    "failure": exc.failure.to_dict(),
                    "snapshot": None if published is None else published.to_dict(),
                },
                status_code=status_code,
            )

    @app.post("/api/live/sessions/{session_id}/heartbeat")
    async def accept_live_helper_heartbeat(session_id: str, request: Request):
        try:
            await adapter.authorize(request, "heartbeat", session_id)
            heartbeat = HelperHeartbeat.from_dict(await request.json())
            presence = helper_presence.observe(session_id, heartbeat)
            await helper_failures.observe(session_id, presence)
            return JSONResponse({"helper_presence": presence.to_dict()})
        except KeyError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=404)
        except LiveAccessError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=exc.status_code)
        except HelperPresenceConflict as exc:
            return JSONResponse({"detail": str(exc)}, status_code=409)
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.get("/api/live/sessions/{session_id}/snapshot")
    async def live_snapshot(request: Request, session_id: str, since_version: int | None = None):
        try:
            authority = await adapter.authorize(request, "snapshot", session_id)
            view = adapter.snapshot(
                authority,
                session_id,
                since_version=since_version,
            )
            return _transport_snapshot_response(
                runtime=runtime,
                view=view,
                v2_sessions=v2_sessions,
                capture_observations=capture_observations,
                helper_presence=helper_presence,
                session_id=session_id,
            )
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/live/sessions/{session_id}/events")
    async def live_events(request: Request, session_id: str, since_seq: int = 0):
        try:
            authority = await adapter.authorize(request, "events", session_id)
            view = adapter.events(
                authority,
                session_id,
                since_seq=since_seq,
            )
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "events": [event.to_dict() for event in view.events],
            **view.fields,
        }

    @app.post("/api/live/sessions/{session_id}/stop")
    async def stop_live_session(session_id: str, request: Request):
        stop_intent = adapter.begin_stop(session_id)
        release_v2_on_error = False
        authority: object | None = None
        try:
            authority = await adapter.authorize(request, "stop", session_id)
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
                while v2_snapshot.status == "closing":
                    mixed = v2_mixers.get(session_id).admit_available(
                        session_id,
                        v2_session,
                        runtime,
                        final=True,
                    )
                    _tape_mixed(tapes, session_id, mixed)
                    v2_snapshot = await v2_session.stop(0.0)
                    if v2_snapshot.status != "closing" or mixed is None:
                        break
                    if loop.time() >= end_time:
                        break
                    # Each mixer call is capped at max_frame_samples. Yield between chunks
                    # so a stop cannot monopolize the service while draining a stale backlog.
                    await asyncio.sleep(0)
                if v2_snapshot.status == "closing":
                    status, failure = live_v2_unconsumed_frames_response()
                    published = await adapter.publication(
                        authority,
                        session_id,
                        wait_for_durability=False,
                    )
                    failure["snapshot"] = None if published is None else published.to_dict()
                    failure["v2_session"] = v2_snapshot.to_dict()
                    return JSONResponse(failure, status_code=status)
                if v2_snapshot.status == "failed":
                    await runtime.abort(
                        session_id,
                        v2_snapshot.terminal_reason or "v2 capture failed",
                    )
                    _release_live_capture_state(
                        session_id,
                        v2_sessions=v2_sessions,
                        v2_mixers=v2_mixers,
                        tapes=tapes,
                        helper_failures=helper_failures,
                        helper_presence=helper_presence,
                    )
                    published = await adapter.publication(
                        authority,
                        session_id,
                        wait_for_durability=True,
                    )
                    status, failure = live_v2_terminal_failure_response(v2_snapshot.terminal_reason)
                    failure["snapshot"] = None if published is None else published.to_dict()
                    failure["v2_session"] = v2_snapshot.to_dict()
                    return JSONResponse(failure, status_code=status)
                release_v2_on_error = True
            deadline = max(0.0, end_time - loop.time())
            stopped = await adapter.stop(authority, session_id, deadline, stop_intent)
            _release_live_capture_state(
                session_id,
                v2_sessions=v2_sessions,
                v2_mixers=v2_mixers,
                tapes=tapes,
                helper_failures=helper_failures,
                helper_presence=helper_presence,
            )
            release_v2_on_error = False
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=True,
            )
            response = {
                "snapshot": None if published is None else published.to_dict(),
                "raw_terminal_status": stopped.session.status,
            }
            if v2_snapshot is not None:
                response["v2_session"] = v2_snapshot.to_dict()
            return response
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        except TimeoutError as exc:
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            return JSONResponse(
                {
                    "detail": str(exc),
                    "snapshot": None if published is None else published.to_dict(),
                },
                status_code=409,
            )
        except LiveSessionBackpressure as exc:
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            return JSONResponse(
                {
                    "detail": str(exc),
                    "failure": {"code": "v2_stop_backpressure"},
                    "snapshot": None if published is None else published.to_dict(),
                    "v2_session": _v2_snapshot_payload(v2_sessions, session_id),
                },
                status_code=429,
            )
        except (LiveSessionClosed, LiveSessionFailed) as exc:
            return await terminal_conflict_response(authority, session_id, exc)
        except LiveV2SessionTerminalError as exc:
            return await terminal_conflict_response(authority, session_id, exc)
        except LiveMixIntegrityError as exc:
            status, failure = live_v2_mix_failure_response(exc)
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            failure["snapshot"] = None if published is None else published.to_dict()
            failure["v2_session"] = _v2_snapshot_payload(v2_sessions, session_id)
            if isinstance(exc, LiveMixSourceMissingError):
                v2_mixers.release(session_id)
                tapes.release(session_id)
            return JSONResponse(failure, status_code=status)
        except LiveServiceError as exc:
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=False,
            )
            return JSONResponse(
                {
                    "detail": str(exc),
                    "failure": exc.failure.to_dict(),
                    "snapshot": None if published is None else published.to_dict(),
                },
                status_code=_failure_status(exc),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            adapter.release_stop(stop_intent)
            if release_v2_on_error:
                _release_live_capture_state(
                    session_id,
                    v2_sessions=v2_sessions,
                    v2_mixers=v2_mixers,
                    tapes=tapes,
                    helper_failures=helper_failures,
                    helper_presence=helper_presence,
                )

    @app.post("/api/live/sessions/{session_id}/abort")
    async def abort_live_session(session_id: str, request: Request):
        try:
            authority = await adapter.authorize(request, "abort", session_id)
            payload = await _optional_json(request)
            reason = str(payload.get("reason") or "aborted")
            await runtime.abort(session_id, reason)
            try:
                v2_session = v2_sessions.get(session_id)
            except KeyError:
                v2_session = None
            if v2_session is not None:
                try:
                    v2_session.abort(reason)
                except LiveV2SessionTerminalError:
                    pass
            _release_live_capture_state(
                session_id,
                v2_sessions=v2_sessions,
                v2_mixers=v2_mixers,
                tapes=tapes,
                helper_failures=helper_failures,
                helper_presence=helper_presence,
            )
            published = await adapter.publication(
                authority,
                session_id,
                wait_for_durability=True,
            )
            return {"snapshot": None if published is None else published.to_dict()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    def revoke_live_view(request: Request, session_id: str):
        assert access is not None
        try:
            revoked = access.revoke_view(_peer_from_request(request), session_id, now=_request_now())
        except LiveAccessError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
        if not revoked:
            raise HTTPException(status_code=404, detail="no live view authority for this session.")
        return {"session_id": session_id, "view_revoked": True}

    async def revoke_live_device(request: Request, device_id: str):
        assert access is not None
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
            _release_live_capture_state(
                session_id,
                v2_sessions=v2_sessions,
                v2_mixers=v2_mixers,
                tapes=tapes,
                helper_failures=helper_failures,
                helper_presence=helper_presence,
            )
            access.release_session(session_id)
        return {"device_id": revoked.device_id, "session_ids": list(revoked.session_ids)}

    if access is not None:
        app.add_api_route(
            "/api/live/sessions/{session_id}/view",
            revoke_live_view,
            methods=["DELETE"],
        )
        app.add_api_route(
            "/api/live/devices/{device_id}",
            revoke_live_device,
            methods=["DELETE"],
        )


@dataclass(frozen=True, slots=True)
class _TransportFrame:
    audio_frame: AudioFrame
    lane: LiveLane | None = None
    v2_frame: LiveV2Frame | None = None


@dataclass(frozen=True, slots=True)
class _TransportAcceptResult:
    ack: FrameAck | LiveV2Ack
    queued_item_ids: tuple[int, ...]


def _tape_mixed(
    tapes: LiveSessionTapeRecorder,
    session_id: str,
    mixed: LiveMixResult | None,
) -> None:
    """Tee one sealed mixer commit, from the two places that produce one.

    The start timestamp comes from the mixer's own diagnostics, not from the frame: the
    frame carries a runtime *sequence*, and only the diagnostics say where in wall-clock
    time this interval begins -- which is the whole basis on which the tape places it.
    """

    if mixed is None:
        return
    tapes.append_mixed(
        session_id,
        pcm=mixed.frame.pcm,
        start_timestamp_ns=mixed.diagnostics.start_timestamp_ns,
        sample_count=mixed.frame.sample_count,
        sample_rate=mixed.frame.sample_rate,
    )


def _release_live_capture_state(
    session_id: str,
    *,
    v2_sessions: Any,
    v2_mixers: Any,
    tapes: Any,
    helper_failures: Any,
    helper_presence: Any,
) -> None:
    """Release the five capture registries as one shared lifecycle operation."""

    for release in (
        v2_sessions.release,
        v2_mixers.release,
        tapes.release,
        helper_failures.release,
        helper_presence.release,
    ):
        try:
            release(session_id)
        except KeyError:
            pass


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
    payload = {
        "descriptor": runtime.descriptor.to_dict(),
        # A pre-session condition has no authenticated session route yet. The browser still
        # gets this server-owned copy from the descriptor it must fetch before capture.
        "preflight_status_lines": {
            "browser_microphone_silent": BROWSER_MICROPHONE_SILENT_STATUS_LINE,
        },
    }
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


def _transport_snapshot_response(
    *,
    runtime: LiveServiceRuntime,
    view: LiveTransportSnapshotView,
    v2_sessions: "_ObservedLiveV2SessionRegistry",
    capture_observations: LiveCaptureObservationRegistry,
    helper_presence: HelperPresenceRegistry,
    session_id: str,
) -> dict[str, Any]:
    # The capture judgment is read from the session as it *is*, then the caller's cursor is
    # applied to the transported snapshot. Deriving the terminal reason from the cursor-gated
    # result instead loses it on the very next poll: the portal polls
    # `/snapshot?since_version=<version>` (live_portal.py) and, once teardown has released
    # helper presence, a cursor-suppressed snapshot left the projection with no facts at all
    # and it answered "starting" / "Waiting for audio capture to start." for a session that
    # had already died. One terminal read followed by silence is not a readable reason.
    terminal_session_status, terminal_lane_failures = _terminal_capture_facts(view.current)
    presence = helper_presence.snapshot(session_id)
    v2_session = _v2_snapshot(v2_sessions, session_id)
    observations = _capture_observation_snapshot(capture_observations, session_id)
    return {
        "snapshot": None if view.visible is None else view.visible.to_dict(),
        "unchanged": view.visible is None,
        "v2_session": None if v2_session is None else v2_session.to_dict(),
        "helper_presence": None if presence is None else presence.to_dict(),
        **view.fields,
        **project_live_capture_status(
            presence,
            v2_session=v2_session,
            observations=observations,
            policy=LiveCaptureHealthPolicy(
                frame_samples=runtime.descriptor.frame_samples,
                sample_rate=runtime.descriptor.sample_rate,
            ),
            terminal_session_status=terminal_session_status,
            terminal_lane_failures=terminal_lane_failures,
        ).to_dict(),
    }


def _terminal_capture_facts(
    snapshot: Any,
) -> tuple[str | None, Mapping[str, str] | None]:
    if snapshot is None:
        return None, None
    terminal_failure = snapshot.terminal_failure
    if terminal_failure is not None:
        detail = terminal_failure.detail
        lane_failures = detail.get("lane_failures") if isinstance(detail, Mapping) else None
        if isinstance(lane_failures, Mapping):
            return (
                "failed",
                {
                    str(lane): code
                    for lane, code in lane_failures.items()
                    if isinstance(lane, str) and isinstance(code, str) and code
                },
            )
        return "failed", None
    if snapshot.session.status in {"closed", "aborted", "failed"}:
        return snapshot.session.status, None
    return None, None


def _v2_snapshot_payload(
    v2_sessions: "_ObservedLiveV2SessionRegistry",
    session_id: str,
) -> dict[str, Any] | None:
    snapshot = _v2_snapshot(v2_sessions, session_id)
    return None if snapshot is None else snapshot.to_dict()


def _v2_snapshot(
    v2_sessions: "_ObservedLiveV2SessionRegistry",
    session_id: str,
) -> LiveV2SessionSnapshot | None:
    try:
        return v2_sessions.get(session_id).snapshot()
    except KeyError:
        return None


def _capture_observation_snapshot(
    capture_observations: LiveCaptureObservationRegistry,
    session_id: str,
):
    try:
        return capture_observations.snapshot(session_id)
    except KeyError:
        return None


class _ObservedLiveV2SessionRegistry:
    """Pair v2-session lifetime with capture-health observation lifetime."""

    def __init__(
        self,
        sessions: LiveV2SessionRegistry,
        observations: LiveCaptureObservationRegistry,
    ) -> None:
        self._sessions = sessions
        self._observations = observations

    def __contains__(self, session_id: object) -> bool:
        return session_id in self._sessions

    def contains(self, session_id: str) -> bool:
        return self._sessions.contains(session_id)

    def create(self, session_id: str):
        session = self._sessions.create(session_id)
        try:
            self._observations.create(session_id)
        except Exception:
            self._sessions.release(session_id)
            raise
        return session

    def get(self, session_id: str):
        return self._sessions.get(session_id)

    def release(self, session_id: str):
        session = self._sessions.release(session_id)
        self._observations.release(session_id)
        return session

    def expire(self, session_id: str, reason: str, *, lane_failure_codes=None):
        snapshot = self._sessions.expire(
            session_id,
            reason,
            lane_failure_codes=lane_failure_codes,
        )
        self._observations.release(session_id)
        return snapshot


def _failure_status(exc: LiveServiceError) -> int:
    if exc.failure.kind == LiveServiceFailureKind.TRANSPORT_PACING:
        return 429 if exc.failure.retryable else 409
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
