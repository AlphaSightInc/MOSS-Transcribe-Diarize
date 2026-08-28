"""Account-owned Phase-2 transport over the settled LiveServiceRuntime.

The runtime is raw inference state. This module is the publication boundary: one serialized
worker per Meeting commits each changed structured transcript through its captured MeetingHandle,
then and only then advances the memory-backed snapshot/event projection read by browsers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any

from starlette.requests import Request

from moss_transcribe_diarize.live_surface import published_speaker_label

from .live_arbiter import InferenceArbiterBackpressure
from .live_capture_status import (
    BROWSER_MICROPHONE_SILENT_STATUS_LINE,
    LiveCaptureHealthPolicy,
    LiveCaptureObservationRegistry,
    project_live_capture_status,
)
from .live_helper_failure import LiveHelperFailureCoordinator
from .live_helper_presence import HelperHeartbeat, HelperPresenceConflict, HelperPresenceRegistry
from .live_ingest import (
    LiveV2EpochDiscontinuityRequiredError,
    LiveV2LaneCapacityError,
    LiveV2StaleDeviceEpochError,
)
from .live_lane_contract import (
    LiveV2ObsoleteClientError,
    LiveV2OutOfOrderFrameError,
    LiveV2PrunedReplayError,
)
from .live_mixer import (
    LiveCompatibilityMixerRegistry,
    LiveMixIntegrityError,
    LiveMixSourceMissingError,
)
from .live_service_runtime import (
    LIVE_TERMINAL_SESSION_STATUSES,
    LiveServiceError,
    LiveServiceEvent,
    LiveServiceRuntime,
    LiveServiceSnapshot,
)
from .live_session import LiveSessionBackpressure, LiveSessionClosed, LiveSessionFailed
from .live_tape import LiveSessionTapeRecorder
from .live_transport import (
    _ObservedLiveV2SessionRegistry,
    _TransportAcceptResult,
    _ack_for_transport,
    _capture_observation_snapshot,
    _descriptor_payload,
    _failure_status,
    _frame_from_payload,
    _jsonable,
    _optional_json,
    _tape_mixed,
    _terminal_capture_facts,
    _v2_snapshot,
    _v2_snapshot_payload,
    live_v2_ingress_failure_response,
    live_v2_mix_failure_response,
    live_v2_obsolete_client_response,
    live_v2_terminal_failure_response,
    live_v2_unconsumed_frames_response,
)
from .live_v2_session import LiveV2SessionRegistry, LiveV2SessionTerminalError
from .phase2 import Account, AccountRevoked


class LiveMeetingNotFound(KeyError):
    pass


class LiveMeetingReadOnly(PermissionError):
    pass


class LiveMeetingTerminal(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class _RawPublication:
    snapshot: LiveServiceSnapshot
    events: tuple[LiveServiceEvent, ...]

    @property
    def event_high_water(self) -> int:
        return -1 if not self.events else self.events[-1].seq


@dataclass(slots=True)
class _LiveBinding:
    owner_key: tuple[str, int]
    origin_session: str
    handle: Any
    queue: asyncio.Queue[_RawPublication | None]
    public_snapshot: LiveServiceSnapshot | None = None
    public_events: tuple[LiveServiceEvent, ...] = ()
    durable_document: dict[str, object] = field(default_factory=lambda: {"segments": []})
    durable_version: int = 0
    public_event_high_water: int = -1
    raw_event_high_water: int = -1
    terminal_persisted: bool = False
    capture_fenced: bool = False
    persistence_failure: str | None = None
    worker: asyncio.Task[None] | None = None
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)


class Phase2LiveMeetings:
    """Account-partitioned transient registry plus durable publication bridge."""

    def __init__(self, runtime: LiveServiceRuntime):
        self.runtime = runtime
        self._bindings: dict[str, _LiveBinding] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.runtime._bind_publication_observer(self._observe_raw)

    async def shutdown(self) -> None:
        for meeting_id, binding in tuple(self._bindings.items()):
            if not binding.terminal_persisted and not binding.capture_fenced:
                try:
                    await self.runtime.abort(meeting_id, "service shutdown")
                    await self.sync_and_flush(meeting_id)
                except Exception:
                    binding.capture_fenced = True
            binding.queue.put_nowait(None)
        workers = tuple(
            binding.worker for binding in self._bindings.values() if binding.worker is not None
        )
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

    async def create(
        self,
        *,
        account: Account,
        workspace: Any,
        origin_session: str,
        echo_mode: str | None,
    ) -> _LiveBinding:
        handle = await workspace.create_meeting("live")
        binding = _LiveBinding(
            owner_key=(account.account_id, account.authority_generation),
            origin_session=origin_session,
            handle=handle,
            queue=asyncio.Queue(),
        )
        binding.worker = asyncio.create_task(
            self._publish(binding), name=f"phase2-live-publish-{handle.meeting_id}"
        )
        self._bindings[handle.meeting_id] = binding
        try:
            self.runtime.create(echo_mode=echo_mode, session_id=handle.meeting_id)
            await self.sync_and_flush(handle.meeting_id)
        except BaseException:
            self._bindings.pop(handle.meeting_id, None)
            binding.queue.put_nowait(None)
            if binding.worker is not None:
                await binding.worker
            try:
                await handle.finish("failed")
            except Exception:
                pass
            raise
        return binding

    def open(
        self,
        account: Account,
        session_id: str,
        meeting_id: str,
        *,
        mutation: bool,
    ) -> _LiveBinding:
        binding = self._bindings.get(meeting_id)
        if binding is None or binding.owner_key != (
            account.account_id,
            account.authority_generation,
        ):
            raise LiveMeetingNotFound(meeting_id)
        if mutation and session_id != binding.origin_session:
            raise LiveMeetingReadOnly("active Meeting observers are read-only.")
        if mutation and (
            binding.capture_fenced
            or binding.terminal_persisted
            or (
                binding.public_snapshot is not None
                and binding.public_snapshot.session.status != "active"
            )
        ):
            raise LiveMeetingTerminal("live Meeting is terminal.")
        return binding

    async def sync_and_flush(self, meeting_id: str) -> _LiveBinding:
        binding = self._bindings[meeting_id]
        snapshot = self.runtime.snapshot(meeting_id)
        if snapshot is None:
            raise KeyError(meeting_id)
        events = self.runtime.events(meeting_id)
        self._accept_raw(meeting_id, snapshot, events)
        target = -1 if not events else events[-1].seq
        async with binding.changed:
            await binding.changed.wait_for(
                lambda: binding.public_event_high_water >= target or binding.capture_fenced
            )
        return binding

    def snapshot(
        self,
        binding: _LiveBinding,
        *,
        since_version: int | None = None,
    ) -> LiveServiceSnapshot | None:
        snapshot = binding.public_snapshot
        if snapshot is None:
            return None
        terminal = (
            snapshot.terminal_failure is not None
            or snapshot.session.status in LIVE_TERMINAL_SESSION_STATUSES
            or binding.capture_fenced
        )
        if (
            since_version is not None
            and snapshot.session.version <= since_version
            and not terminal
        ):
            return None
        return snapshot

    def events(self, binding: _LiveBinding, since_seq: int) -> tuple[LiveServiceEvent, ...]:
        if since_seq < -1:
            raise ValueError("since_seq must be at least -1.")
        return tuple(event for event in binding.public_events if event.seq >= since_seq)

    def _observe_raw(
        self,
        meeting_id: str,
        snapshot: LiveServiceSnapshot,
        events: tuple[LiveServiceEvent, ...],
    ) -> None:
        loop = self._loop
        if loop is None:
            raise RuntimeError("Phase-2 Live publication bridge is not started.")
        loop.call_soon_threadsafe(self._accept_raw, meeting_id, snapshot, events)

    def _accept_raw(
        self,
        meeting_id: str,
        snapshot: LiveServiceSnapshot,
        events: tuple[LiveServiceEvent, ...],
    ) -> None:
        binding = self._bindings.get(meeting_id)
        if binding is None:
            return
        high_water = -1 if not events else events[-1].seq
        if high_water <= binding.raw_event_high_water:
            return
        binding.raw_event_high_water = high_water
        binding.queue.put_nowait(_RawPublication(snapshot=snapshot, events=events))

    async def _publish(self, binding: _LiveBinding) -> None:
        while True:
            publication = await binding.queue.get()
            if publication is None:
                return
            if binding.capture_fenced:
                continue
            document = _transcript_document(publication.snapshot)
            try:
                terminal = _durable_terminal_status(publication.snapshot)
                document_changed = document != binding.durable_document
                if terminal is not None and not binding.terminal_persisted:
                    if document_changed:
                        binding.durable_version = await binding.handle.finish_with_transcript(
                            document,
                            terminal,
                        )
                        binding.durable_document = document
                    else:
                        await binding.handle.finish(terminal)
                    binding.terminal_persisted = True
                elif document_changed:
                    binding.durable_version = await binding.handle.commit_transcript(document)
                    binding.durable_document = document
            except AccountRevoked:
                await self._fence(binding, "meeting_authority_revoked")
                continue
            except Exception:
                await self._fence(binding, "transcript_persistence_failed")
                continue

            binding.public_snapshot = publication.snapshot
            binding.public_events = publication.events
            binding.public_event_high_water = publication.event_high_water
            async with binding.changed:
                binding.changed.notify_all()

    async def _fence(self, binding: _LiveBinding, reason: str) -> None:
        if binding.capture_fenced:
            return
        binding.capture_fenced = True
        binding.persistence_failure = reason
        terminal_snapshot = None
        terminal_events: tuple[LiveServiceEvent, ...] = ()
        try:
            terminal_snapshot = await self.runtime.abort(binding.handle.meeting_id, reason)
            terminal_events = self.runtime.events(binding.handle.meeting_id)
        except Exception:
            pass
        durable_interruption = False
        try:
            await binding.handle.finish("interrupted")
            binding.terminal_persisted = True
            durable_interruption = True
        except AccountRevoked:
            # Account revocation atomically interrupts all active Meetings before the
            # captured handle's generation fence rejects this redundant finish.
            binding.terminal_persisted = True
            durable_interruption = True
        except Exception:
            pass
        if durable_interruption and terminal_snapshot is not None:
            binding.public_snapshot = _durable_terminal_projection(binding, terminal_snapshot)
            new_terminal_events = tuple(
                event
                for event in terminal_events
                if event.seq > binding.public_event_high_water
                and event.kind in {"session_aborted", "terminal_failure", "session_tape_released"}
            )
            binding.public_events = binding.public_events + new_terminal_events
            if new_terminal_events:
                binding.public_event_high_water = new_terminal_events[-1].seq
        async with binding.changed:
            binding.changed.notify_all()


def attach_phase2_live_routes(
    app: Any,
    live: Phase2LiveMeetings,
    *,
    require_account: Any,
    live_helper_lease_seconds: float,
) -> None:
    """Attach only Account-cookie Live routes; no bearer/pairing/view authority exists."""

    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    if live_helper_lease_seconds <= 0:
        raise ValueError("live_helper_lease_seconds must be positive.")
    runtime = live.runtime
    raw_v2_sessions = LiveV2SessionRegistry(
        max_retained_samples=runtime.descriptor.bounds.max_retained_samples
    )
    capture_observations = LiveCaptureObservationRegistry()
    v2_sessions = _ObservedLiveV2SessionRegistry(raw_v2_sessions, capture_observations)
    v2_mixers = LiveCompatibilityMixerRegistry(
        max_output_samples=runtime.descriptor.bounds.max_frame_samples
    )
    tapes = LiveSessionTapeRecorder(None)
    helper_presence = HelperPresenceRegistry()
    helper_failures = LiveHelperFailureCoordinator(
        live_helper_lease_seconds=live_helper_lease_seconds,
        v2_sessions=v2_sessions,
        v2_mixers=v2_mixers,
        tapes=tapes,
        helper_presence=helper_presence,
        access=None,
        abort_mono=runtime.abort,
    )
    app.state.phase2_live = live
    app.state.live_v2_sessions = v2_sessions
    app.state.live_capture_observations = capture_observations
    app.state.live_v2_mixers = v2_mixers
    app.state.live_tapes = tapes
    app.state.live_helper_presence = helper_presence
    app.state.live_helper_failures = helper_failures
    tapes.reap()

    async def authorize(request: Request, meeting_id: str, *, mutation: bool) -> _LiveBinding:
        account = await require_account(request)
        session_id = request.cookies.get("__Host-moss_session")
        try:
            return live.open(account, session_id or "", meeting_id, mutation=mutation)
        except LiveMeetingNotFound as exc:
            raise HTTPException(status_code=404, detail="Live Meeting not found.") from exc
        except LiveMeetingReadOnly as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LiveMeetingTerminal as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/live/descriptor")
    async def live_descriptor(
        request: Request,
        client_min_protocol_version: int | None = None,
        client_max_protocol_version: int | None = None,
    ):
        await require_account(request)
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

    @app.post("/api/live/sessions", status_code=201)
    async def create_live_session(request: Request):
        account = await require_account(request)
        payload = await _optional_json(request)
        session_id = request.cookies.get("__Host-moss_session")
        if not session_id:
            raise HTTPException(status_code=401, detail="Sign in required.")
        try:
            binding = await live.create(
                account=account,
                workspace=request.app.state.phase2_store.workspace(account),
                origin_session=session_id,
                echo_mode=payload.get("echo_mode"),
            )
            v2_sessions.create(binding.handle.meeting_id)
            v2_mixers.create(binding.handle.meeting_id)
            tapes.create(binding.handle.meeting_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        snapshot = binding.public_snapshot
        if snapshot is None:
            raise HTTPException(status_code=500, detail="Live Meeting publication failed.")
        return {
            "id": binding.handle.meeting_id,
            "descriptor": runtime.descriptor.to_dict(),
            "snapshot": snapshot.to_dict(),
        }

    @app.post("/api/live/sessions/{meeting_id}/frames")
    async def accept_live_frame(meeting_id: str, request: Request):
        binding = await authorize(request, meeting_id, mutation=True)
        try:
            payload = await request.json()
            frame = _frame_from_payload(payload)
            if frame.v2_frame is None:
                accepted = runtime.accept_frame(meeting_id, frame.audio_frame)
                result = _TransportAcceptResult(
                    ack=accepted.ack,
                    queued_item_ids=accepted.queued_item_ids,
                    snapshot_version=(
                        0
                        if binding.public_snapshot is None
                        else binding.public_snapshot.session.version
                    ),
                )
            else:
                raw = runtime.snapshot(meeting_id)
                if raw is None:
                    raise KeyError(meeting_id)
                if raw.session.status != "active":
                    raise LiveSessionClosed(f"live session is {raw.session.status}.")
                v2_session = v2_sessions.get(meeting_id)
                ack = v2_session.accept(frame.v2_frame)
                capture_observations.observe_accepted(meeting_id, frame.v2_frame)
                tapes.append_lane_frame(meeting_id, frame.v2_frame)
                mixed = v2_mixers.get(meeting_id).admit_available(
                    meeting_id,
                    v2_session,
                    runtime,
                    final=False,
                    retryable_backpressure=True,
                )
                _tape_mixed(tapes, meeting_id, mixed)
                result = _TransportAcceptResult(
                    ack=ack,
                    queued_item_ids=() if mixed is None else mixed.queued_item_ids,
                    snapshot_version=(
                        0
                        if binding.public_snapshot is None
                        else binding.public_snapshot.session.version
                    ),
                )
            return {
                "ack": _jsonable(_ack_for_transport(result.ack, lane=frame.lane)),
                "queued_item_ids": list(result.queued_item_ids),
                "snapshot_version": result.snapshot_version,
            }
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Live Meeting not found.") from exc
        except (
            LiveV2EpochDiscontinuityRequiredError,
            LiveV2LaneCapacityError,
            LiveV2OutOfOrderFrameError,
            LiveV2PrunedReplayError,
            LiveV2StaleDeviceEpochError,
        ) as exc:
            if isinstance(exc, LiveV2OutOfOrderFrameError):
                capture_observations.observe_sequence_rejection(meeting_id, exc.lane)
            elif isinstance(exc, LiveV2LaneCapacityError):
                capture_observations.observe_backpressure_rejection(meeting_id, exc.lane)
            status, conflict = live_v2_ingress_failure_response(exc)
            conflict["snapshot"] = _public_snapshot_payload(binding)
            conflict["v2_session"] = _v2_snapshot_payload(v2_sessions, meeting_id)
            return JSONResponse(conflict, status_code=status)
        except (InferenceArbiterBackpressure, LiveSessionBackpressure) as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _public_snapshot_payload(binding)},
                status_code=429,
            )
        except (LiveSessionClosed, LiveV2SessionTerminalError) as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _public_snapshot_payload(binding)},
                status_code=409,
            )
        except ValueError as exc:
            status_code = 409 if str(exc).startswith("expected frame sequence") else 400
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except LiveServiceError as exc:
            return JSONResponse(
                {
                    "detail": str(exc),
                    "failure": exc.failure.to_dict(),
                    "snapshot": _public_snapshot_payload(binding),
                },
                status_code=_failure_status(exc),
            )

    @app.post("/api/live/sessions/{meeting_id}/heartbeat")
    async def accept_live_helper_heartbeat(meeting_id: str, request: Request):
        await authorize(request, meeting_id, mutation=True)
        try:
            heartbeat = HelperHeartbeat.from_dict(await request.json())
            presence = helper_presence.observe(meeting_id, heartbeat)
            await helper_failures.observe(meeting_id, presence)
            return {"helper_presence": presence.to_dict()}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Live Meeting not found.") from exc
        except HelperPresenceConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/live/sessions/{meeting_id}/snapshot")
    async def live_snapshot(
        meeting_id: str,
        request: Request,
        since_version: int | None = None,
    ):
        binding = await authorize(request, meeting_id, mutation=False)
        public = live.snapshot(binding, since_version=since_version)
        current = binding.public_snapshot
        terminal_status, terminal_lane_failures = _terminal_capture_facts(current)
        presence = helper_presence.snapshot(meeting_id)
        v2_session = _v2_snapshot(v2_sessions, meeting_id)
        observations = _capture_observation_snapshot(capture_observations, meeting_id)
        return {
            "snapshot": None if public is None else public.to_dict(),
            "unchanged": public is None,
            "v2_session": None if v2_session is None else v2_session.to_dict(),
            "helper_presence": None if presence is None else presence.to_dict(),
            "meeting_transcript_version": _meeting_transcript_version(binding),
            "persistence_failure": binding.persistence_failure,
            **project_live_capture_status(
                presence,
                v2_session=v2_session,
                observations=observations,
                policy=LiveCaptureHealthPolicy(
                    frame_samples=runtime.descriptor.frame_samples,
                    sample_rate=runtime.descriptor.sample_rate,
                ),
                terminal_session_status=terminal_status,
                terminal_lane_failures=terminal_lane_failures,
            ).to_dict(),
        }

    @app.get("/api/live/sessions/{meeting_id}/events")
    async def live_events(meeting_id: str, request: Request, since_seq: int = 0):
        binding = await authorize(request, meeting_id, mutation=False)
        try:
            events = live.events(binding, since_seq)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"events": [event.to_dict() for event in events]}

    @app.post("/api/live/sessions/{meeting_id}/stop")
    async def stop_live_session(meeting_id: str, request: Request):
        binding = await authorize(request, meeting_id, mutation=True)
        release_v2_on_error = False
        try:
            payload = await _optional_json(request)
            deadline = float(payload.get("deadline", 0.0))
            loop = asyncio.get_running_loop()
            end_time = loop.time() + max(0.0, deadline)
            try:
                v2_session = v2_sessions.get(meeting_id)
            except KeyError:
                v2_session = None
            v2_snapshot = None
            if v2_session is not None:
                v2_snapshot = await v2_session.stop(0.0)
                while v2_snapshot.status == "closing":
                    mixed = v2_mixers.get(meeting_id).admit_available(
                        meeting_id, v2_session, runtime, final=True
                    )
                    _tape_mixed(tapes, meeting_id, mixed)
                    v2_snapshot = await v2_session.stop(0.0)
                    if v2_snapshot.status != "closing" or mixed is None:
                        break
                    if loop.time() >= end_time:
                        break
                    await asyncio.sleep(0)
                if v2_snapshot.status == "closing":
                    status, failure = live_v2_unconsumed_frames_response()
                    failure["snapshot"] = _public_snapshot_payload(binding)
                    failure["v2_session"] = v2_snapshot.to_dict()
                    return JSONResponse(failure, status_code=status)
                if v2_snapshot.status == "failed":
                    await runtime.abort(
                        meeting_id, v2_snapshot.terminal_reason or "v2 capture failed"
                    )
                    _release_capture_state(
                        meeting_id,
                        v2_sessions,
                        v2_mixers,
                        tapes,
                        helper_failures,
                        helper_presence,
                    )
                    await live.sync_and_flush(meeting_id)
                    status, failure = live_v2_terminal_failure_response(
                        v2_snapshot.terminal_reason
                    )
                    failure["snapshot"] = _public_snapshot_payload(binding)
                    failure["v2_session"] = v2_snapshot.to_dict()
                    return JSONResponse(failure, status_code=status)
                release_v2_on_error = True
            stopped = await runtime.stop(meeting_id, max(0.0, end_time - loop.time()))
            _release_capture_state(
                meeting_id,
                v2_sessions,
                v2_mixers,
                tapes,
                helper_failures,
                helper_presence,
            )
            release_v2_on_error = False
            binding = await live.sync_and_flush(meeting_id)
            response: dict[str, object] = {
                "snapshot": _public_snapshot_payload(binding),
                "raw_terminal_status": stopped.session.status,
            }
            if v2_snapshot is not None:
                response["v2_session"] = v2_snapshot.to_dict()
            return response
        except TimeoutError as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _public_snapshot_payload(binding)},
                status_code=409,
            )
        except LiveSessionBackpressure as exc:
            return JSONResponse(
                {
                    "detail": str(exc),
                    "failure": {"code": "v2_stop_backpressure"},
                    "snapshot": _public_snapshot_payload(binding),
                    "v2_session": _v2_snapshot_payload(v2_sessions, meeting_id),
                },
                status_code=429,
            )
        except (LiveSessionClosed, LiveSessionFailed, LiveV2SessionTerminalError) as exc:
            return JSONResponse(
                {"detail": str(exc), "snapshot": _public_snapshot_payload(binding)},
                status_code=409,
            )
        except LiveMixIntegrityError as exc:
            status, failure = live_v2_mix_failure_response(exc)
            failure["snapshot"] = _public_snapshot_payload(binding)
            failure["v2_session"] = _v2_snapshot_payload(v2_sessions, meeting_id)
            if isinstance(exc, LiveMixSourceMissingError):
                v2_mixers.release(meeting_id)
                tapes.release(meeting_id)
            return JSONResponse(failure, status_code=status)
        except LiveServiceError as exc:
            return JSONResponse(
                {
                    "detail": str(exc),
                    "failure": exc.failure.to_dict(),
                    "snapshot": _public_snapshot_payload(binding),
                },
                status_code=_failure_status(exc),
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            if release_v2_on_error:
                _release_capture_state(
                    meeting_id,
                    v2_sessions,
                    v2_mixers,
                    tapes,
                    helper_failures,
                    helper_presence,
                )

    @app.post("/api/live/sessions/{meeting_id}/abort")
    async def abort_live_session(meeting_id: str, request: Request):
        binding = await authorize(request, meeting_id, mutation=True)
        payload = await _optional_json(request)
        reason = str(payload.get("reason") or "aborted")
        try:
            await runtime.abort(meeting_id, reason)
            try:
                v2_session = v2_sessions.get(meeting_id)
            except KeyError:
                v2_session = None
            if v2_session is not None:
                try:
                    v2_session.abort(reason)
                except LiveV2SessionTerminalError:
                    pass
            _release_capture_state(
                meeting_id,
                v2_sessions,
                v2_mixers,
                tapes,
                helper_failures,
                helper_presence,
            )
            binding = await live.sync_and_flush(meeting_id)
            return {"snapshot": _public_snapshot_payload(binding)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Live Meeting not found.") from exc


def _transcript_document(snapshot: LiveServiceSnapshot) -> dict[str, object]:
    canonical = snapshot.session.identity_snapshot.canonical_speakers
    sample_rate = snapshot.descriptor.sample_rate
    return {
        "segments": [
            {
                "id": f"seg_{index:04d}",
                "start": segment.start_sample / sample_rate,
                "end": segment.end_sample / sample_rate,
                "speaker": published_speaker_label(segment.canonical_speaker, canonical),
                "text": segment.text,
            }
            for index, segment in enumerate(snapshot.session.effective_transcript, start=1)
        ]
    }


def _durable_terminal_status(snapshot: LiveServiceSnapshot) -> str | None:
    if snapshot.terminal_failure is not None or snapshot.session.status in {"aborted", "failed"}:
        return "interrupted"
    if (
        snapshot.session.status == "closed"
        and snapshot.session.finalization_status != "running"
    ):
        return "completed"
    return None


def _meeting_transcript_version(binding: _LiveBinding) -> int:
    return binding.durable_version


def _durable_terminal_projection(
    binding: _LiveBinding,
    terminal: LiveServiceSnapshot,
) -> LiveServiceSnapshot:
    """Overlay only terminal facts onto the last durable public transcript surface."""

    prior = binding.public_snapshot
    if prior is None:
        session = replace(
            terminal.session,
            committed_samples=0,
            committed=(),
            provisional=None,
            label_revision_version=0,
            text_revision_version=0,
            canonical_through_sample=0,
            effective_transcript=(),
        )
        return replace(terminal, session=session, pending_work_items=0)
    session = replace(
        prior.session,
        status=terminal.session.status,
        failure_reason=terminal.session.failure_reason,
        finalization_status=terminal.session.finalization_status,
    )
    return replace(
        prior,
        session=session,
        pending_work_items=0,
        terminal_failure=terminal.terminal_failure,
    )


def _public_snapshot_payload(binding: _LiveBinding) -> dict[str, Any] | None:
    return None if binding.public_snapshot is None else binding.public_snapshot.to_dict()


def _release_capture_state(
    meeting_id: str,
    v2_sessions: Any,
    v2_mixers: Any,
    tapes: Any,
    helper_failures: Any,
    helper_presence: Any,
) -> None:
    for release in (
        v2_sessions.release,
        v2_mixers.release,
        tapes.release,
        helper_failures.release,
        helper_presence.release,
    ):
        try:
            release(meeting_id)
        except KeyError:
            pass


__all__ = ["Phase2LiveMeetings", "attach_phase2_live_routes"]
