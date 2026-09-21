"""Terminal capture observes the native partition decision without changing it."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "prototypes/terminal-label-capture/run.py"
REQUIRED_KEYS = {
    "span_index",
    "source_start",
    "source_end",
    "samples",
    "terminal_local_label",
    "partition_id",
    "eligible",
    "score_by_canonical",
    "margin",
    "decision",
    "published_identity",
}


def _run(*, marker: str, capture: Path | None) -> dict:
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
    if capture is None:
        environment.pop("MOSS_TERMINAL_LABEL_CAPTURE", None)
    else:
        environment["MOSS_TERMINAL_LABEL_CAPTURE"] = str(capture)
    completed = subprocess.run(
        [sys.executable, str(HARNESS), "--returning-marker", marker],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_terminal_capture_is_off_by_default_and_byte_equivalent_when_enabled(tmp_path):
    without_capture = _run(marker="adam", capture=None)
    capture_path = tmp_path / "terminal-labels.jsonl"
    with_capture = _run(marker="adam", capture=capture_path)
    writer_refusal = _run(marker="adam", capture=tmp_path)

    assert without_capture["capture_rows"] == []
    assert without_capture["published_proposal_bytes"] == with_capture["published_proposal_bytes"]
    assert without_capture["published_proposal_bytes"] == writer_refusal["published_proposal_bytes"]
    assert with_capture["published_identities"] == ["speaker-0001"] * 3
    assert len(with_capture["capture_rows"]) == 3
    assert all(set(row) == REQUIRED_KEYS for row in with_capture["capture_rows"])


def test_capture_replays_partition_short_span_adam_and_keyu_controls(tmp_path):
    adam = _run(marker="adam", capture=tmp_path / "adam.jsonl")
    brief, eligible = adam["capture_rows"][1:]

    assert (brief["samples"], brief["eligible"], brief["terminal_local_label"]) == (
        4_320,
        False,
        "S02",
    )
    assert brief["partition_id"] == "system:S02"
    assert brief["published_identity"] == "speaker-0001"
    assert eligible["eligible"] is True
    assert eligible["score_by_canonical"] == {"speaker-0001": pytest.approx(0.909091)}
    assert eligible["margin"] == pytest.approx(0.909091)
    assert eligible["published_identity"] == "speaker-0001"

    keyu = _run(marker="keyu", capture=tmp_path / "keyu.jsonl")
    keyu_eligible = keyu["capture_rows"][2]
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
        partition = product[row["partition_id"]]
        published = {
            span["span_index"]: span["published_identity"]
            for span in partition["spans"]
        }
        assert row["terminal_local_label"] == partition["terminal_local_label"]
        assert row["decision"] == partition["decision"]
        assert row["published_identity"] == published[row["span_index"]]
