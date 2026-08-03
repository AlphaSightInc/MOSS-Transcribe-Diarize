#!/usr/bin/env python3
"""Validate frozen L2 Stage-0 corpus, model, runtime, and holdout boundaries."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable
import wave


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
ACCEPTED_ALPHABET_SHA256 = (
    "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759"
)
ACCEPTED_STATES = {
    "accepted_existing_provenance_zero_flags",
    "post_audit_frozen",
}
TRUTH_TOKENS = ("golden", "reference", "ground_truth", "truth_path")


class ValidationError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_declared_hash(path: Path, expected: str, kind: str) -> None:
    if not path.is_file():
        raise ValidationError(f"{kind}_missing", str(path))
    actual = sha256_file(path)
    if actual != expected:
        raise ValidationError(
            f"{kind}_hash_mismatch", f"path={path} expected={expected} actual={actual}"
        )


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def _row_fields(row: dict[str, Any]) -> tuple[float, float, str, str]:
    if "speaker_activity" in row:
        activity = row["speaker_activity"]
        transcript = row.get("transcript", {})
        return (
            float(activity["start"]),
            float(activity["end"]),
            str(activity["speaker"]),
            str(transcript.get("text", "")),
        )
    return (
        float(row["start"]),
        float(row["end"]),
        str(row["speaker"]),
        str(row.get("text", "")),
    )


def load_reference(path: Path) -> list[tuple[float, float, str, str]]:
    rows: list[tuple[float, float, str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(_row_fields(json.loads(line)))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValidationError(
                "reference_parse_failed", f"{path}:{line_number}: {exc}"
            ) from exc
    if not rows:
        raise ValidationError("reference_empty", str(path))
    return rows


def reference_findings(
    rows: Iterable[tuple[float, float, str, str]], audio_duration: float
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    previous_start = -1.0
    previous_end = -1.0
    for index, (start, end, _speaker, text) in enumerate(rows):
        if start < 0 or end <= start or end > audio_duration + 0.05:
            findings.append({"index": index, "kind": "invalid_duration", "start": start, "end": end})
        if start < previous_start or end < previous_end:
            findings.append({"index": index, "kind": "non_monotonic", "start": start, "end": end})
        if start < previous_end - 1e-6:
            findings.append({"index": index, "kind": "overlap", "start": start, "previous_end": previous_end})
        duration = end - start
        word_count = len(re.findall(r"\b[\w']+\b", text))
        if duration > 0 and word_count / duration > 8.0:
            findings.append(
                {
                    "index": index,
                    "kind": "high_word_rate",
                    "words_per_second": round(word_count / duration, 6),
                }
            )
        previous_start = start
        previous_end = end
    return findings


def validate_acoustic_support(
    reference_path: Path, evidence_path: Path, *, minimum_token_recall: float = 0.2
) -> None:
    reference = load_reference(reference_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("blind_to_reference_transcript") is not True:
        raise ValidationError("acoustic_evidence_not_blind", str(evidence_path))
    segments = [
        (
            float(row["start"]),
            float(row["end"]),
            _tokens(str(row.get("text", ""))),
        )
        for row in evidence.get("segments", [])
    ]
    for index, (start, end, _speaker, text) in enumerate(reference):
        expected_tokens = _tokens(text)
        if not expected_tokens:
            continue
        heard: set[str] = set()
        for acoustic_start, acoustic_end, acoustic_tokens in segments:
            if acoustic_end > start and acoustic_start < end:
                heard.update(acoustic_tokens)
        recall = len(expected_tokens & heard) / len(expected_tokens)
        if recall < minimum_token_recall:
            raise ValidationError(
                "reference_line_not_acoustically_supported",
                f"line={index} interval={start:.3f}-{end:.3f} token_recall={recall:.3f}",
            )


def _runtime_values(value: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            yield child_prefix, str(key)
            yield from _runtime_values(child, child_prefix)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _runtime_values(child, f"{prefix}[{index}]")
    elif isinstance(value, str):
        yield prefix, value


def audit_runtime_surface(config: dict[str, Any], candidate_source: str) -> None:
    for location, value in _runtime_values(config):
        lowered = value.lower()
        if any(token in lowered for token in TRUTH_TOKENS):
            raise ValidationError(
                "runtime_truth_path_reachable", f"location={location} value={value}"
            )
    try:
        tree = ast.parse(candidate_source)
    except SyntaxError as exc:
        raise ValidationError("runtime_candidate_parse_failed", str(exc)) from exc
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            names.append(node.value)
        if any(token in name.lower() for name in names for token in TRUTH_TOKENS):
            raise ValidationError("runtime_truth_import_reachable", ",".join(names))


def authorize_holdout_open(
    candidate_config: dict[str, Any], holdout_manifest_path: Path
) -> dict[str, Any]:
    if candidate_config.get("candidate_frozen") is not True:
        raise ValidationError("holdout_open_before_candidate_freeze", "candidate_frozen=false")
    spec_hash = candidate_config.get("candidate_spec_sha256")
    if not isinstance(spec_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", spec_hash):
        raise ValidationError("holdout_open_before_candidate_freeze", "candidate spec not frozen")
    expected = candidate_config.get("holdout_manifest_sha256")
    validate_declared_hash(holdout_manifest_path, str(expected), "holdout_manifest")
    return json.loads(holdout_manifest_path.read_text(encoding="utf-8"))


def _audio_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    except (wave.Error, EOFError) as exc:
        raise ValidationError("audio_metadata_invalid", f"{path}: {exc}") from exc


def _validate_case(case: dict[str, Any]) -> dict[str, Any]:
    audio = REPO / case["audio_path"]
    reference = REPO / case["reference_path"]
    cache = REPO / case["vector_cache_path"]
    validate_declared_hash(audio, case["audio_sha256"], "audio")
    validate_declared_hash(reference, case["reference_sha256"], "reference")
    validate_declared_hash(cache, case["vector_cache_sha256"], "vector_cache")
    duration = _audio_duration(audio)
    if abs(duration - float(case["duration_seconds"])) > 0.05:
        raise ValidationError("audio_duration_mismatch", case["case_id"])
    rows = load_reference(reference)
    findings = reference_findings(rows, duration)
    if findings != case["mechanical_findings"]:
        raise ValidationError("reference_findings_drift", case["case_id"])
    speaker_count = len({speaker for _, _, speaker, _ in rows})
    if speaker_count != int(case["speaker_count"]):
        raise ValidationError("speaker_count_mismatch", case["case_id"])
    declared = case["reference_status"]
    if case["acceptance_eligible"]:
        if declared not in ACCEPTED_STATES:
            raise ValidationError("reference_status_not_accepted", case["case_id"])
        structural = [item for item in findings if item["kind"] != "high_word_rate"]
        if structural:
            raise ValidationError(
                "acceptance_reference_structural_failure",
                f"{case['case_id']}:{json.dumps(structural, sort_keys=True)}",
            )
        if declared == "accepted_existing_provenance_zero_flags" and findings:
            raise ValidationError(
                "acceptance_reference_requires_audit",
                f"{case['case_id']}:{json.dumps(findings, sort_keys=True)}",
            )
        if duration >= 240 and declared != "post_audit_frozen":
            raise ValidationError("long_acceptance_missing_acoustic_audit", case["case_id"])
    if declared == "post_audit_frozen":
        if case["reference_sha256"] != ACCEPTED_ALPHABET_SHA256:
            raise ValidationError("post_audit_reference_hash_mismatch", case["case_id"])
        for kind in ("reference_provenance", "human_audit", "acoustic_evidence"):
            validate_declared_hash(
                REPO / case[f"{kind}_path"], case[f"{kind}_sha256"], kind
            )
        validate_acoustic_support(reference, REPO / case["acoustic_evidence_path"])
    return {
        "acceptance_eligible": bool(case["acceptance_eligible"]),
        "case_id": case["case_id"],
        "duration_seconds": round(duration, 6),
        "finding_count": len(findings),
        "findings": findings,
        "reference_status": declared,
        "speaker_count": speaker_count,
        "split": case["split"],
    }


def select_case_scope(
    cases: list[dict[str, Any]], scope: str
) -> tuple[list[dict[str, Any]], list[str]]:
    if scope == "all":
        return cases, []
    if scope != "non-holdout":
        raise ValidationError("case_scope_invalid", scope)
    return (
        [case for case in cases if case["split"] != "blind_holdout"],
        [str(case["case_id"]) for case in cases if case["split"] == "blind_holdout"],
    )


def validate_repository(args: argparse.Namespace) -> dict[str, Any]:
    corpus = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    model = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    candidate = json.loads(args.candidate_config.read_text(encoding="utf-8"))
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    validate_declared_hash(
        REPO / model["asset"]["path"], model["asset"]["sha256"], "model"
    )
    validate_declared_hash(
        REPO / model["frontend"]["source_path"],
        model["frontend"]["source_sha256"],
        "frontend",
    )
    config_hash = hashlib.sha256(
        json.dumps(model["frontend"]["config"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if config_hash != model["frontend"]["config_sha256"]:
        raise ValidationError("frontend_config_hash_mismatch", config_hash)
    actual_corpus_hash = sha256_file(args.corpus_manifest)
    if contract["corpus_manifest_hash"] != actual_corpus_hash:
        raise ValidationError(
            "launcher_corpus_pin_mismatch",
            f"pin={contract['corpus_manifest_hash']} actual={actual_corpus_hash}",
        )
    cache_spec_hash = corpus.get("cache_rebuild_spec_sha256")
    if cache_spec_hash is not None:
        cache_spec_path = REPO / corpus["cache_rebuild_spec_path"]
        validate_declared_hash(cache_spec_path, cache_spec_hash, "cache_rebuild_spec")
        cache_spec = json.loads(cache_spec_path.read_text(encoding="utf-8"))
        if cache_spec.get("model_manifest_sha256") != sha256_file(args.model_manifest):
            raise ValidationError("cache_model_manifest_pin_mismatch", str(cache_spec_path))
        planner = cache_spec.get("production_planner", {})
        validate_declared_hash(
            REPO / planner["source_path"], planner["source_sha256"], "cache_planner_source"
        )
        embedder = cache_spec.get("production_embedder", {})
        validate_declared_hash(
            REPO / embedder["frontend_source_path"],
            embedder["frontend_source_sha256"],
            "cache_frontend_source",
        )
        if embedder.get("model_sha256") != model["asset"]["sha256"]:
            raise ValidationError("cache_model_pin_mismatch", str(cache_spec_path))
        if int(cache_spec["config"]["hard_cap_samples"]) != 40000:
            raise ValidationError("cache_hard_cap_changed", str(cache_spec_path))
    holdout = REPO / corpus["holdout_manifest_path"]
    validate_declared_hash(
        holdout, candidate["holdout_manifest_sha256"], "holdout_manifest"
    )
    holdout_payload = json.loads(holdout.read_text(encoding="utf-8"))
    if holdout_payload.get("sealed") is not True or holdout_payload.get("opened_at") is not None:
        raise ValidationError("holdout_not_sealed", str(holdout))
    audit_runtime_surface(
        candidate, args.candidate_source.read_text(encoding="utf-8")
    )
    selected, skipped = select_case_scope(corpus["cases"], args.case_scope)
    cases = [_validate_case(case) for case in selected]
    accepted_metadata = [
        case for case in corpus["cases"] if case["acceptance_eligible"]
    ]
    splits = {case["split"] for case in accepted_metadata}
    if splits != {"development", "validation", "blind_holdout"}:
        raise ValidationError("acceptance_splits_incomplete", ",".join(sorted(splits)))
    return {
        "accepted_case_count": len(accepted_metadata),
        "case_scope": args.case_scope,
        "cache_rebuild_spec_sha256": cache_spec_hash,
        "cases": cases,
        "corpus_manifest_sha256": actual_corpus_hash,
        "holdout_manifest_sha256": candidate["holdout_manifest_sha256"],
        "holdout_case_files_opened": args.case_scope == "all",
        "model_sha256": model["asset"]["sha256"],
        "overall": "PASS",
        "sealed_skipped_case_ids": skipped,
        "validated_case_count": len(cases),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-manifest", type=Path, default=HERE / "corpus-manifest.json")
    parser.add_argument("--model-manifest", type=Path, default=HERE / "model-manifest.json")
    parser.add_argument("--candidate-config", type=Path, default=HERE / "candidate-config.json")
    parser.add_argument("--candidate-source", type=Path, default=HERE / "runtime_candidate_stub.py")
    parser.add_argument("--case-scope", choices=("all", "non-holdout"), default="all")
    parser.add_argument(
        "--contract", type=Path, default=REPO / "scripts/ralph-l2-afk/contract.json"
    )
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate_repository(args)
    except ValidationError as exc:
        result = {"error": exc.code, "detail": exc.detail, "overall": "FAIL"}
        status = 2
    else:
        status = 0
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
