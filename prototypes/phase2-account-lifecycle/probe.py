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

from moss_transcribe_diarize.app.phase2 import AccountRevoked, GoogleIdentity, Phase2Store


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
                "session_revoked": logout_revoked,
                "origin_valid": origin_valid_after_logout,
                "observer_valid": observer_valid_after_logout,
                "observer_meeting": observer_status_after_logout,
            },
            "logout_failure": {
                "error": failure,
                "session_valid": failing_session_valid_after_failure,
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
                "boundary": "shared Live Stop and indexed File task registrations",
                "irreducible": "only those owners can quiesce inference and settle audio truth",
            },
            {
                "primitive": "final SQLite authority transaction",
                "boundary": "Account row, all sessions, and residual active Meetings",
                "irreducible": "it is the durable generation fence for every captured handle",
            },
            {
                "primitive": "service-owned Unix control command",
                "boundary": "host-local command transport only; it owns no lifecycle policy",
                "irreducible": "an external process cannot safely coordinate in-process work",
            },
        ],
        "invariants": [
            "admission spans authority resolution through task or binding registration",
            "logout settles only Live Meetings originated by one Sign-in session",
            "logout failure keeps that session valid and reopens only its session gate",
            "Account revoke settles all owned work before generation/session mutation",
            "old handles never revive after reallow and other Accounts never mutate",
        ],
        "assumptions_unknowns": [
            "Live and File terminal/audio algorithms are settled by Issues 13, 16, and 17",
            "socket framing and browser rendering are implementation checks, not policy proxies",
            "production cancellation behavior remains unmeasured until focused integration tests",
        ],
        "falsifier": (
            "A drain misses a pre-admitted registration; a failed creator leaks the count; "
            "logout failure revokes authority; revoke leaves active owned work; late/stale work "
            "commits; reallow reuses the old generation; or another Account changes."
        ),
        "tool_decisions": [
            {
                "tool": "asyncio interleaving probe",
                "necessary": "the new uncertainty is admission-versus-drain ordering",
                "decision_change": "any missed registration or leaked count rejects the gate",
            },
            {
                "tool": "production Phase2Store and MeetingHandle",
                "necessary": "generation, session, transcript, and audio truth are SQLite behavior",
                "decision_change": "any late/stale commit or cross-Account mutation rejects ordering",
            },
            {
                "tool": "focused production integration tests after PASS",
                "necessary": "real shared Stop, cancellation, socket, and browser paths are not modeled",
                "decision_change": "a path mismatch rejects or deepens the production seam",
            },
        ],
    }
    with tempfile.TemporaryDirectory(prefix="moss-phase2-lifecycle-") as temporary:
        state: dict[str, object] = {
            "contract": contract,
            "gate": await gate_probe(),
            "ordering": await ordering_probe(Path(temporary) / "phase2.sqlite3"),
        }
    gate = state["gate"]
    ordering = state["ordering"]
    passed = (
        gate["preadmitted_create_registered"] is True
        and gate["drain_waited_for_registration"] is True
        and gate["new_admission"] == "ScopeDraining"
        and gate["create_failure_gate"] == {"state": "open", "active": 0}
        and gate["logout_failure_reopen_admitted"] is True
        and gate["revoke_waited_for_logout"] is True
        and gate["concurrent_logout"] == "ScopeDraining"
        and ordering["logout"]["origin_valid"] is False
        and ordering["logout"]["observer_valid"] is True
        and ordering["logout"]["observer_meeting"] == "active"
        and ordering["logout_failure"]["session_valid"] is True
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
