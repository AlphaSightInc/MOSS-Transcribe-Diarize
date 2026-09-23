"""Service-owned host-local Account control over one mode-0600 Unix socket."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import stat
from pathlib import Path
from typing import Any

from .phase2 import DEFAULT_PHASE2_DATABASE_PATH


DEFAULT_PHASE2_CONTROL_SOCKET_PATH = (
    DEFAULT_PHASE2_DATABASE_PATH.parent / "phase2-control.sock"
)
MAX_CONTROL_LINE_BYTES = 16 * 1024
LOGGER = logging.getLogger(__name__)


class Phase2ControlError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        response_bytes: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.response_bytes = response_bytes


class Phase2ControlServer:
    """Thin transport: lifecycle policy remains entirely in AccountLifecycle."""

    def __init__(self, path: str | Path, lifecycle: Any, operator: Any | None = None) -> None:
        self._path = Path(path).expanduser()
        self._lifecycle = lifecycle
        self._operator = operator
        self._server: asyncio.AbstractServer | None = None
        self._socket_identity: tuple[int, int] | None = None
        self._handlers: set[asyncio.Task[None]] = set()

    @property
    def path(self) -> Path:
        return self._path

    async def start(self) -> None:
        if len(os.fsencode(self._path)) >= 104:
            raise Phase2ControlError("Control socket path is too long for this host.")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await self._discard_stale_socket()
        self._server = await asyncio.start_unix_server(
            self._handle,
            path=str(self._path),
            limit=MAX_CONTROL_LINE_BYTES,
        )
        os.chmod(self._path, 0o600)
        found = self._path.stat()
        self._socket_identity = (found.st_dev, found.st_ino)

    async def stop(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            server.close()
            await asyncio.sleep(0)
        handlers = tuple(self._handlers)
        if handlers:
            for handler in handlers:
                handler.cancel()
            await asyncio.gather(*handlers, return_exceptions=True)
        if server is not None:
            await server.wait_closed()
        try:
            found = self._path.stat()
        except FileNotFoundError:
            return
        if self._socket_identity == (found.st_dev, found.st_ino):
            self._path.unlink()

    async def _discard_stale_socket(self) -> None:
        try:
            found = self._path.lstat()
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(found.st_mode):
            raise Phase2ControlError("Control path exists and is not a Unix socket.")
        try:
            reader, writer = await asyncio.open_unix_connection(str(self._path))
        except (ConnectionRefusedError, FileNotFoundError):
            self._path.unlink(missing_ok=True)
            return
        writer.close()
        await writer.wait_closed()
        del reader
        raise Phase2ControlError("Another product process owns the control socket.")

    async def _handle(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._handlers.add(task)
        try:
            try:
                line = await reader.readline()
                if not line or len(line) > MAX_CONTROL_LINE_BYTES or not line.endswith(b"\n"):
                    raise ValueError("invalid control request")
                request = json.loads(line)
                result = await self._execute(request)
                response = {"ok": True, "result": result}
            except Exception as exc:
                response = {"ok": False, "error": _error_code(exc)}
            try:
                writer.write(json.dumps(response, sort_keys=True).encode("utf-8") + b"\n")
                await writer.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            writer.close()
            try:
                try:
                    await writer.wait_closed()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            finally:
                self._handlers.discard(task)

    async def _execute(self, request: object) -> object:
        if not isinstance(request, dict):
            raise ValueError("invalid control request")
        command = request.get("command")
        account_id = request.get("account_id")
        meeting_id = request.get("meeting_id")
        if (
            command == "status"
            and account_id is None
            and meeting_id is None
            and self._operator is not None
        ):
            return await self._operator.snapshot()
        if command == "accounts.list" and account_id is None and meeting_id is None:
            return await self._lifecycle.list_accounts()
        if command == "accounts.revoke" and isinstance(account_id, str) and meeting_id is None:
            try:
                revoked = await self._lifecycle.revoke_account(account_id)
            except Exception as exc:
                await self._observe_mutation(command, "failed", _error_code(exc))
                raise
            await self._observe_mutation(
                command,
                "succeeded" if revoked else "no_change",
                None,
            )
            return {"account_id": account_id, "revoked": revoked}
        if command == "meetings.interrupt" and account_id is None and isinstance(meeting_id, str):
            try:
                interrupted = await self._lifecycle.interrupt_meeting(meeting_id)
            except Exception as exc:
                await self._observe_mutation(command, "failed", _error_code(exc))
                raise
            await self._observe_mutation(
                command,
                "succeeded" if interrupted else "no_change",
                None,
            )
            return {"meeting_id": meeting_id, "interrupted": interrupted}
        raise ValueError("invalid control request")

    async def _observe_mutation(
        self,
        command: str,
        outcome: str,
        error: str | None,
    ) -> None:
        if self._operator is not None:
            try:
                await self._operator.snapshot(
                    operator_mutation=command,
                    mutation_outcome=outcome,
                    mutation_error=error,
                )
            except Exception:
                # Observability is not Account authority. A post-mutation projection failure
                # cannot turn a committed revoke into a false command failure.
                LOGGER.error("Operator mutation observation failed.")


async def request_control(
    path: str | Path,
    command: str,
    account_id: str | None = None,
    *,
    meeting_id: str | None = None,
) -> object:
    """One bounded request; no database is opened by the client process."""

    try:
        reader, writer = await asyncio.open_unix_connection(str(Path(path).expanduser()))
    except OSError as exc:
        raise Phase2ControlError(
            "Phase-2 product control is unavailable.", code="control_unavailable"
        ) from exc
    request = {"command": command}
    if account_id is not None:
        request["account_id"] = account_id
    if meeting_id is not None:
        request["meeting_id"] = meeting_id
    try:
        writer.write(json.dumps(request, sort_keys=True).encode("utf-8") + b"\n")
        await writer.drain()
        line = await reader.readline()
    finally:
        writer.close()
        await writer.wait_closed()
    if not line or len(line) > MAX_CONTROL_LINE_BYTES:
        raise Phase2ControlError(
            "Phase-2 product returned an invalid control response.",
            code="invalid_control_response",
            response_bytes=len(line),
        )
    try:
        response = json.loads(line)
    except Exception as exc:
        raise Phase2ControlError(
            "Phase-2 product returned an invalid control response.",
            code="invalid_control_response",
            response_bytes=len(line),
        ) from exc
    if not isinstance(response, dict) or response.get("ok") is not True:
        code = response.get("error") if isinstance(response, dict) else None
        raise Phase2ControlError(
            code if isinstance(code, str) else "control_request_failed",
            code=code if isinstance(code, str) else "control_request_failed",
        )
    return response.get("result")


def _error_code(exc: Exception) -> str:
    from .phase2_lifecycle import (
        AccountLifecycleSettlementError,
        AccountLifecycleUnavailable,
        MeetingLifecycleSettlementError,
    )

    if isinstance(exc, AccountLifecycleUnavailable):
        return "account_lifecycle_busy"
    if isinstance(exc, AccountLifecycleSettlementError):
        return "account_settlement_failed"
    if isinstance(exc, MeetingLifecycleSettlementError):
        return "meeting_settlement_failed"
    if isinstance(exc, ValueError):
        return "invalid_request"
    return "control_request_failed"


__all__ = [
    "DEFAULT_PHASE2_CONTROL_SOCKET_PATH",
    "Phase2ControlError",
    "Phase2ControlServer",
    "request_control",
]
