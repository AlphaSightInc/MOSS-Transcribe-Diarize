#!/usr/bin/env python3
"""PROTOTYPE -- throwaway current-lane measurement for 2.5 s versus 1.0 s caps.

Question: how much first-publication latency does a 1.0 s hard cap buy, and what
quality/compute cost does it impose before a longer-context correction exists?

This file deliberately owns no model client.  The integrated runner serializes GPU
work and supplies:

    decoder(case_id, span_id, start_sample, end_sample, pcm_bytes) -> {
        "transcript": str,                 # raw joint-MOSS transcript
        "decode_elapsed_sec": float,
        "generated_tokens": int,
        "canonical_transcript": str,       # optional WeSpeaker-relabeled transcript
    }

Without a decoder, the 2.5 s arm reads the frozen production replay and the 1.0 s
arm prints its exact production-VAD span plan with quality explicitly unmeasured.

One standalone inspection command (no GPU calls):

    .venv/bin/python \
      prototypes/streaming-diarization/live-multiview-prototype/lane_current.py
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import wave
from pathlib import Path
from typing import Any, Callable, Mapping


REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_endpoint import (  # noqa: E402
    EndpointPolicy,
    EndpointPolicyConfig,
)
from moss_transcribe_diarize.app.live_provider_bundle import WebRtcSpeechProvider  # noqa: E402
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    calculate_diarization,
    calculate_tbsa,
)


SAMPLE_RATE = 16_000
SAMPLE_WIDTH_BYTES = 2
FRAME_SAMPLES = 8_000
VAD_FRAME_SAMPLES = 160
VAD_MODE = 1
MIN_SPEECH_SAMPLES = 1_600
MIN_SILENCE_SAMPLES = 8_000
PADDING_SAMPLES = 1_600
CASES = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
CORPUS_ROOT = (
    REPO
    / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
)
DEFAULT_CACHED_ROOT = Path(
    "/private/tmp/claude-501/"
    "-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/"
    "bd3632af-da27-408f-8e03-ecd56a586e8d/scratchpad/"
    "remeasure-20260824T160130"
)

Decoder = Callable[[str, int, int, int, bytes], Mapping[str, Any]]


def _read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        contract = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        )
        if contract != (1, SAMPLE_WIDTH_BYTES, SAMPLE_RATE, "NONE"):
            raise RuntimeError(f"unsupported audio contract {contract}: {path}")
        return source.readframes(source.getnframes())


def _load_reference(case_dir: Path) -> list[Segment]:
    reference: list[Segment] = []
    for line in (case_dir / "reference.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        reference.append(
            Segment(
                start=float(item["start"]),
                end=float(item["end"]),
                speaker=str(item["speaker"]),
                text=str(item["text"]),
            )
        )
    return reference


def _absolute_segments(transcript: str, *, start_sample: int, end_sample: int) -> list[Segment]:
    base = start_sample / SAMPLE_RATE
    return [
        Segment(
            start=base + parsed.start,
            end=base + parsed.end,
            speaker=parsed.speaker,
            text=parsed.text,
        )
        for parsed in span_segments(transcript, sample_count=end_sample - start_sample)
        if parsed.end > parsed.start and parsed.text.strip()
    ]


def _segment_record(segment: Segment) -> dict[str, Any]:
    return {
        "start": segment.start,
        "end": segment.end,
        "speaker": segment.speaker,
        "text": segment.text,
    }


def _plan_spans(pcm: bytes, *, cap_seconds: float) -> list[dict[str, Any]]:
    """Run the shipped WebRTC adapter and endpoint state, not fixed slicing."""
    import webrtcvad

    provider = WebRtcSpeechProvider(
        vad=webrtcvad.Vad(VAD_MODE),
        frame_samples=VAD_FRAME_SAMPLES,
        sample_rate=SAMPLE_RATE,
    )
    policy = EndpointPolicy(
        EndpointPolicyConfig(
            min_speech_samples=MIN_SPEECH_SAMPLES,
            min_silence_samples=MIN_SILENCE_SAMPLES,
            pre_speech_padding_samples=PADDING_SAMPLES,
            post_speech_padding_samples=PADDING_SAMPLES,
            hard_cap_samples=round(cap_seconds * SAMPLE_RATE),
        )
    )
    total_samples = len(pcm) // SAMPLE_WIDTH_BYTES
    endpoint_spans = []
    for sequence, start_sample in enumerate(range(0, total_samples, FRAME_SAMPLES)):
        end_sample = min(total_samples, start_sample + FRAME_SAMPLES)
        frame = AudioFrame(
            sequence=sequence,
            pcm=pcm[start_sample * SAMPLE_WIDTH_BYTES : end_sample * SAMPLE_WIDTH_BYTES],
            sample_count=end_sample - start_sample,
            sample_rate=SAMPLE_RATE,
        )
        observations = provider.observe(
            frame=frame,
            start_sample=start_sample,
            end_sample=end_sample,
        )
        for observation in observations:
            endpoint_spans.extend(policy.observe(observation))
    endpoint_spans.extend(policy.stop())
    return [
        {
            "span_id": span_id,
            "start_sample": span.start_sample,
            "end_sample": span.end_sample,
            "start_sec": span.start_sample / SAMPLE_RATE,
            "end_sec": span.end_sample / SAMPLE_RATE,
            "duration_sec": span.sample_count / SAMPLE_RATE,
            "endpoint_reason": span.reason,
        }
        for span_id, span in enumerate(endpoint_spans)
    ]


def _trace_path(cached: str | Path | Mapping[str, str | Path], case_id: str) -> Path:
    value = cached.get(case_id) if isinstance(cached, Mapping) else cached
    if value is None:
        raise FileNotFoundError(f"no cached current run for {case_id}")
    base = Path(value)
    candidates = (
        base,
        base / "trace.jsonl",
        base / "run-001/trace.jsonl",
        base / case_id / "run-001/trace.jsonl",
        base / case_id / "live/run-001/trace.jsonl",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"cached trace not found for {case_id} below {base}")


def _quality(
    reference: list[Segment],
    hypothesis: list[Segment],
    *,
    canonical_speakers: bool,
) -> dict[str, Any]:
    # WER and text coverage do not use labels.  TBSA and DER do, so raw per-request
    # S01/S02 labels are never presented as session-speaker measurements.
    text_metrics = calculate_tbsa(reference, hypothesis)
    if not canonical_speakers:
        return {
            "measurement_status": "text_only_raw_local_speaker_labels",
            "tbsa": None,
            "wer": text_metrics["wer"],
            "coverage": text_metrics["text_coverage"],
            "text_speaker_accuracy": None,
            "der": None,
            "der_components": None,
        }
    diarization = calculate_diarization(reference, hypothesis)
    return {
        "measurement_status": "measured_canonical_speaker_labels",
        "tbsa": text_metrics["composite"],
        "wer": text_metrics["wer"],
        "coverage": text_metrics["text_coverage"],
        "text_speaker_accuracy": text_metrics["text_speaker_accuracy"],
        "der": diarization["der"],
        "der_components": {
            "miss": diarization["miss"],
            "false_alarm": diarization["false_alarm"],
            "speaker_confusion": diarization["speaker_confusion"],
        },
    }


def _unmeasured_quality(reason: str) -> dict[str, Any]:
    return {
        "measurement_status": reason,
        "tbsa": None,
        "wer": None,
        "coverage": None,
        "text_speaker_accuracy": None,
        "der": None,
        "der_components": None,
    }


def _first_publication(rows: list[dict[str, Any]], segments_by_span: dict[int, list[Segment]]) -> dict[str, Any]:
    for row in rows:
        segments = segments_by_span.get(int(row["span_id"]), [])
        if not segments:
            continue
        published = row.get("publication_session_sec")
        first_word = min(segment.start for segment in segments)
        return {
            "measurement_status": row.get("publication_timing_status"),
            "span_id": row["span_id"],
            "capture_bound_sec": row["end_sec"],
            "publication_from_session_start_sec": published,
            "first_word_audio_start_sec": first_word,
            "first_word_age_at_publication_sec": None if published is None else published - first_word,
        }
    return {
        "measurement_status": "no_nonempty_publication",
        "span_id": None,
        "capture_bound_sec": None,
        "publication_from_session_start_sec": None,
        "first_word_audio_start_sec": None,
        "first_word_age_at_publication_sec": None,
    }


def _decode_accounting(rows: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [row for row in rows if isinstance(row.get("decode_elapsed_sec"), (int, float))]
    elapsed = [float(row["decode_elapsed_sec"]) for row in measured]
    decoded_audio = sum(float(row["duration_sec"]) for row in measured)
    token_values = [
        int(row["generated_tokens"])
        for row in rows
        if isinstance(row.get("generated_tokens"), int)
    ]
    return {
        "measurement_status": (
            "measured"
            if len(measured) == len(rows)
            else "unmeasured"
            if not measured
            else "partially_measured"
        ),
        "request_count": len(rows),
        "measured_request_count": len(measured),
        "decoded_audio_sec": decoded_audio,
        "decode_elapsed_sec": sum(elapsed) if elapsed else None,
        "gpu_decode_rtf": sum(elapsed) / decoded_audio if decoded_audio else None,
        "decode_elapsed_p50_sec": statistics.median(elapsed) if elapsed else None,
        "decode_elapsed_p95_sec": _percentile(elapsed, 0.95),
        "generated_tokens": sum(token_values) if token_values else None,
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(fraction * len(ordered))))
    return ordered[index]


def _cached_case(case_id: str, case_dir: Path, trace_path: Path) -> dict[str, Any]:
    trace = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    terminal = next(row for row in trace if row.get("kind") == "terminal")
    committed = terminal["snapshot"]["session"]["committed"]
    frozen: dict[int, dict[str, Any]] = {}
    processed: dict[int, dict[str, Any]] = {}
    for row in trace:
        if row.get("kind") != "service_event" or not isinstance(row.get("event"), dict):
            continue
        event = row["event"]
        payload = event.get("payload") or {}
        if event.get("kind") == "span_frozen":
            frozen[int(payload["span_id"])] = payload
        elif event.get("kind") == "canonical_processed":
            processed[int(payload["span_id"])] = payload

    rows: list[dict[str, Any]] = []
    hypothesis: list[Segment] = []
    segments_by_span: dict[int, list[Segment]] = {}
    for item in committed:
        span_id = int(item["span_id"])
        start_sample = int(item["start_sample"])
        end_sample = int(item["end_sample"])
        transcript = str(item.get("transcript") or "")
        canonical = str(item.get("revised_transcript") or transcript)
        segments = _absolute_segments(canonical, start_sample=start_sample, end_sample=end_sample)
        segments_by_span[span_id] = segments
        hypothesis.extend(segments)
        event = processed.get(span_id, {})
        queued_to_processed_ms = event.get("queued_to_processed_ms")
        decode_elapsed = event.get("canonical_decode_elapsed_sec")
        publication = (
            end_sample / SAMPLE_RATE + float(queued_to_processed_ms) / 1_000
            if isinstance(queued_to_processed_ms, (int, float))
            else None
        )
        reason = frozen.get(span_id, {}).get("reason")
        if reason is None:
            reason = "hard_cap" if end_sample - start_sample == 40_000 else "stop_flush(untraced)"
        rows.append(
            {
                "span_id": span_id,
                "start_sample": start_sample,
                "end_sample": end_sample,
                "start_sec": start_sample / SAMPLE_RATE,
                "end_sec": end_sample / SAMPLE_RATE,
                "duration_sec": (end_sample - start_sample) / SAMPLE_RATE,
                "endpoint_reason": reason,
                "raw_transcript": transcript,
                "canonical_transcript": canonical,
                "absolute_segments": [_segment_record(segment) for segment in segments],
                "classification": "valid" if segments else ("empty" if not transcript else "unparseable"),
                "empty_reason": event.get("empty_reason"),
                "decode_elapsed_sec": decode_elapsed,
                "processing_elapsed_sec": (
                    float(event["canonical_processing_elapsed_ms"]) / 1_000
                    if isinstance(event.get("canonical_processing_elapsed_ms"), (int, float))
                    else None
                ),
                "queue_wait_sec": (
                    float(event["queue_wait_ms"]) / 1_000
                    if isinstance(event.get("queue_wait_ms"), (int, float))
                    else None
                ),
                "publication_session_sec": publication,
                "publication_timing_status": "modelled_from_session_clock_plus_measured_queue_to_processed",
                "generated_tokens": None,
            }
        )

    quality = _quality(_load_reference(case_dir), hypothesis, canonical_speakers=True)
    empty = [row for row in rows if row["classification"] != "valid"]
    return {
        "case_id": case_id,
        "measurement_status": "cached_production_replay",
        "trace_path": str(trace_path),
        "duration_sec": len(_read_pcm(case_dir / "audio.wav")) / SAMPLE_WIDTH_BYTES / SAMPLE_RATE,
        "span_count": len(rows),
        "endpoint_reason_counts": _reason_counts(rows),
        "empty_or_unparseable_count": len(empty),
        "empty_count": sum(row["classification"] == "empty" for row in rows),
        "unparseable_count": sum(row["classification"] == "unparseable" for row in rows),
        "quality": quality,
        "first_publication": _first_publication(rows, segments_by_span),
        "correction_latency": {
            "measurement_status": "not_applicable_no_text_correction_lane",
            "seconds": None,
        },
        "decode": _decode_accounting(rows),
        "spans": rows,
    }


def _planned_case(case_id: str, case_dir: Path, cap_seconds: float) -> dict[str, Any]:
    pcm = _read_pcm(case_dir / "audio.wav")
    rows = _plan_spans(pcm, cap_seconds=cap_seconds)
    return {
        "case_id": case_id,
        "measurement_status": "production_vad_plan_decode_unmeasured",
        "trace_path": None,
        "duration_sec": len(pcm) / SAMPLE_WIDTH_BYTES / SAMPLE_RATE,
        "span_count": len(rows),
        "endpoint_reason_counts": _reason_counts(rows),
        "empty_or_unparseable_count": None,
        "empty_count": None,
        "unparseable_count": None,
        "quality": _unmeasured_quality("unmeasured_no_decoder"),
        "first_publication": {
            "measurement_status": "analytic_capture_bound_only",
            "span_id": rows[0]["span_id"] if rows else None,
            "capture_bound_sec": rows[0]["end_sec"] if rows else None,
            "publication_from_session_start_sec": None,
            "first_word_audio_start_sec": None,
            "first_word_age_at_publication_sec": None,
        },
        "correction_latency": {
            "measurement_status": "not_applicable_no_text_correction_lane",
            "seconds": None,
        },
        "decode": _decode_accounting(rows),
        "spans": rows,
    }


def _decoded_case(
    case_id: str,
    case_dir: Path,
    cap_seconds: float,
    decoder: Decoder,
) -> dict[str, Any]:
    pcm = _read_pcm(case_dir / "audio.wav")
    rows = _plan_spans(pcm, cap_seconds=cap_seconds)
    raw_hypothesis: list[Segment] = []
    canonical_hypothesis: list[Segment] = []
    raw_by_span: dict[int, list[Segment]] = {}
    canonical_available = True
    worker_available_sec = 0.0
    for row in rows:
        start_sample = int(row["start_sample"])
        end_sample = int(row["end_sample"])
        result = dict(
            decoder(
                case_id,
                int(row["span_id"]),
                start_sample,
                end_sample,
                pcm[start_sample * SAMPLE_WIDTH_BYTES : end_sample * SAMPLE_WIDTH_BYTES],
            )
        )
        raw = str(result.get("transcript") or "")
        raw_segments = _absolute_segments(raw, start_sample=start_sample, end_sample=end_sample)
        raw_by_span[int(row["span_id"])] = raw_segments
        raw_hypothesis.extend(raw_segments)
        has_canonical = "canonical_transcript" in result
        canonical_available = canonical_available and has_canonical
        canonical = str(result.get("canonical_transcript") or "") if has_canonical else raw
        canonical_segments = _absolute_segments(
            canonical,
            start_sample=start_sample,
            end_sample=end_sample,
        )
        canonical_hypothesis.extend(canonical_segments)
        decode_elapsed = float(result["decode_elapsed_sec"])
        processing_elapsed = float(result.get("processing_elapsed_sec", decode_elapsed))
        available = float(row["end_sec"])
        processing_start = max(available, worker_available_sec)
        publication = processing_start + processing_elapsed
        worker_available_sec = publication
        classification = str(
            result.get(
                "classification",
                "valid" if raw_segments else ("empty" if not raw else "unparseable"),
            )
        )
        row.update(
            {
                "raw_transcript": raw,
                "canonical_transcript": canonical if has_canonical else None,
                "absolute_segments": [_segment_record(segment) for segment in raw_segments],
                "canonical_absolute_segments": (
                    [_segment_record(segment) for segment in canonical_segments]
                    if has_canonical
                    else None
                ),
                "classification": classification,
                "empty_reason": result.get("empty_reason"),
                "decode_elapsed_sec": decode_elapsed,
                "processing_elapsed_sec": processing_elapsed,
                "queue_wait_sec": processing_start - available,
                "publication_session_sec": publication,
                "publication_timing_status": "modelled_serial_worker_from_measured_callback_elapsed",
                "generated_tokens": result.get("generated_tokens"),
            }
        )

    hypothesis = canonical_hypothesis if canonical_available else raw_hypothesis
    quality = _quality(
        _load_reference(case_dir),
        hypothesis,
        canonical_speakers=canonical_available,
    )
    empty = [row for row in rows if row["classification"] != "valid"]
    return {
        "case_id": case_id,
        "measurement_status": "fresh_serialized_decode",
        "trace_path": None,
        "duration_sec": len(pcm) / SAMPLE_WIDTH_BYTES / SAMPLE_RATE,
        "span_count": len(rows),
        "endpoint_reason_counts": _reason_counts(rows),
        "empty_or_unparseable_count": len(empty),
        "empty_count": sum(row["classification"] == "empty" for row in rows),
        "unparseable_count": sum(row["classification"] == "unparseable" for row in rows),
        "quality": quality,
        "first_publication": _first_publication(rows, raw_by_span),
        "correction_latency": {
            "measurement_status": "not_applicable_no_text_correction_lane",
            "seconds": None,
        },
        "decode": _decode_accounting(rows),
        "spans": rows,
    }


def _reason_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        reason = str(row["endpoint_reason"])
        counts[reason] = counts.get(reason, 0) + 1
    return dict(sorted(counts.items()))


def _aggregate(cases: Mapping[str, dict[str, Any]]) -> dict[str, Any]:
    def mean(path: tuple[str, ...]) -> float | None:
        values = []
        for case in cases.values():
            value: Any = case
            for key in path:
                value = value[key]
            if isinstance(value, (int, float)):
                values.append(float(value))
        return statistics.mean(values) if values else None

    decoded_audio = sum(float(case["decode"]["decoded_audio_sec"]) for case in cases.values())
    elapsed = sum(
        float(case["decode"]["decode_elapsed_sec"] or 0.0) for case in cases.values()
    )
    return {
        "case_count": len(cases),
        "source_audio_sec": sum(float(case["duration_sec"]) for case in cases.values()),
        "span_count": sum(int(case["span_count"]) for case in cases.values()),
        "empty_or_unparseable_count": (
            sum(int(case["empty_or_unparseable_count"]) for case in cases.values())
            if all(isinstance(case["empty_or_unparseable_count"], int) for case in cases.values())
            else None
        ),
        "macro_quality": {
            "tbsa": mean(("quality", "tbsa")),
            "wer": mean(("quality", "wer")),
            "coverage": mean(("quality", "coverage")),
            "der": mean(("quality", "der")),
        },
        "mean_first_publication_sec": mean(
            ("first_publication", "publication_from_session_start_sec")
        ),
        "mean_first_word_age_at_publication_sec": mean(
            ("first_publication", "first_word_age_at_publication_sec")
        ),
        "decode_elapsed_sec": elapsed if decoded_audio else None,
        "decoded_audio_sec": decoded_audio,
        "gpu_decode_rtf": elapsed / decoded_audio if decoded_audio else None,
    }


def run_current_lane(
    *,
    cap_seconds: float,
    corpus_root: str | Path = CORPUS_ROOT,
    cached_live_roots: str | Path | Mapping[str, str | Path] = DEFAULT_CACHED_ROOT,
    decoder: Decoder | None = None,
) -> dict[str, Any]:
    if cap_seconds not in (1.0, 2.5):
        raise ValueError("current-lane prototype accepts only the preregistered 1.0 or 2.5 second cap")
    root = Path(corpus_root)
    cases: dict[str, dict[str, Any]] = {}
    for case_id in CASES:
        case_dir = root / case_id
        if decoder is not None:
            result = _decoded_case(case_id, case_dir, cap_seconds, decoder)
        elif cap_seconds == 2.5:
            result = _cached_case(case_id, case_dir, _trace_path(cached_live_roots, case_id))
        else:
            result = _planned_case(case_id, case_dir, cap_seconds)
        cases[case_id] = result
    return {
        "schema": "moss-live-multiview-current-prototype.v1",
        "throwaway": True,
        "question": (
            "Does reducing the provisional hard cap from 2.5 s to 1.0 s materially improve "
            "first publication, and what quality/GPU cost does it impose before correction?"
        ),
        "arm": f"current-{cap_seconds:g}s",
        "cap_seconds": cap_seconds,
        "production_semantics": {
            "sample_rate": SAMPLE_RATE,
            "capture_frame_samples": FRAME_SAMPLES,
            "webrtc_vad_mode": VAD_MODE,
            "webrtc_vad_frame_samples": VAD_FRAME_SAMPLES,
            "min_speech_samples": MIN_SPEECH_SAMPLES,
            "min_silence_samples": MIN_SILENCE_SAMPLES,
            "pre_speech_padding_samples": PADDING_SAMPLES,
            "post_speech_padding_samples": PADDING_SAMPLES,
            "hard_cap_samples": round(cap_seconds * SAMPLE_RATE),
        },
        "metric_contract": {
            "quality": "repo calculate_tbsa/calculate_diarization on full 60 s references",
            "gpu_rtf": "sum model decode elapsed / sum audio seconds submitted to decoder",
            "first_publication": (
                "session-clock span end plus measured/modelled serialized processing; "
                "not browser paint latency"
            ),
            "correction_latency": "not applicable: this arm has no text correction lane",
            "speaker_guard": (
                "TBSA/DER withheld for fresh raw MOSS labels unless decoder returns "
                "canonical_transcript after production identity relabeling"
            ),
        },
        "cases": cases,
        "aggregate": _aggregate(cases),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cap", choices=("1", "2.5", "both"), default="both")
    parser.add_argument("--corpus-root", type=Path, default=CORPUS_ROOT)
    parser.add_argument("--cached-root", type=Path, default=DEFAULT_CACHED_ROOT)
    args = parser.parse_args(argv)
    caps = (2.5, 1.0) if args.cap == "both" else (float(args.cap),)
    state = [
        run_current_lane(
            cap_seconds=cap,
            corpus_root=args.corpus_root,
            cached_live_roots=args.cached_root,
        )
        for cap in caps
    ]
    print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
