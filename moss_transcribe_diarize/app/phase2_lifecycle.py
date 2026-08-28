"""One Account authority lifecycle composed from existing Meeting owners.

The module hides admission counts, enumeration, quiescence, and authority ordering. HTTP
logout and the host-local control adapter cross the same interface; neither can mutate the
store directly around process-owned Live/File work.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from .phase2 import Account, AccountRevoked, Phase2Store, normalize_email


class AccountLifecycleUnavailable(RuntimeError):
    """The requested authority scope is closing or already closed."""


class AccountLifecycleSettlementError(RuntimeError):
    """Owned work could not reach durable terminal truth; authority remains unchanged."""


class _DrainGate:
    def __init__(self) -> None:
        self._state = "open"
        self._active = 0
        self._changed = asyncio.Condition()

    async def enter(self) -> None:
        async with self._changed:
            if self._state != "open":
                raise AccountLifecycleUnavailable(self._state)
            self._active += 1

    async def leave(self) -> None:
        async with self._changed:
            self._active -= 1
            assert self._active >= 0
            self._changed.notify_all()

    async def close(self) -> None:
        async with self._changed:
            if self._state != "open":
                raise AccountLifecycleUnavailable(self._state)
            self._state = "closing"

    async def drain(self) -> None:
        async with self._changed:
            if self._state != "closing":
                raise RuntimeError("only a closing lifecycle scope can drain")
            await self._changed.wait_for(lambda: self._active == 0)
            self._state = "closed"

    async def reopen(self) -> None:
        async with self._changed:
            if self._state not in {"closing", "closed"}:
                raise RuntimeError("only a drained lifecycle scope can reopen")
            self._state = "open"
            self._changed.notify_all()


class AccountLifecycle:
    """Deep Account/session lifecycle; callers supply work, never gate mechanics."""

    unavailable_error = AccountLifecycleUnavailable

    def __init__(
        self,
        store: Phase2Store,
        *,
        live: Any | None,
        files: Any | None,
        audio_archive: Any | None = None,
        live_audio_stages: Any | None = None,
        normal_stop_deadline: float = 5.0,
    ) -> None:
        self._store = store
        self._live = live
        self._files = files
        self._audio_archive = audio_archive
        self._live_audio_stages = live_audio_stages
        self._normal_stop_deadline = normal_stop_deadline
        self._live_control: Any | None = None
        self._session_gates: dict[str, _DrainGate] = {}
        self._account_gates: dict[tuple[str, int], _DrainGate] = {}
        self._registry_lock = asyncio.Lock()

    def bind_live_control(self, control: Any) -> None:
        if self._live_control is not None and self._live_control is not control:
            raise RuntimeError("Live transport control is already bound.")
        self._live_control = control

    @asynccontextmanager
    async def admit_creation(
        self,
        session_id: str,
    ) -> AsyncIterator[Account]:
        """Admit, resolve that exact session, and release after owned-work registration."""

        if not session_id:
            raise AccountRevoked("Sign in required.")
        session_gate = await self._gate(self._session_gates, session_id)
        await session_gate.enter()
        account_gate: _DrainGate | None = None
        try:
            account = await self._store.account_for_session(session_id)
            if account is None:
                raise AccountRevoked("Sign in required.")
            account_key = (account.account_id, account.authority_generation)
            account_gate = await self._gate(self._account_gates, account_key)
            await account_gate.enter()
            try:
                yield account
            finally:
                await account_gate.leave()
        finally:
            await session_gate.leave()

    async def logout(self, session_id: str | None) -> bool:
        """Normally Stop this browser's Live bindings, then revoke only its session."""

        if not session_id:
            raise AccountRevoked("Sign in required.")
        account = await self._store.account_for_session(session_id)
        if account is None:
            raise AccountRevoked("Sign in required.")
        account_gate = await self._gate(
            self._account_gates,
            (account.account_id, account.authority_generation),
        )
        await account_gate.enter()
        session_gate = await self._gate(self._session_gates, session_id)
        owns_close = False
        try:
            await session_gate.close()
            owns_close = True
            await session_gate.drain()
            await self._stop_origin_live(session_id)
            revoked = await self._store.revoke_session(session_id)
            if not revoked:
                raise AccountLifecycleSettlementError("Sign-in session changed during logout.")
            return True
        except BaseException:
            if owns_close:
                await session_gate.reopen()
            raise
        finally:
            await account_gate.leave()

    async def revoke_account(self, email: str) -> bool:
        """Quiesce owned process work, then durably fence the Account generation."""

        target = await self._store.account_revoke_target(email)
        account = target.account
        if account is None:
            return await self._store.finalize_account_revoke(target)
        owner_key = (account.account_id, account.authority_generation)
        account_gate = await self._gate(self._account_gates, owner_key)
        await account_gate.close()
        await account_gate.drain()
        live_bindings = () if self._live is None else self._live.fence_account(owner_key)
        file_entries = () if self._files is None else self._files.fence_account(owner_key)
        try:
            await self._interrupt_account_live(live_bindings)
            if self._files is not None:
                await self._files.settle_fenced(file_entries)
            if self._audio_archive is None:
                raise AccountLifecycleSettlementError(
                    "Account Meeting recovery is unavailable."
                )
            await self._store.recover_active_account_meetings(
                account,
                audio_archive=self._audio_archive,
                live_audio_stages=self._live_audio_stages,
            )
            return await self._store.finalize_account_revoke(target)
        except asyncio.CancelledError:
            # Cancellation is service shutdown.  Keep the old generation closed: work was
            # already fenced, so reopening would let it race startup recovery.
            raise
        except Exception as exc:
            # The old generation deliberately stays closed. The command reports failure and a
            # retry may restart the process/recovery; admitting new work would race uncertainty.
            if isinstance(exc, (AccountRevoked, AccountLifecycleSettlementError)):
                raise
            raise AccountLifecycleSettlementError(
                "Account work could not reach durable terminal truth."
            ) from exc

    async def allow_account(self, email: str) -> dict[str, object]:
        normalized = normalize_email(email)
        if not normalized:
            raise ValueError("email is required.")
        await self._store.allow_email(normalized)
        return {"email": normalized, "enabled": True}

    async def list_accounts(self) -> list[dict[str, object]]:
        return await self._store.list_allowlist()

    async def _stop_origin_live(self, session_id: str) -> None:
        if self._live is None:
            return
        if self._live_control is None:
            raise AccountLifecycleSettlementError("Live transport control is unavailable.")
        for binding in self._live.bindings_for_origin(session_id):
            try:
                await self._live_control.stop(
                    binding,
                    binding.handle.meeting_id,
                    self._normal_stop_deadline,
                )
            except Exception as exc:
                raise AccountLifecycleSettlementError(
                    "Live Meeting could not complete normal Stop."
                ) from exc

    async def _interrupt_account_live(self, bindings: tuple[Any, ...]) -> None:
        if self._live is None:
            return
        if self._live_control is None:
            raise AccountLifecycleSettlementError("Live transport control is unavailable.")
        for binding in bindings:
            await self._live.interrupt_binding(
                binding,
                self._live_control,
                "Account revoked by operator",
            )

    async def _gate(self, registry: dict[Any, _DrainGate], key: Any) -> _DrainGate:
        async with self._registry_lock:
            gate = registry.get(key)
            if gate is None:
                gate = _DrainGate()
                registry[key] = gate
            return gate


__all__ = [
    "AccountLifecycle",
    "AccountLifecycleSettlementError",
    "AccountLifecycleUnavailable",
]
