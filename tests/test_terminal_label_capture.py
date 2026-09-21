"""Terminal capture observes the native partition decision without changing it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.live_transcript_convergence import (
    RawTerminalSpan,
    RawToNormalizedSpan,
    TerminalPartitionDecision,
)


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "prototypes/terminal-label-capture/run.py"
RAW_KEYS = {
    "record_type",
    "raw_index",
    "terminal_local_label",
    "start",
    "end",
    "samples",
}
MAPPING_KEYS = {
    "record_type",
    "raw_index",
    "normalized_partition_id",
    "disposition",
}
PARTITION_KEYS = {
    "record_type",
    "schema_version",
    "meeting_owner",
    "run_owner",
    "terminal_local_label",
    "partition_id",
    "member_raw_indexes",
    "start",
    "end",
    "samples",
    "eligibility_floor_samples",
    "eligible",
    "score_by_canonical",
    "margin",
    "decision",
    "published_identity",
}


def _run(*, marker: str, capture: Path | None, shape: str = "partition") -> dict:
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
    if capture is None:
        environment.pop("MOSS_TERMINAL_LABEL_CAPTURE", None)
    else:
        environment["MOSS_TERMINAL_LABEL_CAPTURE"] = str(capture)
    completed = subprocess.run(
        [
            sys.executable,
            str(HARNESS),
            "--returning-marker",
            marker,
            "--shape",
            shape,
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_terminal_diagnostic_values_are_immutable() -> None:
    assert RawTerminalSpan.__dataclass_params__.frozen is True
    assert RawToNormalizedSpan.__dataclass_params__.frozen is True
    assert TerminalPartitionDecision.__dataclass_params__.frozen is True


def test_terminal_capture_is_off_by_default_and_byte_equivalent_when_enabled(tmp_path):
    without_capture = _run(marker="adam", capture=None)
    capture_path = tmp_path / "terminal-labels.jsonl"
    with_capture = _run(marker="adam", capture=capture_path)
    writer_refusal = _run(marker="adam", capture=tmp_path)

    assert without_capture["capture_rows"] == []
    assert without_capture["published_proposal_bytes"] == with_capture["published_proposal_bytes"]
    assert without_capture["published_proposal_bytes"] == writer_refusal["published_proposal_bytes"]
    assert with_capture["published_identities"] == ["speaker-0001"] * 3
    rows = with_capture["capture_rows"]
    assert [row["record_type"] for row in rows] == [
        "raw_terminal_span",
        "raw_terminal_span",
        "raw_terminal_span",
        "raw_to_normalized",
        "raw_to_normalized",
        "raw_to_normalized",
        "normalized_partition",
        "normalized_partition",
    ]
    assert all(set(row) == RAW_KEYS for row in rows[:3])
    assert all(set(row) == MAPPING_KEYS for row in rows[3:6])
    assert all(set(row) == PARTITION_KEYS for row in rows[6:])
    assert {row["meeting_owner"] for row in rows[6:]} == {
        "terminal-label-capture"
    }
    assert all(
        row["run_owner"].startswith("terminal-label-capture:terminal:")
        for row in rows[6:]
    )


def test_capture_replays_partition_short_span_adam_and_keyu_controls(tmp_path):
    adam = _run(marker="adam", capture=tmp_path / "adam.jsonl")
    raw = [row for row in adam["capture_rows"] if row["record_type"] == "raw_terminal_span"]
    partitions = {
        row["partition_id"]: row
        for row in adam["capture_rows"]
        if row["record_type"] == "normalized_partition"
    }
    assert (raw[1]["samples"], raw[1]["terminal_local_label"]) == (4_320, "S02")
    eligible = partitions["system:S02"]
    assert eligible["eligible"] is True
    assert eligible["member_raw_indexes"] == [1, 2]
    assert eligible["score_by_canonical"] == {"speaker-0001": pytest.approx(0.909091)}
    assert eligible["margin"] == pytest.approx(0.909091)
    assert eligible["published_identity"] == "speaker-0001"

    keyu = _run(marker="keyu", capture=tmp_path / "keyu.jsonl")
    keyu_eligible = next(
        row
        for row in keyu["capture_rows"]
        if row.get("partition_id") == "system:S02"
    )
    assert keyu_eligible["eligible"] is True
    assert keyu_eligible["score_by_canonical"] == {"speaker-0001": pytest.approx(0.017033)}
    assert keyu_eligible["margin"] == pytest.approx(0.017033)
    assert keyu_eligible["published_identity"] is None


def test_capture_partition_id_and_decision_are_the_product_records(tmp_path):
    payload = _run(marker="adam", capture=tmp_path / "terminal-labels.jsonl")
    product = {
        partition["partition_id"]: partition
        for partition in payload["product_terminal_partitions"]
    }

    assert product["system:S02"]["decision"] == "terminal_partition_probe"
    assert [span["span_index"] for span in product["system:S02"]["spans"]] == [1, 2]
    for row in payload["capture_rows"]:
        if row["record_type"] != "normalized_partition":
            continue
        partition = product[row["partition_id"]]
        assert row["terminal_local_label"] == partition["terminal_local_label"]
        assert row["decision"] == partition["decision"]
        assert row["member_raw_indexes"] == partition["member_raw_indexes"]
        assert row["score_by_canonical"] == partition["score_by_canonical"]
        assert row["published_identity"] == partition["published_identity"]


def test_raw_stream_keeps_contained_cross_label_and_maps_it_to_no_partition(tmp_path):
    payload = _run(
        marker="adam",
        capture=tmp_path / "contained.jsonl",
        shape="contained_cross_label",
    )
    raw = [
        row for row in payload["capture_rows"]
        if row["record_type"] == "raw_terminal_span"
    ]
    mapping = [
        row for row in payload["capture_rows"]
        if row["record_type"] == "raw_to_normalized"
    ]

    assert [row["terminal_local_label"] for row in raw] == ["S01", "S02"]
    assert mapping[1] == {
        "record_type": "raw_to_normalized",
        "raw_index": 1,
        "normalized_partition_id": None,
        "disposition": "dropped_by_normalization",
    }


def test_same_label_merge_maps_both_raw_spans_to_one_native_partition(tmp_path):
    payload = _run(
        marker="adam",
        capture=tmp_path / "same-label.jsonl",
        shape="same_label_merge",
    )
    mapping = [
        row for row in payload["capture_rows"]
        if row["record_type"] == "raw_to_normalized"
    ]
    partition = next(
        row for row in payload["capture_rows"]
        if row["record_type"] == "normalized_partition"
    )

    assert [row["normalized_partition_id"] for row in mapping] == [
        "system:S01",
        "system:S01",
    ]
    assert partition["member_raw_indexes"] == [0, 1]
