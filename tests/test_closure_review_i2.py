"""Closure-review controls for terminal capture custody."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def _capture_contained_cross_label(tmp_path: Path) -> list[dict[str, object]]:
    capture = tmp_path / "capture.jsonl"
    environment = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(ROOT),
        MOSS_TERMINAL_LABEL_CAPTURE=str(capture),
    )
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "prototypes/terminal-label-capture/run.py"),
            "--returning-marker",
            "adam",
            "--shape",
            "contained_cross_label",
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=True,
    )
    return [
        json.loads(line)
        for line in capture.read_text(encoding="utf-8").splitlines()
    ]


def test_every_terminal_capture_record_is_owned_and_versioned(
    tmp_path: Path,
) -> None:
    """Every I2 capture record, not only partitions, must carry custody."""

    rows = _capture_contained_cross_label(tmp_path)
    assert rows
    assert all(
        row.get("schema_version") == "moss.terminal-identity-diagnostics.v3"
        and row.get("meeting_owner") == "terminal-label-capture"
        and str(row.get("run_owner", "")).startswith(
            "terminal-label-capture:terminal:"
        )
        for row in rows
    )


def test_dropped_raw_terminal_span_remains_lane_scoped(tmp_path: Path) -> None:
    """A span dropped by normalization must still identify its Run-B lane."""

    rows = _capture_contained_cross_label(tmp_path)
    dropped_indexes = {
        row["raw_index"]
        for row in rows
        if row.get("record_type") == "raw_to_normalized"
        and row.get("normalized_partition_id") is None
    }
    dropped_raw = [
        row
        for row in rows
        if row.get("record_type") == "raw_terminal_span"
        and row.get("raw_index") in dropped_indexes
    ]
    assert dropped_raw and all(row.get("source_lane") in {"system", "microphone"} for row in dropped_raw)
