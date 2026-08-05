#!/usr/bin/env python3
"""F1 ledger-only bounded clustering; runtime decisions only, no evaluator imports."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import pdist

from runtime_l1 import decision_units


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]


@dataclass(frozen=True, slots=True)
class F1Config:
    canonical_min_score: float
    canonical_min_margin: float
    max_changed_duration_fraction: float


def semantic_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _normalize(vector: Sequence[float]) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(values))
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)) or norm <= 1e-12:
        raise RuntimeError("f1_vector_invalid")
    return values / norm


def _references(units: Sequence[dict[str, object]]) -> tuple[list[str], np.ndarray]:
    names = sorted({str(unit["current_speaker"]) for unit in units if unit["current_speaker"]})
    kept = []
    refs = []
    for name in names:
        candidates = [
            unit for unit in units
            if unit["current_speaker"] == name and unit["vector"] is not None
        ]
        admitted = [unit for unit in candidates if float(unit["duration_seconds"]) >= 2.0]
        chosen = sorted(admitted or candidates, key=lambda unit: -float(unit["duration_seconds"]))[:10]
        if not chosen:
            continue
        weights = np.asarray([float(unit["duration_seconds"]) for unit in chosen])
        values = np.stack([_normalize(unit["vector"]) for unit in chosen])
        refs.append(_normalize((values * (weights / weights.sum())[:, None]).sum(axis=0)))
        kept.append(name)
    if not refs:
        raise RuntimeError("f1_no_canonical_references")
    return kept, np.stack(refs)


def decide_f1(runtime: dict[str, Any], l1: dict[str, Any], config: F1Config) -> dict[str, Any]:
    units = decision_units(runtime, l1)
    names, refs = _references(units)
    eligible = [index for index, unit in enumerate(units) if unit["vector"] is not None]
    if len(eligible) < 2:
        return {
            "case_id": runtime["case_id"],
            "config": {
                "canonical_min_score": config.canonical_min_score,
                "canonical_min_margin": config.canonical_min_margin,
                "max_changed_duration_fraction": config.max_changed_duration_fraction,
            },
            "corrections": [],
            "final_unit_labels": [unit["current_speaker"] for unit in units],
            "changed_duration_fraction": 0.0,
            "trace": {"status": "insufficient_vectors"},
        }
    values = np.stack([_normalize(units[index]["vector"]) for index in eligible])
    tree = linkage(pdist(values, metric="cosine"), method="average")
    clusters = np.asarray(
        fcluster(tree, max(1, len(names)), criterion="maxclust"), dtype=np.int64
    )
    cluster_ids = sorted(set(int(value) for value in clusters))
    centroids = []
    for cluster in cluster_ids:
        members = [position for position, value in enumerate(clusters) if value == cluster]
        weights = np.asarray([float(units[eligible[position]]["duration_seconds"]) for position in members])
        centroids.append(_normalize((values[members] * (weights / weights.sum())[:, None]).sum(axis=0)))
    similarities = np.stack(centroids) @ refs.T
    left, right = linear_sum_assignment(-similarities)
    mapping: dict[int, str] = {}
    cluster_evidence: dict[str, dict[str, float]] = {}
    for cluster_position, ref_position in zip(left, right, strict=True):
        scores = similarities[int(cluster_position)]
        score = float(scores[int(ref_position)])
        runner = max(
            (float(value) for index, value in enumerate(scores) if index != int(ref_position)),
            default=-1.0,
        )
        margin = score - runner
        cluster = cluster_ids[int(cluster_position)]
        cluster_evidence[str(cluster)] = {"score": score, "margin": margin}
        if score >= config.canonical_min_score and margin >= config.canonical_min_margin:
            mapping[cluster] = names[int(ref_position)]
    ref_index = {name: index for index, name in enumerate(names)}
    proposals = []
    for position, unit_index in enumerate(eligible):
        unit = units[unit_index]
        proposed = mapping.get(int(clusters[position]))
        if proposed is None or proposed == unit["current_speaker"]:
            continue
        vector = values[position]
        proposed_score = float(refs[ref_index[proposed]] @ vector)
        incumbent_score = (
            float(refs[ref_index[str(unit["current_speaker"])]] @ vector)
            if unit["current_speaker"] in ref_index
            else 0.0
        )
        proposals.append(
            {
                "unit_index": unit_index,
                "span_id": unit["span_id"],
                "local_speaker": unit["local_speaker"],
                "previous_speaker": unit["current_speaker"],
                "canonical_speaker": proposed,
                "proposed_score": proposed_score,
                "incumbent_score": incumbent_score,
                "score_delta": proposed_score - incumbent_score,
                "duration_seconds": unit["duration_seconds"],
            }
        )
    total_duration = sum(float(unit["duration_seconds"]) for unit in units)
    budget_seconds = total_duration * config.max_changed_duration_fraction
    accepted = []
    used = 0.0
    labels_by_span: dict[int, dict[str, str | None]] = {}
    for unit in units:
        labels_by_span.setdefault(int(unit["span_id"]), {})[str(unit["local_speaker"])] = unit[
            "current_speaker"
        ]
    for proposal in sorted(proposals, key=lambda item: (-float(item["score_delta"]), int(item["unit_index"]))):
        duration = float(proposal["duration_seconds"])
        if used + duration > budget_seconds + 1e-9:
            continue
        span_labels = dict(labels_by_span[int(proposal["span_id"])])
        span_labels[str(proposal["local_speaker"])] = str(proposal["canonical_speaker"])
        attributed = [label for label in span_labels.values() if label is not None]
        if len(attributed) != len(set(attributed)):
            continue
        labels_by_span[int(proposal["span_id"])] = span_labels
        accepted.append(proposal)
        used += duration
    labels = [unit["current_speaker"] for unit in units]
    for item in accepted:
        labels[int(item["unit_index"])] = item["canonical_speaker"]
    fraction = used / total_duration if total_duration else 0.0
    corrections = [
        {
            "address": {
                "span_id": item["span_id"],
                "local_speaker": item["local_speaker"],
                "canonical_speaker": item["canonical_speaker"],
            },
            "previous_speaker": item["previous_speaker"],
            "proposed_score": round(float(item["proposed_score"]), 6),
            "incumbent_score": round(float(item["incumbent_score"]), 6),
            "score_delta": round(float(item["score_delta"]), 6),
            "duration_seconds": round(float(item["duration_seconds"]), 6),
            "changed_duration_fraction": round(fraction, 6),
        }
        for item in accepted
    ]
    return {
        "case_id": runtime["case_id"],
        "config": {
            "canonical_min_score": config.canonical_min_score,
            "canonical_min_margin": config.canonical_min_margin,
            "max_changed_duration_fraction": config.max_changed_duration_fraction,
        },
        "corrections": corrections,
        "final_unit_labels": labels,
        "changed_duration_fraction": round(fraction, 6),
        "trace": {
            "eligible_units": len(eligible),
            "canonical_count": len(names),
            "cluster_count": len(cluster_ids),
            "cluster_mapping": {str(key): value for key, value in sorted(mapping.items())},
            "cluster_evidence": cluster_evidence,
            "proposal_count": len(proposals),
            "accepted_correction_count": len(accepted),
            "budget_seconds": round(budget_seconds, 6),
            "changed_duration_seconds": round(used, 6),
        },
    }


def audit_f1_chain() -> dict[str, object]:
    candidate = Path(__file__).resolve()
    runtime_l1 = HERE / "runtime_l1.py"
    findings = []
    files = []
    for path in (candidate, runtime_l1):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = [
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        ]
        if path == candidate and any("live_speaker_accuracy" in name for name in imports):
            findings.append("candidate_imports_evaluator")
        subscript_keys = {
            node.slice.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        }
        if path == candidate and ({"reference_path", "reference_sha256", "true_speaker"} & subscript_keys):
            findings.append("candidate_indexes_golden_key")
        files.append(
            {
                "path": path.relative_to(REPO).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "imports": sorted(imports),
                "subscript_keys": sorted(subscript_keys),
            }
        )
    return {
        "files": files,
        "findings": findings,
        "runtime_l1_activity_source": "temporary rows synthesized only from runtime manifest units",
        "a2_terminal_synthetic_metrics_discarded": True,
        "candidate_receives": ["runtime_case", "runtime_l1_decision", "F1Config"],
        "candidate_receives_evaluation_truth": False,
        "passed": not findings,
    }
