import json
import asyncio
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.phase2_llm import parse_upstreams
from moss_transcribe_diarize.app import phase2_llm
from moss_transcribe_diarize.app.phase2_web_cli import parse_args


CONFIG = json.dumps([
    {"name": "macstudio", "base_url": "http://macstudio.tailnet.aisight.us:1234/v1", "models": ["primary"]},
    {"name": "rtx4090", "base_url": "http://100.64.1.2:1235/v1", "models": ["fallback"]},
])
BODY = {"model": "primary", "messages": [{"role": "user", "content": "PRIVATE_TRANSCRIPT"}]}
ANSWER = {"choices": [{"message": {"reasoning_content": "internal reasoning", "content": "Useful content"}}]}


@pytest.mark.parametrize("base", ["http://localhost:1234/v1", "https://127.0.0.1/v1", "http://[::1]/v1",
                                    "http://100.64.0.0/v1", "http://100.127.255.255/v1",
                                    "https://node.tailnet.aisight.us/v1"])
def test_allowlisted_upstreams(base):
    assert parse_upstreams(json.dumps([{"name": "node", "base_url": base, "models": ["model"]}]))[0].base_url == base


@pytest.mark.parametrize("base", ["https://example.com/v1", "http://localhost.evil/v1", "http://100.128.0.0/v1",
    "http://192.168.1.1/v1", "http://node.tailnet.aisight.us.evil/v1", "ftp://localhost/v1",
    "http://user:password@localhost/v1", "http://localhost/v1?secret=x", "http://localhost/v1#fragment", "http://localhost:bad/v1"])
def test_disallowed_upstream_refused_at_app_creation(tmp_path, base):
    raw = json.dumps([{"name": "node", "base_url": base, "models": ["model"]}])
    with pytest.raises(ValueError, match="Invalid MOSS_LLM_UPSTREAMS"):
        create_phase2_app(database_path=tmp_path / "db", llm_upstreams=raw)
    assert not (tmp_path / "db").exists()


@pytest.mark.parametrize("raw", ["bad JSON", "{}", '[{}]', '[{"name":"a","base_url":"http://localhost","models":[]}]',
    '[{"name":"a","base_url":"http://localhost","models":["x","x"]}]'])
def test_malformed_or_ambiguous_config(raw):
    with pytest.raises(ValueError): parse_upstreams(raw)


def test_routing_auth_config_discovery_and_token_bounds(tmp_path, caplog):
    calls = []
    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json=ANSWER)
    app = create_phase2_app(database_path=tmp_path / "db", llm_upstreams=CONFIG)
    app.state.llm_relay.transport = httpx.MockTransport(upstream)
    with TestClient(app, base_url="https://moss.test") as client:
        assert client.get("/api/llm/models").status_code == 401
        assert client.post("/api/llm/chat/completions", json=BODY).status_code == 401
        assert not calls
        client.post("/api/workspace/bootstrap")
        assert client.get("/api/llm/models").json() == {"data": [
            {"id": "primary", "upstream": "macstudio"}, {"id": "fallback", "upstream": "rtx4090"}]}
        assert not calls  # Discovery never calls upstream /models.
        for model, tokens, expected in [("primary", None, 1024), ("fallback", 9000, 4096), ("primary", 17, 17)]:
            body = {**BODY, "model": model, "temperature": 0.3}
            if tokens is not None: body["max_tokens"] = tokens
            response = client.post("/api/llm/chat/completions", json=body)
            assert response.status_code == 200 and response.json() == ANSWER
            sent = calls[-1]
            assert sent.url.host == ("macstudio.tailnet.aisight.us" if model == "primary" else "100.64.1.2")
            assert sent.url.path == "/v1/chat/completions"
            assert json.loads(sent.content) == {**body, "stream": False, "max_tokens": expected}
            assert sent.extensions["timeout"]["read"] == 180
            assert "authorization" not in sent.headers and "cookie" not in sent.headers
        response = client.post("/api/llm/chat/completions", json={**BODY, "model": "not-listed"})
        assert response.status_code == 404 and response.json() == {"detail": "unknown_model"}
        assert len(calls) == 3
        assert client.post("/api/llm/chat/completions", json=BODY, headers={"origin": "https://elsewhere.test"}).status_code == 403
        assert "PRIVATE_TRANSCRIPT" not in caplog.text
        assert "internal reasoning" not in caplog.text


@pytest.mark.parametrize("raw", ["", "  ", "[]"])
def test_disabled_relay(tmp_path, monkeypatch, raw):
    monkeypatch.setenv("MOSS_LLM_UPSTREAMS", raw)
    app = create_phase2_app(database_path=tmp_path / "db")
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        assert client.get("/api/llm/models").json() == {"data": []}
        assert client.post("/api/llm/chat/completions", json=BODY).status_code == 404


@pytest.mark.parametrize("kind,reason", [("empty", "empty_content"), ("missing", "empty_content"),
    ("timeout", "upstream_unreachable"), ("error", "upstream_error"), ("json", "upstream_error"), ("redirect", "upstream_error")])
def test_content_free_failure_and_no_redirect(tmp_path, caplog, kind, reason):
    calls = []
    def upstream(request):
        calls.append(request)
        if kind == "timeout": raise httpx.ReadTimeout("PRIVATE_PROVIDER_FAILURE", request=request)
        if kind == "error": return httpx.Response(500, text="PRIVATE_PROVIDER_FAILURE")
        if kind == "json": return httpx.Response(200, text="PRIVATE_PROVIDER_FAILURE")
        if kind == "redirect": return httpx.Response(307, headers={"Location": "http://example.com"})
        if kind == "missing": return httpx.Response(200, json={"choices": []})
        return httpx.Response(200, json={"choices": [{"message": {"reasoning_content": "PRIVATE_REASONING", "content": "  "}}]})
    app = create_phase2_app(database_path=tmp_path / "db", llm_upstreams=CONFIG)
    app.state.llm_relay.transport = httpx.MockTransport(upstream)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        response = client.post("/api/llm/chat/completions", json=BODY)
        assert response.status_code == 502 and response.json() == {"detail": reason}
    assert len(calls) == 1
    assert "PRIVATE_" not in caplog.text


@pytest.mark.parametrize("extra", [{"base_url": "http://evil"}, {"stream": True}, {"max_tokens": 0},
    {"max_tokens": True}, {"max_tokens": 1.5}, {"temperature": "hot"}, {"messages": []}])
def test_request_is_limited_and_errors_do_not_echo_input(tmp_path, extra):
    app = create_phase2_app(database_path=tmp_path / "db", llm_upstreams=CONFIG)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        response = client.post("/api/llm/chat/completions", json={**BODY, **extra})
        assert response.status_code == 400 and response.json() == {"detail": "invalid_request"}


def test_cli_and_launcher_expose_environment(monkeypatch):
    monkeypatch.setenv("MOSS_LLM_UPSTREAMS", CONFIG)
    args = parse_args(["--tls-certfile", "cert", "--tls-keyfile", "key", "--live-provider-manifest", "manifest",
                       "--live-helper-lease-seconds", "10"])
    assert args.llm_upstreams == CONFIG
    launcher = Path(__file__).resolve().parents[2] / "ops/account-web-launcher.sh"
    assert '--llm-upstreams "${MOSS_LLM_UPSTREAMS:-}"' in launcher.read_text()


def test_whole_request_deadline_is_content_free(tmp_path, monkeypatch):
    async def deadline(awaitable, *, timeout):
        assert timeout == 180
        awaitable.close()
        raise asyncio.TimeoutError("PRIVATE_TIMEOUT")
    monkeypatch.setattr(phase2_llm, "wait_for", deadline)
    app = create_phase2_app(database_path=tmp_path / "db", llm_upstreams=CONFIG)
    with TestClient(app, base_url="https://moss.test") as client:
        client.post("/api/workspace/bootstrap")
        response = client.post("/api/llm/chat/completions", json=BODY)
        assert response.status_code == 502 and response.json() == {"detail": "upstream_unreachable"}
