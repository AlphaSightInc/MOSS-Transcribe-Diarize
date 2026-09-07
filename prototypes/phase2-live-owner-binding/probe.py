"""PROTOTYPE — owner-bound Live Meeting authorization and poll-storage boundary.

Question: is the originating Sign-in session plus an owner-bound Meeting handle sufficient
for capture control while same-Account observers read the in-memory Live registry?
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from moss_transcribe_diarize.app.phase2 import (
    Account,
    AccountRevoked,
    GoogleIdentity,
    Phase2Store,
)


READ_OPERATIONS = frozenset({"snapshot", "events"})
MUTATION_OPERATIONS = frozenset({"frame", "heartbeat", "stop", "abort"})


def print_contract() -> None:
    """Print the design contract before any transition evidence."""

    print(
        json.dumps(
            {
                "action": "structural_contract",
                "question": (
                    "Can current Sign-in authority plus an owner-bound Meeting handle support "
                    "owner-only capture, same-Account observation, and durable-before-public "
                    "Live revisions through one shared transport?"
                ),
                "hypothesis": (
                    "Seven bounded primitives are sufficient; no bearer, view token, client "
                    "Account identity, global Meeting lookup, auth cache, or duplicate transport "
                    "is needed."
                ),
                "minimum_primitives": [
                    {
                        "name": "current_sign_in_session_resolution",
                        "boundary": "one request: SQLite session to enabled Account generation",
                        "irreducible_because": "removal or caching would bypass revocation/isolation",
                    },
                    {
                        "name": "owner_bound_meeting_handle",
                        "boundary": "one durable capability captures Account, generation, Meeting",
                        "irreducible_because": "a bare Meeting lookup permits authority rebinding",
                    },
                    {
                        "name": "account_partitioned_transient_live_binding",
                        "boundary": "active-process runtime, lease, public state; grants no authority",
                        "irreducible_because": "250ms observation needs memory without content SQL",
                    },
                    {
                        "name": "shared_live_transport",
                        "boundary": "all invariant capture protocol outside five adapter hooks",
                        "irreducible_because": "per-authority transports duplicate identical behavior",
                    },
                    {
                        "name": "serialized_durability_bridge",
                        "boundary": "raw callback to durable commit to public high-water",
                        "irreducible_because": "parallel/direct publication exposes undurable order",
                    },
                    {
                        "name": "existing_store_lock_for_external_reads",
                        "boundary": "same SQLite connection; external reads lock, internal reads do not",
                        "irreducible_because": "unlocked reads can observe an uncommitted multi-row tuple",
                    },
                    {
                        "name": "page_local_controller_and_ephemeral_observer",
                        "boundary": "one page; observer writes no control or reattach state",
                        "irreducible_because": "one generic state grants control or resumes after reload",
                    },
                ],
                "invariants": [
                    "every request resolves current SQLite authority",
                    "owner controls; same Account observes; foreign is 404; revoked is 401",
                    "poll content is memory-backed and public never advances before durability",
                    "terminal document and status commit atomically; interruption never resumes",
                    "legacy and Phase2 share frame, Stop, error, and lifecycle semantics",
                ],
                "assumptions_unknowns": [
                    "one Sign-in session is one settled Access client",
                    "sibling tabs sharing that cookie are not distinct clients",
                    "production load beyond the measured transitions is unmeasured",
                ],
                "falsifier": (
                    "Any authority escape, content SQL during poll, mixed durable tuple, held "
                    "publication leak, adapter protocol divergence, lost prefix, late publish, "
                    "or capture resume rejects the design."
                ),
                "tool_decisions": [
                    {
                        "experiment": "browser_state_transitions",
                        "necessary": "observe control, view, storage, and reload state directly",
                        "reject_if": "observer controls/stores reattach or reload retains control",
                    },
                    {
                        "experiment": "shared_transport_two_adapters",
                        "necessary": "execute one protocol through both authority/publication shapes",
                        "reject_if": "frame, conflict, Stop, events, terminal state diverge or held state leaks",
                    },
                    {
                        "experiment": "production_store_sql_trace",
                        "necessary": "count actual auth/content reads and writes on polling",
                        "reject_if": "poll performs content SQL/write or revoked Account opens binding",
                    },
                    {
                        "experiment": "held_and_rolled_back_store_mutation",
                        "necessary": "make the within-transaction multi-row gap observable",
                        "reject_if": "external read returns early or exposes mixed old/new state",
                    },
                    {
                        "experiment": "runtime_thread_serial_commit_handoff",
                        "necessary": "observe raw/durable/public/event order under concurrency",
                        "reject_if": "public advances early, commit reorders, or late callback reaches closed loop",
                    },
                    {
                        "experiment": "finalizer_revoke_shutdown_faults",
                        "necessary": "exercise reachable fences while work is pending",
                        "reject_if": "terminalizes early, loses prefix, accepts late work, or resumes",
                    },
                    {
                        "experiment": "temporary_sqlite_and_controlled_gates",
                        "necessary": "run real persistence/concurrency without retaining prototype data",
                        "reject_if": "result depends on durable fixture state, sleeps, or production database",
                    },
                ],
            },
            sort_keys=True,
        )
    )


@dataclass
class BrowserObservationProbe:
    """Smallest page policy: history may attach a reader, never manufacture a controller."""

    phase: str = "idle"
    originated_capture_id: str | None = None
    observed_meeting_id: str | None = None
    session_storage_meeting_id: str | None = None

    def originate_capture(self, meeting_id: str) -> None:
        self.phase = "active"
        self.originated_capture_id = meeting_id
        self.observed_meeting_id = meeting_id
        self.session_storage_meeting_id = meeting_id

    def open_active_history(self, meeting_id: str) -> str:
        if self.originated_capture_id is not None:
            return "origin_control_preserved"
        self.phase = "viewing"
        self.observed_meeting_id = meeting_id
        return "read_only_observer_attached"

    def reload(self) -> None:
        self.originated_capture_id = None
        self.observed_meeting_id = self.session_storage_meeting_id
        self.phase = "viewing" if self.observed_meeting_id is not None else "idle"

    def state(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "originated_capture_id": self.originated_capture_id,
            "observed_meeting_id": self.observed_meeting_id,
            "session_storage_meeting_id": self.session_storage_meeting_id,
            "capture_mutation_enabled": self.originated_capture_id is not None,
        }


def run_browser_observation_policy_probe() -> None:
    observer = BrowserObservationProbe()
    observer_action = observer.open_active_history("meeting-live")
    observer_before_reload = observer.state()
    observer.reload()
    observer_after_reload = observer.state()

    origin = BrowserObservationProbe()
    origin.originate_capture("meeting-live")
    origin_action = origin.open_active_history("meeting-live")
    origin_before_reload = origin.state()
    origin.reload()
    origin_after_reload = origin.state()

    print(
        json.dumps(
            {
                "action": "browser_history_observation_policy",
                "observer": {
                    "open": observer_action,
                    "before_reload": observer_before_reload,
                    "after_reload": observer_after_reload,
                },
                "origin": {
                    "open": origin_action,
                    "before_reload": origin_before_reload,
                    "after_reload": origin_after_reload,
                },
            },
            sort_keys=True,
        )
    )
    assert observer_action == "read_only_observer_attached"
    assert observer_before_reload["capture_mutation_enabled"] is False
    assert observer_before_reload["session_storage_meeting_id"] is None
    assert observer_after_reload["phase"] == "idle"
    assert origin_action == "origin_control_preserved"
    assert origin_before_reload["capture_mutation_enabled"] is True
    assert origin_after_reload["phase"] == "viewing"
    assert origin_after_reload["capture_mutation_enabled"] is False


@dataclass(frozen=True)
class AdapterCreation:
    session_id: str
    status_code: int


@dataclass
class AdapterState:
    name: str
    create_status: int
    raw_version: int = 0
    durable_version: int = 0
    public_version: int = 0
    public_status: str = "active"
    accepted_sequences: list[int] = field(default_factory=list)
    public_events: list[str] = field(default_factory=lambda: ["created"])
    held_publication: tuple[int, str, str] | None = None
    authorized_operations: list[str] = field(default_factory=list)


class LegacyTransportAdapterProbe:
    """Prototype adapter: legacy authority publishes raw runtime state immediately."""

    def __init__(self) -> None:
        self.state = AdapterState("legacy", 200)

    async def authorize(self, operation: str, session_id: str | None) -> AdapterState:
        self.state.authorized_operations.append(operation)
        return self.state

    async def create(self) -> AdapterCreation:
        return AdapterCreation("probe-session", self.state.create_status)

    def snapshot(self) -> dict[str, object]:
        return {
            "status": self.state.public_status,
            "version": self.state.public_version,
        }

    def events(self) -> tuple[str, ...]:
        return tuple(self.state.public_events)

    async def publication(self, version: int, status: str, event: str) -> None:
        self.state.raw_version = version
        self.state.durable_version = version
        self.state.public_version = version
        self.state.public_status = status
        self.state.public_events.append(event)


class Phase2TransportAdapterProbe(LegacyTransportAdapterProbe):
    """Prototype adapter: owner-bound publication waits for its durable commit."""

    def __init__(self) -> None:
        super().__init__()
        self.state = AdapterState("phase2", 201)

    async def publication(self, version: int, status: str, event: str) -> None:
        self.state.raw_version = version
        self.state.held_publication = (version, status, event)

    def release_durable_publication(self) -> None:
        held = self.state.held_publication
        assert held is not None
        version, status, event = held
        self.state.durable_version = version
        self.state.public_version = version
        self.state.public_status = status
        self.state.public_events.append(event)
        self.state.held_publication = None


class SharedTransportProbe:
    """One frame/Stop/error implementation exercised through either adapter."""

    def __init__(self, adapter: LegacyTransportAdapterProbe) -> None:
        self.adapter = adapter
        self.expected_sequence = 0
        self.session_id: str | None = None

    async def create(self) -> AdapterCreation:
        await self.adapter.authorize("create", None)
        created = await self.adapter.create()
        self.session_id = created.session_id
        return created

    async def frame(self, sequence: int) -> dict[str, object]:
        assert self.session_id is not None
        await self.adapter.authorize("frame", self.session_id)
        if sequence != self.expected_sequence:
            return {
                "status": 409,
                "failure": "v2_out_of_order_frame",
                "expected": self.expected_sequence,
                "received": sequence,
            }
        self.adapter.state.accepted_sequences.append(sequence)
        self.expected_sequence += 1
        version = self.adapter.state.raw_version + 1
        await self.adapter.publication(version, "active", "frame_accepted")
        return {"status": 200, "sequence": sequence}

    async def stop(self) -> dict[str, object]:
        assert self.session_id is not None
        await self.adapter.authorize("stop", self.session_id)
        version = self.adapter.state.raw_version + 1
        await self.adapter.publication(version, "closed", "stopped")
        return {"status": 200}

    async def snapshot(self) -> dict[str, object]:
        assert self.session_id is not None
        await self.adapter.authorize("snapshot", self.session_id)
        return self.adapter.snapshot()

    async def events(self) -> tuple[str, ...]:
        assert self.session_id is not None
        await self.adapter.authorize("events", self.session_id)
        return self.adapter.events()


def _adapter_state(adapter: LegacyTransportAdapterProbe) -> dict[str, object]:
    state = adapter.state
    return {
        "name": state.name,
        "versions": {
            "raw": state.raw_version,
            "durable": state.durable_version,
            "public": state.public_version,
        },
        "public_status": state.public_status,
        "accepted_sequences": list(state.accepted_sequences),
        "public_events": list(state.public_events),
        "publication_held": state.held_publication is not None,
        "authorized_operations": list(state.authorized_operations),
    }


async def run_shared_transport_adapter_probe() -> None:
    legacy_adapter = LegacyTransportAdapterProbe()
    phase2_adapter = Phase2TransportAdapterProbe()
    legacy = SharedTransportProbe(legacy_adapter)
    phase2 = SharedTransportProbe(phase2_adapter)

    legacy_created = await legacy.create()
    phase2_created = await phase2.create()
    assert (legacy_created.status_code, phase2_created.status_code) == (200, 201)

    legacy_frame = await legacy.frame(0)
    phase2_frame = await phase2.frame(0)
    assert legacy_frame == phase2_frame == {"status": 200, "sequence": 0}
    phase2_held_frame = {
        "snapshot": await phase2.snapshot(),
        "events": list(await phase2.events()),
        "state": _adapter_state(phase2_adapter),
    }
    assert phase2_held_frame["snapshot"] == {"status": "active", "version": 0}
    assert phase2_held_frame["events"] == ["created"]
    assert phase2_held_frame["state"]["versions"] == {
        "raw": 1,
        "durable": 0,
        "public": 0,
    }

    phase2_adapter.release_durable_publication()
    assert await phase2.snapshot() == {"status": "active", "version": 1}
    legacy_error = await legacy.frame(0)
    phase2_error = await phase2.frame(0)
    assert legacy_error == phase2_error == {
        "status": 409,
        "failure": "v2_out_of_order_frame",
        "expected": 1,
        "received": 0,
    }

    legacy_stop = await legacy.stop()
    phase2_stop = await phase2.stop()
    assert legacy_stop == phase2_stop == {"status": 200}
    phase2_held_stop = {
        "snapshot": await phase2.snapshot(),
        "events": list(await phase2.events()),
        "state": _adapter_state(phase2_adapter),
    }
    assert phase2_held_stop["snapshot"] == {"status": "active", "version": 1}
    assert phase2_held_stop["events"] == ["created", "frame_accepted"]
    assert phase2_held_stop["state"]["versions"] == {
        "raw": 2,
        "durable": 1,
        "public": 1,
    }

    phase2_adapter.release_durable_publication()
    legacy_final = {
        "snapshot": await legacy.snapshot(),
        "events": list(await legacy.events()),
        "state": _adapter_state(legacy_adapter),
    }
    phase2_final = {
        "snapshot": await phase2.snapshot(),
        "events": list(await phase2.events()),
        "state": _adapter_state(phase2_adapter),
    }
    assert legacy_final["snapshot"] == phase2_final["snapshot"] == {
        "status": "closed",
        "version": 2,
    }
    assert legacy_final["events"] == phase2_final["events"] == [
        "created",
        "frame_accepted",
        "stopped",
    ]
    print(
        json.dumps(
            {
                "action": "shared_transport_adapter_seam",
                "interface": ["authorize", "create", "snapshot", "events", "publication"],
                "shared_frame": legacy_frame,
                "shared_error": legacy_error,
                "shared_stop": legacy_stop,
                "phase2_frame_commit_held": phase2_held_frame,
                "phase2_stop_commit_held": phase2_held_stop,
                "legacy_final": legacy_final,
                "phase2_final": phase2_final,
            },
            sort_keys=True,
        )
    )


@dataclass
class SqlCounts:
    auth_reads: int = 0
    content_reads: int = 0
    writes: int = 0

    def reset(self) -> None:
        self.auth_reads = 0
        self.content_reads = 0
        self.writes = 0

    def observe(self, statement: str) -> None:
        normalized = " ".join(statement.lower().split())
        if normalized.startswith("select"):
            if any(
                table in normalized
                for table in (
                    " meetings",
                    " meeting_transcripts",
                    " meeting_speakers",
                    " meeting_audio",
                    " voiceprints",
                    " llm_artifacts",
                )
            ):
                self.content_reads += 1
            elif " sign_in_sessions" in normalized and " accounts" in normalized:
                self.auth_reads += 1
        elif normalized.startswith(("insert", "update", "delete", "replace")):
            self.writes += 1

    def to_dict(self) -> dict[str, int]:
        return {
            "auth_reads": self.auth_reads,
            "content_reads": self.content_reads,
            "writes": self.writes,
        }


@dataclass
class LiveBinding:
    owner_key: tuple[str, int]
    origin_session: str
    handle: Any
    snapshot: dict[str, object]
    status: str = "active"
    raw_version: int = 0
    durable_version: int = 0
    public_version: int = 0
    raw_event_high_water: int = 0
    public_event_high_water: int = 0
    capture_fenced: bool = False


@dataclass(frozen=True)
class RawPublication:
    revision_version: int
    event_high_water: int
    document: dict[str, object]


class ControlledCommit:
    """Hold each real MeetingHandle commit so visibility ordering is observable."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self._started: dict[int, asyncio.Event] = {}
        self._released: dict[int, asyncio.Event] = {}
        self.order: list[int] = []

    def _event(self, events: dict[int, asyncio.Event], version: int) -> asyncio.Event:
        return events.setdefault(version, asyncio.Event())

    async def __call__(self, publication: RawPublication) -> int:
        self.order.append(publication.revision_version)
        self._event(self._started, publication.revision_version).set()
        await self._event(self._released, publication.revision_version).wait()
        return await self._handle.commit_transcript(publication.document)

    async def wait_started(self, version: int) -> None:
        await self._event(self._started, version).wait()

    def release(self, version: int) -> None:
        self._event(self._released, version).set()


class PublicationBridgeProbe:
    """Prototype of the event-driven, serialized raw→durable→public bridge."""

    def __init__(
        self,
        binding: LiveBinding,
        commit: ControlledCommit,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        self._binding = binding
        self._commit = commit
        self._loop = loop
        self._queue: asyncio.Queue[RawPublication | None] = asyncio.Queue()
        self._raw_changed = asyncio.Condition()
        self._public_changed = asyncio.Condition()
        self._fenced = asyncio.Event()
        self._accepting = True
        self._worker = asyncio.create_task(self._run())

    def observe_from_runtime_thread(self, publication: RawPublication) -> None:
        if not self._accepting:
            return
        self._loop.call_soon_threadsafe(self._accept_raw, publication)

    def _accept_raw(self, publication: RawPublication) -> None:
        self._binding.raw_version = publication.revision_version
        self._binding.raw_event_high_water = publication.event_high_water
        self._queue.put_nowait(publication)
        asyncio.create_task(self._notify(self._raw_changed))

    async def _notify(self, condition: asyncio.Condition) -> None:
        async with condition:
            condition.notify_all()

    async def wait_raw(self, version: int) -> None:
        async with self._raw_changed:
            await self._raw_changed.wait_for(lambda: self._binding.raw_version >= version)

    async def wait_public(self, version: int) -> None:
        async with self._public_changed:
            await self._public_changed.wait_for(lambda: self._binding.public_version >= version)

    async def wait_fenced(self) -> None:
        await self._fenced.wait()

    async def close(self) -> None:
        self._accepting = False
        self._queue.put_nowait(None)
        await self._worker

    async def _run(self) -> None:
        while True:
            publication = await self._queue.get()
            if publication is None:
                return
            try:
                durable_version = await self._commit(publication)
            except AccountRevoked:
                # Keep the last durable document/event boundary and fence capture.
                self._binding.status = "interrupted"
                self._binding.snapshot = {**self._binding.snapshot, "status": "interrupted"}
                self._binding.capture_fenced = True
                self._fenced.set()
                continue
            self._binding.durable_version = durable_version
            self._binding.public_version = publication.revision_version
            self._binding.public_event_high_water = publication.event_high_water
            self._binding.snapshot = {
                "status": "active",
                "transcript_version": durable_version,
                "segments": [
                    segment["text"]
                    for segment in publication.document.get("segments", [])
                    if isinstance(segment, dict) and isinstance(segment.get("text"), str)
                ],
            }
            await self._notify(self._public_changed)


@dataclass(frozen=True)
class FinalizingPublication:
    raw_version: int
    session_status: str
    finalization_status: str
    document: dict[str, object]


class ControlledAtomicTerminal:
    """Hold the final document/status transaction so pre-commit visibility is observable."""

    def __init__(self, handle: Any) -> None:
        self._handle = handle
        self.started = asyncio.Event()
        self.released = asyncio.Event()

    async def __call__(self, publication: FinalizingPublication) -> int:
        self.started.set()
        await self.released.wait()
        return await self._handle.finish_with_transcript(publication.document, "completed")


class TerminalFinalizerGateProbe:
    """Publish durable stop-tail state, then only the finalizer's atomic terminal tuple."""

    def __init__(
        self,
        binding: LiveBinding,
        commit_terminal: ControlledAtomicTerminal,
    ) -> None:
        self.binding = binding
        self._commit_terminal = commit_terminal

    async def accept(self, publication: FinalizingPublication) -> None:
        self.binding.raw_version = publication.raw_version
        if publication.session_status == "closed" and publication.finalization_status == "not_started":
            return
        if publication.session_status == "closed" and publication.finalization_status == "running":
            durable_version = await self.binding.handle.commit_transcript(publication.document)
            self.binding.durable_version = durable_version
            self.binding.public_version = publication.raw_version
            self.binding.snapshot = {
                "status": "closed",
                "finalization_status": "running",
                "transcript_version": durable_version,
                "segments": [
                    segment["text"]
                    for segment in publication.document.get("segments", [])
                    if isinstance(segment, dict) and isinstance(segment.get("text"), str)
                ],
            }
            return
        assert publication.session_status == "closed"
        assert publication.finalization_status in {"final", "failed", "unavailable"}
        durable_version = await self._commit_terminal(publication)
        self.binding.durable_version = durable_version
        self.binding.public_version = publication.raw_version
        self.binding.status = "completed"
        self.binding.snapshot = {
            "status": "completed",
            "transcript_version": durable_version,
            "segments": [
                segment["text"]
                for segment in publication.document.get("segments", [])
                if isinstance(segment, dict) and isinstance(segment.get("text"), str)
            ],
        }


class SimulatedProcessLoss(RuntimeError):
    """Probe-only failure after both terminal writes but before transaction commit."""


async def _probe_external_snapshot(store: Phase2Store, handle: Any) -> dict[str, object]:
    async with store._write_lock:
        cursor = await store._connection.execute(
            """
            SELECT m.status, t.version, t.document_json
            FROM meetings m
            LEFT JOIN meeting_transcripts t
              ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
            WHERE m.account_id = ? AND m.meeting_id = ?
            """,
            (handle._account_id, handle.meeting_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
    document = json.loads(row["document_json"])
    return {
        "status": row["status"],
        "version": int(row["version"]),
        "text": document["segments"][0]["text"],
    }


async def _probe_external_list(store: Phase2Store, handle: Any) -> dict[str, object]:
    return await _probe_external_snapshot(store, handle)


async def _probe_external_auth(store: Phase2Store, session_id: str) -> str | None:
    async with store._write_lock:
        cursor = await store._connection.execute(
            """
            SELECT a.email
            FROM sign_in_sessions s
            JOIN accounts a ON a.account_id = s.account_id
            WHERE s.session_id = ? AND a.enabled = 1
            """,
            (session_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
    return None if row is None else str(row["email"])


async def held_terminal_read_isolation_probe(
    store: Phase2Store,
    handle: Any,
    session_id: str,
    document: dict[str, object],
    *,
    commit: bool,
) -> dict[str, object]:
    """Hold after status UPDATE; external reads use the existing mutation lock."""

    status_updated = asyncio.Event()
    release = asyncio.Event()
    document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))

    async def mutate() -> None:
        try:
            async with store._mutation():
                await store._connection.execute(
                    """
                    UPDATE meetings SET status = 'completed'
                    WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                    """,
                    (handle._account_id, handle.meeting_id),
                )
                status_updated.set()
                await release.wait()
                if not commit:
                    raise SimulatedProcessLoss("probe rollback between terminal writes")
                await store._connection.execute(
                    """
                    UPDATE meeting_transcripts
                    SET document_json = ?, version = version + 1
                    WHERE account_id = ? AND meeting_id = ?
                    """,
                    (document_json, handle._account_id, handle.meeting_id),
                )
        except SimulatedProcessLoss:
            pass

    mutation_task = asyncio.create_task(mutate())
    await status_updated.wait()
    reads = {
        "snapshot": asyncio.create_task(_probe_external_snapshot(store, handle)),
        "list": asyncio.create_task(_probe_external_list(store, handle)),
        "auth": asyncio.create_task(_probe_external_auth(store, session_id)),
    }
    await asyncio.sleep(0)
    blocked = {name: not task.done() for name, task in reads.items()}
    assert blocked == {"snapshot": True, "list": True, "auth": True}
    release.set()
    await mutation_task
    results = {name: await task for name, task in reads.items()}
    return {"blocked_between_writes": blocked, "results_after_transaction": results}


async def commit_terminal_probe(
    store: Phase2Store,
    handle: Any,
    document: dict[str, object],
    *,
    fail_before_commit: bool,
) -> int:
    """Prototype the minimum atomic terminal mutation before production absorbs it."""

    document_json = json.dumps(document, ensure_ascii=False, separators=(",", ":"))
    async with store._mutation():
        cursor = await store._connection.execute(
            """
            UPDATE meetings SET status = 'completed'
            WHERE account_id = ? AND meeting_id = ? AND status = 'active'
              AND EXISTS (
                SELECT 1 FROM accounts
                WHERE account_id = ? AND enabled = 1 AND authority_generation = ?
              )
            """,
            (
                handle._account_id,
                handle.meeting_id,
                handle._account_id,
                handle._authority_generation,
            ),
        )
        if cursor.rowcount != 1:
            raise AccountRevoked("Meeting authority is revoked or interrupted.")
        await store._connection.execute(
            """
            INSERT INTO meeting_transcripts(
                account_id, meeting_id, document_json, version, updated_at_ms
            ) VALUES (?, ?, ?, 1, 0)
            ON CONFLICT(account_id, meeting_id) DO UPDATE SET
                document_json = excluded.document_json,
                version = meeting_transcripts.version + 1,
                updated_at_ms = excluded.updated_at_ms
            """,
            (handle._account_id, handle.meeting_id, document_json),
        )
        if fail_before_commit:
            raise SimulatedProcessLoss("process lost before SQLite commit")
        cursor = await store._connection.execute(
            """
            SELECT version FROM meeting_transcripts
            WHERE account_id = ? AND meeting_id = ?
            """,
            (handle._account_id, handle.meeting_id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return int(row["version"])


class AccountPartitionedLiveRegistry:
    """Prototype-only registry: memory stores state; a valid Account is required to enter."""

    def __init__(self) -> None:
        self._bindings: dict[str, LiveBinding] = {}

    def bind(self, account: Account, session_id: str, handle: Any) -> LiveBinding:
        binding = LiveBinding(
            owner_key=(account.account_id, account.authority_generation),
            origin_session=session_id,
            handle=handle,
            snapshot={"status": "active", "transcript_version": 0, "segments": []},
        )
        self._bindings[handle.meeting_id] = binding
        return binding

    def open(self, account: Account, meeting_id: str) -> LiveBinding | None:
        binding = self._bindings.get(meeting_id)
        if binding is None:
            return None
        return (
            binding
            if binding.owner_key == (account.account_id, account.authority_generation)
            else None
        )

    def interrupt(self, binding: LiveBinding) -> None:
        binding.status = "interrupted"
        binding.snapshot = {**binding.snapshot, "status": "interrupted"}


async def authorize(
    store: Phase2Store,
    registry: AccountPartitionedLiveRegistry,
    *,
    session_id: str,
    meeting_id: str,
    operation: str,
) -> tuple[int, LiveBinding | None]:
    # ADR-0007 requires this SQLite auth resolution on every request. It is the only durable
    # read allowed on the 250 ms snapshot/events path.
    account = await store.account_for_session(session_id)
    if account is None:
        return 401, None
    binding = registry.open(account, meeting_id)
    if binding is None:
        return 404, None
    if operation in READ_OPERATIONS:
        return 200, binding
    if operation not in MUTATION_OPERATIONS:
        raise ValueError(operation)
    if session_id != binding.origin_session:
        return 403, None
    if binding.status != "active":
        return 409, None
    return 200, binding


def show(action: str, binding: LiveBinding, sql: SqlCounts, **outcome: object) -> None:
    print(
        json.dumps(
            {
                "action": action,
                "binding": {
                    "meeting_id": binding.handle.meeting_id,
                    "origin_session_bound": bool(binding.origin_session),
                    "owner_generation": binding.owner_key[1],
                    "status": binding.status,
                    "snapshot": binding.snapshot,
                    "versions": {
                        "raw": binding.raw_version,
                        "durable": binding.durable_version,
                        "public": binding.public_version,
                    },
                    "event_high_water": {
                        "raw": binding.raw_event_high_water,
                        "public": binding.public_event_high_water,
                    },
                    "capture_fenced": binding.capture_fenced,
                },
                "sql": sql.to_dict(),
                "outcome": outcome,
            },
            sort_keys=True,
        )
    )


async def run() -> None:
    print_contract()
    run_browser_observation_policy_probe()
    await run_shared_transport_adapter_probe()
    with tempfile.TemporaryDirectory(prefix="mtd-phase2-live-owner-prototype-") as directory:
        database = Path(directory) / "prototype.sqlite3"
        store = await Phase2Store.open(database)
        counts = SqlCounts()
        await store._connection.set_trace_callback(counts.observe)
        try:
            await store.allow_email("a@example.com")
            await store.allow_email("b@example.com")
            admitted_a = await store.admit(GoogleIdentity("sub-a", "a@example.com", "A"))
            admitted_a_observer = await store.admit(
                GoogleIdentity("sub-a", "a@example.com", "A")
            )
            admitted_b = await store.admit(GoogleIdentity("sub-b", "b@example.com", "B"))
            assert admitted_a is not None
            assert admitted_a_observer is not None
            assert admitted_b is not None
            account_a, session_a = admitted_a
            _, session_a_observer = admitted_a_observer
            _, session_b = admitted_b

            terminal_handle = await store.workspace(account_a).create_meeting("live")
            await terminal_handle.commit_transcript(
                {
                    "segments": [
                        {
                            "id": "seg_0001",
                            "start": 0.0,
                            "end": 1.0,
                            "speaker": "S01",
                            "text": "pre-terminal durable",
                        }
                    ]
                }
            )
            terminal_document = {
                "segments": [
                    {
                        "id": "seg_0001",
                        "start": 0.0,
                        "end": 2.0,
                        "speaker": "S01",
                        "text": "terminal revision",
                    }
                ]
            }
            read_isolation_handle = await store.workspace(account_a).create_meeting("live")
            await read_isolation_handle.commit_transcript(
                {
                    "segments": [
                        {
                            "id": "seg_0001",
                            "start": 0.0,
                            "end": 1.0,
                            "speaker": "S01",
                            "text": "durable prefix",
                        }
                    ]
                }
            )
            rollback_reads = await held_terminal_read_isolation_probe(
                store,
                read_isolation_handle,
                session_a,
                terminal_document,
                commit=False,
            )
            commit_reads = await held_terminal_read_isolation_probe(
                store,
                read_isolation_handle,
                session_a,
                terminal_document,
                commit=True,
            )
            assert rollback_reads["results_after_transaction"]["snapshot"] == {
                "status": "active",
                "version": 1,
                "text": "durable prefix",
            }
            assert rollback_reads["results_after_transaction"]["list"] == (
                rollback_reads["results_after_transaction"]["snapshot"]
            )
            assert rollback_reads["results_after_transaction"]["auth"] == "a@example.com"
            assert commit_reads["results_after_transaction"]["snapshot"] == {
                "status": "completed",
                "version": 2,
                "text": "terminal revision",
            }
            assert commit_reads["results_after_transaction"]["list"] == (
                commit_reads["results_after_transaction"]["snapshot"]
            )
            assert commit_reads["results_after_transaction"]["auth"] == "a@example.com"
            print(
                json.dumps(
                    {
                        "action": "same_connection_external_read_isolation",
                        "rollback": rollback_reads,
                        "commit": commit_reads,
                        "mixed_tuple_observed": False,
                    },
                    sort_keys=True,
                )
            )
            try:
                await commit_terminal_probe(
                    store,
                    terminal_handle,
                    terminal_document,
                    fail_before_commit=True,
                )
            except SimulatedProcessLoss:
                pass
            rolled_back = await terminal_handle.snapshot()
            assert rolled_back.status == "active"
            assert rolled_back.transcript_version == 1
            assert rolled_back.transcript is not None
            assert rolled_back.transcript["segments"][0]["text"] == "pre-terminal durable"
            terminal_version = await commit_terminal_probe(
                store,
                terminal_handle,
                terminal_document,
                fail_before_commit=False,
            )
            terminal_committed = await terminal_handle.snapshot()
            assert terminal_version == 2
            assert terminal_committed.status == "completed"
            assert terminal_committed.transcript_version == 2
            assert terminal_committed.transcript is not None
            assert terminal_committed.transcript["segments"][0]["text"] == "terminal revision"
            print(
                json.dumps(
                    {
                        "action": "terminal_atomicity",
                        "injected_process_loss": {
                            "status": rolled_back.status,
                            "transcript_version": rolled_back.transcript_version,
                            "text": rolled_back.transcript["segments"][0]["text"],
                        },
                        "committed": {
                            "status": terminal_committed.status,
                            "transcript_version": terminal_committed.transcript_version,
                            "text": terminal_committed.transcript["segments"][0]["text"],
                        },
                        "mixed_state_observed": False,
                    },
                    sort_keys=True,
                )
            )

            finalizer_handle = await store.workspace(account_a).create_meeting("live")
            rolling_document = {
                "segments": [
                    {
                        "id": "seg_0001",
                        "start": 0.0,
                        "end": 1.0,
                        "speaker": "S01",
                        "text": "rolling words",
                    }
                ]
            }
            await finalizer_handle.commit_transcript(rolling_document)
            finalizer_binding = LiveBinding(
                owner_key=(account_a.account_id, account_a.authority_generation),
                origin_session=session_a,
                handle=finalizer_handle,
                snapshot={
                    "status": "active",
                    "transcript_version": 1,
                    "segments": ["rolling words"],
                },
                durable_version=1,
                public_version=1,
                raw_version=1,
            )
            controlled_terminal = ControlledAtomicTerminal(finalizer_handle)
            finalizer_gate = TerminalFinalizerGateProbe(
                finalizer_binding,
                controlled_terminal,
            )
            await finalizer_gate.accept(
                FinalizingPublication(2, "closed", "not_started", rolling_document)
            )
            stop_tail_document = {
                "segments": [
                    {
                        "id": "seg_0001",
                        "start": 0.0,
                        "end": 1.5,
                        "speaker": "S01",
                        "text": "rolling words plus stop tail",
                    }
                ]
            }
            await finalizer_gate.accept(
                FinalizingPublication(3, "closed", "running", stop_tail_document)
            )
            during = await finalizer_handle.snapshot()
            assert during.status == "active"
            assert during.transcript_version == 2
            assert finalizer_binding.public_version == 3
            assert finalizer_binding.snapshot["status"] == "closed"
            assert finalizer_binding.snapshot["finalization_status"] == "running"
            assert finalizer_binding.snapshot["segments"] == ["rolling words plus stop tail"]
            final_document = {
                "segments": [
                    {
                        "id": "seg_0001",
                        "start": 0.0,
                        "end": 2.0,
                        "speaker": "S01",
                        "text": "terminal finalizer words",
                    }
                ]
            }
            terminal_task = asyncio.create_task(
                finalizer_gate.accept(
                    FinalizingPublication(4, "closed", "final", final_document)
                )
            )
            await controlled_terminal.started.wait()
            held = await finalizer_handle.snapshot()
            assert held.status == "active"
            assert held.transcript_version == 2
            assert finalizer_binding.public_version == 3
            controlled_terminal.released.set()
            await terminal_task
            finalized = await finalizer_handle.snapshot()
            assert finalized.status == "completed"
            assert finalized.transcript_version == 3
            assert finalized.transcript == final_document
            assert finalizer_binding.public_version == 4
            assert finalizer_binding.snapshot["segments"] == ["terminal finalizer words"]
            print(
                json.dumps(
                    {
                        "action": "terminal_finalizer_publication_gate",
                        "closed_not_started": {
                            "durable_status": during.status,
                            "public_version": 1,
                            "raw_version": 2,
                        },
                        "closed_running": {
                            "durable_status": during.status,
                            "durable_version": during.transcript_version,
                            "public_version": 3,
                            "raw_version": 3,
                            "segments": ["rolling words plus stop tail"],
                        },
                        "atomic_commit_held": {
                            "durable_status": held.status,
                            "durable_version": held.transcript_version,
                            "public_version": 3,
                            "raw_version": 4,
                        },
                        "terminal_published": {
                            "durable_status": finalized.status,
                            "durable_version": finalized.transcript_version,
                            "public_version": finalizer_binding.public_version,
                            "raw_version": finalizer_binding.raw_version,
                            "segments": finalizer_binding.snapshot["segments"],
                        },
                    },
                    sort_keys=True,
                )
            )

            handle = await store.workspace(account_a).create_meeting("live")
            registry = AccountPartitionedLiveRegistry()
            binding = registry.bind(account_a, session_a, handle)
            counts.reset()
            show("create", binding, counts, status=201)

            origin_status, _ = await authorize(
                store,
                registry,
                session_id=session_a,
                meeting_id=handle.meeting_id,
                operation="frame",
            )
            assert origin_status == 200
            version = await handle.commit_transcript(
                {
                    "segments": [
                        {
                            "id": "seg_0001",
                            "start": 0.0,
                            "end": 1.0,
                            "speaker": "S01",
                            "text": "accepted prefix",
                        }
                    ]
                }
            )
            binding.snapshot = {
                "status": "active",
                "transcript_version": version,
                "segments": ["accepted prefix"],
            }
            binding.raw_version = binding.durable_version = binding.public_version = version
            binding.raw_event_high_water = binding.public_event_high_water = 10
            counts.reset()
            show("origin_revision_durable", binding, counts, status=origin_status, version=version)

            controlled_commit = ControlledCommit(handle)
            bridge = PublicationBridgeProbe(binding, controlled_commit, asyncio.get_running_loop())
            second = RawPublication(
                revision_version=2,
                event_high_water=11,
                document={
                    "segments": [
                        {
                            "id": "seg_0001",
                            "start": 0.0,
                            "end": 2.0,
                            "speaker": "S01",
                            "text": "accepted prefix then durable second",
                        }
                    ]
                },
            )
            third = RawPublication(
                revision_version=3,
                event_high_water=12,
                document={
                    "segments": [
                        {
                            "id": "seg_0001",
                            "start": 0.0,
                            "end": 3.0,
                            "speaker": "S01",
                            "text": "late result after revoke",
                        }
                    ]
                },
            )

            def runtime_thread() -> None:
                bridge.observe_from_runtime_thread(second)
                bridge.observe_from_runtime_thread(third)

            producer = threading.Thread(target=runtime_thread, name="prototype-live-runtime")
            producer.start()
            await asyncio.to_thread(producer.join)
            await bridge.wait_raw(3)
            await controlled_commit.wait_started(2)

            counts.reset()
            held_poll_versions: list[int] = []
            for _ in range(4):
                status, opened = await authorize(
                    store,
                    registry,
                    session_id=session_a_observer,
                    meeting_id=handle.meeting_id,
                    operation="snapshot",
                )
                assert status == 200 and opened is binding
                held_poll_versions.append(int(opened.snapshot["transcript_version"]))
            show(
                "raw_ahead_commit_held",
                binding,
                counts,
                poll_versions=held_poll_versions,
                commit_order=controlled_commit.order,
            )
            assert held_poll_versions == [1, 1, 1, 1]
            assert binding.raw_version == 3
            assert binding.public_version == binding.durable_version == 1
            assert binding.public_event_high_water == 10
            assert counts.to_dict() == {"auth_reads": 4, "content_reads": 0, "writes": 0}

            controlled_commit.release(2)
            await bridge.wait_public(2)
            await controlled_commit.wait_started(3)
            counts.reset()
            released_status, released_binding = await authorize(
                store,
                registry,
                session_id=session_a_observer,
                meeting_id=handle.meeting_id,
                operation="snapshot",
            )
            assert released_status == 200 and released_binding is binding
            show(
                "durable_release_advances_public",
                binding,
                counts,
                poll_version=released_binding.snapshot["transcript_version"],
                commit_order=controlled_commit.order,
            )
            assert released_binding.snapshot["transcript_version"] == 2
            assert binding.durable_version == binding.public_version == 2
            assert binding.public_event_high_water == 11

            counts.reset()
            poll_statuses: list[int] = []
            for index in range(8):
                status, opened = await authorize(
                    store,
                    registry,
                    session_id=session_a_observer,
                    meeting_id=handle.meeting_id,
                    operation="snapshot" if index % 2 == 0 else "events",
                )
                assert opened is binding
                assert opened.snapshot["transcript_version"] == 2
                poll_statuses.append(status)
            show(
                "eight_memory_polls",
                binding,
                counts,
                statuses=poll_statuses,
                content_source="memory",
            )
            assert poll_statuses == [200] * 8
            assert counts.to_dict() == {"auth_reads": 8, "content_reads": 0, "writes": 0}

            counts.reset()
            observer_mutation, _ = await authorize(
                store,
                registry,
                session_id=session_a_observer,
                meeting_id=handle.meeting_id,
                operation="stop",
            )
            foreign_read, _ = await authorize(
                store,
                registry,
                session_id=session_b,
                meeting_id=handle.meeting_id,
                operation="snapshot",
            )
            foreign_mutation, _ = await authorize(
                store,
                registry,
                session_id=session_b,
                meeting_id=handle.meeting_id,
                operation="abort",
            )
            show(
                "isolation",
                binding,
                counts,
                observer_mutation=observer_mutation,
                foreign_read=foreign_read,
                foreign_mutation=foreign_mutation,
            )
            assert (observer_mutation, foreign_read, foreign_mutation) == (403, 404, 404)
            assert binding.snapshot["transcript_version"] == 2

            # The store primitive no longer owns interruption: the lifecycle
            # owner settles every Meeting before revoking Account authority.
            # Model that settled boundary while the stale publication is held.
            for owned in (terminal_handle, read_isolation_handle, finalizer_handle, handle):
                if (await owned.snapshot()).status == "active":
                    await owned.finish("interrupted")
            assert await store.revoke_email("a@example.com") is True
            controlled_commit.release(3)
            await bridge.wait_fenced()
            counts.reset()
            revoked, _ = await authorize(
                store,
                registry,
                session_id=session_a,
                meeting_id=handle.meeting_id,
                operation="snapshot",
            )
            show(
                "revoke_races_serial_flush",
                binding,
                counts,
                status=revoked,
                commit_order=controlled_commit.order,
            )
            assert revoked == 401
            assert counts.to_dict() == {"auth_reads": 1, "content_reads": 0, "writes": 0}
            assert binding.capture_fenced is True
            assert binding.status == "interrupted"
            assert binding.raw_version == 3
            assert binding.durable_version == binding.public_version == 2
            assert binding.public_event_high_water == 11
            assert controlled_commit.order == [2, 3]
            await bridge.close()
            late_raw_version = binding.raw_version
            late_thread = threading.Thread(
                target=bridge.observe_from_runtime_thread,
                args=(
                    RawPublication(
                        revision_version=4,
                        event_high_water=13,
                        document={
                            "segments": [
                                {
                                    "id": "seg_0001",
                                    "start": 0.0,
                                    "end": 4.0,
                                    "speaker": "S01",
                                    "text": "late finalizer after bridge shutdown",
                                }
                            ]
                        },
                    ),
                ),
            )
            late_thread.start()
            late_thread.join()
            await asyncio.sleep(0)
            assert binding.raw_version == late_raw_version
            assert binding.durable_version == binding.public_version == 2
            print(
                json.dumps(
                    {
                        "action": "late_finalizer_after_bridge_shutdown",
                        "observer_enabled": False,
                        "raw_version": binding.raw_version,
                        "durable_version": binding.durable_version,
                        "public_version": binding.public_version,
                        "late_publication_ignored": True,
                    },
                    sort_keys=True,
                )
            )
        finally:
            await store.close()

        connection = sqlite3.connect(database)
        try:
            durable = connection.execute(
                """
                SELECT m.status, t.version, t.document_json
                FROM meetings m
                JOIN meeting_transcripts t
                  ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
                WHERE m.meeting_id = ?
                """
                , (handle.meeting_id,)
            ).fetchone()
        finally:
            connection.close()
        assert durable is not None
        assert durable[0] == "interrupted"
        assert durable[1] == 2
        assert "accepted prefix" in durable[2]
        assert "durable second" in durable[2]
        assert "late result after revoke" not in durable[2]
        print(
            json.dumps(
                {
                    "action": "durable_final",
                    "status": durable[0],
                    "transcript_version": durable[1],
                    "accepted_prefix_preserved": True,
                    "late_result_absent": True,
                },
                sort_keys=True,
            )
        )
        print(
            "VERDICT: PASS — one shared transport preserves legacy/Phase-2 frame, Stop, and error semantics; external reads wait for transaction boundaries; Phase-2 publication waits for durability; finalizer completion, revoke, and shutdown fence late work"
        )


if __name__ == "__main__":
    asyncio.run(run())
