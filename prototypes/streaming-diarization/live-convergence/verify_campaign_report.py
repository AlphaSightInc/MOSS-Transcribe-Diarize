#!/usr/bin/env python3
"""Does the campaign report say what the checked-in evidence says?

The M5 report is the one document a reviewer reads instead of thirty-two bundles, so its
numbers are the campaign's public claim.  A hand-transcribed table is a claim nobody
checked; this makes it a command.

Everything the verifier compares against is READ, never restated here:

  1. the BEFORE numbers        -- `prototypes/live-file-gap-baseline-20260824/*/results.json`
  2. the AFTER numbers         -- the M4 exit bundle's `gates.json` `quality.cases`
  3. the per-milestone tallies -- each milestone-exit bundle's own `gates.json`
  4. which gates the campaign  -- the `[C]` / `[PRD…]` markers in the preregistration
     ADDED beyond the PRD         tables under this directory
  5. the milestone list        -- `scripts/ralph-live-convergence/prd.md`

Seven gates:

  G-R1 every evidence path the ledger cites exists
  G-R2 every milestone's "N of M" tally equals the tally recomputed from its gates.json
  G-R3 every FAILING gate is named on its ledger row -- a report cannot quietly drop one
  G-R4 the per-case rows carry the before/after values the evidence holds …
  G-R5 … and carry no six-decimal number that is not a value or a difference of values
       the evidence holds (a digit-flip has nowhere to hide)
  G-R6 the added-gates section lists exactly the gates a preregistration marks `[C]`
  G-R7 every PRD milestone M0..M5 has a section

Usage:

    .venv/bin/python prototypes/streaming-diarization/live-convergence/verify_campaign_report.py
    .venv/bin/python …/verify_campaign_report.py --emit       # tables, for the report body
    .venv/bin/python …/verify_campaign_report.py --selftest   # mutate a copy, require reactions

Exit 0 = the report and the evidence still say the same thing.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
EVIDENCE = REPO_ROOT / "evidence/live-convergence-0824"
BASELINE = REPO_ROOT / "prototypes/live-file-gap-baseline-20260824"
DEFAULT_REPORT = EVIDENCE / "CAMPAIGN_REPORT.md"
PRD = REPO_ROOT / "scripts/ralph-live-convergence/prd.md"

TRIO = ["lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin"]
FIVE_MINUTE = "keyu-5m"
THREE_MINUTE = "lex_adam_frank"
CASES = TRIO + [THREE_MINUTE, FIVE_MINUTE]

# Which bundle holds each milestone's scored exit.  M5 is this report itself.
MILESTONE_EXITS = {
    "M0": "M0d-paired-reacquisition",
    "M1": "M1-e1-exit",
    "M2": "M2-e2-exit",
    "M3": "M3-disposition",
    "M4": "M4-e4-exit-2",
}

PREREGISTRATIONS = {
    "M1": HERE / "PREREGISTRATION-M1a.md",
    "M2": HERE / "PREREGISTRATION-M2-exit.md",
    "M3": HERE / "PREREGISTRATION-M3.md",
    "M4": HERE / "PREREGISTRATION-M4.md",
}

AXES = ["wer", "text_coverage", "der", "speaker_accuracy"]
SIX_DP = re.compile(r"-?(?:\d+)?\.\d{6}")
GATE_ROW = re.compile(r"^\|\s*(G-M\d+-\d+)\s*`\[(?P<marker>[^\]]+)\]`")
ADDED_SECTION = "Gates the campaign added beyond the PRD"


def fmt(value: float) -> str:
    """House style: leading dot for a fraction, `0.000000` for an exact zero."""
    text = f"{value:.6f}"
    if text.startswith("0.") and float(text) != 0.0:
        return text[1:]
    if text.startswith("-0.") and float(text) != 0.0:
        return "-" + text[2:]
    return text


def display(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- evidence


def load_baseline() -> dict[str, dict[str, dict[str, float]]]:
    """Per case, per arm, the four axes of the 2026-08-24 paired baseline."""
    out: dict[str, dict[str, dict[str, float]]] = {}
    trio = json.loads((BASELINE / "trio-60s/results.json").read_text())
    for case in trio["cases"]:
        if case.get("tier") != "primary":
            continue
        out[case["case_id"]] = {
            arm: axes_of(case["arms"][arm]["scores"]) for arm in ("file", "live")
        }
    five = json.loads((BASELINE / "keyu-5m/results.json").read_text())
    out[FIVE_MINUTE] = {
        arm: axes_of(five["results"][arm]["scores"]) for arm in ("file", "live")
    }
    return out


def axes_of(scores: dict) -> dict[str, float]:
    return {
        "wer": scores["tbsa"]["wer"],
        "text_coverage": scores["tbsa"]["text_coverage"],
        "der": scores["diarization"]["der"],
        "speaker_accuracy": scores["speaker"]["speaker_accuracy"],
    }


def load_gates(milestone: str) -> dict:
    return json.loads((EVIDENCE / MILESTONE_EXITS[milestone] / "gates.json").read_text())


def tally(gates: dict) -> tuple[int, int, list[str]]:
    """(passing, scored, failing names).  A leading underscore means reported, not gated."""
    scored = {name: body for name, body in gates.items() if not name.startswith("_")}
    failing = sorted(name for name, body in scored.items() if not body.get("pass"))
    return len(scored) - len(failing), len(scored), failing


def load_final() -> dict[str, dict[str, dict[str, float]]]:
    """Per case, per arm, the four axes of the M4 exit batch (run A; B agrees to 6 dp)."""
    quality = load_gates("M4")["quality"]["cases"]
    out: dict[str, dict[str, dict[str, float]]] = {}
    for case, body in quality.items():
        run = body["runs"]["A"]
        out[case] = {
            arm: {axis: run[arm][axis] for axis in AXES} for arm in ("file", "live")
        }
    return out


def trio_mean(per_case: dict[str, dict[str, dict[str, float]]], arm: str, axis: str) -> float:
    return statistics.mean(per_case[case][arm][axis] for case in TRIO)


def trajectory() -> list[tuple[str, dict[str, float | None]]]:
    """Trio means at each rung of the ladder, each read from the bundle that measured it."""
    baseline, final = load_baseline(), load_final()
    m1 = load_gates("M1")["gates"]["G_M1_1_trio_live_wer_bound"]
    m2 = load_gates("M2")["gates"]
    m3 = load_gates("M3")["gates"]
    rows: list[tuple[str, dict[str, float | None]]] = [
        (
            "baseline live (2026-08-24)",
            {axis: trio_mean(baseline, "live", axis) for axis in AXES},
        ),
        (
            "M1 bounded salvage",
            {
                "wer": m1["trio_live_wer_mean"],
                "text_coverage": None,
                "der": statistics.mean(
                    m1["per_case"][case]["live_der_mean"] for case in TRIO
                ),
                "speaker_accuracy": None,
            },
        ),
        (
            "M2 rolling convergence",
            {
                "wer": m2["G_M2_1_trio_rolling_wer"]["trio_rolling_wer_mean"],
                "text_coverage": None,
                # The M2 exit's own DER / speaker accuracy, as M3's bounds quote them.
                "der": m3["G-M3-1"]["bounds"]["m2_exit"],
                "speaker_accuracy": m3["G-M3-3"]["bounds"]["m2_exit"],
            },
        ),
        (
            "M4 terminal convergence",
            {axis: trio_mean(final, "live", axis) for axis in AXES},
        ),
        (
            "paired file arm",
            {axis: trio_mean(final, "file", axis) for axis in AXES},
        ),
    ]
    return rows


def added_gates() -> tuple[dict[str, list[str]], dict[str, list[str]], list[str]]:
    """Gates a preregistration marks `[C]`, the ones it marks `[PRD…]`, and unmarked files."""
    campaign: dict[str, list[str]] = {}
    prd_named: dict[str, list[str]] = {}
    unmarked: list[str] = []
    for milestone, path in PREREGISTRATIONS.items():
        text = path.read_text()
        marked = [GATE_ROW.match(line) for line in text.splitlines()]
        rows = [match for match in marked if match]
        if not rows:
            unmarked.append(milestone)
            continue
        for match in rows:
            bucket = campaign if match.group("marker") == "C" else prd_named
            bucket.setdefault(milestone, []).append(match.group(1))
        # A `[C, …]` marker is campaign-added with a citation; treat it as campaign-added.
        for match in rows:
            marker = match.group("marker")
            if marker.startswith("C,"):
                campaign.setdefault(milestone, []).append(match.group(1))
                prd_named.get(milestone, []).remove(match.group(1))
    return campaign, prd_named, unmarked


def prd_milestones() -> list[str]:
    found = re.findall(r"^- \*\*(M\d)\b", PRD.read_text(), flags=re.MULTILINE)
    seen: list[str] = []
    for name in found:
        if name not in seen:
            seen.append(name)
    return seen


# ----------------------------------------------------------------------------- tables


def case_rows() -> tuple[list[list[str]], list[list[str]]]:
    """The two per-case tables: text, then speaker.  Emitted and checked from one source."""
    baseline, final = load_baseline(), load_final()
    text_rows: list[list[str]] = []
    speaker_rows: list[list[str]] = []
    for case in CASES:
        before = baseline.get(case)
        after = final[case]
        text_rows.append(
            [
                case,
                fmt(before["live"]["wer"]) if before else "n/a",
                fmt(after["live"]["wer"]),
                fmt(after["file"]["wer"]),
                fmt(abs(after["live"]["wer"] - after["file"]["wer"])),
            ]
        )
        speaker_rows.append(
            [
                case,
                fmt(before["live"]["der"]) if before else "n/a",
                fmt(after["live"]["der"]),
                fmt(after["file"]["der"]),
                fmt(before["live"]["speaker_accuracy"]) if before else "n/a",
                fmt(after["live"]["speaker_accuracy"]),
                fmt(after["file"]["speaker_accuracy"]),
            ]
        )
    text_rows.append(
        [
            "**trio mean**",
            fmt(trio_mean(baseline, "live", "wer")),
            fmt(trio_mean(final, "live", "wer")),
            fmt(trio_mean(final, "file", "wer")),
            fmt(abs(trio_mean(final, "live", "wer") - trio_mean(final, "file", "wer"))),
        ]
    )
    speaker_rows.append(
        [
            "**trio mean**",
            fmt(trio_mean(baseline, "live", "der")),
            fmt(trio_mean(final, "live", "der")),
            fmt(trio_mean(final, "file", "der")),
            fmt(trio_mean(baseline, "live", "speaker_accuracy")),
            fmt(trio_mean(final, "live", "speaker_accuracy")),
            fmt(trio_mean(final, "file", "speaker_accuracy")),
        ]
    )
    return text_rows, speaker_rows


def ledger_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for milestone, bundle in MILESTONE_EXITS.items():
        passing, scored, failing = tally(load_gates(milestone)["gates"])
        rows.append(
            [
                milestone,
                f"`evidence/live-convergence-0824/{bundle}/`",
                f"{passing} of {scored}",
                ", ".join(failing) if failing else "none",
            ]
        )
    return rows


def emit() -> None:
    def table(header: list[str], rows: list[list[str]]) -> str:
        lines = ["| " + " | ".join(header) + " |"]
        lines.append("|" + "|".join(["---"] * len(header)) + "|")
        for row in rows:
            lines.append("| " + " | ".join(row) + " |")
        return "\n".join(lines)

    text_rows, speaker_rows = case_rows()
    print("### Ledger\n")
    print(table(["milestone", "evidence", "gates", "failing"], ledger_rows()))
    print("\n### Text\n")
    print(
        table(
            ["case", "live WER before", "live WER after", "paired file WER", "distance"],
            text_rows,
        )
    )
    print("\n### Speaker\n")
    print(
        table(
            [
                "case",
                "live DER before",
                "live DER after",
                "file DER",
                "live spk before",
                "live spk after",
                "file spk",
            ],
            speaker_rows,
        )
    )
    print("\n### Trajectory (trio means)\n")
    rows = [
        [
            label,
            *[fmt(values[axis]) if values[axis] is not None else "—" for axis in AXES],
        ]
        for label, values in trajectory()
    ]
    print(table(["rung", "WER", "coverage", "DER", "speaker accuracy"], rows))
    campaign, _, unmarked = added_gates()
    print("\n### Campaign-added gates (marked `[C]` in the preregistrations)\n")
    for milestone, gates in sorted(campaign.items()):
        print(f"- {milestone}: {', '.join(sorted(set(gates)))}")
    if unmarked:
        print(f"- unmarked preregistrations (all gates PRD-named): {', '.join(unmarked)}")


# ---------------------------------------------------------------------------- verify


def verify(report_path: Path) -> list[str]:
    """Every failure, as a list of one-line complaints.  Empty means the report holds."""
    problems: list[str] = []
    if not report_path.exists():
        return [f"G-R0 the report does not exist: {display(report_path)}"]
    text = report_path.read_text()
    lines = text.splitlines()

    # G-R1 / G-R2 / G-R3 -- the ledger.
    for milestone, bundle, expected_tally, failing in ledger_rows():
        row = next(
            (line for line in lines if line.startswith(f"| {milestone} ") and bundle in line),
            None,
        )
        if row is None:
            problems.append(
                f"G-R1 no ledger row for {milestone} citing {bundle}"
            )
            continue
        if not (EVIDENCE / MILESTONE_EXITS[milestone]).is_dir():
            problems.append(f"G-R1 {milestone} cites a bundle that does not exist: {bundle}")
        if expected_tally not in row:
            problems.append(
                f"G-R2 {milestone} ledger row says {row.strip()!r}; evidence says {expected_tally!r}"
            )
        for gate in [name for name in failing.split(", ") if name != "none"]:
            if gate not in text:
                problems.append(f"G-R3 {milestone} failed {gate} and the report never names it")

    # G-R4 / G-R5 -- the per-case rows.
    text_rows, speaker_rows = case_rows()
    allowed = allowed_numbers()
    for rows, table_name in ((text_rows, "text"), (speaker_rows, "speaker")):
        for row in rows:
            label = row[0]
            wanted = [cell for cell in row[1:] if cell != "n/a"]
            candidates = [
                line
                for line in lines
                if line.startswith(f"| {label} ") or line.startswith(f"| {label} |")
            ]
            if not candidates:
                problems.append(f"G-R4 no {table_name} row for {label}")
                continue
            if not any(all(value in line for value in wanted) for line in candidates):
                problems.append(
                    f"G-R4 {table_name} row for {label} is missing one of {wanted}"
                )
            key = label.strip("*")
            for line in candidates:
                for number in SIX_DP.findall(line):
                    if number not in allowed[key]:
                        problems.append(
                            f"G-R5 {key} row carries {number}, which no evidence value "
                            f"or difference of values produces"
                        )

    # G-R6 -- the added-gates section.
    campaign, prd_named, _ = added_gates()
    section = section_text(lines, ADDED_SECTION)
    if section is None:
        problems.append(f"G-R6 no section titled {ADDED_SECTION!r}")
    else:
        expected = {gate for gates in campaign.values() for gate in gates}
        for gate in sorted(expected):
            if gate not in section:
                problems.append(f"G-R6 {gate} is marked [C] and the added-gates section omits it")
        for gates in prd_named.values():
            for gate in gates:
                if gate in expected:
                    continue
                if re.search(rf"^.*\b{re.escape(gate)}\b.*$", section, flags=re.MULTILINE):
                    problems.append(
                        f"G-R6 {gate} is PRD-named and the added-gates section claims it"
                    )

    # G-R7 -- milestone coverage.
    for milestone in prd_milestones():
        if not re.search(rf"^#+ .*\b{milestone}\b", text, flags=re.MULTILINE):
            problems.append(f"G-R7 no section for milestone {milestone}")

    return list(dict.fromkeys(problems))


def allowed_numbers() -> dict[str, set[str]]:
    """Per case (and the trio mean): every value the evidence holds, and their differences."""
    baseline, final = load_baseline(), load_final()
    allowed: dict[str, set[str]] = {}
    for case in CASES:
        values: list[float] = []
        for arm in ("file", "live"):
            if case in baseline:
                values.extend(baseline[case][arm][axis] for axis in AXES)
            values.extend(final[case][arm][axis] for axis in AXES)
        allowed[case] = close_under_difference(values)
    means: list[float] = []
    for arm in ("file", "live"):
        means.extend(trio_mean(baseline, arm, axis) for axis in AXES)
        means.extend(trio_mean(final, arm, axis) for axis in AXES)
    allowed["trio mean"] = close_under_difference(means)
    return allowed


def close_under_difference(values: list[float]) -> set[str]:
    out = {fmt(value) for value in values}
    for left in values:
        for right in values:
            out.add(fmt(abs(left - right)))
            out.add(fmt(left - right))
    return out


def section_text(lines: list[str], title: str) -> str | None:
    start = next((i for i, line in enumerate(lines) if line.startswith("#") and title in line), None)
    if start is None:
        return None
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("#"):
            if len(line) - len(line.lstrip("#")) <= level:
                return "\n".join(lines[start + 1 : index])
    return "\n".join(lines[start + 1 :])


# -------------------------------------------------------------------------- selftest


MUTATIONS: list[tuple[str, str]] = [
    ("digit flip in a per-case row", "flip"),
    ("a failing gate's name deleted", "drop-failing"),
    ("a tally inflated", "inflate-tally"),
    ("a ledger row's evidence path removed", "drop-path"),
    ("a campaign-added gate dropped from its section", "drop-added"),
    ("a milestone section renamed", "drop-milestone"),
]


def mutate(text: str, kind: str) -> str:
    if kind == "flip":
        rows = case_rows()[0]
        row = rows[0]
        return text.replace(row[2], bump(row[2]), 1)
    if kind == "drop-failing":
        failing = tally(load_gates("M4")["gates"])[2]
        return text.replace(failing[0], "G-M4-XX")
    if kind == "inflate-tally":
        passing, scored, _ = tally(load_gates("M4")["gates"])
        return text.replace(f"{passing} of {scored}", f"{scored} of {scored}", 1)
    if kind == "drop-path":
        return text.replace(
            f"`evidence/live-convergence-0824/{MILESTONE_EXITS['M2']}/`", "(bundle)", 1
        )
    if kind == "drop-added":
        campaign = added_gates()[0]
        gate = sorted({g for gates in campaign.values() for g in gates})[0]
        section = section_text(text.splitlines(), ADDED_SECTION) or ""
        return text.replace(section, section.replace(gate, "", 1), 1)
    if kind == "drop-milestone":
        return re.sub(r"^(#+ .*?)\bM3\b", r"\1(M-three)", text, flags=re.MULTILINE)
    raise SystemExit(f"unknown mutation {kind}")


def bump(number: str) -> str:
    digits = list(number)
    digits[-1] = "0" if digits[-1] == "9" else str(int(digits[-1]) + 1)
    return "".join(digits)


def selftest(report_path: Path) -> int:
    control = verify(report_path)
    print(f"control: {'PASS' if not control else 'FAIL'} ({len(control)} problems)")
    for problem in control:
        print(f"    {problem}")
    failures = 0 if not control else 1
    original = report_path.read_text()
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / report_path.name
        for label, kind in MUTATIONS:
            copy.write_text(mutate(original, kind))
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
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--emit", action="store_true", help="print the tables, do not verify")
    parser.add_argument("--selftest", action="store_true", help="mutate a copy, require reactions")
    args = parser.parse_args()

    if args.emit:
        emit()
        return 0
    if args.selftest:
        failures = selftest(args.report)
        print(f"\nselftest failures: {failures}")
        return 1 if failures else 0

    problems = verify(args.report)
    if problems:
        print(f"FAIL — {len(problems)} problem(s) in {display(args.report)}")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"PASS — {display(args.report)} matches the checked-in evidence on all seven gates")
    return 0


if __name__ == "__main__":
    sys.exit(main())
