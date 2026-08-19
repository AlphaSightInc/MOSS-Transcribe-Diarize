#!/usr/bin/env python3
"""PROTOTYPE: measure serial separate-lane decode and deterministic timed merge.

One command:

  .venv/bin/python prototypes/lane-balance/proto_separate_lane_decode.py \
    --output evidence/phase1/g3-attended/separate-lane-decode-20260819.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))
from proto_lane_balance_v3 import (  # noqa: E402
    DEFAULT_BASE_URL,
    dbfs,
    discover_model,
    mix,
    read_pcm,
    rms,
    sha256,
    shuffle_edit_score,
    transcribe,
    words,
    write_pcm,
)
from moss_transcribe_diarize.app import speaker_identity  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import render_segments  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript  # noqa: E402


PREREGISTRATION = ROOT / "preregistration-separate-lane-v1.json"
MODEL_ASSET = REPO / "prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("MOSS_VLLM_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument("--fixture-root", type=Path, default=REPO)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    return parser.parse_args()


def merge_lane_transcripts(
    shared_text: str, microphone_text: str
) -> tuple[str, dict[str, Any]]:
    shared_segments = parse_transcript(shared_text)
    microphone_segments = parse_transcript(microphone_text)
    if not shared_segments or not microphone_segments:
        raise RuntimeError("separate_lane_unparseable")
    shared_labels = sorted({segment.speaker for segment in shared_segments})
    microphone_labels = sorted({segment.speaker for segment in microphone_segments})
    shared_map = {label: f"S{index:02d}" for index, label in enumerate(shared_labels, 1)}
    microphone_map = {
        label: f"S{index:02d}"
        for index, label in enumerate(microphone_labels, len(shared_labels) + 1)
    }
    tagged: list[tuple[str, TranscriptSegment]] = []
    tagged.extend(
        ("shared", replace(segment, speaker=shared_map[segment.speaker]))
        for segment in shared_segments
    )
    tagged.extend(
        ("microphone", replace(segment, speaker=microphone_map[segment.speaker]))
        for segment in microphone_segments
    )
    tagged.sort(key=lambda item: (
        item[1].start,
        0 if item[0] == "shared" else 1,
        item[1].end,
        item[1].speaker,
    ))
    merged_segments = [segment for _, segment in tagged]
    merged_text = render_segments(merged_segments, lambda segment: segment.speaker)
    roundtrip = parse_transcript(merged_text)
    overlap_pairs = []
    for shared_index, shared in enumerate(shared_segments):
        for microphone_index, microphone in enumerate(microphone_segments):
            overlap = max(0.0, min(shared.end, microphone.end) - max(shared.start, microphone.start))
            if overlap > 0:
                overlap_pairs.append({
                    "shared_index": shared_index,
                    "microphone_index": microphone_index,
                    "seconds": overlap,
                })
    metadata = {
        "shared_segment_count": len(shared_segments),
        "microphone_segment_count": len(microphone_segments),
        "merged_segment_count": len(merged_segments),
        "all_segments_preserved": len(merged_segments) == len(shared_segments) + len(microphone_segments),
        "parse_roundtrip_equal": roundtrip == merged_segments,
        "shared_label_map": shared_map,
        "microphone_label_map": microphone_map,
        "namespace_collision_free": set(shared_map.values()).isdisjoint(microphone_map.values()),
        "local_label_count": len(shared_map) + len(microphone_map),
        "speaker_capacity_passes": len(shared_map) + len(microphone_map) <= 16,
        "segment_lane_trace": [
            {
                "lane": lane,
                "start": segment.start,
                "end": segment.end,
                "speaker": segment.speaker,
                "text": segment.text,
            }
            for lane, segment in tagged
        ],
        "cross_lane_overlap_pairs": overlap_pairs,
        "cross_lane_overlap_pair_count": len(overlap_pairs),
        "cross_lane_overlap_seconds_sum": sum(pair["seconds"] for pair in overlap_pairs),
        "overlap_preserved": True,
    }
    return merged_text, metadata


def _intervals_by_speaker(segments: list[TranscriptSegment]) -> dict[str, list[tuple[float, float]]]:
    grouped: dict[str, list[tuple[float, float]]] = {}
    for segment in segments:
        if segment.end > segment.start:
            grouped.setdefault(segment.speaker, []).append((segment.start, segment.end))
    return grouped


def _cosine(a: list[float], b: list[float]) -> float:
    numerator = sum(left * right for left, right in zip(a, b))
    left_norm = math.sqrt(sum(value * value for value in a))
    right_norm = math.sqrt(sum(value * value for value in b))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def embedding_geometry(
    embedder: Any,
    groups: list[dict[str, Any]],
) -> dict[str, Any]:
    started = time.monotonic()
    vectors: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for group in groups:
        try:
            vector = [float(value) for value in embedder.embed(group["path"], group["intervals"])]
        except Exception as exc:
            failures.append({
                "lane": group["lane"],
                "speaker": group["speaker"],
                "error": exc.__class__.__name__,
            })
            continue
        vectors.append({
            "lane": group["lane"],
            "speaker": group["speaker"],
            "interval_count": len(group["intervals"]),
            "duration_seconds": sum(end - start for start, end in group["intervals"]),
            "vector": vector,
        })
    pairs = []
    for left_index, left in enumerate(vectors):
        for right in vectors[left_index + 1:]:
            pairs.append({
                "left": f"{left['lane']}:{left['speaker']}",
                "right": f"{right['lane']}:{right['speaker']}",
                "raw_cosine": _cosine(left["vector"], right["vector"]),
            })
    cosine_values = [pair["raw_cosine"] for pair in pairs]
    return {
        "group_count": len(groups),
        "embedded_group_count": len(vectors),
        "failures": failures,
        "elapsed_seconds": time.monotonic() - started,
        "groups": [
            {key: value for key, value in vector.items() if key != "vector"}
            for vector in vectors
        ],
        "pairwise_cosines": pairs,
        "pairwise_summary": {
            "count": len(cosine_values),
            "minimum": min(cosine_values) if cosine_values else None,
            "median": statistics.median(cosine_values) if cosine_values else None,
            "maximum": max(cosine_values) if cosine_values else None,
        },
        "warning": "raw geometry only; no identity-accuracy or merge-threshold verdict",
    }


def main() -> int:
    args = parse_args()
    output_path = args.output.resolve()
    if output_path.exists():
        raise RuntimeError(f"refuse_to_overwrite_output:{output_path}")
    contract = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if contract.get("schema") != "moss-separate-lane-decode-preregistration.v1":
        raise RuntimeError("preregistration_schema")
    v3_path = REPO / contract["trigger"]["lane_balance_v3_result"]
    if sha256(v3_path) != contract["trigger"]["sha256"]:
        raise RuntimeError("lane_balance_v3_hash_mismatch")
    v3 = json.loads(v3_path.read_text(encoding="utf-8"))
    if v3["selection"]["verdict"] != contract["trigger"]["verdict"]:
        raise RuntimeError("lane_balance_v3_verdict_mismatch")
    fixture_root = args.fixture_root.resolve()
    model = discover_model(args.base_url, args.timeout_seconds)
    runner = VllmRunner(
        base_url=args.base_url,
        model=model,
        api_key=None,
        timeout=args.timeout_seconds,
    )
    embedder = speaker_identity._OnnxWeSpeakerEmbedder(MODEL_ASSET, device="cpu")
    corpus_results: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="moss-separate-lane-") as temporary:
        temporary_root = Path(temporary)
        for corpus_id, source in v3["corpora"].items():
            corpus_root = temporary_root / corpus_id
            corpus_root.mkdir()
            input_state = source["input"]
            shared_path = fixture_root / input_state["shared_lane"]["path"]
            microphone_path = fixture_root / input_state["microphone_lane"]["path"]
            if sha256(shared_path) != input_state["shared_lane"]["sha256"]:
                raise RuntimeError(f"shared_fixture_hash_mismatch:{corpus_id}")
            if sha256(microphone_path) != input_state["microphone_lane"]["sha256"]:
                raise RuntimeError(f"microphone_fixture_hash_mismatch:{corpus_id}")
            shared, sample_rate = read_pcm(shared_path, int(input_state["clip_seconds"]))
            microphone_source, microphone_rate = read_pcm(
                microphone_path, int(input_state["clip_seconds"])
            )
            if sample_rate != microphone_rate:
                raise RuntimeError(f"sample_rate_mismatch:{corpus_id}")
            attenuation_db = float(input_state["microphone_lane"]["attenuation_db"])
            attenuated_microphone = [
                sample * (10 ** (attenuation_db / 20)) for sample in microphone_source
            ]
            shared_decode_path = corpus_root / "shared.wav"
            microphone_decode_path = corpus_root / "microphone-attended-level.wav"
            identity_mix_path = corpus_root / "identity-mix.wav"
            write_pcm(shared_decode_path, shared, sample_rate)
            write_pcm(microphone_decode_path, attenuated_microphone, sample_rate)
            identity_mix, _ = mix(shared, attenuated_microphone)
            write_pcm(identity_mix_path, identity_mix, sample_rate)

            decode_wall_started = time.monotonic()
            shared_text, shared_runtime = transcribe(runner, shared_decode_path)
            microphone_text, microphone_runtime = transcribe(runner, microphone_decode_path)
            decode_wall_seconds = time.monotonic() - decode_wall_started
            merged_text, merge_state = merge_lane_transcripts(shared_text, microphone_text)
            shared_reference = source["clean_references"]["shared"]["normalized_tokens"]
            microphone_reference = source["clean_references"]["microphone"]["normalized_tokens"]
            merged_score = shuffle_edit_score(
                shared_reference, microphone_reference, words(merged_text)
            )
            baseline = source["results"]["gain_0db"]
            baseline_score = baseline["shuffle_edit"]
            baseline_runtime = baseline["transcription_runtime"]

            baseline_segments = parse_transcript(baseline["transcript"])
            baseline_groups = [
                {
                    "lane": "mono-mix",
                    "speaker": speaker,
                    "path": identity_mix_path,
                    "intervals": intervals,
                }
                for speaker, intervals in _intervals_by_speaker(baseline_segments).items()
            ]
            shared_segments = parse_transcript(shared_text)
            microphone_segments = parse_transcript(microphone_text)
            isolated_groups = [
                {
                    "lane": "shared",
                    "speaker": speaker,
                    "path": shared_decode_path,
                    "intervals": intervals,
                }
                for speaker, intervals in _intervals_by_speaker(shared_segments).items()
            ] + [
                {
                    "lane": "microphone",
                    "speaker": speaker,
                    "path": microphone_decode_path,
                    "intervals": intervals,
                }
                for speaker, intervals in _intervals_by_speaker(microphone_segments).items()
            ]
            result = {
                "input": {
                    "total_disparity_db": dbfs(rms(shared)) - dbfs(rms(attenuated_microphone)),
                    "shared_audio_sha256": sha256(shared_decode_path),
                    "attenuated_microphone_audio_sha256": sha256(microphone_decode_path),
                    "identity_mix_audio_sha256": sha256(identity_mix_path),
                },
                "decode": {
                    "request_order": ["shared", "microphone"],
                    "request_count": 2,
                    "serial_wall_seconds": decode_wall_seconds,
                    "shared": {"transcript": shared_text, "runtime": shared_runtime},
                    "microphone": {"transcript": microphone_text, "runtime": microphone_runtime},
                },
                "merge": {"transcript": merged_text, **merge_state},
                "content": {
                    "baseline_identity": baseline_score,
                    "separate_lane_merge": merged_score,
                    "wer_improvement": baseline_score["word_error_rate"] - merged_score["word_error_rate"],
                },
                "latency_and_load": {
                    "baseline_request_count": 1,
                    "request_multiplier": 2.0,
                    "baseline_decoder_elapsed_seconds": baseline_runtime["elapsed_seconds"],
                    "separate_decoder_elapsed_sum_seconds": (
                        shared_runtime["elapsed_seconds"] + microphone_runtime["elapsed_seconds"]
                    ),
                    "measured_serial_wall_seconds": decode_wall_seconds,
                    "elapsed_sum_multiplier": (
                        (shared_runtime["elapsed_seconds"] + microphone_runtime["elapsed_seconds"])
                        / baseline_runtime["elapsed_seconds"]
                    ),
                    "baseline_generated_tokens": baseline_runtime["generated_tokens"],
                    "separate_generated_tokens": (
                        shared_runtime["generated_tokens"] + microphone_runtime["generated_tokens"]
                    ),
                    "generated_token_multiplier": (
                        (shared_runtime["generated_tokens"] + microphone_runtime["generated_tokens"])
                        / baseline_runtime["generated_tokens"]
                    ),
                },
                "identity_geometry": {
                    "baseline_mono_mix": embedding_geometry(embedder, baseline_groups),
                    "separate_lane": embedding_geometry(embedder, isolated_groups),
                },
            }
            corpus_results[corpus_id] = result
            print(json.dumps({
                "corpus_complete": True,
                "corpus": corpus_id,
                "full_state": result,
            }, ensure_ascii=False), flush=True)

    improvements = [
        result["content"]["wer_improvement"] for result in corpus_results.values()
    ]
    content_passes = (
        sum(improvement >= 0.05 for improvement in improvements) >= 3
        and min(improvements) >= -0.05
    )
    structure_checks = [
        result["merge"][key]
        for result in corpus_results.values()
        for key in (
            "all_segments_preserved",
            "parse_roundtrip_equal",
            "namespace_collision_free",
            "speaker_capacity_passes",
            "overlap_preserved",
        )
    ]
    structure_passes = all(structure_checks)
    verdict = (
        "LIVE_DUAL_LANE_SEAM_PROTOTYPE_REQUIRED"
        if content_passes and structure_passes
        else "NO_SYNTHETIC_BED_MIXER_REMEDY_SELECTED"
    )
    summary = {
        "verdict": verdict,
        "content_improvements": {
            corpus_id: result["content"]["wer_improvement"]
            for corpus_id, result in corpus_results.items()
        },
        "content_passes": content_passes,
        "structure_passes": structure_passes,
        "request_multiplier": 2.0,
        "median_elapsed_sum_multiplier": statistics.median(
            result["latency_and_load"]["elapsed_sum_multiplier"]
            for result in corpus_results.values()
        ),
        "next_step": (
            "prototype the minimal live dual-lane scheduling and identity seam together with latency experiments"
            if content_passes and structure_passes
            else "obtain new real attended lane evidence before another mixer-policy attempt"
        ),
    }
    artifact = {
        "schema": "moss-separate-lane-decode-result.v1",
        "preregistration": {
            "path": str(PREREGISTRATION.relative_to(REPO)),
            "sha256": sha256(PREREGISTRATION),
        },
        "scope": contract["scope"],
        "vllm": {"base_url": args.base_url, "model": model},
        "identity_model": {
            "path": str(MODEL_ASSET.relative_to(REPO)),
            "sha256": sha256(MODEL_ASSET),
            "class": "moss_transcribe_diarize.app.speaker_identity._OnnxWeSpeakerEmbedder",
        },
        "corpora": corpus_results,
        "selection": summary,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "complete": True,
        "output": str(output_path),
        "output_sha256": sha256(output_path),
        "selection": summary,
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
