#!/usr/bin/env python3
"""F3 decision-only process; no evaluator or golden-path import."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from f3_candidate import F3Schedule, change_evidence, run_f3, semantic_hash
import runtime_l1
from runtime_l1 import load_runtime_case, run_runtime_l1
from runtime_fixture import sha256_file


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SPEC = HERE / "f3-adaptive-margin-family.json"
SPEC_SHA256 = "56491ebcd5f6aa5da8a2366863b5c7fccbc7e454e2dc1692169ff8572c0e99ae"
PRECONDITION = HERE / "evidence/f3-precondition/f3-precondition.json"
DEFAULT_EVIDENCE = HERE / "evidence/f3"


def schedules() -> list[F3Schedule]:
    spec = json.loads(SPEC.read_text())
    result = [
        F3Schedule(
            item["config_id"],
            tuple((segment["end_seconds_exclusive"], float(segment["margin"])) for segment in item["segments"]),
        )
        for item in spec["development_grid"]["schedules"]
    ]
    if len(result) != int(spec["development_grid"]["configuration_count"]):
        raise RuntimeError("f3_grid_count_drift")
    return result


def _assert_precondition() -> None:
    if sha256_file(SPEC) != SPEC_SHA256:
        raise RuntimeError("f3_spec_hash_drift")
    payload = json.loads(PRECONDITION.read_text())
    if payload["overall"] != "PASS" or payload["scoring_executed"]:
        raise RuntimeError("f3_precondition_not_green")


def _write(path: Path, payload: object) -> None:
    if path.exists():
        raise RuntimeError(f"f3_output_exists:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _decision(runtime: dict[str, Any], l1: dict[str, Any], schedule: F3Schedule) -> dict[str, Any]:
    candidate = run_f3(runtime, schedule)
    changes, fraction = change_evidence(runtime, l1, candidate)
    return {
        "config_id": schedule.config_id,
        "final_unit_labels": candidate["final_unit_labels"],
        "live_unit_labels": candidate["live_unit_labels"],
        "changed_duration_fraction": fraction,
        "corrections": changes,
        "counts": candidate["counts"],
        "span_trace": candidate["span_trace"],
        "revision_trace": candidate["revision_trace"],
        "f3": candidate["f3"],
        "production_bindings": candidate["production_bindings"],
        "production_config": candidate["production_config"],
    }


def decision_mode(split: str, evidence: Path) -> None:
    _assert_precondition()
    spec = json.loads(SPEC.read_text())
    case_ids = spec["target_error_subset"][f"{split}_case_ids"]
    if split == "development":
        configs = schedules()
        output = evidence / "f3-dev-decisions.json"
        transcript = evidence / "f3-dev-decisions.txt"
    elif split == "validation":
        selected = json.loads((evidence / "f3-selected-config.json").read_text())
        if selected["family_spec_sha256"] != SPEC_SHA256:
            raise RuntimeError("f3_selected_config_spec_drift")
        configs = [next(schedule for schedule in schedules() if schedule.config_id == selected["config_id"])]
        output = evidence / "f3-validation-decisions.json"
        transcript = evidence / "f3-validation-decisions.txt"
    else:
        raise RuntimeError(f"f3_split_invalid:{split}")
    events = []
    cases = []
    for case_id in case_ids:
        runtime = load_runtime_case(case_id)
        if runtime["split"] != split:
            raise RuntimeError(f"f3_runtime_split:{case_id}:{runtime['split']}")
        l1 = run_runtime_l1(runtime)
        decisions = []
        events.append(f"RUN {split} {case_id} configs={len(configs)}")
        for schedule in configs:
            first = _decision(runtime, l1, schedule)
            second = _decision(runtime, l1, schedule)
            first_hash = semantic_hash(first)
            second_hash = semantic_hash(second)
            if first_hash != second_hash:
                raise RuntimeError(f"f3_nondeterministic:{case_id}:{schedule.config_id}")
            decisions.append(
                {
                    "config_id": schedule.config_id,
                    "decision": first,
                    "run1_semantic_sha256": first_hash,
                    "run2_semantic_sha256": second_hash,
                    "deterministic": True,
                }
            )
            events.append(f"PASS {case_id} {schedule.config_id} sha256={first_hash}")
        cases.append(
            {
                "case_id": case_id,
                "runtime_shape_sha256": runtime["runtime_shape_sha256"],
                "l1": l1,
                "l1_semantic_sha256": semantic_hash(l1),
                "decisions": decisions,
            }
        )
    payload = {
        "schema": "moss-l15-f3-decisions.v1",
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
    print(f"PASS {split} decisions output_sha256={sha256_file(output)}")


def timing_mode(evidence: Path) -> None:
    _assert_precondition()
    selected = json.loads((evidence / "f3-selected-config.json").read_text())
    schedule = next(item for item in schedules() if item.config_id == selected["config_id"])
    runtime = load_runtime_case("30m-lex-bill-ackman")
    target_code = runtime_l1.a2_control.sweep.__code__
    durations: list[float] = []
    hashes = []
    for _index in range(20):
        starts: dict[int, float] = {}

        def profile(frame: Any, event: str, _arg: Any) -> None:
            if frame.f_code is not target_code:
                return
            key = id(frame)
            if event == "call":
                starts[key] = time.perf_counter()
            elif event in {"return", "exception"}:
                started = starts.pop(key, None)
                if started is not None:
                    durations.append(time.perf_counter() - started)

        previous = sys.getprofile()
        sys.setprofile(profile)
        try:
            decision = run_f3(runtime, schedule)
        finally:
            sys.setprofile(previous)
        hashes.append(semantic_hash(decision))
    if len(set(hashes)) != 1:
        raise RuntimeError("f3_timing_nondeterministic")
    ordered = sorted(durations)
    position = 0.95 * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    p95 = ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)
    gate = 0.20015926258638502
    payload = {
        "schema": "moss-l15-f3-timing.v1",
        "case_id": runtime["case_id"],
        "config_id": schedule.config_id,
        "replay_runs": 20,
        "sweep_call_count": len(durations),
        "sweep_samples_seconds": durations,
        "percentile_method": "linear_type7",
        "p95_seconds": p95,
        "gate_seconds": gate,
        "passed": p95 <= gate,
        "decision_semantic_sha256": hashes[0],
        "overall": "PASS" if p95 <= gate else "FAIL",
    }
    _write(evidence / "f3-timing.json", payload)
    print(f"PASS timing runs=20 sweeps={len(durations)} p95={p95:.9f} gate={gate:.9f}")


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
