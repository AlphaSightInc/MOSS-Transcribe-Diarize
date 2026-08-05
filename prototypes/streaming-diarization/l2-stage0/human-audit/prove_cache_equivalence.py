#!/usr/bin/env python3
"""Rebuild word-edited references and prove cache arrays remain byte-identical."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import wave
from typing import Any

import numpy as np

HERE = Path(__file__).resolve().parent
STAGE0 = HERE.parent
REPO = STAGE0.parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(STAGE0))

from moss_transcribe_diarize.app.speaker_identity import (  # noqa: E402
    WeSpeakerResNet152LmAdapter,
)
from production_cache import build_cache, plan_reference, sha256_file, validate_cache  # noqa: E402
from rebuild_caches import _audio_samples, _resolve, _validate_spec  # noqa: E402
from validate_inputs import load_reference  # noqa: E402


CASE_IDS = ("5m-acquired-coca-cola", "5m-acquired-rolex")
ARRAY_FIELDS = ("rows", "vec_idx", "vecs", "span_bounds", "span_reasons")


def _without_text(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_text(child)
            for key, child in value.items()
            if key != "text"
        }
    if isinstance(value, list):
        return [_without_text(child) for child in value]
    return value


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _text(value: dict[str, Any]) -> str:
    if "text" in value:
        return str(value["text"])
    return str(value.get("transcript", {}).get("text", ""))


def _word_rate(value: dict[str, Any]) -> tuple[int, float]:
    activity = value.get("speaker_activity", value)
    duration = float(activity["end"]) - float(activity["start"])
    word_count = len(re.findall(r"\b[\w']+\b", _text(value)))
    return word_count, round(word_count / duration, 6)


def _array_bytes_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def prove(
    *,
    corpus_path: Path,
    model_path: Path,
    spec_path: Path,
    output_root: Path,
    json_output: Path,
) -> dict[str, Any]:
    if json_output.exists() or output_root.exists():
        raise RuntimeError("cache_equivalence_output_exists")
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    model = json.loads(model_path.read_text(encoding="utf-8"))
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    config = _validate_spec(spec, model, model_manifest_path=model_path)
    embedder = WeSpeakerResNet152LmAdapter(_resolve(model["asset"]["path"]))
    preflight = embedder.preflight()
    if not preflight.available:
        raise RuntimeError(f"cache_production_embedder_unavailable:{preflight.reason}")
    by_id = {str(case["case_id"]): case for case in corpus["cases"]}
    results: list[dict[str, Any]] = []
    for case_id in CASE_IDS:
        case = by_id[case_id]
        superseded = case.get("superseded_reference")
        if not isinstance(superseded, dict):
            raise RuntimeError(f"cache_equivalence_superseded_reference_missing:{case_id}")
        old_reference = _resolve(superseded["path"])
        new_reference = _resolve(case["reference_path"])
        if sha256_file(old_reference) != superseded["sha256"]:
            raise RuntimeError(f"cache_equivalence_old_reference_hash_mismatch:{case_id}")
        if sha256_file(new_reference) != case["reference_sha256"]:
            raise RuntimeError(f"cache_equivalence_new_reference_hash_mismatch:{case_id}")
        old_rows = _jsonl(old_reference)
        new_rows = _jsonl(new_reference)
        if len(old_rows) != len(new_rows):
            raise RuntimeError(f"cache_equivalence_reference_row_count_changed:{case_id}")
        changed_lines: list[dict[str, Any]] = []
        for line_number, (old_row, new_row) in enumerate(zip(old_rows, new_rows, strict=True), 1):
            if _without_text(old_row) != _without_text(new_row):
                raise RuntimeError(
                    f"cache_equivalence_non_text_reference_change:{case_id}:{line_number}"
                )
            if old_row != new_row:
                old_word_count, old_words_per_second = _word_rate(old_row)
                new_word_count, new_words_per_second = _word_rate(new_row)
                changed_lines.append(
                    {
                        "line_number": line_number,
                        "new_word_count": new_word_count,
                        "new_text": _text(new_row),
                        "new_words_per_second": new_words_per_second,
                        "old_word_count": old_word_count,
                        "old_text": _text(old_row),
                        "old_words_per_second": old_words_per_second,
                        "zero_based_index": line_number - 1,
                    }
                )
        audio = _resolve(case["audio_path"])
        old_cache = _resolve(case["vector_cache_path"])
        if sha256_file(audio) != case["audio_sha256"]:
            raise RuntimeError(f"cache_equivalence_audio_hash_mismatch:{case_id}")
        if sha256_file(old_cache) != case["vector_cache_sha256"]:
            raise RuntimeError(f"cache_equivalence_old_cache_hash_mismatch:{case_id}")
        plan = plan_reference(
            load_reference(new_reference),
            total_samples=_audio_samples(audio, config.sample_rate),
            config=config,
        )
        rebuilt = output_root / case_id / "harness_cache.npz"
        stats = build_cache(
            plan,
            audio_path=audio,
            output_path=rebuilt,
            embedder=embedder,
            config=config,
            expected_embedding_dimension=int(model["frontend"]["config"]["embedding_dimension"]),
        )
        self_replan = validate_cache(rebuilt, plan, config=config)
        field_results: dict[str, Any] = {}
        with np.load(old_cache, allow_pickle=False) as old_payload, np.load(
            rebuilt, allow_pickle=False
        ) as new_payload:
            if tuple(old_payload.files) != ARRAY_FIELDS or tuple(new_payload.files) != ARRAY_FIELDS:
                raise RuntimeError(f"cache_equivalence_schema_changed:{case_id}")
            for field in ARRAY_FIELDS:
                old_array = old_payload[field]
                new_array = new_payload[field]
                equal = (
                    old_array.dtype == new_array.dtype
                    and old_array.shape == new_array.shape
                    and np.array_equal(old_array, new_array)
                    and _array_bytes_sha256(old_array) == _array_bytes_sha256(new_array)
                )
                field_results[field] = {
                    "array_equal": bool(equal),
                    "current_bytes_sha256": _array_bytes_sha256(old_array),
                    "dtype": str(old_array.dtype),
                    "rebuilt_bytes_sha256": _array_bytes_sha256(new_array),
                    "shape": list(old_array.shape),
                }
                if not equal:
                    raise RuntimeError(f"cache_equivalence_array_mismatch:{case_id}:{field}")
        results.append(
            {
                "cache_arrays": field_results,
                "case_id": case_id,
                "current_cache_path": case["vector_cache_path"],
                "current_cache_sha256": case["vector_cache_sha256"],
                "new_reference_path": case["reference_path"],
                "new_reference_sha256": case["reference_sha256"],
                "only_text_changed": True,
                "rebuilt_cache_path": rebuilt.resolve().relative_to(REPO.resolve()).as_posix(),
                "rebuilt_cache_sha256": sha256_file(rebuilt),
                "reference_changed_lines": changed_lines,
                "self_replan": self_replan,
                "stats": stats,
                "superseded_reference": superseded,
                "text_carrying_cache_fields": [],
                "unit_bounds_byte_identical": field_results["rows"]["array_equal"]
                and field_results["span_bounds"]["array_equal"],
                "vectors_byte_identical": field_results["vecs"]["array_equal"],
            }
        )
    result = {
        "cases": results,
        "corpus_manifest_sha256": sha256_file(corpus_path),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_sha256": model["asset"]["sha256"],
        "overall": "PASS",
        "production_embedder": preflight.descriptor,
        "schema": "moss-human-audit-cache-equivalence.v1",
        "spec_sha256": sha256_file(spec_path),
    }
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-manifest", type=Path, default=STAGE0 / "corpus-manifest.json")
    parser.add_argument("--model-manifest", type=Path, default=STAGE0 / "model-manifest.json")
    parser.add_argument("--spec", type=Path, default=STAGE0 / "cache-rebuild-spec.json")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    result = prove(
        corpus_path=args.corpus_manifest,
        model_path=args.model_manifest,
        spec_path=args.spec,
        output_root=args.output_root,
        json_output=args.json_output,
    )
    for case in result["cases"]:
        print(
            "PASS "
            f"{case['case_id']} unit_bounds_byte_identical={case['unit_bounds_byte_identical']} "
            f"vectors_byte_identical={case['vectors_byte_identical']}"
        )
    print(json.dumps({"case_count": len(result["cases"]), "overall": result["overall"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
