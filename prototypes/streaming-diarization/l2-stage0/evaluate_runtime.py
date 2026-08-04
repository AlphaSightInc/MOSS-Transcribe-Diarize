#!/usr/bin/env python3
"""Consolidate and validate the A4 resource-envelope stop verdict."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
BASE_SHA256 = "f5a06998cddcee91b536750a3c988c1650d2b0601d877fc6c4a92ea1c7c39796"
OPTIMIZED_SHA256 = "8f7714eaf45504dadbc11cb1afec38fff1503ba8c22ad5112cf374fb0058de1a"
OPTIMIZATION = "eager-prewarmed-session-v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_pinned(path: Path, expected_hash: str) -> dict[str, Any]:
    actual_hash = sha256(path)
    if actual_hash != expected_hash:
        raise SystemExit(f"artifact_hash_mismatch:{path}:{actual_hash}")
    return json.loads(path.read_text(encoding="utf-8"))


def compact_measurements(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "audio_seconds": row["duration_seconds"],
            "cache_warmup_seconds": (
                row["cache_warmup"]["wall_seconds"] if row.get("cache_warmup") else None
            ),
            "runs": [
                {
                    "phase": run["phase"],
                    "wall_seconds": run["wall_seconds"],
                    "rtf": run["rtf"],
                    "projected_30m_wall_seconds": run["projected_30m_wall_seconds"],
                    "peak_rss_bytes": run["peak_rss_bytes"],
                    "chunk_count": run["chunk_count"],
                }
                for run in row["runs"]
            ],
        }
        for row in result["measurements"]
    ]


def chunk_summary(result: dict[str, Any]) -> dict[str, Any]:
    chunks = [
        chunk
        for measurement in result["measurements"]
        for run in measurement["runs"]
        for chunk in run["chunks"]
    ]
    return {
        "count": len(chunks),
        "max_frames": max(chunk["frames"] for chunk in chunks),
        "source_pcm_bytes_per_chunk": sorted({chunk["source_pcm_bytes"] for chunk in chunks}),
        "decoded_bytes_per_chunk": sorted({chunk["decoded_array_bytes"] for chunk in chunks}),
        "scratch_wav_bytes_per_chunk": sorted({chunk["scratch_wav_bytes"] for chunk in chunks}),
        "embed_rchar_delta_range": [
            min(chunk["embed_rchar_delta"] for chunk in chunks),
            max(chunk["embed_rchar_delta"] for chunk in chunks),
        ],
        "embed_read_bytes_delta_range": [
            min(chunk["embed_read_bytes_delta"] for chunk in chunks),
            max(chunk["embed_read_bytes_delta"] for chunk in chunks),
        ],
        "whole_tape_materialized": any(
            run["whole_tape_materialized"]
            for measurement in result["measurements"]
            for run in measurement["runs"]
        ),
    }


def artifact(path: Path) -> dict[str, Any]:
    return {"path": str(path.relative_to(HERE.parents[2])), "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, default=HERE / "evidence/a4/base/a4-runtime-base.json")
    parser.add_argument(
        "--optimized", type=Path, default=HERE / "evidence/a4/optimized/a4-runtime-optimized.json"
    )
    parser.add_argument(
        "--host-before", type=Path, default=HERE / "evidence/a4/host-state-before.txt"
    )
    parser.add_argument(
        "--host-after",
        type=Path,
        default=HERE / "evidence/a4/host-state-after-and-cleanup.txt",
    )
    parser.add_argument("--json-output", type=Path, default=HERE / "evidence/a4/a4-verdict.json")
    parser.add_argument("--transcript-output", type=Path, default=HERE / "evidence/a4/a4-verdict.txt")
    args = parser.parse_args()

    base = load_pinned(args.base, BASE_SHA256)
    optimized = load_pinned(args.optimized, OPTIMIZED_SHA256)
    before_text = args.host_before.read_text(encoding="utf-8")
    after_text = args.host_after.read_text(encoding="utf-8")
    required_before = (
        "idle_verdict=PASS_no_live_session_activity_since_current_service_start",
        "repo_head=9089b33210401111865da7abc160ab0bcb4aa266",
        "repo_status_count=0",
    )
    required_after = (
        "live_session_creates_since_start=0",
        "live_frames_since_start=0",
        "live_heartbeats_since_start=0",
        "nonterminal_batch_jobs=0",
        "repo_status_count=0",
        "cleanup=PASS_exact_remote_scratch_removed",
        "repo_status_count_after_cleanup=0",
    )
    if any(value not in before_text for value in required_before):
        raise SystemExit("host_before_contract_failed")
    if any(value not in after_text for value in required_after):
        raise SystemExit("host_after_contract_failed")
    if base["verdict"]["overall"] != "BLOCKED":
        raise SystemExit("base_expected_blocked")
    if optimized["verdict"]["overall"] != "BLOCKED":
        raise SystemExit("optimized_expected_blocked")
    if optimized["optimization"]["name"] != OPTIMIZATION:
        raise SystemExit("optimization_identity_mismatch")
    if not optimized["optimization"]["all_tape_chunks_processed"]:
        raise SystemExit("optimization_skipped_tape_chunks")
    if optimized["optimization"]["audio_or_vector_cached"]:
        raise SystemExit("optimization_cached_forbidden_data")

    base_chunks = chunk_summary(base)
    optimized_chunks = chunk_summary(optimized)
    if base_chunks["count"] != 1_780 or optimized_chunks["count"] != 1_780:
        raise SystemExit("chunk_count_mismatch")
    if base_chunks["whole_tape_materialized"] or optimized_chunks["whole_tape_materialized"]:
        raise SystemExit("whole_tape_materialized")

    optimized_gates = optimized["verdict"]["gates"]
    failed_gates = [gate["gate"] for gate in optimized_gates if not gate["pass"]]
    if failed_gates != [
        "finalizer_rtf_30m_cold_and_warm",
        "analysis_30m_cold_and_warm_seconds",
    ]:
        raise SystemExit("unexpected_final_gate_set")

    max_peak_rss = max(
        run["peak_rss_bytes"]
        for result in (base, optimized)
        for measurement in result["measurements"]
        for run in measurement["runs"]
    )
    result = {
        "schema": "moss-l2-stage0-a4-verdict.v1",
        "verdict": "BLOCKED",
        "campaign_stop": True,
        "next_stage_authorized": False,
        "reason": "sole preregistered optimization still missed fixed 30-minute RTF/time gates",
        "base": {
            "artifact": artifact(args.base),
            "measurements": compact_measurements(base),
            "gates": base["verdict"]["gates"],
            "chunks": base_chunks,
        },
        "sole_optimization": {
            "name": OPTIMIZATION,
            "artifact": artifact(args.optimized),
            "measurements": compact_measurements(optimized),
            "gates": optimized_gates,
            "chunks": optimized_chunks,
        },
        "resource_summary": {
            "max_peak_rss_bytes": max_peak_rss,
            "base_queue": base["contention"]["jobs"],
            "optimized_queue": optimized["contention"]["jobs"],
            "base_stop_ack_p95_overhead_ms": base["stop_acknowledgement"]["p95_overhead_ms"],
            "optimized_stop_ack_p95_overhead_ms": optimized["stop_acknowledgement"][
                "p95_overhead_ms"
            ],
            "base_new_session_latency": base["contention"]["latency"],
            "optimized_new_session_latency": optimized["contention"]["latency"],
        },
        "host_safety": {
            "before": artifact(args.host_before),
            "after_and_cleanup": artifact(args.host_after),
            "deployed_tree_unchanged": True,
            "live_session_activity": False,
            "remote_scratch_removed": True,
            "thermal_state": "unavailable_in_wsl; GPU telemetry recorded as auxiliary state",
        },
        "failed_gates": failed_gates,
        "holdout_opened": False,
        "product_or_deployment_changes": False,
    }
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "A4 VERDICT: BLOCKED; CAMPAIGN A STOP",
        f"base_sha256={BASE_SHA256}",
        f"optimized_sha256={OPTIMIZED_SHA256}",
    ]
    for gate in optimized_gates:
        lines.append(
            f"gate={gate['gate']} actual={gate['actual']} limit={gate['limit']} "
            f"verdict={'PASS' if gate['pass'] else 'FAIL'}"
        )
    lines.extend(
        [
            f"max_peak_rss_bytes={max_peak_rss}",
            "optimization_attempts=1",
            "holdout_opened=false",
            "next_stage_authorized=false",
        ]
    )
    args.transcript_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"verdict=BLOCKED json={args.json_output.relative_to(HERE.parents[2])} "
        f"transcript={args.transcript_output.relative_to(HERE.parents[2])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
