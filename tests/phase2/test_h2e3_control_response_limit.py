"""The production control reply and operator relay have a separate 1 MiB bound."""

import asyncio
import json
import runpy
import socket
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from moss_transcribe_diarize import phase2_acceptance_external as external
from moss_transcribe_diarize.app.phase2_control import (
    MAX_CONTROL_LINE_BYTES,
    Phase2ControlError,
    Phase2ControlServer,
    request_control,
)

MAX_CONTROL_RESPONSE_BYTES = 1_048_576


def test_production_growth_states(capsys):
    run = Path(__file__).resolve().parents[2] / "prototypes/round6-h2e-control/run.py"
    main = runpy.run_path(str(run))["main"]
    asyncio.run(main(assert_h2e3=True))
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 60
    assert sum(row["request"] == "PASS" for row in rows) == 60


@pytest.mark.parametrize("wire_bytes", [1_048_576, 1_048_577])
def test_control_response_byte_boundary(wire_bytes):
    empty = json.dumps({"ok": True, "result": {"padding": ""}}, sort_keys=True).encode() + b"\n"
    padding = "x" * (wire_bytes - len(empty))

    class Operator:
        async def snapshot(self):
            return {"padding": padding}

    async def exercise(path):
        server = Phase2ControlServer(path, lifecycle=None, operator=Operator())
        await server.start()
        try:
            if wire_bytes == MAX_CONTROL_RESPONSE_BYTES:
                result = await request_control(server.path, "status")
                assert result == {"padding": padding}
            else:
                with pytest.raises(Phase2ControlError) as caught:
                    await request_control(server.path, "status")
                assert caught.value.code == "invalid_control_response"
                assert caught.value.response_bytes == wire_bytes
        finally:
            await server.stop()

    with tempfile.TemporaryDirectory(prefix="h2e3-") as root:
        asyncio.run(exercise(Path(root) / "s"))


@pytest.mark.parametrize("wire_bytes", [MAX_CONTROL_LINE_BYTES + 1, MAX_CONTROL_RESPONSE_BYTES])
def test_admin_relay_preserves_large_in_limit_status(monkeypatch, wire_bytes):
    empty = json.dumps({"ok": True, "result": {"padding": ""}}, sort_keys=True).encode() + b"\n"
    result = {"padding": "x" * (wire_bytes - len(empty))}
    response = json.dumps({"ok": True, "result": result}, sort_keys=True).encode() + b"\n"
    assert len(response) == wire_bytes

    def cli(argv, **kwargs):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(argv[2])
            client.sendall(b'{"command": "status"}\n')
            with client.makefile("rb") as incoming:
                value = json.loads(incoming.readline())["result"]
        return subprocess.CompletedProcess(argv, 0, (json.dumps(value) + "\n").encode(), b"")

    monkeypatch.setattr(external.subprocess, "run", cli)
    with tempfile.TemporaryDirectory(prefix="h2e3-") as root:
        upstream_path = Path(root) / "upstream"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.bind(str(upstream_path))
            upstream.listen(1)
            upstream.settimeout(5)

            def serve():
                connection, _ = upstream.accept()
                with connection:
                    with connection.makefile("rb") as incoming:
                        assert json.loads(incoming.readline()) == {"command": "status"}
                    connection.sendall(response)

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(serve)
                completed, captured = external._run_admin_status(Path("mtd-admin"), upstream_path, json_output=True)
                future.result(timeout=5)
    assert completed.returncode == 0
    assert captured == result


def test_server_request_limit_stays_16_kib():
    class Operator:
        async def snapshot(self):
            return {"status": "ready"}

    async def exercise(path):
        server = Phase2ControlServer(path, lifecycle=None, operator=Operator())
        await server.start()
        try:
            reader, writer = await asyncio.open_unix_connection(str(server.path))
            try:
                request = json.dumps({"command": "status", "padding": "x" * MAX_CONTROL_LINE_BYTES}).encode() + b"\n"
                assert len(request) > MAX_CONTROL_LINE_BYTES
                writer.write(request)
                await writer.drain()
                response = json.loads(await reader.readline())
                assert response == {"error": "invalid_request", "ok": False}
            finally:
                writer.close()
                await writer.wait_closed()
        finally:
            await server.stop()

    with tempfile.TemporaryDirectory(prefix="h2e3-") as root:
        asyncio.run(exercise(Path(root) / "s"))
