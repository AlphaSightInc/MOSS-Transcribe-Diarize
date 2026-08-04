#!/usr/bin/env python3
"""Quantify every v2 unit whose span failed before identity assignment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def find_repo(path: Path) -> Path:
    for candidate in (path, *path.parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "moss_transcribe_diarize").is_dir():
            return candidate
    raise RuntimeError("contamination_repo_root_not_found")


HERE = Path(__file__).resolve().parent
REPO = find_repo(HERE)
L2 = REPO / "prototypes/streaming-diarization/l2-stage0"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(L2))

from legacy_ingest import derive_legacy_plan, load_legacy_archive  # noqa: E402
from production_cache import PlannerConfig  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    load_reference_speaker_activity_jsonl,
)


ARCHIVE = REPO / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
REFERENCE = REPO / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/reference.jsonl"
SPEC = L2 / "l1-control-spec.json"
RUNNER = L2 / "run_l1_control.py"
ADAPTER = L2 / "legacy_ingest.py"
V2_RUN = L2 / "evidence/anchor-fidelity/legacy-measurement-v2/legacy-anchor-run1.json"
EXPECTED_HASHES = {
    "archive": "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5",
    "reference": "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759",
    "spec": "883503461c225f3bfe5888abf3b3fbb5a071fc630d7e23abbf2f5ba2756ed735",
    "runner": "8719c18a70433b166d563caca72f0075d89cdab2fea74d27cfecac1b168d85d5",
    "adapter_v2": "895aeda6870519ee5b577ce3fc0a47b9c8d7eda84d2af77369e8e503ae9c8c91",
    "v2_run": "d1076d21735de792111f4ce957e9593ebabf98e10d43eb1ae4b0c967d92536a5",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO).as_posix()


def require_inputs() -> dict[str, str]:
    paths = {
        "archive": ARCHIVE,
        "reference": REFERENCE,
        "spec": SPEC,
        "runner": RUNNER,
        "adapter_v2": ADAPTER,
        "v2_run": V2_RUN,
    }
    actual = {name: sha256_file(path) for name, path in paths.items()}
    drift = {
        name: {"expected": EXPECTED_HASHES[name], "actual": actual[name]}
        for name in paths
        if actual[name] != EXPECTED_HASHES[name]
    }
    if drift:
        raise RuntimeError(f"contamination_input_hash_drift:{json.dumps(drift, sort_keys=True)}")
    return actual


def run_probe(output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise RuntimeError(f"contamination_output_dir_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    input_hashes = require_inputs()
    sealed = json.loads(V2_RUN.read_text(encoding="utf-8"))["result"]
    config_payload = json.loads(SPEC.read_text(encoding="utf-8"))["production_config"]
    config = PlannerConfig.from_mapping(config_payload)
    reference = load_reference_speaker_activity_jsonl(REFERENCE)
    truth = [(item.start, item.end, item.speaker, "") for item in reference]
    archive = load_legacy_archive(ARCHIVE)
    plan = derive_legacy_plan(
        archive,
        truth,
        total_samples=300 * config.sample_rate,
        config=config,
    )
    nonprepared = {
        int(item["span_id"]): item
        for item in sealed["span_trace"]
        if item["status"] != "prepared"
    }
    affected = []
    for unit_index, (unit, row) in enumerate(zip(plan.units, archive.rows, strict=True)):
        trace = nonprepared.get(unit.span_id)
        if trace is None:
            continue
        live_label = sealed["live_unit_labels"][unit_index]
        final_label = sealed["final_unit_labels"][unit_index]
        if live_label is not None or final_label is not None:
            raise RuntimeError(f"contamination_nonprepared_unit_labelled:{unit_index}")
        piece_seconds = sum(piece.duration for piece in unit.pieces)
        affected.append(
            {
                "assignment_handling": "bypassed_before_evidence_and_assignment",
                "eligible_for_embedding": bool(row[5]),
                "evidence_duration_seconds": round(float(row[4]), 9),
                "final_label": final_label,
                "hypothesis_interval_count": 0,
                "ledger_record_count": len(trace["ledger_records"]),
                "live_label": live_label,
                "preparation_reason": trace["diagnostics"]["reason"],
                "preparation_status": trace["status"],
                "reference_piece_seconds": round(piece_seconds, 9),
                "score_handling": "no_hypothesis_interval; reference_time_remains_denominator_and_is_missed",
                "span_id": unit.span_id,
                "true_speaker_index": unit.true_speaker,
                "unit_index": unit_index,
            }
        )
    if not affected:
        raise RuntimeError("contamination_no_nonprepared_units")
    metrics = sealed["metrics"]
    expected_accuracy = metrics["matched_speaker_seconds"] / metrics["reference_seconds"]
    if abs(expected_accuracy - metrics["speaker_accuracy"]) > 1e-6:
        raise RuntimeError("contamination_scorer_formula_unexpected")
    result = {
        "affected_eligible_unit_count": sum(item["eligible_for_embedding"] for item in affected),
        "affected_reference_piece_seconds": round(
            sum(float(item["reference_piece_seconds"]) for item in affected), 9
        ),
        "affected_unit_count": len(affected),
        "affected_units": affected,
        "failed_span_count": len(nonprepared),
        "failed_spans": [
            {
                "reason": item["diagnostics"]["reason"],
                "span_id": span_id,
                "status": item["status"],
            }
            for span_id, item in sorted(nonprepared.items())
        ],
        "inflation_mechanism": {
            "direct_scalar_inflation_from_omission": False,
            "name": "pre_assignment_censoring_as_null_hypothesis",
            "statement": (
                "The adapter bypassed policy and emitted null labels, so the scorer saw no "
                "confusing hypothesis intervals or mapping evidence for these units. Production "
                "speaker_accuracy retains all reference time in its denominator, so omitted "
                "seconds are missed and receive zero credit; omission alone cannot arithmetically "
                "inflate this scalar. It contaminates the instrument by censoring the decisions "
                "whose fidelity was being tested."
            ),
        },
        "input_hashes": input_hashes,
        "schema": "moss-l2-stage0-v2-contamination.v1",
        "score_formula": {
            "matched_speaker_seconds": metrics["matched_speaker_seconds"],
            "reference_seconds": metrics["reference_seconds"],
            "speaker_accuracy": metrics["speaker_accuracy"],
            "speaker_accuracy_recomputed": round(expected_accuracy, 9),
            "missed_speaker_seconds": metrics["missed_speaker_seconds"],
            "confused_speaker_seconds": metrics["confused_speaker_seconds"],
        },
        "score_path": {
            "null_filter": "prototypes/streaming-diarization/l2-stage0/run_l1_control.py:202-210",
            "scorer_call": "prototypes/streaming-diarization/l2-stage0/run_l1_control.py:432-435",
        },
        "verdict": "V2_CONTAMINATED_PRE_ASSIGNMENT",
    }
    result_path = output_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    transcript_path = output_dir / "transcript.txt"
    lines = [
        "V2 contamination quantification",
        f"failed_spans={len(nonprepared)} affected_units={len(affected)} eligible_units={result['affected_eligible_unit_count']}",
        *(
            "unit={unit_index} span={span_id} eligible={eligible_for_embedding} "
            "evidence_seconds={evidence_duration_seconds:.9f} reference_seconds={reference_piece_seconds:.9f} "
            "status={preparation_status}/{preparation_reason} labels=null/null hypothesis_intervals=0".format(**item)
            for item in affected
        ),
        f"matched={metrics['matched_speaker_seconds']:.9f} reference={metrics['reference_seconds']:.9f} missed={metrics['missed_speaker_seconds']:.9f} confused={metrics['confused_speaker_seconds']:.9f}",
        "MECHANISM pre_assignment_censoring_as_null_hypothesis",
        "DIRECT_SCALAR_INFLATION_FROM_OMISSION False",
        "VERDICT V2_CONTAMINATED_PRE_ASSIGNMENT",
    ]
    transcript_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = output_dir / "V2_CONTAMINATION_EVIDENCE.sha256"
    manifest_inputs = [
        Path(__file__).resolve(),
        ARCHIVE,
        REFERENCE,
        SPEC,
        RUNNER,
        V2_RUN,
        result_path,
        transcript_path,
    ]
    manifest_path.write_text(
        "\n".join(
            f"{sha256_file(path)}  {repo_path(path)}" for path in sorted(manifest_inputs)
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        **{key: value for key, value in result.items() if key != "affected_units"},
        "evidence_manifest_path": repo_path(manifest_path),
        "evidence_manifest_sha256": sha256_file(manifest_path),
        "result_path": repo_path(result_path),
        "result_sha256": sha256_file(result_path),
        "transcript_path": repo_path(transcript_path),
        "transcript_sha256": sha256_file(transcript_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_probe(args.output_dir)
    except Exception as exc:
        print(f"BLOCKED {exc.__class__.__name__}:{exc}")
        print("<promise>BLOCKED</promise>")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
