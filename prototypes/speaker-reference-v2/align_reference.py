#!/usr/bin/env python3
"""Create immutable speaker-reference v2 by blind CTC forced alignment."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import soundfile as sf
import torch
import torchaudio

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.speaker_reference import (  # noqa: E402
    V2_SCHEMA,
    normalize_reference_text,
)

METHOD = "torchaudio MMS_FA CTC forced alignment with wildcard gaps"
MODEL = "MMS_FA wav2vec2_model (with_star=True)"
ALIGNMENT_DATE = "2026-08-03"
SUSPECT_MEAN_TOKEN_SCORE = 0.35
COARSE_GAP_SPLIT_SEC = 10.0


def main() -> int:
    args = _parse_args()
    audio_path = args.audio.resolve()
    v1_path = args.v1.resolve()
    rows = _read_jsonl(v1_path)

    audio, sample_rate = sf.read(audio_path, dtype="float32", always_2d=True)
    if sample_rate != torchaudio.pipelines.MMS_FA.sample_rate:
        raise ValueError(f"audio sample rate must be 16000, got {sample_rate}")
    mono = audio.mean(axis=1, dtype="float32")
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=True).eval()
    tokenizer = bundle.get_tokenizer()
    aligner = bundle.get_aligner()
    aligned_rows: list[tuple[float, float, float] | None] = [None] * len(rows)
    for first, last, window_start, window_end in _coarse_groups(
        rows, audio_duration_sec=len(mono) / sample_rate
    ):
        transcript: list[str] = ["*"]
        bounds: list[tuple[int, int]] = []
        for row in rows[first:last]:
            words = normalize_reference_text(_required_text(row, "text")).split()
            if bounds:
                transcript.append("*")
            start_word = len(transcript)
            transcript.extend(words)
            bounds.append((start_word, len(transcript)))
        transcript.append("*")
        unsupported = sorted(
            {
                character
                for word in transcript
                for character in word
                if character not in bundle.get_dict()
            }
        )
        if unsupported:
            raise ValueError(f"normalized transcript contains unsupported characters: {unsupported}")
        first_sample = round(window_start * sample_rate)
        last_sample = round(window_end * sample_rate)
        waveform = torch.from_numpy(mono[first_sample:last_sample][None, :].copy())
        with torch.inference_mode():
            emission, _ = model(waveform)
        word_spans = aligner(emission[0], tokenizer(transcript))
        seconds_per_emission = waveform.shape[1] / emission.shape[1] / sample_rate
        for row_index, (start_word, end_word) in enumerate(bounds, start=first):
            spans = [span for word in word_spans[start_word:end_word] for span in word]
            if not spans:
                raise ValueError(f"record {row_index + 1} produced no aligned token spans")
            frame_count = sum(span.end - span.start for span in spans)
            mean_score = sum(
                span.score * (span.end - span.start) for span in spans
            ) / frame_count
            aligned_rows[row_index] = (
                window_start + spans[0].start * seconds_per_emission,
                window_start + spans[-1].end * seconds_per_emission,
                mean_score,
            )

    v2_rows: list[dict[str, Any]] = []
    suspects: list[dict[str, Any]] = []
    for record_number, (row, aligned) in enumerate(zip(rows, aligned_rows), start=1):
        if aligned is None:
            raise AssertionError(f"record {record_number} was not aligned")
        start, end, mean_score = aligned
        normalized = normalize_reference_text(_required_text(row, "text"))
        word_count = len(normalized.split())
        rate = word_count / (end - start)
        aligned = {
            "schema": V2_SCHEMA,
            "speaker_activity": {
                "speaker": _required_text(row, "speaker"),
                "start": round(start, 6),
                "end": round(end, 6),
            },
            "transcript": {
                "text": _required_text(row, "text"),
                "line_index": row["line_index"],
            },
            "alignment": {
                "method": METHOD,
                "model": MODEL,
                "normalized_text": normalized,
                "normalized_text_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
                "word_count": word_count,
                "mean_token_score": round(mean_score, 6),
            },
        }
        v2_rows.append(aligned)
        if mean_score < SUSPECT_MEAN_TOKEN_SCORE or rate > 8.0:
            suspects.append(
                {
                    "record": record_number,
                    "line_index": row["line_index"],
                    "speaker": row["speaker"],
                    "start": aligned["speaker_activity"]["start"],
                    "end": aligned["speaker_activity"]["end"],
                    "words_per_sec": round(rate, 6),
                    "mean_token_score": round(mean_score, 6),
                    "text": row["text"],
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in v2_rows),
        encoding="utf-8",
    )
    v2_sha = _sha256(args.output)
    provenance = {
        "schema": "moss-speaker-reference-provenance.v1",
        "reference_version": 2,
        "alignment_date": ALIGNMENT_DATE,
        "method": METHOD,
        "model": MODEL,
        "blind_to_live_output": True,
        "v1_fields_used": ["speaker", "text", "line_index", "start", "end"],
        "v1_timing_use": "coarse partitioning only at gaps >=10s; never copied to v2",
        "coarse_gap_split_sec": COARSE_GAP_SPLIT_SEC,
        "audio": str(audio_path),
        "audio_sha256": _sha256(audio_path),
        "v1_reference": str(v1_path),
        "v1_reference_sha256": _sha256(v1_path),
        "v2_reference": str(args.output.resolve()),
        "v2_reference_sha256": v2_sha,
        "segment_count": len(v2_rows),
        "suspect_threshold_mean_token_score": SUSPECT_MEAN_TOKEN_SCORE,
        "suspect_count": len(suspects),
    }
    args.provenance.parent.mkdir(parents=True, exist_ok=True)
    args.provenance.write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    args.suspects.parent.mkdir(parents=True, exist_ok=True)
    args.suspects.write_text(json.dumps(suspects, indent=2, sort_keys=True) + "\n")
    print(json.dumps(provenance, sort_keys=True))
    print(f"suspects={len(suspects)} path={args.suspects}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--v1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provenance", type=Path, required=True)
    parser.add_argument("--suspects", type=Path, required=True)
    return parser.parse_args()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        raise ValueError("v1 reference is empty")
    return rows


def _coarse_groups(
    rows: list[dict[str, Any]], *, audio_duration_sec: float
) -> list[tuple[int, int, float, float]]:
    """Bound independent CTC windows using only obviously long v1 gaps."""

    starts = [0]
    boundaries: list[float] = []
    for index in range(len(rows) - 1):
        current_end = float(rows[index]["end"])
        next_start = float(rows[index + 1]["start"])
        if next_start - current_end >= COARSE_GAP_SPLIT_SEC:
            starts.append(index + 1)
            boundaries.append((current_end + next_start) / 2.0)
    ends = starts[1:] + [len(rows)]
    window_starts = [0.0] + boundaries
    window_ends = boundaries + [audio_duration_sec]
    return list(zip(starts, ends, window_starts, window_ends))


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"reference {key} must be a non-empty string")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
