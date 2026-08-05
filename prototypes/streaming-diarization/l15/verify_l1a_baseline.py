#!/usr/bin/env python3
"""Verify raw L1.a baseline wrappers, repeatability, traces, pins, and timing."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from run_l1_baseline import percentile_type7, semantic_sha256, sha256_file


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    split = json.loads((HERE / "split-manifest.json").read_text(encoding="utf-8"))
    expected_ids = [
        case["case_id"]
        for group in ("development", "validation")
        for case in split["groups"][group]
    ]
    failures: list[str] = []
    checks = {
        "alphabet_gate_passed": summary["accepted_alphabet_gate"]["passed"] is True,
        "case_scope_exact": [case["case_id"] for case in summary["cases"]] == expected_ids,
        "holdout_sealed": summary["holdout"]["opened"] is False,
        "overall_pass": summary["overall"] == "PASS" and not summary["failures"],
        "production_bindings": summary["provenance"]["a2_production_bindings"]["sweep"]
        == "moss_transcribe_diarize.app.live_identity_sweep.sweep",
        "raw_run_count": sum(len(case["runs"]) for case in summary["cases"]) == 32,
    }
    raw_hashes = []
    timing_samples: list[float] = []
    for case in summary["cases"]:
        semantic_hashes = set()
        if len(case["runs"]) != 2 or not case["deterministic"]:
            failures.append(f"repeatability:{case['case_id']}")
        if case["metrics"].get("two_sided_mapping") is not True:
            failures.append(f"two_sided_mapping:{case['case_id']}")
        for run in case["runs"]:
            path = REPO / run["path"]
            actual_file_hash = sha256_file(path)
            if actual_file_hash != run["result_sha256"]:
                failures.append(f"file_hash:{case['case_id']}:{run['run_index']}")
            wrapper = json.loads(path.read_text(encoding="utf-8"))
            actual_semantic = semantic_sha256(wrapper["result"])
            semantic_hashes.add(actual_semantic)
            if actual_semantic != wrapper["semantic_sha256"] or actual_semantic != run["semantic_sha256"]:
                failures.append(f"semantic_hash:{case['case_id']}:{run['run_index']}")
            required = {
                "changed_duration_fraction",
                "final_unit_labels",
                "fixture_fidelity",
                "live_metrics",
                "metrics",
                "revision_trace",
                "span_trace",
            }
            if not required.issubset(wrapper["result"]):
                failures.append(f"trace_surface:{case['case_id']}:{run['run_index']}")
            timing_samples.extend(wrapper["sweep_wall_time"]["samples_seconds"])
            raw_hashes.append(
                {
                    "case_id": case["case_id"],
                    "path": run["path"],
                    "sha256": actual_file_hash,
                }
            )
        if len(semantic_hashes) != 1:
            failures.append(f"semantic_repeatability:{case['case_id']}")
    timing = summary["sweep_compute_baseline"]["30m-lex-bill-ackman"]
    checks["sweep_call_count"] = len(timing_samples) == timing["call_count"] == 64
    checks["sweep_p95_recomputed"] = (
        percentile_type7(timing_samples, 95) == timing["p95_seconds"]
    )
    checks["all_cases_deterministic"] = all(case["deterministic"] for case in summary["cases"])
    checks["all_cases_two_sided"] = all(
        case["metrics"]["two_sided_mapping"] for case in summary["cases"]
    )
    for name, passed in checks.items():
        if not passed:
            failures.append(name)
    for case in split["groups"]["blind_holdout"]:
        for label in ("audio", "reference", "vector_cache"):
            if (REPO / case[f"{label}_path"]).exists():
                failures.append(f"holdout_present:{case['case_id']}:{label}")
    payload = {
        "checks": checks,
        "failures": sorted(set(failures)),
        "overall": "PASS" if not failures else "FAIL",
        "raw_run_count": len(raw_hashes),
        "raw_runs": raw_hashes,
        "schema": "moss-l15-l1a-baseline-verification.v1",
        "summary_path": args.summary.resolve().relative_to(REPO).as_posix(),
        "summary_sha256": sha256_file(args.summary),
        "sweep_p95_seconds": timing["p95_seconds"],
    }
    transcript = "\n".join(
        [
            *(f"{'PASS' if passed else 'FAIL'} {name}" for name, passed in checks.items()),
            f"PASS raw_wrappers_verified={len(raw_hashes)}" if not failures else f"FAIL failures={','.join(failures)}",
            f"RESULT {payload['overall']}",
        ]
    ) + "\n"
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.transcript_output.write_text(transcript, encoding="utf-8")
    print(transcript, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
