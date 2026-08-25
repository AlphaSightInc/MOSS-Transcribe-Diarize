#!/usr/bin/env python3
"""Does the plan's §18 acceptance record say what the checked-in evidence says?

§18 is the plan's own ledger: one row per phase, and morning review signs it before any
merge off the campaign branch.  A row is therefore two claims at once -- *these gates
passed, at this time* and *nobody has signed this yet* -- and both are forgeable by typing.
This makes the row a command instead.

Everything compared against is READ, never restated here:

  1. which bundle scored a phase  -- `verify_campaign_report.MILESTONE_EXITS`
  2. the tally and the failures   -- that bundle's own `gates.json`
  3. when the gates passed        -- the commit date of that `gates.json`, from git, in UTC
     (the one clock every bundle has; three of the five write no UTC stamp of their own)
  4. which phases are in scope    -- Appendix B §B.3 puts §13 multi-view out of it

Seven gates:

  G-P1 every scored phase row cites its milestone's exit bundle, and the bundle exists
  G-P2 every row's "N of M" tally equals the tally recomputed from that gates.json
  G-P3 every FAILING gate is named on its own row -- a row cannot quietly drop one
  G-P4 every row's UTC stamp is the commit date of the evidence it cites
  G-P5 no row is signed: the reviewer column is unsigned and the status still awaits
       morning sign-off (a signed row here would be a signature nobody gave)
  G-P6 the sign-off block above the table is still blank in every one of its FIELDS
       (a name typed beside one label leaves the rest of that line blank)
  G-P7 the out-of-scope phase row claims no evidence, no gates and no timestamp

Usage:

    .venv/bin/python prototypes/streaming-diarization/live-convergence/verify_plan_record.py
    .venv/bin/python …/verify_plan_record.py --emit       # the rows, for the plan body
    .venv/bin/python …/verify_plan_record.py --selftest   # mutate a copy, require reactions

Exit 0 = §18 and the evidence still say the same thing, and nothing is signed.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_campaign_report import (  # noqa: E402  (path shim above)
    EVIDENCE,
    MILESTONE_EXITS,
    REPO_ROOT,
    display,
    load_gates,
    tally,
)

DEFAULT_PLAN = REPO_ROOT / "docs/plans/live-mode-convergence-implementation-20260824.md"
SECTION_TITLE = "18. Review acceptance record"

# The plan's phases, and the milestone whose exit bundle scored each one.
PHASES = {
    "E0": "M0",
    "E1": "M1",
    "E2": "M2",
    "E3": "M3",
    "E4": "M4",
}
OUT_OF_SCOPE_PHASE = "Optional multi-view"

UNSIGNED = "unsigned"
AWAITING = "awaiting morning sign-off"
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
BLANK_RUN = re.compile(r"_{4,}")
# A field whose value is not a blank run is still blank if it is a choice nobody has made
# yet -- `YES / NO`, `E0 / other`.  Anything else in a value is somebody's answer.
CHOICE = re.compile(r"[A-Za-z0-9]+(?:\s*/\s*[A-Za-z0-9]+)+")
FIELD_SEPARATOR = re.compile(r"\s{2,}")


# --------------------------------------------------------------------------- evidence


def gates_committed_utc(milestone: str) -> str:
    """When the gates passed: the commit date of the evidence that scored them, in UTC."""
    path = EVIDENCE / MILESTONE_EXITS[milestone] / "gates.json"
    proc = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%cd",
            "--date=format-local:%Y-%m-%dT%H:%M:%SZ",
            "--",
            str(path.relative_to(REPO_ROOT)),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "TZ": "UTC"},
        capture_output=True,
        text=True,
        check=True,
    )
    stamp = proc.stdout.strip()
    if not STAMP.fullmatch(stamp):
        raise SystemExit(
            f"{display(path)} has no commit date; §18's clock cannot be recomputed"
        )
    return stamp


def phase_rows() -> list[list[str]]:
    """One §18 row per scored phase, generated from the evidence rather than typed."""
    rows: list[list[str]] = []
    for phase, milestone in PHASES.items():
        bundle = MILESTONE_EXITS[milestone]
        passing, scored, failing = tally(load_gates(milestone)["gates"])
        unsigned = (
            "; ".join(f"`{name}` unsigned" for name in failing) if failing else "none unsigned"
        )
        rows.append(
            [
                phase,
                f"`evidence/live-convergence-0824/{bundle}/`",
                f"{UNSIGNED} — morning review",
                "Appendix B §18 (conditional)",
                f"gates passed {gates_committed_utc(milestone)} "
                f"({passing} of {scored}; {unsigned}), {AWAITING}",
            ]
        )
    rows.append(
        [
            OUT_OF_SCOPE_PHASE,
            "— (not run)",
            "—",
            "not authorized — Appendix B §B.3 puts §13 out of campaign scope",
            "Blocked",
        ]
    )
    return rows


def section_lines(plan_text: str) -> list[str]:
    lines = plan_text.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if line.startswith("#") and SECTION_TITLE in line),
        None,
    )
    if start is None:
        return []
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("#") and len(line) - len(line.lstrip("#")) <= level:
            return lines[start:index]
    return lines[start:]


def signoff_block(section: list[str]) -> list[str]:
    """The fenced sign-off block at the top of §18 -- the lines morning review fills in."""
    fences = [i for i, line in enumerate(section) if line.strip().startswith("```")]
    if len(fences) < 2:
        return []
    return section[fences[0] + 1 : fences[1]]


# ---------------------------------------------------------------------------- verify


def verify(plan_path: Path) -> list[str]:
    """Every failure, as a list of one-line complaints.  Empty means §18 holds."""
    if not plan_path.exists():
        return [f"G-P0 the plan does not exist: {display(plan_path)}"]
    section = section_lines(plan_path.read_text())
    if not section:
        return [f"G-P0 {display(plan_path)} has no section titled {SECTION_TITLE!r}"]

    problems: list[str] = []
    for phase, bundle_cell, reviewer, _authorization, status in phase_rows():
        row = next(
            (line for line in section if line.startswith(f"| {phase} |")),
            None,
        )
        if row is None:
            problems.append(f"G-P1 §18 has no row for phase {phase}")
            continue
        if phase == OUT_OF_SCOPE_PHASE:
            # G-P7 -- a phase nobody ran cannot carry evidence, a tally or a clock.
            if STAMP.search(row) or re.search(r"\d+ of \d+", row) or "evidence/" in row:
                problems.append(
                    f"G-P7 the {phase} row claims a result and Appendix B §B.3 put it out of scope"
                )
            continue

        milestone = PHASES[phase]
        if bundle_cell not in row:
            problems.append(f"G-P1 the {phase} row does not cite {bundle_cell}")
        if not (EVIDENCE / MILESTONE_EXITS[milestone]).is_dir():
            problems.append(
                f"G-P1 the {phase} row cites a bundle that does not exist: {bundle_cell}"
            )

        passing, scored, failing = tally(load_gates(milestone)["gates"])
        if f"{passing} of {scored}" not in row:
            problems.append(
                f"G-P2 the {phase} row says {row.strip()!r}; "
                f"{MILESTONE_EXITS[milestone]}/gates.json says {passing!r} of {scored!r}"
            )
        for gate in failing:
            if gate not in row:
                problems.append(
                    f"G-P3 {milestone} failed {gate} and the {phase} row never names it"
                )

        stamp = gates_committed_utc(milestone)
        if stamp not in row:
            problems.append(
                f"G-P4 the {phase} row's clock is not {stamp}, "
                f"the commit date of the evidence it cites"
            )

        if reviewer not in row or AWAITING not in row:
            problems.append(
                f"G-P5 the {phase} row is signed, or no longer awaits morning sign-off"
            )
        if status not in row:
            problems.append(f"G-P5 the {phase} row's status is not {status!r}")

    # G-P6 -- the sign-off block itself.  Every FIELD, not merely every line: a signature
    # typed beside a label leaves the line's other blanks untouched.
    block = signoff_block(section)
    if not block:
        problems.append("G-P6 §18 has no sign-off block")
    for line in block:
        for cell in FIELD_SEPARATOR.split(line.strip()):
            if ":" not in cell:
                continue
            if BLANK_RUN.search(cell):
                continue
            value = cell.rsplit(":", 1)[1].strip()
            if CHOICE.fullmatch(value):
                continue
            problems.append(f"G-P6 a sign-off field is filled in: {cell.strip()!r}")

    return list(dict.fromkeys(problems))


# ----------------------------------------------------------------------------- emit


def emit() -> None:
    header = [
        "Phase",
        "Prototype/evidence bundle reviewed",
        "Reviewer / date",
        "Owner authorization",
        "Status",
    ]
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join(["---"] * len(header)) + "|")
    for row in phase_rows():
        print("| " + " | ".join(row) + " |")


# -------------------------------------------------------------------------- selftest


MUTATIONS: list[tuple[str, str]] = [
    ("a bundle path removed from a row", "drop-path"),
    ("a tally inflated", "inflate-tally"),
    ("a failing gate's name deleted", "drop-failing"),
    ("a row's clock moved", "move-clock"),
    ("a row signed by a reviewer", "sign-row"),
    ("a sign-off choice decided", "sign-block"),
    ("a reviewer name typed into a sign-off blank", "sign-name"),
    ("the out-of-scope phase claims a result", "claim-optional"),
]


def mutate(text: str, kind: str) -> str:
    if kind == "drop-path":
        return text.replace(
            f"`evidence/live-convergence-0824/{MILESTONE_EXITS['M4']}/`", "—", 1
        )
    if kind == "inflate-tally":
        passing, scored, _ = tally(load_gates("M1")["gates"])
        return text.replace(f"{passing} of {scored}", f"{scored} of {scored}", 1)
    if kind == "drop-failing":
        failing = tally(load_gates("M2")["gates"])[2][0]
        return text.replace(f"`{failing}` unsigned", "none unsigned", 1)
    if kind == "move-clock":
        stamp = gates_committed_utc("M3")
        return text.replace(stamp, stamp[:-3] + "00Z", 1)
    if kind == "sign-row":
        return text.replace(f"{UNSIGNED} — morning review", "reviewed 2026-08-25", 1)
    if kind == "sign-block":
        return text.replace(
            "ADR change accepted: YES / NO", "ADR change accepted: YES, accepted", 1
        )
    if kind == "sign-name":
        # The first blank field of the block, answered; the rest of its line stays blank.
        block = signoff_block(section_lines(text))
        line = next(line for line in block if BLANK_RUN.search(line))
        return text.replace(line, BLANK_RUN.sub("A. Reviewer", line, count=1), 1)
    if kind == "claim-optional":
        return text.replace(
            f"| {OUT_OF_SCOPE_PHASE} | — (not run)",
            f"| {OUT_OF_SCOPE_PHASE} | `evidence/live-convergence-0824/M4-e4-exit-2/`",
            1,
        )
    raise SystemExit(f"unknown mutation {kind}")


def selftest(plan_path: Path) -> int:
    control = verify(plan_path)
    print(f"control: {'PASS' if not control else 'FAIL'} ({len(control)} problems)")
    for problem in control:
        print(f"    {problem}")
    failures = 0 if not control else 1
    original = plan_path.read_text()
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / plan_path.name
        for label, kind in MUTATIONS:
            mutated = mutate(original, kind)
            if mutated == original:
                print(f"  INERT  {label} (the mutation changed nothing)")
                failures += 1
                continue
            copy.write_text(mutated)
            caught = verify(copy)
            status = "CAUGHT" if caught else "MISSED"
            if not caught:
                failures += 1
            print(f"  {status:6s} {label}")
            for problem in caught[:2]:
                print(f"           -> {problem}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--emit", action="store_true", help="print the rows, do not verify")
    parser.add_argument("--selftest", action="store_true", help="mutate a copy, require reactions")
    args = parser.parse_args()

    if args.emit:
        emit()
        return 0
    if args.selftest:
        failures = selftest(args.plan)
        print(f"\nselftest failures: {failures}")
        return 1 if failures else 0

    problems = verify(args.plan)
    if problems:
        print(f"FAIL — {len(problems)} problem(s) in §18 of {display(args.plan)}")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"PASS — §18 of {display(args.plan)} matches the checked-in evidence "
        f"on all seven gates, and every row is unsigned"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
