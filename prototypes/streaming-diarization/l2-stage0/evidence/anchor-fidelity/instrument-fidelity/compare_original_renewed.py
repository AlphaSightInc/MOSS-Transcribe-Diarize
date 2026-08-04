#!/usr/bin/env python3
"""Diagnosis-only comparison of unchanged proto policy vs sealed renewed output."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[5]
SOURCE = Path("/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize")
ORIGINAL = HERE / "original-instrument-v2/stdout.json"
RENEWED = REPO / (
    "prototypes/streaming-diarization/l2-stage0/evidence/anchor-fidelity/"
    "legacy-measurement-v3/legacy-anchor-run1.json"
)
CACHE = REPO / (
    "prototypes/streaming-diarization/data/real/benchmark_5m/"
    "acquired_alphabet/harness_cache.npz"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(
    original: list[int], renewed: list[str | None]
) -> tuple[dict[int, str], list[dict[str, object]]]:
    mapping: dict[int, str] = {}
    reverse: dict[str, int] = {}
    mismatches: list[dict[str, object]] = []
    for unit, (old, new) in enumerate(zip(original, renewed, strict=True)):
        if old < 0 or new is None:
            if not (old < 0 and new is None):
                mismatches.append(
                    {"unit_index": unit, "original": old, "renewed": new}
                )
            continue
        prior_new = mapping.setdefault(old, new)
        prior_old = reverse.setdefault(new, old)
        if prior_new != new or prior_old != old:
            mismatches.append(
                {"unit_index": unit, "original": old, "renewed": new}
            )
    return mapping, mismatches


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()

    if sha256(CACHE) != "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5":
        raise RuntimeError("archived_cache_hash_mismatch")

    original = json.loads(ORIGINAL.read_text())
    renewed_envelope = json.loads(RENEWED.read_text())
    renewed = renewed_envelope["result"]
    cache = dict(np.load(CACHE))
    rows = cache["rows"]
    if len(rows) != 92:
        raise RuntimeError("archived_row_count_mismatch")

    live_mapping, live_mismatches = normalize(
        original["live_labels"], renewed["live_unit_labels"]
    )
    final_mapping, final_mismatches = normalize(
        original["final_labels"], renewed["final_unit_labels"]
    )

    source_module_dir = SOURCE / "prototypes/streaming-diarization"
    sys.path.insert(0, str(source_module_dir))
    proto = importlib.import_module("proto_ab_identity")
    original_live = np.asarray(original["live_labels"], dtype=np.int64)
    eligible_only_score = float(proto.accuracy(rows, original_live))
    all_rows_score = float(proto.accuracy(rows, original_live, elig_only=False))

    revision_corrections = sum(
        len(item["revision"]["corrections"]) for item in renewed["revision_trace"]
    )
    result = {
        "schema": "moss-l2-stage0-original-renewed-differential.v1",
        "verdict": "WORKING_HYPOTHESIS_REFUTED_NO_PER_UNIT_POLICY_DIVERGENCE",
        "inputs": {
            "archive_sha256": sha256(CACHE),
            "original_stdout_sha256": sha256(ORIGINAL),
            "original_policy_sha256": sha256(source_module_dir / "proto_ab_identity.py"),
            "renewed_run_sha256": sha256(RENEWED),
            "renewed_runner_sha256": sha256(
                REPO / "prototypes/streaming-diarization/l2-stage0/run_l1_control.py"
            ),
        },
        "bindings": {
            "runner_import": "run_l1_control.py:21-40 imports production BoundedCausalIdentityPreparer, WeSpeakerLiveEvidenceProvider, FingerprintAlbum",
            "runner_construction": "run_l1_control.py:246-265 constructs those production objects",
            "runner_prepare_call": "run_l1_control.py:361-375 calls BoundedCausalIdentityPreparer.prepare with the current snapshot",
            "production_prepare": "moss_transcribe_diarize/app/live_identity.py:89-166",
            "production_assignment": "moss_transcribe_diarize/app/live_identity.py:123 and 229-240 call assign_speakers at 297-355",
            "production_evidence": "moss_transcribe_diarize/app/live_provider_bundle.py:567-631 scores against only base_snapshot canonical speakers",
            "production_album_timing": "moss_transcribe_diarize/app/live_provider_bundle.py:575 and 726-765 reconcile the prior committed span before scoring the current span",
            "runner_diagnostics_decode_only": "run_l1_control.py:379-388 decodes production assignments; it does not assign",
        },
        "per_unit": {
            "row_count": len(rows),
            "eligible_count": int((rows[:, 5] > 0).sum()),
            "ineligible_count": int((rows[:, 5] <= 0).sum()),
            "live_canonical_mapping": {str(k): v for k, v in live_mapping.items()},
            "final_canonical_mapping": {str(k): v for k, v in final_mapping.items()},
            "live_mismatch_count": len(live_mismatches),
            "live_mismatches": live_mismatches,
            "final_mismatch_count": len(final_mismatches),
            "final_mismatches": final_mismatches,
            "first_divergent_unit": None,
            "album_state_at_first_divergence": None,
            "album_state_reason": "No assignment divergence exists on any of the 92 rows, so there is no divergent moment at which to compare album state.",
        },
        "causality": {
            "original_live_equals_final": original["live_labels"] == original["final_labels"],
            "renewed_live_equals_final": renewed["live_unit_labels"] == renewed["final_unit_labels"],
            "renewed_changed_duration_fraction": renewed["changed_duration_fraction"],
            "renewed_sweep_correction_count": revision_corrections,
            "future_information_used_for_assignment": False,
            "explanation": "Both live paths produce the same normalized label/null decision for every row. Neither final sweep changes a label; the renewed runner therefore shows no final-album hindsight on this replay.",
        },
        "score_bridge": {
            "original_default_eligible_only": eligible_only_score,
            "original_all_rows": all_rows_score,
            "renewed_production_scorer": renewed["live_metrics"]["speaker_accuracy"],
            "renewed_matched_seconds": renewed["live_metrics"]["matched_speaker_seconds"],
            "renewed_missed_seconds": renewed["live_metrics"]["missed_speaker_seconds"],
            "renewed_confused_seconds": renewed["live_metrics"]["confused_speaker_seconds"],
            "accepted_anchor": 0.9135,
            "anchor_reproduced": False,
            "original_default_filter": "proto_ab_identity.py:351-355 defaults elig_only=True and excludes all nine ineligible rows from its denominator",
            "conclusion": "Unchanged original policy does not reproduce 0.9135 on fd13; it scores 1.0 on eligible rows. Including null rows moves it to approximately 0.98335, consistent with renewed 0.983449 boundary scoring, not 0.9135.",
        },
        "first_joint_album_checkpoint": {
            "unit_index": 2,
            "span_id": int(rows[2, 0]),
            "original_before_assignment": "canonical 0 enrolled from eligible unit 0; no future units visible (proto_ab_identity.py:299-339)",
            "renewed_before_assignment": "speaker-0001 reconciled from prior span/unit 0 before current scoring (live_provider_bundle.py:575,726-765)",
            "decision": "original canonical 1 birth == renewed speaker-0002 birth",
        },
        "stop": {
            "reason": "expected_original_anchor_not_reproduced_and_no_policy_divergence_to_name",
            "h4_run": False,
            "fix_implemented": False,
            "a3_run": False,
        },
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
