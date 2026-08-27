#!/usr/bin/env python3
"""Audit G1-G7 and produce the decision-ready G4 baseline summary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

SURFACES = ("pre_stop_immediate", "pre_stop_settled", "post_stop_final")
QUALITY_FIELDS = (
    "wer",
    "content_recall",
    "tbsa",
    "der",
    "matched_word_speaker_accuracy",
    "reference_speech_der",
)
EXPECTED_WINDOWS = {
    "mono_javier_intro_50s": 5,
    "interview_bill_ackman_60s": 6,
    "interview_keyu_jin_60s": 6,
    "interview_adam_frank_180s": 18,
    "discussion_jamie_dimon_180s": 18,
    "discussion_rtfl_90s": 8,
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        raise ValueError("mean requires at least one value")
    return sum(items) / len(items)


def distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return {"count": 0, "mean": None, "p50_nearest_rank": None,
                "p95_nearest_rank": None, "max": None}

    def nearest_rank(q: float) -> float:
        return ordered[max(0, math.ceil(q * len(ordered)) - 1)]

    return {
        "count": len(ordered),
        "mean": round(mean(ordered), 6),
        "p50_nearest_rank": round(nearest_rank(0.50), 6),
        "p95_nearest_rank": round(nearest_rank(0.95), 6),
        "max": round(ordered[-1], 6),
    }


def means(rows: list[dict[str, float]], fields: tuple[str, ...]) -> dict[str, float]:
    return {field: round(mean(float(row[field]) for row in rows), 6) for field in fields}


def weighted_means(
    rows: list[tuple[float, dict[str, float]]], fields: tuple[str, ...]
) -> dict[str, float]:
    denominator = sum(weight for weight, _ in rows)
    return {
        field: round(sum(weight * float(row[field]) for weight, row in rows) / denominator, 6)
        for field in fields
    }


def queue_depth_zero(capture: dict[str, Any]) -> bool:
    lines = capture["vllm_queue_metrics"]
    return len(lines) == 2 and all(float(line.rsplit(" ", 1)[1]) == 0.0 for line in lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--evidence-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f"refusing to overwrite {args.output}")

    results_path = args.results.resolve()
    campaign_root = results_path.parent
    results = load(results_path)
    manifest = load(args.manifest.resolve())
    evidence_root = args.evidence_root.resolve()
    actual = results["actual"]
    manifest_by_case = {row["case_id"]: row for row in manifest["cases"]}
    category_of = {case_id: row["category"] for case_id, row in manifest_by_case.items()}

    raw_surface_checks: list[dict[str, Any]] = []
    per_observation_checks: list[dict[str, Any]] = []
    for row in actual:
        case_id = row["case_id"]
        actual_dir = campaign_root / f"pass-{row['pass']}" / case_id / "actual"
        required_raw = (
            actual_dir / "events.jsonl",
            actual_dir / "snapshots.jsonl",
            actual_dir / "live-replay/run-001/trace.jsonl",
        )
        surface_hashes = {}
        for surface in (*SURFACES, "stop_return"):
            path = actual_dir / f"{surface}.jsonl"
            surface_hashes[surface] = {
                "path": str(path.relative_to(campaign_root.parent)),
                "exists_nonempty": path.is_file() and path.stat().st_size > 0,
                "expected_sha256": row["surface_sha256"][surface],
                "observed_sha256": sha256(path) if path.is_file() else None,
            }
        raw_surface_checks.append(
            {
                "pass": row["pass"],
                "case_id": case_id,
                "support_files_present": all(path.is_file() and path.stat().st_size > 0 for path in required_raw),
                "surfaces": surface_hashes,
            }
        )

        queue = row["events"]["rolling_queue"]
        windows = queue["windows"]
        expected = EXPECTED_WINDOWS[case_id]
        manifest_case = manifest_by_case[case_id]
        per_observation_checks.append(
            {
                "pass": row["pass"],
                "case_id": case_id,
                "duration_seconds": row["duration_seconds"],
                "sample_accounting_exact": row["sample_accounting"]["exact"]
                and row["sample_accounting"]["accepted_samples"] == manifest_case["audio"]["samples"]
                and row["sample_accounting"]["accounted_samples"] == manifest_case["audio"]["samples"],
                "corpus_hashes_exact": row["audio"]["wav_sha256"] == manifest_case["audio"]["wav_sha256"]
                and row["audio"]["pcm_sha256"] == manifest_case["audio"]["pcm_sha256"]
                and row["reference_sha256"] == manifest_case["reference_sha256"],
                "window_count": len(windows),
                "expected_window_count": expected,
                "window_grid_exact": [item["window_index"] for item in windows] == list(range(expected)),
                "all_windows_applied": all(item["outcome"] == "applied" for item in windows),
                "all_windows_rolling": all(item["rolling_status"] == "rolling" for item in windows),
                "normalization": {
                    "merged_segments": sum(item["normalization_merged_segments"] for item in windows),
                    "dropped_segments": sum(item["normalization_dropped_segments"] for item in windows),
                    "displaced_samples": sum(item["normalization_displaced_samples"] for item in windows),
                },
                "text_revision_refusals": queue["text_revision_refusals"],
                "proposal_refusals": queue["proposal_refusals"],
                "pcm_evicted": queue["status_counts"].get("pcm_evicted", 0),
                "failed_windows": queue["failed_windows"],
                "stale_completions": queue["stale_completions"],
                "admission_refusals": queue["admission_refusals"],
                "terminal_failures": row["events"]["terminal_failures"],
                "max_queue_depth": queue["max_depth"],
                "final_queue_depth": queue["final_depth"],
                "pre_stop_combined_rtf": row["events"]["rtf"]["pre_stop_combined"],
            }
        )

    per_case_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in actual:
        per_case_rows[row["case_id"]].append(row)

    per_case: dict[str, Any] = {}
    for case_id in EXPECTED_WINDOWS:
        rows = per_case_rows[case_id]
        quality = {
            surface: means([row["surface_scores"][surface] for row in rows], QUALITY_FIELDS)
            for surface in SURFACES
        }
        first_values = [
            item["age_seconds"] for row in rows for item in row["events"]["first_publication_rows"]
        ]
        correction_values = [
            item["age_seconds"] for row in rows for item in row["events"]["correction_rows"]
        ]
        drain_values = [row["surface_clocks"]["pre_stop_settled"]["wait"]["seconds"] for row in rows]
        stop_values = [row["events"]["stop_to_final_seconds"] for row in rows]
        per_case[case_id] = {
            "category": category_of[case_id],
            "duration_seconds": rows[0]["duration_seconds"],
            "observations": len(rows),
            "quality": quality,
            "latency": {
                "first_publication_age_seconds": distribution(first_values),
                "changed_region_correction_age_seconds": distribution(correction_values),
                "drain_wait_seconds": distribution(drain_values),
                "stop_to_final_seconds": distribution(stop_values),
            },
        }

    quality_aggregate: dict[str, Any] = {}
    for surface in SURFACES:
        case_scores = [(case_id, row["quality"][surface]) for case_id, row in per_case.items()]
        categories: dict[str, list[dict[str, float]]] = defaultdict(list)
        for case_id, scores in case_scores:
            categories[category_of[case_id]].append(scores)
        quality_aggregate[surface] = {
            "macro_mean": means([scores for _, scores in case_scores], QUALITY_FIELDS),
            "category_mean": {
                category: means(rows, QUALITY_FIELDS) for category, rows in sorted(categories.items())
            },
            "duration_weighted_mean": weighted_means(
                [(per_case[case_id]["duration_seconds"], scores) for case_id, scores in case_scores],
                QUALITY_FIELDS,
            ),
        }

    latency_fields = (
        "first_publication_age_seconds",
        "changed_region_correction_age_seconds",
        "drain_wait_seconds",
        "stop_to_final_seconds",
    )
    latency_case_scalars = {
        case_id: {
            "first_publication_age_seconds": row["latency"]["first_publication_age_seconds"]["p95_nearest_rank"],
            "changed_region_correction_age_seconds": row["latency"]["changed_region_correction_age_seconds"]["p95_nearest_rank"],
            "drain_wait_seconds": row["latency"]["drain_wait_seconds"]["mean"],
            "stop_to_final_seconds": row["latency"]["stop_to_final_seconds"]["mean"],
        }
        for case_id, row in per_case.items()
    }
    latency_categories: dict[str, list[tuple[str, dict[str, float]]]] = defaultdict(list)
    for case_id, row in latency_case_scalars.items():
        latency_categories[category_of[case_id]].append((case_id, row))
    latency_aggregate = {
        "interpretation": (
            "First-publication and correction aggregates use pooled nearest-rank distributions; "
            "macro/category/duration-weighted values aggregate each case's pooled p95. Drain and "
            "Stop values aggregate each case's two-pass mean."
        ),
        "pooled": {
            "first_publication_age_seconds": distribution(
                item["age_seconds"] for row in actual for item in row["events"]["first_publication_rows"]
            ),
            "changed_region_correction_age_seconds": distribution(
                item["age_seconds"] for row in actual for item in row["events"]["correction_rows"]
            ),
            "drain_wait_seconds": distribution(
                row["surface_clocks"]["pre_stop_settled"]["wait"]["seconds"] for row in actual
            ),
            "stop_to_final_seconds": distribution(row["events"]["stop_to_final_seconds"] for row in actual),
        },
        "macro_mean": means(list(latency_case_scalars.values()), latency_fields),
        "category": {
            category: {
                "case_aggregate_mean": means([row for _, row in items], latency_fields),
                "first_publication_age_seconds_pooled": distribution(
                    event["age_seconds"]
                    for case_id, _ in items
                    for row in per_case_rows[case_id]
                    for event in row["events"]["first_publication_rows"]
                ),
                "changed_region_correction_age_seconds_pooled": distribution(
                    event["age_seconds"]
                    for case_id, _ in items
                    for row in per_case_rows[case_id]
                    for event in row["events"]["correction_rows"]
                ),
            }
            for category, items in sorted(latency_categories.items())
        },
        "duration_weighted_mean": weighted_means(
            [
                (per_case[case_id]["duration_seconds"], row)
                for case_id, row in latency_case_scalars.items()
            ],
            latency_fields,
        ),
        "by_pass": {},
    }
    for pass_name in ("A", "B"):
        rows = [row for row in actual if row["pass"] == pass_name]
        latency_aggregate["by_pass"][pass_name] = {
            "first_publication_age_seconds": distribution(
                item["age_seconds"] for row in rows for item in row["events"]["first_publication_rows"]
            ),
            "changed_region_correction_age_seconds": distribution(
                item["age_seconds"] for row in rows for item in row["events"]["correction_rows"]
            ),
        }
    latency_aggregate["control_pass_p95_spread"] = {
        field: round(
            abs(
                latency_aggregate["by_pass"]["A"][field]["p95_nearest_rank"]
                - latency_aggregate["by_pass"]["B"][field]["p95_nearest_rank"]
            ),
            6,
        )
        for field in ("first_publication_age_seconds", "changed_region_correction_age_seconds")
    }

    total_audio = sum(float(row["duration_seconds"]) for row in actual)
    total_pre_stop_decode = sum(
        float(row["events"]["decode_seconds"]["base"])
        + float(row["events"]["decode_seconds"]["rolling"])
        for row in actual
    )
    restart_pre = load(evidence_root / "restart-pre.json")
    restart_post = load(evidence_root / "restart-post.json")
    campaign_post = load(evidence_root / "campaign-post.json")
    cached_probe = load(evidence_root / "jamie-production-class-probe.json")
    raw_ok = all(
        item["support_files_present"]
        and all(
            surface["exists_nonempty"]
            and surface["expected_sha256"] == surface["observed_sha256"]
            for surface in item["surfaces"].values()
        )
        for item in raw_surface_checks
    )
    observation_integrity_ok = all(
        item["sample_accounting_exact"]
        and item["corpus_hashes_exact"]
        and item["window_grid_exact"]
        and item["all_windows_applied"]
        and item["all_windows_rolling"]
        and not item["text_revision_refusals"]
        and item["proposal_refusals"] == 0
        and item["pcm_evicted"] == 0
        and item["failed_windows"] == 0
        and item["stale_completions"] == 0
        and item["admission_refusals"] == 0
        and not item["terminal_failures"]
        for item in per_observation_checks
    )
    jamie_checks = [item for item in per_observation_checks if item["case_id"] == "discussion_jamie_dimon_180s"]
    provenance_ok = (
        results["checks"]["runtime_descriptor_unchanged"]
        and restart_pre["runtime"]["live"]["descriptor"] == restart_post["runtime"]["live"]["descriptor"]
        == campaign_post["runtime"]["live"]["descriptor"]
        and restart_post["git"]["production_patch_sha256"] == campaign_post["git"]["production_patch_sha256"]
        and restart_post["git"]["production_file_sha256"] == campaign_post["git"]["production_file_sha256"]
        and restart_post["remote_model"]["data"][0]["id"] == campaign_post["remote_model"]["data"][0]["id"]
    )
    gates = {
        "G1_exact_execution": len(actual) == 12
        and math.isclose(total_audio, 1239.987, abs_tol=1e-9)
        and all(item["sample_accounting_exact"] for item in per_observation_checks)
        and raw_ok,
        "G2_full_rolling_coverage": sum(item["window_count"] for item in per_observation_checks) == 122
        and all(item["window_grid_exact"] and item["all_windows_applied"] for item in per_observation_checks),
        "G3_root_cause_closure": observation_integrity_ok,
        "G4_jamie_witness": cached_probe.get("verdict") == "PASS"
        and len(jamie_checks) == 2
        and all(item["window_count"] == 18 and item["normalization"]["displaced_samples"] == 2720 for item in jamie_checks),
        "G5_runtime": total_pre_stop_decode / total_audio < 1
        and max(item["max_queue_depth"] for item in per_observation_checks) <= 1
        and queue_depth_zero(campaign_post),
        "G6_surface_reported": all(
            row["latency"]["first_publication_age_seconds"]["count"] > 0
            and row["latency"]["changed_region_correction_age_seconds"]["count"] > 0
            for row in per_case.values()
        ),
        "G7_provenance": provenance_ok and all(item["corpus_hashes_exact"] for item in per_observation_checks),
    }

    report = {
        "schema": "moss-g4-gates.v1",
        "source": str(results_path),
        "denominator": {
            "cases": len(per_case),
            "passes": 2,
            "actual_live_sessions": len(actual),
            "observed_audio_seconds": round(total_audio, 6),
            "rolling_windows": sum(item["window_count"] for item in per_observation_checks),
            "first_publication_regions": latency_aggregate["pooled"]["first_publication_age_seconds"]["count"],
            "changed_regions": latency_aggregate["pooled"]["changed_region_correction_age_seconds"]["count"],
        },
        "gates": gates,
        "all_gates_pass": all(gates.values()),
        "runtime": {
            "combined_pre_stop_rtf": round(total_pre_stop_decode / total_audio, 6),
            "max_session_pre_stop_rtf": max(item["pre_stop_combined_rtf"] for item in per_observation_checks),
            "max_refinement_queue_depth": max(item["max_queue_depth"] for item in per_observation_checks),
            "endpoint_queue_drained": queue_depth_zero(campaign_post),
            "legacy_strict_replay_failures": [
                {"pass": row["pass"], "case_id": row["case_id"], **row["replay_gate_failure"]}
                for row in actual if row["replay_gate_failure"] is not None
            ],
        },
        "integrity": {
            "per_observation": per_observation_checks,
            "raw_surface_checks": raw_surface_checks,
        },
        "quality": {
            "per_case_two_pass_mean": per_case,
            "aggregate": quality_aggregate,
        },
        "latency": latency_aggregate,
        "provenance": {
            "branch": restart_post["git"]["branch"],
            "head": restart_post["git"]["head"],
            "production_patch_sha256": restart_post["git"]["production_patch_sha256"],
            "production_file_sha256": restart_post["git"]["production_file_sha256"],
            "service_pid": campaign_post["service"]["pid"],
            "model": campaign_post["remote_model"]["data"][0]["id"],
            "descriptor": campaign_post["runtime"]["live"]["descriptor"],
            "corpus_manifest_sha256": sha256(args.manifest.resolve()),
            "stable": provenance_ok,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"gates": gates, "all_gates_pass": all(gates.values())}, sort_keys=True))
    return 0 if all(gates.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
