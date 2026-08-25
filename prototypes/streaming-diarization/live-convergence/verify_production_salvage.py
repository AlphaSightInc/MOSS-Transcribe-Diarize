"""Does the shipped `classify_live_transcript` decide exactly what plan §9.1 measured?

The M1a comparison ran a throwaway classifier over the 184-span corpus of plan §9.2 and
adjudicated O1 (hard-cap freeze) against O2 (recomputed speech ratio). This replays that
adjudicated O1 column against the *production* module, so "the prototype won and the product
shipped something else" is a failure rather than a story.

One difference is expected and is asserted, not tolerated: the prototype consulted a refusal
phrase list before the gate, so it reported `refused_boilerplate` for six spans. Production
ships no phrase list -- measured, it refused nothing the gate had not -- so those same six
spans must come back `refused_gate`, still refused, for a reason that is a fact about the
span rather than about the English language.

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/verify_production_salvage.py

Exit 0 iff every span agrees. Issues zero MOSS requests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
for path in (str(REPO), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)

from compare_salvage_gates import constructed_spans  # noqa: E402

from moss_transcribe_diarize.app.live_span_bounds import classify_live_transcript  # noqa: E402

COMPARISON = REPO / "evidence/live-convergence-0824/M1a-salvage-gate-comparison/comparison.json"
#: The prototype's phrase list ran ahead of the gate; production has no phrase list, and the
#: gate refuses every span the list did.
PROTOTYPE_ONLY = {"refused_boilerplate": "refused_gate"}


def main() -> int:
    rows = json.loads(COMPARISON.read_text(encoding="utf-8"))["rows"]
    failures: list[str] = []
    tally: dict[str, int] = {}

    for row in rows:
        sample_count = round(row["duration_s"] * 16000)
        outcome = classify_live_transcript(
            row["text"], sample_count=sample_count, freeze_reason=row["freeze_reason"]
        )
        measured = row["O1_hard_cap"]
        expected = PROTOTYPE_ONLY.get(measured["disposition"], measured["disposition"])
        where = f"{row['case']}#{row['span_id']} ({row['freeze_reason']})"
        tally[outcome.disposition.value] = tally.get(outcome.disposition.value, 0) + 1
        if outcome.disposition.value != expected:
            failures.append(f"{where}: expected {expected}, got {outcome.disposition.value}")
        elif outcome.publishes != measured["publishes"]:
            failures.append(f"{where}: publishes {outcome.publishes}, measured {measured['publishes']}")
        elif outcome.disposition.value == "salvaged" and outcome.transcript != measured["rendered"]:
            failures.append(f"{where}: {outcome.transcript!r} != measured {measured['rendered']!r}")

    for span in constructed_spans():
        outcome = classify_live_transcript(
            span["text"], sample_count=span["sample_count"], freeze_reason=span["freeze_reason"]
        )
        if outcome.disposition.value != span["expect"]:
            failures.append(f"constructed {span['name']}: expected {span['expect']}, got {outcome.disposition.value}")
        elif len(outcome.segments) != span["expect_speakers"]:
            failures.append(
                f"constructed {span['name']}: {len(outcome.segments)} segments, expected {span['expect_speakers']}"
            )

    print(f"corpus spans: {len(rows)}   constructed: {len(constructed_spans())}")
    print("production dispositions: " + json.dumps(dict(sorted(tally.items()))))
    for failure in failures:
        print(f"DISAGREES  {failure}")
    print("PASS" if not failures else f"FAIL ({len(failures)} disagreements)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
