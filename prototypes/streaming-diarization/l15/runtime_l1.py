#!/usr/bin/env python3
"""Run calibrated A2 L1 on a runtime-only ASR frame; no golden path is accepted."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(L2))

import run_l1_control as a2_control  # noqa: E402
from runtime_fixture import sha256_file  # noqa: E402


RUNTIME_MANIFEST = HERE / "runtime-input-manifest.json"
BASELINE_SPEC = HERE / "l1-baseline-spec.json"


def load_runtime_case(case_id: str) -> dict[str, Any]:
    payload = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    matches = [case for case in payload["cases"] if case["case_id"] == case_id]
    if len(matches) != 1:
        raise RuntimeError(f"runtime_case_unknown:{case_id}")
    case = matches[0]
    if case["split"] not in {"development", "validation"}:
        raise RuntimeError(f"runtime_case_holdout_refused:{case_id}")
    cache_path = REPO / case["runtime_cache_path"]
    if sha256_file(cache_path) != case["runtime_cache_sha256"]:
        raise RuntimeError(f"runtime_case_cache_hash:{case_id}")
    return case


def _runtime_activity_rows(runtime: dict[str, Any]) -> list[dict[str, object]]:
    rows = []
    for unit_index, unit in enumerate(runtime["units"]):
        for piece in unit["pieces"]:
            rows.append(
                {
                    "start": piece["start_sample"] / 16_000.0,
                    "end": piece["end_sample"] / 16_000.0,
                    "speaker": f"runtime-unit-{unit_index:05d}",
                }
            )
    return rows


def run_runtime_l1(
    runtime: dict[str, Any], *, suppress_terminal_synthetic_metrics: bool = True
) -> dict[str, Any]:
    """Use A2 replay_case with a temporary activity file made only from runtime units."""

    production = json.loads(BASELINE_SPEC.read_text(encoding="utf-8"))["production_config"]
    cache_path = REPO / runtime["runtime_cache_path"]
    with tempfile.TemporaryDirectory() as directory:
        activity_path = Path(directory) / "runtime-activity.jsonl"
        activity_path.write_text(
            "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in _runtime_activity_rows(runtime)),
            encoding="utf-8",
        )
        original_scorer = a2_control.score_live_speaker_accuracy
        if suppress_terminal_synthetic_metrics:
            # replay_case computes both hypotheses only after every causal assignment and
            # production sweep are complete. Its terminal score is against this temporary
            # runtime activity, is discarded below, and cannot influence those decisions.
            a2_control.score_live_speaker_accuracy = lambda _reference, _hypothesis: {
                "synthetic_terminal_score_suppressed": True
            }
        try:
            result = a2_control.replay_case(
                {
                    "case_id": runtime["case_id"],
                    "reference_path": str(activity_path),
                    "vector_cache_path": str(cache_path),
                    "duration_seconds": runtime["total_samples"] / 16_000.0,
                    "split": runtime["split"],
                },
                production,
                repo_root=REPO,
            )
        finally:
            a2_control.score_live_speaker_accuracy = original_scorer
    # A2's terminal scorer necessarily scores the synthetic runtime activity. Those metrics
    # are discarded and cannot affect the already-computed labels or production traces.
    decision = {
        key: value
        for key, value in result.items()
        if key not in {"metrics", "live_metrics"}
    }
    decision["terminal_synthetic_metrics_suppressed"] = suppress_terminal_synthetic_metrics
    return decision


def decision_units(runtime: dict[str, Any], l1: dict[str, Any]) -> list[dict[str, object]]:
    labels = l1["final_unit_labels"]
    if len(labels) != len(runtime["units"]):
        raise RuntimeError(f"runtime_l1_unit_count:{runtime['case_id']}")
    cache_path = REPO / runtime["runtime_cache_path"]
    with np.load(cache_path, allow_pickle=False) as payload:
        vectors = payload["vecs"].astype(np.float32)
        indexes = payload["vec_idx"].astype(np.int64)
    spans = {span["span_id"]: span for span in runtime["spans"]}
    units = []
    for index, (unit, label) in enumerate(zip(runtime["units"], labels, strict=True)):
        pieces = unit["pieces"]
        units.append(
            {
                "unit_index": index,
                "span_id": unit["span_id"],
                "local_speaker": unit["local_speaker"],
                "span_start": spans[unit["span_id"]]["start_sample"] / 16_000.0,
                "span_end": spans[unit["span_id"]]["end_sample"] / 16_000.0,
                "intervals": [
                    [piece["start_sample"] / 16_000.0, piece["end_sample"] / 16_000.0]
                    for piece in pieces
                ],
                "duration_seconds": sum(
                    (piece["end_sample"] - piece["start_sample"]) / 16_000.0 for piece in pieces
                ),
                "current_speaker": label,
                "vector": (
                    None
                    if indexes[index] < 0
                    else [float(value) for value in vectors[indexes[index]]]
                ),
            }
        )
    return units
