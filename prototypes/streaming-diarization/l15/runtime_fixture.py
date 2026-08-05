#!/usr/bin/env python3
"""D8-safe runtime fixtures derived only from audio and deployed ASR segments."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import inspect
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

import numpy as np


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_endpoint import (  # noqa: E402
    EndpointPolicy,
    EndpointPolicyConfig,
    SpeechObservation,
)


SAMPLE_RATE = 16_000
MIN_SPEECH_SAMPLES = 1_600
MIN_SILENCE_SAMPLES = 8_000
PRE_SPEECH_PADDING_SAMPLES = 0
POST_SPEECH_PADDING_SAMPLES = 0
HARD_CAP_SAMPLES = 40_000
MIN_EVIDENCE_SAMPLES = 8_000


@dataclass(frozen=True, slots=True)
class RuntimeSpan:
    span_id: int
    start_sample: int
    end_sample: int
    reason: str


@dataclass(frozen=True, slots=True)
class RuntimePiece:
    start_sample: int
    end_sample: int

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample

    @property
    def start(self) -> float:
        return self.start_sample / SAMPLE_RATE

    @property
    def end(self) -> float:
        return self.end_sample / SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class RuntimeUnit:
    span_id: int
    local_speaker: str
    pieces: tuple[RuntimePiece, ...]


@dataclass(frozen=True, slots=True)
class RuntimePlan:
    spans: tuple[RuntimeSpan, ...]
    units: tuple[RuntimeUnit, ...]
    total_samples: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def planner_bindings() -> dict[str, str]:
    name = f"{EndpointPolicy.__module__}.{EndpointPolicy.__name__}"
    source = Path(inspect.getsourcefile(EndpointPolicy) or "").resolve()
    expected = (REPO / "moss_transcribe_diarize/app/live_endpoint.py").resolve()
    if name != "moss_transcribe_diarize.app.live_endpoint.EndpointPolicy" or source != expected:
        raise RuntimeError(f"runtime_planner_binding_mismatch:{name}:{source}")
    return {
        "policy": name,
        "source_path": source.relative_to(REPO).as_posix(),
        "source_sha256": sha256_file(source),
    }


def _speech_union(intervals: Iterable[tuple[int, int]], total_samples: int) -> list[tuple[int, int]]:
    merged: list[list[int]] = []
    for raw_start, raw_end in sorted(intervals):
        start = max(0, min(total_samples, raw_start))
        end = max(0, min(total_samples, raw_end))
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
        if cursor < start:
            yield SpeechObservation(cursor, start, False)
        yield SpeechObservation(start, end, True)
        cursor = end
    if cursor < total_samples:
        yield SpeechObservation(cursor, total_samples, False)


def _sample(seconds: object) -> int:
    return int(round(float(seconds) * SAMPLE_RATE))


def plan_runtime_asr(segments: Sequence[dict[str, Any]], *, total_samples: int) -> RuntimePlan:
    if total_samples <= 0:
        raise ValueError("runtime_audio_sample_count_invalid")
    normalized: list[tuple[int, int, str]] = []
    for index, segment in enumerate(segments):
        speaker = str(segment.get("speaker", "")).strip()
        if not speaker:
            raise ValueError(f"runtime_asr_speaker_absent:{index}")
        start = max(0, min(total_samples, _sample(segment["start"])))
        end = max(0, min(total_samples, _sample(segment["end"])))
        if end <= start:
            raise ValueError(f"runtime_asr_interval_invalid:{index}:{start}:{end}")
        normalized.append((start, end, speaker))
    normalized.sort(key=lambda item: (item[0], item[1], item[2]))
    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=MIN_SPEECH_SAMPLES,
            min_silence_samples=MIN_SILENCE_SAMPLES,
            pre_speech_padding_samples=PRE_SPEECH_PADDING_SAMPLES,
            post_speech_padding_samples=POST_SPEECH_PADDING_SAMPLES,
            hard_cap_samples=HARD_CAP_SAMPLES,
        )
    )
    emitted = []
    speech = _speech_union(((start, end) for start, end, _speaker in normalized), total_samples)
    for observation in _observations(speech, total_samples):
        emitted.extend(policy.observe(observation))
    emitted.extend(policy.flush())
    spans = tuple(
        RuntimeSpan(index, span.start_sample, span.end_sample, span.reason)
        for index, span in enumerate(emitted)
    )
    if sum(span.end_sample - span.start_sample for span in spans) != total_samples:
        raise RuntimeError("runtime_plan_not_gap_free")
    if any(left.end_sample != right.start_sample for left, right in zip(spans, spans[1:])):
        raise RuntimeError("runtime_plan_not_contiguous")
    grouped: dict[tuple[int, str], list[RuntimePiece]] = {}
    for span in spans:
        for start, end, speaker in normalized:
            clipped_start = max(span.start_sample, start)
            clipped_end = min(span.end_sample, end)
            if clipped_end > clipped_start:
                grouped.setdefault((span.span_id, speaker), []).append(
                    RuntimePiece(clipped_start, clipped_end)
                )
    units = tuple(
        RuntimeUnit(span_id, speaker, tuple(grouped[(span_id, speaker)]))
        for span_id, speaker in sorted(grouped)
    )
    return RuntimePlan(spans=spans, units=units, total_samples=total_samples)


def runtime_shape(plan: RuntimePlan) -> tuple[object, ...]:
    return (
        tuple((span.span_id, span.start_sample, span.end_sample, span.reason) for span in plan.spans),
        tuple(
            (
                unit.span_id,
                unit.local_speaker,
                tuple((piece.start_sample, piece.end_sample) for piece in unit.pieces),
            )
            for unit in plan.units
        ),
    )


def expected_arrays(plan: RuntimePlan) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rows: list[tuple[float, ...]] = []
    indexes: list[int] = []
    labels: list[str] = []
    vector_count = 0
    for unit_index, unit in enumerate(plan.units):
        eligible = [piece for piece in unit.pieces if piece.sample_count >= MIN_EVIDENCE_SAMPLES]
        selected = eligible or list(unit.pieces)
        rows.append(
            (
                float(unit.span_id),
                float(unit_index),
                min(piece.start_sample for piece in unit.pieces) / SAMPLE_RATE,
                max(piece.end_sample for piece in unit.pieces) / SAMPLE_RATE,
                sum(piece.sample_count for piece in selected) / SAMPLE_RATE,
                float(bool(eligible)),
            )
        )
        labels.append(unit.local_speaker)
        if eligible:
            indexes.append(vector_count)
            vector_count += 1
        else:
            indexes.append(-1)
    return (
        np.asarray(rows, dtype=np.float64).reshape((-1, 6)),
        np.asarray(indexes, dtype=np.int64),
        np.asarray(labels, dtype=np.str_),
    )


def build_runtime_cache(
    plan: RuntimePlan,
    *,
    audio_path: Path,
    output_path: Path,
    embedder: Any,
    embedding_dimension: int = 256,
) -> dict[str, int]:
    if output_path.exists():
        raise RuntimeError(f"runtime_cache_version_exists:{output_path}")
    rows, indexes, labels = expected_arrays(plan)
    vectors: list[np.ndarray] = []
    for unit, vector_index in zip(plan.units, indexes, strict=True):
        if vector_index < 0:
            continue
        intervals = [
            (piece.start, piece.end)
            for piece in unit.pieces
            if piece.sample_count >= MIN_EVIDENCE_SAMPLES
        ]
        vector = np.asarray(embedder.embed(audio_path, intervals), dtype=np.float32)
        if vector.shape != (embedding_dimension,):
            raise RuntimeError(f"runtime_embedding_shape:{vector.shape}")
        vectors.append(vector)
    stacked = (
        np.stack(vectors)
        if vectors
        else np.zeros((0, embedding_dimension), dtype=np.float32)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        output_path,
        rows=rows,
        vec_idx=indexes,
        vecs=stacked,
        local_speakers=labels,
        span_bounds=np.asarray(
            [(span.span_id, span.start_sample, span.end_sample) for span in plan.spans],
            dtype=np.int64,
        ),
        span_reasons=np.asarray([span.reason for span in plan.spans], dtype=np.str_),
    )
    return {
        "span_count": len(plan.spans),
        "unit_count": len(plan.units),
        "eligible_unit_count": int(np.count_nonzero(indexes >= 0)),
        "vector_count": len(vectors),
    }


def validate_runtime_cache(path: Path, plan: RuntimePlan) -> dict[str, object]:
    expected_rows, expected_indexes, expected_labels = expected_arrays(plan)
    with np.load(path, allow_pickle=False) as payload:
        checks = {
            "rows": np.array_equal(payload["rows"], expected_rows),
            "vector_indexes": np.array_equal(payload["vec_idx"], expected_indexes),
            "local_speakers": np.array_equal(payload["local_speakers"], expected_labels),
            "span_bounds": np.array_equal(
                payload["span_bounds"],
                np.asarray(
                    [(span.span_id, span.start_sample, span.end_sample) for span in plan.spans],
                    dtype=np.int64,
                ),
            ),
            "span_reasons": np.array_equal(
                payload["span_reasons"],
                np.asarray([span.reason for span in plan.spans], dtype=np.str_),
            ),
            "vector_count": len(payload["vecs"]) == int(np.count_nonzero(expected_indexes >= 0)),
        }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"runtime_cache_self_replan_mismatch:{','.join(failed)}")
    return {"checks": checks, "self_replan": "PASS"}
