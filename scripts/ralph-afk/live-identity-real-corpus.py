#!/usr/bin/env python3
"""Hash-pinned 9-clip real-audio acceptance for the production live identity path."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tests"))

import live_identity_accuracy as identity  # noqa: E402

from moss_transcribe_diarize.app.live_identity_album import (  # noqa: E402
    ALBUM_ADMISSION_SECONDS,
    ALBUM_BIRTH_MIN_SECONDS,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
)
from moss_transcribe_diarize.app.live_identity_sweep import SWEEP_INTERVAL_SECONDS  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import (  # noqa: E402
    WeSpeakerResNet152LmAdapter,
)


DEFAULT_MANIFEST = REPO_ROOT / "tests" / "fixtures" / "live_identity_real_corpus.json"
DEFAULT_CORPUS = REPO_ROOT / "prototypes" / "streaming-diarization" / "data" / "real"
DEFAULT_ASSET = (
    REPO_ROOT
    / "prototypes"
    / "streaming-diarization"
    / "data"
    / "voxceleb_resnet152_LM.onnx"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _truth(path: Path) -> tuple[np.ndarray, int]:
    speakers: dict[str, int] = {}
    rows: list[tuple[float, float, int]] = []
    previous_end = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        record = json.loads(line)
        speaker = speakers.setdefault(str(record["speaker"]), len(speakers))
        start = max(float(record["start"]), previous_end)
        end = float(record["end"])
        if end <= start:
            continue
        rows.append((start, end, speaker))
        previous_end = end
    if not rows:
        raise ValueError(f"{path}: no positive reference turns")
    return np.asarray(rows, dtype=np.float64), len(speakers)


def _meeting(
    *,
    name: str,
    audio_path: Path,
    reference_path: Path,
    adapter: WeSpeakerResNet152LmAdapter,
) -> identity.Meeting:
    truth, speaker_count = _truth(reference_path)
    grouped: dict[tuple[int, int], list[identity.Piece]] = {}
    for piece in identity.plan_spans(truth):
        grouped.setdefault((piece.span, piece.true_speaker), []).append(piece)

    rows: list[tuple[float, float, float, float, float, float]] = []
    vectors: list[np.ndarray] = []
    minimum_seconds = identity.MIN_SEGMENT_SAMPLES / identity.LIVE_SAMPLE_RATE
    for (span, true_speaker), pieces in sorted(grouped.items()):
        selected = [piece for piece in pieces if piece.duration >= minimum_seconds]
        duration = sum(piece.duration for piece in selected)
        eligible = bool(selected)
        if eligible:
            vector = adapter.embed(
                audio_path,
                [(piece.start, piece.end) for piece in selected],
            )
            vectors.append(np.asarray(vector, dtype=np.float32))
        rows.append(
            (
                float(span),
                float(true_speaker),
                min(piece.start for piece in pieces),
                max(piece.end for piece in pieces),
                duration,
                float(eligible),
            )
        )
    meeting = identity.Meeting(
        name=name,
        speaker_count=speaker_count,
        truth=truth,
        rows=np.asarray(rows, dtype=np.float64),
        vectors=(
            np.stack(vectors)
            if vectors
            else np.zeros((0, 256), dtype=np.float32)
        ),
    )
    identity.assert_fixture_matches_production(meeting)
    return meeting


def run(
    *,
    manifest_path: Path,
    corpus_root: Path,
    asset_path: Path,
    mean_gate: float,
    long_clip_gate: float,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != 9:
        raise ValueError("real-corpus manifest must declare exactly 9 cases")
    if _sha256(asset_path) != manifest["identity_asset_sha256"]:
        raise ValueError("identity asset hash does not match the acceptance manifest")

    adapter = WeSpeakerResNet152LmAdapter(asset_path)
    preflight = adapter.preflight()
    if not preflight.available:
        raise ValueError(f"identity encoder preflight refused: {preflight.reason}")

    results: list[dict[str, Any]] = []
    for case in cases:
        case_root = corpus_root / case["path"]
        audio_path = case_root / "audio.wav"
        reference_path = case_root / "reference.jsonl"
        if _sha256(audio_path) != case["audio_sha256"]:
            raise ValueError(f"{case['name']}: audio hash mismatch")
        if _sha256(reference_path) != case["reference_sha256"]:
            raise ValueError(f"{case['name']}: reference hash mismatch")
        meeting = _meeting(
            name=case["name"],
            audio_path=audio_path,
            reference_path=reference_path,
            adapter=adapter,
        )
        replay = identity.replay(
            meeting,
            policy="album",
            min_match_score=ALBUM_MIN_MATCH_SCORE,
            min_match_margin=ALBUM_MIN_MATCH_MARGIN,
            admission_seconds=ALBUM_ADMISSION_SECONDS,
            birth_min_seconds=ALBUM_BIRTH_MIN_SECONDS,
            sweep_interval=SWEEP_INTERVAL_SECONDS,
        )
        results.append(
            {
                "name": case["name"],
                "tier": case["tier"],
                "accuracy": replay.accuracy,
                "live_accuracy": replay.live_accuracy,
                "canonical_speakers": replay.canonical_speaker_count,
                "true_speakers": meeting.speaker_count,
                "residual_corrections": replay.residual_corrections,
            }
        )

    mean_accuracy = float(np.mean([item["accuracy"] for item in results]))
    minimum_accuracy = min(item["accuracy"] for item in results)
    long_minimum = min(
        item["accuracy"] for item in results if item["tier"] == "3min"
    )
    green = (
        mean_accuracy >= mean_gate
        and long_minimum >= long_clip_gate
        and all(item["residual_corrections"] == 0 for item in results)
    )
    return {
        "verdict": "GREEN" if green else "RED",
        "parameters": {
            "match_evidence_samples": identity.MIN_SEGMENT_SAMPLES,
            "enrollment_samples": int(
                ALBUM_ADMISSION_SECONDS * identity.LIVE_SAMPLE_RATE
            ),
            "birth_min_samples": int(
                ALBUM_BIRTH_MIN_SECONDS * identity.LIVE_SAMPLE_RATE
            ),
            "min_match_score": ALBUM_MIN_MATCH_SCORE,
            "min_match_margin": ALBUM_MIN_MATCH_MARGIN,
        },
        "mean_accuracy": mean_accuracy,
        "minimum_accuracy": minimum_accuracy,
        "long_clip_minimum_accuracy": long_minimum,
        "mean_gate": mean_gate,
        "long_clip_gate": long_clip_gate,
        "cases": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--identity-asset", type=Path, default=DEFAULT_ASSET)
    parser.add_argument("--mean-gate", type=float, default=0.90)
    parser.add_argument("--long-clip-gate", type=float, default=0.95)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    try:
        evidence = run(
            manifest_path=args.manifest,
            corpus_root=args.corpus_root,
            asset_path=args.identity_asset,
            mean_gate=args.mean_gate,
            long_clip_gate=args.long_clip_gate,
        )
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        print(f"P4_REAL VERDICT=REFUSED reason={exc}")
        return 2
    for case in evidence["cases"]:
        print(
            "P4_REAL "
            f"clip={case['name']} tier={case['tier']} "
            f"accuracy={100.0 * case['accuracy']:.2f}% "
            f"live={100.0 * case['live_accuracy']:.2f}% "
            f"speakers={case['canonical_speakers']}/{case['true_speakers']} "
            f"residual={case['residual_corrections']}"
        )
    print(
        f"P4_REAL VERDICT={evidence['verdict']} "
        f"mean={100.0 * evidence['mean_accuracy']:.2f}% "
        f"minimum={100.0 * evidence['minimum_accuracy']:.2f}% "
        f"long_minimum={100.0 * evidence['long_clip_minimum_accuracy']:.2f}%"
    )
    if args.json_output is not None:
        args.json_output.write_text(
            json.dumps(evidence, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    return 0 if evidence["verdict"] == "GREEN" else 3


if __name__ == "__main__":
    raise SystemExit(main())
