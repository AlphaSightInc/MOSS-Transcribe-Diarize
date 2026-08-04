#!/usr/bin/env python3
"""A5 evaluator and three-arm dev/validation runner."""

from __future__ import annotations

import argparse
import ast
from dataclasses import asdict
import hashlib
import inspect
import json
from pathlib import Path
import sys
from typing import Any, Iterator, Sequence
import wave

import numpy as np


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from candidate_engine import (  # noqa: E402
    CandidateConfig,
    PcmChunk,
    RuntimeSpan,
    RuntimeUnit,
    run_joint_span_candidate,
    propose_ledger_only,
    run_continuity_candidate,
    run_span_local_weak_candidate,
    run_tape_candidate,
)
from production_cache import PlannerConfig, plan_reference  # noqa: E402
from run_l1_control import replay_case  # noqa: E402
from moss_transcribe_diarize.app.live_identity_sweep import SweepRevision  # noqa: E402
from moss_transcribe_diarize.app import speaker_identity  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    AudioFrame,
    CanonicalResult,
    LabelRevision,
    LiveIdentityPreparation,
    LiveIdentitySnapshot,
    LiveSession,
    UNATTRIBUTED_SPEAKER,
    display_speaker_label,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.live_speaker_accuracy import (  # noqa: E402
    SpeakerActivityInterval,
    load_reference_speaker_activity_jsonl,
    score_live_speaker_accuracy,
)


BLOCKED_PROMISE = "<promise>BLOCKED</promise>"


class CandidateRunError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def semantic_sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_dev_cases(
    cases: Sequence[dict[str, object]],
    requested_ids: Sequence[str],
    *,
    candidate_frozen: bool,
) -> list[dict[str, object]]:
    by_id = {str(case["case_id"]): case for case in cases}
    selected: list[dict[str, object]] = []
    for case_id in requested_ids:
        case = by_id.get(case_id)
        if case is None:
            raise CandidateRunError("candidate_case_unknown", case_id)
        if case.get("split") == "blind_holdout":
            if not candidate_frozen:
                raise CandidateRunError("candidate_holdout_before_freeze", case_id)
            raise CandidateRunError("candidate_holdout_requires_single_a5_opening", case_id)
        if not case.get("acceptance_eligible"):
            raise CandidateRunError("candidate_case_not_acceptance_eligible", case_id)
        if case.get("split") not in {"development", "validation"}:
            raise CandidateRunError("candidate_case_split_not_allowed", case_id)
        selected.append(case)
    return selected


def audit_candidate_source(path: Path = HERE / "candidate_engine.py") -> dict[str, object]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    forbidden_imports = {
        "case_registry",
        "json",
        "os",
        "pathlib",
        "production_cache",
        "wave",
    }
    forbidden_fragments = (
        "golden",
        "reference_path",
        "true_speaker",
        "truth",
        "live_speaker_accuracy",
    )
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in forbidden_imports:
                    violations.append(f"forbidden_import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in forbidden_imports or "live_speaker_accuracy" in module:
                violations.append(f"forbidden_import:{module}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            violations.append("forbidden_file_open")
    lowered = source.lower()
    for fragment in forbidden_fragments:
        if fragment in lowered:
            violations.append(f"forbidden_source_fragment:{fragment}")
    try:
        display_path = path.relative_to(REPO).as_posix()
    except ValueError:
        display_path = str(path)
    return {
        "schema": "moss-l2-stage0-candidate-source-audit.v1",
        "path": display_path,
        "sha256": sha256(path),
        "violations": sorted(set(violations)),
        "overall": "PASS" if not violations else "FAIL",
    }


def _display(canonical: str | None, canonicals: Sequence[str]) -> str:
    return UNATTRIBUTED_SPEAKER if canonical is None else display_speaker_label(canonical, canonicals)


def _span_transcript(
    span: RuntimeSpan,
    units: Sequence[RuntimeUnit],
    canonicals: Sequence[str],
) -> tuple[str, tuple[str, ...]]:
    segments: list[tuple[float, float, str, str]] = []
    for unit in units:
        for start, end in unit.intervals:
            segments.append(
                (
                    start - span.start,
                    end - span.start,
                    _display(unit.current_speaker, canonicals),
                    unit.local_speaker,
                )
            )
    segments.sort()
    transcript = "".join(
        f"[{start:g}][{speaker}]w[{end:g}]"
        for start, end, speaker, _local in segments
    )
    return transcript, tuple(local for _start, _end, _speaker, local in segments)


def _content_signature(transcript: str, sample_count: int) -> tuple[tuple[float, float, str], ...]:
    return tuple(
        (segment.start, segment.end, segment.text)
        for segment in span_segments(transcript, sample_count=sample_count)
    )


def publish_runtime_revision(
    spans: Sequence[RuntimeSpan],
    units: Sequence[RuntimeUnit],
    revision: SweepRevision,
    *,
    sample_rate: int,
) -> dict[str, object]:
    """Apply revisions through production LiveSession.revise_labels semantics."""

    canonicals = tuple(
        sorted(
            {
                speaker
                for speaker in (
                    [unit.current_speaker for unit in units]
                    + [correction.canonical_speaker for correction in revision.corrections]
                )
                if speaker is not None
            }
        )
    )
    max_span_samples = max(round((span.end - span.start) * sample_rate) for span in spans)
    session = LiveSession(max_retained_samples=max_span_samples)
    sequence = 0
    by_span: dict[int, list[RuntimeUnit]] = {}
    for unit in units:
        by_span.setdefault(unit.span_id, []).append(unit)
    local_tracks: dict[int, tuple[str, ...]] = {}
    for span in spans:
        start_sample = round(span.start * sample_rate)
        end_sample = round(span.end * sample_rate)
        sample_count = end_sample - start_sample
        if sample_count <= 0 or sample_count > 40000:
            raise CandidateRunError("candidate_publisher_span_bound_failed", str(span.span_id))
        ack = session.accept_frame(
            AudioFrame(sequence=sequence, pcm=b"\0\0" * sample_count, sample_count=sample_count)
        )
        sequence += 1
        if ack.start_sample != start_sample or ack.end_sample != end_sample:
            raise CandidateRunError("candidate_publisher_sample_grid_mismatch", str(span.span_id))
        frozen = session.freeze_until(end_sample, reason=span.reason)
        members = sorted(by_span.get(span.span_id, ()), key=lambda item: item.local_speaker)
        if not members:
            submitted = session.submit_empty_canonical(
                span_id=frozen.id,
                epoch=frozen.epoch,
                start_sample=frozen.start_sample,
                end_sample=frozen.end_sample,
            )
        else:
            transcript, track = _span_transcript(span, members, canonicals)
            local_tracks[span.span_id] = track
            base = session.snapshot().identity_snapshot
            proposed = LiveIdentitySnapshot(
                version=base.version + 1,
                canonical_speakers=canonicals,
            )
            preparation = LiveIdentityPreparation(
                span_id=frozen.id,
                epoch=frozen.epoch,
                start_sample=frozen.start_sample,
                end_sample=frozen.end_sample,
                base_snapshot_version=base.version,
                proposed_snapshot=proposed,
                relabeled_transcript=transcript,
            )
            submitted = session.submit_prepared_canonical(
                CanonicalResult(
                    span_id=frozen.id,
                    epoch=frozen.epoch,
                    start_sample=frozen.start_sample,
                    end_sample=frozen.end_sample,
                    transcript=transcript,
                    identity_preparation=preparation,
                    local_speakers=track,
                )
            )
        if not submitted.submitted:
            raise CandidateRunError(
                "candidate_publisher_commit_refused", f"{span.span_id}:{submitted.refusal}"
            )

    before = session.snapshot()
    before_commits = {commit.span_id: commit for commit in before.committed}
    outcome = session.revise_labels(
        tuple(
            LabelRevision(
                span_id=correction.span_id,
                local_speaker=correction.local_speaker,
                canonical_speaker=correction.canonical_speaker,
            )
            for correction in revision.corrections
        )
    )
    after = session.snapshot()
    after_commits = {commit.span_id: commit for commit in after.committed}
    if outcome.refusals:
        raise CandidateRunError(
            "candidate_publisher_revision_refused", json.dumps(dict(outcome.refusals), sort_keys=True)
        )

    display_to_canonical = {
        display_speaker_label(canonical, canonicals): canonical for canonical in canonicals
    }
    final_labels: dict[tuple[int, str], str | None] = {}
    for span in spans:
        track = local_tracks.get(span.span_id, ())
        if not track:
            continue
        commit = after_commits[span.span_id]
        published = commit.revised_transcript or commit.transcript
        parsed = span_segments(
            published,
            sample_count=round((span.end - span.start) * sample_rate),
        )
        if len(parsed) != len(track):
            raise CandidateRunError("candidate_publisher_track_drift", str(span.span_id))
        for local, segment in zip(track, parsed, strict=True):
            canonical = display_to_canonical.get(segment.speaker)
            key = (span.span_id, local)
            if key in final_labels and final_labels[key] != canonical:
                raise CandidateRunError("candidate_publisher_local_label_split", str(key))
            final_labels[key] = canonical

    ordered = [final_labels[(unit.span_id, unit.local_speaker)] for unit in units]
    prefix_unchanged = all(
        before_commits[key].prefix_hash == after_commits[key].prefix_hash
        for key in before_commits
    )
    bounds_unchanged = all(
        (before_commits[key].start_sample, before_commits[key].end_sample)
        == (after_commits[key].start_sample, after_commits[key].end_sample)
        for key in before_commits
    )
    content_unchanged = True
    timing_unchanged = True
    for span in spans:
        before_commit = before_commits[span.span_id]
        after_commit = after_commits[span.span_id]
        before_sig = _content_signature(
            before_commit.transcript,
            before_commit.end_sample - before_commit.start_sample,
        )
        after_sig = _content_signature(
            after_commit.revised_transcript or after_commit.transcript,
            after_commit.end_sample - after_commit.start_sample,
        )
        content_unchanged &= [item[2] for item in before_sig] == [item[2] for item in after_sig]
        timing_unchanged &= [item[:2] for item in before_sig] == [item[:2] for item in after_sig]
    return {
        "final_unit_labels": ordered,
        "outcome": asdict(outcome),
        "revision": revision.to_dict(),
        "immutability": {
            "words_unchanged": content_unchanged,
            "span_bounds_unchanged": bounds_unchanged,
            "word_timings_unchanged": timing_unchanged,
            "prefix_hashes_unchanged": prefix_unchanged,
        },
        "production_binding": {
            "publisher": "moss_transcribe_diarize.app.live_session.LiveSession.revise_labels",
            "coordinator_conversion_lines": "moss_transcribe_diarize/app/live_coordinator.py:448-456",
            "source_path": Path(inspect.getsourcefile(LiveSession.revise_labels) or "")
            .resolve()
            .relative_to(REPO)
            .as_posix(),
        },
    }


class ProductionWindowEmbedder:
    def __init__(self, embedder: object, audio_path: Path):
        self.embedder = embedder
        self.audio_path = audio_path

    def embed(self, intervals: Sequence[tuple[float, float]]) -> Sequence[float]:
        method = getattr(self.embedder, "embed")
        return method(self.audio_path, list(intervals))


def pcm_chunks(path: Path, *, hard_cap_samples: int = 40000) -> Iterator[PcmChunk]:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
            raise CandidateRunError("candidate_audio_format_mismatch", str(path))
        start = 0
        while True:
            payload = wav.readframes(hard_cap_samples)
            if not payload:
                break
            samples = np.frombuffer(payload, dtype="<i2").copy()
            yield PcmChunk(start, samples)
            start += len(samples)


def _resolve(path: object) -> Path:
    candidate = Path(str(path))
    return candidate if candidate.is_absolute() else REPO / candidate


def _planner_config(production: dict[str, object]) -> PlannerConfig:
    return PlannerConfig.from_mapping(
        {name: production[name] for name in PlannerConfig.__dataclass_fields__}
    )


def runtime_case(
    case: dict[str, object],
    l1_result: dict[str, object],
    production: dict[str, object],
) -> tuple[
    tuple[RuntimeSpan, ...],
    tuple[RuntimeUnit, ...],
    object,
    tuple[SpeakerActivityInterval, ...],
]:
    reference = load_reference_speaker_activity_jsonl(_resolve(case["reference_path"]))
    rows = [(item.start, item.end, item.speaker, "") for item in reference]
    config = _planner_config(production)
    plan = plan_reference(
        rows,
        total_samples=round(float(case["duration_seconds"]) * config.sample_rate),
        config=config,
    )
    with np.load(_resolve(case["vector_cache_path"]), allow_pickle=False) as payload:
        cache_rows = payload["rows"].astype(np.float64)
        vectors = payload["vecs"].astype(np.float32)
        vector_indexes = payload["vec_idx"].astype(np.int64)
    if len(plan.units) != len(cache_rows) or len(plan.units) != len(l1_result["final_unit_labels"]):
        raise CandidateRunError("candidate_production_frame_mismatch", str(case["case_id"]))
    indexes_by_span: dict[int, list[int]] = {}
    for index, unit in enumerate(plan.units):
        indexes_by_span.setdefault(unit.span_id, []).append(index)
    local_of: dict[int, str] = {}
    for span_id, indexes in indexes_by_span.items():
        for position, index in enumerate(sorted(indexes), start=1):
            local_of[index] = f"S{position:02d}"
    units = tuple(
        RuntimeUnit(
            span_id=unit.span_id,
            local_speaker=local_of[index],
            span_start=plan.span(unit.span_id).start_sample / config.sample_rate,
            span_end=plan.span(unit.span_id).end_sample / config.sample_rate,
            intervals=tuple((piece.start, piece.end) for piece in unit.pieces),
            current_speaker=l1_result["final_unit_labels"][index],
            duration_seconds=sum(piece.duration for piece in unit.pieces),
            vector=(
                None
                if vector_indexes[index] < 0
                else tuple(float(value) for value in vectors[vector_indexes[index]])
            ),
        )
        for index, unit in enumerate(plan.units)
    )
    spans = tuple(
        RuntimeSpan(
            span.span_id,
            span.start_sample / config.sample_rate,
            span.end_sample / config.sample_rate,
            span.reason,
        )
        for span in plan.spans
    )
    return spans, units, plan, reference


def _hypothesis(
    plan: object, labels: Sequence[str | None]
) -> tuple[SpeakerActivityInterval, ...]:
    units = getattr(plan, "units")
    return tuple(
        SpeakerActivityInterval(piece.start, piece.end, label)
        for unit, label in zip(units, labels, strict=True)
        if label is not None
        for piece in unit.pieces
    )


def _arm_result(
    *,
    name: str,
    spans: Sequence[RuntimeSpan],
    units: Sequence[RuntimeUnit],
    plan: object,
    reference: Sequence[SpeakerActivityInterval],
    proposal: object,
    l1_result: dict[str, object],
    sample_rate: int,
) -> dict[str, object]:
    revision = getattr(proposal, "revision")
    published = publish_runtime_revision(spans, units, revision, sample_rate=sample_rate)
    labels = published["final_unit_labels"]
    metrics = score_live_speaker_accuracy(reference, _hypothesis(plan, labels))
    mapping = l1_result["metrics"]["speaker_mapping"]
    denominator = 0.0
    recovered = 0.0
    target_units: list[dict[str, object]] = []
    for index, (planned, unit, label) in enumerate(
        zip(getattr(plan, "units"), units, labels, strict=True)
    ):
        speaker = getattr(plan, "speaker_labels")[planned.true_speaker]
        expected = mapping.get(speaker)
        l1_incorrect = unit.current_speaker != expected
        category = None
        if l1_incorrect and unit.vector is None:
            category = "sub_floor"
        elif l1_incorrect and unit.current_speaker is None:
            category = "weak_vector"
        if category is None:
            continue
        denominator += unit.duration_seconds
        correct = label == expected
        if correct:
            recovered += unit.duration_seconds
        target_units.append(
            {
                "unit_index": index,
                "span_id": unit.span_id,
                "local_speaker": unit.local_speaker,
                "category": category,
                "duration_seconds": round(unit.duration_seconds, 6),
                "l1_speaker": unit.current_speaker,
                "candidate_speaker": label,
                "expected_via_immutable_l1_mapping": expected,
                "recovered": correct,
            }
        )
    return {
        "arm": name,
        "metrics": metrics,
        "final_unit_labels": labels,
        "proposal": {
            "revision": revision.to_dict(),
            "correction_evidence": list(getattr(proposal, "correction_evidence")),
            "changed_duration_fraction": getattr(proposal, "changed_duration_fraction"),
            "trace": getattr(proposal, "trace"),
        },
        "publisher": published,
        "target_recovery": {
            "denominator_seconds": round(denominator, 6),
            "recovered_seconds": round(recovered, 6),
            "recovery_fraction": round(recovered / denominator if denominator else 1.0, 6),
            "units": target_units,
        },
    }


def _empty_proposal(unit_count: int, span_count: int) -> object:
    from candidate_engine import ArmProposal

    return ArmProposal(
        revision=SweepRevision(swept_spans=span_count, swept_units=unit_count),
        correction_evidence=(),
        changed_duration_fraction=0.0,
        trace={"arm": "l1", "status": "production_l1_no_additional_revision"},
    )


def padding_negative_control() -> dict[str, object]:
    reference = (SpeakerActivityInterval(0.1, 0.9, "A"),)
    baseline = score_live_speaker_accuracy(
        reference, (SpeakerActivityInterval(0.1, 0.9, "speaker-0001"),)
    )
    padded = score_live_speaker_accuracy(
        reference, (SpeakerActivityInterval(0.0, 1.0, "speaker-0001"),)
    )
    passed = (
        padded["false_positive_speaker_seconds"] > baseline["false_positive_speaker_seconds"]
        and padded["diarization_error_rate"] > baseline["diarization_error_rate"]
    )
    return {
        "overall": "PASS" if passed else "FAIL",
        "baseline": baseline,
        "padded": padded,
        "reason": "invented boundary activity is observable and penalized",
    }


def production_bindings(model_path: Path) -> dict[str, object]:
    embed_source = Path(inspect.getsourcefile(speaker_identity._OnnxWeSpeakerEmbedder) or "").resolve()
    sweep_source = Path(inspect.getsourcefile(SweepRevision) or "").resolve()
    publisher_source = Path(inspect.getsourcefile(LiveSession.revise_labels) or "").resolve()
    for path in (embed_source, sweep_source, publisher_source):
        if REPO not in path.parents:
            raise CandidateRunError("candidate_production_binding_outside_worktree", str(path))
    return {
        "embedder": "moss_transcribe_diarize.app.speaker_identity._OnnxWeSpeakerEmbedder",
        "embedder_source_path": embed_source.relative_to(REPO).as_posix(),
        "embedder_source_sha256": sha256(embed_source),
        "model_path": model_path.relative_to(REPO).as_posix(),
        "model_sha256": sha256(model_path),
        "revision": "moss_transcribe_diarize.app.live_identity_sweep.SweepRevision",
        "revision_source_path": sweep_source.relative_to(REPO).as_posix(),
        "revision_source_sha256": sha256(sweep_source),
        "publisher": "moss_transcribe_diarize.app.live_session.LiveSession.revise_labels",
        "publisher_source_path": publisher_source.relative_to(REPO).as_posix(),
        "publisher_source_sha256": sha256(publisher_source),
    }


def evaluate_gates(cases: Sequence[dict[str, object]], spec: dict[str, object]) -> dict[str, object]:
    total_reference = sum(float(case["arms"]["l1_control"]["metrics"]["reference_seconds"]) for case in cases)
    target_scores = {}
    for arm in ("l1_control", "ledger_only_control", "tape_candidate"):
        matched = sum(float(case["arms"][arm]["metrics"]["matched_speaker_seconds"]) for case in cases)
        target_scores[arm] = matched / total_reference
    requirements = spec["development_validation_gates"]
    minimum_gain = float(requirements["minimum_target_subset_gain_over_each_control_pp"])
    gain_l1 = (target_scores["tape_candidate"] - target_scores["l1_control"]) * 100.0
    gain_ledger = (target_scores["tape_candidate"] - target_scores["ledger_only_control"]) * 100.0
    denominator = sum(float(case["arms"]["tape_candidate"]["target_recovery"]["denominator_seconds"]) for case in cases)
    recovered = sum(float(case["arms"]["tape_candidate"]["target_recovery"]["recovered_seconds"]) for case in cases)
    recovery_fraction = recovered / denominator if denominator else 1.0
    validation_regressions = {
        str(case["case_id"]): (
            float(case["arms"]["tape_candidate"]["metrics"]["speaker_accuracy"])
            - float(case["arms"]["l1_control"]["metrics"]["speaker_accuracy"])
        ) * 100.0
        for case in cases
        if case["split"] == "validation"
    }
    fp_der = {
        str(case["case_id"]): {
            "fp_delta_seconds": float(case["arms"]["tape_candidate"]["metrics"]["false_positive_speaker_seconds"])
            - float(case["arms"]["l1_control"]["metrics"]["false_positive_speaker_seconds"]),
            "der_delta": float(case["arms"]["tape_candidate"]["metrics"]["diarization_error_rate"])
            - float(case["arms"]["l1_control"]["metrics"]["diarization_error_rate"]),
        }
        for case in cases
    }
    two_sided = all(
        not case["arms"]["l1_control"]["metrics"]["two_sided_mapping"]
        or case["arms"]["tape_candidate"]["metrics"]["two_sided_mapping"]
        for case in cases
    )
    evidence_complete = all(
        len(case["arms"][arm]["proposal"]["revision"]["corrections"])
        == len(case["arms"][arm]["proposal"]["correction_evidence"])
        and all(
            "score_delta" in item and "changed_duration_fraction" in item
            for item in case["arms"][arm]["proposal"]["correction_evidence"]
        )
        for case in cases
        for arm in ("ledger_only_control", "tape_candidate")
    )
    gates = [
        {
            "gate": "tape_beats_l1_target_subset_pp",
            "actual": round(gain_l1, 6),
            "limit": minimum_gain,
            "pass": gain_l1 >= minimum_gain,
        },
        {
            "gate": "tape_beats_ledger_target_subset_pp",
            "actual": round(gain_ledger, 6),
            "limit": minimum_gain,
            "pass": gain_ledger >= minimum_gain,
        },
        {
            "gate": "unreachable_seconds_recovery_fraction",
            "actual": round(recovery_fraction, 6),
            "limit": float(requirements["minimum_recovery_fraction"]),
            "pass": recovery_fraction >= float(requirements["minimum_recovery_fraction"]),
        },
        {
            "gate": "validation_case_regression_pp",
            "actual": {key: round(value, 6) for key, value in validation_regressions.items()},
            "limit": -float(requirements["validation_case_max_regression_pp"]),
            "pass": all(value >= -float(requirements["validation_case_max_regression_pp"]) for value in validation_regressions.values()),
        },
        {
            "gate": "fp_speaker_seconds_and_der_not_worse",
            "actual": fp_der,
            "limit": 0.0,
            "pass": all(value["fp_delta_seconds"] <= 1e-6 and value["der_delta"] <= 1e-6 for value in fp_der.values()),
        },
        {
            "gate": "two_sided_mapping_preserved",
            "actual": two_sided,
            "limit": True,
            "pass": two_sided,
        },
        {
            "gate": "correction_evidence_complete",
            "actual": evidence_complete,
            "limit": True,
            "pass": evidence_complete,
        },
    ]
    return {
        "target_subset_scores": {key: round(value, 6) for key, value in target_scores.items()},
        "recovery": {
            "denominator_seconds": round(denominator, 6),
            "recovered_seconds": round(recovered, 6),
            "fraction": round(recovery_fraction, 6),
        },
        "gates": gates,
        "overall": "PASS" if all(gate["pass"] for gate in gates) else "FAIL",
    }


def run_dev_validation(
    *,
    corpus_path: Path,
    candidate_config_path: Path,
    family_path: Path,
    l1_spec_path: Path,
    model_manifest_path: Path,
    evidence_dir: Path,
) -> dict[str, object]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    candidate_config = json.loads(candidate_config_path.read_text(encoding="utf-8"))
    family = json.loads(family_path.read_text(encoding="utf-8"))
    l1_spec = json.loads(l1_spec_path.read_text(encoding="utf-8"))
    model_manifest = json.loads(model_manifest_path.read_text(encoding="utf-8"))
    if candidate_config.get("candidate_frozen"):
        raise CandidateRunError("candidate_dev_run_after_freeze")
    if family["holdout"]["opened"]:
        raise CandidateRunError("candidate_dev_spec_claims_holdout_open")
    selected = select_dev_cases(
        corpus["cases"], l1_spec["case_ids"], candidate_frozen=False
    )
    source_audit = audit_candidate_source()
    if source_audit["overall"] != "PASS":
        raise CandidateRunError("candidate_source_audit_failed", json.dumps(source_audit))
    model_path = _resolve(model_manifest["asset"]["path"])
    if sha256(model_path) != model_manifest["asset"]["sha256"]:
        raise CandidateRunError("candidate_model_hash_mismatch")
    bindings = production_bindings(model_path)
    config = CandidateConfig.from_mapping(family["candidate_family"])
    embedder = speaker_identity._OnnxWeSpeakerEmbedder(model_path, device="cpu")
    cases: list[dict[str, object]] = []
    evidence_dir = evidence_dir.resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for case in selected:
        l1 = replay_case(case, l1_spec["production_config"])
        a2_path = HERE / f"evidence/a2-l1-renewed-fixed-runs/a2-l1-{case['case_id']}-run1.json"
        a2 = json.loads(a2_path.read_text(encoding="utf-8"))
        l1_hash = semantic_sha256(l1)
        if l1_hash != a2["semantic_sha256"]:
            raise CandidateRunError("candidate_l1_a2_semantic_drift", str(case["case_id"]))
        spans, units, plan, reference = runtime_case(case, l1, l1_spec["production_config"])
        l1_proposal = _empty_proposal(len(units), len(spans))
        ledger_proposal = propose_ledger_only(units, config)
        chunks = pcm_chunks(_resolve(case["audio_path"]), hard_cap_samples=40000)
        family_id = str(family["candidate_family"]["family_id"])
        if family_id == "energy-vad-overlap-wespeaker-ahc-v1":
            candidate_runner = run_tape_candidate
        elif family_id == "energy-vad-overlap-wespeaker-continuity-rescue-v2":
            candidate_runner = run_continuity_candidate
        elif family_id == "energy-vad-overlap-wespeaker-span-local-weak-rescue-v3":
            candidate_runner = run_span_local_weak_candidate
        elif family_id == "energy-vad-overlap-wespeaker-joint-span-rescue-v4":
            candidate_runner = run_joint_span_candidate
        else:
            raise CandidateRunError("candidate_family_unknown", family_id)
        tape_proposal = candidate_runner(
            units,
            chunks,
            duration_seconds=float(case["duration_seconds"]),
            sample_rate=int(l1_spec["production_config"]["sample_rate"]),
            embedder=ProductionWindowEmbedder(embedder, _resolve(case["audio_path"])),
            config=config,
        )
        arms = {
            "l1_control": _arm_result(
                name="l1_control", spans=spans, units=units, plan=plan,
                reference=reference, proposal=l1_proposal, l1_result=l1,
                sample_rate=int(l1_spec["production_config"]["sample_rate"]),
            ),
            "ledger_only_control": _arm_result(
                name="ledger_only_control", spans=spans, units=units, plan=plan,
                reference=reference, proposal=ledger_proposal, l1_result=l1,
                sample_rate=int(l1_spec["production_config"]["sample_rate"]),
            ),
            "tape_candidate": _arm_result(
                name="tape_candidate", spans=spans, units=units, plan=plan,
                reference=reference, proposal=tape_proposal, l1_result=l1,
                sample_rate=int(l1_spec["production_config"]["sample_rate"]),
            ),
        }
        case_result = {
            "schema": "moss-l2-stage0-a5-case-result.v1",
            "case_id": case["case_id"],
            "split": case["split"],
            "frame": {
                "planner": "production_endpoint_policy",
                "audio_sha256": case["audio_sha256"],
                "reference_sha256": case["reference_sha256"],
                "vector_cache_sha256": case["vector_cache_sha256"],
                "span_count": len(spans),
                "unit_count": len(units),
            },
            "l1_a2_semantic_sha256": l1_hash,
            "arms": arms,
        }
        path = evidence_dir / f"a5-{case['case_id']}.json"
        path.write_text(json.dumps(case_result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        cases.append({**case_result, "raw_path": path.relative_to(REPO).as_posix(), "raw_sha256": sha256(path)})
        print(
            f"case={case['case_id']} l1={arms['l1_control']['metrics']['speaker_accuracy']:.6f} "
            f"ledger={arms['ledger_only_control']['metrics']['speaker_accuracy']:.6f} "
            f"tape={arms['tape_candidate']['metrics']['speaker_accuracy']:.6f} "
            f"recovered={arms['tape_candidate']['target_recovery']['recovered_seconds']:.6f}"
        )
    gates = evaluate_gates(cases, family)
    padding = padding_negative_control()
    if padding["overall"] != "PASS":
        raise CandidateRunError("candidate_padding_negative_control_failed")
    result = {
        "schema": "moss-l2-stage0-a5-dev-validation.v1",
        "overall": gates["overall"],
        "candidate_ready_to_freeze": gates["overall"] == "PASS",
        "candidate_frozen": False,
        "holdout_opened": False,
        "case_count": len(cases),
        "cases": [
            {
                "case_id": case["case_id"],
                "split": case["split"],
                "raw_path": case["raw_path"],
                "raw_sha256": case["raw_sha256"],
                "metrics": {arm: case["arms"][arm]["metrics"] for arm in case["arms"]},
                "changed_duration_fraction": {
                    arm: case["arms"][arm]["proposal"]["changed_duration_fraction"]
                    for arm in case["arms"]
                },
            }
            for case in cases
        ],
        "gate_evaluation": gates,
        "padding_negative_control": padding,
        "source_audit": source_audit,
        "production_bindings": bindings,
        "pins": {
            "corpus_manifest_sha256": sha256(corpus_path),
            "candidate_config_sha256": sha256(candidate_config_path),
            "candidate_family_sha256": sha256(family_path),
            "l1_spec_sha256": sha256(l1_spec_path),
            "model_manifest_sha256": sha256(model_manifest_path),
            "a5_holdout_procedure_sha256": sha256(HERE / "a5-holdout-procedure.json"),
        },
        "iteration": family["candidate_family"]["iteration"],
        "iteration_budget": family["iteration_budget"],
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-manifest", type=Path, default=HERE / "corpus-manifest.json")
    parser.add_argument("--candidate-config", type=Path, default=HERE / "candidate-config.json")
    parser.add_argument("--candidate-family", type=Path, default=HERE / "a5-dev-candidate-family-v1.json")
    parser.add_argument("--l1-spec", type=Path, default=HERE / "l1-control-spec.json")
    parser.add_argument("--model-manifest", type=Path, default=HERE / "model-manifest.json")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--transcript-output", type=Path)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audit = audit_candidate_source()
    if audit["overall"] != "PASS":
        print(f"BLOCKED candidate_source_audit_failed: {audit['violations']}")
        print(BLOCKED_PROMISE)
        return 2
    if args.preflight_only:
        print(json.dumps(audit, sort_keys=True))
        return 0
    if args.case_id:
        corpus = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate_config.read_text(encoding="utf-8"))
        try:
            select_dev_cases(
                corpus["cases"], args.case_id,
                candidate_frozen=bool(candidate.get("candidate_frozen")),
            )
        except CandidateRunError as exc:
            print(f"BLOCKED {exc.code}: {exc.detail}")
            print(BLOCKED_PROMISE)
            return 2
        print("BLOCKED candidate_case_subset_runs_forbidden: run frozen six-case dev scope")
        print(BLOCKED_PROMISE)
        return 2
    if args.evidence_dir is None or args.json_output is None or args.transcript_output is None:
        print("BLOCKED candidate_evidence_paths_required")
        print(BLOCKED_PROMISE)
        return 2
    try:
        result = run_dev_validation(
            corpus_path=args.corpus_manifest,
            candidate_config_path=args.candidate_config,
            family_path=args.candidate_family,
            l1_spec_path=args.l1_spec,
            model_manifest_path=args.model_manifest,
            evidence_dir=args.evidence_dir,
        )
    except CandidateRunError as exc:
        print(f"BLOCKED {exc.code}: {exc.detail}")
        print(BLOCKED_PROMISE)
        return 2
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        f"A5 DEV/VALIDATION RESULT: {result['overall']}",
        "holdout=SEALED",
        f"candidate_ready_to_freeze={str(result['candidate_ready_to_freeze']).lower()}",
    ]
    for gate in result["gate_evaluation"]["gates"]:
        lines.append(
            f"gate={gate['gate']} actual={gate['actual']} limit={gate['limit']} "
            f"verdict={'PASS' if gate['pass'] else 'FAIL'}"
        )
    args.transcript_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        f"overall={result['overall']} candidate_ready_to_freeze={result['candidate_ready_to_freeze']} "
        f"output={args.json_output}"
    )
    return 0 if result["overall"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
