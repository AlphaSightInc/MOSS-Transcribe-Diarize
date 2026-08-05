#!/usr/bin/env python3
"""Build production-planned and production-embedded exploratory lane fixtures."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import wave


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ROOT = HERE / "exploratory/f2-dual-lane"
ASR = ROOT / "runtime-asr/provenance.json"
OUTPUT = ROOT / "runtime-fixture.json"
MODEL_MANIFEST = REPO / "prototypes/streaming-diarization/l2-stage0/model-manifest.json"
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.speaker_identity import (  # noqa: E402
    PINNED_TIER_B_ASSET_SPEC,
    WeSpeakerResNet152LmAdapter,
)
from runtime_fixture import (  # noqa: E402
    build_runtime_cache,
    plan_runtime_asr,
    planner_bindings,
    runtime_shape,
    sha256_file,
    validate_runtime_cache,
)


def main() -> int:
    if OUTPUT.exists():
        raise RuntimeError("f2_runtime_fixture_version_exists")
    provenance = json.loads(ASR.read_text())
    if provenance["overall"] != "PASS" or not all(not value for key, value in provenance["constraints"].items() if key.endswith("opened")):
        raise RuntimeError("f2_runtime_asr_scope_invalid")
    model = json.loads(MODEL_MANIFEST.read_text())
    model_path = REPO / model["asset"]["path"]
    if sha256_file(model_path) != model["asset"]["sha256"]:
        raise RuntimeError("f2_model_hash_mismatch")
    if model["asset"]["sha256"] != PINNED_TIER_B_ASSET_SPEC.state_sha256:
        raise RuntimeError("f2_model_not_production_pin")
    embedder = WeSpeakerResNet152LmAdapter(model_path)
    preflight = embedder.preflight()
    if not preflight.available:
        raise RuntimeError(f"f2_embedder_unavailable:{preflight.reason}")
    cases = []
    for record in provenance["cases"]:
        lane = record["capture_lane"]
        audio_path = REPO / record["audio_path"]
        segments_path = REPO / record["segments_path"]
        if sha256_file(audio_path) != record["audio_sha256"] or sha256_file(segments_path) != record["segments_sha256"]:
            raise RuntimeError(f"f2_runtime_input_hash:{lane}")
        with wave.open(str(audio_path), "rb") as handle:
            if handle.getframerate() != 16_000 or handle.getnchannels() != 1:
                raise RuntimeError(f"f2_audio_format:{lane}")
            total_samples = handle.getnframes()
        segments = json.loads(segments_path.read_text())["segments"]
        plan = plan_runtime_asr(segments, total_samples=total_samples)
        cache_path = ROOT / "runtime-fixtures" / lane / "runtime_cache.npz"
        stats = build_runtime_cache(plan, audio_path=audio_path, output_path=cache_path, embedder=embedder)
        fidelity = validate_runtime_cache(cache_path, plan)
        cases.append(
            {
                "capture_lane": lane,
                "audio_path": record["audio_path"],
                "audio_sha256": record["audio_sha256"],
                "segments_path": record["segments_path"],
                "segments_sha256": record["segments_sha256"],
                "cache_path": cache_path.relative_to(REPO).as_posix(),
                "cache_sha256": sha256_file(cache_path),
                "runtime_shape_sha256": __import__("hashlib").sha256(
                    json.dumps(runtime_shape(plan), separators=(",", ":")).encode()
                ).hexdigest(),
                "total_samples": total_samples,
                "stats": stats,
                "self_replan": fidelity,
            }
        )
        print(f"PASS {lane} spans={stats['span_count']} units={stats['unit_count']} vectors={stats['vector_count']}")
    payload = {
        "schema": "moss-l15-f2-runtime-fixture.v1",
        "frame": "production-endpoint-over-deployed-asr-per-capture-lane",
        "runtime_asr_provenance_path": ASR.relative_to(REPO).as_posix(),
        "runtime_asr_provenance_sha256": sha256_file(ASR),
        "production_planner": planner_bindings(),
        "production_embedder": {
            "binding": "moss_transcribe_diarize.app.speaker_identity.WeSpeakerResNet152LmAdapter",
            "model_sha256": model["asset"]["sha256"],
            "frontend_source_sha256": model["frontend"]["source_sha256"],
            "preflight": preflight.descriptor,
        },
        "cases": cases,
        "reference_opened": False,
        "gated_corpus_opened": False,
        "holdout_opened": False,
        "overall": "PASS",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"PASS overall fixture_sha256={sha256_file(OUTPUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
