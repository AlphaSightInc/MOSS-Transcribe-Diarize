#!/usr/bin/env python3
"""Build D8-safe production-planned, production-embedded runtime fixtures."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sys
import wave


REPO = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.speaker_identity import (  # noqa: E402
    PINNED_TIER_B_ASSET_SPEC,
    WeSpeakerResNet152LmAdapter,
)
from runtime_fixture import (  # noqa: E402
    HARD_CAP_SAMPLES,
    SAMPLE_RATE,
    build_runtime_cache,
    plan_runtime_asr,
    planner_bindings,
    runtime_shape,
    sha256_file,
    validate_runtime_cache,
)


ASR_PROVENANCE = HERE / "runtime-inputs" / "asr-provenance.json"
MODEL_MANIFEST = REPO / "prototypes/streaming-diarization/l2-stage0/model-manifest.json"
OUTPUT_ROOT = HERE / "runtime-inputs" / "production-asr-frame-v1"
OUTPUT_MANIFEST = HERE / "runtime-input-manifest.json"
EVIDENCE = HERE / "evidence" / "runtime-fixture"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sample_count(path: Path) -> int:
    with wave.open(str(path), "rb") as handle:
        if handle.getframerate() != SAMPLE_RATE or handle.getnchannels() != 1:
            raise RuntimeError(f"runtime_audio_format_mismatch:{path}")
        return handle.getnframes()


def main() -> int:
    if OUTPUT_MANIFEST.exists() or OUTPUT_ROOT.exists():
        raise RuntimeError("runtime_fixture_version_exists")
    asr = json.loads(ASR_PROVENANCE.read_text(encoding="utf-8"))
    if asr["case_count"] != 16 or asr["constraints"]["holdout_case_opened"]:
        raise RuntimeError("runtime_asr_scope_invalid")
    model = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    model_path = REPO / model["asset"]["path"]
    if sha256_file(model_path) != model["asset"]["sha256"]:
        raise RuntimeError("runtime_model_hash_mismatch")
    if model["asset"]["sha256"] != PINNED_TIER_B_ASSET_SPEC.state_sha256:
        raise RuntimeError("runtime_model_not_production_pin")
    if HARD_CAP_SAMPLES != int(model["frontend"]["config"]["hard_cap_samples"]):
        raise RuntimeError("runtime_hard_cap_drift")
    embedder = WeSpeakerResNet152LmAdapter(model_path)
    preflight = embedder.preflight()
    if not preflight.available:
        raise RuntimeError(f"runtime_embedder_unavailable:{preflight.reason}")
    events: list[str] = []
    cases = []
    for index, record in enumerate(asr["cases"], 1):
        case_id = record["case_id"]
        audio_path = REPO / record["audio_path"]
        segments_path = REPO / record["segments_path"]
        if record["split"] not in {"development", "validation"}:
            raise RuntimeError(f"runtime_case_split_invalid:{case_id}")
        if sha256_file(audio_path) != record["audio_sha256"]:
            raise RuntimeError(f"runtime_audio_hash_mismatch:{case_id}")
        if sha256_file(segments_path) != record["segments_sha256"]:
            raise RuntimeError(f"runtime_segments_hash_mismatch:{case_id}")
        segments = json.loads(segments_path.read_text(encoding="utf-8"))["segments"]
        plan = plan_runtime_asr(segments, total_samples=sample_count(audio_path))
        cache_path = OUTPUT_ROOT / case_id / "runtime_cache.npz"
        events.append(
            f"BUILD {index}/16 {case_id} spans={len(plan.spans)} units={len(plan.units)}"
        )
        print(events[-1], flush=True)
        stats = build_runtime_cache(
            plan,
            audio_path=audio_path,
            output_path=cache_path,
            embedder=embedder,
            embedding_dimension=int(model["frontend"]["config"]["embedding_dimension"]),
        )
        fidelity = validate_runtime_cache(cache_path, plan)
        case_payload = {
            "case_id": case_id,
            "split": record["split"],
            "audio_path": record["audio_path"],
            "audio_sha256": record["audio_sha256"],
            "asr_segments_path": record["segments_path"],
            "asr_segments_sha256": record["segments_sha256"],
            "runtime_cache_path": cache_path.relative_to(REPO).as_posix(),
            "runtime_cache_sha256": sha256_file(cache_path),
            "runtime_shape_sha256": __import__("hashlib").sha256(
                json.dumps(runtime_shape(plan), separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "total_samples": plan.total_samples,
            "spans": [
                {
                    "span_id": span.span_id,
                    "start_sample": span.start_sample,
                    "end_sample": span.end_sample,
                    "reason": span.reason,
                }
                for span in plan.spans
            ],
            "units": [
                {
                    "span_id": unit.span_id,
                    "local_speaker": unit.local_speaker,
                    "pieces": [
                        {"start_sample": piece.start_sample, "end_sample": piece.end_sample}
                        for piece in unit.pieces
                    ],
                }
                for unit in plan.units
            ],
            "stats": stats,
            "self_replan": fidelity,
        }
        cases.append(case_payload)
        events.append(f"PASS {case_id} cache_sha256={case_payload['runtime_cache_sha256']}")
        print(events[-1], flush=True)
    manifest = {
        "schema": "moss-l15-runtime-input-manifest.v1",
        "created_at_utc": utc_now(),
        "frame": "production-endpoint-over-deployed-asr",
        "case_count": len(cases),
        "cases": cases,
        "input_asr_provenance_path": ASR_PROVENANCE.relative_to(REPO).as_posix(),
        "input_asr_provenance_sha256": sha256_file(ASR_PROVENANCE),
        "model_manifest_path": MODEL_MANIFEST.relative_to(REPO).as_posix(),
        "model_manifest_sha256": sha256_file(MODEL_MANIFEST),
        "production_embedder": {
            "binding": "moss_transcribe_diarize.app.speaker_identity.WeSpeakerResNet152LmAdapter",
            "model_sha256": model["asset"]["sha256"],
            "frontend_source_sha256": model["frontend"]["source_sha256"],
            "preflight": preflight.descriptor,
        },
        "production_planner": planner_bindings(),
        "golden_paths_present": False,
        "holdout_cases_present": False,
        "overall": "PASS",
    }
    OUTPUT_MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "build-transcript.txt").write_text("\n".join(events) + "\n", encoding="utf-8")
    print(f"PASS overall manifest_sha256={sha256_file(OUTPUT_MANIFEST)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
