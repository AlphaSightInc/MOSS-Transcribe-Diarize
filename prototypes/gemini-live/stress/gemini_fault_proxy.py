"""Local HTTPS/WSS Gemini fault proxy. Prototype; no audio or credentials are logged.

Run: python gemini_fault_proxy.py --port 18520 --cert CERT --key KEY --log faults.jsonl
Plan: {"schedule":[{"transport":"rest","ordinal":1,"fault":"http_503"}],
       "probabilities":{"ws":{"ws_close_1011":0.1}},"seed":7}
POST a replacement plan to /__fault/plan; GET /__fault/status for counters.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
import json
import os
import random
import time
from pathlib import Path

import httpx
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect as ws_connect
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.protocols.websockets.websockets_impl import WebSocketProtocol


REST_FAULTS = frozenset({"http_429", "http_500", "http_503", "latency_fixed",
                         "latency_heavy_tail", "connection_reset", "response_truncate",
                         "malformed_json", "stall"})
WS_FAULTS = frozenset({"latency_fixed", "latency_heavy_tail", "connection_reset", "stall",
                       "ws_close_1011", "ws_close_1007", "ws_goaway"})
HOP_HEADERS = frozenset({"connection", "content-length", "host", "keep-alive",
                         "proxy-authenticate", "proxy-authorization", "te", "trailers",
                         "transfer-encoding", "upgrade"})


class FaultHTTPProtocol(H11Protocol):
    """Expose this local test socket to the reset injector after ASGI scope creation."""

    def handle_events(self) -> None:
        super().handle_events()
        if self.scope is not None:
            self.scope.setdefault("extensions", {})["fault_transport"] = self.transport


class FaultWSProtocol(WebSocketProtocol):
    async def run_asgi(self) -> None:
        self.scope.setdefault("extensions", {})["fault_transport"] = self.transport
        await super().run_asgi()


class FaultPlan:
    def __init__(self, data: dict, log: Path):
        self.log = log
        self.reset(data)

    def reset(self, data: dict) -> None:
        self.schedule = list(data.get("schedule") or [])
        self.probabilities = dict(data.get("probabilities") or {})
        self.rng = random.Random(data.get("seed", 0))
        self.counts = {"rest": 0, "ws": 0}
        self.injected = {}
        for entry in self.schedule:
            transport, fault = entry["transport"], entry["fault"]
            if transport not in ("rest", "ws") or fault not in (REST_FAULTS if transport == "rest" else WS_FAULTS):
                raise ValueError(f"invalid scheduled fault {transport}:{fault}")
            if int(entry["ordinal"]) <= 0:
                raise ValueError("ordinal must be positive")
        for transport, rates in self.probabilities.items():
            if transport not in ("rest", "ws"):
                raise ValueError("invalid transport")
            for fault, probability in rates.items():
                if fault not in (REST_FAULTS if transport == "rest" else WS_FAULTS):
                    raise ValueError(f"invalid probabilistic fault {transport}:{fault}")
                if not 0 <= float(probability) <= 1:
                    raise ValueError("probability must be in [0,1]")

    def choose(self, transport: str, path: str) -> tuple[int, dict | None]:
        self.counts[transport] += 1
        ordinal = self.counts[transport]
        fault = next((entry for entry in self.schedule if
                      entry["transport"] == transport and int(entry["ordinal"]) == ordinal), None)
        if fault is None:
            for name, probability in self.probabilities.get(transport, {}).items():
                if self.rng.random() < float(probability):
                    fault = {"fault": name, "transport": transport, "probability": probability}
                    break
        if fault:
            name = fault["fault"]
            self.injected[name] = self.injected.get(name, 0) + 1
            self.record({"transport": transport, "ordinal": ordinal, "fault": name,
                         "path": path, "phase": "chosen"})
        return ordinal, fault

    def record(self, row: dict) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"wall_time": time.time(), "monotonic_ns": time.monotonic_ns(),
                                     **row}, sort_keys=True) + "\n")

    def delay(self, fault: dict) -> float:
        base = max(0.0, float(fault.get("seconds", 1)))
        if fault["fault"] == "latency_heavy_tail":
            shape = max(0.1, float(fault.get("shape", 1.5)))
            maximum = max(base, float(fault.get("max_seconds", 30)))
            return min(maximum, base * (1 - self.rng.random()) ** (-1 / shape))
        return base


def make_app(plan: FaultPlan, *, rest_upstream: str, ws_upstream: str) -> Starlette:
    rest_client = httpx.AsyncClient(timeout=httpx.Timeout(120), follow_redirects=False)

    async def set_plan(request: Request) -> Response:
        try:
            data = await request.json()
            plan.reset(data)
        except (ValueError, KeyError, TypeError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        return JSONResponse({"status": "set", "schedule": len(plan.schedule),
                             "probabilistic_kinds": sum(map(len, plan.probabilities.values()))})

    async def status(_: Request) -> Response:
        return JSONResponse({"counts": plan.counts, "injected": plan.injected,
                             "schedule": len(plan.schedule)})

    async def rest(request: Request) -> Response:
        ordinal, fault = plan.choose("rest", request.url.path)
        name = fault["fault"] if fault else None
        if name in ("latency_fixed", "latency_heavy_tail", "stall"):
            delay = plan.delay(fault)
            plan.record({"transport": "rest", "ordinal": ordinal, "fault": name,
                         "phase": "delay", "seconds": round(delay, 3)})
            await asyncio.sleep(delay)
        if name and name.startswith("http_"):
            code = int(name.split("_")[1])
            return JSONResponse({"error": {"code": code, "message": "injected fault"}}, status_code=code)
        if name == "connection_reset":
            request.scope["extensions"]["fault_transport"].abort()
            return Response(status_code=204)
        if name == "malformed_json":
            return Response(b'{"injected":', media_type="application/json")
        path = request.url.path
        if request.url.query:
            path += "?" + request.url.query
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_HEADERS}
        body = await request.body()
        try:
            async with rest_client.stream(request.method, rest_upstream.rstrip("/") + path,
                                          headers=headers, content=body) as upstream:
                raw = b"".join([part async for part in upstream.aiter_raw()])
                response_headers = {k: v for k, v in upstream.headers.items()
                                    if k.lower() not in HOP_HEADERS}
                if name == "response_truncate" and raw:
                    cut = max(1, len(raw) // 2)
                    plan.record({"transport": "rest", "ordinal": ordinal, "fault": name,
                                 "phase": "truncated", "original_bytes": len(raw), "sent_bytes": cut})
                    async def partial_body():
                        yield raw[:cut]
                    response_headers["content-length"] = str(len(raw))
                    return StreamingResponse(partial_body(), status_code=upstream.status_code,
                                             headers=response_headers)
                return Response(raw, status_code=upstream.status_code, headers=response_headers)
        except (httpx.HTTPError, OSError) as exc:
            plan.record({"transport": "rest", "ordinal": ordinal, "fault": name or "upstream_error",
                         "phase": "upstream_error", "error_type": type(exc).__name__})
            return JSONResponse({"error": {"code": 502, "message": "upstream unavailable"}}, status_code=502)

    async def websocket(websocket: WebSocket) -> None:
        path = websocket.url.path
        ordinal, fault = plan.choose("ws", path)
        name = fault["fault"] if fault else None
        if name in ("latency_fixed", "latency_heavy_tail", "stall"):
            delay = plan.delay(fault)
            plan.record({"transport": "ws", "ordinal": ordinal, "fault": name,
                         "phase": "delay", "seconds": round(delay, 3)})
            await websocket.accept()
            await asyncio.sleep(delay)
        elif name in ("ws_close_1011", "ws_close_1007", "ws_goaway", "connection_reset"):
            await websocket.accept()
            if name == "connection_reset":
                websocket.scope["extensions"]["fault_transport"].abort()
                return
            if name == "ws_goaway":
                await websocket.send_text('{"goAway":{"timeLeft":"0s"}}')
            await websocket.close(code=1007 if name == "ws_close_1007" else 1011)
            return
        else:
            await websocket.accept()
        uri = ws_upstream.rstrip("/") + path
        if websocket.url.query:
            uri += "?" + websocket.url.query
        headers = {k.decode(): v.decode() for k, v in websocket.scope["headers"]
                   if k.lower() not in (b"host", b"connection", b"upgrade")
                   and not k.lower().startswith(b"sec-websocket-")}
        try:
            async with ws_connect(uri, additional_headers=headers, max_size=None) as upstream:
                async def client_to_google():
                    while True:
                        message = await websocket.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        data = message.get("bytes")
                        if data is None:
                            data = message.get("text")
                        if data is not None:
                            await upstream.send(data)

                async def google_to_client():
                    async for data in upstream:
                        if isinstance(data, bytes):
                            await websocket.send_bytes(data)
                        else:
                            await websocket.send_text(data)

                tasks = [asyncio.create_task(client_to_google()), asyncio.create_task(google_to_client())]
                done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                for task in done:
                    if task.exception():
                        raise task.exception()
        except (WebSocketDisconnect, OSError, Exception) as exc:
            plan.record({"transport": "ws", "ordinal": ordinal, "fault": name or "upstream_error",
                         "phase": "closed", "error_type": type(exc).__name__})
            try:
                await websocket.close(code=1011)
            except RuntimeError:
                pass

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await rest_client.aclose()

    app = Starlette(routes=[Route("/__fault/plan", set_plan, methods=["POST"]),
                            Route("/__fault/status", status, methods=["GET"]),
                            Route("/{path:path}", rest, methods=["GET", "POST", "PUT", "DELETE"]),
                            WebSocketRoute("/{path:path}", websocket)], lifespan=lifespan)
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=18520)
    parser.add_argument("--cert", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--rest-upstream", default="https://generativelanguage.googleapis.com")
    parser.add_argument("--ws-upstream", default="wss://generativelanguage.googleapis.com")
    parser.add_argument("--down", action="store_true", help="leave port unbound: true ECONNREFUSED mode")
    args = parser.parse_args()
    if not 18520 <= args.port <= 18529:
        parser.error("proxy port must be in 18520-18529")
    data = json.loads(args.plan.read_text()) if args.plan else {}
    plan = FaultPlan(data, args.log)
    if args.down:
        plan.record({"transport": "all", "fault": "google_down", "phase": "unbound",
                     "port": args.port})
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return
    uvicorn.run(make_app(plan, rest_upstream=args.rest_upstream, ws_upstream=args.ws_upstream),
                host="127.0.0.1", port=args.port, ssl_certfile=str(args.cert),
                ssl_keyfile=str(args.key), http=FaultHTTPProtocol, ws=FaultWSProtocol,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
