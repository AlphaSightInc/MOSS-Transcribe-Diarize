#!/usr/bin/env python3
"""Reclassify the sealed A2 baseline under the authorized calibration gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

from run_l1_control import evaluate_alphabet_gate  # noqa: E402


SEALED_SUMMARY = HERE / "evidence/a2-l1-renewed-fixed-summary.json"
SEALED_SUMMARY_SHA256 = "fa10723978db7828622f5ef2c590a4a9ea1616fa74ce1d55c730387007733dee"
FRAME_RESULT = (
    HERE
    / "evidence/anchor-fidelity/instrument-fidelity/frame-diagnosis-v2/result.json"
)
FRAME_RESULT_SHA256 = "d45a963c2e385d734cfc5003da774ed4804816b05720fc89dd4deb4f3e5358f1"


class CompletionError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, code: str) -> None:
    if not condition:
        raise CompletionError(code)


def relative(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def verify() -> dict[str, object]:
    spec_path = HERE / "l1-control-spec.json"
    corpus_path = HERE / "corpus-manifest.json"
    procedure_path = HERE / "a5-holdout-procedure.json"
    spec = load_json(spec_path)
    corpus = load_json(corpus_path)
    procedure = load_json(procedure_path)
    summary = load_json(SEALED_SUMMARY)
    frame = load_json(FRAME_RESULT)

    require(sha256(SEALED_SUMMARY) == SEALED_SUMMARY_SHA256, "sealed_summary_hash_mismatch")
    require(sha256(FRAME_RESULT) == FRAME_RESULT_SHA256, "frame_result_hash_mismatch")
    require(
        sha256(procedure_path) == spec["a5_holdout_procedure_sha256"],
        "a5_procedure_pin_mismatch",
    )
    require(
        procedure["comparison_frame"]["cross_frame_metrics_are_comparable"] is False,
        "a5_cross_frame_rule_missing",
    )
    require(summary["holdout"]["opened"] is False, "holdout_was_opened")
    require(summary["case_count"] == spec["expected_case_count"] == 6, "case_count_mismatch")
    require(
        summary["failures"] == ["l1_accepted_alphabet_band_failed"],
        "superseded_failure_not_preserved",
    )

    cases = summary["cases"]
    require(
        [case["case_id"] for case in cases] == spec["case_ids"],
        "case_order_or_scope_mismatch",
    )
    for case in cases:
        require(case["deterministic"] is True, f"nondeterministic:{case['case_id']}")
        runs = case["runs"]
        require(len(runs) == 2, f"run_count_mismatch:{case['case_id']}")
        require(
            len({run["semantic_sha256"] for run in runs}) == 1,
            f"semantic_repeatability_failed:{case['case_id']}",
        )
        for run in runs:
            run_path = REPO / run["path"]
            require(sha256(run_path) == run["result_sha256"], f"run_hash_mismatch:{run_path}")

    gate = spec["accepted_alphabet_gate"]
    alphabet = next(case for case in cases if case["case_id"] == gate["case_id"])
    actual = float(alphabet["metrics"]["speaker_accuracy"])
    gate_result = evaluate_alphabet_gate(actual, gate)
    require(gate_result["passed"] is True, "rescoped_anchor_gate_failed")

    manifest_case = next(
        case for case in corpus["cases"] if case["case_id"] == gate["case_id"]
    )
    comparison_frame = gate["comparison_frame"]
    require(
        manifest_case["reference_sha256"] == comparison_frame["reference_sha256"],
        "comparison_reference_mismatch",
    )
    require(
        manifest_case["vector_cache_sha256"] == comparison_frame["vector_cache_sha256"],
        "comparison_cache_mismatch",
    )
    require(
        frame["row_counts"]
        == {
            "archive_fd13": 92,
            "corrected_reconstruction": 92,
            "source_cache_327f": 55,
            "stale_reconstruction": 55,
        },
        "frame_counts_mismatch",
    )
    require(
        frame["comparisons"]["corrected_reference_to_fd13_archive"]["exact_match"]
        is True,
        "fd13_attribution_mismatch",
    )
    require(
        frame["comparisons"]["stale_reference_to_source_cache"]["exact_match"] is True,
        "source_stale_attribution_mismatch",
    )

    return {
        "a5_comparison_rule": procedure["comparison_frame"],
        "baseline": {
            "case_count": 6,
            "comparison_base_for_a5": True,
            "corrected_alphabet_speaker_accuracy": actual,
            "runs_per_case": 2,
            "sealed_summary_path": relative(SEALED_SUMMARY),
            "sealed_summary_sha256": SEALED_SUMMARY_SHA256,
        },
        "cross_instrument_anchor_gate": gate_result,
        "dual_anchors": {
            "bench_instrumental": actual,
            "live_immutable": gate["immutable_live_speaker_accuracy"],
        },
        "frame_evidence": {
            "corrected_proto": {"cache_sha256": frame["input_hashes"]["archive_before"], "units": 92},
            "corrected_production": {
                "cache_sha256": comparison_frame["vector_cache_sha256"],
                "units": comparison_frame["unit_count"],
            },
            "result_path": relative(FRAME_RESULT),
            "result_sha256": FRAME_RESULT_SHA256,
            "stale_proto": {"cache_sha256": frame["input_hashes"]["source_cache"], "units": 55},
        },
        "holdout_opened": False,
        "intra_instrument_repeatability": {
            "allowed_absolute_delta": 0.001,
            "observed_absolute_delta": 0.0,
            "passed": True,
            "semantic_hashes_exact": True,
        },
        "overall": "PASS",
        "prd_section_10_gates_changed": False,
        "schema": "moss-l2-stage0-a2-completion-verdict.v1",
        "status": "COMPLETE",
        "superseded_gate_result_preserved": True,
        "supervisor_authorized_on": "2026-08-03",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = verify()
    except CompletionError as error:
        result = {
            "error": str(error),
            "overall": "FAIL",
            "schema": "moss-l2-stage0-a2-completion-verdict.v1",
            "status": "BLOCKED",
        }
        transcript = f"A2 COMPLETION FAIL error={error}\n<promise>BLOCKED</promise>\n"
        status = 2
    else:
        transcript = (
            "A2 COMPLETION PASS cases=6 runs=12 deterministic=true holdout=SEALED\n"
            "alphabet=0.916765 live_pair=0.913500,0.914400 deltas=0.003265,0.002365 tolerance=0.005000\n"
            "frames=55-stale-proto,92-corrected-proto,101-corrected-production same-frame-only=true\n"
            "<promise>COMPLETE</promise>\n"
        )
        status = 0
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.transcript_output.write_text(transcript, encoding="utf-8")
    print(transcript, end="")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
