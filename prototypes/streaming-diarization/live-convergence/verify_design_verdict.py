#!/usr/bin/env python3
"""Does the design doc's §7 campaign verdict say what the checked-in evidence says?

`docs/design-streaming-diarization.md` §7 is the project's *index* of measured verdicts:
the one place a future campaign looks before re-litigating a settled question.  The
campaign report is the long form; the §7 entry is a paragraph that must survive being
read on its own, months later, by somebody who will not open a bundle.  Two things make
such a paragraph dangerous: a number that drifted from the evidence, and a verdict that
sounds accepted when nobody accepted it.  This makes both mechanical.

Everything compared against is READ, never restated here:

  1. which bundle scored a phase   -- `verify_campaign_report.MILESTONE_EXITS`
     and which phase it scored     -- `verify_plan_record.PHASES`
  2. the headline numbers          -- the baseline results.json and the M4 exit gates.json,
                                      via `verify_campaign_report`'s own readers
  3. every other number            -- `CAMPAIGN_REPORT.md`, whose numbers G-R5 already
                                      binds to the evidence (an index introduces none)
  4. which gates are unsigned      -- each milestone-exit bundle's own gates.json
  5. the entry's date              -- the newest commit date among that evidence

Seven gates:

  G-D1 §7 carries exactly ONE entry citing this campaign's evidence root, it is dated with
       the campaign's own clock, and it sits above §7's accepted production-decision
       paragraph (a verdict awaiting review does not displace the accepted one)
  G-D2 every path the entry cites exists
  G-D3 the entry carries the headline values the evidence holds, and carries no six-decimal
       number the campaign report does not hold (the index may summarise, not introduce)
  G-D4 every unsigned gate is named, and the entry's count of them is the number of gates
       that actually failed across the five milestone exits
  G-D5 nothing here is signed: the entry still awaits morning sign-off and names no reviewer
  G-D6 every "what did not change" claim is bound to the gate that holds it, and that gate
       passes -- if the gate ever flips, the sentence fails with it
  G-D7 every phase E0..E4 is named, cites the bundle that scored it, and reports that
       bundle's own tally

Usage:

    .venv/bin/python prototypes/streaming-diarization/live-convergence/verify_design_verdict.py
    .venv/bin/python …/verify_design_verdict.py --emit       # the facts the entry must carry
    .venv/bin/python …/verify_design_verdict.py --selftest   # mutate a copy, require reactions

Exit 0 = §7 and the evidence still say the same thing, and nothing is signed.
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from verify_campaign_report import (  # noqa: E402  (path shim above)
    CASES,
    EVIDENCE,
    FIVE_MINUTE,
    MILESTONE_EXITS,
    REPO_ROOT,
    SIX_DP,
    display,
    fmt,
    load_baseline,
    load_final,
    load_gates,
    tally,
    trajectory,
    trio_mean,
)
from verify_plan_record import PHASES, gates_committed_utc  # noqa: E402

DEFAULT_DOC = REPO_ROOT / "docs/design-streaming-diarization.md"
REPORT = EVIDENCE / "CAMPAIGN_REPORT.md"
SECTION_TITLE = "7. Prototype evidence"
ACCEPTED_PARAGRAPH = "Production decision (2026-07-30)"

# The entry is identified by the evidence it cites, not by a title this file restates.
CAMPAIGN_ROOT = "evidence/live-convergence-0824"

# Claims about what the campaign did NOT change, and the deployed gate that holds each.
# The words are the entry's; the truth is the gate's.
INVARIANT_CLAIMS = {
    "file mode byte-identical": ("M4", "G-M4-12"),
    "terminal work never enters the capture clock": ("M4", "G-M4-11"),
    "no tape survives its session": ("M4", "G-M4-10"),
    "replaces the surface exactly once": ("M4", "G-M4-9"),
}

AWAITING = "awaiting morning sign-off"
SIGNATURE = re.compile(r"\b(?:reviewed|signed|approved|accepted)\s+by\b", re.IGNORECASE)
COUNT_WORDS = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
UNSIGNED_COUNT = re.compile(
    r"\b(?P<count>\d+|" + "|".join(COUNT_WORDS) + r")\s+gates?\s+(?:are\s+|remain\s+)?unsigned\b",
    re.IGNORECASE,
)
CITED_PATH = re.compile(r"`((?:docs|evidence|prototypes|scripts|moss_transcribe_diarize)/[^`]+)`")


# --------------------------------------------------------------------------- evidence


def campaign_date() -> str:
    """The campaign's own clock: the newest commit date among its scored evidence."""
    return max(gates_committed_utc(milestone) for milestone in MILESTONE_EXITS)[:10]


def unsigned_gates() -> list[str]:
    """Every gate that failed across the five milestone exits, in milestone order."""
    return [
        gate
        for milestone in MILESTONE_EXITS
        for gate in tally(load_gates(milestone)["gates"])[2]
    ]


def headline_values() -> dict[str, str]:
    """The numbers a reader of the index must be able to trust, recomputed from evidence."""
    baseline, final = load_baseline(), load_final()
    values = {
        "trio live WER before": fmt(trio_mean(baseline, "live", "wer")),
        "trio live WER after": fmt(trio_mean(final, "live", "wer")),
        "trio file WER": fmt(trio_mean(final, "file", "wer")),
        "trio live DER before": fmt(trio_mean(baseline, "live", "der")),
        "trio live DER after": fmt(trio_mean(final, "live", "der")),
        "trio live speaker before": fmt(trio_mean(baseline, "live", "speaker_accuracy")),
        "trio live speaker after": fmt(trio_mean(final, "live", "speaker_accuracy")),
        "live-to-file distance": fmt(
            abs(trio_mean(final, "live", "wer") - trio_mean(final, "file", "wer"))
        ),
    }
    for axis, name in (("wer", "WER"), ("der", "DER")):
        values[f"five-minute live {name} before"] = fmt(baseline[FIVE_MINUTE]["live"][axis])
        values[f"five-minute live {name} after"] = fmt(final[FIVE_MINUTE]["live"][axis])
    for label, axes in trajectory():
        if axes["wer"] is not None:
            values[f"ladder: {label} WER"] = fmt(axes["wer"])
    return values


def report_numbers() -> set[str]:
    """Every six-decimal number the campaign report holds; G-R5 binds those to evidence."""
    return set(SIX_DP.findall(REPORT.read_text()))


# ------------------------------------------------------------------------------ entry


def section_lines(text: str) -> list[str]:
    lines = text.splitlines()
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


def entry_blocks(section: list[str]) -> list[tuple[int, list[str]]]:
    """§7's verdict entries: each a top-level `- ` bullet plus its continuation lines."""
    blocks: list[tuple[int, list[str]]] = []
    current: list[str] | None = None
    start = 0
    for index, line in enumerate(section):
        if line.startswith("- "):
            if current is not None:
                blocks.append((start, current))
            current, start = [line], index
        elif current is not None:
            if line and not line.startswith(" "):
                blocks.append((start, current))
                current = None
            else:
                current.append(line)
    if current is not None:
        blocks.append((start, current))
    return blocks


def campaign_entry(section: list[str]) -> list[tuple[int, str]]:
    """Every §7 entry that cites this campaign's evidence root.  There must be one."""
    return [
        (start, "\n".join(block))
        for start, block in entry_blocks(section)
        if CAMPAIGN_ROOT in "\n".join(block)
    ]


# ----------------------------------------------------------------------------- verify


def verify(doc_path: Path) -> list[str]:
    """Every failure, as a list of one-line complaints.  Empty means §7 holds."""
    if not doc_path.exists():
        return [f"G-D0 the design doc does not exist: {display(doc_path)}"]
    section = section_lines(doc_path.read_text())
    if not section:
        return [f"G-D0 {display(doc_path)} has no section titled {SECTION_TITLE!r}"]

    found = campaign_entry(section)
    if len(found) != 1:
        return [
            f"G-D1 §7 has {len(found)} entries citing {CAMPAIGN_ROOT}; the campaign writes one"
        ]
    start, entry = found[0]

    problems: list[str] = []

    # G-D1 -- the campaign's own clock, and placement below the accepted decision.
    date = campaign_date()
    if f"({date})" not in entry:
        problems.append(
            f"G-D1 the entry is not dated ({date}), the newest commit date of the evidence it cites"
        )
    accepted = next(
        (i for i, line in enumerate(section) if line.startswith(ACCEPTED_PARAGRAPH)), None
    )
    if accepted is None:
        problems.append(f"G-D1 §7 no longer carries the {ACCEPTED_PARAGRAPH!r} paragraph")
    elif start > accepted:
        problems.append(
            f"G-D1 the entry sits below the accepted {ACCEPTED_PARAGRAPH!r} paragraph; "
            f"a verdict awaiting review does not displace the accepted one"
        )

    # G-D2 -- every path it cites exists.
    for cited in CITED_PATH.findall(entry):
        if not (REPO_ROOT / cited.rstrip("/")).exists():
            problems.append(f"G-D2 the entry cites a path that does not exist: {cited}")

    # G-D3 -- the headline values, and no number of its own.
    for label, value in headline_values().items():
        if value not in entry:
            problems.append(f"G-D3 the entry does not carry {label} = {value}")
    for number in SIX_DP.findall(entry):
        if number not in report_numbers():
            problems.append(
                f"G-D3 the entry carries {number}, which {display(REPORT)} does not hold"
            )

    # G-D4 -- the unsigned gates, named and counted.
    failing = unsigned_gates()
    for gate in failing:
        if gate not in entry:
            problems.append(f"G-D4 {gate} is unsigned and the entry never names it")
    match = UNSIGNED_COUNT.search(entry)
    if match is None:
        problems.append("G-D4 the entry never says how many gates are unsigned")
    else:
        claimed = match.group("count").lower()
        counted = COUNT_WORDS[len(failing)] if len(failing) < len(COUNT_WORDS) else None
        if claimed not in {str(len(failing)), counted}:
            problems.append(
                f"G-D4 the entry claims {claimed} unsigned gates; the evidence has {len(failing)}"
            )

    # G-D5 -- nothing is signed.
    if AWAITING not in entry:
        problems.append(f"G-D5 the entry does not record that it is {AWAITING!r}")
    signature = SIGNATURE.search(entry)
    if signature:
        problems.append(
            f"G-D5 the entry carries a signature nobody gave: {signature.group(0)!r}"
        )

    # G-D6 -- each unchanged-by-the-campaign claim, bound to the gate that holds it.
    for claim, (milestone, gate) in INVARIANT_CLAIMS.items():
        if claim not in entry:
            problems.append(f"G-D6 the entry does not claim {claim!r} ({gate} holds it)")
            continue
        body = load_gates(milestone)["gates"].get(gate)
        if body is None:
            problems.append(f"G-D6 {gate} is not in {MILESTONE_EXITS[milestone]}/gates.json")
        elif not body.get("pass"):
            problems.append(f"G-D6 the entry claims {claim!r} and {gate} does not pass")

    # G-D7 -- every phase, citing the bundle that scored it, with that bundle's own tally.
    for phase, milestone in PHASES.items():
        if not re.search(rf"\b{phase}\b", entry):
            problems.append(f"G-D7 the entry never names phase {phase}")
        bundle = f"{CAMPAIGN_ROOT}/{MILESTONE_EXITS[milestone]}/"
        if bundle not in entry:
            problems.append(f"G-D7 the entry does not cite {phase}'s exit bundle {bundle}")
            continue
        passing, scored, _ = tally(load_gates(milestone)["gates"])
        cited = entry[entry.index(bundle) + len(bundle) :].split("\n\n")[0]
        if f"{passing} of {scored}" not in cited[:120]:
            problems.append(
                f"G-D7 the {phase} citation does not report {passing} of {scored}, "
                f"the tally in {MILESTONE_EXITS[milestone]}/gates.json"
            )

    return list(dict.fromkeys(problems))


# ------------------------------------------------------------------------------- emit


def emit() -> None:
    print(f"date (newest evidence commit): {campaign_date()}")
    print(f"\nheadline values the entry must carry:")
    for label, value in headline_values().items():
        print(f"  {value}   {label}")
    print(f"\nunsigned gates ({len(unsigned_gates())}):")
    for gate in unsigned_gates():
        print(f"  {gate}")
    print("\ninvariant claims, and the gate that holds each:")
    for claim, (milestone, gate) in INVARIANT_CLAIMS.items():
        body = load_gates(milestone)["gates"].get(gate, {})
        print(f"  [{'pass' if body.get('pass') else 'FAIL'}] {gate}  {claim!r}")
    print("\nphase bundles the entry must cite:")
    for phase, milestone in PHASES.items():
        print(f"  {phase}  {CAMPAIGN_ROOT}/{MILESTONE_EXITS[milestone]}/")
    print(f"\ncases scored: {', '.join(CASES)}")


# --------------------------------------------------------------------------- selftest


MUTATIONS: list[tuple[str, str]] = [
    ("a headline number flipped", "flip"),
    ("a number the report does not hold", "invent-number"),
    ("a headline value dropped entirely", "drop-headline"),
    ("a cited path renamed", "break-path"),
    ("an unsigned gate's name deleted", "drop-unsigned"),
    ("the unsigned count deflated", "deflate-count"),
    ("the entry signed by a reviewer", "sign"),
    ("an invariant claimed without its gate", "drop-invariant"),
    ("a phase's exit bundle uncited", "drop-bundle"),
    ("a phase's tally inflated", "inflate-tally"),
    ("the entry moved below the accepted production decision", "move-below"),
    ("the entry dated by hand", "move-date"),
]


def mutate(text: str, kind: str) -> str:
    section = section_lines(text)
    entry = campaign_entry(section)[0][1]
    if kind == "flip":
        value = headline_values()["trio live WER after"]
        return text.replace(value, bump(value), 1)
    if kind == "invent-number":
        held = report_numbers()
        stray = next(fmt(n / 1_000_000.0) for n in range(1, 1000) if fmt(n / 1_000_000.0) not in held)
        return text.replace(entry, entry.replace(AWAITING, f"{AWAITING} ({stray})", 1), 1)
    if kind == "drop-headline":
        value = headline_values()["five-minute live DER after"]
        return text.replace(entry, entry.replace(value, "unchanged"), 1)
    if kind == "break-path":
        return text.replace(entry, entry.replace(display(REPORT), display(REPORT) + ".bak", 1), 1)
    if kind == "drop-unsigned":
        gate = unsigned_gates()[0]
        return text.replace(entry, entry.replace(gate, "a gate", 1), 1)
    if kind == "deflate-count":
        match = UNSIGNED_COUNT.search(entry)
        deflated = COUNT_WORDS[COUNT_WORDS.index(match.group("count").lower()) - 1]
        return text.replace(match.group(0), match.group(0).replace(match.group("count"), deflated), 1)
    if kind == "sign":
        return text.replace(entry, entry.replace(AWAITING, "accepted by the owner", 1), 1)
    if kind == "drop-invariant":
        claim = next(iter(INVARIANT_CLAIMS))
        return text.replace(entry, entry.replace(claim, "unchanged", 1), 1)
    if kind == "drop-bundle":
        bundle = f"{CAMPAIGN_ROOT}/{MILESTONE_EXITS['M2']}/"
        return text.replace(entry, entry.replace(bundle, CAMPAIGN_ROOT, 1), 1)
    if kind == "inflate-tally":
        passing, scored, _ = tally(load_gates("M4")["gates"])
        return text.replace(entry, entry.replace(f"{passing} of {scored}", f"{scored} of {scored}", 1), 1)
    if kind == "move-below":
        lines = text.splitlines()
        block = entry.splitlines()
        first = lines.index(block[0])
        remainder = lines[:first] + lines[first + len(block) :]
        anchor = next(i for i, line in enumerate(remainder) if line.startswith(ACCEPTED_PARAGRAPH))
        tail = next(
            (i for i in range(anchor, len(remainder)) if not remainder[i].strip()), len(remainder)
        )
        return "\n".join(remainder[:tail] + [""] + block + remainder[tail:]) + "\n"
    if kind == "move-date":
        date = campaign_date()
        return text.replace(f"({date})", "(2026-08-24)", 1)
    raise SystemExit(f"unknown mutation {kind}")


def bump(number: str) -> str:
    digits = list(number)
    digits[-1] = "0" if digits[-1] == "9" else str(int(digits[-1]) + 1)
    return "".join(digits)


def selftest(doc_path: Path) -> int:
    control = verify(doc_path)
    print(f"control: {'PASS' if not control else 'FAIL'} ({len(control)} problems)")
    for problem in control:
        print(f"    {problem}")
    failures = 0 if not control else 1
    original = doc_path.read_text()
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch) / doc_path.name
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
    parser.add_argument("--doc", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--emit", action="store_true", help="print the facts, do not verify")
    parser.add_argument("--selftest", action="store_true", help="mutate a copy, require reactions")
    args = parser.parse_args()

    if args.emit:
        emit()
        return 0
    if args.selftest:
        failures = selftest(args.doc)
        print(f"\nselftest failures: {failures}")
        return 1 if failures else 0

    problems = verify(args.doc)
    if problems:
        print(f"FAIL — {len(problems)} problem(s) in §7 of {display(args.doc)}")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(
        f"PASS — §7 of {display(args.doc)} matches the checked-in evidence "
        f"on all seven gates, and nothing is signed"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
