#!/usr/bin/env python3
"""F1 decision-only process. This module has no evaluator or golden-path import."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from pathlib import Path
import statistics
import time
from typing import Any

from f1_candidate import F1Config, decide_f1, semantic_hash
from runtime_l1 import load_runtime_case, run_runtime_l1
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SPEC = HERE / "f1-ledger-only-family.json"
SPEC_SHA256 = "770b73703550cd989a6125f51a4e32ef352b4d203a7d888589864d19d20d13fb"
PRECONDITION = HERE / "evidence/f1-precondition/f1-precondition.json"
DEFAULT_EVIDENCE = HERE / "evidence/f1"


def config_grid() -> list[dict[str, object]]:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    grid = spec["development_grid"]
    output = []
    for score, margin, budget in itertools.product(
        grid["canonical_min_score"],
        grid["canonical_min_margin"],
        grid["max_changed_duration_fraction"],
    ):
        output.append(
            {
                "config_id": f"f1-s{int(score*100):03d}-m{int(margin*100):03d}-b{int(budget*100):03d}",
                "canonical_min_score": float(score),
                "canonical_min_margin": float(margin),
                "max_changed_duration_fraction": float(budget),
            }
        )
    if len(output) != int(grid["configuration_count"]):
        raise RuntimeError("f1_grid_count_drift")
    return output


def _config(payload: dict[str, object]) -> F1Config:
    return F1Config(
        float(payload["canonical_min_score"]),
        float(payload["canonical_min_margin"]),
        float(payload["max_changed_duration_fraction"]),
    )


def _assert_preconditions() -> dict[str, object]:
    if sha256_file(SPEC) != SPEC_SHA256:
        raise RuntimeError("f1_spec_hash_drift")
    precondition = json.loads(PRECONDITION.read_text(encoding="utf-8"))
    if precondition["overall"] != "PASS" or precondition["scoring_executed"]:
        raise RuntimeError("f1_precondition_not_green")
    return precondition


def _write(path: Path, payload: object) -> None:
    if path.exists():
        raise RuntimeError(f"f1_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _emit(events: list[str], message: str) -> None:
    events.append(message)
    print(message, flush=True)


def decision_mode(split: str, evidence: Path) -> Path:
    precondition = _assert_preconditions()
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    key = f"{split}_case_ids"
    case_ids = spec["target_error_subset"][key]
    if split == "development":
        configs = config_grid()
        output = evidence / "f1-dev-decisions.json"
        transcript = evidence / "f1-dev-decisions.txt"
    elif split == "validation":
        selected_path = evidence / "f1-selected-config.json"
        if not selected_path.is_file():
            raise RuntimeError("f1_validation_before_dev_selection")
        selected = json.loads(selected_path.read_text(encoding="utf-8"))
        if selected["family_spec_sha256"] != SPEC_SHA256:
            raise RuntimeError("f1_selected_config_spec_drift")
        configs = [{"config_id": selected["config_id"], **selected["config"]}]
        output = evidence / "f1-validation-decisions.json"
        transcript = evidence / "f1-validation-decisions.txt"
    else:
        raise RuntimeError(f"f1_decision_split:{split}")
    events: list[str] = []
    cases = []
    for index, case_id in enumerate(case_ids, 1):
        _emit(events, f"L1 {split} {index}/{len(case_ids)} {case_id}")
        runtime = load_runtime_case(case_id)
        if runtime["split"] != split:
            raise RuntimeError(f"f1_runtime_split:{case_id}:{runtime['split']}")
        l1 = run_runtime_l1(runtime)
        l1_hash = semantic_hash(l1)
        decisions = []
        for config_payload in configs:
            config = _config(config_payload)
            first = decide_f1(runtime, l1, config)
            second = decide_f1(runtime, l1, config)
            first_hash = semantic_hash(first)
            second_hash = semantic_hash(second)
            if first_hash != second_hash:
                raise RuntimeError(f"f1_nondeterministic:{case_id}:{config_payload['config_id']}")
            decisions.append(
                {
                    "config_id": config_payload["config_id"],
                    "decision": first,
                    "run1_semantic_sha256": first_hash,
                    "run2_semantic_sha256": second_hash,
                    "deterministic": True,
                }
            )
        cases.append(
            {
                "case_id": case_id,
                "runtime_shape_sha256": runtime["runtime_shape_sha256"],
                "l1": l1,
                "l1_semantic_sha256": l1_hash,
                "decisions": decisions,
            }
        )
        _emit(events, f"PASS {case_id} configs={len(configs)} l1_sha256={l1_hash}")
    payload = {
        "schema": "moss-l15-f1-decisions.v1",
        "family_id": spec["family_id"],
        "family_spec_sha256": SPEC_SHA256,
        "split": split,
        "case_count": len(cases),
        "configuration_count": len(configs),
        "cases": cases,
        "precondition_sha256": sha256_file(PRECONDITION),
        "golden_path_opened": False,
        "scoring_executed": False,
        "holdout_opened": False,
        "overall": "PASS",
    }
    _write(output, payload)
    _write(transcript, {"events": events, "output_sha256": sha256_file(output)})
    print(f"PASS {split} decisions output_sha256={sha256_file(output)}", flush=True)
    return output


def timing_mode(evidence: Path) -> Path:
    _assert_preconditions()
    selected = json.loads((evidence / "f1-selected-config.json").read_text(encoding="utf-8"))
    dev = json.loads((evidence / "f1-dev-decisions.json").read_text(encoding="utf-8"))
    case = next(item for item in dev["cases"] if item["case_id"] == "30m-lex-bill-ackman")
    runtime = load_runtime_case(case["case_id"])
    config = _config(selected["config"])
    samples = []
    hashes = []
    for _index in range(20):
        start = time.perf_counter()
        decision = decide_f1(runtime, case["l1"], config)
        samples.append(time.perf_counter() - start)
        hashes.append(semantic_hash(decision))
    if len(set(hashes)) != 1:
        raise RuntimeError("f1_timing_nondeterministic")
    ordered = sorted(samples)
    position = 0.95 * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    p95 = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    payload = {
        "schema": "moss-l15-f1-timing.v1",
        "case_id": case["case_id"],
        "config_id": selected["config_id"],
        "samples_seconds": samples,
        "sample_count": len(samples),
        "p50_seconds": statistics.median(samples),
        "p95_seconds": p95,
        "gate_seconds": 0.20015926258638502,
        "passed": p95 <= 0.20015926258638502,
        "decision_semantic_sha256": hashes[0],
        "overall": "PASS" if p95 <= 0.20015926258638502 else "FAIL",
    }
    output = evidence / "f1-timing.json"
    _write(output, payload)
    print(f"PASS timing p95={p95:.9f} gate={payload['gate_seconds']:.9f}", flush=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("dev-decisions", "validation-decisions", "timing"))
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE)
    args = parser.parse_args()
    if args.mode == "dev-decisions":
        decision_mode("development", args.evidence_dir)
    elif args.mode == "validation-decisions":
        decision_mode("validation", args.evidence_dir)
    else:
        timing_mode(args.evidence_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
