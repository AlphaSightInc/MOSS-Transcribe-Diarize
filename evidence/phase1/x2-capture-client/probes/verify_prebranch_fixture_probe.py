#!/usr/bin/env python3
"""Prove the frozen "before" client really is the pre-branch client.

`frontend/src/capture/prebranch/preBranchCaptureClient.ts` is what makes every
correctness assertion in `preBranchDefects.test.ts` falsifiable: each test drives that
file next to the shipped one and shows the old code failing the assertion. That only
means anything while the frozen copy is genuinely the pre-branch code -- edit one line
of it to make a test go green and the whole reproduction becomes theatre.

So: re-read the git object and compare, byte for byte, below the header banner.

One command:
    /opt/homebrew/bin/python3 evidence/phase1/x2-capture-client/probes/verify_prebranch_fixture_probe.py

Exit 0 = frozen copy matches `afk2/r2-capture-client`. Exit 1 = it drifted.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
FIXTURE = REPO / "frontend/src/capture/prebranch/preBranchCaptureClient.ts"
SOURCE_REF = "afk2/r2-capture-client"
SOURCE_PATH = "frontend/src/capture/captureClient.ts"
BANNER_END = " */\n\n"


def main() -> int:
    if not FIXTURE.is_file():
        print(f"PROBE FAIL  missing {FIXTURE.relative_to(REPO)}")
        return 1
    frozen = FIXTURE.read_text(encoding="utf-8")
    if not frozen.startswith("/*") or BANNER_END not in frozen:
        print("PROBE FAIL  frozen fixture lost its header banner")
        return 1
    body = frozen.split(BANNER_END, 1)[1]

    proc = subprocess.run(
        ["git", "show", f"{SOURCE_REF}:{SOURCE_PATH}"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"PROBE FAIL  cannot read {SOURCE_REF}:{SOURCE_PATH}: {proc.stderr.strip()}")
        return 1
    original = proc.stdout

    if body != original:
        frozen_lines = body.splitlines()
        original_lines = original.splitlines()
        print("PROBE FAIL  frozen pre-branch fixture no longer matches the git object")
        print(f"  ref     {SOURCE_REF}:{SOURCE_PATH}")
        print(f"  lines   frozen={len(frozen_lines)} original={len(original_lines)}")
        for index, (left, right) in enumerate(zip(frozen_lines, original_lines), start=1):
            if left != right:
                print(f"  first divergence at body line {index}")
                print(f"    frozen   {left!r}")
                print(f"    original {right!r}")
                break
        return 1

    revision = subprocess.run(
        ["git", "rev-parse", "--short", SOURCE_REF],
        cwd=REPO,
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(
        f"PROBE OK  {FIXTURE.relative_to(REPO)} is byte-identical to "
        f"{SOURCE_REF} ({revision}):{SOURCE_PATH} — {len(original.splitlines())} lines"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
