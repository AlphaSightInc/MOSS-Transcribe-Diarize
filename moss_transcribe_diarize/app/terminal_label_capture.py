"""Opt-in serialization of terminal diagnostics already decided by the live path."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock


ENVIRONMENT_VARIABLE = "MOSS_TERMINAL_LABEL_CAPTURE"


def capture_from_environment() -> "TerminalLabelCapture | None":
    """Return an explicit sink, or nothing on the ordinary product path."""

    destination = os.environ.get(ENVIRONMENT_VARIABLE)
    return TerminalLabelCapture(Path(destination)) if destination else None


class TerminalLabelCapture:
    """Serialize immutable native diagnostics; writer failure stays observational."""

    def __init__(self, destination: Path):
        self.destination = destination
        self._lock = Lock()

    def record_diagnostics(
        self,
        raw_spans: tuple[object, ...],
        raw_to_normalized: tuple[object, ...],
        partitions: tuple[object, ...],
        *,
        meeting_owner: str,
        run_owner: str,
        schema_version: str,
    ) -> None:
        custody = {
            "schema_version": schema_version,
            "meeting_owner": meeting_owner,
            "run_owner": run_owner,
        }
        raw_lanes = {span.raw_index: span.source_lane for span in raw_spans}
        rows = [
            {
                **custody,
                "record_type": "raw_terminal_span",
                "raw_index": span.raw_index,
                "terminal_local_label": span.terminal_local_label,
                "start": span.start,
                "end": span.end,
                "samples": span.samples,
                "source_lane": span.source_lane,
            }
            for span in raw_spans
        ]
        rows.extend(
            {
                **custody,
                "record_type": "raw_to_normalized",
                "raw_index": mapping.raw_index,
                "normalized_partition_id": mapping.normalized_partition_id,
                "disposition": mapping.disposition,
                "source_lane": raw_lanes.get(mapping.raw_index),
            }
            for mapping in raw_to_normalized
        )
        rows.extend(self._partition_row(partition) for partition in partitions)
        self._append(rows)

    def record_partitions(self, partitions: tuple[object, ...]) -> None:
        """Serialize handed partition values for callers that need only that stream."""

        self._append([self._partition_row(partition) for partition in partitions])

    @staticmethod
    def _partition_row(partition: object) -> dict[str, object]:
        return {
            "record_type": "normalized_partition",
            "schema_version": partition.schema_version,
            "meeting_owner": partition.meeting_owner,
            "run_owner": partition.run_owner,
            "terminal_local_label": partition.terminal_local_label,
            "partition_id": partition.partition_id,
            "member_raw_indexes": list(partition.member_raw_indexes),
            "start": partition.start,
            "end": partition.end,
            "samples": partition.samples,
            "eligibility_floor_samples": partition.minimum_samples,
            "eligible": partition.eligible,
            "score_by_canonical": dict(partition.score_by_canonical),
            "margin": partition.margin,
            "decision": partition.decision,
            "published_identity": partition.published_identity,
        }

    def _append(self, rows: list[dict[str, object]]) -> None:
        try:
            with self._lock:
                self.destination.parent.mkdir(parents=True, exist_ok=True)
                with self.destination.open("a", encoding="utf-8") as output:
                    for row in rows:
                        output.write(
                            json.dumps(row, sort_keys=True, separators=(",", ":"))
                            + "\n"
                        )
        except Exception:
            pass
