"""Content-free control failure facts survive the acceptance collector boundary."""

import asyncio
import errno
import tempfile
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.phase2_control import (
    MAX_CONTROL_LINE_BYTES,
    Phase2ControlError,
    Phase2ControlServer,
)
from moss_transcribe_diarize.phase2_acceptance_external import _control
from moss_transcribe_diarize.phase2_acceptance_measure import _failure_details


def test_missing_control_socket_retains_safe_code_and_nested_errno():
    with tempfile.TemporaryDirectory(prefix="h2e2-") as root:
        missing = Path(root) / "missing.sock"
    with pytest.raises(Phase2ControlError) as caught:
        _control(missing, "status")
    details = _failure_details(caught.value, {})
    assert details["control_code"] == "control_unavailable"
    assert details["errno"] == errno.ENOENT
    assert "missing.sock" not in str(details)


def test_oversized_status_retains_safe_code_and_response_bytes():
    class Operator:
        async def snapshot(self):
            return {"padding": "x" * MAX_CONTROL_LINE_BYTES}

    async def exercise(path):
        server = Phase2ControlServer(path, lifecycle=None, operator=Operator())
        await server.start()
        try:
            with pytest.raises(Phase2ControlError) as caught:
                await asyncio.to_thread(_control, server.path, "status")
            return _failure_details(caught.value, {})
        finally:
            await server.stop()

    with tempfile.TemporaryDirectory(prefix="h2e2-") as root:
        details = asyncio.run(exercise(Path(root) / "s"))
    assert details["control_code"] == "invalid_control_response"
    assert details["response_bytes"] > MAX_CONTROL_LINE_BYTES
    assert "padding" not in str(details)


def test_server_status_failure_retains_allowlisted_code():
    class Operator:
        async def snapshot(self):
            raise RuntimeError("private text must not enter the receipt")

    async def exercise(path):
        server = Phase2ControlServer(path, lifecycle=None, operator=Operator())
        await server.start()
        try:
            with pytest.raises(Phase2ControlError) as caught:
                await asyncio.to_thread(_control, server.path, "status")
            return _failure_details(caught.value, {})
        finally:
            await server.stop()

    with tempfile.TemporaryDirectory(prefix="h2e2-") as root:
        details = asyncio.run(exercise(Path(root) / "s"))
    assert details["control_code"] == "control_request_failed"
    assert "private text" not in str(details)
