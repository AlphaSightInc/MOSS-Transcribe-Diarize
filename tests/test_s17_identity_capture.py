"""S17 refuses capture evidence without record-level custody."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "s17_identity_rerun", ROOT / "prototypes/s17-identity-rerun/run.py"
)
assert SPEC is not None and SPEC.loader is not None
S17 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S17)


def _rows() -> list[dict[str, object]]:
    custody = {
        "schema_version": "moss.terminal-identity-diagnostics.v3",
        "meeting_owner": "meeting-a",
        "run_owner": "meeting-a:terminal:0:1",
    }
    return [
        {
            **custody,
            "record_type": "raw_terminal_span",
            "source_lane": "system",
            "raw_index": 0,
            "terminal_local_label": "S01",
            "start": 0,
            "end": 8_000,
            "samples": 8_000,
        },
        {
            **custody,
            "record_type": "raw_to_normalized",
            "source_lane": "system",
            "raw_index": 0,
            "normalized_partition_id": "system:S01",
            "disposition": "survived",
        },
        {
            **custody,
            "record_type": "normalized_partition",
            "terminal_local_label": "S01",
            "partition_id": "system:S01",
            "member_raw_indexes": [0],
            "start": 0,
            "end": 8_000,
            "samples": 8_000,
            "eligibility_floor_samples": 8_000,
            "eligible": True,
            "score_by_canonical": {},
            "margin": None,
            "decision": "terminal_overlap_mapping",
            "published_identity": None,
        },
    ]


def test_s17_accepts_record_level_owner_and_lane() -> None:
    receipt = S17.partition_receipt("single", _rows())

    assert receipt["raw_terminal_spans"][0]["source_lane"] == "system"
    assert receipt["raw_terminal_spans"][0]["meeting_owner"] == "meeting-a"


@pytest.mark.parametrize("missing", ["meeting_owner", "run_owner", "source_lane"])
def test_s17_marks_raw_row_without_owner_or_lane_incomplete(missing: str) -> None:
    rows = _rows()
    del rows[0][missing]

    with pytest.raises(S17.IncompleteCaptureReceipt, match="^INCOMPLETE:"):
        S17.partition_receipt("single", rows)
