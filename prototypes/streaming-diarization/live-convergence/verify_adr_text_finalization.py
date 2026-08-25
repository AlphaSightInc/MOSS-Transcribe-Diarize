#!/usr/bin/env python3
"""Does the text-finalization ADR still quote the plan's decisions verbatim?

Appendix B Q8 of the convergence plan accepted the ADR in advance on one condition: its
content is the plan's architectural decisions *verbatim*. "Verbatim" is checkable, so it is
checked here instead of asserted in prose.

The verifier reads the plan, not a constant, for three things:

  1. which decisions are required   -- parsed out of the Appendix B Q8 row itself
     (e.g. "from D1-D7 verbatim" -> the range 1..7);
  2. what each decision says       -- the `### D<n>` sections of the decisions section;
  3. where the section boundaries  -- the next `### ` heading.

Then it requires the required range to appear in the ADR as one contiguous byte-identical
block, exactly once, and requires every decision *outside* that range to be absent -- so
widening the ADR's scope by copying one more decision fails just as loudly as narrowing it.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/verify_adr_text_finalization.py

Exit 0 = the ADR and the plan still say the same thing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PLAN = REPO_ROOT / "docs/plans/live-mode-convergence-implementation-20260824.md"
DEFAULT_ADR = REPO_ROOT / "docs/adr/0005-live-text-finalization-authority.md"

DECISION_HEADING = re.compile(r"^### D(\d+)\b.*$")
ANY_H3 = re.compile(r"^### ")
# "from D1-D7 verbatim" / "from D1–D7 verbatim", either dash.
REQUIRED_RANGE = re.compile(r"\bD(\d+)\s*[-–—]\s*D(\d+)\b")


def display(path: Path) -> str:
    """Repo-relative when the file is in the repo, absolute when it is a mutated copy."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def parse_decisions(plan_text: str) -> dict[int, str]:
    """Every `### D<n>` section of the plan, keyed by n, trailing blank lines stripped."""
    lines = plan_text.splitlines()
    starts: list[tuple[int, int]] = []
    for index, line in enumerate(lines):
        match = DECISION_HEADING.match(line)
        if match:
            starts.append((int(match.group(1)), index))
    sections: dict[int, str] = {}
    for position, (number, start) in enumerate(starts):
        end = len(lines)
        for candidate in range(start + 1, len(lines)):
            if ANY_H3.match(lines[candidate]):
                end = candidate
                break
        body = lines[start:end]
        while body and not body[-1].strip():
            body.pop()
        if number in sections:
            raise SystemExit(f"plan defines D{number} twice; cannot verify verbatim quoting")
        sections[number] = "\n".join(body)
    return sections


def parse_required_range(plan_text: str) -> tuple[int, int]:
    """The decision range the owner required the ADR to carry, read from the plan."""
    candidates = [
        line for line in plan_text.splitlines()
        if "verbatim" in line and REQUIRED_RANGE.search(line)
    ]
    if not candidates:
        raise SystemExit("no line in the plan states which decisions the ADR must quote verbatim")
    if len(candidates) > 1:
        raise SystemExit(
            "the plan states the verbatim requirement more than once; resolve the ambiguity:\n  "
            + "\n  ".join(candidates)
        )
    match = REQUIRED_RANGE.search(candidates[0])
    assert match is not None
    first, last = int(match.group(1)), int(match.group(2))
    if first > last:
        raise SystemExit(f"the plan asks for an empty decision range D{first}-D{last}")
    return first, last


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--adr", type=Path, default=DEFAULT_ADR)
    args = parser.parse_args()

    plan_text = args.plan.read_text(encoding="utf-8")
    adr_text = args.adr.read_text(encoding="utf-8")

    sections = parse_decisions(plan_text)
    first, last = parse_required_range(plan_text)
    required = list(range(first, last + 1))
    missing = [n for n in required if n not in sections]
    if missing:
        raise SystemExit(f"plan asks for D{first}-D{last} but defines no " + ", ".join(f"D{n}" for n in missing))

    failures: list[str] = []
    print(f"plan            : {display(args.plan)}")
    print(f"record          : {display(args.adr)}")
    print(f"required range  : D{first}-D{last} (read from the plan's own verbatim clause)")
    print(f"decisions found : {', '.join(f'D{n}' for n in sorted(sections))}")
    print()

    for number in required:
        section = sections[number]
        count = adr_text.count(section)
        title = section.splitlines()[0]
        if count == 1:
            print(f"  D{number} verbatim   OK    {len(section):5d} bytes  {title}")
        else:
            print(f"  D{number} verbatim   FAIL  appears {count}x  {title}")
            failures.append(f"D{number} appears {count} times in the record, expected exactly 1")

    contiguous = "\n\n".join(sections[n] for n in required)
    if adr_text.count(contiguous) == 1:
        print(f"\n  contiguous block  OK    {len(contiguous)} bytes, one block, in plan order")
    else:
        print(f"\n  contiguous block  FAIL  found {adr_text.count(contiguous)}x")
        failures.append(
            "the required decisions are not one contiguous block in plan order "
            "(interleaved commentary would let the record drift from the plan silently)"
        )

    outside = [n for n in sorted(sections) if n not in required]
    for number in outside:
        section = sections[number]
        title = section.splitlines()[0]
        if section in adr_text:
            print(f"  D{number} excluded   FAIL  quoted but outside D{first}-D{last}  {title}")
            failures.append(f"D{number} is quoted verbatim but the owner scoped the record to D{first}-D{last}")
        else:
            print(f"  D{number} excluded   OK    not quoted  {title}")

    print()
    if failures:
        print("FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"PASS  the record carries D{first}-D{last} exactly as the plan states them, and nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
