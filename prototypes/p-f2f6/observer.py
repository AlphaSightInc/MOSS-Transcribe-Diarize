"""Pure copier of already-decided terminal diagnostics; no decision dependency."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from records import TerminalDecisionDiagnostics


@dataclass(frozen=True, slots=True)
class ObserverReceipt:
    written: bool
    records_attempted: int


def copy_diagnostics(
    diagnostics: TerminalDecisionDiagnostics, destination: Path
) -> ObserverReceipt:
    """Append immutable records and make writer failure observational only."""

    rows = [
        {"record_type": "raw_terminal_span", **asdict(record)}
        for record in diagnostics.raw_spans
    ]
    rows.extend(
        {
            "record_type": "raw_to_normalized",
            **asdict(record),
        }
        for record in diagnostics.raw_to_normalized
    )
    rows.extend(
        {
            "record_type": "normalized_partition",
            **{
                **asdict(record),
                "score_by_canonical": dict(record.score_by_canonical),
            },
        }
        for record in diagnostics.normalized_partitions
    )
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("a", encoding="utf-8") as output:
            for row in rows:
                output.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    except OSError:
        return ObserverReceipt(written=False, records_attempted=len(rows))
    return ObserverReceipt(written=True, records_attempted=len(rows))
