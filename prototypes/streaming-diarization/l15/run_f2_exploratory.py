#!/usr/bin/env python3
"""Run the preregistered exploratory F2 lane-prior effect measurement."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from f2_candidate import F2Config, measure_lane_prior, semantic_hash
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SPEC = HERE / "f2-lane-prior-family.json"
FIXTURE = HERE / "exploratory/f2-dual-lane/runtime-fixture.json"
EVIDENCE = HERE / "evidence/f2"
RESULT = EVIDENCE / "f2-exploratory-effects.json"
VERDICT = EVIDENCE / "f2-exploratory-verdict.json"


def load_units() -> tuple[list[dict[str, object]], dict[str, object]]:
    fixture = json.loads(FIXTURE.read_text())
    if fixture["overall"] != "PASS" or fixture["reference_opened"] or fixture["holdout_opened"]:
        raise RuntimeError("f2_fixture_scope_invalid")
    units = []
    for case in fixture["cases"]:
        cache_path = REPO / case["cache_path"]
        if sha256_file(cache_path) != case["cache_sha256"]:
            raise RuntimeError(f"f2_cache_hash:{case['capture_lane']}")
        with np.load(cache_path, allow_pickle=False) as payload:
            rows = payload["rows"].astype(np.float64)
            indexes = payload["vec_idx"].astype(np.int64)
            vectors = payload["vecs"].astype(np.float32)
            if len(rows) != len(indexes):
                raise RuntimeError("f2_cache_shape")
            for index, (row, vector_index) in enumerate(zip(rows, indexes, strict=True)):
                if vector_index < 0:
                    continue
                units.append(
                    {
                        "unit_id": f"{case['capture_lane']}:{index:04d}",
                        "capture_lane": case["capture_lane"],
                        "duration_seconds": float(row[4]),
                        "vector": [float(value) for value in vectors[vector_index]],
                    }
                )
    return units, fixture


def main() -> int:
    if RESULT.exists() or VERDICT.exists():
        raise RuntimeError("f2_exploratory_result_exists")
    spec = json.loads(SPEC.read_text())
    if spec["run_started"] or spec["acceptance_scope"] != "NONE_EXPLORATORY_ONLY":
        raise RuntimeError("f2_preregistration_scope_invalid")
    if spec["holdout"]["status"] != "SEALED" or spec["holdout"]["opening_allowed"]:
        raise RuntimeError("f2_holdout_scope_invalid")
    units, fixture = load_units()
    runs = []
    for strength in spec["exploratory_grid"]["prior_strength"]:
        first = measure_lane_prior(units, F2Config(float(strength)))
        second = measure_lane_prior(units, F2Config(float(strength)))
        first_hash = semantic_hash(first)
        second_hash = semantic_hash(second)
        if first_hash != second_hash:
            raise RuntimeError(f"f2_nondeterministic:{strength}")
        runs.append(
            {
                "prior_strength": strength,
                "run_1_sha256": first_hash,
                "run_2_sha256": second_hash,
                "deterministic": True,
                "measurement": first,
            }
        )
    result = {
        "schema": "moss-l15-f2-exploratory-effects.v1",
        "family_id": spec["family_id"],
        "family_spec_sha256": sha256_file(SPEC),
        "runtime_fixture_sha256": sha256_file(FIXTURE),
        "frame": fixture["frame"],
        "eligible_unit_count": len(units),
        "runs": runs,
        "selection_performed": False,
        "acceptance_scoring_performed": False,
        "identity_accuracy_claim": False,
        "reference_opened": False,
        "gated_corpus_opened": False,
        "validation_opened": False,
        "holdout_opened": False,
        "overall": "PASS_EXPLORATORY_MEASUREMENT",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    requirements = spec["acceptance_grade_evidence_requirements"]
    verdict = {
        "schema": "moss-l15-f2-exploratory-verdict.v1",
        "family_id": spec["family_id"],
        "disposition": "EXPLORATORY_ONLY_NOT_FREEZEABLE",
        "effect_result_path": RESULT.relative_to(REPO).as_posix(),
        "effect_result_sha256": sha256_file(RESULT),
        "effect_by_prior_strength": [
            {
                "prior_strength": run["prior_strength"],
                "margin_weighted_mean_delta": run["measurement"]["margin"]["weighted_mean_delta"],
                "own_lane_classification_rate_before": run["measurement"]["own_lane_classification_rate"]["before"],
                "own_lane_classification_rate_after": run["measurement"]["own_lane_classification_rate"]["after"],
                "classification_rate_delta": run["measurement"]["own_lane_classification_rate"]["delta"],
                "flip_count": run["measurement"]["flips"]["count"],
                "flip_duration_seconds": run["measurement"]["flips"]["duration_seconds"],
            }
            for run in runs
        ],
        "interpretation": "measured acoustic lane-prior effect only; no speaker identity or acceptance claim",
        "acceptance_grade_evidence_requirements": requirements,
        "campaign_gates_applied": False,
        "freezeable": False,
        "holdout_opened": False,
        "overall": "PASS_EXPLORATORY_DELIVERABLE",
    }
    VERDICT.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
    print(f"PASS f2 exploratory units={len(units)} result_sha256={sha256_file(RESULT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
