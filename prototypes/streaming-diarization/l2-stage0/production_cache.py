#!/usr/bin/env python3
"""Shared A1.2/A2 derived-cache path bound to production planner and embedder seams."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_endpoint import (  # noqa: E402
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)


@dataclass(frozen=True, slots=True)
class PlannerConfig:
    sample_rate: int
    min_speech_samples: int
    min_silence_samples: int
    pre_speech_padding_samples: int
    post_speech_padding_samples: int
    hard_cap_samples: int
    min_evidence_samples: int

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "PlannerConfig":
        return cls(**{name: int(payload[name]) for name in cls.__dataclass_fields__})

    def endpoint_config(self) -> EndpointPolicyConfig:
        return EndpointPolicyConfig(
            min_speech_samples=self.min_speech_samples,
            min_silence_samples=self.min_silence_samples,
            pre_speech_padding_samples=self.pre_speech_padding_samples,
            post_speech_padding_samples=self.post_speech_padding_samples,
            hard_cap_samples=self.hard_cap_samples,
        )


@dataclass(frozen=True, slots=True)
class PlannedSpan:
    span_id: int
    start_sample: int
    end_sample: int
    reason: str


@dataclass(frozen=True, slots=True)
class Piece:
    span: int
    start_sample: int
    end_sample: int
    true_speaker: int
    sample_rate: int

    @property
    def start(self) -> float:
        return self.start_sample / self.sample_rate

    @property
    def end(self) -> float:
        return self.end_sample / self.sample_rate

    @property
    def duration(self) -> float:
        return self.sample_count / self.sample_rate

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class EvidenceUnit:
    span_id: int
    true_speaker: int
    pieces: tuple[Piece, ...]


@dataclass(frozen=True, slots=True)
class CachePlan:
    spans: tuple[PlannedSpan, ...]
    units: tuple[EvidenceUnit, ...]
    speaker_labels: tuple[str, ...]
    total_samples: int

    def span(self, span_id: int) -> PlannedSpan:
        return self.spans[span_id]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def production_planner_bindings() -> dict[str, str]:
    policy_name = f"{EndpointPolicy.__module__}.{EndpointPolicy.__name__}"
    expected_name = "moss_transcribe_diarize.app.live_endpoint.EndpointPolicy"
    if policy_name != expected_name:
        raise RuntimeError(f"cache_production_planner_import_mismatch:{policy_name}")
    source = Path(inspect.getsourcefile(EndpointPolicy) or "").resolve()
    expected_source = (REPO / "moss_transcribe_diarize/app/live_endpoint.py").resolve()
    if source != expected_source:
        raise RuntimeError(f"cache_production_planner_source_mismatch:{source}")
    return {
        "policy": policy_name,
        "source_path": source.relative_to(REPO).as_posix(),
        "source_sha256": sha256_file(source),
    }


def _sample(value: float, sample_rate: int) -> int:
    return int(round(float(value) * sample_rate))


def _speech_union(
    intervals: Iterable[tuple[int, int]], total_samples: int
) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for start, end in sorted(intervals):
        start = max(0, min(total_samples, start))
        end = max(0, min(total_samples, end))
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]


def _observations(
    speech: Sequence[tuple[int, int]], total_samples: int
) -> Iterable[SpeechObservation]:
    cursor = 0
    for start, end in speech:
        if start > cursor:
            yield SpeechObservation(cursor, start, False)
        yield SpeechObservation(start, end, True)
        cursor = end
    if cursor < total_samples:
        yield SpeechObservation(cursor, total_samples, False)


def plan_reference(
    rows: Sequence[tuple[float, float, str, str]],
    *,
    total_samples: int,
    config: PlannerConfig,
) -> CachePlan:
    if total_samples <= 0:
        raise ValueError("cache_audio_sample_count_invalid")
    speaker_index: dict[str, int] = {}
    truth: list[tuple[int, int, int]] = []
    for start, end, speaker, _text in rows:
        start_sample = _sample(start, config.sample_rate)
        end_sample = _sample(end, config.sample_rate)
        if end_sample <= start_sample or start_sample < 0 or end_sample > total_samples:
            raise ValueError(
                f"cache_reference_interval_invalid:{start_sample}:{end_sample}:{total_samples}"
            )
        truth.append(
            (
                start_sample,
                end_sample,
                speaker_index.setdefault(speaker, len(speaker_index)),
            )
        )

    policy = EndpointPolicy(config.endpoint_config())
    emitted = []
    speech = _speech_union(((start, end) for start, end, _speaker in truth), total_samples)
    for observation in _observations(speech, total_samples):
        emitted.extend(policy.observe(observation))
    emitted.extend(policy.flush())
    spans = tuple(
        PlannedSpan(index, span.start_sample, span.end_sample, span.reason)
        for index, span in enumerate(emitted)
    )
    if sum(span.end_sample - span.start_sample for span in spans) != total_samples:
        raise RuntimeError("cache_production_plan_not_gap_free")
    if any(left.end_sample != right.start_sample for left, right in zip(spans, spans[1:])):
        raise RuntimeError("cache_production_plan_not_contiguous")

    grouped: dict[tuple[int, int], list[Piece]] = {}
    for span in spans:
        for start, end, speaker in truth:
            clipped_start = max(span.start_sample, start)
            clipped_end = min(span.end_sample, end)
            if clipped_end <= clipped_start:
                continue
            piece = Piece(
                span=span.span_id,
                start_sample=clipped_start,
                end_sample=clipped_end,
                true_speaker=speaker,
                sample_rate=config.sample_rate,
            )
            grouped.setdefault((span.span_id, speaker), []).append(piece)
    units = tuple(
        EvidenceUnit(span_id=key[0], true_speaker=key[1], pieces=tuple(grouped[key]))
        for key in sorted(grouped)
    )
    labels = tuple(label for label, _index in sorted(speaker_index.items(), key=lambda item: item[1]))
    return CachePlan(spans=spans, units=units, speaker_labels=labels, total_samples=total_samples)


def expected_rows(plan: CachePlan, config: PlannerConfig) -> tuple[np.ndarray, np.ndarray]:
    rows: list[tuple[float, ...]] = []
    indexes: list[int] = []
    vector_count = 0
    for unit in plan.units:
        eligible = [piece for piece in unit.pieces if piece.sample_count >= config.min_evidence_samples]
        selected = eligible or list(unit.pieces)
        duration_samples = sum(piece.sample_count for piece in selected)
        rows.append(
            (
                float(unit.span_id),
                float(unit.true_speaker),
                min(piece.start_sample for piece in unit.pieces) / config.sample_rate,
                max(piece.end_sample for piece in unit.pieces) / config.sample_rate,
                duration_samples / config.sample_rate,
                float(bool(eligible)),
            )
        )
        if eligible:
            indexes.append(vector_count)
            vector_count += 1
        else:
            indexes.append(-1)
    return np.asarray(rows, dtype=np.float64), np.asarray(indexes, dtype=np.int64)


def build_cache(
    plan: CachePlan,
    *,
    audio_path: Path,
    output_path: Path,
    embedder: Any,
    config: PlannerConfig,
    expected_embedding_dimension: int | None = None,
) -> dict[str, int]:
    if output_path.exists():
        raise RuntimeError(f"cache_version_exists:{output_path}")
    rows, vector_indexes = expected_rows(plan, config)
    vectors: list[np.ndarray] = []
    for unit, vector_index in zip(plan.units, vector_indexes, strict=True):
        if vector_index < 0:
            continue
        eligible = [
            piece for piece in unit.pieces
            if piece.sample_count >= config.min_evidence_samples
        ]
        intervals = [(piece.start, piece.end) for piece in eligible]
        vectors.append(np.asarray(embedder.embed(audio_path, intervals), dtype=np.float32))
    if vectors:
        dimensions = {vector.shape for vector in vectors}
        if len(dimensions) != 1 or next(iter(dimensions)) != (len(vectors[0]),):
            raise RuntimeError("cache_embedding_shape_mismatch")
        if expected_embedding_dimension is not None and len(vectors[0]) != expected_embedding_dimension:
            raise RuntimeError(
                f"cache_embedding_dimension_mismatch:{len(vectors[0])}:"
                f"{expected_embedding_dimension}"
            )
        stacked = np.stack(vectors)
    else:
        stacked = np.zeros((0, expected_embedding_dimension or 256), dtype=np.float32)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        output_path,
        rows=rows,
        vec_idx=vector_indexes,
        vecs=stacked,
        span_bounds=np.asarray(
            [(span.span_id, span.start_sample, span.end_sample) for span in plan.spans],
            dtype=np.int64,
        ),
        span_reasons=np.asarray([span.reason for span in plan.spans]),
    )
    return {
        "eligible_unit_count": int(np.count_nonzero(rows[:, 5] > 0)) if len(rows) else 0,
        "span_count": len(plan.spans),
        "unit_count": len(rows),
        "vector_count": len(vectors),
    }


def validate_cache(
    path: Path,
    plan: CachePlan,
    *,
    config: PlannerConfig,
) -> dict[str, Any]:
    expected, expected_indexes = expected_rows(plan, config)
    with np.load(path, allow_pickle=False) as payload:
        rows = payload["rows"].astype(np.float64)
        indexes = payload["vec_idx"].astype(np.int64)
        vectors = payload["vecs"].astype(np.float32)
        span_bounds = payload["span_bounds"].astype(np.int64)
        span_reasons = payload["span_reasons"].astype(str)
    expected_bounds = np.asarray(
        [(span.span_id, span.start_sample, span.end_sample) for span in plan.spans],
        dtype=np.int64,
    )
    expected_reasons = np.asarray([span.reason for span in plan.spans])
    checks = {
        "rows": np.array_equal(rows, expected),
        "vector_indexes": np.array_equal(indexes, expected_indexes),
        "vector_count": len(vectors) == int(np.count_nonzero(expected_indexes >= 0)),
        "span_bounds": np.array_equal(span_bounds, expected_bounds),
        "span_reasons": np.array_equal(span_reasons, expected_reasons),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"cache_self_replan_mismatch:{','.join(failed)}")
    return {
        "checks": checks,
        "eligible_unit_count": int(np.count_nonzero(expected_indexes >= 0)),
        "self_replan": "PASS",
        "span_count": len(plan.spans),
        "unit_count": len(plan.units),
        "vector_count": len(vectors),
    }
