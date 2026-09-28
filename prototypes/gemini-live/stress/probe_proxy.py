"""One-command local REST/WS pass-through and fault probe; no Google calls.

Run: python prototypes/gemini-live/stress/probe_proxy.py --out evidence/P64/proxy-local-probe.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket
from websockets.asyncio.client import connect as ws_connect
from websockets.exceptions import ConnectionClosed, InvalidMessage

ROOT = Path(__file__).resolve().parents[3]
PROXY = Path(__file__).with_name("gemini_fault_proxy.py")


async def echo(request: Request) -> Response:
    return Response(await request.body(), media_type="application/octet-stream",
                    headers={"x-probe": "echo"})


async def echo_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
        if message.get("bytes") is not None:
            await websocket.send_bytes(message["bytes"])
        elif message.get("text") is not None:
            await websocket.send_text(message["text"])


mock_app = Starlette(routes=[Route("/{path:path}", echo, methods=["POST"]),
                             WebSocketRoute("/{path:path}", echo_ws)])


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


async def wait_ready(url: str, verify: bool | str) -> None:
    last_error = None
    async with httpx.AsyncClient(verify=verify) as client:
        for _ in range(60):
            try:
                response = await client.get(url, timeout=1)
                if response.status_code < 500:
                    return
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__ + ": " + str(exc)[:120]
            await asyncio.sleep(.1)
    raise RuntimeError(f"server not ready: {url} ({last_error})")


async def probe(cert: Path, out: Path) -> dict:
    direct = "http://127.0.0.1:18523"
    proxied = "https://127.0.0.1:18520"
    await wait_ready(direct + "/ready", False)
    await wait_ready(proxied + "/__fault/status", str(cert))
    async with httpx.AsyncClient(verify=str(cert), timeout=8) as client:
        bodies = [b'{"public":1}', b"three public windows", b"\x00\xff" * 500]
        rest_equal = []
        for body in bodies:
            a = await client.post(direct + "/v1beta/interactions", content=body)
            b = await client.post(proxied + "/v1beta/interactions", content=body)
            rest_equal.append(a.status_code == b.status_code and a.content == b.content and
                              a.headers.get("x-probe") == b.headers.get("x-probe"))
        ctx = ssl.create_default_context(cafile=str(cert))
        async with ws_connect("ws://127.0.0.1:18523/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent") as ws:
            await ws.send(b"public-audio-frame")
            direct_ws = await ws.recv()
        async with ws_connect("wss://127.0.0.1:18520/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent", ssl=ctx) as ws:
            await ws.send(b"public-audio-frame")
            proxied_ws = await ws.recv()
        ws_equal = direct_ws == proxied_ws
        schedule = [
            {"transport": "rest", "ordinal": 1, "fault": "http_429"},
            {"transport": "rest", "ordinal": 2, "fault": "http_500"},
            {"transport": "rest", "ordinal": 3, "fault": "http_503"},
            {"transport": "rest", "ordinal": 4, "fault": "latency_fixed", "seconds": .1},
            {"transport": "rest", "ordinal": 5, "fault": "latency_heavy_tail", "seconds": .02, "max_seconds": .1},
            {"transport": "rest", "ordinal": 6, "fault": "malformed_json"},
            {"transport": "rest", "ordinal": 7, "fault": "connection_reset"},
            {"transport": "rest", "ordinal": 8, "fault": "response_truncate"},
            {"transport": "rest", "ordinal": 9, "fault": "stall", "seconds": .1},
            {"transport": "ws", "ordinal": 1, "fault": "ws_close_1011"},
            {"transport": "ws", "ordinal": 2, "fault": "ws_close_1007"},
            {"transport": "ws", "ordinal": 3, "fault": "ws_goaway"},
            {"transport": "ws", "ordinal": 4, "fault": "stall", "seconds": .1},
            {"transport": "ws", "ordinal": 5, "fault": "connection_reset"},
        ]
        set_result = await client.post(proxied + "/__fault/plan", json={"schedule": schedule, "seed": 7})
        assert set_result.status_code == 200
        observed = []
        for expected in (429, 500, 503):
            r = await client.post(proxied + "/v1beta/interactions", content=b"test")
            observed.append({"fault": f"http_{expected}", "status": r.status_code})
            assert r.status_code == expected
        for name in ("latency_fixed", "latency_heavy_tail"):
            start = time.monotonic()
            r = await client.post(proxied + "/v1beta/interactions", content=b"test")
            elapsed = time.monotonic() - start
            observed.append({"fault": name, "status": r.status_code, "elapsed_s": round(elapsed, 3)})
            assert r.status_code == 200
        r = await client.post(proxied + "/v1beta/interactions", content=b"test")
        assert r.content == b'{"injected":'
        observed.append({"fault": "malformed_json", "status": r.status_code})
        for name in ("connection_reset", "response_truncate"):
            try:
                await client.post(proxied + "/v1beta/interactions", content=b"test" * 500)
                outcome = "NO_ERROR"
            except httpx.HTTPError as exc:
                outcome = type(exc).__name__
            observed.append({"fault": name, "client_error": outcome})
            assert outcome != "NO_ERROR"
        start = time.monotonic()
        r = await client.post(proxied + "/v1beta/interactions", content=b"test")
        elapsed = time.monotonic() - start
        assert elapsed >= .08 and r.status_code == 200
        observed.append({"fault": "stall", "elapsed_s": round(elapsed, 3)})
        for fault, code in (("ws_close_1011", 1011), ("ws_close_1007", 1007), ("ws_goaway", 1011)):
            first = None
            try:
                async with ws_connect("wss://127.0.0.1:18520/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent", ssl=ctx) as ws:
                    first = await ws.recv()
                    await ws.recv()
            except ConnectionClosed as exc:
                observed.append({"fault": fault, "close_code": exc.rcvd.code if exc.rcvd else None,
                                 "first_message": first if fault == "ws_goaway" else None})
                assert exc.rcvd and exc.rcvd.code == code
        start = time.monotonic()
        async with ws_connect("wss://127.0.0.1:18520/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent", ssl=ctx) as ws:
            await ws.send(b"after-stall")
            assert await ws.recv() == b"after-stall"
        observed.append({"fault": "ws_stall", "elapsed_s": round(time.monotonic() - start, 3)})
        try:
            async with ws_connect("wss://127.0.0.1:18520/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent", ssl=ctx) as ws:
                await ws.recv()
            outcome = "NO_ERROR"
        except ConnectionClosed as exc:
            outcome = "no_close_frame" if exc.rcvd is None else f"close_{exc.rcvd.code}"
        except InvalidMessage:
            outcome = "handshake_reset"
        observed.append({"fault": "ws_connection_reset", "client_error": outcome})
        assert outcome in ("no_close_frame", "handshake_reset")
        status = (await client.get(proxied + "/__fault/status")).json()
    result = {"rest_body_equal": rest_equal, "websocket_message_equal": ws_equal,
              "faults_observed": observed, "proxy_status": status}
    out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--mock-port", type=int)
    args = parser.parse_args()
    if args.mock_port:
        uvicorn.run(mock_app, host="127.0.0.1", port=args.mock_port, log_level="warning")
        return
    if args.out is None or args.out.exists():
        parser.error("--out must be a new JSON path")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="p64-proxy-", dir=os.environ.get("TMPDIR")) as scratch_name:
        scratch = Path(scratch_name)
        cert, key = scratch / "cert.pem", scratch / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        mock = proxy = None
        try:
            mock_log = (scratch / "mock.log").open("wb")
            mock = subprocess.Popen([sys.executable, __file__, "--mock-port", "18523"],
                                    stdout=mock_log, stderr=subprocess.STDOUT, start_new_session=True)
            proxy_log = (scratch / "proxy.log").open("wb")
            proxy = subprocess.Popen([sys.executable, str(PROXY), "--port", "18520",
                                      "--cert", str(cert), "--key", str(key),
                                      "--log", str(args.out.with_name("proxy-local-faults.jsonl")),
                                      "--rest-upstream", "http://127.0.0.1:18523",
                                      "--ws-upstream", "ws://127.0.0.1:18523"],
                                     stdout=proxy_log, stderr=subprocess.STDOUT, start_new_session=True)
            result = asyncio.run(probe(cert, args.out))
            print(json.dumps(result, indent=2))
        finally:
            if args.out.exists() is False:
                print((scratch / "proxy.log").read_text(errors="replace")[-2000:])
                print((scratch / "mock.log").read_text(errors="replace")[-1000:])
            stop(proxy)
            stop(mock)
            if 'mock_log' in locals(): mock_log.close()
            if 'proxy_log' in locals(): proxy_log.close()


if __name__ == "__main__":
    main()
