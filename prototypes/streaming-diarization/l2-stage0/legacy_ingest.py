#!/usr/bin/env python3
"""Diagnosis-only adapter for the superseded three-array L1 cache schema."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Sequence

import numpy as np

from production_cache import (
    CachePlan,
    EvidenceUnit,
    Piece,
    PlannedSpan,
    PlannerConfig,
)


LEGACY_REASON = "legacy_unavailable"


class LegacyIngestError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class LegacyArchive:
    rows: np.ndarray
    vector_indexes: np.ndarray
    vectors: np.ndarray
    sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_legacy_archive(path: Path) -> LegacyArchive:
    try:
        with path.open("rb") as handle:
            with np.load(handle, allow_pickle=False) as payload:
                required = {"rows", "vec_idx", "vecs"}
                missing = sorted(required - set(payload.files))
                if missing:
                    raise LegacyIngestError(
                        "legacy_archive_missing_field", ",".join(missing)
                    )
                extra = sorted(set(payload.files) - required)
                if extra:
                    raise LegacyIngestError(
                        "legacy_archive_schema_surprise", ",".join(extra)
                    )
                rows = payload["rows"].astype(np.float64)
                vector_indexes = payload["vec_idx"].astype(np.int64)
                vectors = payload["vecs"].astype(np.float32)
    except LegacyIngestError:
        raise
    except Exception as exc:
        raise LegacyIngestError(
            "legacy_archive_corrupt", f"{path}:{exc.__class__.__name__}:{exc}"
        ) from exc
    _validate_legacy_arrays(rows, vector_indexes, vectors)
    return LegacyArchive(
        rows=rows,
        vector_indexes=vector_indexes,
        vectors=vectors,
        sha256=sha256_file(path),
    )


def _validate_legacy_arrays(
    rows: np.ndarray,
    vector_indexes: np.ndarray,
    vectors: np.ndarray,
) -> None:
    if rows.ndim != 2:
        raise LegacyIngestError("legacy_row_schema_surprise", f"ndim={rows.ndim}")
    if rows.shape[1] < 6:
        raise LegacyIngestError(
            "legacy_row_schema_missing_field", f"columns={rows.shape[1]}"
        )
    if rows.shape[1] != 6:
        raise LegacyIngestError(
            "legacy_row_schema_surprise", f"columns={rows.shape[1]}"
        )
    if not len(rows):
        raise LegacyIngestError("legacy_row_schema_surprise", "rows_empty")
    if not np.isfinite(rows).all():
        raise LegacyIngestError("legacy_row_schema_surprise", "rows_non_finite")
    if vector_indexes.ndim != 1 or len(vector_indexes) != len(rows):
        raise LegacyIngestError(
            "legacy_vector_index_schema_surprise",
            f"shape={vector_indexes.shape}:rows={len(rows)}",
        )
    if vectors.ndim != 2 or not np.isfinite(vectors).all():
        raise LegacyIngestError(
            "legacy_vector_schema_surprise", f"shape={vectors.shape}"
        )
    for column, name in ((0, "span_id"), (1, "speaker_id")):
        values = rows[:, column]
        if np.any(values < 0) or not np.equal(values, values.astype(np.int64)).all():
            raise LegacyIngestError(
                "legacy_row_schema_surprise", f"{name}_invalid"
            )
    if np.any(rows[:, 2] < 0) or np.any(rows[:, 3] <= rows[:, 2]):
        raise LegacyIngestError("legacy_row_bounds_invalid", "start_end")
    if np.any(rows[:, 4] <= 0) or np.any(rows[:, 4] > rows[:, 3] - rows[:, 2] + 1e-9):
        raise LegacyIngestError("legacy_row_schema_surprise", "duration_invalid")
    if not np.isin(rows[:, 5], (0.0, 1.0)).all():
        raise LegacyIngestError("legacy_row_schema_surprise", "eligible_invalid")

    span_ids = rows[:, 0].astype(np.int64)
    if np.any(span_ids[1:] < span_ids[:-1]):
        raise LegacyIngestError("legacy_row_bounds_non_monotonic", "span_id_order")
    unique_spans = sorted(set(int(value) for value in span_ids))
    if unique_spans != list(range(len(unique_spans))):
        raise LegacyIngestError(
            "legacy_row_schema_surprise", f"span_ids={unique_spans}"
        )
    previous_end = None
    for span_id in unique_spans:
        span_rows = rows[span_ids == span_id]
        start = float(span_rows[:, 2].min())
        end = float(span_rows[:, 3].max())
        if previous_end is not None and start < previous_end - 1e-9:
            raise LegacyIngestError(
                "legacy_row_bounds_non_monotonic",
                f"span={span_id}:start={start}:previous_end={previous_end}",
            )
        previous_end = end

    eligible = rows[:, 5] > 0
    expected_indexes = np.where(
        eligible, np.cumsum(eligible) - 1, -1
    ).astype(np.int64)
    if not np.array_equal(vector_indexes, expected_indexes):
        raise LegacyIngestError("legacy_vector_index_mismatch", "eligible_order")
    if len(vectors) != int(np.count_nonzero(eligible)):
        raise LegacyIngestError(
            "legacy_vector_count_mismatch",
            f"vectors={len(vectors)}:eligible={int(np.count_nonzero(eligible))}",
        )


def _sample(seconds: float, sample_rate: int) -> int:
    return int(round(float(seconds) * sample_rate))


def _reconcile_archived_duration(
    pieces: list[Piece],
    row: np.ndarray,
    config: PlannerConfig,
) -> list[Piece]:
    eligible_indexes = [
        index
        for index, piece in enumerate(pieces)
        if piece.sample_count >= config.min_evidence_samples
    ]
    selected_indexes = eligible_indexes or list(range(len(pieces)))
    target_samples = _sample(float(row[4]), config.sample_rate)
    planned_samples = sum(pieces[index].sample_count for index in selected_indexes)
    residual = target_samples - planned_samples
    if residual == 0:
        return pieces
    if abs(residual) > len(selected_indexes):
        raise LegacyIngestError(
            "legacy_unit_duration_quantization_mismatch",
            f"target={target_samples}:planned={planned_samples}:residual={residual}",
        )
    index = selected_indexes[-1]
    piece = pieces[index]
    new_start = piece.start_sample - residual
    previous_end = pieces[index - 1].end_sample if index else None
    if new_start < 0 or new_start >= piece.end_sample:
        raise LegacyIngestError(
            "legacy_unit_duration_reconciliation_failed", f"residual={residual}"
        )
    if previous_end is not None and new_start < previous_end:
        raise LegacyIngestError(
            "legacy_unit_duration_reconciliation_failed",
            f"residual={residual}:previous_end={previous_end}:new_start={new_start}",
        )
    pieces[index] = Piece(
        span=piece.span,
        start_sample=new_start,
        end_sample=piece.end_sample,
        true_speaker=piece.true_speaker,
        sample_rate=piece.sample_rate,
    )
    return pieces


def derive_legacy_plan(
    archive: LegacyArchive,
    reference_rows: Sequence[tuple[float, float, str, str]],
    *,
    total_samples: int,
    config: PlannerConfig,
    span_reason: str = LEGACY_REASON,
) -> CachePlan:
    labels = tuple(dict.fromkeys(row[2] for row in reference_rows))
    speaker_index = {label: index for index, label in enumerate(labels)}
    units = []
    tolerance = 1.0 / config.sample_rate + 1e-12
    for unit_index, row in enumerate(archive.rows):
        span_id = int(row[0])
        true_speaker = int(row[1])
        unit_start = _sample(float(row[2]), config.sample_rate)
        unit_end = _sample(float(row[3]), config.sample_rate)
        pieces = []
        for start, end, label, _text in reference_rows:
            if speaker_index[label] != true_speaker:
                continue
            clipped_start = max(unit_start, _sample(start, config.sample_rate))
            clipped_end = min(unit_end, _sample(end, config.sample_rate))
            if clipped_end <= clipped_start:
                continue
            pieces.append(
                Piece(
                    span=span_id,
                    start_sample=clipped_start,
                    end_sample=clipped_end,
                    true_speaker=true_speaker,
                    sample_rate=config.sample_rate,
                )
            )
        if not pieces:
            raise LegacyIngestError(
                "legacy_unit_reference_mismatch",
                f"span={span_id}:speaker={true_speaker}:start={row[2]}:end={row[3]}",
            )
        pieces = _reconcile_archived_duration(pieces, row, config)
        planned_start = min(piece.start for piece in pieces)
        planned_end = max(piece.end for piece in pieces)
        eligible = [
            piece for piece in pieces
            if piece.sample_count >= config.min_evidence_samples
        ]
        planned_duration = sum(piece.duration for piece in eligible or pieces)
        deltas = {
            "start": abs(planned_start - float(row[2])),
            "end": abs(planned_end - float(row[3])),
            "duration": abs(planned_duration - float(row[4])),
        }
        failed = [name for name, delta in deltas.items() if delta > tolerance]
        if failed:
            raise LegacyIngestError(
                "legacy_unit_reference_mismatch",
                f"unit={unit_index}:fields={','.join(failed)}:deltas={deltas}",
            )
        if bool(eligible) != bool(row[5]):
            raise LegacyIngestError(
                "legacy_unit_eligibility_mismatch", f"unit={unit_index}"
            )
        units.append(
            EvidenceUnit(
                span_id=span_id,
                true_speaker=true_speaker,
                pieces=tuple(pieces),
            )
        )
    span_ids = archive.rows[:, 0].astype(np.int64)
    spans = []
    for span_id in sorted(set(int(value) for value in span_ids)):
        pieces = [
            piece
            for unit in units
            if unit.span_id == span_id
            for piece in unit.pieces
        ]
        spans.append(
            PlannedSpan(
                span_id=span_id,
                start_sample=min(piece.start_sample for piece in pieces),
                end_sample=max(piece.end_sample for piece in pieces),
                reason=span_reason,
            )
        )
    return CachePlan(
        spans=tuple(spans),
        units=tuple(units),
        speaker_labels=labels,
        total_samples=total_samples,
    )


def write_adapted_cache(
    archive: LegacyArchive,
    plan: CachePlan,
    output_path: Path,
) -> dict[str, object]:
    if output_path.exists():
        raise LegacyIngestError("legacy_adapted_cache_exists", str(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    span_bounds = np.asarray(
        [(span.span_id, span.start_sample, span.end_sample) for span in plan.spans],
        dtype=np.int64,
    )
    span_reasons = np.asarray([span.reason for span in plan.spans])
    np.savez(
        output_path,
        rows=archive.rows,
        vec_idx=archive.vector_indexes,
        vecs=archive.vectors,
        span_bounds=span_bounds,
        span_reasons=span_reasons,
    )
    return {
        "adapted_cache_sha256": sha256_file(output_path),
        "duration_source": "archived_rows_nearest_sample_no_tolerance_change",
        "legacy_archive_sha256": archive.sha256,
        "span_bounds_source": "reconciled_piece_min_max",
        "span_count": len(plan.spans),
        "span_reason": plan.spans[0].reason if plan.spans else None,
        "unit_count": len(plan.units),
        "vector_count": len(archive.vectors),
    }


def validate_adapted_cache(
    path: Path,
    archive: LegacyArchive,
    plan: CachePlan,
    *,
    config: PlannerConfig,
) -> dict[str, object]:
    with np.load(path, allow_pickle=False) as payload:
        rows = payload["rows"].astype(np.float64)
        indexes = payload["vec_idx"].astype(np.int64)
        vectors = payload["vecs"].astype(np.float32)
        bounds = payload["span_bounds"].astype(np.int64)
        reasons = payload["span_reasons"].astype(str)
    expected_bounds = np.asarray(
        [(span.span_id, span.start_sample, span.end_sample) for span in plan.spans],
        dtype=np.int64,
    )
    expected_reasons = np.asarray([span.reason for span in plan.spans])
    checks = {
        "archived_rows_byte_values": np.array_equal(rows, archive.rows),
        "archived_vector_indexes_byte_values": np.array_equal(indexes, archive.vector_indexes),
        "archived_vectors_byte_values": np.array_equal(vectors, archive.vectors),
        "span_bounds_from_archived_rows": np.array_equal(bounds, expected_bounds),
        "span_reasons_declared": np.array_equal(reasons, expected_reasons),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise LegacyIngestError("legacy_adapted_cache_validation_failed", ",".join(failed))
    if len(plan.units) != len(rows):
        raise LegacyIngestError(
            "legacy_unit_count_mismatch", f"plan={len(plan.units)}:rows={len(rows)}"
        )
    max_duration_delta = 0.0
    for unit_index, (unit, row) in enumerate(zip(plan.units, rows, strict=True)):
        if (unit.span_id, unit.true_speaker) != (int(row[0]), int(row[1])):
            raise LegacyIngestError(
                "legacy_unit_key_mismatch", f"unit={unit_index}"
            )
        eligible = [
            piece for piece in unit.pieces
            if piece.sample_count >= config.min_evidence_samples
        ]
        duration = sum(piece.duration for piece in eligible or unit.pieces)
        max_duration_delta = max(max_duration_delta, abs(duration - float(row[4])))
    if max_duration_delta > 1.0 / config.sample_rate + 1e-12:
        raise LegacyIngestError(
            "legacy_unit_duration_mismatch",
            f"max_delta={max_duration_delta:.9f}",
        )
    return {
        "checks": checks,
        "max_duration_delta_seconds": round(max_duration_delta, 9),
        "self_replan": "LEGACY_INGEST_PASS",
        "span_count": len(plan.spans),
        "unit_count": len(plan.units),
        "vector_count": len(vectors),
    }
