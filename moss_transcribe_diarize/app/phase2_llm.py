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
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from starlette.requests import Request


class GeminiSummaryGenerator:
    """Generate a transcript-only JSON briefing with the server's Gemini key."""

    def __init__(self, api_key: str):
        self.api_key = api_key

    @classmethod
    def from_local_key(cls):
        key_path = Path(__file__).resolve().parents[2] / ".env.local"
        key = None
        if key_path.exists():
            for line in key_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("GEMINI_API_KEY="):
                    key = line.partition("=")[2].strip()
                    break
        key = key or os.environ.get("MOSS_GEMINI_API_KEY")
        return cls(key) if key else None

    async def __call__(self, document, *, model: str, language: str, prompt: str):
        from google import genai
        from google.genai import types
        from .phase2_summary import SUMMARY_PRICES

        def timestamp(seconds):
            whole = math.floor(float(seconds))
            return f"{whole // 3600:02d}:{whole // 60 % 60:02d}:{whole % 60:02d}"

        rows = sorted(document["segments"], key=lambda row: (row["start"], row["end"]))
        source = {"segments": [
            {**({"source_lane": row["source_lane"]} if row.get("source_lane") else {}),
             "start": timestamp(row["start"]), "end": timestamp(row["end"]),
             "speaker": row["speaker"], "text": row["text"]}
            for row in rows]}
        instruction = f"{prompt}{f'\nWrite the final briefing in {language.strip()}.' if language.strip() else ''}"
        client = genai.Client(api_key=self.api_key)
        try:
            response = await wait_for(client.aio.models.generate_content(
                model=model, contents=json.dumps(source, ensure_ascii=False),
                config=types.GenerateContentConfig(system_instruction=instruction,
                                                   response_mime_type="application/json", temperature=0),
            ), timeout=180)
        finally:
            await client.aio.aclose()
        metadata = response.usage_metadata
        input_tokens = metadata.prompt_token_count
        candidate_tokens = metadata.candidates_token_count
        thought_tokens = metadata.thoughts_token_count or 0
        if (type(input_tokens) is not int or input_tokens < 0
                or type(candidate_tokens) is not int or candidate_tokens < 0
                or type(thought_tokens) is not int or thought_tokens < 0):
            raise ValueError("Gemini usage metadata is incomplete.")
        output_tokens = candidate_tokens + thought_tokens
        input_rate, output_rate = SUMMARY_PRICES[model]
        usage = {"model": model, "input_tokens": input_tokens, "output_tokens": output_tokens,
                 "cost_usd": round((input_tokens * input_rate + output_tokens * output_rate) / 1_000_000, 9)}
        return json.loads(response.text or ""), usage


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
        tokens = body.get("max_tokens", 2048)
        if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens <= 0:
            raise HTTPException(400, "invalid_request")
        if "temperature" in body:
            temperature = body["temperature"]
            if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
                    or not math.isfinite(temperature)):
                raise HTTPException(400, "invalid_request")
        payload = {**body, "max_tokens": max(2048, min(tokens, 4096)), "stream": False,
                   "chat_template_kwargs": {"enable_thinking": False}}

        async def request_answer(client: httpx.AsyncClient) -> Any:
            for attempt in range(2):
                response = await client.post(f"{upstream.base_url}/chat/completions", json=payload)
                if not response.is_success:
                    raise HTTPException(502, "upstream_error")
                try:
                    result = response.json()
                except ValueError:
                    raise HTTPException(502, "upstream_error") from None
                try:
                    message = result["choices"][0]["message"]
                    content = message.get("content")
                    reasoning = message.get("reasoning_content")
                except (KeyError, IndexError, TypeError, AttributeError):
                    content = reasoning = None
                if isinstance(content, str) and content.strip():
                    return result
                # Some thinking servers still reason despite the template hint.
                # One fresh disabled-thinking attempt, never reasoning as an answer.
                if attempt == 0 and isinstance(reasoning, str) and reasoning.strip():
                    continue
                raise HTTPException(502, "empty_content")

        try:
            async with httpx.AsyncClient(transport=self.transport, timeout=180,
                                         follow_redirects=False, trust_env=False) as client:
                return await wait_for(request_answer(client), timeout=180)
        except (httpx.RequestError, asyncio.TimeoutError):
            raise HTTPException(502, "upstream_unreachable") from None



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
