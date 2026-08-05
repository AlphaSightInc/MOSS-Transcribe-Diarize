#!/usr/bin/env python3
"""F3 live-pass adaptive margin via the production causal preparer."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import inspect
import json
from pathlib import Path
import sys
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer as ProductionCausalPreparer,
    LiveIdentityConfig,
)

import runtime_l1
from runtime_fixture import sha256_file


SAMPLE_RATE = 16_000


@dataclass(frozen=True, slots=True)
class F3Schedule:
    config_id: str
    segments: tuple[tuple[float | None, float], ...]

    def __post_init__(self) -> None:
        if not self.config_id or not self.segments or self.segments[-1][0] is not None:
            raise ValueError("f3_schedule_invalid")
        previous = 0.0
        for index, (boundary, margin) in enumerate(self.segments):
            if margin < 0.0:
                raise ValueError("f3_margin_invalid")
            if boundary is not None:
                if boundary <= previous or index == len(self.segments) - 1:
                    raise ValueError("f3_boundary_invalid")
                previous = boundary

    def margin_at(self, meeting_seconds: float) -> float:
        if meeting_seconds < 0.0:
            raise ValueError("f3_meeting_seconds_invalid")
        for boundary, margin in self.segments:
            if boundary is None or meeting_seconds < boundary:
                return margin
        raise AssertionError("f3_schedule_unreachable")


def semantic_hash(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class _RecordingProvider:
    def __init__(self, inner: Any, record: dict[str, Any]):
        self._inner = inner
        self._record = record

    def score(self, **kwargs: Any) -> Any:
        evidence = self._inner.score(**kwargs)
        self._record["evidence"] = [
            {
                "local_speaker": item.local_speaker,
                "canonical_speaker": item.canonical_speaker,
                "score": item.score,
                "evidence_id": item.evidence_id,
            }
            for item in evidence
        ]
        return evidence

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def run_f3(runtime: dict[str, Any], schedule: F3Schedule) -> dict[str, Any]:
    """Replay one runtime case; only the production preparer's per-span config varies."""

    records: list[dict[str, Any]] = []
    production_class = ProductionCausalPreparer

    class ScheduledProductionPreparer:
        def __init__(self, *, config: LiveIdentityConfig, evidence_provider: Any):
            self._base_config = config
            self._evidence_provider = evidence_provider

        def prepare(self, **kwargs: Any) -> Any:
            span = kwargs["span"]
            meeting_seconds = span.end_sample / SAMPLE_RATE
            margin = schedule.margin_at(meeting_seconds)
            record: dict[str, Any] = {
                "span_id": span.id,
                "meeting_seconds": meeting_seconds,
                "scheduled_margin": margin,
                "evidence": [],
            }
            preparer = production_class(
                config=LiveIdentityConfig(
                    max_speakers=self._base_config.max_speakers,
                    min_match_score=self._base_config.min_match_score,
                    min_match_margin=margin,
                ),
                evidence_provider=_RecordingProvider(self._evidence_provider, record),
            )
            result = preparer.prepare(**kwargs)
            record["status"] = result.status
            record["reason"] = result.reason
            record["diagnostics"] = dict(result.proposed_snapshot.diagnostics)
            records.append(record)
            return result

        def __getattr__(self, name: str) -> Any:
            return getattr(self._evidence_provider, name)

    original = runtime_l1.a2_control.BoundedCausalIdentityPreparer
    runtime_l1.a2_control.BoundedCausalIdentityPreparer = ScheduledProductionPreparer
    try:
        result = runtime_l1.run_runtime_l1(runtime)
    finally:
        runtime_l1.a2_control.BoundedCausalIdentityPreparer = original
    if original is not production_class:
        raise RuntimeError("f3_production_preparer_binding_drift")
    result["f3"] = {
        "config_id": schedule.config_id,
        "segments": [
            {"end_seconds_exclusive": boundary, "margin": margin}
            for boundary, margin in schedule.segments
        ],
        "span_records": records,
        "production_preparer_binding": (
            f"{production_class.__module__}.{production_class.__name__}"
        ),
        "production_preparer_source_sha256": sha256_file(
            Path(inspect.getsourcefile(production_class) or "")
        ),
        "sweep_margin_changed": False,
    }
    return result


def change_evidence(
    runtime: dict[str, Any],
    l1: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    l1_labels = l1["final_unit_labels"]
    candidate_labels = candidate["final_unit_labels"]
    if len(l1_labels) != len(candidate_labels) or len(l1_labels) != len(runtime["units"]):
        raise RuntimeError("f3_change_unit_count")
    local_of_unit = {
        int(record["unit_index"]): str(record["local_speaker"])
        for span in candidate["span_trace"]
        for record in span["ledger_records"]
    }
    evidence_of_span = {
        int(record["span_id"]): record for record in candidate["f3"]["span_records"]
    }
    durations = [
        sum((piece["end_sample"] - piece["start_sample"]) / SAMPLE_RATE for piece in unit["pieces"])
        for unit in runtime["units"]
    ]
    total_duration = sum(durations)
    changed_duration = sum(
        duration
        for duration, before, after in zip(durations, l1_labels, candidate_labels, strict=True)
        if before != after
    )
    fraction = changed_duration / total_duration if total_duration else 0.0
    changes = []
    for index, (before, after) in enumerate(zip(l1_labels, candidate_labels, strict=True)):
        if before == after:
            continue
        span_id = int(runtime["units"][index]["span_id"])
        local = local_of_unit.get(index)
        record = evidence_of_span.get(span_id, {})
        scores = {
            item["canonical_speaker"]: float(item["score"])
            for item in record.get("evidence", [])
            if local is not None and item["local_speaker"] == local
        }
        candidate_score = scores.get(after) if after is not None else None
        runner_scores = [score for canonical, score in scores.items() if canonical != after]
        runner_score = max(runner_scores) if runner_scores else None
        score_delta = (
            candidate_score - runner_score
            if candidate_score is not None and runner_score is not None
            else None
        )
        changes.append(
            {
                "address": {
                    "span_id": span_id,
                    "local_speaker": local,
                    "canonical_speaker": after,
                },
                "previous_speaker": before,
                "duration_seconds": durations[index],
                "scheduled_margin": record.get("scheduled_margin"),
                "candidate_score": candidate_score,
                "runner_up_score": runner_score,
                "score_delta": score_delta,
                "evidence_status": "pair_scores_available" if score_delta is not None else "causal_chain_without_pair_scores",
                "changed_duration_fraction": fraction,
            }
        )
    return changes, fraction


def audit_f3_chain() -> dict[str, object]:
    chain = (HERE / "f3_candidate.py", HERE / "f3_decisions.py", HERE / "runtime_l1.py")
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
                "sha256": sha256_file(path),
                "imports": sorted(imports),
                "subscript_keys": sorted(keys),
            }
        )
    candidate_tree = ast.parse((HERE / "f3_candidate.py").read_text())
    direct_assign_calls = [
        node for node in ast.walk(candidate_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "assign_speakers"
    ]
    if direct_assign_calls:
        findings.append("candidate_direct_assign_speakers_call")
    binding = f"{ProductionCausalPreparer.__module__}.{ProductionCausalPreparer.__name__}"
    source = Path(inspect.getsourcefile(ProductionCausalPreparer) or "").resolve()
    expected = (REPO / "moss_transcribe_diarize/app/live_identity.py").resolve()
    if binding != "moss_transcribe_diarize.app.live_identity.BoundedCausalIdentityPreparer":
        findings.append(f"production_preparer_name:{binding}")
    if source != expected:
        findings.append(f"production_preparer_source:{source}")
    return {
        "chain": files,
        "findings": findings,
        "production_preparer_binding": binding,
        "production_preparer_source": source.relative_to(REPO).as_posix(),
        "production_preparer_source_sha256": sha256_file(source),
        "candidate_calls_assign_speakers_directly": bool(direct_assign_calls),
        "candidate_receives_evaluation_truth": False,
        "passed": not findings,
    }
