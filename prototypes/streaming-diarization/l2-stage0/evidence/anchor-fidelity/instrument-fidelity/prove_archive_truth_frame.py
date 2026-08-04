#!/usr/bin/env python3
"""Diagnosis-only gate: identify which reference frame produced cached row truth."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
BENCH = REPO / "prototypes/streaming-diarization"
L2 = BENCH / "l2-stage0"
SOURCE = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
STALE_REFERENCE = SOURCE / (
    "prototypes/streaming-diarization/data/real/benchmark_5m/"
    "acquired_alphabet/reference.jsonl"
)
CORRECTED_REFERENCE = BENCH / (
    "data/real/benchmark_5m/acquired_alphabet/reference.jsonl"
)
SOURCE_CACHE = SOURCE / (
    "prototypes/streaming-diarization/data/real/benchmark_5m/"
    "acquired_alphabet/harness_cache.npz"
)
ARCHIVED_CACHE = BENCH / (
    "data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
)

EXPECTED = {
    "archive": "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5",
    "corrected_reference": "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759",
    "source_cache": "327f33283422b0664911585d2a60e7490979e9c71152ec967cf0d042979aa68a",
    "stale_reference": "27c9b96e86cce3be86a3ce06dd64c1710e2c94e72a01c30339e953db94b8ebbe",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


sys.path.insert(0, str(BENCH))
import proto_ab_identity as harness  # noqa: E402
from proto_real_replay import load_truth as load_v1_truth  # noqa: E402

sys.path.insert(0, str(L2))
from validate_inputs import load_reference  # noqa: E402


def schema_aware_truth(path: Path) -> list[tuple[float, float, int]]:
    speakers: dict[str, int] = {}
    return [
        (start, end, speakers.setdefault(speaker, len(speakers)))
        for start, end, speaker, _text in load_reference(path)
    ]


def cache_rows(truth: list[tuple[float, float, int]]) -> np.ndarray:
    pieces = harness.plan_spans(truth)
    groups: dict[tuple[int, int], list[object]] = {}
    for piece in pieces:
        groups.setdefault((piece.span, piece.true_spk), []).append(piece)
    rows: list[tuple[float, ...]] = []
    for (span, speaker), group in sorted(groups.items()):
        eligible = [piece for piece in group if piece.dur >= harness.MIN_EVID]
        duration = sum(piece.dur for piece in eligible) or sum(
            piece.dur for piece in group
        )
        rows.append(
            (
                float(span),
                float(speaker),
                min(piece.start for piece in group),
                max(piece.end for piece in group),
                duration,
                float(bool(eligible)),
            )
        )
    return np.asarray(rows, dtype=np.float64)


def comparison(actual: np.ndarray, expected: np.ndarray) -> dict[str, object]:
    shape_match = actual.shape == expected.shape
    if not shape_match:
        return {
            "actual_shape": list(actual.shape),
            "exact_match": False,
            "expected_shape": list(expected.shape),
            "max_abs_delta": None,
            "mismatch_row_count": None,
            "mismatch_row_indexes": None,
        }
    mismatch = np.any(actual != expected, axis=1)
    return {
        "actual_shape": list(actual.shape),
        "column_mismatch_counts": [
            int(np.count_nonzero(actual[:, index] != expected[:, index]))
            for index in range(actual.shape[1])
        ],
        "exact_match": bool(np.array_equal(actual, expected)),
        "expected_shape": list(expected.shape),
        "max_abs_delta": float(np.max(np.abs(actual - expected))),
        "mismatch_row_count": int(np.count_nonzero(mismatch)),
        "mismatch_row_indexes": np.flatnonzero(mismatch).astype(int).tolist(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    inputs = output / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)

    for name, path in (
        ("archive", ARCHIVED_CACHE),
        ("corrected_reference", CORRECTED_REFERENCE),
        ("source_cache", SOURCE_CACHE),
        ("stale_reference", STALE_REFERENCE),
    ):
        actual_hash = sha256(path)
        if actual_hash != EXPECTED[name]:
            raise RuntimeError(
                f"frame_input_hash_mismatch:{name}:expected={EXPECTED[name]}:actual={actual_hash}"
            )

    stale_copy = inputs / "stale-reference-27c9b96e.jsonl"
    corrected_copy = inputs / "corrected-reference-28dc9a5b.jsonl"
    stale_copy.write_bytes(STALE_REFERENCE.read_bytes())
    corrected_copy.write_bytes(CORRECTED_REFERENCE.read_bytes())

    stale_truth = load_v1_truth(STALE_REFERENCE.parent)
    corrected_truth = schema_aware_truth(CORRECTED_REFERENCE)
    stale_rows = cache_rows(stale_truth)
    corrected_rows = cache_rows(corrected_truth)
    source_rows = dict(np.load(SOURCE_CACHE))["rows"]
    archive_before = sha256(ARCHIVED_CACHE)
    archive_rows = dict(np.load(ARCHIVED_CACHE))["rows"]
    archive_after = sha256(ARCHIVED_CACHE)

    comparisons = {
        "stale_reference_to_source_cache": comparison(source_rows, stale_rows),
        "stale_reference_to_fd13_archive": comparison(archive_rows, stale_rows),
        "corrected_reference_to_source_cache": comparison(source_rows, corrected_rows),
        "corrected_reference_to_fd13_archive": comparison(
            archive_rows, corrected_rows
        ),
    }
    stale_frame_claim = bool(
        comparisons["stale_reference_to_fd13_archive"]["exact_match"]
        and not comparisons["corrected_reference_to_fd13_archive"]["exact_match"]
    )
    corrected_frame_proved = bool(
        comparisons["corrected_reference_to_fd13_archive"]["exact_match"]
        and not comparisons["stale_reference_to_fd13_archive"]["exact_match"]
    )
    if archive_before != archive_after:
        raise RuntimeError("archived_cache_changed_during_frame_probe")

    result = {
        "schema": "moss-l2-stage0-cache-truth-frame.v1",
        "overall": "BLOCKED" if corrected_frame_proved else "PASS",
        "verdict": (
            "SUPERVISOR_SYNTHESIS_REFUTED_ARCHIVE_IS_CORRECTED_FRAME"
            if corrected_frame_proved
            else (
                "SUPERVISOR_SYNTHESIS_VERIFIED_ARCHIVE_IS_STALE_FRAME"
                if stale_frame_claim
                else "FRAME_ORIGIN_UNRESOLVED"
            )
        ),
        "row_schema": [
            "span_id",
            "truth_speaker_index",
            "unit_start_seconds",
            "unit_end_seconds",
            "eligible_duration_seconds",
            "eligible_flag",
        ],
        "input_hashes": {
            "archive_before": archive_before,
            "archive_after": archive_after,
            "corrected_reference": sha256(CORRECTED_REFERENCE),
            "source_cache": sha256(SOURCE_CACHE),
            "stale_reference": sha256(STALE_REFERENCE),
            "setup_inputs_source": sha256(L2 / "setup_inputs.py"),
            "validate_inputs_source": sha256(L2 / "validate_inputs.py"),
            "plan_spans_source": sha256(BENCH / "proto_ab_identity.py"),
            "v1_loader_source": sha256(BENCH / "proto_real_replay.py"),
        },
        "copied_inputs": {
            "corrected_reference": str(corrected_copy),
            "corrected_reference_sha256": sha256(corrected_copy),
            "stale_reference": str(stale_copy),
            "stale_reference_sha256": sha256(stale_copy),
        },
        "truth_counts": {
            "corrected_turns": len(corrected_truth),
            "stale_turns": len(stale_truth),
        },
        "row_counts": {
            "archive_fd13": len(archive_rows),
            "corrected_reconstruction": len(corrected_rows),
            "source_cache_327f": len(source_rows),
            "stale_reconstruction": len(stale_rows),
        },
        "comparisons": comparisons,
        "raw_rows": {
            "archive_fd13": archive_rows.tolist(),
            "corrected_reconstruction": corrected_rows.tolist(),
            "source_cache_327f": source_rows.tolist(),
            "stale_reconstruction": stale_rows.tolist(),
        },
        "gate": {
            "stale_frame_claim_verified": stale_frame_claim,
            "corrected_frame_proved": corrected_frame_proved,
            "required_stop": corrected_frame_proved,
            "named_error": (
                "frame_gate_archive_matches_corrected_reference"
                if corrected_frame_proved
                else None
            ),
        },
    }
    result_path = output / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    if corrected_frame_proved:
        print("ERROR frame_gate_archive_matches_corrected_reference")
        print("<promise>BLOCKED</promise>")
        return 2
    if not stale_frame_claim:
        print("ERROR frame_gate_origin_unresolved")
        print("<promise>BLOCKED</promise>")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
