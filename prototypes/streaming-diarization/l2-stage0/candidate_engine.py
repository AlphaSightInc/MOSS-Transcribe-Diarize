#!/usr/bin/env python3
"""Runtime-only evidence engine for the A5 feasibility prototype."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Protocol, Sequence

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import pdist

from moss_transcribe_diarize.app.live_identity_sweep import (
    REASSIGNED,
    SweepCorrection,
    SweepRevision,
)


class CandidateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RuntimeSpan:
    span_id: int
    start: float
    end: float
    reason: str

    def __post_init__(self) -> None:
        if self.span_id < 0 or self.end <= self.start:
            raise CandidateError("candidate_span_invalid")


@dataclass(frozen=True, slots=True)
class RuntimeUnit:
    span_id: int
    local_speaker: str
    span_start: float
    span_end: float
    intervals: tuple[tuple[float, float], ...]
    current_speaker: str | None
    duration_seconds: float
    vector: tuple[float, ...] | None

    def __post_init__(self) -> None:
        if self.span_id < 0 or not self.local_speaker or self.span_end <= self.span_start:
            raise CandidateError("candidate_unit_invalid")
        previous = self.span_start
        duration = 0.0
        for start, end in self.intervals:
            if start < self.span_start or end > self.span_end:
                raise CandidateError("candidate_interval_outside_committed_span")
            if end <= start or start < previous:
                raise CandidateError("candidate_interval_invalid_or_nonmonotonic")
            duration += end - start
            previous = end
        if not self.intervals or self.duration_seconds <= 0.0:
            raise CandidateError("candidate_unit_has_no_duration")
        if abs(duration - self.duration_seconds) > 1e-6:
            raise CandidateError("candidate_unit_duration_mismatch")
        if self.vector is not None:
            values = np.asarray(self.vector, dtype=np.float64)
            if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)):
                raise CandidateError("candidate_vector_invalid")
            if float(np.linalg.norm(values)) <= 1e-12:
                raise CandidateError("candidate_vector_zero")


@dataclass(frozen=True, slots=True)
class WindowEvidence:
    start: float
    end: float
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        values = np.asarray(self.vector, dtype=np.float64)
        if self.end <= self.start or values.ndim != 1 or not len(values):
            raise CandidateError("candidate_window_invalid")
        if not np.all(np.isfinite(values)) or float(np.linalg.norm(values)) <= 1e-12:
            raise CandidateError("candidate_window_vector_invalid")


@dataclass(frozen=True, slots=True)
class PcmChunk:
    start_sample: int
    samples: np.ndarray

    def __post_init__(self) -> None:
        if self.start_sample < 0 or self.samples.ndim != 1 or not len(self.samples):
            raise CandidateError("candidate_pcm_chunk_invalid")
        if len(self.samples) > 40000:
            raise CandidateError("candidate_pcm_chunk_exceeds_hard_cap")


@dataclass(frozen=True, slots=True)
class CandidateConfig:
    canonical_min_score: float
    canonical_min_margin: float
    incumbent_improvement_margin: float
    max_changed_duration_fraction: float
    minimum_unit_cluster_vote_fraction: float
    minimum_unit_cluster_vote_margin: float
    cluster_distance_threshold: float
    vad_frame_seconds: float = 0.02
    vad_noise_percentile: float = 20.0
    vad_noise_relative_threshold_db: float = 12.0
    vad_threshold_floor_dbfs: float = -45.0
    vad_threshold_ceiling_dbfs: float = -30.0
    vad_bridge_silence_seconds: float = 0.2
    vad_minimum_region_seconds: float = 0.3
    window_seconds: float = 2.5
    window_hop_seconds: float = 1.875
    minimum_window_seconds: float = 0.5
    maximum_embedded_audio_ratio: float = 1.0

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "CandidateConfig":
        vad = payload["energy_vad"]
        windows = payload["tape_windows"]
        grouping = payload["grouping"]
        change = payload["change_evidence"]
        assert isinstance(vad, dict) and isinstance(windows, dict)
        assert isinstance(grouping, dict) and isinstance(change, dict)
        return cls(
            canonical_min_score=float(change["canonical_min_score"]),
            canonical_min_margin=float(change["canonical_min_margin"]),
            incumbent_improvement_margin=float(change["incumbent_improvement_margin"]),
            max_changed_duration_fraction=float(change["max_changed_duration_fraction"]),
            minimum_unit_cluster_vote_fraction=float(change["minimum_unit_cluster_vote_fraction"]),
            minimum_unit_cluster_vote_margin=float(change["minimum_unit_cluster_vote_margin"]),
            cluster_distance_threshold=float(grouping["cluster_distance_threshold"]),
            vad_frame_seconds=float(vad["frame_seconds"]),
            vad_noise_percentile=float(vad["noise_percentile"]),
            vad_noise_relative_threshold_db=float(vad["noise_relative_threshold_db"]),
            vad_threshold_floor_dbfs=float(vad["threshold_floor_dbfs"]),
            vad_threshold_ceiling_dbfs=float(vad["threshold_ceiling_dbfs"]),
            vad_bridge_silence_seconds=float(vad["bridge_silence_seconds"]),
            vad_minimum_region_seconds=float(vad["minimum_region_seconds"]),
            window_seconds=float(windows["window_seconds"]),
            window_hop_seconds=float(windows["hop_seconds"]),
            minimum_window_seconds=float(windows["minimum_window_seconds"]),
            maximum_embedded_audio_ratio=float(windows["maximum_embedded_audio_ratio"]),
        )


@dataclass(frozen=True, slots=True)
class ArmProposal:
    revision: SweepRevision
    correction_evidence: tuple[dict[str, object], ...]
    changed_duration_fraction: float
    trace: dict[str, object]


class WindowEmbedder(Protocol):
    def embed(self, intervals: Sequence[tuple[float, float]]) -> Sequence[float]: ...


def _normalize(vector: Sequence[float]) -> np.ndarray:
    values = np.asarray(vector, dtype=np.float64)
    norm = float(np.linalg.norm(values))
    if values.ndim != 1 or not len(values) or not np.all(np.isfinite(values)) or norm <= 1e-12:
        raise CandidateError("candidate_vector_invalid")
    return values / norm


def _overlap(intervals: Sequence[tuple[float, float]], start: float, end: float) -> float:
    return sum(max(0.0, min(right, end) - max(left, start)) for left, right in intervals)


def _speaker_references(
    units: Sequence[RuntimeUnit],
) -> tuple[tuple[str, ...], np.ndarray]:
    names = tuple(sorted({unit.current_speaker for unit in units if unit.current_speaker}))
    refs: list[np.ndarray] = []
    kept: list[str] = []
    for name in names:
        candidates = [
            unit for unit in units
            if unit.current_speaker == name and unit.vector is not None
        ]
        admitted = [unit for unit in candidates if unit.duration_seconds >= 2.0]
        chosen = sorted(admitted or candidates, key=lambda unit: -unit.duration_seconds)[:10]
        if not chosen:
            continue
        weights = np.asarray([unit.duration_seconds for unit in chosen], dtype=np.float64)
        values = np.stack([_normalize(unit.vector or ()) for unit in chosen])
        refs.append(_normalize((values * (weights / weights.sum())[:, None]).sum(axis=0)))
        kept.append(name)
    if not refs:
        raise CandidateError("candidate_no_canonical_references")
    return tuple(kept), np.stack(refs)


def group_windows(
    windows: Sequence[WindowEvidence], config: CandidateConfig
) -> tuple[int, ...]:
    """Group only acoustic vectors; current labels are intentionally not an input."""

    if not windows:
        return ()
    if len(windows) == 1:
        return (1,)
    values = np.stack([_normalize(window.vector) for window in windows])
    distances = pdist(values, metric="cosine")
    if not np.all(np.isfinite(distances)):
        raise CandidateError("candidate_window_distance_invalid")
    tree = linkage(distances, method="average")
    labels = fcluster(tree, config.cluster_distance_threshold, criterion="distance")
    return tuple(int(label) for label in labels)


def _map_clusters(
    windows: Sequence[WindowEvidence],
    clusters: Sequence[int],
    names: Sequence[str],
    refs: np.ndarray,
    config: CandidateConfig,
) -> tuple[dict[int, str], dict[int, dict[str, float]]]:
    cluster_ids = sorted(set(clusters))
    centroids = []
    for cluster in cluster_ids:
        members = [index for index, value in enumerate(clusters) if value == cluster]
        weights = np.asarray(
            [windows[index].end - windows[index].start for index in members], dtype=np.float64
        )
        values = np.stack([_normalize(windows[index].vector) for index in members])
        centroids.append(_normalize((values * (weights / weights.sum())[:, None]).sum(axis=0)))
    similarity = np.stack(centroids) @ refs.T
    left, right = linear_sum_assignment(-similarity)
    mapping: dict[int, str] = {}
    evidence: dict[int, dict[str, float]] = {}
    for cluster_pos, ref_pos in zip(left, right, strict=True):
        scores = similarity[cluster_pos]
        score = float(scores[ref_pos])
        runner = max(
            (float(value) for index, value in enumerate(scores) if index != ref_pos),
            default=-1.0,
        )
        margin = score - runner
        cluster = cluster_ids[int(cluster_pos)]
        evidence[cluster] = {"score": score, "margin": margin}
        if score >= config.canonical_min_score and margin >= config.canonical_min_margin:
            mapping[cluster] = names[int(ref_pos)]
    return mapping, evidence


def _finalize_proposals(
    units: Sequence[RuntimeUnit],
    proposed: Sequence[dict[str, object]],
    *,
    max_fraction: float,
    reason: str,
    trace: dict[str, object],
) -> ArmProposal:
    total_duration = sum(unit.duration_seconds for unit in units)
    if total_duration <= 0.0:
        raise CandidateError("candidate_total_duration_invalid")
    ranked = sorted(
        proposed,
        key=lambda item: (
            -int(item.get("budget_priority", 0)),
            -float(item["score_delta"]),
            int(item["unit_index"]),
        ),
    )
    budget = total_duration * max_fraction
    selected: list[dict[str, object]] = []
    used = 0.0
    for item in ranked:
        duration = float(item["duration_seconds"])
        if used + duration <= budget + 1e-9:
            selected.append(item)
            used += duration

    by_span: dict[int, list[dict[str, object]]] = {}
    for item in selected:
        by_span.setdefault(int(item["span_id"]), []).append(item)
    accepted: list[dict[str, object]] = []
    collision_spans: list[int] = []
    for span_id, changes in sorted(by_span.items()):
        labels = {
            unit.local_speaker: unit.current_speaker
            for unit in units
            if unit.span_id == span_id
        }
        for item in changes:
            labels[str(item["local_speaker"])] = str(item["canonical_speaker"])
        attributed = [label for label in labels.values() if label is not None]
        if len(attributed) != len(set(attributed)):
            collision_spans.append(span_id)
            continue
        accepted.extend(changes)

    accepted.sort(key=lambda item: (int(item["span_id"]), str(item["local_speaker"])))
    changed = sum(float(item["duration_seconds"]) for item in accepted)
    fraction = changed / total_duration
    corrections = tuple(
        SweepCorrection(
            span_id=int(item["span_id"]),
            local_speaker=str(item["local_speaker"]),
            previous_speaker=(
                None if item["previous_speaker"] is None else str(item["previous_speaker"])
            ),
            canonical_speaker=str(item["canonical_speaker"]),
            reason=reason,
            score=float(item["proposed_score"]),
        )
        for item in accepted
    )
    correction_evidence = tuple(
        {
            "address": {
                "span_id": int(item["span_id"]),
                "local_speaker": str(item["local_speaker"]),
                "canonical_speaker": str(item["canonical_speaker"]),
            },
            "previous_speaker": item["previous_speaker"],
            "proposed_score": round(float(item["proposed_score"]), 6),
            "incumbent_score": round(float(item["incumbent_score"]), 6),
            "score_delta": round(float(item["score_delta"]), 6),
            "duration_seconds": round(float(item["duration_seconds"]), 6),
            "changed_duration_fraction": round(fraction, 6),
        }
        for item in accepted
    )
    return ArmProposal(
        revision=SweepRevision(
            corrections=corrections,
            swept_spans=len({unit.span_id for unit in units}),
            swept_units=len(units),
        ),
        correction_evidence=correction_evidence,
        changed_duration_fraction=round(fraction, 6),
        trace={
            **trace,
            "candidate_proposal_count": len(proposed),
            "budget_selected_count": len(selected),
            "collision_spans_rejected": collision_spans,
            "accepted_correction_count": len(accepted),
            "changed_duration_seconds": round(changed, 6),
            "changed_duration_fraction": round(fraction, 6),
        },
    )


def propose_tape_from_windows(
    units: Sequence[RuntimeUnit],
    windows: Sequence[WindowEvidence],
    config: CandidateConfig,
) -> ArmProposal:
    names, refs = _speaker_references(units)
    clusters = group_windows(windows, config)
    mapping, cluster_evidence = _map_clusters(windows, clusters, names, refs, config)
    ref_pos = {name: index for index, name in enumerate(names)}
    proposals: list[dict[str, object]] = []
    unit_trace: list[dict[str, object]] = []
    for unit_index, unit in enumerate(units):
        votes: dict[str, float] = {}
        window_indexes: list[int] = []
        for index, (window, cluster) in enumerate(zip(windows, clusters, strict=True)):
            canonical = mapping.get(cluster)
            if canonical is None:
                continue
            overlap = _overlap(unit.intervals, window.start, window.end)
            if overlap <= 0.0:
                continue
            votes[canonical] = votes.get(canonical, 0.0) + overlap
            window_indexes.append(index)
        total_vote = sum(votes.values())
        ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        if not ranked or total_vote <= 0.0:
            unit_trace.append({"unit_index": unit_index, "status": "no_mapped_window_vote"})
            continue
        canonical, best_vote = ranked[0]
        runner_vote = ranked[1][1] if len(ranked) > 1 else 0.0
        vote_fraction = best_vote / total_vote
        vote_margin = (best_vote - runner_vote) / total_vote
        if (
            vote_fraction < config.minimum_unit_cluster_vote_fraction
            or vote_margin < config.minimum_unit_cluster_vote_margin
        ):
            unit_trace.append(
                {
                    "unit_index": unit_index,
                    "status": "ambiguous_window_vote",
                    "vote_fraction": round(vote_fraction, 6),
                    "vote_margin": round(vote_margin, 6),
                }
            )
            continue
        selected = [
            index for index in window_indexes
            if mapping.get(clusters[index]) == canonical
        ]
        weights = np.asarray(
            [_overlap(unit.intervals, windows[index].start, windows[index].end) for index in selected],
            dtype=np.float64,
        )
        vectors = np.stack([_normalize(windows[index].vector) for index in selected])
        pooled = _normalize((vectors * (weights / weights.sum())[:, None]).sum(axis=0))
        scores = refs @ pooled
        proposed_score = float(scores[ref_pos[canonical]])
        runner_score = max(
            (float(value) for index, value in enumerate(scores) if index != ref_pos[canonical]),
            default=-1.0,
        )
        if (
            proposed_score < config.canonical_min_score
            or proposed_score - runner_score < config.canonical_min_margin
        ):
            unit_trace.append({"unit_index": unit_index, "status": "canonical_score_refused"})
            continue
        incumbent_score = (
            float(scores[ref_pos[unit.current_speaker]])
            if unit.current_speaker in ref_pos
            else 0.0
        )
        delta = proposed_score - incumbent_score
        if unit.current_speaker == canonical:
            unit_trace.append({"unit_index": unit_index, "status": "label_unchanged"})
            continue
        if unit.current_speaker is not None and delta < config.incumbent_improvement_margin:
            unit_trace.append({"unit_index": unit_index, "status": "below_improvement_margin"})
            continue
        proposals.append(
            {
                "unit_index": unit_index,
                "span_id": unit.span_id,
                "local_speaker": unit.local_speaker,
                "previous_speaker": unit.current_speaker,
                "canonical_speaker": canonical,
                "proposed_score": proposed_score,
                "incumbent_score": incumbent_score,
                "score_delta": delta,
                "duration_seconds": unit.duration_seconds,
            }
        )
        unit_trace.append(
            {
                "unit_index": unit_index,
                "status": "proposed",
                "canonical_speaker": canonical,
                "score_delta": round(delta, 6),
                "vote_fraction": round(vote_fraction, 6),
                "vote_margin": round(vote_margin, 6),
            }
        )
    return _finalize_proposals(
        units,
        proposals,
        max_fraction=config.max_changed_duration_fraction,
        reason=REASSIGNED,
        trace={
            "arm": "tape",
            "window_count": len(windows),
            "cluster_count": len(set(clusters)),
            "cluster_mapping": {str(key): value for key, value in sorted(mapping.items())},
            "cluster_evidence": {str(key): value for key, value in sorted(cluster_evidence.items())},
            "unit_trace": unit_trace,
        },
    )


def propose_continuity_rescue_from_windows(
    units: Sequence[RuntimeUnit],
    windows: Sequence[WindowEvidence],
    config: CandidateConfig,
) -> ArmProposal:
    """Rescue only unattributed L1 units using causal-looking acoustic continuity."""

    names, refs = _speaker_references(units)
    ref_pos = {name: index for index, name in enumerate(names)}
    matched: list[dict[str, object]] = []
    for index, window in enumerate(windows):
        vector = _normalize(window.vector)
        scores = refs @ vector
        order = np.argsort(-scores)
        winner = int(order[0])
        score = float(scores[winner])
        runner = float(scores[int(order[1])]) if len(order) > 1 else -1.0
        margin = score - runner
        matched.append(
            {
                "window_index": index,
                "canonical_speaker": (
                    names[winner]
                    if score >= config.canonical_min_score
                    and margin >= config.canonical_min_margin
                    else None
                ),
                "score": score,
                "margin": margin,
            }
        )

    groups: list[list[int]] = []
    current: list[int] = []
    for index, match in enumerate(matched):
        canonical = match["canonical_speaker"]
        if canonical is None:
            if len(current) >= 2:
                groups.append(current)
            current = []
            continue
        if current:
            previous_index = current[-1]
            previous = matched[previous_index]
            overlaps = windows[index].start < windows[previous_index].end
            if previous["canonical_speaker"] != canonical or not overlaps:
                if len(current) >= 2:
                    groups.append(current)
                current = []
        current.append(index)
    if len(current) >= 2:
        groups.append(current)

    continuity_windows = {
        index: group_id
        for group_id, group in enumerate(groups, start=1)
        for index in group
    }
    proposals: list[dict[str, object]] = []
    unit_trace: list[dict[str, object]] = []
    for unit_index, unit in enumerate(units):
        if unit.current_speaker is not None:
            unit_trace.append({"unit_index": unit_index, "status": "attributed_l1_immutable"})
            continue
        votes: dict[str, float] = {}
        selected_by_speaker: dict[str, list[int]] = {}
        for window_index in sorted(continuity_windows):
            match = matched[window_index]
            canonical = match["canonical_speaker"]
            assert isinstance(canonical, str)
            overlap = _overlap(
                unit.intervals,
                windows[window_index].start,
                windows[window_index].end,
            )
            if overlap <= 0.0:
                continue
            votes[canonical] = votes.get(canonical, 0.0) + overlap
            selected_by_speaker.setdefault(canonical, []).append(window_index)
        total_vote = sum(votes.values())
        ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        if not ranked or total_vote <= 0.0:
            unit_trace.append({"unit_index": unit_index, "status": "no_continuity_vote"})
            continue
        canonical, best_vote = ranked[0]
        runner_vote = ranked[1][1] if len(ranked) > 1 else 0.0
        vote_fraction = best_vote / total_vote
        vote_margin = (best_vote - runner_vote) / total_vote
        if (
            vote_fraction < config.minimum_unit_cluster_vote_fraction
            or vote_margin < config.minimum_unit_cluster_vote_margin
        ):
            unit_trace.append(
                {
                    "unit_index": unit_index,
                    "status": "ambiguous_continuity_vote",
                    "vote_fraction": round(vote_fraction, 6),
                    "vote_margin": round(vote_margin, 6),
                }
            )
            continue
        selected = selected_by_speaker[canonical]
        weights = np.asarray(
            [
                _overlap(unit.intervals, windows[index].start, windows[index].end)
                for index in selected
            ],
            dtype=np.float64,
        )
        vectors = np.stack([_normalize(windows[index].vector) for index in selected])
        pooled = _normalize((vectors * (weights / weights.sum())[:, None]).sum(axis=0))
        scores = refs @ pooled
        proposed_score = float(scores[ref_pos[canonical]])
        runner_score = max(
            (
                float(value)
                for index, value in enumerate(scores)
                if index != ref_pos[canonical]
            ),
            default=-1.0,
        )
        if (
            proposed_score < config.canonical_min_score
            or proposed_score - runner_score < config.canonical_min_margin
        ):
            unit_trace.append({"unit_index": unit_index, "status": "canonical_score_refused"})
            continue
        proposals.append(
            {
                "unit_index": unit_index,
                "span_id": unit.span_id,
                "local_speaker": unit.local_speaker,
                "previous_speaker": None,
                "canonical_speaker": canonical,
                "proposed_score": proposed_score,
                "incumbent_score": 0.0,
                "score_delta": proposed_score,
                "duration_seconds": unit.duration_seconds,
            }
        )
        unit_trace.append(
            {
                "unit_index": unit_index,
                "status": "proposed",
                "canonical_speaker": canonical,
                "score_delta": round(proposed_score, 6),
                "vote_fraction": round(vote_fraction, 6),
                "vote_margin": round(vote_margin, 6),
            }
        )
    return _finalize_proposals(
        units,
        proposals,
        max_fraction=config.max_changed_duration_fraction,
        reason=REASSIGNED,
        trace={
            "arm": "tape_continuity_rescue",
            "window_count": len(windows),
            "window_matches": matched,
            "continuity_groups": [
                {
                    "group_id": group_id,
                    "canonical_speaker": matched[group[0]]["canonical_speaker"],
                    "window_indexes": group,
                }
                for group_id, group in enumerate(groups, start=1)
            ],
            "unit_trace": unit_trace,
        },
    )


def propose_span_local_weak_rescue_from_windows(
    units: Sequence[RuntimeUnit],
    windows: Sequence[WindowEvidence],
    config: CandidateConfig,
) -> ArmProposal:
    """Pool tape windows by committed unit address; rescue weak unlabeled units only."""

    names, refs = _speaker_references(units)
    ref_pos = {name: index for index, name in enumerate(names)}
    matched: list[dict[str, object]] = []
    for index, window in enumerate(windows):
        vector = _normalize(window.vector)
        scores = refs @ vector
        order = np.argsort(-scores)
        winner = int(order[0])
        score = float(scores[winner])
        runner = float(scores[int(order[1])]) if len(order) > 1 else -1.0
        margin = score - runner
        matched.append(
            {
                "window_index": index,
                "canonical_speaker": (
                    names[winner]
                    if score >= config.canonical_min_score
                    and margin >= config.canonical_min_margin
                    else None
                ),
                "score": score,
                "margin": margin,
            }
        )

    proposals: list[dict[str, object]] = []
    unit_trace: list[dict[str, object]] = []
    for unit_index, unit in enumerate(units):
        if unit.current_speaker is not None:
            unit_trace.append({"unit_index": unit_index, "status": "attributed_l1_immutable"})
            continue
        if unit.vector is None:
            unit_trace.append({"unit_index": unit_index, "status": "sub_floor_immutable"})
            continue
        votes: dict[str, float] = {}
        selected_by_speaker: dict[str, list[int]] = {}
        for window_index, match in enumerate(matched):
            canonical = match["canonical_speaker"]
            if not isinstance(canonical, str):
                continue
            overlap = _overlap(
                unit.intervals,
                windows[window_index].start,
                windows[window_index].end,
            )
            if overlap <= 0.0:
                continue
            votes[canonical] = votes.get(canonical, 0.0) + overlap
            selected_by_speaker.setdefault(canonical, []).append(window_index)
        total_vote = sum(votes.values())
        ranked = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        if not ranked or total_vote <= 0.0:
            unit_trace.append({"unit_index": unit_index, "status": "no_span_local_vote"})
            continue
        canonical, best_vote = ranked[0]
        runner_vote = ranked[1][1] if len(ranked) > 1 else 0.0
        vote_fraction = best_vote / total_vote
        vote_margin = (best_vote - runner_vote) / total_vote
        if (
            vote_fraction < config.minimum_unit_cluster_vote_fraction
            or vote_margin < config.minimum_unit_cluster_vote_margin
        ):
            unit_trace.append(
                {
                    "unit_index": unit_index,
                    "status": "ambiguous_span_local_vote",
                    "vote_fraction": round(vote_fraction, 6),
                    "vote_margin": round(vote_margin, 6),
                }
            )
            continue
        selected = selected_by_speaker[canonical]
        weights = np.asarray(
            [
                _overlap(unit.intervals, windows[index].start, windows[index].end)
                for index in selected
            ],
            dtype=np.float64,
        )
        vectors = np.stack([_normalize(windows[index].vector) for index in selected])
        pooled = _normalize((vectors * (weights / weights.sum())[:, None]).sum(axis=0))
        scores = refs @ pooled
        proposed_score = float(scores[ref_pos[canonical]])
        runner_score = max(
            (
                float(value)
                for index, value in enumerate(scores)
                if index != ref_pos[canonical]
            ),
            default=-1.0,
        )
        if (
            proposed_score < config.canonical_min_score
            or proposed_score - runner_score < config.canonical_min_margin
        ):
            unit_trace.append({"unit_index": unit_index, "status": "canonical_score_refused"})
            continue
        proposals.append(
            {
                "unit_index": unit_index,
                "span_id": unit.span_id,
                "local_speaker": unit.local_speaker,
                "previous_speaker": None,
                "canonical_speaker": canonical,
                "proposed_score": proposed_score,
                "incumbent_score": 0.0,
                "score_delta": proposed_score,
                "duration_seconds": unit.duration_seconds,
            }
        )
        unit_trace.append(
            {
                "unit_index": unit_index,
                "status": "proposed",
                "canonical_speaker": canonical,
                "score_delta": round(proposed_score, 6),
                "vote_fraction": round(vote_fraction, 6),
                "vote_margin": round(vote_margin, 6),
            }
        )
    return _finalize_proposals(
        units,
        proposals,
        max_fraction=config.max_changed_duration_fraction,
        reason=REASSIGNED,
        trace={
            "arm": "tape_span_local_weak_rescue",
            "window_count": len(windows),
            "window_matches": matched,
            "unit_trace": unit_trace,
        },
    )


def propose_joint_span_rescue_from_windows(
    units: Sequence[RuntimeUnit],
    windows: Sequence[WindowEvidence],
    config: CandidateConfig,
) -> ArmProposal:
    """Jointly assign weak unlabeled units, then apply causal-observability budget order."""

    names, refs = _speaker_references(units)
    matched: list[dict[str, object]] = []
    for index, window in enumerate(windows):
        vector = _normalize(window.vector)
        scores = refs @ vector
        order = np.argsort(-scores)
        winner = int(order[0])
        score = float(scores[winner])
        runner = float(scores[int(order[1])]) if len(order) > 1 else -1.0
        margin = score - runner
        matched.append(
            {
                "window_index": index,
                "canonical_speaker": (
                    names[winner]
                    if score >= config.canonical_min_score
                    and margin >= config.canonical_min_margin
                    else None
                ),
                "score": score,
                "margin": margin,
            }
        )

    evidence_by_span: dict[int, list[dict[str, object]]] = {}
    unit_trace: list[dict[str, object]] = []
    for unit_index, unit in enumerate(units):
        if unit.current_speaker is not None:
            unit_trace.append({"unit_index": unit_index, "status": "attributed_l1_immutable"})
            continue
        if unit.vector is None:
            unit_trace.append({"unit_index": unit_index, "status": "sub_floor_immutable"})
            continue
        votes: dict[str, float] = {}
        selected_by_speaker: dict[str, list[int]] = {}
        for window_index, match in enumerate(matched):
            canonical = match["canonical_speaker"]
            if not isinstance(canonical, str):
                continue
            overlap = _overlap(
                unit.intervals,
                windows[window_index].start,
                windows[window_index].end,
            )
            if overlap <= 0.0:
                continue
            votes[canonical] = votes.get(canonical, 0.0) + overlap
            selected_by_speaker.setdefault(canonical, []).append(window_index)
        total_vote = sum(votes.values())
        ranked_votes = sorted(votes.items(), key=lambda item: (-item[1], item[0]))
        if not ranked_votes or total_vote <= 0.0:
            unit_trace.append({"unit_index": unit_index, "status": "no_joint_tape_evidence"})
            continue
        window_canonical, best_vote = ranked_votes[0]
        runner_vote = ranked_votes[1][1] if len(ranked_votes) > 1 else 0.0
        vote_fraction = best_vote / total_vote
        vote_margin = (best_vote - runner_vote) / total_vote
        if (
            vote_fraction < config.minimum_unit_cluster_vote_fraction
            or vote_margin < config.minimum_unit_cluster_vote_margin
        ):
            unit_trace.append(
                {
                    "unit_index": unit_index,
                    "status": "ambiguous_joint_tape_evidence",
                    "vote_fraction": round(vote_fraction, 6),
                    "vote_margin": round(vote_margin, 6),
                }
            )
            continue
        selected = selected_by_speaker[window_canonical]
        weights = np.asarray(
            [
                _overlap(unit.intervals, windows[index].start, windows[index].end)
                for index in selected
            ],
            dtype=np.float64,
        )
        values = np.stack([_normalize(windows[index].vector) for index in selected])
        pooled = _normalize((values * (weights / weights.sum())[:, None]).sum(axis=0))
        window_scores = refs @ pooled
        unit_scores = refs @ _normalize(unit.vector)
        unit_order = np.argsort(-unit_scores)
        unit_winner = int(unit_order[0])
        unit_runner = (
            float(unit_scores[int(unit_order[1])]) if len(unit_order) > 1 else -1.0
        )
        unit_passes = (
            float(unit_scores[unit_winner]) >= config.canonical_min_score
            and float(unit_scores[unit_winner]) - unit_runner >= config.canonical_min_margin
        )
        identity_scores = unit_scores if unit_passes else window_scores
        starts_at_span = abs(unit.intervals[0][0] - unit.span_start) <= 1e-9
        ends_at_span = abs(unit.intervals[-1][1] - unit.span_end) <= 1e-9
        priority = 2 if starts_at_span and ends_at_span else 1 if starts_at_span else 0
        evidence_by_span.setdefault(unit.span_id, []).append(
            {
                "unit_index": unit_index,
                "identity_scores": identity_scores,
                "identity_source": "weak_unit_vector_prior" if unit_passes else "tape_window_pool",
                "window_canonical": window_canonical,
                "vote_fraction": vote_fraction,
                "vote_margin": vote_margin,
                "budget_priority": priority,
            }
        )

    proposals: list[dict[str, object]] = []
    for span_id, rows in sorted(evidence_by_span.items()):
        used = {
            unit.current_speaker
            for unit in units
            if unit.span_id == span_id and unit.current_speaker is not None
        }
        available_positions = [index for index, name in enumerate(names) if name not in used]
        if not available_positions:
            for row in rows:
                unit_trace.append(
                    {"unit_index": row["unit_index"], "status": "no_unused_span_canonical"}
                )
            continue
        matrix = np.stack(
            [np.asarray(row["identity_scores"])[available_positions] for row in rows]
        )
        left, right = linear_sum_assignment(-matrix)
        assigned_rows = set(int(value) for value in left)
        for row_position, canonical_position in zip(left, right, strict=True):
            row = rows[int(row_position)]
            unit_index = int(row["unit_index"])
            unit = units[unit_index]
            identity_scores = np.asarray(row["identity_scores"])
            ref_index = available_positions[int(canonical_position)]
            proposed_score = float(identity_scores[ref_index])
            runner_score = max(
                (
                    float(identity_scores[index])
                    for index in available_positions
                    if index != ref_index
                ),
                default=-1.0,
            )
            if (
                proposed_score < config.canonical_min_score
                or proposed_score - runner_score < config.canonical_min_margin
            ):
                unit_trace.append(
                    {"unit_index": unit_index, "status": "joint_assignment_score_refused"}
                )
                continue
            canonical = names[ref_index]
            proposals.append(
                {
                    "unit_index": unit_index,
                    "span_id": unit.span_id,
                    "local_speaker": unit.local_speaker,
                    "previous_speaker": None,
                    "canonical_speaker": canonical,
                    "proposed_score": proposed_score,
                    "incumbent_score": 0.0,
                    "score_delta": proposed_score,
                    "duration_seconds": unit.duration_seconds,
                    "budget_priority": int(row["budget_priority"]),
                }
            )
            unit_trace.append(
                {
                    "unit_index": unit_index,
                    "status": "proposed",
                    "canonical_speaker": canonical,
                    "identity_source": row["identity_source"],
                    "window_canonical": row["window_canonical"],
                    "score_delta": round(proposed_score, 6),
                    "budget_priority": int(row["budget_priority"]),
                    "vote_fraction": round(float(row["vote_fraction"]), 6),
                    "vote_margin": round(float(row["vote_margin"]), 6),
                }
            )
        for row_position, row in enumerate(rows):
            if row_position not in assigned_rows:
                unit_trace.append(
                    {"unit_index": row["unit_index"], "status": "joint_assignment_capacity_refused"}
                )
    return _finalize_proposals(
        units,
        proposals,
        max_fraction=config.max_changed_duration_fraction,
        reason=REASSIGNED,
        trace={
            "arm": "tape_joint_span_rescue",
            "window_count": len(windows),
            "window_matches": matched,
            "budget_priority_order": [
                "full_committed_span",
                "active_at_span_start",
                "mid_span_birth_or_tail",
            ],
            "unit_trace": unit_trace,
        },
    )


def propose_ledger_only(
    units: Sequence[RuntimeUnit], config: CandidateConfig
) -> ArmProposal:
    names, refs = _speaker_references(units)
    eligible = [index for index, unit in enumerate(units) if unit.vector is not None]
    if len(eligible) <= 1:
        return _finalize_proposals(
            units, (), max_fraction=config.max_changed_duration_fraction, reason=REASSIGNED,
            trace={"arm": "ledger_only", "status": "insufficient_vectors"},
        )
    values = np.stack([_normalize(units[index].vector or ()) for index in eligible])
    count = max(1, len(names))
    tree = linkage(pdist(values, metric="cosine"), method="average")
    clusters = tuple(int(value) for value in fcluster(tree, count, criterion="maxclust"))
    synthetic = tuple(
        WindowEvidence(float(index), float(index + 1), tuple(values[position]))
        for position, index in enumerate(eligible)
    )
    mapping, cluster_evidence = _map_clusters(synthetic, clusters, names, refs, config)
    ref_pos = {name: index for index, name in enumerate(names)}
    proposals: list[dict[str, object]] = []
    for position, unit_index in enumerate(eligible):
        unit = units[unit_index]
        canonical = mapping.get(clusters[position])
        if canonical is None or canonical == unit.current_speaker:
            continue
        vector = values[position]
        proposed_score = float(refs[ref_pos[canonical]] @ vector)
        incumbent_score = (
            float(refs[ref_pos[unit.current_speaker]] @ vector)
            if unit.current_speaker in ref_pos
            else 0.0
        )
        proposals.append(
            {
                "unit_index": unit_index,
                "span_id": unit.span_id,
                "local_speaker": unit.local_speaker,
                "previous_speaker": unit.current_speaker,
                "canonical_speaker": canonical,
                "proposed_score": proposed_score,
                "incumbent_score": incumbent_score,
                "score_delta": proposed_score - incumbent_score,
                "duration_seconds": unit.duration_seconds,
            }
        )
    proposed_fraction = (
        sum(float(item["duration_seconds"]) for item in proposals)
        / sum(unit.duration_seconds for unit in units)
    )
    if proposed_fraction > config.max_changed_duration_fraction:
        proposals = []
    return _finalize_proposals(
        units,
        proposals,
        max_fraction=config.max_changed_duration_fraction,
        reason=REASSIGNED,
        trace={
            "arm": "ledger_only",
            "cluster_count": len(set(clusters)),
            "runtime_visible_canonical_count": count,
            "cluster_mapping": {str(key): value for key, value in sorted(mapping.items())},
            "cluster_evidence": {str(key): value for key, value in sorted(cluster_evidence.items())},
            "all_or_nothing_proposed_fraction": round(proposed_fraction, 6),
            "all_or_nothing_budget_pass": proposed_fraction <= config.max_changed_duration_fraction,
        },
    )


def _speech_regions(
    chunks: Iterable[PcmChunk],
    *,
    sample_rate: int,
    duration_seconds: float,
    config: CandidateConfig,
) -> tuple[tuple[float, float], ...]:
    frame_samples = round(config.vad_frame_seconds * sample_rate)
    if frame_samples <= 0 or 40000 % frame_samples:
        raise CandidateError("candidate_vad_frame_not_chunk_aligned")
    energies: list[float] = []
    expected = 0
    max_chunk = 0
    for chunk in chunks:
        if chunk.start_sample != expected:
            raise CandidateError("candidate_pcm_chunks_not_contiguous")
        max_chunk = max(max_chunk, len(chunk.samples))
        values = chunk.samples.astype(np.float64)
        complete = len(values) // frame_samples * frame_samples
        for frame in values[:complete].reshape(-1, frame_samples):
            rms = float(np.sqrt(np.mean(frame * frame)))
            energies.append(-120.0 if rms <= 0.0 else 20.0 * math.log10(rms / 32768.0))
        if complete != len(values) and expected + len(values) < round(duration_seconds * sample_rate):
            raise CandidateError("candidate_vad_partial_nonterminal_frame")
        expected += len(values)
    if expected != round(duration_seconds * sample_rate) or max_chunk > 40000:
        raise CandidateError("candidate_pcm_duration_mismatch")
    if not energies:
        return ()
    noise = float(np.percentile(np.asarray(energies), config.vad_noise_percentile))
    threshold = min(
        config.vad_threshold_ceiling_dbfs,
        max(config.vad_threshold_floor_dbfs, noise + config.vad_noise_relative_threshold_db),
    )
    speech = [value >= threshold for value in energies]
    bridge = round(config.vad_bridge_silence_seconds / config.vad_frame_seconds)
    index = 0
    while index < len(speech):
        if speech[index]:
            index += 1
            continue
        end = index
        while end < len(speech) and not speech[end]:
            end += 1
        if index > 0 and end < len(speech) and end - index <= bridge:
            speech[index:end] = [True] * (end - index)
        index = end
    minimum = round(config.vad_minimum_region_seconds / config.vad_frame_seconds)
    regions: list[tuple[float, float]] = []
    index = 0
    while index < len(speech):
        if not speech[index]:
            index += 1
            continue
        end = index
        while end < len(speech) and speech[end]:
            end += 1
        if end - index >= minimum:
            regions.append(
                (
                    index * config.vad_frame_seconds,
                    min(duration_seconds, end * config.vad_frame_seconds),
                )
            )
        index = end
    return tuple(regions)


def _windows(
    regions: Sequence[tuple[float, float]],
    config: CandidateConfig,
    *,
    duration_seconds: float,
) -> tuple[tuple[float, float], ...]:
    result: list[tuple[float, float]] = []
    seen: set[tuple[int, int]] = set()
    for start, end in regions:
        cursor = start
        while cursor < end:
            right = min(end, cursor + config.window_seconds)
            if right - cursor >= config.minimum_window_seconds:
                key = (round(cursor * 1_000_000), round(right * 1_000_000))
                if key not in seen:
                    result.append((cursor, right))
                    seen.add(key)
            if right >= end:
                tail = max(start, end - config.window_seconds)
                if end - tail >= config.minimum_window_seconds:
                    key = (round(tail * 1_000_000), round(end * 1_000_000))
                    if key not in seen:
                        result.append((tail, end))
                        seen.add(key)
                break
            cursor += config.window_hop_seconds
    ordered = sorted(result)
    budget = duration_seconds * config.maximum_embedded_audio_ratio
    total = sum(end - start for start, end in ordered)
    if total <= budget + 1e-9:
        return tuple(ordered)
    count = max(1, int(budget // config.window_seconds))
    if count >= len(ordered):
        return tuple(ordered)
    positions = np.linspace(0, len(ordered) - 1, num=count, dtype=np.int64)
    selected = tuple(ordered[int(index)] for index in sorted(set(positions.tolist())))
    if sum(end - start for start, end in selected) > budget + 1e-9:
        raise CandidateError("candidate_window_budget_exceeded")
    return selected


def run_tape_candidate(
    units: Sequence[RuntimeUnit],
    chunks: Iterable[PcmChunk],
    *,
    duration_seconds: float,
    sample_rate: int,
    embedder: WindowEmbedder,
    config: CandidateConfig,
) -> ArmProposal:
    regions = _speech_regions(
        chunks, sample_rate=sample_rate, duration_seconds=duration_seconds, config=config
    )
    intervals = _windows(regions, config, duration_seconds=duration_seconds)
    windows = tuple(
        WindowEvidence(start, end, tuple(float(value) for value in embedder.embed(((start, end),))))
        for start, end in intervals
    )
    proposal = propose_tape_from_windows(units, windows, config)
    return ArmProposal(
        revision=proposal.revision,
        correction_evidence=proposal.correction_evidence,
        changed_duration_fraction=proposal.changed_duration_fraction,
        trace={
            **proposal.trace,
            "vad_regions": [[round(start, 6), round(end, 6)] for start, end in regions],
            "vad_region_count": len(regions),
            "window_intervals": [[round(start, 6), round(end, 6)] for start, end in intervals],
        },
    )


def run_continuity_candidate(
    units: Sequence[RuntimeUnit],
    chunks: Iterable[PcmChunk],
    *,
    duration_seconds: float,
    sample_rate: int,
    embedder: WindowEmbedder,
    config: CandidateConfig,
) -> ArmProposal:
    regions = _speech_regions(
        chunks, sample_rate=sample_rate, duration_seconds=duration_seconds, config=config
    )
    intervals = _windows(regions, config, duration_seconds=duration_seconds)
    windows = tuple(
        WindowEvidence(start, end, tuple(float(value) for value in embedder.embed(((start, end),))))
        for start, end in intervals
    )
    proposal = propose_continuity_rescue_from_windows(units, windows, config)
    return ArmProposal(
        revision=proposal.revision,
        correction_evidence=proposal.correction_evidence,
        changed_duration_fraction=proposal.changed_duration_fraction,
        trace={
            **proposal.trace,
            "vad_regions": [[round(start, 6), round(end, 6)] for start, end in regions],
            "vad_region_count": len(regions),
            "window_intervals": [[round(start, 6), round(end, 6)] for start, end in intervals],
        },
    )


def run_span_local_weak_candidate(
    units: Sequence[RuntimeUnit],
    chunks: Iterable[PcmChunk],
    *,
    duration_seconds: float,
    sample_rate: int,
    embedder: WindowEmbedder,
    config: CandidateConfig,
) -> ArmProposal:
    regions = _speech_regions(
        chunks, sample_rate=sample_rate, duration_seconds=duration_seconds, config=config
    )
    intervals = _windows(regions, config, duration_seconds=duration_seconds)
    windows = tuple(
        WindowEvidence(start, end, tuple(float(value) for value in embedder.embed(((start, end),))))
        for start, end in intervals
    )
    proposal = propose_span_local_weak_rescue_from_windows(units, windows, config)
    return ArmProposal(
        revision=proposal.revision,
        correction_evidence=proposal.correction_evidence,
        changed_duration_fraction=proposal.changed_duration_fraction,
        trace={
            **proposal.trace,
            "vad_regions": [[round(start, 6), round(end, 6)] for start, end in regions],
            "vad_region_count": len(regions),
            "window_intervals": [[round(start, 6), round(end, 6)] for start, end in intervals],
        },
    )


def run_joint_span_candidate(
    units: Sequence[RuntimeUnit],
    chunks: Iterable[PcmChunk],
    *,
    duration_seconds: float,
    sample_rate: int,
    embedder: WindowEmbedder,
    config: CandidateConfig,
) -> ArmProposal:
    regions = _speech_regions(
        chunks, sample_rate=sample_rate, duration_seconds=duration_seconds, config=config
    )
    intervals = _windows(regions, config, duration_seconds=duration_seconds)
    windows = tuple(
        WindowEvidence(start, end, tuple(float(value) for value in embedder.embed(((start, end),))))
        for start, end in intervals
    )
    proposal = propose_joint_span_rescue_from_windows(units, windows, config)
    return ArmProposal(
        revision=proposal.revision,
        correction_evidence=proposal.correction_evidence,
        changed_duration_fraction=proposal.changed_duration_fraction,
        trace={
            **proposal.trace,
            "vad_regions": [[round(start, 6), round(end, 6)] for start, end in regions],
            "vad_region_count": len(regions),
            "window_intervals": [[round(start, 6), round(end, 6)] for start, end in intervals],
        },
    )
