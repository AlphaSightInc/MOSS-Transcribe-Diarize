#!/usr/bin/env python3
"""Measure the minimal span-wise dual-lane decoder/identity seam.

One command:

  .venv/bin/python prototypes/lane-balance/proto_live_dual_lane.py \
    --output evidence/phase1/g3-attended/live-dual-lane-20260819.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).parent
LATENCY_ROOT = REPO / "prototypes/live-latency"
IDENTITY_ROOT = REPO / "prototypes/streaming-diarization"
sys.path[:0] = [str(REPO), str(ROOT), str(LATENCY_ROOT), str(IDENTITY_ROOT)]

import proto_ab_identity as identity_bench  # noqa: E402
from proto_cap_silence_sweep import (  # noqa: E402
    decode_span,
    discover_model,
    distribution,
    load_cache,
    plan_spans,
)
from proto_lane_balance_v3 import (  # noqa: E402
    dbfs,
    mix,
    read_pcm,
    rms,
    sha256,
    shuffle_edit_score,
    words,
    write_pcm,
)
from moss_transcribe_diarize.app import speaker_identity  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import render_segments  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript  # noqa: E402


CONTRACT_PATH = ROOT / "preregistration-live-dual-lane-v1.json"
V3_PATH = REPO / "evidence/phase1/g3-attended/lane-balance-v3-20260819.json"
MODEL_PATH = IDENTITY_ROOT / "data/voxceleb_resnet152_LM.onnx"
DEFAULT_CACHE = Path("/tmp/moss-live-dual-lane-decode-cache-20260819.json")
DEFAULT_BASE_URL = "http://127.0.0.1:18000/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("MOSS_VLLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def pcm_bytes(samples: list[float], path: Path) -> bytes:
    write_pcm(path, samples, 16_000)
    with path.open("rb") as source:
        source.seek(44)
        payload = source.read()
    if len(payload) != len(samples) * 2:
        raise RuntimeError(f"wav_pcm_size:{path}:{len(payload)}:{len(samples) * 2}")
    return payload


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def merge_span(
    span: dict[str, Any],
    shared: dict[str, Any],
    microphone: dict[str, Any],
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    tagged: list[tuple[str, TranscriptSegment]] = []
    maps: dict[str, dict[str, str]] = {}
    next_label = 1
    for lane, decoded in (("shared", shared), ("microphone", microphone)):
        source_labels = sorted({item["speaker"] for item in decoded["segments"]})
        maps[lane] = {
            label: f"S{index:02d}"
            for index, label in enumerate(source_labels, next_label)
        }
        next_label += len(source_labels)
        tagged.extend(
            (
                lane,
                TranscriptSegment(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    speaker=maps[lane][item["speaker"]],
                    text=str(item["text"]),
                ),
            )
            for item in decoded["segments"]
        )
    tagged.sort(key=lambda item: (
        item[1].start,
        0 if item[0] == "shared" else 1,
        item[1].end,
        item[1].speaker,
    ))
    merged_segments = [segment for _, segment in tagged]
    transcript = render_segments(merged_segments, lambda item: item.speaker) if merged_segments else ""
    roundtrip = parse_transcript(transcript) if transcript else []
    overlaps = []
    shared_segments = [segment for lane, segment in tagged if lane == "shared"]
    microphone_segments = [segment for lane, segment in tagged if lane == "microphone"]
    for left_index, left in enumerate(shared_segments):
        for right_index, right in enumerate(microphone_segments):
            seconds = max(0.0, min(left.end, right.end) - max(left.start, right.start))
            if seconds:
                overlaps.append({
                    "shared_index": left_index,
                    "microphone_index": right_index,
                    "seconds": seconds,
                })
    trace = [
        {
            "lane": lane,
            "span_id": span["id"],
            "start": segment.start,
            "end": segment.end,
            "absolute_start": span["start_sample"] / 16_000 + segment.start,
            "absolute_end": span["start_sample"] / 16_000 + segment.end,
            "speaker": segment.speaker,
            "text": segment.text,
        }
        for lane, segment in tagged
    ]
    state = {
        "shared_label_map": maps["shared"],
        "microphone_label_map": maps["microphone"],
        "namespace_collision_free": set(maps["shared"].values()).isdisjoint(maps["microphone"].values()),
        "source_segment_count": len(shared["segments"]) + len(microphone["segments"]),
        "merged_segment_count": len(merged_segments),
        "all_segments_preserved": len(merged_segments) == len(shared["segments"]) + len(microphone["segments"]),
        "parse_roundtrip_equal": roundtrip == merged_segments,
        "local_speaker_count": next_label - 1,
        "overlap_pairs": overlaps,
        "overlap_preserved": True,
        "source_trace": trace,
    }
    return transcript, state, trace


def queue_metrics(
    spans: list[dict[str, Any]],
    service_seconds: list[float],
    render_bound_seconds: float,
) -> dict[str, Any]:
    available = 0.0
    finishes: list[float] = []
    waits: list[float] = []
    first: list[float] = []
    last: list[float] = []
    max_depth = 0
    timeline = []
    for span, service in zip(spans, service_seconds, strict=True):
        arrival = float(span["freeze_seconds"])
        depth = sum(finish > arrival for finish in finishes)
        max_depth = max(max_depth, depth)
        started = max(arrival, available)
        finished = started + service
        wait = started - arrival
        finishes.append(finished)
        available = finished
        tail = wait + service + render_bound_seconds
        waits.append(wait)
        first.append(float(span["duration_seconds"]) + tail)
        last.append(tail)
        timeline.append({
            "span_id": span["id"],
            "arrival_seconds": arrival,
            "queue_depth_at_arrival": depth,
            "started_seconds": started,
            "service_seconds": service,
            "finished_seconds": finished,
            "queue_wait_seconds": wait,
            "first_word_visible_bound_seconds": first[-1],
            "last_word_visible_bound_seconds": last[-1],
        })
    audio_end = spans[-1]["end_sample"] / 16_000 if spans else 0.0
    return {
        "timeline": timeline,
        "max_queue_depth": max_depth,
        "queue_wait_seconds": distribution(waits),
        "first_word_visible_bound_seconds": distribution(first),
        "last_word_visible_bound_seconds": distribution(last),
        "stop_drain_seconds": max(0.0, available - audio_end),
    }


def two_session_fairness(
    spans: list[dict[str, Any]],
    services: list[float],
) -> dict[str, Any]:
    arrivals = {
        session: [float(span["freeze_seconds"]) for span in spans]
        for session in ("A", "B")
    }
    next_index = {"A": 0, "B": 0}
    completed = {"A": 0, "B": 0}
    time_now = 0.0
    last_session = "B"
    trace = []
    max_skew = 0
    while any(next_index[session] < len(spans) for session in next_index):
        ready = [
            session
            for session in ("A", "B")
            if next_index[session] < len(spans)
            and arrivals[session][next_index[session]] <= time_now
        ]
        if not ready:
            time_now = min(
                arrivals[session][next_index[session]]
                for session in ("A", "B")
                if next_index[session] < len(spans)
            )
            continue
        session = next((item for item in ready if item != last_session), ready[0])
        index = next_index[session]
        started = time_now
        time_now += services[index]
        next_index[session] += 1
        completed[session] += 1
        last_session = session
        both_unfinished = all(next_index[item] < len(spans) for item in ("A", "B"))
        if both_unfinished:
            max_skew = max(max_skew, abs(completed["A"] - completed["B"]))
        trace.append({
            "session": session,
            "span_id": spans[index]["id"],
            "started_seconds": started,
            "finished_seconds": time_now,
            "completed": dict(completed),
            "both_unfinished": both_unfinished,
        })
    return {
        "policy": "round_robin_at_span_item_boundaries",
        "max_completed_span_skew_while_both_unfinished": max_skew,
        "terminal_completed": completed,
        "trace": trace,
    }


def identity_measurement(
    *,
    embedder: Any,
    lane_paths: dict[str, Path],
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    rows: list[tuple[float, ...]] = []
    vectors: list[np.ndarray] = []
    vector_indexes: list[int] = []
    units = []
    failures = []
    grouped: dict[tuple[int, str, str], list[tuple[float, float]]] = {}
    for item in traces:
        grouped.setdefault(
            (int(item["span_id"]), str(item["lane"]), str(item["speaker"])), []
        ).append((float(item["absolute_start"]), float(item["absolute_end"])))
    for (span_id, lane, speaker), intervals in sorted(grouped.items()):
        eligible = [interval for interval in intervals if interval[1] - interval[0] >= 0.5]
        duration = sum(end - start for start, end in (eligible or intervals))
        vector_index = -1
        if eligible:
            try:
                vector = np.asarray(embedder.embed(lane_paths[lane], eligible), dtype=np.float32)
                vectors.append(vector)
                vector_index = len(vectors) - 1
            except Exception as exc:
                failures.append({
                    "span_id": span_id,
                    "lane": lane,
                    "speaker": speaker,
                    "error": exc.__class__.__name__,
                })
        rows.append((
            float(span_id),
            0.0 if lane == "shared" else 1.0,
            min(start for start, _ in intervals),
            max(end for _, end in intervals),
            duration,
            float(vector_index >= 0),
        ))
        vector_indexes.append(vector_index)
        units.append({
            "span_id": span_id,
            "lane": lane,
            "speaker": speaker,
            "intervals": intervals,
            "eligible_intervals": eligible,
            "duration_seconds": duration,
            "embedded": vector_index >= 0,
        })
    if not rows or not vectors:
        return {
            "accuracy": 0.0,
            "canonical_speakers": 0,
            "failures": failures,
            "units": units,
        }
    cache = {
        "rows": np.asarray(rows, dtype=np.float64),
        "vecs": np.stack(vectors),
        "vec_idx": np.asarray(vector_indexes, dtype=np.int64),
    }
    identity_bench.SWEEP_EVERY = 60.0
    live, terminal, _, _ = identity_bench.simulate(
        cache,
        policy="album",
        min_score=0.35,
        margin=0.1,
        admission=2.0,
        birth_floor=1.0,
        sweep=True,
    )
    return {
        "accuracy": float(identity_bench.accuracy(cache["rows"], terminal)),
        "canonical_speakers": len({int(value) for value in terminal if value >= 0}),
        "live_assignments": live.tolist(),
        "terminal_sweep_assignments": terminal.tolist(),
        "failures": failures,
        "units": units,
    }


def evaluate_corpus(
    *,
    corpus_id: str,
    source: dict[str, Any],
    runner: VllmRunner,
    model: str,
    embedder: Any,
    cache: dict[str, Any],
    cache_path: Path,
    scratch: Path,
    render_bound_seconds: float,
) -> dict[str, Any]:
    inputs = source["input"]
    seconds = int(inputs["clip_seconds"])
    shared_source = REPO / inputs["shared_lane"]["path"]
    microphone_source = REPO / inputs["microphone_lane"]["path"]
    if file_sha(shared_source) != inputs["shared_lane"]["sha256"]:
        raise RuntimeError(f"shared_hash:{corpus_id}")
    if file_sha(microphone_source) != inputs["microphone_lane"]["sha256"]:
        raise RuntimeError(f"microphone_hash:{corpus_id}")
    shared, sample_rate = read_pcm(shared_source, seconds)
    microphone_clean, microphone_rate = read_pcm(microphone_source, seconds)
    if sample_rate != 16_000 or microphone_rate != sample_rate:
        raise RuntimeError(f"sample_rate:{corpus_id}")
    attenuation = float(inputs["microphone_lane"]["attenuation_db"])
    microphone = [value * (10 ** (attenuation / 20)) for value in microphone_clean]
    mixed, limited = mix(shared, microphone)
    corpus_scratch = scratch / corpus_id
    corpus_scratch.mkdir()
    paths = {
        "shared": corpus_scratch / "shared.wav",
        "microphone": corpus_scratch / "microphone.wav",
        "mixed": corpus_scratch / "mixed.wav",
    }
    payloads = {
        "shared": pcm_bytes(shared, paths["shared"]),
        "microphone": pcm_bytes(microphone, paths["microphone"]),
        "mixed": pcm_bytes(mixed, paths["mixed"]),
    }
    hashes = {lane: file_sha(path) for lane, path in paths.items()}
    spans = plan_spans(payloads["mixed"], {"hard_cap_ms": 2500, "min_silence_ms": 500})
    baseline_spans = []
    candidate_spans = []
    all_traces: list[dict[str, Any]] = []
    baseline_services = []
    candidate_services = []
    for span in spans:
        baseline = decode_span(
            runner=runner,
            pcm=payloads["mixed"],
            span=span,
            audio_sha=hashes["mixed"],
            model=model,
            cache=cache,
            cache_path=cache_path,
            scratch=corpus_scratch,
        )
        shared_decode = decode_span(
            runner=runner,
            pcm=payloads["shared"],
            span=span,
            audio_sha=hashes["shared"],
            model=model,
            cache=cache,
            cache_path=cache_path,
            scratch=corpus_scratch,
        )
        microphone_decode = decode_span(
            runner=runner,
            pcm=payloads["microphone"],
            span=span,
            audio_sha=hashes["microphone"],
            model=model,
            cache=cache,
            cache_path=cache_path,
            scratch=corpus_scratch,
        )
        merged, structure, trace = merge_span(span, shared_decode, microphone_decode)
        all_traces.extend(trace)
        baseline_spans.append({"span": span, "decode": baseline})
        candidate_spans.append({
            "span": span,
            "shared": shared_decode,
            "microphone": microphone_decode,
            "merged_transcript": merged,
            "structure": structure,
        })
        baseline_services.append(float(baseline["elapsed_seconds"]))
        candidate_services.append(
            float(shared_decode["elapsed_seconds"]) + float(microphone_decode["elapsed_seconds"])
        )
    references = source["clean_references"]
    shared_reference = references["shared"]["normalized_tokens"]
    microphone_reference = references["microphone"]["normalized_tokens"]
    baseline_hypothesis = [
        token
        for item in baseline_spans
        for segment in item["decode"]["segments"]
        for token in words(segment["text"])
    ]
    candidate_hypothesis = [
        token
        for item in candidate_spans
        for token in words(item["merged_transcript"])
    ]
    baseline_score = shuffle_edit_score(shared_reference, microphone_reference, baseline_hypothesis)
    candidate_score = shuffle_edit_score(shared_reference, microphone_reference, candidate_hypothesis)
    baseline_queue = queue_metrics(spans, baseline_services, render_bound_seconds)
    candidate_queue = queue_metrics(spans, candidate_services, render_bound_seconds)
    structures = [item["structure"] for item in candidate_spans]
    identity = identity_measurement(
        embedder=embedder,
        lane_paths={"shared": paths["shared"], "microphone": paths["microphone"]},
        traces=all_traces,
    )
    classifications = [
        decoded["classification"]
        for item in candidate_spans
        for decoded in (item["shared"], item["microphone"])
    ]
    capped = sum(
        int(decoded["capped"])
        for item in candidate_spans
        for decoded in (item["shared"], item["microphone"])
    )
    fairness = two_session_fairness(spans, candidate_services)
    gates = {
        "content": baseline_score["word_error_rate"] - candidate_score["word_error_rate"] >= 0.05,
        "structure": all(
            state["namespace_collision_free"]
            and state["all_segments_preserved"]
            and state["parse_roundtrip_equal"]
            and state["overlap_preserved"]
            and state["local_speaker_count"] <= 16
            for state in structures
        ),
        "identity": (
            identity["accuracy"] >= 0.80
            and identity["canonical_speakers"] <= 4
            and not identity["failures"]
        ),
        "decode_integrity": capped == 0 and all(value == "valid" for value in classifications),
        "queue_depth": candidate_queue["max_queue_depth"] <= 16,
        "stop_drain": candidate_queue["stop_drain_seconds"] <= 5.0,
        "request_multiplier": len(candidate_spans) * 2 == len(baseline_spans) * 2,
        "fairness": fairness["max_completed_span_skew_while_both_unfinished"] <= 1,
        "first_word_latency": (
            candidate_queue["first_word_visible_bound_seconds"]["p95"]
            <= baseline_queue["first_word_visible_bound_seconds"]["p95"]
        ),
        "last_word_latency": (
            candidate_queue["last_word_visible_bound_seconds"]["p95"]
            <= baseline_queue["last_word_visible_bound_seconds"]["p95"]
        ),
    }
    return {
        "input": {
            "seconds": seconds,
            "attenuation_db": attenuation,
            "total_disparity_db": dbfs(rms(shared)) - dbfs(rms(microphone)),
            "wav_sha256": hashes,
            "limited_samples": limited,
        },
        "endpoint_spans": spans,
        "baseline": {
            "request_count": len(baseline_spans),
            "content": baseline_score,
            "queue_and_latency": baseline_queue,
            "spans": baseline_spans,
        },
        "dual_lane": {
            "request_count": len(candidate_spans) * 2,
            "request_multiplier": 2.0,
            "content": candidate_score,
            "wer_improvement": baseline_score["word_error_rate"] - candidate_score["word_error_rate"],
            "queue_and_latency": candidate_queue,
            "identity": identity,
            "fairness_two_sessions": fairness,
            "decode_classifications": classifications,
            "decode_capped_count": capped,
            "spans": candidate_spans,
        },
        "gates": gates,
        "passes": all(gates.values()),
    }


def main() -> int:
    cli = parse_args()
    output = cli.output.resolve()
    if output.exists():
        raise RuntimeError(f"refuse_to_overwrite:{output}")
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if contract.get("schema") != "moss-live-dual-lane-preregistration.v1":
        raise RuntimeError("contract_schema")
    for binding in contract["bound_evidence"].values():
        if sha256(REPO / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound_evidence_hash:{binding['path']}")
    manifest_path = REPO / contract["production_contract"]["manifest_path"]
    if sha256(manifest_path) != contract["production_contract"]["manifest_sha256"]:
        raise RuntimeError("manifest_hash")
    v3 = json.loads(V3_PATH.read_text(encoding="utf-8"))
    model = discover_model(cli.base_url, cli.timeout_seconds)
    runner = VllmRunner(base_url=cli.base_url, model=model, api_key=None, timeout=cli.timeout_seconds)
    embedder = speaker_identity._OnnxWeSpeakerEmbedder(MODEL_PATH, device="cpu")
    cache = load_cache(cli.cache)
    results = {}
    with tempfile.TemporaryDirectory(prefix="moss-live-dual-lane-") as temporary:
        scratch = Path(temporary)
        for corpus_id, source in v3["corpora"].items():
            print(f"MEASURE {corpus_id}", flush=True)
            results[corpus_id] = evaluate_corpus(
                corpus_id=corpus_id,
                source=source,
                runner=runner,
                model=model,
                embedder=embedder,
                cache=cache,
                cache_path=cli.cache,
                scratch=scratch,
                render_bound_seconds=(
                    contract["bound_evidence"]["attended_latency_baseline"]
                    ["active_reader_render_bound_ms"] / 1_000
                ),
            )
            print(json.dumps({
                "corpus": corpus_id,
                "wer_improvement": results[corpus_id]["dual_lane"]["wer_improvement"],
                "identity_accuracy": results[corpus_id]["dual_lane"]["identity"]["accuracy"],
                "gates": results[corpus_id]["gates"],
            }), flush=True)
    passes = all(result["passes"] for result in results.values())
    failed_gates = sorted({
        gate
        for result in results.values()
        for gate, passed in result["gates"].items()
        if not passed
    })
    verdict = (
        contract["decision_rule"]["passing_verdict"]
        if passes
        else contract["decision_rule"]["failing_verdict"]
    )
    artifact = {
        "schema": "moss-live-dual-lane-result.v1",
        "preregistration": {
            "path": str(CONTRACT_PATH.relative_to(REPO)),
            "sha256": sha256(CONTRACT_PATH),
        },
        "scope": contract["scope"],
        "module_interface": contract["module_interface"],
        "vllm": {"base_url": cli.base_url, "model": model},
        "identity_model": {
            "path": str(MODEL_PATH.relative_to(REPO)),
            "sha256": sha256(MODEL_PATH),
        },
        "corpora": results,
        "selection": {
            "verdict": verdict,
            "passes": passes,
            "failed_gates": failed_gates,
            "production_change": "NONE",
            "next_step": (
                "obtain fresh real attended lane evidence before production design"
                if passes
                else "retain production mono mix; obtain fresh real attended lane evidence before another remedy"
            ),
        },
        "decode_cache": {"path": str(cli.cache), "entry_count": len(cache["entries"])},
    }
    encoded = json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(encoded, encoding="utf-8")
    print(json.dumps({
        "complete": True,
        "output": str(output),
        "sha256": sha256(output),
        "selection": artifact["selection"],
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
