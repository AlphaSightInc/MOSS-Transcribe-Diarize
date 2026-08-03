#!/usr/bin/env python3
"""Copy immutable bench inputs, adopt accepted alphabet v2, rebuild, and freeze."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path
import shutil
import sys
import wave

import numpy as np

from case_registry import CASES
from validate_inputs import load_reference, reference_findings, sha256_file


HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
REPO = HERE.parents[2]
DATA = BENCH / "data"
MODEL_REL = Path("voxceleb_resnet152_LM.onnx")
ACCEPTED_REFERENCE = REPO / "tests/fixtures/live_identity_real_corpus/speaker-reference-v2-post-audit.jsonl"
EXPECTED_REFERENCE_SHA256 = "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759"


def _copy_inputs(source_bench: Path) -> None:
    source_data = source_bench / "data"
    if source_data.resolve() == DATA.resolve():
        raise ValueError("source bench must differ from isolated worktree bench")
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_data / MODEL_REL, DATA / MODEL_REL)
    for spec in CASES:
        source = source_data / spec["rel"]
        target = DATA / spec["rel"]
        target.mkdir(parents=True, exist_ok=True)
        for name in ("audio.wav", "reference.jsonl", "harness_cache.npz"):
            shutil.copy2(source / name, target / name)


def _rebuild_alphabet(source_bench: Path) -> dict[str, object]:
    target = DATA / "real/benchmark_5m/acquired_alphabet"
    source = source_bench / "data/real/benchmark_5m/acquired_alphabet"
    old_reference_hash = sha256_file(target / "reference.jsonl")
    old_cache_hash = sha256_file(target / "harness_cache.npz")
    accepted_hash = sha256_file(ACCEPTED_REFERENCE)
    if accepted_hash != EXPECTED_REFERENCE_SHA256:
        raise ValueError(f"accepted alphabet reference hash mismatch: {accepted_hash}")
    shutil.copy2(ACCEPTED_REFERENCE, target / "reference.jsonl")

    sys.path.insert(0, str(BENCH))
    import proto_ab_identity as harness

    speakers: dict[str, int] = {}
    truth: list[tuple[float, float, int]] = []
    for start, end, speaker, _text in load_reference(target / "reference.jsonl"):
        truth.append((start, end, speakers.setdefault(speaker, len(speakers))))
    pieces = harness.plan_spans(truth)
    groups: dict[tuple[int, int], list[object]] = {}
    for piece in pieces:
        groups.setdefault((piece.span, piece.true_spk), []).append(piece)
    adapter = harness.load_production_embedder()
    vectors: list[np.ndarray] = []
    vector_indexes: list[int] = []
    rows: list[tuple[float, ...]] = []
    for (span, speaker), group in sorted(groups.items()):
        eligible_pieces = [piece for piece in group if piece.dur >= harness.MIN_EVID]
        duration = sum(piece.dur for piece in eligible_pieces) or sum(piece.dur for piece in group)
        if eligible_pieces:
            vector = adapter.embed(
                target / "audio.wav",
                [(piece.start, piece.end) for piece in eligible_pieces],
            )
            vectors.append(np.asarray(vector, np.float32))
            vector_indexes.append(len(vectors) - 1)
        else:
            vector_indexes.append(-1)
        rows.append(
            (
                float(span),
                float(speaker),
                min(piece.start for piece in group),
                max(piece.end for piece in group),
                duration,
                float(bool(eligible_pieces)),
            )
        )
    np.savez(
        target / "harness_cache.npz",
        vecs=np.stack(vectors) if vectors else np.zeros((0, 256), np.float32),
        vec_idx=np.asarray(vector_indexes, np.int64),
        rows=np.asarray(rows, np.float64),
    )
    frontend = REPO / "moss_transcribe_diarize/app/speaker_identity.py"
    return {
        "audio_sha256": sha256_file(target / "audio.wav"),
        "frontend_source_sha256": sha256_file(frontend),
        "model_sha256": sha256_file(DATA / MODEL_REL),
        "new_reference_sha256": sha256_file(target / "reference.jsonl"),
        "new_vector_cache_sha256": sha256_file(target / "harness_cache.npz"),
        "old_reference_path": str(source / "reference.jsonl"),
        "old_reference_sha256": old_reference_hash,
        "old_vector_cache_path": str(source / "harness_cache.npz"),
        "old_vector_cache_sha256": old_cache_hash,
        "row_count": len(rows),
        "speaker_count": len(speakers),
        "vector_count": len(vectors),
    }


def _duration(path: Path) -> float:
    with wave.open(str(path), "rb") as handle:
        return handle.getnframes() / handle.getframerate()


def _repo_path(path: Path) -> str:
    return path.relative_to(REPO).as_posix()


def _case_manifest(spec: dict[str, object]) -> dict[str, object]:
    root = DATA / str(spec["rel"])
    audio = root / "audio.wav"
    reference = root / "reference.jsonl"
    cache = root / "harness_cache.npz"
    duration = _duration(audio)
    rows = load_reference(reference)
    entry: dict[str, object] = {
        "acceptance_eligible": spec["accepted"],
        "audio_path": _repo_path(audio),
        "audio_sha256": sha256_file(audio),
        "case_id": spec["case_id"],
        "duration_seconds": round(duration, 6),
        "mechanical_findings": reference_findings(rows, duration),
        "reference_path": _repo_path(reference),
        "reference_sha256": sha256_file(reference),
        "reference_status": spec["status"],
        "speaker_count": len({speaker for _, _, speaker, _ in rows}),
        "split": spec["split"],
        "vector_cache_path": _repo_path(cache),
        "vector_cache_sha256": sha256_file(cache),
    }
    if spec["status"] == "post_audit_frozen":
        evidence_root = REPO / "tests/fixtures/live_identity_real_corpus"
        for kind, name in (
            ("reference_provenance", "speaker-reference-v2-post-audit.provenance.json"),
            ("human_audit", "speaker-reference-v2-human-audit-20260803.json"),
            ("acoustic_evidence", "speaker-reference-v2-candidate.acoustic-evidence.json"),
        ):
            path = evidence_root / name
            entry[f"{kind}_path"] = _repo_path(path)
            entry[f"{kind}_sha256"] = sha256_file(path)
    return entry


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def _runtime_versions() -> dict[str, object]:
    packages = ("numpy", "scipy", "soundfile", "onnxruntime", "torch", "torchaudio")
    import onnxruntime

    return {
        "available_onnx_providers": onnxruntime.get_available_providers(),
        "packages": {name: importlib.metadata.version(name) for name in packages},
        "platform": platform.platform(),
        "python": platform.python_version(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-bench", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, default=HERE / "evidence/a1-setup.json")
    args = parser.parse_args()
    _copy_inputs(args.source_bench)
    rebuild = _rebuild_alphabet(args.source_bench)
    rebuild_path = HERE / "evidence/vector-rebuild.json"
    rebuild_hash = _write_json(rebuild_path, rebuild)

    cases = [_case_manifest(spec) for spec in CASES]
    holdout_cases = [
        {
            "case_fingerprint_sha256": hashlib.sha256(
                (case["audio_sha256"] + case["reference_sha256"] + case["vector_cache_sha256"]).encode()
            ).hexdigest(),
            "case_id": case["case_id"],
        }
        for case in cases
        if case["split"] == "blind_holdout"
    ]
    holdout_path = HERE / "holdout-manifest.json"
    holdout_hash = _write_json(
        holdout_path,
        {
            "cases": holdout_cases,
            "opened_at": None,
            "schema": "moss-l2-stage0-holdout.v1",
            "sealed": True,
        },
    )
    candidate_path = HERE / "candidate-config.json"
    _write_json(
        candidate_path,
        {
            "candidate_frozen": False,
            "candidate_spec_sha256": "UNFROZEN",
            "holdout_manifest_sha256": holdout_hash,
            "schema": "moss-l2-stage0-candidate-config.v1",
        },
    )
    frontend_config = {
        "embedding_dimension": 256,
        "frontend_version": "wespeaker-onnx-fbank-v1",
        "hard_cap_samples": 40000,
        "min_evidence_samples": 8000,
        "onnx_intra_op_threads": 1,
        "onnx_inter_op_threads": 1,
        "provider": "CPUExecutionProvider",
        "sample_rate": 16000,
    }
    model_path = DATA / MODEL_REL
    frontend_path = REPO / "moss_transcribe_diarize/app/speaker_identity.py"
    model_manifest_path = HERE / "model-manifest.json"
    _write_json(
        model_manifest_path,
        {
            "asset": {"path": _repo_path(model_path), "sha256": sha256_file(model_path)},
            "frontend": {
                "config": frontend_config,
                "config_sha256": hashlib.sha256(
                    json.dumps(frontend_config, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest(),
                "source_path": _repo_path(frontend_path),
                "source_sha256": sha256_file(frontend_path),
            },
            "provider_revision": "4adba1525a6c9d5fff74b6df43a6ec97a86c4112",
            "runtime": _runtime_versions(),
            "schema": "moss-l2-stage0-model.v1",
        },
    )
    corpus_path = HERE / "corpus-manifest.json"
    corpus_hash = _write_json(
        corpus_path,
        {
            "cases": cases,
            "holdout_manifest_path": _repo_path(holdout_path),
            "schema": "moss-l2-stage0-corpus.v1",
            "split_frozen_at": "2026-08-03",
        },
    )
    contract_path = REPO / "scripts/ralph-l2-afk/contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["corpus_manifest_hash"] = corpus_hash
    _write_json(contract_path, contract)
    result = {
        "case_count": len(cases),
        "corpus_manifest_sha256": corpus_hash,
        "holdout_case_count": len(holdout_cases),
        "holdout_manifest_sha256": holdout_hash,
        "model_manifest_sha256": sha256_file(model_manifest_path),
        "reference_rebuild_sha256": rebuild_hash,
        "status": "FROZEN",
    }
    _write_json(args.json_output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
