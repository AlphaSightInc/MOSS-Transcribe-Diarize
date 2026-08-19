#!/usr/bin/env python3
"""Run the sealed real-speech cap/silence sweep through production seams.

One command:

    .venv/bin/python prototypes/live-latency/proto_cap_silence_sweep.py \
      --output evidence/phase1/g3-attended/live-cap-silence-sweep-20260819.json

The output prints every span, raw transcript, score, timing, identity unit, and gate.
Discovery selects once; validation runs only the baseline and that frozen selection.
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
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import numpy as np
import webrtcvad


REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).parent
BENCH = REPO / "prototypes/streaming-diarization"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(BENCH))

import proto_ab_identity as identity_bench  # noqa: E402
from moss_transcribe_diarize.app import speaker_identity  # noqa: E402
from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.app.live_endpoint import (  # noqa: E402
    EndpointPolicy,
    EndpointPolicyConfig,
)
from moss_transcribe_diarize.app.live_provider_bundle import WebRtcSpeechProvider  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.speaker_reference import normalize_reference_text  # noqa: E402


CONTRACT_PATH = ROOT / "preregistration-cap-silence-v1.json"
DEFAULT_BASE_URL = "http://127.0.0.1:18000/v1"
DEFAULT_CACHE = Path("/tmp/moss-cap-silence-decode-cache-20260819.json")


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("MOSS_VLLM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def discover_model(base_url: str, timeout: float) -> str:
    endpoint = base_url.rstrip("/") + "/models"
    with urlopen(endpoint, timeout=timeout) as response:
        payload = json.load(response)
    models = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
    models = [item for item in models if isinstance(item, str) and item]
    if len(models) != 1:
        raise RuntimeError(f"expected_one_model:{models}")
    return models[0]


def read_audio(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        state = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        )
        if state != (1, 2, 16_000, "NONE"):
            raise RuntimeError(f"audio_contract:{path}:{state}")
        return source.readframes(source.getnframes())


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(pcm)


def plan_spans(pcm: bytes, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    frame_samples = 8_000
    provider = WebRtcSpeechProvider(
        vad=webrtcvad.Vad(1),
        frame_samples=160,
        sample_rate=16_000,
    )
    policy = EndpointPolicy(EndpointPolicyConfig(
        min_speech_samples=1_600,
        min_silence_samples=int(candidate["min_silence_ms"] * 16),
        pre_speech_padding_samples=1_600,
        post_speech_padding_samples=1_600,
        hard_cap_samples=int(candidate["hard_cap_ms"] * 16),
    ))
    sample_count = len(pcm) // 2
    spans: list[Any] = []
    sequence = 0
    start = 0
    while start < sample_count:
        end = min(start + frame_samples, sample_count)
        frame_pcm = pcm[start * 2:end * 2]
        frame = AudioFrame(
            sequence=sequence,
            pcm=frame_pcm,
            sample_count=end - start,
            sample_rate=16_000,
        )
        for observation in provider.observe(frame=frame, start_sample=start, end_sample=end):
            spans.extend(policy.observe(observation))
        start = end
        sequence += 1
    spans.extend(policy.stop())
    if not spans or spans[0].start_sample != 0 or spans[-1].end_sample != sample_count:
        raise RuntimeError("endpoint_partition_incomplete")
    if any(left.end_sample != right.start_sample for left, right in zip(spans, spans[1:])):
        raise RuntimeError("endpoint_partition_gap")
    return [
        {
            "id": index,
            "start_sample": span.start_sample,
            "end_sample": span.end_sample,
            "sample_count": span.sample_count,
            "duration_seconds": span.sample_count / 16_000,
            "freeze_seconds": span.end_sample / 16_000,
            "reason": span.reason,
        }
        for index, span in enumerate(spans)
    ]


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": "moss-cap-silence-decode-cache.v1", "entries": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != "moss-cap-silence-decode-cache.v1":
        raise RuntimeError("decode_cache_schema")
    return payload


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def decode_span(
    *,
    runner: VllmRunner,
    pcm: bytes,
    span: dict[str, Any],
    audio_sha: str,
    model: str,
    cache: dict[str, Any],
    cache_path: Path,
    scratch: Path,
) -> dict[str, Any]:
    key = f"{audio_sha}:{span['start_sample']}:{span['end_sample']}:{model}"
    existing = cache["entries"].get(key)
    if isinstance(existing, dict):
        return existing
    span_pcm = pcm[span["start_sample"] * 2:span["end_sample"] * 2]
    wav_path = scratch / f"{span['start_sample']}-{span['end_sample']}.wav"
    write_wav(wav_path, span_pcm)
    token_cap = canonical_decode_token_cap(sample_count=span["sample_count"])
    started = time.monotonic()
    classification = "valid"
    error = None
    try:
        response = runner.transcribe(wav_path, max_new_tokens=token_cap)
        transcript = str(response.text)
        generated_tokens = int(response.generated_tokens)
        prompt_tokens = int(response.prompt_len)
    except EmptyTranscriptionError as exc:
        transcript = ""
        generated_tokens = 0
        prompt_tokens = 0
        error = str(exc)
        classification = "unparseable" if "zero parsed segments" in error else "empty"
    elapsed = time.monotonic() - started
    segments = span_segments(transcript, sample_count=span["sample_count"])
    result = {
        "classification": classification,
        "error": error,
        "transcript": transcript,
        "segments": [
            {"start": item.start, "end": item.end, "speaker": item.speaker, "text": item.text}
            for item in segments
        ],
        "elapsed_seconds": elapsed,
        "prompt_tokens": prompt_tokens,
        "generated_tokens": generated_tokens,
        "token_cap": token_cap,
        "capped": generated_tokens >= token_cap,
    }
    cache["entries"][key] = result
    save_cache(cache_path, cache)
    return result


def words(text: str) -> list[str]:
    return normalize_reference_text(text).split()


def levenshtein(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for reference_token in reference:
        current = [previous[0] + 1]
        for index, hypothesis_token in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[index] + 1,
                previous[index - 1] + int(reference_token != hypothesis_token),
            ))
        previous = current
    return previous[-1]


def lcs(reference: list[str], hypothesis: list[str]) -> int:
    previous = [0] * (len(hypothesis) + 1)
    for reference_token in reference:
        current = [0]
        for index, hypothesis_token in enumerate(hypothesis, 1):
            current.append(
                previous[index - 1] + 1
                if reference_token == hypothesis_token
                else max(previous[index], current[-1])
            )
        previous = current
    return previous[-1]


def nearest(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "p50": nearest(values, 0.50),
        "p95": nearest(values, 0.95),
        "max": max(values) if values else None,
    }


def load_truth(corpus: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    speakers: dict[str, int] = {}
    segments = []
    reference_words: list[str] = []
    for line in (REPO / corpus["reference"]).read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        speaker_id = speakers.setdefault(item["speaker"], len(speakers))
        segments.append({
            "start": float(item["start"]),
            "end": float(item["end"]),
            "speaker": speaker_id,
            "speaker_name": item["speaker"],
        })
        reference_words.extend(words(item.get("text", "")))
    return segments, reference_words


def truth_for_intervals(
    intervals: list[tuple[float, float]], truth: list[dict[str, Any]]
) -> tuple[int | None, dict[int, float]]:
    overlap: dict[int, float] = {}
    for start, end in intervals:
        for item in truth:
            duration = max(0.0, min(end, item["end"]) - max(start, item["start"]))
            overlap[item["speaker"]] = overlap.get(item["speaker"], 0.0) + duration
    if not overlap or max(overlap.values()) <= 0:
        return None, overlap
    return max(sorted(overlap), key=lambda speaker: overlap[speaker]), overlap


def identity_score(
    *,
    embedder: Any,
    audio_path: Path,
    spans: list[dict[str, Any]],
    truth: list[dict[str, Any]],
    vector_cache: dict[str, list[float]],
) -> dict[str, Any]:
    rows: list[tuple[float, ...]] = []
    vectors: list[np.ndarray] = []
    vector_indices: list[int] = []
    units: list[dict[str, Any]] = []
    for span_index, span in enumerate(spans):
        grouped: dict[str, list[tuple[float, float]]] = {}
        for segment in span["decode"]["segments"]:
            absolute = (
                span["start_sample"] / 16_000 + float(segment["start"]),
                span["start_sample"] / 16_000 + float(segment["end"]),
            )
            if absolute[1] > absolute[0]:
                grouped.setdefault(segment["speaker"], []).append(absolute)
        for local_speaker, intervals in sorted(grouped.items()):
            eligible_intervals = [item for item in intervals if item[1] - item[0] >= 0.5]
            true_speaker, overlap = truth_for_intervals(eligible_intervals or intervals, truth)
            eligible = bool(eligible_intervals) and true_speaker is not None
            duration = sum(end - start for start, end in (eligible_intervals or intervals))
            vector_index = -1
            if eligible:
                vector_key = json.dumps(
                    [str(audio_path), eligible_intervals], separators=(",", ":")
                )
                vector = vector_cache.get(vector_key)
                if vector is None:
                    vector = [float(value) for value in embedder.embed(audio_path, eligible_intervals)]
                    vector_cache[vector_key] = vector
                vectors.append(np.asarray(vector, dtype=np.float32))
                vector_index = len(vectors) - 1
            rows.append((
                float(span_index),
                float(-1 if true_speaker is None else true_speaker),
                min(start for start, _ in intervals),
                max(end for _, end in intervals),
                duration,
                float(eligible),
            ))
            vector_indices.append(vector_index)
            units.append({
                "span_id": span_index,
                "local_speaker": local_speaker,
                "intervals": intervals,
                "eligible_intervals": eligible_intervals,
                "duration_seconds": duration,
                "truth_speaker": true_speaker,
                "truth_overlap_seconds": overlap,
                "embedded": eligible,
            })
    if not rows or not any(row[5] > 0 for row in rows):
        return {"accuracy": 0.0, "canonical_speakers": 0, "units": units, "eligible_units": 0}
    cache = {
        "rows": np.asarray(rows, dtype=np.float64),
        "vecs": np.stack(vectors) if vectors else np.zeros((0, 256), dtype=np.float32),
        "vec_idx": np.asarray(vector_indices, dtype=np.int64),
    }
    identity_bench.SWEEP_EVERY = 60.0
    live, retro, _, _ = identity_bench.simulate(
        cache,
        policy="album",
        min_score=0.35,
        margin=0.1,
        admission=2.0,
        birth_floor=1.0,
        sweep=True,
    )
    accuracy = identity_bench.accuracy(cache["rows"], retro)
    return {
        "accuracy": float(accuracy),
        "canonical_speakers": len({int(item) for item in live if item >= 0}),
        "eligible_units": int(sum(row[5] > 0 for row in rows)),
        "live_assignments": live.tolist(),
        "terminal_sweep_assignments": retro.tolist(),
        "units": units,
    }


def evaluate(
    *,
    corpus: dict[str, Any],
    candidate: dict[str, Any],
    runner: VllmRunner,
    model: str,
    embedder: Any,
    cache: dict[str, Any],
    cache_path: Path,
    vector_cache: dict[str, list[float]],
    render_bound_ms: float,
) -> dict[str, Any]:
    audio_path = REPO / corpus["audio"]
    pcm = read_audio(audio_path)
    spans = plan_spans(pcm, candidate)
    truth, reference_words = load_truth(corpus)
    with tempfile.TemporaryDirectory(prefix="moss-cap-sweep-") as temporary:
        scratch = Path(temporary)
        for span in spans:
            span["decode"] = decode_span(
                runner=runner,
                pcm=pcm,
                span=span,
                audio_sha=corpus["audio_sha256"],
                model=model,
                cache=cache,
                cache_path=cache_path,
                scratch=scratch,
            )
    hypothesis_words = [
        token
        for span in spans
        for segment in span["decode"]["segments"]
        for token in words(segment["text"])
    ]
    distance = levenshtein(reference_words, hypothesis_words)
    matches = lcs(reference_words, hypothesis_words)
    available = 0.0
    finishes: list[float] = []
    queue_waits: list[float] = []
    first_visible: list[float] = []
    last_visible: list[float] = []
    max_depth = 0
    for span in spans:
        arrival = float(span["freeze_seconds"])
        elapsed = float(span["decode"]["elapsed_seconds"])
        depth = sum(finish > arrival for finish in finishes)
        max_depth = max(max_depth, depth)
        started = max(arrival, available)
        wait = started - arrival
        finish = started + elapsed
        finishes.append(finish)
        available = finish
        tail = wait + elapsed + render_bound_ms / 1_000
        queue_waits.append(wait)
        last_visible.append(tail)
        first_visible.append(float(span["duration_seconds"]) + tail)
    identity = identity_score(
        embedder=embedder,
        audio_path=audio_path,
        spans=spans,
        truth=truth,
        vector_cache=vector_cache,
    )
    classifications = [span["decode"]["classification"] for span in spans]
    return {
        "corpus_id": corpus["id"],
        "role": corpus["role"],
        "candidate": candidate,
        "audio_sha256": corpus["audio_sha256"],
        "reference_sha256": corpus["reference_sha256"],
        "reference_word_count": len(reference_words),
        "hypothesis_word_count": len(hypothesis_words),
        "word_error_distance": distance,
        "word_error_rate": distance / max(1, len(reference_words)),
        "true_lcs_matches": matches,
        "content_recall": matches / max(1, len(reference_words)),
        "request_count": len(spans),
        "empty_count": classifications.count("empty"),
        "empty_rate": classifications.count("empty") / len(spans),
        "unparseable_count": classifications.count("unparseable"),
        "unparseable_rate": classifications.count("unparseable") / len(spans),
        "decode_capped_count": sum(bool(span["decode"]["capped"]) for span in spans),
        "decode_capped_rate": sum(bool(span["decode"]["capped"]) for span in spans) / len(spans),
        "decode_elapsed_seconds": distribution([
            float(span["decode"]["elapsed_seconds"]) for span in spans
        ]),
        "queue_wait_seconds": distribution(queue_waits),
        "max_queue_depth": max_depth,
        "first_word_visible_seconds": distribution(first_visible),
        "last_word_visible_seconds": distribution(last_visible),
        "identity": identity,
        "spans": spans,
    }


def aggregate(results: dict[str, dict[str, Any]], candidate_id: str, role: str) -> dict[str, Any]:
    rows = [
        candidates[candidate_id]
        for corpus_id, candidates in results.items()
        if candidates.get(candidate_id) is not None and candidates[candidate_id]["role"] == role
    ]
    return {
        "corpus_count": len(rows),
        "mean_wer": statistics.fmean(row["word_error_rate"] for row in rows),
        "mean_content_recall": statistics.fmean(row["content_recall"] for row in rows),
        "mean_identity_accuracy": statistics.fmean(row["identity"]["accuracy"] for row in rows),
        "mean_canonical_speakers": statistics.fmean(row["identity"]["canonical_speakers"] for row in rows),
        "total_requests": sum(row["request_count"] for row in rows),
        "empty_rate": sum(row["empty_count"] for row in rows) / sum(row["request_count"] for row in rows),
        "unparseable_rate": sum(row["unparseable_count"] for row in rows) / sum(row["request_count"] for row in rows),
        "decode_capped_rate": sum(row["decode_capped_count"] for row in rows) / sum(row["request_count"] for row in rows),
        "max_queue_depth": max(row["max_queue_depth"] for row in rows),
        "median_first_word_p95_seconds": statistics.median(
            row["first_word_visible_seconds"]["p95"] for row in rows
        ),
        "worst_first_word_p95_seconds": max(
            row["first_word_visible_seconds"]["p95"] for row in rows
        ),
    }


def guards(
    results: dict[str, dict[str, Any]],
    candidate_id: str,
    role: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    baseline_id = contract["discovery_selection"]["baseline_id"]
    baseline = aggregate(results, baseline_id, role)
    candidate = aggregate(results, candidate_id, role)
    per = contract["discovery_selection"]["per_corpus_guards"]
    agg = contract["discovery_selection"]["aggregate_guards"]
    per_corpus = {}
    for corpus_id, candidates in results.items():
        if candidate_id not in candidates or candidates[candidate_id]["role"] != role:
            continue
        base = candidates[baseline_id]
        item = candidates[candidate_id]
        checks = {
            "wer": item["word_error_rate"] - base["word_error_rate"] <= per["max_wer_increase"],
            "content_recall": base["content_recall"] - item["content_recall"] <= per["max_content_recall_loss"],
            "identity": base["identity"]["accuracy"] - item["identity"]["accuracy"] <= per["max_identity_accuracy_loss"],
            "speaker_count": item["identity"]["canonical_speakers"] - base["identity"]["canonical_speakers"] <= per["max_canonical_speaker_increase"],
            "empty_rate": item["empty_rate"] - base["empty_rate"] <= per["max_empty_rate_increase"],
        }
        per_corpus[corpus_id] = {"passes": all(checks.values()), "checks": checks}
    request_multiplier = candidate["total_requests"] / baseline["total_requests"]
    improvement_ms = (
        baseline["median_first_word_p95_seconds"]
        - candidate["median_first_word_p95_seconds"]
    ) * 1_000
    aggregate_checks = {
        "wer": candidate["mean_wer"] - baseline["mean_wer"] <= agg["max_wer_increase"],
        "content_recall": baseline["mean_content_recall"] - candidate["mean_content_recall"] <= agg["max_content_recall_loss"],
        "identity": baseline["mean_identity_accuracy"] - candidate["mean_identity_accuracy"] <= agg["max_identity_accuracy_loss"],
        "request_multiplier": request_multiplier <= agg["max_request_multiplier"],
        "queue_depth": candidate["max_queue_depth"] <= agg["max_queue_depth"],
        "decode_capped": candidate["decode_capped_rate"] <= agg["max_decode_capped_rate"],
        "unparseable": candidate["unparseable_rate"] <= agg["max_unparseable_rate"],
        "latency": improvement_ms >= agg["min_median_first_word_p95_improvement_ms"],
    }
    return {
        "passes": all(item["passes"] for item in per_corpus.values()) and all(aggregate_checks.values()),
        "per_corpus": per_corpus,
        "aggregate_checks": aggregate_checks,
        "request_multiplier": request_multiplier,
        "median_first_word_p95_improvement_ms": improvement_ms,
        "baseline": baseline,
        "candidate": candidate,
    }


def main() -> int:
    cli = args()
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    contract_sha = sha256(CONTRACT_PATH)
    if contract_sha != "e7d5b3e231eb82e98c5f26198578163c17402d2a656ebee91890804c4625aeab":
        raise RuntimeError(f"contract_changed_after_validation:{contract_sha}")
    model = discover_model(cli.base_url, cli.timeout_seconds)
    runner = VllmRunner(base_url=cli.base_url, model=model, api_key=None, timeout=cli.timeout_seconds)
    model_path = REPO / contract["production_contract"]["identity"]["model_path"]
    embedder = speaker_identity._OnnxWeSpeakerEmbedder(model_path, device="cpu")
    cache = load_cache(cli.cache)
    vector_cache: dict[str, list[float]] = {}
    candidates = {item["id"]: item for item in contract["candidates"]}
    baseline_id = contract["discovery_selection"]["baseline_id"]
    results: dict[str, dict[str, Any]] = {item["id"]: {} for item in contract["corpora"]}
    render_bound = float(contract["production_contract"]["reader_render_bound_ms"])

    for corpus in [item for item in contract["corpora"] if item["role"] == "discovery"]:
        for candidate in contract["candidates"]:
            print(f"MEASURE discovery {corpus['id']} {candidate['id']}", flush=True)
            results[corpus["id"]][candidate["id"]] = evaluate(
                corpus=corpus,
                candidate=candidate,
                runner=runner,
                model=model,
                embedder=embedder,
                cache=cache,
                cache_path=cli.cache,
                vector_cache=vector_cache,
                render_bound_ms=render_bound,
            )

    discovery_guards = {
        candidate_id: guards(results, candidate_id, "discovery", contract)
        for candidate_id in candidates
        if candidate_id != baseline_id
    }
    passing = [candidate_id for candidate_id, item in discovery_guards.items() if item["passes"]]
    order = {item["id"]: index for index, item in enumerate(contract["candidates"])}
    selected = min(
        passing,
        key=lambda candidate_id: (
            discovery_guards[candidate_id]["candidate"]["median_first_word_p95_seconds"],
            discovery_guards[candidate_id]["candidate"]["total_requests"],
            order[candidate_id],
        ),
        default=None,
    )

    validation_ids = [baseline_id] + ([] if selected is None else [selected])
    for corpus in [item for item in contract["corpora"] if item["role"] == "validation"]:
        for candidate_id in validation_ids:
            print(f"MEASURE validation {corpus['id']} {candidate_id}", flush=True)
            results[corpus["id"]][candidate_id] = evaluate(
                corpus=corpus,
                candidate=candidates[candidate_id],
                runner=runner,
                model=model,
                embedder=embedder,
                cache=cache,
                cache_path=cli.cache,
                vector_cache=vector_cache,
                render_bound_ms=render_bound,
            )

    validation = None if selected is None else guards(results, selected, "validation", contract)
    validation_passes = False
    if validation is not None:
        validation_contract = contract["validation_gate"]
        improvements = []
        for corpus_id, candidate_results in results.items():
            if selected not in candidate_results or candidate_results[selected]["role"] != "validation":
                continue
            improvements.append(
                (candidate_results[baseline_id]["first_word_visible_seconds"]["p95"]
                 - candidate_results[selected]["first_word_visible_seconds"]["p95"]) * 1_000
            )
        validation["replication_checks"] = {
            "quality_and_load": validation["passes"],
            "median_latency": statistics.median(improvements) >= validation_contract["min_median_first_word_p95_improvement_ms"],
            "worst_latency": min(improvements) >= validation_contract["min_worst_corpus_first_word_p95_improvement_ms"],
        }
        validation["per_corpus_first_word_p95_improvement_ms"] = improvements
        validation_passes = all(validation["replication_checks"].values())

    document = {
        "schema": "moss-live-cap-silence-sweep-result.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {"path": str(CONTRACT_PATH.relative_to(REPO)), "sha256": contract_sha},
        "scope": contract["scope"],
        "vllm": {"base_url": cli.base_url, "model": model},
        "production_contract": contract["production_contract"],
        "discovery": {"guards": discovery_guards, "selected_candidate": selected},
        "validation": validation,
        "selection": {
            "verdict": "CANDIDATE_REPLICATED" if validation_passes else "NO_POLICY_CHANGE",
            "candidate": selected if validation_passes else None,
            "discovery_candidate": selected,
            "next_step": (
                "implement the replicated endpoint policy via regenerated manifest hashes"
                if validation_passes
                else "retain the deployed endpoint policy"
            ),
        },
        "corpora": results,
        "decode_cache": {"path": str(cli.cache), "entry_count": len(cache["entries"])},
    }
    raw = json.dumps(document, indent=2, sort_keys=True) + "\n"
    document["result_sha256_without_self"] = hashlib.sha256(raw.encode()).hexdigest()
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    cli.output.parent.mkdir(parents=True, exist_ok=True)
    cli.output.write_text(encoded, encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
