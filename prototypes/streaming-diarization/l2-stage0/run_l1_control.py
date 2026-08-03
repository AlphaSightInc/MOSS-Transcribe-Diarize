#!/usr/bin/env python3
"""PROTOTYPE — A2 production L1 control runner."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Sequence

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

import numpy as np

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
)
from moss_transcribe_diarize.app.live_identity_album import (
    ALBUM_ADMISSION_SECONDS,
    ALBUM_BIRTH_MIN_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    FingerprintAlbum,
)
from moss_transcribe_diarize.app.live_identity_sweep import (
    SWEEP_INTERVAL_SECONDS,
    SWEEP_MERGE_THRESHOLD,
    SweepLedger,
    sweep,
)
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot
from moss_transcribe_diarize.live_speaker_accuracy import (
    SpeakerActivityInterval,
    load_reference_speaker_activity_jsonl,
    score_live_speaker_accuracy,
)
from production_cache import (
    Piece,
    PlannerConfig,
    plan_reference,
    production_planner_bindings,
    validate_cache,
)


BLOCKED_PROMISE = "<promise>BLOCKED</promise>"


class ControlError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def production_bindings() -> dict[str, str]:
    ledger_name = f"{SweepLedger.__module__}.{SweepLedger.__name__}"
    sweep_name = f"{sweep.__module__}.{sweep.__name__}"
    expected_ledger = "moss_transcribe_diarize.app.live_identity_sweep.SweepLedger"
    expected_sweep = "moss_transcribe_diarize.app.live_identity_sweep.sweep"
    if ledger_name != expected_ledger or sweep_name != expected_sweep:
        raise ControlError(
            "l1_production_import_mismatch",
            f"ledger={ledger_name} sweep={sweep_name}",
        )
    source = Path(inspect.getsourcefile(sweep) or "").resolve()
    expected_source = (REPO / "moss_transcribe_diarize/app/live_identity_sweep.py").resolve()
    if source != expected_source:
        raise ControlError("l1_production_source_mismatch", str(source))
    return {
        "ledger": ledger_name,
        "source_path": source.relative_to(REPO).as_posix(),
        "source_sha256": _sha256(source),
        "sweep": sweep_name,
    }


class CachedEncoder:
    """Return only the frozen production vectors for the exact requested intervals."""

    def __init__(self) -> None:
        self.unit_of_start: dict[float, int] = {}
        self.vector_of_unit: dict[int, list[float]] = {}
        self.intervals_seen: dict[int, list[tuple[float, float]]] = {}

    def embed(self, wav_path: Path, intervals: Sequence[tuple[float, float]]) -> list[float]:
        del wav_path
        unit = self.unit_of_start[round(float(intervals[0][0]), 6)]
        self.intervals_seen[unit] = [
            (float(start), float(end)) for start, end in intervals
        ]
        return self.vector_of_unit[unit]


def _resolve(root: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def _truth(
    reference_path: Path,
) -> tuple[list[tuple[float, float, str, str]], tuple[SpeakerActivityInterval, ...]]:
    reference = load_reference_speaker_activity_jsonl(reference_path)
    truth = [
        (interval.start, interval.end, interval.speaker, "")
        for interval in reference
    ]
    return truth, reference


def _planner_config(production_config: dict[str, object]) -> PlannerConfig:
    return PlannerConfig.from_mapping(
        {
            name: production_config[name]
            for name in PlannerConfig.__dataclass_fields__
        }
    )


def _load_cache(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    with np.load(path) as payload:
        rows = payload["rows"].astype(np.float64)
        vectors = payload["vecs"].astype(np.float32)
        stored_index = payload["vec_idx"].astype(np.int64)
    eligible = rows[:, 5] > 0
    vector_index = np.where(eligible, np.cumsum(eligible) - 1, -1).astype(np.int64)
    if not np.array_equal(stored_index, vector_index):
        raise ControlError("l1_vector_index_mismatch", str(path))
    if int(np.count_nonzero(eligible)) != len(vectors):
        raise ControlError("l1_vector_count_mismatch", str(path))
    return rows, vectors, vector_index


def _assert_fixture_fidelity(
    case_id: str,
    units: list[list[Piece]],
    rows: np.ndarray,
    *,
    sample_rate: int,
    min_evidence_samples: int,
) -> dict[str, object]:
    if len(units) != len(rows):
        raise ControlError(
            "l1_fixture_unit_count_mismatch",
            f"{case_id}:planned={len(units)} cached={len(rows)}",
        )
    max_duration_delta = 0.0
    for index, (pieces, row) in enumerate(zip(units, rows, strict=True)):
        planned_key = (pieces[0].span, pieces[0].true_speaker)
        cached_key = (int(row[0]), int(row[1]))
        if planned_key != cached_key:
            raise ControlError(
                "l1_fixture_unit_key_mismatch",
                f"{case_id}:{index}:planned={planned_key} cached={cached_key}",
            )
        selected = [
            piece for piece in pieces
            if piece.sample_count >= min_evidence_samples
        ]
        duration = sum(piece.duration for piece in selected or pieces)
        delta = abs(duration - float(row[4]))
        max_duration_delta = max(max_duration_delta, delta)
        if delta > 1.0 / sample_rate:
            raise ControlError(
                "l1_fixture_duration_mismatch",
                f"{case_id}:{index}:planned={duration:.9f} cached={row[4]:.9f}",
            )
    return {
        "eligible_unit_count": int(np.count_nonzero(rows[:, 5] > 0)),
        "max_duration_delta_seconds": round(max_duration_delta, 9),
        "unit_count": len(units),
    }


def _hypothesis(
    units: list[list[Piece]], labels: Sequence[str | None]
) -> tuple[SpeakerActivityInterval, ...]:
    return tuple(
        SpeakerActivityInterval(piece.start, piece.end, label)
        for pieces, label in zip(units, labels, strict=True)
        if label is not None
        for piece in pieces
    )


def replay_case(
    case: dict[str, object],
    production_config: dict[str, object],
    *,
    repo_root: Path = REPO,
) -> dict[str, object]:
    """Drive the production identity path and production L1 sweep over one frozen cache."""

    case_id = str(case["case_id"])
    reference_path = _resolve(repo_root, case["reference_path"])
    cache_path = _resolve(repo_root, case["vector_cache_path"])
    truth, reference = _truth(reference_path)
    rows, vectors, vector_index = _load_cache(cache_path)
    sample_rate = int(production_config["sample_rate"])
    planner_config = _planner_config(production_config)
    plan = plan_reference(
        truth,
        total_samples=int(round(float(case["duration_seconds"]) * sample_rate)),
        config=planner_config,
    )
    try:
        cache_self_replan = validate_cache(cache_path, plan, config=planner_config)
    except RuntimeError as exc:
        raise ControlError("l1_cache_self_replan_mismatch", f"{case_id}:{exc}") from exc
    units = [list(unit.pieces) for unit in plan.units]
    fidelity = _assert_fixture_fidelity(
        case_id,
        units,
        rows,
        sample_rate=sample_rate,
        min_evidence_samples=planner_config.min_evidence_samples,
    )
    fidelity["cache_self_replan"] = cache_self_replan
    encoder = CachedEncoder()
    album = FingerprintAlbum(
        admission_seconds=float(production_config["album_admission_seconds"]),
        exemplars_per_speaker=int(production_config["album_exemplars_per_speaker"]),
    )
    identity_config = LiveIdentityConfig(
        max_speakers=int(production_config["max_speakers"]),
        min_match_score=float(production_config["min_match_score"]),
        min_match_margin=float(production_config["min_match_margin"]),
    )
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=encoder,
        min_segment_samples=int(production_config["min_evidence_samples"]),
        birth_min_seconds=float(production_config["album_birth_min_seconds"]),
        album=album,
    )
    preparer = BoundedCausalIdentityPreparer(
        config=identity_config,
        evidence_provider=provider,
    )
    ledger = SweepLedger()
    spans: dict[int, list[int]] = {}
    for index, pieces in enumerate(units):
        spans.setdefault(pieces[0].span, []).append(index)
    snapshot = LiveIdentitySnapshot()
    live_labels: list[str | None] = [None] * len(units)
    final_labels: list[str | None] = [None] * len(units)
    unit_of: dict[tuple[int, str], int] = {}
    span_trace: list[dict[str, object]] = []
    revision_trace: list[dict[str, object]] = []
    counts = {"abstain": 0, "failed": 0, "prepared": 0}
    sweep_interval = float(production_config["sweep_interval_seconds"])
    next_sweep_at = sweep_interval

    def run_sweep(reason: str, meeting_seconds: float, *, apply: bool) -> int:
        before = {
            f"{span_id}:{unit.local_speaker}": unit.canonical_speaker
            for span_id, members in ledger.spans()
            for unit in members
        }
        revision = sweep(
            ledger=ledger,
            album=album,
            config=identity_config,
            merge_threshold=float(production_config["merge_threshold"]),
        )
        applied = 0
        if apply:
            for correction in revision.corrections:
                final_labels[unit_of[(correction.span_id, correction.local_speaker)]] = (
                    correction.canonical_speaker
                )
            applied = ledger.apply(revision)
        after = {
            f"{span_id}:{unit.local_speaker}": unit.canonical_speaker
            for span_id, members in ledger.spans()
            for unit in members
        }
        revision_trace.append(
            {
                "applied_corrections": applied,
                "apply": apply,
                "labels_after": after,
                "labels_before": before,
                "meeting_seconds": round(meeting_seconds, 6),
                "reason": reason,
                "revision": revision.to_dict(),
            }
        )
        return len(revision.corrections)

    for planned_span in plan.spans:
        span_id = planned_span.span_id
        members = sorted(spans.get(span_id, []), key=lambda index: units[index][0].start)
        span_start = planned_span.start_sample / sample_rate
        span_end = planned_span.end_sample / sample_rate
        sample_count = planned_span.end_sample - planned_span.start_sample
        if not members:
            counts["no_speaker_activity"] = counts.get("no_speaker_activity", 0) + 1
            span_trace.append(
                {
                    "assignments": {},
                    "canonical_speakers": list(snapshot.canonical_speakers),
                    "diagnostics": {},
                    "end_seconds": round(span_end, 6),
                    "ledger_records": [],
                    "reason": planned_span.reason,
                    "span_id": span_id,
                    "start_seconds": round(span_start, 6),
                    "status": "no_speaker_activity",
                }
            )
            if span_end >= next_sweep_at:
                run_sweep("cadence", span_end, apply=True)
                next_sweep_at = (int(span_end // sweep_interval) + 1) * sweep_interval
            continue
        label_of = {
            index: f"S{position + 1:02d}"
            for position, index in enumerate(members)
        }
        unit_of.update({(span_id, label): index for index, label in label_of.items()})
        encoder.unit_of_start = {}
        encoder.vector_of_unit = {}
        segments: list[tuple[float, float, str]] = []
        for index in members:
            for piece in units[index]:
                relative_start = piece.start - span_start
                relative_end = piece.end - span_start
                segments.append((relative_start, relative_end, label_of[index]))
                encoder.unit_of_start[round(relative_start, 6)] = index
            if vector_index[index] >= 0:
                encoder.vector_of_unit[index] = [
                    float(value) for value in vectors[vector_index[index]]
                ]
        segments.sort()
        preparation = preparer.prepare(
            span=FrozenSpan(
                id=span_id,
                epoch=0,
                start_sample=planned_span.start_sample,
                end_sample=planned_span.end_sample,
                reason=planned_span.reason,
            ),
            pcm=b"\0\0" * sample_count,
            transcript="".join(
                f"[{start:.6f}][{label}]w[{end:.6f}]"
                for start, end, label in segments
            ),
            base_snapshot=snapshot,
        )
        counts[preparation.status] = counts.get(preparation.status, 0) + 1
        diagnostics = dict(preparation.proposed_snapshot.diagnostics)
        assignments: dict[str, str] = {}
        if preparation.status == "prepared":
            label_to_unit = {label: index for index, label in label_of.items()}
            for assignment in diagnostics.get("assignments", "").split(","):
                if "->" not in assignment:
                    continue
                local, canonical = assignment.split("->", 1)
                assignments[local] = canonical
                live_labels[label_to_unit[local]] = canonical
                final_labels[label_to_unit[local]] = canonical
            snapshot = preparation.proposed_snapshot
        records = []
        for index in members:
            intervals = encoder.intervals_seen.get(index)
            if not intervals:
                continue
            disposition = ledger.record(
                span_id=span_id,
                local_speaker=label_of[index],
                canonical_speaker=final_labels[index],
                vector=vectors[vector_index[index]],
                duration_sec=sum(end - start for start, end in intervals),
            )
            records.append(
                {
                    "canonical_speaker": final_labels[index],
                    "disposition": disposition,
                    "duration_seconds": round(
                        sum(end - start for start, end in intervals), 6
                    ),
                    "local_speaker": label_of[index],
                    "unit_index": index,
                }
            )
        span_trace.append(
            {
                "assignments": assignments,
                "canonical_speakers": list(snapshot.canonical_speakers),
                "diagnostics": diagnostics,
                "end_seconds": round(span_end, 6),
                "ledger_records": records,
                "reason": planned_span.reason,
                "span_id": span_id,
                "start_seconds": round(span_start, 6),
                "status": preparation.status,
            }
        )
        if span_end >= next_sweep_at:
            run_sweep("cadence", span_end, apply=True)
            next_sweep_at = (int(span_end // sweep_interval) + 1) * sweep_interval

    end_seconds = plan.total_samples / sample_rate
    run_sweep("final", end_seconds, apply=True)
    residual_corrections = run_sweep("residual_check", end_seconds, apply=False)
    live_hypothesis = _hypothesis(units, live_labels)
    final_hypothesis = _hypothesis(units, final_labels)
    live_metrics = score_live_speaker_accuracy(reference, live_hypothesis)
    metrics = score_live_speaker_accuracy(reference, final_hypothesis)
    changed_seconds = sum(
        piece.duration
        for pieces, live, final in zip(units, live_labels, final_labels, strict=True)
        if live != final
        for piece in pieces
    )
    reference_seconds = sum(interval.duration for interval in reference)
    return {
        "case_id": case_id,
        "changed_duration_fraction": round(
            changed_seconds / reference_seconds if reference_seconds else 0.0, 6
        ),
        "changed_speaker_seconds": round(changed_seconds, 6),
        "counts": {
            **counts,
            "final_canonical_speakers": len({item for item in final_labels if item}),
            "ledger_refused_units": ledger.refused_units,
            "ledger_spans": ledger.span_count,
            "ledger_units": ledger.unit_count,
            "live_canonical_speakers": len({item for item in live_labels if item}),
            "residual_corrections": residual_corrections,
        },
        "final_unit_labels": final_labels,
        "fixture_fidelity": fidelity,
        "live_metrics": live_metrics,
        "live_unit_labels": live_labels,
        "metrics": metrics,
        "production_bindings": production_bindings(),
        "production_planner": production_planner_bindings(),
        "production_config": production_config,
        "revision_trace": revision_trace,
        "span_trace": span_trace,
        "split": case["split"],
    }


def select_cases(
    corpus: dict[str, object],
    candidate: dict[str, object],
    requested_ids: list[str],
) -> list[dict[str, object]]:
    by_id = {str(case["case_id"]): case for case in corpus["cases"]}
    selected = []
    for case_id in requested_ids:
        if case_id not in by_id:
            raise ControlError("l1_case_unknown", case_id)
        case = by_id[case_id]
        if case.get("split") == "blind_holdout":
            if not candidate.get("candidate_frozen"):
                raise ControlError("l1_holdout_before_candidate_freeze", case_id)
            raise ControlError("l1_holdout_requires_a5_opening_session", case_id)
        if not case.get("acceptance_eligible"):
            raise ControlError("l1_case_not_acceptance_eligible", case_id)
        if case.get("split") not in {"development", "validation"}:
            raise ControlError("l1_case_split_not_allowed", f"{case_id}:{case.get('split')}")
        selected.append(case)
    return selected


def _assert_production_source_commit(source_commit: object) -> None:
    ancestor = subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor", str(source_commit), "HEAD"],
        check=False,
    )
    if ancestor.returncode != 0:
        raise ControlError("l1_source_commit_not_ancestor", str(source_commit))
    product_diff = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "diff",
            "--quiet",
            str(source_commit),
            "HEAD",
            "--",
            "moss_transcribe_diarize",
        ],
        check=False,
    )
    if product_diff.returncode != 0:
        raise ControlError("l1_product_tree_drift", str(source_commit))


def _validate_file_hash(root: Path, path_value: object, expected: object, label: str) -> None:
    path = _resolve(root, path_value)
    actual = _sha256(path)
    if actual != expected:
        raise ControlError(f"l1_{label}_hash_mismatch", f"{path}:{actual}")


def validate_control_inputs(
    spec: dict[str, object],
    corpus: dict[str, object],
    selected: list[dict[str, object]],
    model: dict[str, object],
    *,
    corpus_manifest: Path,
) -> dict[str, object]:
    _assert_production_source_commit(spec["source_commit"])
    actual_corpus_hash = _sha256(corpus_manifest)
    if actual_corpus_hash != spec["corpus_manifest_sha256"]:
        raise ControlError("l1_corpus_manifest_hash_mismatch", actual_corpus_hash)
    procedure_path = _resolve(REPO, spec["a5_holdout_procedure_path"])
    if _sha256(procedure_path) != spec["a5_holdout_procedure_sha256"]:
        raise ControlError("l1_a5_holdout_procedure_hash_mismatch", str(procedure_path))
    cache_spec_path = _resolve(REPO, spec["cache_rebuild_spec_path"])
    if _sha256(cache_spec_path) != spec["cache_rebuild_spec_sha256"]:
        raise ControlError("l1_cache_rebuild_spec_hash_mismatch", str(cache_spec_path))
    cache_spec = json.loads(cache_spec_path.read_text(encoding="utf-8"))
    selected_ids = [case["case_id"] for case in selected]
    if selected_ids != spec["case_ids"] or len(selected) != int(spec["expected_case_count"]):
        raise ControlError("l1_case_scope_mismatch", json.dumps(selected_ids))
    for case in selected:
        for label in ("audio", "reference", "vector_cache"):
            _validate_file_hash(
                REPO,
                case[f"{label}_path"],
                case[f"{label}_sha256"],
                label,
            )
    _validate_file_hash(
        REPO,
        model["asset"]["path"],
        model["asset"]["sha256"],
        "model",
    )
    config = spec["production_config"]
    expected_constants = {
        "album_admission_seconds": ALBUM_ADMISSION_SECONDS,
        "album_birth_min_seconds": ALBUM_BIRTH_MIN_SECONDS,
        "album_exemplars_per_speaker": ALBUM_EXEMPLARS_PER_SPEAKER,
        "merge_threshold": SWEEP_MERGE_THRESHOLD,
        "min_match_margin": ALBUM_MIN_MATCH_MARGIN,
        "min_match_score": ALBUM_MIN_MATCH_SCORE,
        "sweep_interval_seconds": SWEEP_INTERVAL_SECONDS,
    }
    drift = {
        name: {"expected": value, "spec": config.get(name)}
        for name, value in expected_constants.items()
        if config.get(name) != value
    }
    if drift:
        raise ControlError("l1_production_constant_drift", json.dumps(drift, sort_keys=True))
    frontend = model["frontend"]["config"]
    for name in ("hard_cap_samples", "min_evidence_samples", "sample_rate"):
        if config[name] != frontend[name]:
            raise ControlError(
                "l1_frontend_config_drift",
                f"{name}:spec={config[name]} model={frontend[name]}",
            )
    if int(config["hard_cap_samples"]) != 40000:
        raise ControlError("l1_hard_cap_changed", str(config["hard_cap_samples"]))
    planner_values = {
        name: config[name] for name in PlannerConfig.__dataclass_fields__
    }
    if planner_values != cache_spec["config"]:
        raise ControlError(
            "l1_cache_planner_config_drift",
            json.dumps({"cache": cache_spec["config"], "l1": planner_values}, sort_keys=True),
        )
    if production_planner_bindings() != cache_spec["production_planner"]:
        raise ControlError("l1_cache_planner_binding_drift", str(cache_spec_path))
    return {
        "a5_holdout_procedure_sha256": spec["a5_holdout_procedure_sha256"],
        "corpus_manifest_sha256": actual_corpus_hash,
        "cache_rebuild_spec_sha256": spec["cache_rebuild_spec_sha256"],
        "model_manifest_sha256": _sha256(HERE / "model-manifest.json"),
        "production_bindings": production_bindings(),
        "source_commit": spec["source_commit"],
        "spec_sha256": _sha256(HERE / "l1-control-spec.json"),
    }


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return _sha256(path)


def run_controls(
    spec: dict[str, object],
    selected: list[dict[str, object]],
    provenance: dict[str, object],
    *,
    evidence_dir: Path,
) -> tuple[dict[str, object], str]:
    repeatability = spec["repeatability"]
    run_count = int(repeatability["runs_per_case"])
    cases = []
    failures: list[str] = []
    transcript = [
        f"A2 L1 control source_commit={provenance['source_commit']}",
        f"scope={len(selected)} development/validation cases holdout=SEALED",
    ]
    for case in selected:
        run_records = []
        for run_index in range(1, run_count + 1):
            result = replay_case(case, spec["production_config"])
            semantic_hash = semantic_sha256(result)
            path = evidence_dir / f"a2-l1-{case['case_id']}-run{run_index}.json"
            wrapper = {
                "case_id": case["case_id"],
                "result": result,
                "run_index": run_index,
                "semantic_sha256": semantic_hash,
            }
            file_hash = _write_json(path, wrapper)
            run_records.append(
                {
                    "path": path.relative_to(REPO).as_posix(),
                    "result_sha256": file_hash,
                    "run_index": run_index,
                    "semantic_sha256": semantic_hash,
                }
            )
        deterministic = len({item["semantic_sha256"] for item in run_records}) == 1
        if not deterministic:
            failures.append(f"l1_repeatability_failed:{case['case_id']}")
        first_result = json.loads(
            (REPO / run_records[0]["path"]).read_text(encoding="utf-8")
        )["result"]
        metrics = first_result["metrics"]
        cases.append(
            {
                "case_id": case["case_id"],
                "changed_duration_fraction": first_result["changed_duration_fraction"],
                "deterministic": deterministic,
                "metrics": metrics,
                "runs": run_records,
                "split": case["split"],
            }
        )
        transcript.append(
            ("PASS " if deterministic else "FAIL ")
            + f"{case['case_id']} repeat={run_records[0]['semantic_sha256']} "
            + f"accuracy={metrics['speaker_accuracy']:.6f} "
            + f"der={metrics['diarization_error_rate']:.6f}"
        )
    alphabet_gate = spec["accepted_alphabet_gate"]
    alphabet = next(item for item in cases if item["case_id"] == alphabet_gate["case_id"])
    alphabet_delta = abs(
        alphabet["metrics"]["speaker_accuracy"] - alphabet_gate["speaker_accuracy"]
    )
    alphabet_pass = alphabet_delta <= alphabet_gate["absolute_tolerance"]
    if not alphabet_pass:
        failures.append("l1_accepted_alphabet_band_failed")
    transcript.append(
        f"{'PASS' if alphabet_pass else 'FAIL'} accepted_alphabet "
        f"actual={alphabet['metrics']['speaker_accuracy']:.6f} "
        f"target={alphabet_gate['speaker_accuracy']:.6f} "
        f"tolerance={alphabet_gate['absolute_tolerance']:.6f}"
    )
    overall = "PASS" if not failures else "FAIL"
    transcript.append(f"RESULT {overall} failures={','.join(failures) if failures else 'none'}")
    summary = {
        "accepted_alphabet_gate": {
            **alphabet_gate,
            "absolute_delta": round(alphabet_delta, 6),
            "actual_speaker_accuracy": alphabet["metrics"]["speaker_accuracy"],
            "passed": alphabet_pass,
        },
        "case_count": len(cases),
        "cases": cases,
        "failures": failures,
        "holdout": {
            "opened": False,
            "procedure_sha256": provenance["a5_holdout_procedure_sha256"],
            "status": "SEALED_FOR_A5",
        },
        "overall": overall,
        "provenance": provenance,
        "repeatability": repeatability,
        "schema": "moss-l2-stage0-l1-control-results.v1",
    }
    return summary, "\n".join(transcript) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-manifest", type=Path, default=HERE / "corpus-manifest.json")
    parser.add_argument("--candidate-config", type=Path, default=HERE / "candidate-config.json")
    parser.add_argument("--model-manifest", type=Path, default=HERE / "model-manifest.json")
    parser.add_argument("--spec", type=Path, default=HERE / "l1-control-spec.json")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--transcript-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    corpus = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate_config.read_text(encoding="utf-8"))
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    requested_ids = args.case_id or list(spec["case_ids"])
    try:
        cases = select_cases(corpus, candidate, requested_ids)
    except ControlError as exc:
        print(f"BLOCKED {exc.code}: {exc.detail}")
        print(BLOCKED_PROMISE)
        return 2
    if args.preflight_only:
        print(json.dumps({"case_ids": [case["case_id"] for case in cases], "overall": "PASS"}))
        return 0
    if args.evidence_dir is None or args.json_output is None or args.transcript_output is None:
        print("BLOCKED l1_evidence_paths_required: use --evidence-dir, --json-output, and --transcript-output")
        print(BLOCKED_PROMISE)
        return 2
    model = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    try:
        provenance = validate_control_inputs(
            spec,
            corpus,
            cases,
            model,
            corpus_manifest=args.corpus_manifest,
        )
        summary, transcript = run_controls(
            spec,
            cases,
            provenance,
            evidence_dir=args.evidence_dir,
        )
    except ControlError as exc:
        summary = {"detail": exc.detail, "error": exc.code, "overall": "FAIL"}
        transcript = f"FAIL {exc.code}: {exc.detail}\n"
    _write_json(args.json_output, summary)
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.write_text(transcript, encoding="utf-8")
    print(transcript, end="")
    return 0 if summary["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
