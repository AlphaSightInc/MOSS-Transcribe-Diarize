#!/usr/bin/env python3
"""PROTOTYPE: isolate live/offline identity divergence from one retained tape.

Question: does the captured signal fail before mixing, during mixing, or only after
truth-derived evidence intervals are replaced by the live endpointer/ASR path?

One command prints full derived state and writes JSON. Raw PCM and generated WAVs stay
under the tape session directory; only hashes and numeric metrics leave it.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import sys
import wave
from pathlib import Path

import numpy as np
from scipy import signal


SAMPLE_RATE = 16_000
PCM_SCALE = 32_768.0
HEADROOM_GAIN = 10 ** (-6 / 20)
LIMITER_THRESHOLD = 0.98
LIMITER_RANGE = 1.0 - LIMITER_THRESHOLD


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tape-index", type=Path, required=True)
    parser.add_argument("--source-wav", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--identity-asset", type=Path, required=True)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--corpus-start-sample", type=int, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != SAMPLE_RATE:
            raise ValueError(f"{path}: expected mono PCM16 at {SAMPLE_RATE} Hz")
        return np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").copy()


def write_wav(path: Path, pcm: np.ndarray) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(np.asarray(pcm, dtype="<i2").tobytes())


def read_pcm(path: Path) -> np.ndarray:
    return np.fromfile(path, dtype="<i2")


def dbfs(value: float) -> float:
    return -math.inf if value <= 0 else 20.0 * math.log10(value / PCM_SCALE)


def basic_metrics(pcm: np.ndarray) -> dict[str, float | int]:
    values = pcm.astype(np.float64)
    rms = float(np.sqrt(np.mean(values * values))) if len(values) else 0.0
    block = SAMPLE_RATE // 10
    trimmed = values[: len(values) // block * block]
    block_rms = (
        np.sqrt(np.mean(trimmed.reshape(-1, block) ** 2, axis=1))
        if len(trimmed)
        else np.zeros(0)
    )
    return {
        "samples": int(len(pcm)),
        "duration_seconds": len(pcm) / SAMPLE_RATE,
        "rms_dbfs": dbfs(rms),
        "peak_fraction": float(np.max(np.abs(values)) / PCM_SCALE) if len(values) else 0.0,
        "clipped_fraction": float(np.mean(np.abs(values) >= 32760)) if len(values) else 0.0,
        "zero_fraction": float(np.mean(values == 0)) if len(values) else 1.0,
        "silent_100ms_fraction": float(np.mean(block_rms < PCM_SCALE * 10 ** (-60 / 20))) if len(block_rms) else 1.0,
    }


def energy_envelope(pcm: np.ndarray) -> np.ndarray:
    block = SAMPLE_RATE // 100
    values = pcm[: len(pcm) // block * block].astype(np.float64).reshape(-1, block)
    envelope = np.sqrt(np.mean(values * values, axis=1))
    envelope -= np.mean(envelope)
    scale = np.std(envelope)
    return envelope / scale if scale else envelope


def coarse_start(track: np.ndarray, source: np.ndarray, expected_sample: int) -> tuple[int, float]:
    track_env = energy_envelope(track)
    source_env = energy_envelope(source)
    correlation = signal.correlate(track_env, source_env, mode="full", method="fft")
    lags = signal.correlation_lags(len(track_env), len(source_env), mode="full")
    expected_block = round(expected_sample / (SAMPLE_RATE // 100))
    allowed = np.abs(lags - expected_block) <= 10 * 100
    selected = np.flatnonzero(allowed)
    peak = selected[int(np.argmax(correlation[selected]))]
    start_block = int(lags[peak])
    normalized = float(correlation[peak] / max(1, len(source_env)))
    return start_block * (SAMPLE_RATE // 100), normalized


def fine_window_start(track: np.ndarray, source: np.ndarray, predicted: int, source_at: int) -> int:
    duration = 10 * SAMPLE_RATE
    pad = SAMPLE_RATE // 4
    source_window = source[source_at : source_at + duration].astype(np.float64)
    low = predicted + source_at - pad
    track_window = track[low : low + duration + 2 * pad].astype(np.float64)
    correlation = signal.correlate(track_window, source_window, mode="valid", method="fft")
    return low + int(np.argmax(correlation)) - source_at


def alignment(track: np.ndarray, source: np.ndarray, expected_sample: int) -> dict[str, object]:
    coarse, correlation = coarse_start(track, source, expected_sample)
    points = [30 * SAMPLE_RATE, 145 * SAMPLE_RATE, 260 * SAMPLE_RATE]
    starts = [fine_window_start(track, source, coarse, point) for point in points]
    slope, intercept = np.polyfit(np.asarray(points, dtype=np.float64), np.asarray(starts, dtype=np.float64), 1)
    selected = int(round(float(np.median(starts))))
    return {
        "expected_start_sample": expected_sample,
        "coarse_start_sample": coarse,
        "coarse_offset_samples": coarse - expected_sample,
        "coarse_energy_correlation": correlation,
        "fine_start_samples": starts,
        "selected_start_sample": selected,
        "selected_offset_samples": selected - expected_sample,
        "fine_offsets_from_coarse": [item - coarse for item in starts],
        "drift_ppm": float(slope * 1_000_000),
        "drift_intercept_samples": float(intercept),
    }


def aligned_slice(track: np.ndarray, start: int, count: int) -> np.ndarray:
    if start < 0 or start + count > len(track):
        raise ValueError(f"aligned slice [{start}, {start + count}) outside {len(track)} samples")
    return track[start : start + count].copy()


def projection(reference: np.ndarray, observed: np.ndarray) -> dict[str, float]:
    x = reference.astype(np.float64)
    y = observed.astype(np.float64)
    denominator = float(np.dot(x, x))
    gain = float(np.dot(x, y) / denominator) if denominator else 0.0
    residual = y - gain * x
    return {
        "correlation": float(np.corrcoef(x, y)[0, 1]) if np.std(x) and np.std(y) else 0.0,
        "projection_gain": gain,
        "observed_to_reference_rms_db": dbfs(float(np.sqrt(np.mean(y * y)))) - dbfs(float(np.sqrt(np.mean(x * x)))),
        "residual_rms_dbfs": dbfs(float(np.sqrt(np.mean(residual * residual)))),
    }


def reconstruct_mix(system: np.ndarray, microphone: np.ndarray) -> np.ndarray:
    mixed = system.astype(np.float64) / PCM_SCALE * HEADROOM_GAIN
    mixed += microphone.astype(np.float64) / PCM_SCALE * HEADROOM_GAIN
    magnitude = np.abs(mixed)
    limited = magnitude > LIMITER_THRESHOLD
    mixed[limited] = np.sign(mixed[limited]) * (
        LIMITER_THRESHOLD
        + LIMITER_RANGE * np.tanh((magnitude[limited] - LIMITER_THRESHOLD) / LIMITER_RANGE)
    )
    return (np.clip(mixed, -1.0, 1.0) * 32767.0).astype("<i2")


def truth(path: Path) -> tuple[np.ndarray, int, tuple[str, ...]]:
    speakers: dict[str, int] = {}
    rows: list[tuple[float, float, int]] = []
    previous_end = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        speaker = speakers.setdefault(str(item["speaker"]), len(speakers))
        start = max(float(item["start"]), previous_end)
        end = float(item["end"])
        if end > start:
            rows.append((start, end, speaker))
            previous_end = end
    return np.asarray(rows, dtype=np.float64), len(speakers), tuple(speakers)


def identity_replay(
    audio_path: Path,
    reference_path: Path,
    asset_path: Path,
    repo: Path,
) -> dict[str, object]:
    sys.path.insert(0, str(repo / "tests"))
    import live_identity_accuracy as identity
    from moss_transcribe_diarize.app.live_identity_album import (
        ALBUM_ADMISSION_SECONDS,
        ALBUM_BIRTH_MIN_SECONDS,
        ALBUM_MIN_MATCH_MARGIN,
        ALBUM_MIN_MATCH_SCORE,
    )
    from moss_transcribe_diarize.app.live_identity_sweep import SWEEP_INTERVAL_SECONDS
    from moss_transcribe_diarize.app.speaker_identity import WeSpeakerResNet152LmAdapter

    ground_truth, speaker_count, speaker_names = truth(reference_path)
    grouped: dict[tuple[int, int], list[object]] = {}
    for piece in identity.plan_spans(ground_truth):
        grouped.setdefault((piece.span, piece.true_speaker), []).append(piece)
    adapter = WeSpeakerResNet152LmAdapter(asset_path)
    rows: list[tuple[float, float, float, float, float, float]] = []
    vectors: list[np.ndarray] = []
    minimum = identity.MIN_SEGMENT_SAMPLES / identity.LIVE_SAMPLE_RATE
    for (span, speaker), pieces in sorted(grouped.items()):
        selected = [piece for piece in pieces if piece.duration >= minimum]
        duration = sum(piece.duration for piece in selected)
        if selected:
            vectors.append(np.asarray(adapter.embed(audio_path, [(piece.start, piece.end) for piece in selected]), dtype=np.float32))
        rows.append((float(span), float(speaker), min(piece.start for piece in pieces), max(piece.end for piece in pieces), duration, float(bool(selected))))
    meeting = identity.Meeting(
        name=audio_path.stem,
        speaker_count=speaker_count,
        truth=ground_truth,
        rows=np.asarray(rows, dtype=np.float64),
        vectors=np.stack(vectors) if vectors else np.zeros((0, 256), dtype=np.float32),
    )
    identity.assert_fixture_matches_production(meeting)
    replay = identity.replay(
        meeting,
        policy="album",
        min_match_score=ALBUM_MIN_MATCH_SCORE,
        min_match_margin=ALBUM_MIN_MATCH_MARGIN,
        admission_seconds=ALBUM_ADMISSION_SECONDS,
        birth_min_seconds=ALBUM_BIRTH_MIN_SECONDS,
        sweep_interval=SWEEP_INTERVAL_SECONDS,
    )
    return {"speakers": speaker_names, **dataclasses.asdict(replay)}


def gap_metrics(track: dict[str, object]) -> dict[str, object]:
    gaps = track["gaps"]
    samples = sum(int(gap["end_sample"]) - int(gap["start_sample"]) for gap in gaps)
    return {"count": len(gaps), "samples": samples, "seconds": samples / SAMPLE_RATE, "items": gaps}


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.tape_index.read_text(encoding="utf-8"))
    tape_dir = args.tape_index.parent.resolve()
    work_dir = args.work_dir.resolve()
    if tape_dir not in work_dir.parents:
        raise ValueError("work-dir must be inside the tape session directory")
    work_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    source = read_wav(args.source_wav)
    tracks = {
        name: read_pcm(tape_dir / str(payload["file"]))
        for name, payload in manifest["tracks"].items()
    }
    mixed_origin = int(manifest["tracks"]["mixed"]["origin_timestamp_ns"])
    corpus_origin_ns = mixed_origin + round(args.corpus_start_sample * 1_000_000_000 / SAMPLE_RATE)
    expected = {
        name: round((corpus_origin_ns - int(payload["origin_timestamp_ns"])) * SAMPLE_RATE / 1_000_000_000)
        for name, payload in manifest["tracks"].items()
    }
    alignments = {name: alignment(pcm, source, expected[name]) for name, pcm in tracks.items()}
    aligned = {
        name: aligned_slice(pcm, int(alignments[name]["selected_start_sample"]), len(source))
        for name, pcm in tracks.items()
    }
    timeline = {
        name: aligned_slice(pcm, expected[name], len(source))
        for name, pcm in tracks.items()
    }
    system_wav = work_dir / "system-aligned.wav"
    mixed_wav = work_dir / "mixed-aligned.wav"
    write_wav(system_wav, aligned["system"])
    write_wav(mixed_wav, aligned["mixed"])
    predicted_mix = reconstruct_mix(timeline["system"], timeline["microphone"])
    difference = timeline["mixed"].astype(np.int32) - predicted_mix.astype(np.int32)
    result: dict[str, object] = {
        "question": "where does retained live audio first diverge from the clean identity path?",
        "source": {"sha256": sha256(args.source_wav), **basic_metrics(source)},
        "reference_sha256": sha256(args.reference),
        "identity_asset_sha256": sha256(args.identity_asset),
        "tape": {
            "session_id": manifest["session_id"],
            "ended_at": manifest["ended_at"],
            "total_bytes": manifest["total_bytes"],
            "max_bytes": manifest["max_bytes"],
            "degradation": manifest["degradation"],
            "corpus_start_sample": args.corpus_start_sample,
            "tracks": {
                name: {
                    "sha256": sha256(tape_dir / str(manifest["tracks"][name]["file"])),
                    "manifest_samples": manifest["tracks"][name]["sample_count"],
                    "manifest_bytes": manifest["tracks"][name]["bytes"],
                    "gaps": gap_metrics(manifest["tracks"][name]),
                    "whole_track": basic_metrics(pcm),
                    "aligned_corpus": basic_metrics(aligned[name]),
                    "alignment": alignments[name],
                }
                for name, pcm in tracks.items()
            },
        },
        "signal_differential": {
            "source_to_system": projection(source, aligned["system"]),
            "source_to_mixed": projection(source, aligned["mixed"]),
            "system_to_microphone_bleed": projection(aligned["system"], aligned["microphone"]),
            "system_to_mixed": projection(aligned["system"], aligned["mixed"]),
            "mixer_reconstruction": {
                "exact_fraction": float(np.mean(difference == 0)),
                "max_abs_error_pcm16": int(np.max(np.abs(difference))),
                "rmse_pcm16": float(np.sqrt(np.mean(difference.astype(np.float64) ** 2))),
            },
        },
        "truth_segmented_identity": {
            "system": identity_replay(system_wav, args.reference, args.identity_asset, args.repo),
            "mixed": identity_replay(mixed_wav, args.reference, args.identity_asset, args.repo),
        },
        "raw_audio_locations": [str(tape_dir), str(work_dir)],
    }
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
