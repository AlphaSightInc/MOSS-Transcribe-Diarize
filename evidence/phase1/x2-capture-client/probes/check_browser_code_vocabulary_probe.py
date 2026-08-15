#!/usr/bin/env python3
"""Check that every `browser_*` code the server understands can be emitted, and no other.

The PRD's second defect is that the whole browser failure vocabulary was dead: the client
hardcoded `state: "capturing"` and `failure_code: null`, so none of the server's seven
codes could ever appear. "Fixed" therefore has to mean all seven, not two.

The two sides are maintained independently -- the server's copy table in
`moss_transcribe_diarize/app/live_capture_status.py`, the client's unions in
`frontend/src/capture/captureClient.ts` -- so comparing them is a real check: drop or
misspell a code on either side and this fails.

It also requires each code to be named by an assertion in the committed browser tests, so
a code that exists only as a string in a type union (never assigned, never on the wire)
does not count as emitted.

One command:
    /opt/homebrew/bin/python3 evidence/phase1/x2-capture-client/probes/check_browser_code_vocabulary_probe.py

Exit 0 = the vocabularies match and every code is exercised. Exit 1 = drift.

Limit: this is a source-level check. That every code is *reachable from a real browser
event* is what the vitest suite demonstrates (`track.onended`, AudioContext
`statechange`, rejected `getUserMedia`/`getDisplayMedia`, a surface with no audio track,
and metered clipping/silence frames); an attended Chrome run is out of scope here.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SERVER = REPO / "moss_transcribe_diarize" / "app" / "live_capture_status.py"
CLIENT = REPO / "frontend" / "src" / "capture" / "captureClient.ts"
TESTS = [
    REPO / "frontend" / "src" / "capture" / "captureClient.test.ts",
    REPO / "frontend" / "src" / "capture" / "preBranchDefects.test.ts",
]

CODE = re.compile(r"browser_[a-z_]+")


def main() -> int:
    server_source = SERVER.read_text(encoding="utf-8")
    start = server_source.index("_FAILURE_STATUS_LINES")
    end = server_source.index("BROWSER_CAPTURE_FAILURE_CODES")
    server_codes = set(CODE.findall(server_source[start:end]))

    client_source = CLIENT.read_text(encoding="utf-8")
    client_codes = set(CODE.findall(client_source))

    test_source = "\n".join(path.read_text(encoding="utf-8") for path in TESTS)
    tested_codes = set(CODE.findall(test_source))

    print(f"server ({SERVER.relative_to(REPO)}): {len(server_codes)} codes")
    for code in sorted(server_codes):
        in_client = code in client_codes
        in_tests = code in tested_codes
        print(f"  {code:42} client={str(in_client):5} asserted-in-tests={in_tests}")

    failures = []
    missing = server_codes - client_codes
    if missing:
        failures.append(f"the client can never emit {sorted(missing)}")
    invented = client_codes - server_codes
    if invented:
        failures.append(
            f"the client emits {sorted(invented)}, which the server has no copy for; it "
            "would fall through to the generic status line"
        )
    untested = server_codes - tested_codes
    if untested:
        failures.append(f"no committed browser test asserts {sorted(untested)}")

    print()
    if failures:
        print("PROBE FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"PROBE OK  all {len(server_codes)} server browser codes are emittable and asserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
