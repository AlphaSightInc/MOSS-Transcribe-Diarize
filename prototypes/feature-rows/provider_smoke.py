#!/usr/bin/env python3
"""One 50 s external-summary smoke through tests/e2e/verify_summaries.py.

This is deliberately not the R4-10 S15 campaign.  It runs the verifier's browser
path once after narrowing its fixed population to the 50 s corpus.  A local TLS
proxy is the only observer of the provider boundary: it forwards no more than the
configured cap, retains no headers or bodies, and writes a redacted receipt.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
CORPUS = "mono_javier_intro_50s"
MODEL = "google/gemini-2.5-flash-lite"
TIMESTAMP = re.compile(r"^\d{2}:[0-5]\d:[0-5]\d$")


def free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def safe_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


class CountingProxy:
    """OpenAI-compatible TLS hop that retains only model, status, and count."""

    def __init__(self, *, port: int, origin: str, certificate: Path, key: Path, events: Path, cap: int):
        self.origin = origin
        self.events = events
        self.cap = cap
        self.lock = threading.Lock()
        self.count = 0
        self.rows: list[dict[str, object]] = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

            def cors(self) -> None:
                self.send_header("Access-Control-Allow-Origin", owner.origin)
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

            def send_json(self, status: int, payload: bytes) -> None:
                self.send_response(status)
                self.cors()
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_OPTIONS(self) -> None:
                self.send_response(204)
                self.cors()
                self.end_headers()

            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                try:
                    model = json.loads(body).get("model")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    model = None
                with owner.lock:
                    if owner.count >= owner.cap:
                        row = {"provider_post": owner.count, "forwarded": False,
                               "path": self.path, "model": model, "status": 429}
                        owner.rows.append(row)
                        with owner.events.open("a") as stream:
                            stream.write(json.dumps(row, sort_keys=True) + "\n")
                        self.send_json(429, b'{"error":"provider post cap reached"}')
                        return
                    owner.count += 1
                    number = owner.count

                # The browser sends /v1/chat/completions to this proxy.  It becomes
                # OpenRouter's /api/v1/chat/completions without ever retaining auth
                # or transcript content outside the in-flight request.
                target = "https://openrouter.ai/api" + self.path
                headers = {"Content-Type": self.headers.get("Content-Type", "application/json")}
                authorization = self.headers.get("Authorization")
                if authorization:
                    headers["Authorization"] = authorization
                upstream = urllib.request.Request(target, data=body, method="POST", headers=headers)
                status = 502
                response_body = b'{"error":"provider transport failure"}'
                content_type = "application/json"
                try:
                    with urllib.request.urlopen(upstream, timeout=360) as response:
                        status = response.status
                        response_body = response.read()
                        content_type = response.headers.get_content_type()
                except urllib.error.HTTPError as error:
                    status = error.code
                    response_body = error.read()
                    content_type = error.headers.get_content_type() if error.headers else "application/json"
                except urllib.error.URLError:
                    pass
                row = {"provider_post": number, "forwarded": True, "path": self.path,
                       "model": model, "status": status}
                with owner.lock:
                    owner.rows.append(row)
                    with owner.events.open("a") as stream:
                        stream.write(json.dumps(row, sort_keys=True) + "\n")
                self.send_response(status)
                self.cors()
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(response_body)))
                self.end_headers()
                self.wfile.write(response_body)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certificate, key)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class FixtureApp:
    """The production Account app with the existing no-decoder fixture runner."""

    def __init__(self, *, port: int, state: Path, certificate: Path, key: Path):
        from moss_transcribe_diarize.app import phase2
        from prototypes.surfaces.summary_fixture import FixtureRunner
        from tests.reference_ui_screenshot_diff import _ui_runtime

        # Prototype-only: R4-7 owns supported SQLite-runtime qualification.
        phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
        app = phase2.create_phase2_app(
            database_path=state / "smoke.sqlite3",
            file_runner=FixtureRunner(),
            file_work_root=state / "file-work",
            meeting_audio_root=state / "meeting-audio",
            open_workspace=True,
            live_runtime_factory=_ui_runtime,
            live_helper_lease_seconds=30,
        )
        import uvicorn

        self.server = uvicorn.Server(uvicorn.Config(
            app, host="127.0.0.1", port=port, log_level="warning", access_log=False,
            ssl_certfile=str(certificate), ssl_keyfile=str(key),
        ))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> bool:
        self.thread.start()
        deadline = time.monotonic() + 30
        while not self.server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        return bool(self.server.started)

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=20)


def verifier_module() -> Any:
    spec = importlib.util.spec_from_file_location("r4_verify_summaries", ROOT / "tests/e2e/verify_summaries.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load tests/e2e/verify_summaries.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summary_facts(module: Any) -> dict[str, object]:
    meetings = module.api("GET", "/api/meetings").get("meetings", [])
    with_summaries: list[tuple[str, dict[str, object]]] = []
    for meeting in meetings:
        ident = meeting.get("id")
        if not ident:
            continue
        artifact = module.api("GET", f"/api/meetings/{ident}/summary").get("summary") or {}
        if artifact:
            with_summaries.append((ident, artifact))
    if not with_summaries:
        return {"summary_current": False, "timestamps_valid_hh_mm_ss": False,
                "timestamp_count": 0, "summary_error_code": None}
    _ident, artifact = with_summaries[-1]
    document = artifact.get("document") or {}
    timestamps = [item.get("timestamp") for item in document.get("details", []) if item.get("timestamp") is not None]
    return {
        "summary_current": artifact.get("state") == "current",
        "timestamps_valid_hh_mm_ss": bool(timestamps) and all(isinstance(value, str) and TIMESTAMP.fullmatch(value)
                                                                  for value in timestamps),
        "timestamp_count": len(timestamps),
        "summary_error_code": artifact.get("error_code"),
    }


def failure_class(rows: list[dict[str, object]], facts: dict[str, object]) -> str | None:
    if facts["summary_current"] and facts["timestamps_valid_hh_mm_ss"]:
        return None
    if facts["summary_current"]:
        return "timestamp-absent"
    statuses = {row.get("status") for row in rows if row.get("forwarded")}
    if statuses & {401, 403}:
        return "auth"
    if statuses & {402, 429}:
        return "quota"
    if statuses & {404}:
        return "model"
    if 200 in statuses:
        return "schema"
    if 502 in statuses:
        return "transport"
    return "summary-state"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Tracked, redacted evidence directory.")
    parser.add_argument("--cap", type=int, default=3)
    parser.add_argument("--prior-posts", type=Path,
                        help="Redacted proxy record from a failed prior invocation in this same smoke.")
    args = parser.parse_args(argv)
    if args.cap < 1 or args.cap > 3:
        parser.error("--cap must be from 1 through 3")
    args.out = args.out.resolve()
    prior_posts = 0
    if args.prior_posts:
        try:
            prior_posts = sum(1 for line in args.prior_posts.read_text().splitlines()
                              if json.loads(line).get("forwarded"))
        except (OSError, json.JSONDecodeError) as error:
            parser.error(f"--prior-posts is not a readable redacted proxy record: {error}")
    if prior_posts >= args.cap:
        parser.error("prior provider posts already exhaust the task-wide cap")
    if not os.environ.get("OPENROUTER_API_KEY"):
        receipt = {"status": "BLOCKED", "reason": "auth: OPENROUTER_API_KEY absent after sourcing",
                   "exit_code": 77, "provider_posts_observed": 0, "decoder_requests_used": 0}
        safe_write(args.out / "receipt.json", receipt)
        print(json.dumps(receipt, sort_keys=True))
        return 77

    args.out.mkdir(parents=True, exist_ok=True)
    posts = args.out / "provider-posts.jsonl"
    posts.write_text("")
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix="moss-r4-provider-smoke-", dir="/private/tmp") as tempdir:
        state = Path(tempdir)
        certificate, key = state / "cert.pem", state / "key.pem"
        certificate_result = subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
            "-keyout", str(key), "-out", str(certificate),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        if certificate_result.returncode:
            receipt = {"status": "BLOCKED", "reason": "local-prerequisite: openssl certificate creation failed",
                       "exit_code": certificate_result.returncode, "provider_posts_observed": 0,
                       "decoder_requests_used": 0}
            safe_write(args.out / "receipt.json", receipt)
            print(json.dumps(receipt, sort_keys=True))
            return certificate_result.returncode

        app_port, proxy_port = free_port(), free_port()
        origin = f"https://127.0.0.1:{app_port}"
        proxy = CountingProxy(port=proxy_port, origin=origin, certificate=certificate, key=key,
                              events=posts, cap=args.cap - prior_posts)
        app = FixtureApp(port=app_port, state=state, certificate=certificate, key=key)
        proxy.start()
        verifier_exit = 1
        facts: dict[str, object] = {"summary_current": False, "timestamps_valid_hh_mm_ss": False,
                                    "timestamp_count": 0, "summary_error_code": None}
        try:
            if not app.start():
                raise RuntimeError("local product fixture did not become ready")
            os.environ.update({
                "MOSS_BASE": origin,
                "MOSS_SUMMARY_PROVIDERS": "external",
                "MOSS_SUMMARY_ENDPOINT": f"https://127.0.0.1:{proxy_port}/v1",
                "MOSS_SUMMARY_MODEL": MODEL,
                "TRIALS": "1",
            })
            module = verifier_module()
            module.TRANSCRIPTS = (CORPUS,)
            module.TRIALS = 1
            module.PROVIDERS = {"external"}
            verifier_exit = int(module.main())
            facts = summary_facts(module)
        except Exception as error:  # The receipt is intentionally class-only, never provider text.
            facts["summary_error_code"] = type(error).__name__
        finally:
            app.stop()
            proxy.stop()

    models = sorted({str(row["model"]) for row in proxy.rows if row.get("model")})
    failure = failure_class(proxy.rows, facts)
    total_posts = prior_posts + proxy.count
    passed = verifier_exit == 0 and failure is None and total_posts <= args.cap
    receipt = {
        "schema": "moss-r4-provider-smoke.v1",
        "started_at": started,
        "command": "provider_smoke.py --out <evidence-dir> --cap 3 [--prior-posts <redacted-record>]",
        "population": {"transcripts": ["50s"], "trials": 1},
        "exit_code": verifier_exit,
        "status": "PROVIDER-VERIFIED" if passed else "BLOCKED",
        "reason": None if passed else failure,
        "summary_current": facts["summary_current"],
        "timestamps_valid_hh_mm_ss": facts["timestamps_valid_hh_mm_ss"],
        "timestamp_count": facts["timestamp_count"],
        "summary_error_code": facts["summary_error_code"],
        "model_actually_used": models[0] if len(models) == 1 else models,
        "provider_posts_observed": total_posts,
        "provider_posts_this_attempt": proxy.count,
        "provider_posts_prior_failed_invocation": prior_posts,
        "provider_post_cap_total": args.cap,
        "decoder_requests_used": 0,
        "artifacts": [str(posts.relative_to(ROOT)), str((args.out / "receipt.json").relative_to(ROOT))],
        "official_s15_still_needs": "frozen product stack; real decoder; 50s and 180s x TRIALS=3; provider cap 10",
    }
    safe_write(args.out / "receipt.json", receipt)
    print(json.dumps({key: receipt[key] for key in ("status", "exit_code", "summary_current",
                                                     "timestamps_valid_hh_mm_ss", "model_actually_used",
                                                     "provider_posts_observed", "reason")}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
