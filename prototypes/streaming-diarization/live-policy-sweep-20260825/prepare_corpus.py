#!/usr/bin/env python3
"""Prepare the preregistered, fully referenced live-policy corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import wave
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "prototypes/streaming-diarization/data/real"
SAMPLE_RATE = 16_000

WHOLE_CASES = {
    "interview_bill_ackman_60s": (
        "two-person interview",
        DATA / "benchmark_diarization_1min/samples/lex_bill_ackman",
    ),
    "interview_keyu_jin_60s": (
        "two-person interview",
        DATA / "benchmark_diarization_1min/samples/lex_keyu_jin",
    ),
    "interview_adam_frank_180s": (
        "two-person interview",
        DATA / "calibration_diarization_3min/samples/lex_adam_frank",
    ),
    "discussion_jamie_dimon_180s": (
        "multi-person discussion",
        DATA / "calibration_diarization_3min/samples/acquired_jamie_dimon_3min",
    ),
    "discussion_rtfl_90s": (
        "multi-person conversation",
        DATA / "regression_fixtures/youtube_rtfl_first_90s",
    ),
}
MONO_SOURCE = DATA / "benchmark_diarization_1min/samples/lex_javier_milei"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wav_facts(path: Path) -> dict[str, Any]:
    with wave.open(str(path), "rb") as handle:
        shape = (handle.getnchannels(), handle.getsampwidth(), handle.getframerate(), handle.getcomptype())
        if shape != (1, 2, SAMPLE_RATE, "NONE"):
            raise RuntimeError(f"unsupported WAV shape {path}: {shape}")
        samples = handle.getnframes()
        pcm = handle.readframes(samples)
    return {
        "samples": samples,
        "duration_seconds": samples / SAMPLE_RATE,
        "wav_bytes": path.stat().st_size,
        "wav_sha256": sha256(path),
        "pcm_sha256": hashlib.sha256(pcm).hexdigest(),
    }


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def copy_whole(case_id: str, category: str, source: Path, corpus: Path) -> dict[str, Any]:
    target = corpus / case_id
    target.mkdir()
    for name in ("audio.wav", "reference.jsonl"):
        shutil.copyfile(source / name, target / name)
        if (source / name).read_bytes() != (target / name).read_bytes():
            raise RuntimeError(f"copy changed bytes: {case_id}/{name}")
    references = load_jsonl(target / "reference.jsonl")
    return {
        "case_id": case_id,
        "category": category,
        "derived": False,
        "source_directory": str(source.relative_to(REPO)),
        "source_audio_sha256": sha256(source / "audio.wav"),
        "source_reference_sha256": sha256(source / "reference.jsonl"),
        "audio": wav_facts(target / "audio.wav"),
        "reference_sha256": sha256(target / "reference.jsonl"),
        "reference_rows": len(references),
        "reference_speakers": sorted({str(row["speaker"]) for row in references}),
        "whole_file_byte_identical": True,
    }


def prepare_monologue(corpus: Path) -> dict[str, Any]:
    case_id = "mono_javier_intro_50s"
    target = corpus / case_id
    target.mkdir()
    source_audio = MONO_SOURCE / "audio.wav"
    with wave.open(str(source_audio), "rb") as source:
        shape = (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype())
        if shape != (1, 2, SAMPLE_RATE, "NONE"):
            raise RuntimeError(f"unsupported WAV shape {source_audio}: {shape}")
        source.setpos(10 * SAMPLE_RATE)
        pcm = source.readframes(50 * SAMPLE_RATE)
    if len(pcm) != 50 * SAMPLE_RATE * 2:
        raise RuntimeError("monologue slice is not exactly 50 seconds")
    with wave.open(str(target / "audio.wav"), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)

    selected = [
        row for row in load_jsonl(MONO_SOURCE / "reference.jsonl")
        if float(row["start"]) == 10.0 and float(row["end"]) == 60.0
    ]
    if len(selected) != 1 or str(selected[0]["speaker"]) != "Lex Fridman":
        raise RuntimeError(f"monologue golden boundary drift: {selected}")
    reference = {**selected[0], "start": 0.0, "end": 50.0}
    write_jsonl(target / "reference.jsonl", [reference])
    return {
        "case_id": case_id,
        "category": "monologue",
        "derived": True,
        "source_directory": str(MONO_SOURCE.relative_to(REPO)),
        "source_slice_seconds": [10.0, 60.0],
        "source_audio_sha256": sha256(source_audio),
        "source_reference_sha256": sha256(MONO_SOURCE / "reference.jsonl"),
        "audio": wav_facts(target / "audio.wav"),
        "reference_sha256": sha256(target / "reference.jsonl"),
        "reference_rows": 1,
        "reference_speakers": ["Lex Fridman"],
        "whole_file_byte_identical": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    corpus = args.output.resolve()
    corpus.mkdir(parents=True, exist_ok=False)
    cases = [prepare_monologue(corpus)]
    cases.extend(copy_whole(case_id, category, source, corpus) for case_id, (category, source) in WHOLE_CASES.items())
    duration = sum(float(case["audio"]["duration_seconds"]) for case in cases)
    if len(cases) != 6 or not all(float(case["audio"]["duration_seconds"]) < 300 for case in cases):
        raise RuntimeError("preregistered corpus denominator/clip-duration gate failed")
    payload = {
        "schema": "moss-live-policy-corpus.v1",
        "cases": cases,
        "denominator": {"cases": len(cases), "audio_seconds": duration},
    }
    (corpus / "corpus-manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
