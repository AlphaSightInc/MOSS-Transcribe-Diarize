#!/usr/bin/env python3
"""Exercise `ConcurrentViewReader` against a local pinned-TLS stub before it costs a run.

Why this exists
---------------
Iteration 26 cost an unrun soak driver: `live-soak.sh` had never been executed once, its
per-minute abort test was unconditionally true, and `bash -n` said it was fine. The
lesson recorded there -- *an instrument that has never run is not evidence that it
works* -- applies to `live-pipeline-probe.py --concurrent-readers`, which is about to be
the sole instrument for candidate 56 and costs a pairing code every time it runs.

So the reader is exercised here against a throwaway HTTPS server on 127.0.0.1 that
speaks just enough of the view contract: `/snapshot` (with `since_version`) and
`/events` (with `since_seq`), 200 for the first N polls and then the exact pair the Mac
saw at the cut -- 401 `{"detail":"invalid bearer authority."}` on both routes.

What it asserts, and each one is a way the reader could be silently useless:
  1. it polls concurrently with the caller's own work, and both routes are hit;
  2. `since_version` and `since_seq` advance, so it is a *streaming* reader and not a
     replaying one (a reader that re-reads from 0 hides the cut behind cached events);
  3. the first non-200 is captured **with its body and its offset**, which is the whole
     deliverable -- no host recorded that body in either F1 re-run;
  4. `first_non_200` stays the first one after later refusals arrive;
  5. `stop()`/`join()` terminate it, so a probe run cannot hang on a reader;
  6. a reader that dies records `error` instead of taking the run down.

The stub uses a self-signed leaf and the reader is given that leaf's own DER sha256, so
the pin path is exercised for real rather than bypassed.

No secret is involved: the stub's bearer is a literal and the certificate is generated
into a temporary directory and deleted.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
HEALTHY_POLLS = 6          # snapshot+events pairs answered 200 before the cut
BEARER = "stub-view-token"


def _load_probe():
    spec = importlib.util.spec_from_file_location(
        "ralph_live_pipeline_probe", HERE / "live-pipeline-probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # `@dataclass` resolves annotations through `sys.modules[cls.__module__]`, so a
    # module executed without being registered there dies at import.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Stub(BaseHTTPRequestHandler):
    served = 0
    seen_versions: list[str | None] = []
    seen_seqs: list[str | None] = []
    lock = threading.Lock()

    def log_message(self, *_args) -> None:  # keep the probe's stderr readable
        return

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        with _Stub.lock:
            if parsed.path.endswith("/snapshot"):
                _Stub.seen_versions.append((query.get("since_version") or [None])[0])
            elif parsed.path.endswith("/events"):
                _Stub.seen_seqs.append((query.get("since_seq") or [None])[0])
            index = _Stub.served
            _Stub.served += 1

        # Two requests per poll; refuse everything from HEALTHY_POLLS on, exactly as the
        # server does once a session stops being viewable.
        if index >= HEALTHY_POLLS * 2:
            self._reply(401, {"detail": "invalid bearer authority."})
            return
        if parsed.path.endswith("/snapshot"):
            version = index // 2
            self._reply(200, {"snapshot": {"session": {"version": version}}})
        else:
            seq = index // 2
            self._reply(200, {"events": [{"seq": seq, "kind": "frame_accepted"}]})

    def _reply(self, status: int, body: dict) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def _self_signed(workdir: Path) -> tuple[Path, str]:
    key = workdir / "stub.key"
    cert = workdir / "stub.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    der = ssl.PEM_cert_to_DER_cert(cert.read_text())
    combined = workdir / "stub-combined.pem"
    combined.write_text(key.read_text() + cert.read_text())
    return combined, hashlib.sha256(der).hexdigest()


def main() -> int:
    probe = _load_probe()
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
        if not ok:
            failures.append(name)

    with tempfile.TemporaryDirectory(prefix="ralph-view-reader-") as tmp:
        workdir = Path(tmp)
        pem, pin = _self_signed(workdir)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(pem))
        server = HTTPServer(("127.0.0.1", 0), _Stub)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            reader = probe.ConcurrentViewReader(
                name="probe-reader",
                host="127.0.0.1",
                port=port,
                pin=pin,
                session_id="stub-session",
                view_token=BEARER,
                interval=0.02,
            )
            reader.start()
            # The caller keeps working while the reader polls -- that overlap is the
            # property under test, so it is not simulated with a sleep alone.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                with _Stub.lock:
                    enough = _Stub.served >= HEALTHY_POLLS * 2 + 4
                if enough:
                    break
                time.sleep(0.01)
            reader.stop()
            reader.join(timeout=5.0)
            check("reader terminates on stop()", not reader.is_alive())
            summary = reader.summary()

            check(
                "both routes were polled",
                summary["status_counts"].get("snapshot:200", 0) > 0
                and summary["status_counts"].get("events:200", 0) > 0,
                json.dumps(summary["status_counts"]),
            )
            versions = [v for v in _Stub.seen_versions if v is not None]
            check(
                "since_version advances (streaming, not replaying)",
                versions == sorted(versions) and len(set(versions)) > 1,
                f"since_version={_Stub.seen_versions[:6]}",
            )
            seqs = [s for s in _Stub.seen_seqs if s is not None]
            check(
                "since_seq advances",
                seqs == sorted(seqs, key=int) and len(set(seqs)) > 1,
                f"since_seq={_Stub.seen_seqs[:6]}",
            )
            first = summary["first_non_200"]
            check(
                "the first refusal is captured with its body",
                isinstance(first, dict)
                and first["status"] == 401
                and isinstance(first["body"], dict)
                and first["body"].get("detail") == "invalid bearer authority.",
                json.dumps(first),
            )
            check(
                "the refusal carries an offset from the reader's own start",
                isinstance(first, dict) and isinstance(first["at_seconds"], float),
                "" if not isinstance(first, dict) else f"at_seconds={first['at_seconds']}",
            )
            check(
                "first_non_200 stays FIRST after later refusals",
                isinstance(first, dict)
                and isinstance(summary["last_non_200"], dict)
                and summary["last_non_200"]["at_seconds"] >= first["at_seconds"]
                and sum(
                    count
                    for key, count in summary["status_counts"].items()
                    if key.endswith(":401")
                )
                > 1,
            )
            check("no reader error on the healthy path", summary["error"] is None, str(summary["error"]))
        finally:
            server.shutdown()
            server.server_close()

    # A reader pointed at a closed port must record the failure, not raise it into the run.
    dead = probe.ConcurrentViewReader(
        name="dead-reader",
        host="127.0.0.1",
        port=1,
        pin="0" * 64,
        session_id="stub-session",
        view_token=BEARER,
        interval=0.01,
    )
    dead.start()
    dead.join(timeout=5.0)
    check(
        "a reader that cannot connect records the error instead of raising",
        not dead.is_alive() and dead.summary()["error"] is not None,
        str(dead.summary()["error"]),
    )

    print()
    if failures:
        print(f"FAILED {len(failures)}: {', '.join(failures)}")
        return 1
    print("all view-reader checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
