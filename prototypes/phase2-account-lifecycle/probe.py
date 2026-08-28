"""Throwaway Issue #18 probe: authority drains after owned work settles.

One command, from the repository root:
  PYTHONDONTWRITEBYTECODE=1 uv run --frozen --extra dev python \
    prototypes/phase2-account-lifecycle/probe.py

This deliberately models only the new ordering primitive. Live Stop, audio settlement,
File cancellation, and SQLite authority fencing are exercised through their production
MeetingHandle/Phase2Store contracts rather than reimplemented as algorithms here.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from moss_transcribe_diarize.app.phase2 import (
    AccountRevoked,
    GoogleIdentity,
    MeetingAudio,
    Phase2Store,
)


EMAIL = "owner@example.com"
OTHER_EMAIL = "other@example.com"


class ScopeDraining(RuntimeError):
    pass


class AsyncDrainGate:
    """Prototype primitive: reject new entrants, wait for the exact admitted count."""

    def __init__(self) -> None:
        self.state = "open"
        self.active = 0
        self._changed = asyncio.Condition()

    @asynccontextmanager
    async def admit(self) -> AsyncIterator[None]:
        async with self._changed:
            if self.state != "open":
                raise ScopeDraining(self.state)
            self.active += 1
        try:
            yield
        finally:
            async with self._changed:
                self.active -= 1
                self._changed.notify_all()

    async def close_and_drain(self) -> None:
        async with self._changed:
            if self.state == "closed":
                return
            if self.state != "open":
                raise ScopeDraining(self.state)
            self.state = "closing"
            await self._changed.wait_for(lambda: self.active == 0)
            self.state = "closed"

    async def reopen(self) -> None:
        async with self._changed:
            if self.state not in {"closing", "closed"}:
                raise RuntimeError("only a closing or closed gate can reopen")
            self.state = "open"
            self._changed.notify_all()


async def gate_probe() -> dict[str, object]:
    session = AsyncDrainGate()
    account = AsyncDrainGate()
    admitted = asyncio.Event()
    release = asyncio.Event()
    registered = False

    async def create() -> None:
        nonlocal registered
        async with session.admit(), account.admit():
            admitted.set()
            await release.wait()
            registered = True

    create_task = asyncio.create_task(create())
    await admitted.wait()
    session_drain = asyncio.create_task(session.close_and_drain())
    await asyncio.sleep(0)
    rejected = None
    try:
        async with session.admit():
            pass
    except ScopeDraining as exc:
        rejected = type(exc).__name__
    waited = not session_drain.done()
    release.set()
    await create_task
    await session_drain

    failure_gate = AsyncDrainGate()
    failure = None
    try:
        async with failure_gate.admit():
            raise RuntimeError("injected create failure")
    except RuntimeError as exc:
        failure = str(exc)

    await session.reopen()
    reopen_admitted = False
    async with session.admit():
        reopen_admitted = True

    logout_entered = asyncio.Event()
    release_logout = asyncio.Event()

    async def logout() -> None:
        async with account.admit():
            logout_entered.set()
            await release_logout.wait()

    logout_task = asyncio.create_task(logout())
    await logout_entered.wait()
    revoke_task = asyncio.create_task(account.close_and_drain())
    await asyncio.sleep(0)
    concurrent_rejected = None
    try:
        async with account.admit():
            pass
    except ScopeDraining as exc:
        concurrent_rejected = type(exc).__name__
    revoke_waited = not revoke_task.done()
    release_logout.set()
    await logout_task
    await revoke_task

    return {
        "preadmitted_create_registered": registered,
        "drain_waited_for_registration": waited,
        "new_admission": rejected,
        "session_gate": {"state": session.state, "active": session.active},
        "create_failure": failure,
        "create_failure_gate": {
            "state": failure_gate.state,
            "active": failure_gate.active,
        },
        "logout_failure_reopen_admitted": reopen_admitted,
        "revoke_waited_for_logout": revoke_waited,
        "concurrent_logout": concurrent_rejected,
        "account_gate": {"state": account.state, "active": account.active},
    }


async def publication_fence_probe() -> dict[str, object]:
    """Measure the smallest synchronous fence needed before settlement awaits."""

    publication_ready = asyncio.Event()
    release_publication = asyncio.Event()
    first_settlement_entered = asyncio.Event()
    release_first_settlement = asyncio.Event()
    bindings = {
        "first": {"result_fenced": False, "durable_versions": []},
        "second": {"result_fenced": False, "durable_versions": []},
    }

    async def publish(name: str) -> None:
        publication_ready.set()
        await release_publication.wait()
        if bindings[name]["result_fenced"]:
            return
        bindings[name]["durable_versions"].append(1)

    async def settle_first() -> None:
        first_settlement_entered.set()
        await release_first_settlement.wait()
        raise RuntimeError("injected first settlement failure")

    publication = asyncio.create_task(publish("second"))
    await publication_ready.wait()
    for binding in bindings.values():
        binding["result_fenced"] = True
    settlement = asyncio.create_task(settle_first())
    await first_settlement_entered.wait()
    release_publication.set()
    await publication
    blocked_while_first_held = bindings["second"]["durable_versions"] == []
    release_first_settlement.set()
    failure = None
    try:
        await settlement
    except RuntimeError as exc:
        failure = str(exc)
    return {
        "all_fenced_before_await": all(
            bool(binding["result_fenced"]) for binding in bindings.values()
        ),
        "second_publication_blocked": blocked_while_first_held,
        "first_settlement": failure,
        "bindings": bindings,
    }


async def publication_worker_policy_probe() -> dict[str, object]:
    """Falsify cooperative worker shutdown around thread-backed terminal work."""

    idle_queue: asyncio.Queue[None] = asyncio.Queue()

    async def idle_worker() -> None:
        await idle_queue.get()

    idle = asyncio.create_task(idle_worker())
    await asyncio.sleep(0)
    idle_queue.put_nowait(None)
    await idle

    terminal_entered = asyncio.Event()
    terminal_release = asyncio.Event()
    terminal_state: dict[str, object] = {
        "account_enabled": True,
        "audio_state": "staging",
        "audio_recorded": False,
        "meeting_status": "active",
        "publication_fenced": False,
        "publish_count": 0,
        "raw_status": "closed",
        "raw_stage_present": True,
    }
    order: list[str] = []

    async def terminal_worker() -> None:
        terminal_entered.set()
        await terminal_release.wait()
        terminal_state["publish_count"] = 1
        terminal_state["audio_state"] = "available"
        terminal_state["audio_recorded"] = True
        order.append("audio_published")
        terminal_state["raw_stage_present"] = False
        order.append("raw_discarded")
        terminal_state["meeting_status"] = "completed"
        order.append("meeting_completed")

    terminal = asyncio.create_task(terminal_worker())
    await terminal_entered.wait()
    terminal_state["publication_fenced"] = True
    order.append("fence")

    async def revoke_after_join() -> None:
        await asyncio.gather(terminal)
        order.append("worker_joined")
        terminal_state["account_enabled"] = False
        order.append("authority_disabled")

    service_revoke = asyncio.create_task(revoke_after_join())

    async def transport_handler() -> None:
        await asyncio.shield(service_revoke)

    handler = asyncio.create_task(transport_handler())
    await asyncio.sleep(0)
    handler.cancel()
    await asyncio.gather(handler, return_exceptions=True)

    async def lifecycle_shutdown() -> None:
        await asyncio.gather(service_revoke)

    shutdown = asyncio.create_task(lifecycle_shutdown())
    await asyncio.sleep(0)
    held = {
        "account_enabled": terminal_state["account_enabled"],
        "audio_recorded": terminal_state["audio_recorded"],
        "audio_state": terminal_state["audio_state"],
        "handler_cancelled": handler.cancelled(),
        "lifecycle_shutdown_waiting": not shutdown.done(),
        "meeting_status": terminal_state["meeting_status"],
        "publication_fenced": terminal_state["publication_fenced"],
        "raw_status": terminal_state["raw_status"],
        "raw_stage_present": terminal_state["raw_stage_present"],
        "service_revoke_cancelled": service_revoke.cancelled(),
        "service_revoke_waiting": not service_revoke.done(),
        "worker_cancelled": terminal.cancelled(),
        "worker_done": terminal.done(),
    }
    terminal_release.set()
    await shutdown
    settled = dict(terminal_state)
    settled.update(
        {
            "order": order,
            "handler_cancelled": handler.cancelled(),
            "lifecycle_shutdown_done": shutdown.done(),
            "service_revoke_cancelled": service_revoke.cancelled(),
            "service_revoke_done": service_revoke.done(),
            "worker_cancelled": terminal.cancelled(),
            "worker_done": terminal.done(),
        }
    )

    return {
        "idle_exit": {
            "cancelled": idle.cancelled(),
            "done": idle.done(),
            "exit_signal": "queued",
        },
        "terminal_audio": {
            "held": held,
            "settled": settled,
        },
    }


async def committed_mutation_fence_probe(path: Path) -> dict[str, object]:
    """Hold after real COMMIT; fence must join and converge before terminal truth."""

    first_document = {"segments": [{"text": "accepted before fence"}]}
    queued_document = {"segments": [{"text": "queued but never admitted"}]}
    store = await Phase2Store.open(path)
    try:
        await store.allow_email(EMAIL)
        admitted = await store.admit(GoogleIdentity("commit-owner", EMAIL, "Owner"))
        assert admitted is not None
        account, _ = admitted
        handle = await store.workspace(account).create_meeting("live")
        queue: asyncio.Queue[dict[str, object] | None] = asyncio.Queue()
        commit_completed = asyncio.Event()
        release_commit_result = asyncio.Event()
        publication_fenced = False
        durable_document: dict[str, object] = {"segments": []}
        durable_version = 0
        admitted_commits = 0
        skipped_documents: list[dict[str, object]] = []

        async def commit_then_pause(document: dict[str, object]) -> int:
            version = await handle.commit_transcript(document)
            commit_completed.set()
            await release_commit_result.wait()
            return version

        async def worker() -> None:
            nonlocal admitted_commits, durable_document, durable_version
            while True:
                publication = await queue.get()
                if publication is None:
                    return
                if publication_fenced:
                    skipped_documents.append(publication)
                    continue
                admitted_commits += 1
                durable_version = await commit_then_pause(publication)
                durable_document = publication

        queue.put_nowait(first_document)
        publication_worker = asyncio.create_task(worker())
        await commit_completed.wait()
        queue.put_nowait(queued_document)
        publication_fenced = True
        queue.put_nowait(None)

        connection = sqlite3.connect(path)
        try:
            held_row = connection.execute(
                """
                SELECT m.status, t.version, t.document_json
                FROM meetings m
                JOIN meeting_transcripts t
                  ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
                WHERE m.meeting_id = ?
                """,
                (handle.meeting_id,),
            ).fetchone()
        finally:
            connection.close()
        assert held_row is not None
        held = {
            "admitted_commits": admitted_commits,
            "binding_document": durable_document,
            "binding_version": durable_version,
            "db_document": json.loads(held_row[2]),
            "db_status": held_row[0],
            "db_version": held_row[1],
            "publication_fenced": publication_fenced,
            "queued_count": queue.qsize(),
            "worker_cancelled": publication_worker.cancelled(),
            "worker_done": publication_worker.done(),
        }

        release_commit_result.set()
        await publication_worker
        await handle.finish("interrupted")
        connection = sqlite3.connect(path)
        try:
            final_row = connection.execute(
                """
                SELECT m.status, t.version, t.document_json
                FROM meetings m
                JOIN meeting_transcripts t
                  ON t.account_id = m.account_id AND t.meeting_id = m.meeting_id
                WHERE m.meeting_id = ?
                """,
                (handle.meeting_id,),
            ).fetchone()
        finally:
            connection.close()
        assert final_row is not None
        return {
            "held_after_real_commit": held,
            "settled": {
                "admitted_commits": admitted_commits,
                "binding_document": durable_document,
                "binding_version": durable_version,
                "db_document": json.loads(final_row[2]),
                "db_status": final_row[0],
                "db_version": final_row[1],
                "skipped_documents": skipped_documents,
                "worker_cancelled": publication_worker.cancelled(),
                "worker_done": publication_worker.done(),
            },
        }
    finally:
        await store.close()


async def service_owned_file_probe() -> dict[str, object]:
    """Measure handler cancellation while a fenced File runner remains held."""

    runner_entered = asyncio.Event()
    runner_release = asyncio.Event()
    state: dict[str, object] = {
        "account_enabled": True,
        "input_present": True,
        "meeting_status": "active",
        "registry_entry": True,
        "runner_done": False,
    }

    async def runner() -> None:
        runner_entered.set()
        await runner_release.wait()
        state["runner_done"] = True

    runner_task = asyncio.create_task(runner())
    await runner_entered.wait()

    async def file_task() -> None:
        try:
            await asyncio.shield(runner_task)
        except asyncio.CancelledError:
            await runner_task
            state["input_present"] = False
            state["registry_entry"] = False
            raise

    owned_file = asyncio.create_task(file_task())
    await asyncio.sleep(0)

    async def revoke_settlement() -> None:
        owned_file.cancel()
        await asyncio.gather(owned_file, return_exceptions=True)
        state["meeting_status"] = "interrupted"
        state["account_enabled"] = False

    service_revoke = asyncio.create_task(revoke_settlement())

    async def transport_handler() -> None:
        await asyncio.shield(service_revoke)

    handler = asyncio.create_task(transport_handler())
    await asyncio.sleep(0)
    handler.cancel()
    await asyncio.gather(handler, return_exceptions=True)

    async def lifecycle_shutdown() -> None:
        await asyncio.gather(service_revoke)

    shutdown = asyncio.create_task(lifecycle_shutdown())
    await asyncio.sleep(0)
    held = dict(state)
    held.update(
        {
            "file_task_cancelled": owned_file.cancelled(),
            "file_task_done": owned_file.done(),
            "handler_cancelled": handler.cancelled(),
            "lifecycle_shutdown_waiting": not shutdown.done(),
            "service_revoke_cancelled": service_revoke.cancelled(),
            "service_revoke_waiting": not service_revoke.done(),
        }
    )
    runner_release.set()
    await shutdown
    settled = dict(state)
    settled.update(
        {
            "file_task_cancelled": owned_file.cancelled(),
            "file_task_done": owned_file.done(),
            "handler_cancelled": handler.cancelled(),
            "lifecycle_shutdown_done": shutdown.done(),
            "service_revoke_cancelled": service_revoke.cancelled(),
            "service_revoke_done": service_revoke.done(),
        }
    )
    return {"held": held, "settled": settled}


@dataclass
class ControlledMeeting:
    handle: object
    origin_session: str


async def provision(path: Path):
    store = await Phase2Store.open(path)
    try:
        await store.allow_email(EMAIL)
        first = await store.admit(GoogleIdentity("owner-sub", EMAIL, "Owner"))
        second = await store.admit(GoogleIdentity("owner-sub", EMAIL, "Owner"))
        await store.allow_email(OTHER_EMAIL)
        other = await store.admit(GoogleIdentity("other-sub", OTHER_EMAIL, "Other"))
        assert first is not None and second is not None and other is not None
        return store, first, second, other
    except BaseException:
        await store.close()
        raise


async def stop_origin(
    meetings: list[ControlledMeeting], session_id: str, fail_id: str | None = None
) -> list[str]:
    """Stand-in boundary for the existing shared Live normal-Stop operation."""

    settled: list[str] = []
    for controlled in meetings:
        if controlled.origin_session != session_id:
            continue
        if controlled.handle.meeting_id == fail_id:
            raise RuntimeError("injected durable Stop refusal")
        if (await controlled.handle.snapshot()).status == "active":
            await controlled.handle.record_audio_unavailable()
            await controlled.handle.finish("completed")
            settled.append(controlled.handle.meeting_id)
    return settled


def durable_state(path: Path) -> dict[str, object]:
    connection = sqlite3.connect(path)
    try:
        accounts = connection.execute(
            "SELECT account_id, enabled, authority_generation FROM accounts ORDER BY account_id"
        ).fetchall()
        meetings = connection.execute(
            "SELECT account_id, meeting_id, status FROM meetings ORDER BY account_id, meeting_id"
        ).fetchall()
        sessions = connection.execute(
            "SELECT account_id, session_id FROM sign_in_sessions ORDER BY account_id, session_id"
        ).fetchall()
        audio = connection.execute(
            "SELECT meeting_id, state FROM meeting_audio ORDER BY meeting_id"
        ).fetchall()
        return {
            "accounts": accounts,
            "meetings": meetings,
            "sessions": sessions,
            "audio": audio,
        }
    finally:
        connection.close()


async def ordering_probe(path: Path) -> dict[str, object]:
    store, (account, session), (_, observer_session), (other, other_session) = (
        await provision(path)
    )
    try:
        workspace = store.workspace(account)
        first = await workspace.create_meeting("live")
        second = await workspace.create_meeting("live")
        observed = await workspace.create_meeting("live")
        other_handle = await store.workspace(other).create_meeting("live")
        controlled = [
            ControlledMeeting(first, session),
            ControlledMeeting(second, session),
            ControlledMeeting(observed, observer_session),
        ]

        settled = await stop_origin(controlled, session)
        expected_settled = [first.meeting_id, second.meeting_id]
        settled_statuses = {
            handle.meeting_id: (await handle.snapshot()).status
            for handle in (first, second)
        }
        logout_revoked = await store.revoke_session(session)
        observer_status_after_logout = (await observed.snapshot()).status
        origin_valid_after_logout = await store.account_for_session(session) is not None
        observer_valid_after_logout = (
            await store.account_for_session(observer_session) is not None
        )

        failing = await workspace.create_meeting("live")
        admitted = await store.admit(GoogleIdentity("owner-sub", EMAIL, "Owner"))
        assert admitted is not None
        failing_session = admitted[1]
        failure = None
        try:
            await stop_origin(
                [ControlledMeeting(failing, failing_session)],
                failing_session,
                failing.meeting_id,
            )
        except RuntimeError as exc:
            failure = str(exc)
        failing_session_valid_after_failure = (
            await store.account_for_session(failing_session) is not None
        )

        # Prototype the only truthful interruption transition after File audio has
        # already reached verified complete metadata: change state only, then finish.
        audio_boundary = await workspace.create_meeting("file")
        available = MeetingAudio(
            state="available",
            relative_path=f"{account.account_id}/{audio_boundary.meeting_id}/audio.mp3",
            byte_count=17,
            duration_ms=125,
            format="mp3",
            sample_rate_hz=16_000,
            channels=1,
            bit_rate_bps=48_000,
        )
        await store._commit_meeting_audio(
            account.account_id,
            account.authority_generation,
            audio_boundary.meeting_id,
            available,
        )
        async with store._mutation():
            cursor = await store._connection.execute(
                """
                UPDATE meeting_audio SET state = 'partial'
                WHERE account_id = ? AND meeting_id = ? AND state = 'available'
                  AND EXISTS (
                    SELECT 1 FROM meetings
                    WHERE account_id = ? AND meeting_id = ? AND status = 'active'
                  )
                """,
                (
                    account.account_id,
                    audio_boundary.meeting_id,
                    account.account_id,
                    audio_boundary.meeting_id,
                ),
            )
            audio_downgraded = cursor.rowcount == 1
            await cursor.close()
        await audio_boundary.finish("interrupted")
        audio_boundary_snapshot = await audio_boundary.snapshot()
        interrupted_audio = audio_boundary_snapshot.audio

        # Cleanup uncertainty must keep both Meeting and Account authority unchanged.
        unregistered = await workspace.create_meeting("live")
        cleanup_failure = None
        try:
            raise OSError("injected persistent raw-stage cleanup failure")
        except OSError as exc:
            cleanup_failure = str(exc)
        uncertain_before_retry = (await unregistered.snapshot()).status
        authority_before_retry = await store.account_for_session(observer_session) is not None
        await unregistered.record_audio_unavailable()
        await unregistered.finish("interrupted")
        uncertain_after_retry = (await unregistered.snapshot()).status

        old_generation = account.authority_generation
        for handle in (observed, failing):
            if (await handle.snapshot()).status == "active":
                await handle.record_audio_unavailable()
                await handle.finish("interrupted")
        await store.revoke_email(EMAIL)

        late = "unexpected-success"
        try:
            await failing.commit_transcript({"segments": [{"text": "late"}]})
        except AccountRevoked:
            late = "AccountRevoked"

        await store.allow_email(EMAIL)
        fresh = await store.admit(GoogleIdentity("owner-sub", EMAIL, "Owner"))
        assert fresh is not None
        fresh_account, fresh_session = fresh
        stale = "unexpected-success"
        try:
            await observed.commit_transcript({"segments": [{"text": "stale"}]})
        except AccountRevoked:
            stale = "AccountRevoked"
        fresh_handle = await store.workspace(fresh_account).create_meeting("live")

        result = {
            "logout": {
                "settled": settled,
                "expected_settled": expected_settled,
                "settled_statuses": settled_statuses,
                "session_revoked": logout_revoked,
                "origin_valid": origin_valid_after_logout,
                "observer_valid": observer_valid_after_logout,
                "observer_meeting": observer_status_after_logout,
            },
            "logout_failure": {
                "error": failure,
                "session_valid": failing_session_valid_after_failure,
            },
            "audio_boundary": {
                "downgraded": audio_downgraded,
                "meeting_status": audio_boundary_snapshot.status,
                "audio": None if interrupted_audio is None else interrupted_audio.to_dict(),
                "expected_metadata": available.to_dict(),
            },
            "unregistered_recovery": {
                "cleanup_failure": cleanup_failure,
                "status_before_retry": uncertain_before_retry,
                "authority_before_retry": authority_before_retry,
                "status_after_retry": uncertain_after_retry,
            },
            "revoke": {
                "late_commit": late,
                "old_sessions_valid": [
                    await store.account_for_session(observer_session) is not None,
                    await store.account_for_session(failing_session) is not None,
                ],
                "old_generation": old_generation,
                "fresh_generation": fresh_account.authority_generation,
                "stale_after_reallow": stale,
                "fresh_session_valid": (
                    await store.account_for_session(fresh_session) is not None
                ),
                "fresh_meeting": (await fresh_handle.snapshot()).status,
            },
            "other_account": {
                "session_valid": await store.account_for_session(other_session) is not None,
                "meeting": (await other_handle.snapshot()).status,
            },
        }
    finally:
        await store.close()
    result["durable"] = durable_state(path)
    return result


async def main() -> None:
    contract = {
        "structural_question": (
            "How can admitted Meeting creation and terminal settlement finish while captured "
            "authority is valid, before logout or Account revoke removes that authority?"
        ),
        "minimum_primitives": [
            {
                "primitive": "counted async drain gate",
                "boundary": "one Sign-in session and one Account generation, in process only",
                "irreducible": "a boolean cannot distinguish zero admitted creators from one",
            },
            {
                "primitive": "existing owned-work controls",
                "boundary": (
                    "shared Live Stop, synchronous publication-admission fence, cooperative "
                    "worker join, indexed File tasks, and fixed owner/mode recovery"
                ),
                "irreducible": (
                    "only those owners can quiesce inference and settle audio truth; cancelling "
                    "an accepted mutation cannot prove whether SQLite COMMIT already became durable"
                ),
            },
            {
                "primitive": "service-owned revoke settlement task",
                "boundary": (
                    "one accepted Account revoke from fence installation through final authority "
                    "mutation, held strongly and joined by product lifespan"
                ),
                "irreducible": (
                    "a cancellable socket handler cannot own filesystem threads, File cleanup, "
                    "or durable terminal truth"
                ),
            },
            {
                "primitive": "final SQLite authority transaction",
                "boundary": "Account row and all sessions after a zero-active-row assertion",
                "irreducible": "it is the durable generation fence for every captured handle",
            },
            {
                "primitive": "Unix control transport",
                "boundary": "host-local command transport only; it owns no lifecycle policy",
                "irreducible": "an external process cannot safely coordinate in-process work",
            },
        ],
        "invariants": [
            "admission spans authority resolution through task or binding registration",
            "logout settles only Live Meetings originated by one Sign-in session",
            "logout failure keeps that session valid and reopens only its session gate",
            "Account revoke settles all owned work before generation/session mutation",
            "interruption downgrades verified complete audio by state only before terminal status",
            "cleanup uncertainty leaves Meeting active and durable Account authority unchanged",
            "a synchronous Live result fence precedes every settlement await",
            "the fence blocks new publication admission and skips work still queued at the fence",
            "an already-admitted SQLite mutation or thread-backed operation is joined, never cancelled",
            "durable SQLite and binding document converge before interrupted terminal truth and return",
            "terminal audio publication is joined before authority changes",
            "handler or client cancellation cannot cancel an accepted Account settlement",
            "product lifespan joins accepted revoke settlement before Live, File, or Store shutdown",
            "Account interruption persists the synchronized durable transcript, never still-queued raw words",
            "old handles never revive after reallow and other Accounts never mutate",
        ],
        "assumptions_unknowns": [
            "Live and File terminal/audio algorithms are settled by Issues 13, 16, and 17",
            "socket framing and browser rendering are implementation checks, not policy proxies",
            "production cancellation, socket, and browser behavior is measured by focused tests",
        ],
        "falsifier": (
            "A drain misses a pre-admitted registration; a failed creator leaks the count; "
            "logout failure revokes authority; revoke leaves active owned work; late/stale work "
            "commits; complete audio stays available after interruption; cleanup uncertainty "
            "becomes terminal; terminal audio is orphaned or cancelled; authority changes before "
            "its worker joins; handler cancellation abandons Live/File cleanup; a real COMMIT is "
            "cancelled before binding convergence; queued post-fence text commits; reallow reuses "
            "the old generation; or another Account changes."
        ),
        "tool_decisions": [
            {
                "tool": "asyncio interleaving probe",
                "necessary": (
                    "the new uncertainties are admission-versus-drain ordering and cooperative "
                    "publication admission/worker shutdown"
                ),
                "decision_change": (
                    "any missed registration, leaked count, cancelled accepted mutation, queued "
                    "post-fence commit, or authority mutation before worker join rejects the design"
                ),
            },
            {
                "tool": "production Phase2Store and MeetingHandle",
                "necessary": "generation, session, transcript, and audio truth are SQLite behavior",
                "decision_change": "any late/stale commit or cross-Account mutation rejects ordering",
            },
            {
                "tool": "focused production integration tests after PASS",
                "necessary": "real shared Stop, cancellation, socket, and browser paths cross adapters",
                "decision_change": "a path mismatch rejects or deepens the production seam",
            },
        ],
    }
    with tempfile.TemporaryDirectory(prefix="moss-phase2-lifecycle-") as temporary:
        state: dict[str, object] = {
            "contract": contract,
            "gate": await gate_probe(),
            "publication_fence": await publication_fence_probe(),
            "publication_worker_policy": await publication_worker_policy_probe(),
            "committed_mutation_fence": await committed_mutation_fence_probe(
                Path(temporary) / "committed.sqlite3"
            ),
            "service_owned_file": await service_owned_file_probe(),
            "ordering": await ordering_probe(Path(temporary) / "phase2.sqlite3"),
        }
    gate = state["gate"]
    ordering = state["ordering"]
    publication_fence = state["publication_fence"]
    publication_worker_policy = state["publication_worker_policy"]
    idle_exit = publication_worker_policy["idle_exit"]
    terminal_audio = publication_worker_policy["terminal_audio"]
    committed_mutation_fence = state["committed_mutation_fence"]
    service_owned_file = state["service_owned_file"]
    audio_boundary = ordering["audio_boundary"]
    preserved_audio = dict(audio_boundary["expected_metadata"])
    preserved_audio["state"] = "partial"
    passed = (
        gate["preadmitted_create_registered"] is True
        and gate["drain_waited_for_registration"] is True
        and gate["new_admission"] == "ScopeDraining"
        and gate["create_failure_gate"] == {"state": "open", "active": 0}
        and gate["logout_failure_reopen_admitted"] is True
        and gate["revoke_waited_for_logout"] is True
        and gate["concurrent_logout"] == "ScopeDraining"
        and ordering["logout"]["settled"] == ordering["logout"]["expected_settled"]
        and set(ordering["logout"]["settled_statuses"].values()) == {"completed"}
        and ordering["logout"]["origin_valid"] is False
        and ordering["logout"]["observer_valid"] is True
        and ordering["logout"]["observer_meeting"] == "active"
        and ordering["logout_failure"]["session_valid"] is True
        and audio_boundary["downgraded"] is True
        and audio_boundary["meeting_status"] == "interrupted"
        and audio_boundary["audio"] == preserved_audio
        and ordering["unregistered_recovery"]
        == {
            "cleanup_failure": "injected persistent raw-stage cleanup failure",
            "status_before_retry": "active",
            "authority_before_retry": True,
            "status_after_retry": "interrupted",
        }
        and publication_fence["all_fenced_before_await"] is True
        and publication_fence["second_publication_blocked"] is True
        and publication_fence["first_settlement"]
        == "injected first settlement failure"
        and idle_exit
        == {"cancelled": False, "done": True, "exit_signal": "queued"}
        and committed_mutation_fence["held_after_real_commit"]
        == {
            "admitted_commits": 1,
            "binding_document": {"segments": []},
            "binding_version": 0,
            "db_document": {"segments": [{"text": "accepted before fence"}]},
            "db_status": "active",
            "db_version": 1,
            "publication_fenced": True,
            "queued_count": 2,
            "worker_cancelled": False,
            "worker_done": False,
        }
        and committed_mutation_fence["settled"]
        == {
            "admitted_commits": 1,
            "binding_document": {"segments": [{"text": "accepted before fence"}]},
            "binding_version": 1,
            "db_document": {"segments": [{"text": "accepted before fence"}]},
            "db_status": "interrupted",
            "db_version": 1,
            "skipped_documents": [
                {"segments": [{"text": "queued but never admitted"}]}
            ],
            "worker_cancelled": False,
            "worker_done": True,
        }
        and terminal_audio["held"]
        == {
            "account_enabled": True,
            "audio_recorded": False,
            "audio_state": "staging",
            "handler_cancelled": True,
            "lifecycle_shutdown_waiting": True,
            "meeting_status": "active",
            "publication_fenced": True,
            "raw_status": "closed",
            "raw_stage_present": True,
            "service_revoke_cancelled": False,
            "service_revoke_waiting": True,
            "worker_cancelled": False,
            "worker_done": False,
        }
        and terminal_audio["settled"]
        == {
            "account_enabled": False,
            "audio_recorded": True,
            "audio_state": "available",
            "handler_cancelled": True,
            "lifecycle_shutdown_done": True,
            "meeting_status": "completed",
            "order": [
                "fence",
                "audio_published",
                "raw_discarded",
                "meeting_completed",
                "worker_joined",
                "authority_disabled",
            ],
            "publication_fenced": True,
            "publish_count": 1,
            "raw_status": "closed",
            "raw_stage_present": False,
            "service_revoke_cancelled": False,
            "service_revoke_done": True,
            "worker_cancelled": False,
            "worker_done": True,
        }
        and service_owned_file["held"]
        == {
            "account_enabled": True,
            "file_task_cancelled": False,
            "file_task_done": False,
            "handler_cancelled": True,
            "input_present": True,
            "lifecycle_shutdown_waiting": True,
            "meeting_status": "active",
            "registry_entry": True,
            "runner_done": False,
            "service_revoke_cancelled": False,
            "service_revoke_waiting": True,
        }
        and service_owned_file["settled"]
        == {
            "account_enabled": False,
            "file_task_cancelled": True,
            "file_task_done": True,
            "handler_cancelled": True,
            "input_present": False,
            "lifecycle_shutdown_done": True,
            "meeting_status": "interrupted",
            "registry_entry": False,
            "runner_done": True,
            "service_revoke_cancelled": False,
            "service_revoke_done": True,
        }
        and ordering["revoke"]["late_commit"] == "AccountRevoked"
        and ordering["revoke"]["old_sessions_valid"] == [False, False]
        and ordering["revoke"]["fresh_generation"]
        == ordering["revoke"]["old_generation"] + 1
        and ordering["revoke"]["stale_after_reallow"] == "AccountRevoked"
        and ordering["other_account"] == {"session_valid": True, "meeting": "active"}
    )
    state["verdict"] = {
        "result": "PASS" if passed else "FAIL",
        "derived_from": {
            "gate_results": gate,
            "authority_results": {
                "logout": ordering["logout"],
                "logout_failure": ordering["logout_failure"],
                "audio_boundary": audio_boundary,
                "unregistered_recovery": ordering["unregistered_recovery"],
                "publication_fence": publication_fence,
                "publication_worker_policy": publication_worker_policy,
                "committed_mutation_fence": committed_mutation_fence,
                "service_owned_file": service_owned_file,
                "revoke": ordering["revoke"],
                "other_account": ordering["other_account"],
            },
        },
        "production_decision": (
            "Use one lifecycle module with session/account-generation drain gates; compose existing "
            "Live/File settlement, then perform the final durable authority mutation."
        ),
    }
    print(json.dumps(state, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
