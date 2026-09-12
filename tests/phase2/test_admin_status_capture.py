"""A live response, not an earlier volatile snapshot, is each CLI's exact oracle."""
import json
import socket
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from moss_transcribe_diarize import phase2_acceptance_external as external


@pytest.mark.parametrize("corrupt", [None, "human", "json"])
def test_status_capture_binds_each_rendering_to_its_own_response(monkeypatch, corrupt):
    monkeypatch.setattr(Path, "is_file", lambda self: True)
    monkeypatch.setattr(external.os, "access", lambda *args: True)
    monkeypatch.setattr(external, "serialize_operator_payload", lambda kind, value: dict(value))
    monkeypatch.setattr(external, "render_operator_status", lambda value: f"time={value['time']} free={value['free']}")
    sources = [{"time": 1, "free": 100}, {"time": 2, "free": 99}]

    def cli(argv, **kwargs):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(argv[2])
            client.sendall(b'{"command": "status"}\n')
            with client.makefile("rb") as incoming:
                value = json.loads(incoming.readline())["result"]
        machine = "--json" in argv
        if corrupt == ("json" if machine else "human"):
            value["free"] += 1
        output = json.dumps(value) if machine else external.render_operator_status(value)
        return subprocess.CompletedProcess(argv, 0, (output + "\n").encode(), b"")

    monkeypatch.setattr(external.subprocess, "run", cli)
    with tempfile.TemporaryDirectory(dir="/tmp") as directory:
        path = Path(directory) / "upstream"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(path))
            server.listen(2)
            server.settimeout(5)

            def serve():
                for source in sources:
                    connection, _ = server.accept()
                    with connection:
                        connection.settimeout(5)
                        with connection.makefile("rb") as incoming:
                            assert json.loads(incoming.readline()) == {"command": "status"}
                        connection.sendall(json.dumps({"ok": True, "result": source}).encode() + b"\n")

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(serve)
                observed = external._admin_status_surfaces(path, [])
                future.result(timeout=5)
    assert observed["human_exact_projection"] is (corrupt != "human")
    assert observed["json_exact_projection"] is (corrupt != "json")
