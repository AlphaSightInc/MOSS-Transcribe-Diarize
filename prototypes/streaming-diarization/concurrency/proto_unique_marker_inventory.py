#!/usr/bin/env python3
"""Measure whether the real fixture has eight distinct, recognizable markers.

Question: can the read-only vLLM endpoint recognize one marker from each of
eight separately bounded real-speech clips?  A positive result permits the W2
isolation oracle to assign one unique clip to every session in the frozen
1/2/4/8 matrix.  This is a fixture-inventory probe, not a G4/G5 measurement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from moss_transcribe_diarize.app.vllm_runner import VllmRunner


ROOT = Path(__file__).resolve().parents[3]
FIXTURE_MANIFEST = Path(__file__).with_name("cpu_hf_local_fixture.json")


@dataclass(frozen=True)
class Candidate:
    identifier: str
    start_seconds: float
    end_seconds: float
    expected_marker: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vllm-base-url", required=True)
    parser.add_argument("--vllm-model", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _write_clip(*, source: wave.Wave_read, candidate: Candidate, path: Path) -> None:
    sample_rate = source.getframerate()
    start = int(candidate.start_seconds * sample_rate)
    length = int((candidate.end_seconds - candidate.start_seconds) * sample_rate)
    source.setpos(start)
    frames = source.readframes(length)
    if len(frames) != length * source.getnchannels() * source.getsampwidth():
        raise RuntimeError(f"candidate exceeds source audio: {candidate.identifier}")
    with wave.open(str(path), "wb") as destination:
        destination.setparams(source.getparams())
        destination.writeframes(frames)


def _fixture() -> tuple[dict[str, object], Path]:
    fixture = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
    if not isinstance(fixture, dict):
        raise RuntimeError("fixture manifest must be an object")
    audio = fixture.get("audio")
    if not isinstance(audio, dict) or not isinstance(audio.get("path"), str):
        raise RuntimeError("fixture manifest lacks an audio path")
    expected_sha256 = audio.get("sha256")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise RuntimeError("fixture manifest lacks an audio SHA-256")
    path = ROOT / audio["path"]
    if not path.is_file():
        raise RuntimeError(f"fixture is absent: {path}")
    if _sha256(path) != expected_sha256:
        raise RuntimeError("fixture source SHA-256 drifted from its manifest")
    return fixture, path


def _fixture_candidates(fixture: dict[str, object]) -> tuple[Candidate, ...]:
    raw_clips = fixture.get("clips")
    if not isinstance(raw_clips, list) or not raw_clips:
        raise RuntimeError("fixture manifest lacks clips")
    candidates: list[Candidate] = []
    identifiers: set[str] = set()
    markers: set[str] = set()
    for raw_clip in raw_clips:
        if not isinstance(raw_clip, dict):
            raise RuntimeError("fixture clip must be an object")
        identifier = raw_clip.get("id")
        marker = raw_clip.get("expected_marker")
        start_seconds = raw_clip.get("start_seconds")
        end_seconds = raw_clip.get("end_seconds")
        if not isinstance(identifier, str) or not identifier:
            raise RuntimeError("fixture clip lacks an id")
        if not isinstance(marker, str) or not marker.strip():
            raise RuntimeError("fixture clip lacks an expected marker")
        if (
            isinstance(start_seconds, bool)
            or not isinstance(start_seconds, (int, float))
            or isinstance(end_seconds, bool)
            or not isinstance(end_seconds, (int, float))
            or end_seconds <= start_seconds
        ):
            raise RuntimeError(f"fixture clip has invalid bounds: {identifier}")
        normalized_marker = marker.casefold()
        if identifier in identifiers or normalized_marker in markers:
            raise RuntimeError("fixture candidate markers and ids must be distinct")
        identifiers.add(identifier)
        markers.add(normalized_marker)
        candidates.append(Candidate(identifier, float(start_seconds), float(end_seconds), marker))
    return tuple(candidates)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    fixture, fixture_path = _fixture()
    candidates = _fixture_candidates(fixture)

    runner = VllmRunner(
        base_url=args.vllm_base_url,
        model=args.vllm_model,
        timeout=args.timeout_seconds,
    )
    results: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="moss-unique-marker-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        with wave.open(str(fixture_path), "rb") as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                raise RuntimeError("fixture must be mono 16-bit 16 kHz PCM WAV")
            for candidate in candidates:
                clip = temp_dir / f"{candidate.identifier}.wav"
                _write_clip(source=source, candidate=candidate, path=clip)
                started = time.monotonic()
                transcription = runner.transcribe(clip)
                text = transcription.text
                results.append(
                    {
                        "id": candidate.identifier,
                        "start_seconds": candidate.start_seconds,
                        "end_seconds": candidate.end_seconds,
                        "expected_marker": candidate.expected_marker,
                        "transcript": text,
                        "marker_present": candidate.expected_marker.casefold() in text.casefold(),
                        "elapsed_seconds": time.monotonic() - started,
                    }
                )

    for row in results:
        marker = str(row["expected_marker"]).casefold()
        row["marker_absent_from_other_candidates"] = all(
            marker not in str(other["transcript"]).casefold()
            for other in results
            if other is not row
        )

    result = {
        "schema": "moss-unique-marker-inventory.v1",
        "question": "Can the production vLLM endpoint recognize every distinct real-speech marker configured for the W2 fixture?",
        "fixture": str(fixture_path.relative_to(ROOT)),
        "fixture_sha256": _sha256(fixture_path),
        "fixture_manifest": str(FIXTURE_MANIFEST.relative_to(ROOT)),
        "fixture_manifest_sha256": _sha256(FIXTURE_MANIFEST),
        "vllm_base_url": args.vllm_base_url.rstrip("/"),
        "vllm_model": args.vllm_model,
        "candidates": results,
        "all_markers_present_and_unique": all(
            row["marker_present"] and row["marker_absent_from_other_candidates"] for row in results
        ),
        "does_not_establish": [
            "cross-session isolation",
            "round-robin fairness",
            "G4 or G5",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_markers_present_and_unique"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
