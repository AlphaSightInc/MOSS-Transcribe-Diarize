#!/usr/bin/env python3
"""Per-iteration guardrail preflight for the Phase 1 rebuild fleet.

Wired in as RALPH_PREFLIGHT_CMD with RALPH_PREFLIGHT_REQUIRED=1, so it runs before every
iteration and STOPS the loop when it fails. Every check here exists because the first fleet
run actually failed that way on 2026-08-13:

  prerequisites  ticket 3 spent 8 iterations building scaffolding for a measurement it could
                 never run, because nothing checked at iteration 0 that a local model runtime
                 existed. Missing prerequisites now stop the loop immediately.
  ownership      tickets 1 and 3 both implemented v2 retryable backpressure with incompatible
                 APIs, because nothing declared who owned live_service_runtime.py.
  forbidden      gates passed on stub evidence: --passWithNoTests, tautological assertions,
                 hardcoded fixture strings standing in for model output, and a probe script
                 deleted after producing the artifact that was the only proof of a gate.

Usage:  preflight.py <ticket-id> [--base <ref>]
Exit:   0 = clear to proceed, 1 = violation (loop stops), 2 = harness error.
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
OWNERSHIP = HERE / "ownership.json"


def sh(*args: str) -> str:
    return subprocess.run(args, cwd=REPO, capture_output=True, text=True).stdout.strip()


# --------------------------------------------------------------------------- prerequisites
def check_reference_repo() -> str | None:
    ref = Path("/Users/gao/Desktop/AI_Projects/LiveTranscribe/frontend/src/App.tsx")
    if not ref.is_file():
        return f"reference frontend missing at {ref}"
    n = len(ref.read_text(encoding="utf-8", errors="replace").splitlines())
    if n < 1000:
        return f"reference App.tsx is only {n} lines; expected the full ~1773-line component"
    return None


def check_node_toolchain() -> str | None:
    if shutil.which("npm") is None:
        return "npm not on PATH; the frontend cannot be built"
    return None


def check_capture_harness() -> str | None:
    p = REPO / "prototypes/browser-capture-feasibility/framer_worklet.js"
    if not p.is_file():
        return f"capture harness worklet missing at {p}"
    return None


def check_model_runtime() -> str | None:
    """The single check that would have saved ticket 3 eight wasted iterations.

    Real-decode measurement needs a model somewhere. Local checkout, a vLLM endpoint, or
    the operator-authorized GPU host all count; nothing at all does not.
    """
    model = REPO / "pretrained" / "moss-transcribe-diarize"
    if model.is_dir() and any(model.iterdir()):
        return None
    if os.environ.get("MOSS_VLLM_BASE_URL"):
        return None
    host = os.environ.get("MOSS_MEASUREMENT_SSH_HOST")
    if host:
        probe = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, "true"],
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return None
        return (
            f"MOSS_MEASUREMENT_SSH_HOST={host!r} is set but unreachable "
            f"({(probe.stderr or '').strip()[:120]}). STOP and escalate."
        )
    return (
        "no model runtime reachable: pretrained/moss-transcribe-diarize absent, "
        "MOSS_VLLM_BASE_URL unset, MOSS_MEASUREMENT_SSH_HOST unset. Real-decode "
        "measurement is impossible here. STOP and escalate on the issue rather than "
        "building measurement scaffolding you can never run."
    )


PREREQS = {
    "reference_repo": check_reference_repo,
    "node_toolchain": check_node_toolchain,
    "capture_harness": check_capture_harness,
    "model_runtime": check_model_runtime,
}


# ------------------------------------------------------------------------------- ownership
def changed_paths(base: str) -> list[str]:
    merge_base = sh("git", "merge-base", base, "HEAD") or base
    tracked = sh("git", "diff", "--name-only", merge_base, "HEAD").splitlines()
    dirty = sh("git", "status", "--porcelain=v1", "--untracked-files=all").splitlines()
    for line in dirty:
        if len(line) <= 3:
            continue
        path = line[2:].strip().strip('"')
        if " -> " in path:  # rename: score the destination
            path = path.split(" -> ", 1)[1].strip().strip('"')
        tracked.append(path)
    return sorted({p for p in tracked if p})


# Paths any ticket may touch: its own loop state, its own evidence, and shared docs.
ALWAYS_ALLOWED = (
    "scripts/afk",  # any loop's own state dir: afk-tN, afk2-<ticket>, afk-guardrails
    "evidence/phase1/",
    "docs/",
    ".wayfinder/",
    "tests/",
    "CONTEXT.md",
    "AGENTS.md",
)


def check_ownership(ticket: dict, base: str) -> list[str]:
    owns = tuple(ticket.get("owns", ()))
    violations = []
    for path in changed_paths(base):
        if path.startswith(ALWAYS_ALLOWED) or path.startswith(owns):
            continue
        violations.append(path)
    return violations


# ------------------------------------------------------------------------------- forbidden
FORBIDDEN_CONTENT = [
    (
        "--passWithNoTests",
        "frontend/package.json",
        "a test gate that passes with zero test files is not a gate",
    ),
]


def check_forbidden() -> list[str]:
    out = []
    for needle, rel, why in FORBIDDEN_CONTENT:
        p = REPO / rel
        if p.is_file() and needle in p.read_text(encoding="utf-8", errors="replace"):
            out.append(f"{rel} contains {needle!r}: {why}")

    # A probe script that produced a committed artifact must remain runnable. Ticket 5's G7
    # evidence survived while its probe was deleted, so nobody could re-run the gate.
    #
    # The first version of this check globbed *.json and read only a top-level "probe" key. An
    # adversarial review found it missed three real violations -- all cited in .txt artifacts --
    # and silently swallowed unparseable files, so it reported OK across fourteen iterations
    # while three cited probes were absent. Scan every artifact as text instead, and treat an
    # unreadable one as a violation rather than a pass.
    # Second adversarial round (2026-08-16) found two more blind spots, both exploited during
    # AFK3:
    #
    #   1. The citation pattern only matched filenames containing "probe" or "proto". An
    #      artifact whose generator was named anything else -- run-final-gate.sh,
    #      regenerate_evidence.py, a measure_*.py -- cited a script this check could not see,
    #      so deleting that script was invisible. Match any cited runner instead. This stays
    #      quiet on the overwhelmingly common case: a cited path that exists passes, and
    #      product source files are cited constantly and do exist.
    #   2. Only existence was checked, so a probe that had rotted into something that could
    #      not even load still passed. Compile cited Python runners.
    #
    # What (2) does NOT cover, stated plainly because this file is the thing that enforces
    # stating it: compiling proves the file parses, not that it runs. A probe that imports a
    # deleted module, needs a fixture nobody committed, or fails against current `dev` still
    # passes here. Proving re-runnability means running it, which preflight cannot afford --
    # these probes start servers and drive Chrome for minutes at a time. Re-running remains
    # the reviewer's job; this check only stops the cheapest lie.
    ev = REPO / "evidence" / "phase1"
    if not ev.is_dir():
        return out
    runner_suffixes = {".py", ".sh", ".js", ".ts", ".mjs"}
    known: set[str] = set()
    for path in REPO.rglob("*"):
        if path.is_file() and path.suffix in runner_suffixes:
            if ".git" not in path.parts and ".venv" not in path.parts and "node_modules" not in path.parts:
                known.add(path.name)
    # `(?!:\d)` drops `module.py:88` -- a traceback or log frame, not a claim that anyone can
    # run that file. Captured vLLM and pytest output is full of them, and every one that names
    # a file outside this tree would otherwise stop the fleet for no reason.
    cited = re.compile(r"[\w./-]+\.(?:py|sh|js|ts|mjs)\b(?!:\d)")
    for artifact in sorted(ev.rglob("*")):
        if not artifact.is_file() or artifact.suffix not in {".json", ".txt", ".md"}:
            continue
        try:
            text = artifact.read_text(encoding="utf-8", errors="strict")
        except Exception as exc:
            out.append(f"{artifact.relative_to(REPO)} is unreadable ({exc}); cannot verify probes")
            continue
        for ref in sorted(set(cited.findall(text))):
            # An absolute path outside the repo is a statement about someone else's disk (a
            # /tmp scratch clone, the control-plane repo), not a citation this tree can honour.
            # Whether such evidence is re-runnable *here* is a review question, not a per-
            # iteration stop condition.
            if ref.startswith("/") and not ref.startswith(f"{REPO}/"):
                continue
            name = ref.rsplit("/", 1)[-1]
            resolved = REPO / ref
            if not resolved.is_file():
                if name in known:
                    continue
                out.append(
                    f"{artifact.relative_to(REPO)} cites runner {ref!r} which is not in the tree; "
                    "a gate whose probe was deleted cannot be re-run by anyone"
                )
                continue
            if resolved.suffix != ".py":
                continue
            try:
                compile(resolved.read_text(encoding="utf-8", errors="strict"), str(resolved), "exec")
            except Exception as exc:
                out.append(
                    f"{artifact.relative_to(REPO)} cites runner {ref!r} which does not compile "
                    f"({type(exc).__name__}: {exc}); a gate whose probe cannot load is not re-runnable"
                )
    return out


# ------------------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ticket")
    ap.add_argument("--base", default="dev")
    args = ap.parse_args()

    try:
        registry = json.loads(OWNERSHIP.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - harness error
        print(f"PREFLIGHT HARNESS ERROR: cannot read ownership.json: {exc}", file=sys.stderr)
        return 2
    ticket = registry.get(args.ticket)
    if ticket is None:
        print(f"PREFLIGHT HARNESS ERROR: unknown ticket {args.ticket!r}", file=sys.stderr)
        return 2

    failures: list[str] = []

    for name in ticket.get("prerequisites", ()):
        check = PREREQS.get(name)
        if check is None:
            failures.append(f"unknown prerequisite {name!r}")
            continue
        problem = check()
        if problem:
            failures.append(f"prerequisite {name}: {problem}")

    owned = check_ownership(ticket, args.base)
    if owned:
        failures.append(
            "touched paths this ticket does not own (declare intent on the issue instead of "
            "editing another ticket's files): " + ", ".join(owned[:12])
        )

    failures.extend(check_forbidden())

    if failures:
        print(f"PREFLIGHT FAIL [{args.ticket}]", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(f"PREFLIGHT OK [{args.ticket}] prerequisites present, ownership clean, no banned patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
