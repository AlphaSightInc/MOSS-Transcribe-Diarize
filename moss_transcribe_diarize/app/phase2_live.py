"""Account-owned Phase-2 transport over the settled LiveServiceRuntime.

The runtime is raw inference state. This module is the publication boundary: one serialized
worker per Meeting commits each changed structured transcript through its captured MeetingHandle,
then and only then advances the memory-backed snapshot/event projection read by browsers.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from starlette.requests import Request

from moss_transcribe_diarize.live_surface import published_speaker_label

from .live_service_runtime import (
    LIVE_TERMINAL_SESSION_STATUSES,
    LiveServiceEvent,
    LiveServiceRuntime,
    LiveServiceSnapshot,
)
from .live_transport import (
    LiveTransportCreated,
    LiveTransportEventView,
    LiveTransportSnapshotView,
    attach_live_routes,
)
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
    authority_cleanup_task: asyncio.Task[None] | None = None
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)


class Phase2LiveMeetings:
    """Account-partitioned transient registry plus durable publication bridge."""

    def __init__(
        self,
        runtime: LiveServiceRuntime,
        *,
        audio_archive: Any,
        audio_stages: Any,
    ):
        self.runtime = runtime
        self.audio_archive = audio_archive
        self.audio_stages = audio_stages
        self._bindings: dict[str, _LiveBinding] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._accepting_publications = False
        self._publication_observer = self._observe_raw

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._accepting_publications = True
        self.runtime._bind_publication_observer(self._publication_observer)

    async def shutdown(self) -> None:
        for binding in tuple(self._bindings.values()):
            if not binding.terminal_persisted:
                await self._fence(binding, "service shutdown")
        self.runtime._unbind_publication_observer(self._publication_observer)
        self._accepting_publications = False
        self._loop = None
        for binding in self._bindings.values():
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
        try:
            # This single pre-capture fsync uses the same measured local stage seam as
            # frame appends and cannot outlive a cancelled creation task in a worker.
            self.audio_stages.reserve(account.account_id, handle.meeting_id)
        except BaseException:
            try:
                self.audio_stages.discard(account.account_id, handle.meeting_id)
            except Exception:
                pass
            try:
                await handle.finish("failed")
            except Exception:
                pass
            raise
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
                await asyncio.to_thread(
                    self.audio_stages.discard,
                    account.account_id,
                    handle.meeting_id,
                )
            except Exception:
                pass
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
                lambda: binding.public_event_high_water >= target
                or (binding.capture_fenced and binding.persistence_failure is not None)
            )
        return binding

    async def wait_for_terminal(self, binding: _LiveBinding) -> None:
        async with binding.changed:
            await binding.changed.wait_for(
                lambda: binding.terminal_persisted
                or (binding.capture_fenced and binding.persistence_failure is not None)
            )

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
        if not self._accepting_publications:
            return
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._accept_raw, meeting_id, snapshot, events)

    def _accept_raw(
        self,
        meeting_id: str,
        snapshot: LiveServiceSnapshot,
        events: tuple[LiveServiceEvent, ...],
    ) -> None:
        if not self._accepting_publications:
            return
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
            if _terminal_finalization_not_started(
                publication.snapshot,
                finalizer_configured=self.runtime._terminal_finalizer is not None,
            ):
                # `session_closed` is emitted immediately before the configured finalizer is
                # marked running. This one raw intermediate is not a durable/public ending;
                # the next queued publication carries running or a terminal refusal.
                continue
            document = _transcript_document(publication.snapshot)
            try:
                terminal = _durable_terminal_status(
                    publication.snapshot,
                    finalizer_configured=self.runtime._terminal_finalizer is not None,
                )
                document_changed = document != binding.durable_document
                if terminal is not None and not binding.terminal_persisted:
                    if document_changed:
                        binding.durable_version = await binding.handle.commit_transcript(document)
                        binding.durable_document = document
                    try:
                        await self._settle_audio(
                            binding,
                            publication.snapshot,
                            interrupted=terminal == "interrupted",
                        )
                    except AccountRevoked:
                        await self._fence(binding, "meeting_authority_revoked")
                        continue
                    except Exception:
                        await self._terminal_recovery_failed(
                            binding,
                            "audio_terminal_recovery_failed",
                            publication.snapshot,
                            publication.events,
                        )
                        continue
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

    async def _settle_audio(
        self,
        binding: _LiveBinding,
        snapshot: LiveServiceSnapshot,
        *,
        interrupted: bool,
    ) -> None:
        account_id = binding.owner_key[0]
        prefix = await asyncio.to_thread(
            self.audio_stages.prefix,
            account_id,
            binding.handle.meeting_id,
            expected_samples=snapshot.session.accepted_samples,
        )
        if prefix is None:
            await binding.handle.record_audio_unavailable()
        else:
            await binding.handle.publish_audio(
                self.audio_archive,
                prefix.path,
                partial=interrupted or not prefix.complete,
                raw_pcm=True,
            )
        await asyncio.to_thread(
            self.audio_stages.discard,
            account_id,
            binding.handle.meeting_id,
        )

    async def _terminal_recovery_failed(
        self,
        binding: _LiveBinding,
        reason: str,
        terminal_snapshot: LiveServiceSnapshot | None,
        terminal_events: tuple[LiveServiceEvent, ...],
    ) -> None:
        binding.capture_fenced = True
        recovered = False
        durable_interruption = False
        try:
            await binding.handle.recover_interrupted_audio(
                self.audio_archive,
                self.audio_stages,
            )
            recovered = True
        except AccountRevoked:
            durable_interruption = await self._discard_stage_after_authority_loss(binding)
        except Exception:
            # Keep the canonical row active: startup recovery is the only durable owner
            # of a stage whose verified cleanup has not completed.
            pass
        if recovered:
            try:
                await binding.handle.finish("interrupted")
                durable_interruption = True
            except AccountRevoked:
                durable_interruption = await self._discard_stage_after_authority_loss(
                    binding
                )
            except Exception:
                pass
        if durable_interruption:
            binding.terminal_persisted = True
            # The terminal transcript was committed before audio settlement began, so
            # this exact runtime publication is now safe to expose in full.
            binding.public_snapshot = terminal_snapshot
            binding.public_events = terminal_events
            binding.public_event_high_water = (
                -1 if not terminal_events else terminal_events[-1].seq
            )
        binding.persistence_failure = reason
        async with binding.changed:
            binding.changed.notify_all()

    async def _discard_stage_after_authority_loss(self, binding: _LiveBinding) -> bool:
        cleanup = binding.authority_cleanup_task
        if cleanup is None:
            cleanup = asyncio.create_task(
                asyncio.to_thread(
                    self._discard_revoked_stage,
                    binding.owner_key[0],
                    binding.handle.meeting_id,
                ),
                name=f"phase2-live-revoked-cleanup-{binding.handle.meeting_id}",
            )
            binding.authority_cleanup_task = cleanup
        try:
            await asyncio.shield(cleanup)
            return True
        except asyncio.CancelledError:
            # The task remains owned by the binding; shutdown will await the same work.
            raise
        except Exception:
            return False
        finally:
            if cleanup.done() and binding.authority_cleanup_task is cleanup:
                binding.authority_cleanup_task = None

    def _discard_revoked_stage(self, account_id: str, meeting_id: str) -> None:
        failure: Exception | None = None
        for _ in range(2):
            try:
                self.audio_stages.discard(account_id, meeting_id)
                return
            except Exception as exc:
                failure = exc
        assert failure is not None
        raise failure

    async def _fence(self, binding: _LiveBinding, reason: str) -> None:
        if binding.terminal_persisted:
            return
        if binding.capture_fenced:
            try:
                terminal_snapshot = self.runtime.snapshot(binding.handle.meeting_id)
            except Exception:
                terminal_snapshot = None
            try:
                terminal_events = self.runtime.events(binding.handle.meeting_id)
            except Exception:
                terminal_events = ()
            await self._terminal_recovery_failed(
                binding,
                binding.persistence_failure or reason,
                terminal_snapshot,
                terminal_events,
            )
            return
        binding.capture_fenced = True
        try:
            terminal_snapshot = self.runtime.snapshot(binding.handle.meeting_id)
        except Exception:
            terminal_snapshot = None
        terminal_events: tuple[LiveServiceEvent, ...] = ()
        try:
            aborted = await self.runtime.abort(binding.handle.meeting_id, reason)
            terminal_snapshot = aborted
        except Exception:
            pass
        try:
            terminal_events = self.runtime.events(binding.handle.meeting_id)
        except Exception:
            pass
        durable_interruption = False
        try:
            if terminal_snapshot is not None:
                await self._settle_audio(
                    binding,
                    terminal_snapshot,
                    interrupted=True,
                )
            await binding.handle.finish("interrupted")
            binding.terminal_persisted = True
            durable_interruption = True
        except AccountRevoked:
            # Account revocation atomically interrupts all active Meetings before the
            # captured handle's generation fence rejects this redundant finish.
            durable_interruption = await self._discard_stage_after_authority_loss(binding)
            binding.terminal_persisted = durable_interruption
        except Exception:
            recovered = False
            try:
                await binding.handle.recover_interrupted_audio(
                    self.audio_archive,
                    self.audio_stages,
                )
                recovered = True
            except AccountRevoked:
                durable_interruption = await self._discard_stage_after_authority_loss(
                    binding
                )
                binding.terminal_persisted = durable_interruption
            except Exception:
                pass
            if recovered:
                try:
                    await binding.handle.finish("interrupted")
                    binding.terminal_persisted = True
                    durable_interruption = True
                except AccountRevoked:
                    durable_interruption = await self._discard_stage_after_authority_loss(
                        binding
                    )
                    binding.terminal_persisted = durable_interruption
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
        # Publish the failure flag only after the durable/public terminal projection is ready;
        # otherwise a concurrent poll can observe the reason beside the old active snapshot.
        binding.persistence_failure = reason
        async with binding.changed:
            binding.changed.notify_all()


@dataclass(frozen=True, slots=True)
class _Phase2CreateAuthority:
    account: Account
    origin_session: str
    workspace: Any


class _Phase2LiveTransportAdapter:
    """Account authority and durable publication at the shared Live transport seam."""

    _MUTATIONS = frozenset({"frame", "heartbeat", "stop", "abort"})

    def __init__(self, live: Phase2LiveMeetings, require_account: Any) -> None:
        self.live = live
        self.require_account = require_account

    async def authorize(
        self,
        request: Request,
        operation: str,
        session_id: str | None,
    ) -> object:
        from fastapi import HTTPException

        account = await self.require_account(request)
        sign_in_session = request.cookies.get("__Host-moss_session")
        if operation == "descriptor":
            return account
        if operation == "create":
            if not sign_in_session:
                raise HTTPException(status_code=401, detail="Sign in required.")
            return _Phase2CreateAuthority(
                account=account,
                origin_session=sign_in_session,
                workspace=request.app.state.phase2_store.workspace(account),
            )
        if session_id is None:
            raise ValueError("session_id is required after Live Meeting creation.")
        try:
            return self.live.open(
                account,
                sign_in_session or "",
                session_id,
                mutation=operation in self._MUTATIONS,
            )
        except LiveMeetingNotFound as exc:
            raise HTTPException(status_code=404, detail="Live Meeting not found.") from exc
        except LiveMeetingReadOnly as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except LiveMeetingTerminal as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    async def create(
        self,
        payload: Mapping[str, object],
        authority: object,
    ) -> LiveTransportCreated:
        if not isinstance(authority, _Phase2CreateAuthority):
            raise TypeError("Phase-2 Live creation requires Account authority.")
        binding = await self.live.create(
            account=authority.account,
            workspace=authority.workspace,
            origin_session=authority.origin_session,
            echo_mode=payload.get("echo_mode"),
        )
        return LiveTransportCreated(
            session_id=binding.handle.meeting_id,
            authority=binding,
            status_code=201,
            response_fields={},
            arm_helper_lease=True,
        )

    def snapshot(
        self,
        authority: object,
        session_id: str,
        *,
        since_version: int | None,
    ) -> LiveTransportSnapshotView:
        binding = self._binding(authority)
        return LiveTransportSnapshotView(
            visible=self.live.snapshot(binding, since_version=since_version),
            current=binding.public_snapshot,
            fields={
                "meeting_transcript_version": binding.durable_version,
                "persistence_failure": binding.persistence_failure,
            },
        )

    def events(
        self,
        authority: object,
        session_id: str,
        *,
        since_seq: int,
    ) -> LiveTransportEventView:
        return LiveTransportEventView(
            events=self.live.events(self._binding(authority), since_seq),
            fields={},
        )

    async def publication(
        self,
        authority: object,
        session_id: str,
        *,
        wait_for_durability: bool,
    ) -> LiveServiceSnapshot | None:
        binding = self._binding(authority)
        if wait_for_durability:
            binding = await self.live.sync_and_flush(session_id)
            await self.live.wait_for_terminal(binding)
        return binding.public_snapshot

    @staticmethod
    def _binding(authority: object) -> _LiveBinding:
        if not isinstance(authority, _LiveBinding):
            raise TypeError("Phase-2 Live publication requires a Meeting binding.")
        return authority


def attach_phase2_live_routes(
    app: Any,
    live: Phase2LiveMeetings,
    *,
    require_account: Any,
    live_helper_lease_seconds: float,
) -> None:
    """Attach Account authority to the one shared Live transport implementation."""

    app.state.phase2_live = live
    attach_live_routes(
        app,
        live.runtime,
        None,
        live_helper_lease_seconds=live_helper_lease_seconds,
        tape_store=live.audio_stages,
        transport_adapter=_Phase2LiveTransportAdapter(live, require_account),
    )


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


def _durable_terminal_status(
    snapshot: LiveServiceSnapshot,
    *,
    finalizer_configured: bool,
) -> str | None:
    if snapshot.terminal_failure is not None or snapshot.session.status in {"aborted", "failed"}:
        return "interrupted"
    if snapshot.session.status == "closed" and snapshot.session.finalization_status in {
        "final",
        "failed",
        "unavailable",
    }:
        return "completed"
    if (
        snapshot.session.status == "closed"
        and snapshot.session.finalization_status == "not_started"
        and not finalizer_configured
    ):
        return "completed"
    return None


def _terminal_finalization_not_started(
    snapshot: LiveServiceSnapshot,
    *,
    finalizer_configured: bool,
) -> bool:
    return (
        finalizer_configured
        and snapshot.terminal_failure is None
        and snapshot.session.status == "closed"
        and snapshot.session.finalization_status == "not_started"
    )


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


__all__ = ["Phase2LiveMeetings", "attach_phase2_live_routes"]
