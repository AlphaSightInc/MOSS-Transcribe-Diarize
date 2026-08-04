#!/usr/bin/env python3
"""Diagnosis-only replay of current L1 scoring over a legacy-ingested cache."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Iterator

import run_l1_control as control
from legacy_ingest import (
    LEGACY_REASON,
    derive_legacy_plan,
    load_legacy_archive,
    validate_adapted_cache,
    write_adapted_cache,
)


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
OFFICIAL_RUNNER = HERE / "run_l1_control.py"
OFFICIAL_CORPUS = HERE / "corpus-manifest.json"
OFFICIAL_SPEC = HERE / "l1-control-spec.json"
CONTRACT = REPO / "scripts/ralph-l2-afk/contract.json"
ARCHIVED_CACHE = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_5m/acquired_alphabet/harness_cache.npz"
)
SPAN_REASON_AUDIT = (
    HERE / "evidence/anchor-fidelity/span-reason-independence-audit-post-duration.json"
)
SPAN_REASON_TEST = HERE / "evidence/anchor-fidelity/legacy-green-reason-post-duration.json"
CASE_ID = "5m-acquired-alphabet"
EXPECTED_OFFICIAL_RUNNER_SHA256 = (
    "8719c18a70433b166d563caca72f0075d89cdab2fea74d27cfecac1b168d85d5"
)
EXPECTED_ARCHIVED_CACHE_SHA256 = (
    "fd13bacb3ee8397354c0ae55a8b9534db9df56b13dce73c0b956d7cdf3947be5"
)
EXPECTED_ANCHOR = 0.9135
EXPECTED_TOLERANCE = 0.001
RUN_COUNT = 2


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


@contextmanager
def _legacy_plan_seam(plan, archive) -> Iterator[None]:
    original_plan_reference = control.plan_reference
    original_validate_cache = control.validate_cache

    def use_legacy_plan(_rows, *, total_samples, config):
        if total_samples != plan.total_samples:
            raise RuntimeError("legacy_plan_total_samples_drift")
        return plan

    def validate_legacy(path, candidate_plan, *, config):
        if candidate_plan is not plan:
            raise RuntimeError("legacy_plan_identity_drift")
        return validate_adapted_cache(path, archive, plan, config=config)

    control.plan_reference = use_legacy_plan
    control.validate_cache = validate_legacy
    try:
        yield
    finally:
        control.plan_reference = original_plan_reference
        control.validate_cache = original_validate_cache


def replay_legacy_case(
    case: dict[str, object],
    production_config: dict[str, object],
    *,
    archive_path: Path,
    adapted_cache_path: Path,
    span_reason: str = LEGACY_REASON,
    repo_root: Path = control.REPO,
) -> dict[str, object]:
    archive = load_legacy_archive(archive_path)
    reference_path = control._resolve(repo_root, case["reference_path"])
    truth, _reference = control._truth(reference_path)
    planner_config = control._planner_config(production_config)
    plan = derive_legacy_plan(
        archive,
        truth,
        total_samples=int(
            round(float(case["duration_seconds"]) * planner_config.sample_rate)
        ),
        config=planner_config,
        span_reason=span_reason,
    )
    ingest = write_adapted_cache(archive, plan, adapted_cache_path)
    adapted_case = {**case, "vector_cache_path": str(adapted_cache_path)}
    with _legacy_plan_seam(plan, archive):
        result = control.replay_case(
            adapted_case,
            production_config,
            repo_root=repo_root,
        )
    result["legacy_ingest"] = ingest
    result["legacy_ingest"].update(
        {
            "official_replay_function": "run_l1_control.replay_case",
            "official_runner_sha256": sha256_file(OFFICIAL_RUNNER),
            "plan_source": "archived_rows_unit_boundaries",
            "validation_seam": "legacy_ingest.validate_adapted_cache",
        }
    )
    return result


def _assert_official_inputs() -> dict[str, object]:
    runner_hash = sha256_file(OFFICIAL_RUNNER)
    if runner_hash != EXPECTED_OFFICIAL_RUNNER_SHA256:
        raise RuntimeError(
            "legacy_official_runner_hash_mismatch:"
            f"expected={EXPECTED_OFFICIAL_RUNNER_SHA256}:actual={runner_hash}"
        )
    cache_hash = sha256_file(ARCHIVED_CACHE)
    if cache_hash != EXPECTED_ARCHIVED_CACHE_SHA256:
        raise RuntimeError(
            "legacy_archive_hash_mismatch:"
            f"expected={EXPECTED_ARCHIVED_CACHE_SHA256}:actual={cache_hash}"
        )
    corpus_hash = sha256_file(OFFICIAL_CORPUS)
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    spec = json.loads(OFFICIAL_SPEC.read_text(encoding="utf-8"))
    if contract["corpus_manifest_hash"] != corpus_hash:
        raise RuntimeError("legacy_official_launcher_pin_drift")
    if spec["corpus_manifest_sha256"] != corpus_hash:
        raise RuntimeError("legacy_official_l1_pin_drift")
    gate = spec["accepted_alphabet_gate"]
    if gate != {
        "absolute_tolerance": EXPECTED_TOLERANCE,
        "case_id": CASE_ID,
        "speaker_accuracy": EXPECTED_ANCHOR,
    }:
        raise RuntimeError(f"legacy_accepted_anchor_pin_drift:{gate}")
    return {
        "archived_cache_sha256_before": cache_hash,
        "corpus_manifest_sha256": corpus_hash,
        "official_l1_spec_sha256": sha256_file(OFFICIAL_SPEC),
        "official_runner_sha256": runner_hash,
    }


def _assert_reason_precondition() -> dict[str, object]:
    audit = json.loads(SPAN_REASON_AUDIT.read_text(encoding="utf-8"))
    if audit.get("overall") != "PASS":
        raise RuntimeError("legacy_span_reason_audit_not_passed")
    for item in audit["input_files"]:
        path = REPO / item["path"]
        actual = sha256_file(path)
        if actual != item["sha256"]:
            raise RuntimeError(
                f"legacy_span_reason_audit_input_drift:{item['path']}:{actual}"
            )
    test = json.loads(SPAN_REASON_TEST.read_text(encoding="utf-8"))
    expected_test = (
        "test_legacy_ingest.LegacyIngestTest."
        "test_span_reason_placeholder_does_not_change_score"
    )
    if test.get("overall") != "PASS" or not any(
        expected_test in name for name in test.get("tests", [])
    ):
        raise RuntimeError("legacy_span_reason_equivalence_test_not_passed")
    return {
        "audit_path": repo_path(SPAN_REASON_AUDIT),
        "audit_sha256": sha256_file(SPAN_REASON_AUDIT),
        "equivalence_test_path": repo_path(SPAN_REASON_TEST),
        "equivalence_test_sha256": sha256_file(SPAN_REASON_TEST),
    }


def _score_projection(result: dict[str, object]) -> dict[str, object]:
    return {name: value for name, value in result.items() if name != "legacy_ingest"}


def _write_manifest(output_dir: Path, paths: list[Path]) -> tuple[Path, str]:
    manifest = output_dir / "LEGACY_MEASUREMENT_EVIDENCE.sha256"
    lines = [f"{sha256_file(path)}  {repo_path(path)}" for path in sorted(paths)]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest, sha256_file(manifest)


def run_measurement(output_dir: Path) -> tuple[int, dict[str, object]]:
    if output_dir.exists():
        raise RuntimeError(f"legacy_output_dir_exists:{output_dir}")
    output_dir.mkdir(parents=True)
    pins = _assert_official_inputs()
    reason_precondition = _assert_reason_precondition()
    corpus = json.loads(OFFICIAL_CORPUS.read_text(encoding="utf-8"))
    spec = json.loads(OFFICIAL_SPEC.read_text(encoding="utf-8"))
    case = next(item for item in corpus["cases"] if item["case_id"] == CASE_ID)
    run_records = []
    evidence_paths: list[Path] = []
    for run_index in range(1, RUN_COUNT + 1):
        adapted_cache = output_dir / f"adapted-cache-run{run_index}.npz"
        result = replay_legacy_case(
            case,
            spec["production_config"],
            archive_path=ARCHIVED_CACHE,
            adapted_cache_path=adapted_cache,
            span_reason=LEGACY_REASON,
        )
        projection_hash = control.semantic_sha256(_score_projection(result))
        run_path = output_dir / f"legacy-anchor-run{run_index}.json"
        run_hash = write_json(
            run_path,
            {
                "case_id": CASE_ID,
                "result": result,
                "run_index": run_index,
                "scoring_projection_sha256": projection_hash,
            },
        )
        evidence_paths.extend((adapted_cache, run_path))
        run_records.append(
            {
                "adapted_cache_path": repo_path(adapted_cache),
                "adapted_cache_sha256": sha256_file(adapted_cache),
                "path": repo_path(run_path),
                "result_sha256": run_hash,
                "run_index": run_index,
                "scoring_projection_sha256": projection_hash,
                "speaker_accuracy": result["metrics"]["speaker_accuracy"],
            }
        )
    cache_after = sha256_file(ARCHIVED_CACHE)
    if cache_after != pins["archived_cache_sha256_before"]:
        raise RuntimeError(
            "legacy_archive_modified_during_measurement:"
            f"before={pins['archived_cache_sha256_before']}:after={cache_after}"
        )
    deterministic = len(
        {item["scoring_projection_sha256"] for item in run_records}
    ) == 1
    accuracy = float(run_records[0]["speaker_accuracy"])
    delta = abs(accuracy - EXPECTED_ANCHOR)
    passed = deterministic and delta <= EXPECTED_TOLERANCE
    failures = []
    if not deterministic:
        failures.append("legacy_anchor_nondeterministic")
    if delta > EXPECTED_TOLERANCE:
        failures.append("legacy_anchor_band_failed")
    transcript_lines = [
        f"PRECONDITION PASS span_reasons_independent audit={reason_precondition['audit_sha256']}",
        f"ARCHIVE BEFORE {pins['archived_cache_sha256_before']}",
    ]
    transcript_lines.extend(
        f"RUN {item['run_index']} accuracy={item['speaker_accuracy']:.9f} "
        f"projection={item['scoring_projection_sha256']}"
        for item in run_records
    )
    transcript_lines.extend(
        [
            f"ARCHIVE AFTER {cache_after}",
            f"DETERMINISM {'PASS' if deterministic else 'FAIL'}",
            f"ANCHOR {'PASS' if delta <= EXPECTED_TOLERANCE else 'FAIL'} "
            f"actual={accuracy:.9f} target={EXPECTED_ANCHOR:.9f} "
            f"delta={delta:.9f} tolerance={EXPECTED_TOLERANCE:.9f}",
            f"RESULT {'PASS' if passed else 'BLOCKED'} "
            f"failures={','.join(failures) if failures else 'none'}",
        ]
    )
    transcript_path = output_dir / "measurement-transcript.txt"
    transcript_path.write_text("\n".join(transcript_lines) + "\n", encoding="utf-8")
    summary = {
        **pins,
        "accepted_anchor": {
            "absolute_delta": round(delta, 9),
            "absolute_tolerance": EXPECTED_TOLERANCE,
            "actual_speaker_accuracy": accuracy,
            "passed": delta <= EXPECTED_TOLERANCE,
            "speaker_accuracy": EXPECTED_ANCHOR,
        },
        "archived_cache_read_only": True,
        "archived_cache_sha256_after": cache_after,
        "case_id": CASE_ID,
        "deterministic": deterministic,
        "failures": failures,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "official_files_modified": False,
        "overall": "PASS" if passed else "BLOCKED",
        "reason_precondition": reason_precondition,
        "runs": run_records,
        "schema": "moss-l2-stage0-legacy-anchor-fidelity.v1",
        "span_reason": LEGACY_REASON,
    }
    summary_path = output_dir / "summary.json"
    write_json(summary_path, summary)
    evidence_paths.extend((summary_path, transcript_path))
    manifest, manifest_hash = _write_manifest(output_dir, evidence_paths)
    return (0 if passed else 2), {
        **summary,
        "evidence_manifest_path": repo_path(manifest),
        "evidence_manifest_sha256": manifest_hash,
        "transcript_path": repo_path(transcript_path),
        "transcript_sha256": sha256_file(transcript_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        status, result = run_measurement(args.output_dir)
    except Exception as exc:
        print(f"BLOCKED {exc.__class__.__name__}:{exc}")
        print("<promise>BLOCKED</promise>")
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    if status:
        print("<promise>BLOCKED</promise>")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
