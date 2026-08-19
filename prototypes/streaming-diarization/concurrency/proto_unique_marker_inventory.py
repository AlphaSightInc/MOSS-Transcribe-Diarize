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


# These bounds come from the already-recorded real-source transcript.  They
# deliberately use multiword phrases unlikely to arise in a different clip.
CANDIDATES = (
    Candidate("new-york", 39.0, 45.0, "New York"),
    Candidate("payments", 48.0, 53.0, "payments team"),
    Candidate("huge-thanks", 52.0, 58.0, "huge thanks"),
    Candidate("show-notes", 58.0, 63.0, "show notes"),
    Candidate("investment-advice", 63.0, 68.0, "investment advice"),
    Candidate("entertainment", 68.0, 73.0, "entertainment purposes"),
    Candidate("appropriate", 73.0, 75.0, "feels appropriate"),
    Candidate("dressed-up", 75.0, 78.0, "dressed up"),
)


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


def _fixture_path() -> Path:
    fixture = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
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
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    args = parse_args()
    fixture_path = _fixture_path()
    if len({candidate.expected_marker.casefold() for candidate in CANDIDATES}) != len(CANDIDATES):
        raise RuntimeError("candidate marker inventory is not distinct")

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
            for candidate in CANDIDATES:
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
        "question": "Can the production vLLM endpoint recognize eight distinct real-speech markers?",
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
