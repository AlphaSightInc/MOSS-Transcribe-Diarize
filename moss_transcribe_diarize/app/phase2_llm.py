"""Authenticated, config-only relay for key-less tailnet chat models.

Bodies are transient: never send prompts, responses, or upstream exception text to
the operator journal. Browser-owned HTTPS providers bypass this relay entirely.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
from asyncio import wait_for
import ipaddress
import json
import math
import os
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from starlette.requests import Request


@dataclass(frozen=True)
class LlmUpstream:
    name: str
    base_url: str
    models: tuple[str, ...]


def parse_upstreams(raw: str | None) -> tuple[LlmUpstream, ...]:
    if not raw or not raw.strip():
        return ()
    try:
        values = json.loads(raw)
        if not isinstance(values, list):
            raise ValueError
        upstreams = []
        names: set[str] = set()
        models: set[str] = set()
        for value in values:
            if not isinstance(value, dict) or set(value) != {"name", "base_url", "models"}:
                raise ValueError
            name, base, listed = value["name"], value["base_url"], value["models"]
            if not isinstance(name, str) or not name.strip() or name in names:
                raise ValueError
            if not isinstance(base, str):
                raise ValueError
            url = urlsplit(base)
            host = url.hostname or ""
            allowed = host == "localhost" or host.endswith(".tailnet.aisight.us")
            if not allowed:
                try:
                    address = ipaddress.ip_address(host)
                    allowed = address.is_loopback or address in ipaddress.ip_network("100.64.0.0/10")
                except ValueError:
                    pass
            if (url.scheme not in {"http", "https"} or not allowed or url.username is not None
                    or url.password is not None or url.query or url.fragment):
                raise ValueError
            _ = url.port  # Reject malformed ports at startup, before any requests.
            if not isinstance(listed, list) or not listed:
                raise ValueError
            for model in listed:
                if not isinstance(model, str) or not model.strip() or model in models:
                    raise ValueError
                models.add(model)
            names.add(name)
            upstreams.append(LlmUpstream(name, base.rstrip("/"), tuple(listed)))
        return tuple(upstreams)
    except (ValueError, TypeError):
        raise ValueError("Invalid MOSS_LLM_UPSTREAMS configuration.") from None


class LlmRelay:
    def __init__(self, upstreams: tuple[LlmUpstream, ...]):
        self.upstreams = upstreams
        self.transport: httpx.AsyncBaseTransport | None = None

    async def complete(self, body: Any) -> Any:
        if not self.upstreams:
            raise HTTPException(404, "relay_disabled")
        if (not isinstance(body, dict) or not {"model", "messages"} <= body.keys()
                or body.keys() - {"model", "messages", "max_tokens", "temperature"}):
            raise HTTPException(400, "invalid_request")
        model, messages = body["model"], body["messages"]
        if (not isinstance(model, str) or not isinstance(messages, list) or not messages
                or any(not isinstance(m, dict) or not isinstance(m.get("role"), str)
                       or not isinstance(m.get("content"), str) for m in messages)):
            raise HTTPException(400, "invalid_request")
        upstream = next((u for u in self.upstreams if model in u.models), None)
        if upstream is None:
            raise HTTPException(404, "unknown_model")
        tokens = body.get("max_tokens", 1024)
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise HTTPException(400, "invalid_request")
        if "temperature" in body:
            temperature = body["temperature"]
            if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
                    or not math.isfinite(temperature)):
                raise HTTPException(400, "invalid_request")
        payload = {**body, "max_tokens": min(tokens, 4096), "stream": False}
        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=180,
                                         follow_redirects=False, trust_env=False) as client:
                response = await wait_for(
                    client.post(f"{upstream.base_url}/chat/completions", json=payload), timeout=180)
        except (httpx.RequestError, asyncio.TimeoutError):
            raise HTTPException(502, "upstream_unreachable") from None
        if not response.is_success:
            raise HTTPException(502, "upstream_error")
        try:
            result = response.json()
        except ValueError:
            raise HTTPException(502, "upstream_error") from None
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            content = None
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(502, "empty_content")
        return result


def attach_llm_routes(app: Any, require_account: Any, raw: str | None = None) -> None:
    relay = LlmRelay(parse_upstreams(os.environ.get("MOSS_LLM_UPSTREAMS") if raw is None else raw))
    app.state.llm_relay = relay

    @app.get("/api/llm/models")
    async def models(request: Request):
        await require_account(request)
        return {"data": [{"id": model, "upstream": upstream.name}
                         for upstream in relay.upstreams for model in upstream.models]}

    @app.post("/api/llm/chat/completions")
    async def completions(request: Request):
        await require_account(request)
        if not relay.upstreams:
            raise HTTPException(404, "relay_disabled")
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(400, "invalid_request") from None
        return await relay.complete(body)
