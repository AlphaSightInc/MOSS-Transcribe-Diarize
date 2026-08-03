#!/usr/bin/env python3
"""Version-rebuild A1-frozen derived caches without opening holdout early."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import wave
from typing import Any, Callable

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.speaker_identity import (  # noqa: E402
    PINNED_TIER_B_ASSET_SPEC,
    WeSpeakerResNet152LmAdapter,
)
from production_cache import (  # noqa: E402
    PlannerConfig,
    build_cache,
    plan_reference,
    production_planner_bindings,
    sha256_file,
    validate_cache,
)
from validate_inputs import load_reference  # noqa: E402


CACHE_VERSION = "cache-v2-production-endpoint"


def select_scope(
    corpus: dict[str, Any], scope: str, *, candidate: dict[str, Any], a5_opening: bool = False
) -> tuple[list[dict[str, Any]], list[str]]:
    if scope == "non-holdout":
        selected = [case for case in corpus["cases"] if case["split"] != "blind_holdout"]
        excluded = [str(case["case_id"]) for case in corpus["cases"] if case["split"] == "blind_holdout"]
        return selected, excluded
    if scope != "holdout":
        raise RuntimeError(f"cache_scope_invalid:{scope}")
    if candidate.get("candidate_frozen") is not True or not a5_opening:
        raise RuntimeError("cache_holdout_before_a5_opening")
    return (
        [case for case in corpus["cases"] if case["split"] == "blind_holdout"],
        [str(case["case_id"]) for case in corpus["cases"] if case["split"] != "blind_holdout"],
    )


def _resolve(value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else REPO / path


def _repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def _audio_samples(path: Path, sample_rate: int) -> int:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != sample_rate:
            raise RuntimeError(f"cache_audio_sample_rate_mismatch:{path}:{handle.getframerate()}")
        return handle.getnframes()


def _old_unit_count(path: Path) -> int:
    with np.load(path, allow_pickle=False) as payload:
        return len(payload["rows"])


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def _validate_spec(
    spec: dict[str, Any], model: dict[str, Any], *, model_manifest_path: Path
) -> PlannerConfig:
    if sha256_file(model_manifest_path) != spec["model_manifest_sha256"]:
        raise RuntimeError("cache_model_manifest_hash_mismatch")
    model_path = _resolve(model["asset"]["path"])
    if sha256_file(model_path) != model["asset"]["sha256"]:
        raise RuntimeError("cache_model_hash_mismatch")
    if model["asset"]["sha256"] != PINNED_TIER_B_ASSET_SPEC.state_sha256:
        raise RuntimeError("cache_model_not_production_pin")
    frontend_path = _resolve(model["frontend"]["source_path"])
    if sha256_file(frontend_path) != model["frontend"]["source_sha256"]:
        raise RuntimeError("cache_frontend_hash_mismatch")
    bindings = production_planner_bindings()
    if bindings != spec["production_planner"]:
        raise RuntimeError("cache_production_planner_pin_mismatch")
    expected_embedder = {
        "binding": "moss_transcribe_diarize.app.speaker_identity.WeSpeakerResNet152LmAdapter",
        "frontend_source_path": model["frontend"]["source_path"],
        "frontend_source_sha256": model["frontend"]["source_sha256"],
        "model_sha256": model["asset"]["sha256"],
    }
    if spec["production_embedder"] != expected_embedder:
        raise RuntimeError("cache_production_embedder_pin_mismatch")
    config = PlannerConfig.from_mapping(spec["config"])
    if config.hard_cap_samples != 40000:
        raise RuntimeError("cache_hard_cap_changed")
    if config.sample_rate != model["frontend"]["config"]["sample_rate"]:
        raise RuntimeError("cache_sample_rate_drift")
    if config.min_evidence_samples != model["frontend"]["config"]["min_evidence_samples"]:
        raise RuntimeError("cache_evidence_floor_drift")
    return config


def rebuild(
    *,
    corpus_path: Path,
    model_path: Path,
    candidate_path: Path,
    spec_path: Path,
    output_root: Path,
    audit_output: Path,
    scope: str,
    a5_opening: bool,
    apply_manifest: bool,
    event: Callable[[str], None] = print,
) -> dict[str, Any]:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    model = json.loads(model_path.read_text(encoding="utf-8"))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    selected, excluded = select_scope(corpus, scope, candidate=candidate, a5_opening=a5_opening)
    config = _validate_spec(spec, model, model_manifest_path=model_path)
    embedder = WeSpeakerResNet152LmAdapter(_resolve(model["asset"]["path"]))
    preflight = embedder.preflight()
    if not preflight.available:
        raise RuntimeError(f"cache_production_embedder_unavailable:{preflight.reason}")

    updated_by_id: dict[str, tuple[str, str]] = {}
    audits: list[dict[str, Any]] = []
    for index, case in enumerate(selected, 1):
        case_id = str(case["case_id"])
        audio_path = _resolve(case["audio_path"])
        reference_path = _resolve(case["reference_path"])
        old_cache_path = _resolve(case["vector_cache_path"])
        if sha256_file(audio_path) != case["audio_sha256"]:
            raise RuntimeError(f"cache_audio_hash_mismatch:{case_id}")
        if sha256_file(reference_path) != case["reference_sha256"]:
            raise RuntimeError(f"cache_reference_hash_mismatch:{case_id}")
        if sha256_file(old_cache_path) != case["vector_cache_sha256"]:
            raise RuntimeError(f"cache_old_hash_mismatch:{case_id}")
        total_samples = _audio_samples(audio_path, config.sample_rate)
        plan = plan_reference(load_reference(reference_path), total_samples=total_samples, config=config)
        target = output_root / case_id / "harness_cache.npz"
        event(
            f"REBUILD {index}/{len(selected)} {case_id} old_units={_old_unit_count(old_cache_path)} "
            f"planned_units={len(plan.units)}"
        )
        stats = build_cache(
            plan,
            audio_path=audio_path,
            output_path=target,
            embedder=embedder,
            config=config,
            expected_embedding_dimension=int(model["frontend"]["config"]["embedding_dimension"]),
        )
        fidelity = validate_cache(target, plan, config=config)
        if fidelity["self_replan"] != "PASS":
            raise RuntimeError(f"cache_self_replan_mismatch:{case_id}")
        old_count = _old_unit_count(old_cache_path)
        new_hash = sha256_file(target)
        updated_by_id[case_id] = (_repo_path(target), new_hash)
        audits.append(
            {
                "acceptance_eligible": bool(case["acceptance_eligible"]),
                "audio_sha256": case["audio_sha256"],
                "case_id": case_id,
                "new_cache_path": _repo_path(target),
                "new_cache_sha256": new_hash,
                "new_unit_count": len(plan.units),
                "old_cache_path": case["vector_cache_path"],
                "old_cache_sha256": case["vector_cache_sha256"],
                "old_unit_count": old_count,
                "planned_minus_cached_units": len(plan.units) - old_count,
                "reference_sha256": case["reference_sha256"],
                "self_replan": fidelity,
                "split": case["split"],
                **stats,
            }
        )
        event(f"PASS {case_id} new_sha256={new_hash} self_replan=PASS")

    audit = {
        "cache_version": CACHE_VERSION,
        "cases": audits,
        "excluded_case_ids": excluded,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_corpus_manifest_sha256": sha256_file(corpus_path),
        "model_sha256": model["asset"]["sha256"],
        "overall": "PASS",
        "production_embedder": {
            "binding": "moss_transcribe_diarize.app.speaker_identity.WeSpeakerResNet152LmAdapter",
            "frontend_source_sha256": model["frontend"]["source_sha256"],
            "preflight": preflight.descriptor,
        },
        "production_planner": production_planner_bindings(),
        "schema": "moss-l2-stage0-cache-provenance-audit.v1",
        "scope": scope,
        "selected_case_count": len(selected),
        "spec_sha256": sha256_file(spec_path),
    }
    _write_json(audit_output, audit)
    if apply_manifest:
        for case in corpus["cases"]:
            replacement = updated_by_id.get(str(case["case_id"]))
            if replacement is None:
                continue
            case["vector_cache_path"], case["vector_cache_sha256"] = replacement
            case["vector_cache_version"] = CACHE_VERSION
        corpus["cache_rebuild_spec_path"] = _repo_path(spec_path)
        corpus["cache_rebuild_spec_sha256"] = sha256_file(spec_path)
        _write_json(corpus_path, corpus)
    return audit


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-manifest", type=Path, default=HERE / "corpus-manifest.json")
    parser.add_argument("--model-manifest", type=Path, default=HERE / "model-manifest.json")
    parser.add_argument("--candidate-config", type=Path, default=HERE / "candidate-config.json")
    parser.add_argument("--spec", type=Path, default=HERE / "cache-rebuild-spec.json")
    parser.add_argument("--output-root", type=Path, default=HERE / "data" / CACHE_VERSION)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--transcript-output", type=Path, required=True)
    parser.add_argument("--scope", choices=("non-holdout", "holdout"), default="non-holdout")
    parser.add_argument("--a5-opening-session", action="store_true")
    parser.add_argument("--apply-manifest", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    transcript: list[str] = []

    def event(message: str) -> None:
        transcript.append(message)
        print(message, flush=True)

    try:
        audit = rebuild(
            corpus_path=args.corpus_manifest,
            model_path=args.model_manifest,
            candidate_path=args.candidate_config,
            spec_path=args.spec,
            output_root=args.output_root,
            audit_output=args.audit_output,
            scope=args.scope,
            a5_opening=args.a5_opening_session,
            apply_manifest=args.apply_manifest,
            event=event,
        )
    except Exception as exc:
        event(f"BLOCKED {exc.__class__.__name__}:{exc}")
        event("<promise>BLOCKED</promise>")
        _write_json(
            args.audit_output,
            {
                "error": str(exc),
                "error_type": exc.__class__.__name__,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "overall": "BLOCKED",
                "scope": args.scope,
            },
        )
        args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
        args.transcript_output.write_text("\n".join(transcript) + "\n", encoding="utf-8")
        return 2
    event(json.dumps({"case_count": len(audit["cases"]), "overall": audit["overall"]}, sort_keys=True))
    args.transcript_output.parent.mkdir(parents=True, exist_ok=True)
    args.transcript_output.write_text("\n".join(transcript) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
