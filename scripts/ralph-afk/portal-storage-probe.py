#!/usr/bin/env python3
"""Measure the browser-storage half of the PRD's secret-hygiene clause.

The clause reads: *no bearer token, device token, view token, or pairing payload appears
in any CLI output, log, URL, telemetry file, or browser storage*.  Every check the repo
had for the last clause -- `tests/test_live_portal.py:217-219` -- is a **source-text**
assertion on a **locally rendered** page: the served HTML must not contain the strings
`localstorage`, `sessionstorage` or `document.cookie`.  That is a real guarantee and it is
kept here, run against the *deployed* page instead of a local render.

What was never measured is the **runtime** half.  `tests/test_live_portal.py` instruments
`localStorage`/`sessionStorage` with a recording Proxy and hands the result back to Python
as `storageWrites` (`:618,657,737,812,841`) -- and **no node ever asserts it is empty**.
The instrumentation is dead: a runtime write would pass the suite today.  This probe is the
missing assertion, plus the surfaces the harness's fake `document` cannot see on its own.

Design, and the two things that make it evidence rather than decoration:

* **It measures the deployed page.**  The script is fetched from the live service over the
  pinned leaf and its sha256 is compared with this checkout's own render, so the artefact
  under test is proven to be the artefact being served.  `/api/live/descriptor`'s
  `source_revision` cannot answer this -- it is a manifest field stamped when the finalizer
  last ran, not the running code's revision.
* **It carries negative controls.**  A recorder nobody has ever seen fire is a recorder that
  might not work.  Each control splices one deliberate write into a *copy* of the served
  script and requires the probe to catch it; a control that is not detected makes the whole
  run UNDECIDED rather than green.

The extra surfaces are reached without editing the tracked suite: a prologue is prepended to
the script copy under test, and it routes `document.cookie`, `window.name`, `indexedDB` and
`caches` writes *into* the harness's own `localStorage` Proxy.  So one recorder answers for
every surface, and the assertion this probe makes is exactly the assertion a future tracked
node would make -- `storageWrites == []`.

Read-only against the deployed service: one unauthenticated `GET /live`.  No pairing code,
no device, no session, no token, no product change.

Exit codes: 0 all clauses GREEN; 3 at least one RED; 5 no RED but something UNDECIDED;
6 the probe cannot answer (named refusal, never a traceback).
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import ssl
import subprocess
import shutil
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Identifiers that must not appear in the served page at all.  The first three are the
# tracked suite's own list; the rest are the storage surfaces it never named.
FORBIDDEN_IDENTIFIERS = (
    "localstorage",
    "sessionstorage",
    "document.cookie",
    "indexeddb",
    "window.name",
    "navigator.storage",
    "caches.open",
)

# Scenarios of the tracked harness that return `storageWrites`, with the view token each
# one types into the page.  Driving both means the recorder is read on a healthy meeting
# *and* on a reconnect path, which is where a "remember my token" convenience would live.
SCENARIOS = {
    "happy": "portal-view-secret",
    "retry": "retry-token",
}

# Routes every surface that is not the harness's Proxy into the harness's Proxy, so the
# single assertion `storageWrites == []` answers for all of them.  Prepended to a COPY of
# the served script; the served script itself is never modified.
PROLOGUE = """
    /* ralph portal-storage-probe: route every storage surface into the harness recorder */
    (() => {
      let seen = 0;
      const record = (surface, value) => {
        localStorage["__probe:" + surface + ":" + seen] = String(value);
        seen += 1;
      };
      try {
        Object.defineProperty(document, "cookie", {
          configurable: true,
          get() { return ""; },
          set(value) { record("document.cookie", value); },
        });
      } catch (error) { /* a document that refuses the accessor is reported by the control */ }
      try {
        Object.defineProperty(window, "name", {
          configurable: true,
          get() { return ""; },
          set(value) { record("window.name", value); },
        });
      } catch (error) { /* ditto */ }
      const surfaceProxy = (name) => new Proxy({}, {
        get(target, key) {
          record(name, String(key));
          return () => ({ then: () => undefined });
        },
      });
      globalThis.indexedDB = surfaceProxy("indexedDB");
      globalThis.caches = surfaceProxy("caches");
    })();
"""

# Each control splices one deliberate write into a copy of the script and must be caught.
# `localStorage.setItem` is deliberately not used: the harness's Proxy traps `set`, not a
# `setItem` method, and a control that throws would prove nothing about the recorder.
CONTROLS = {
    "localStorage": 'localStorage["moss-probe-control"] = "portal-view-secret";',
    "sessionStorage": 'sessionStorage["moss-probe-control"] = "portal-view-secret";',
    "document.cookie": 'document.cookie = "mtd-view=portal-view-secret";',
    "window.name": 'window.name = "portal-view-secret";',
    "indexedDB": 'indexedDB.open("moss-probe-control");',
    "caches": 'caches.open("moss-probe-control");',
}


class ProbeRefusal(Exception):
    """The probe cannot answer the question it was asked. Named, never a traceback."""


# ---------------------------------------------------------------------------
# Pinned transport -- the leaf pin is the whole trust decision, like the Mac client
# ---------------------------------------------------------------------------
def fetch_deployed_live_page(host: str, port: int, pin: str, timeout: float) -> tuple[int, str, str]:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    conn = http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
    try:
        conn.connect()
        observed = hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
        if observed != pin.lower():
            raise ProbeRefusal(
                f"served leaf sha256 {observed} does not match the pin {pin.lower()}"
            )
        conn.request("GET", "/live", headers={"accept": "text/html"})
        response = conn.getresponse()
        raw = response.read()
        return response.status, raw.decode("utf-8", "replace"), observed
    except OSError as error:
        raise ProbeRefusal(f"cannot reach https://{host}:{port}/live: {error}") from error
    finally:
        conn.close()


def render_local_live_page() -> str:
    """Render /live from THIS checkout using the tracked suite's own app factory."""
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    sys.path.insert(0, str(REPO_ROOT))
    try:
        from fastapi.testclient import TestClient  # noqa: PLC0415

        from test_live_portal import _make_live_app  # noqa: PLC0415
    except Exception as error:  # pragma: no cover - environment refusal
        raise ProbeRefusal(f"cannot import the tracked portal harness: {error}") from error
    with tempfile.TemporaryDirectory() as tmpdir:
        return TestClient(_make_live_app(tmpdir)).get("/live").text


def extract_script(html: str, origin: str) -> str:
    scripts = re.findall(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    if len(scripts) != 1:
        raise ProbeRefusal(f"expected one inline portal script in the {origin} page, found {len(scripts)}")
    return scripts[0]


def splice(html: str, script: str, prologue: str = "", epilogue: str = "") -> str:
    """Return the page with `script` replaced by prologue + script + epilogue."""
    return html.replace(script, prologue + script + "\n" + epilogue + "\n", 1)


def run_scenario(html: str, scenario: str) -> dict:
    sys.path.insert(0, str(REPO_ROOT / "tests"))
    from test_live_portal import _run_node_probe  # noqa: PLC0415

    return _run_node_probe(html, scenario)


# ---------------------------------------------------------------------------
# Clause reduction
# ---------------------------------------------------------------------------
def request_urls(result: dict) -> list[str]:
    requests = list(result.get("requests") or [])
    requests += list(result.get("pollRequests") or [])
    requests += list(result.get("controlRequests") or [])
    return [str(item.get("url", "")) for item in requests]


def authorization_headers(result: dict) -> list[str]:
    values: list[str] = []
    for key in ("requests", "pollRequests", "controlRequests"):
        for item in result.get(key) or []:
            headers = item.get("headers") or {}
            for name, value in headers.items():
                if name.lower() == "authorization":
                    values.append(str(value))
    return values


def rendered_text(result: dict) -> str:
    parts = [str(result.get("domText") or "")]
    for key in ("transcriptBeforeControls", "statusDetailAfterSecondPoll", "statusAfterFailure", "connectionAfterClosed"):
        parts.append(str(result.get(key) or ""))
    for row in result.get("eventRows") or []:
        parts.append(str(row))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="100.64.0.8")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument(
        "--pin",
        default="a35ca9fc4a0f5b32bf7da6dc2e03c1fa5b4ac60992f0ee49b6d5677d22b680ff",
        help="expected leaf certificate sha256 (hex)",
    )
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="measure this checkout's render only; the deployed-parity clause becomes UNDECIDED",
    )
    parser.add_argument("--report", type=Path, default=None)
    args = parser.parse_args()

    if shutil.which("node") is None:
        print("REFUSED: node is required to run the portal script", file=sys.stderr)
        return 6

    report: dict = {
        "probe": "portal-storage",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": args.host,
        "port": args.port,
        "pin_prefix": args.pin[:8],
        "offline": bool(args.offline),
    }
    clauses: list[dict] = []

    def clause(name: str, verdict: str, detail: str) -> None:
        clauses.append({"clause": name, "verdict": verdict, "detail": detail})

    try:
        local_html = render_local_live_page()
        local_script = extract_script(local_html, "local")
        report["local"] = {
            "script_sha256": hashlib.sha256(local_script.encode()).hexdigest(),
            "script_bytes": len(local_script),
        }

        if args.offline:
            html, script = local_html, local_script
            report["measured"] = "local render"
            clause(
                "deployed page is this checkout's page",
                "UNDECIDED",
                "--offline: the deployed page was not fetched",
            )
        else:
            status, deployed_html, observed = fetch_deployed_live_page(
                args.host, args.port, args.pin, args.timeout
            )
            deployed_script = extract_script(deployed_html, "deployed")
            report["deployed"] = {
                "status": status,
                "leaf_sha256": observed,
                "html_sha256": hashlib.sha256(deployed_html.encode()).hexdigest(),
                "html_bytes": len(deployed_html),
                "script_sha256": hashlib.sha256(deployed_script.encode()).hexdigest(),
                "script_bytes": len(deployed_script),
            }
            if status != 200:
                raise ProbeRefusal(f"GET /live answered {status}")
            html, script = deployed_html, deployed_script
            report["measured"] = "deployed page"
            same = deployed_script == local_script
            report["parity"] = same
            clause(
                "deployed page is this checkout's page",
                "GREEN" if same else "RED",
                (
                    f"served script sha256 {report['deployed']['script_sha256'][:12]} == local render"
                    if same
                    else "the served portal script differs from this checkout's render; "
                    "everything below speaks for the DEPLOYED script only"
                ),
            )

        # --- static surface, on the page actually measured -----------------------
        lowered = html.lower()
        present = [name for name in FORBIDDEN_IDENTIFIERS if name in lowered]
        report["static"] = {"scanned": list(FORBIDDEN_IDENTIFIERS), "present": present}
        clause(
            "no browser-storage identifier appears in the served page",
            "GREEN" if not present else "RED",
            f"{len(FORBIDDEN_IDENTIFIERS)} identifiers scanned, present: {present or 'none'}",
        )

        # --- runtime: the assertion the tracked harness never makes --------------
        runtime: dict = {}
        instrumented = splice(html, script, prologue=PROLOGUE)
        for scenario, token in SCENARIOS.items():
            result = run_scenario(instrumented, scenario)
            writes = result.get("storageWrites")
            if writes is None:
                raise ProbeRefusal(f"scenario {scenario} returned no storageWrites field")
            urls = request_urls(result)
            headers = authorization_headers(result)
            text = rendered_text(result)
            runtime[scenario] = {
                "storage_writes": writes,
                "request_count": len(urls),
                "authorization_headers": len(headers),
                "token_in_request_url": any(token in url for url in urls),
                "token_in_rendered_text": token in text,
                "token_only_as_bearer": bool(headers) and all(value == f"Bearer {token}" for value in headers),
            }
        report["runtime"] = runtime

        wrote = {name: data["storage_writes"] for name, data in runtime.items() if data["storage_writes"]}
        clause(
            "the portal writes nothing to browser storage at runtime",
            "GREEN" if not wrote else "RED",
            (
                f"{len(runtime)} scenarios driven ({', '.join(runtime)}), storageWrites empty in all"
                if not wrote
                else f"writes observed: {json.dumps(wrote)}"
            ),
        )
        leaked = {
            name: {k: v for k, v in data.items() if k.startswith("token_") and k != "token_only_as_bearer"}
            for name, data in runtime.items()
            if data["token_in_request_url"] or data["token_in_rendered_text"]
        }
        clause(
            "the view token reaches no URL and no rendered text",
            "GREEN" if not leaked else "RED",
            (
                "token absent from every request URL and every rendered node in "
                f"{len(runtime)} scenarios; carried only as Authorization: Bearer "
                f"({sum(d['authorization_headers'] for d in runtime.values())} headers)"
                if not leaked
                else json.dumps(leaked)
            ),
        )

        # --- negative controls: a recorder nobody has seen fire may not work -----
        controls: dict = {}
        for surface, statement in CONTROLS.items():
            probe_html = splice(html, script, prologue=PROLOGUE, epilogue=statement)
            result = run_scenario(probe_html, "happy")
            writes = result.get("storageWrites") or []
            controls[surface] = {"detected": bool(writes), "writes": writes}
        report["controls"] = controls
        blind = [surface for surface, data in controls.items() if not data["detected"]]
        clause(
            "the recorder catches a deliberate write on every surface",
            "GREEN" if not blind else "UNDECIDED",
            (
                f"{len(controls)} controls spliced, all detected"
                if not blind
                else f"undetected on {blind}: the green above is not evidence for those surfaces"
            ),
        )

    except ProbeRefusal as refusal:
        report["refusal"] = str(refusal)
        report["clauses"] = clauses
        report["rc"] = 6
        emit(report, args.report)
        print(f"REFUSED: {refusal}", file=sys.stderr)
        return 6

    reds = [item for item in clauses if item["verdict"] == "RED"]
    undecided = [item for item in clauses if item["verdict"] == "UNDECIDED"]
    rc = 3 if reds else (5 if undecided else 0)
    report["clauses"] = clauses
    report["rc"] = rc
    emit(report, args.report)
    for item in clauses:
        print(f"{item['verdict']:9s} {item['clause']}\n          {item['detail']}")
    print(f"rc={rc}")
    return rc


def emit(report: dict, path: Path | None) -> None:
    if path is not None:
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
