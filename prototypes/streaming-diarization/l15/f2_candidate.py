#!/usr/bin/env python3
"""Exploratory soft lane prior over runtime-visible embeddings; no scorer imports."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
KNOWN_LANES = {"local-mic", "remote-system"}


@dataclass(frozen=True, slots=True)
class F2Config:
    prior_strength: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.prior_strength < 1.0:
            raise ValueError("f2_prior_strength_invalid")


def semantic_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalize(vector: Sequence[float]) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(values))
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)) or norm <= 1e-12:
        raise RuntimeError("f2_vector_invalid")
    return values / norm


def _centroid(units: Sequence[dict[str, Any]]) -> np.ndarray:
    values = np.stack([_normalize(unit["vector"]) for unit in units])
    weights = np.asarray([float(unit["duration_seconds"]) for unit in units], dtype=np.float64)
    if np.any(weights <= 0.0):
        raise RuntimeError("f2_duration_invalid")
    return _normalize((values * (weights / weights.sum())[:, None]).sum(axis=0))


def apply_lane_prior(
    scores: dict[str, float],
    *,
    unit_lane: str,
    canonical_lanes: dict[str, str],
    prior_strength: float,
) -> dict[str, float]:
    if not 0.0 <= prior_strength < 1.0:
        raise ValueError("f2_prior_strength_invalid")
    adjusted = {}
    for name, score in scores.items():
        canonical_lane = canonical_lanes.get(name, "unknown")
        cross_known = (
            unit_lane in KNOWN_LANES
            and canonical_lane in KNOWN_LANES
            and unit_lane != canonical_lane
        )
        adjusted[name] = float(score) * (1.0 - prior_strength if cross_known else 1.0)
    return adjusted


def _weighted_quantile(values: Sequence[float], weights: Sequence[float], quantile: float) -> float:
    ordered = sorted(zip(values, weights, strict=True), key=lambda item: item[0])
    target = sum(weights) * quantile
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= target:
            return float(value)
    return float(ordered[-1][0])


def measure_lane_prior(units: Sequence[dict[str, Any]], config: F2Config) -> dict[str, Any]:
    prepared = [
        {
            **unit,
            "capture_lane": str(unit["capture_lane"]),
            "duration_seconds": float(unit["duration_seconds"]),
            "vector": _normalize(unit["vector"]),
        }
        for unit in units
        if unit.get("vector") is not None
    ]
    lanes = sorted({unit["capture_lane"] for unit in prepared})
    if lanes != sorted(KNOWN_LANES):
        raise RuntimeError(f"f2_lane_set_invalid:{lanes}")
    traces = []
    for index, unit in enumerate(prepared):
        own_lane = unit["capture_lane"]
        other_lane = next(lane for lane in KNOWN_LANES if lane != own_lane)
        own_members = [
            candidate
            for position, candidate in enumerate(prepared)
            if position != index and candidate["capture_lane"] == own_lane
        ]
        other_members = [candidate for candidate in prepared if candidate["capture_lane"] == other_lane]
        if not own_members or not other_members:
            continue
        vector = unit["vector"]
        raw_scores = {
            own_lane: float(vector @ _centroid(own_members)),
            other_lane: float(vector @ _centroid(other_members)),
        }
        adjusted = apply_lane_prior(
            raw_scores,
            unit_lane=own_lane,
            canonical_lanes={own_lane: own_lane, other_lane: other_lane},
            prior_strength=config.prior_strength,
        )
        before_prediction = max(sorted(raw_scores), key=lambda lane: raw_scores[lane])
        after_prediction = max(sorted(adjusted), key=lambda lane: adjusted[lane])
        traces.append(
            {
                "unit_id": unit["unit_id"],
                "capture_lane": own_lane,
                "duration_seconds": unit["duration_seconds"],
                "raw_scores": raw_scores,
                "adjusted_scores": adjusted,
                "margin_before": raw_scores[own_lane] - raw_scores[other_lane],
                "margin_after": adjusted[own_lane] - adjusted[other_lane],
                "prediction_before": before_prediction,
                "prediction_after": after_prediction,
                "flipped": before_prediction != after_prediction,
            }
        )
    if not traces:
        raise RuntimeError("f2_no_measurable_units")
    durations = [float(item["duration_seconds"]) for item in traces]
    before = [float(item["margin_before"]) for item in traces]
    after = [float(item["margin_after"]) for item in traces]
    total_duration = sum(durations)

    def weighted_mean(values: Sequence[float]) -> float:
        return sum(value * weight for value, weight in zip(values, durations, strict=True)) / total_duration

    before_correct = sum(
        duration
        for item, duration in zip(traces, durations, strict=True)
        if item["prediction_before"] == item["capture_lane"]
    )
    after_correct = sum(
        duration
        for item, duration in zip(traces, durations, strict=True)
        if item["prediction_after"] == item["capture_lane"]
    )
    flipped = [item for item in traces if item["flipped"]]
    return {
        "config": {"prior_strength": config.prior_strength},
        "unit_count": len(traces),
        "duration_seconds": total_duration,
        "margin": {
            "before_weighted_mean": weighted_mean(before),
            "after_weighted_mean": weighted_mean(after),
            "weighted_mean_delta": weighted_mean(after) - weighted_mean(before),
            "before_weighted_median": _weighted_quantile(before, durations, 0.5),
            "after_weighted_median": _weighted_quantile(after, durations, 0.5),
            "before_weighted_p95": _weighted_quantile(before, durations, 0.95),
            "after_weighted_p95": _weighted_quantile(after, durations, 0.95),
        },
        "own_lane_classification_rate": {
            "before": before_correct / total_duration,
            "after": after_correct / total_duration,
            "delta": (after_correct - before_correct) / total_duration,
        },
        "flips": {
            "count": len(flipped),
            "duration_seconds": sum(float(item["duration_seconds"]) for item in flipped),
            "units": [item["unit_id"] for item in flipped],
        },
        "cross_score_multiplier": 1.0 - config.prior_strength,
        "trace": traces,
        "identity_accuracy_claim": False,
    }


def audit_f2_chain() -> dict[str, object]:
    chain = (
        HERE / "collect_f2_runtime_asr.py",
        HERE / "build_f2_runtime_fixture.py",
        HERE / "f2_candidate.py",
        HERE / "run_f2_exploratory.py",
    )
    findings = []
    files = []
    forbidden_keys = {"reference_path", "reference_sha256", "true_speaker", "golden_label"}
    for path in chain:
        if not path.exists():
            findings.append(f"chain_file_missing:{path.name}")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        keys = {
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        if any("live_speaker_accuracy" in name for name in imports):
            findings.append(f"{path.name}:evaluator_import")
        if forbidden_keys & keys:
            findings.append(f"{path.name}:golden_key:{sorted(forbidden_keys & keys)}")
        files.append(
            {
                "path": path.relative_to(REPO).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "imports": sorted(imports),
                "subscript_keys": sorted(keys),
            }
        )
    return {
        "chain": files,
        "findings": findings,
        "candidate_receives": ["runtime_unit_vectors", "capture_lane", "F2Config"],
        "candidate_receives_evaluation_truth": False,
        "passed": not findings,
    }
