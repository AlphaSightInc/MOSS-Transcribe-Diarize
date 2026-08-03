#!/usr/bin/env python3
"""Bind transcript-independent ASR responses to an audio corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.speaker_reference import ACOUSTIC_EVIDENCE_SCHEMA  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument(
        "--response",
        action="append",
        required=True,
        help="chunk start seconds and raw ASR response as OFFSET:PATH",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    segments: list[dict] = []
    responses: list[dict] = []
    for value in args.response:
        offset_text, separator, path_text = value.partition(":")
        if not separator:
            raise ValueError("--response must be OFFSET:PATH")
        offset = float(offset_text)
        response_path = Path(path_text)
        raw = response_path.read_bytes()
        payload = json.loads(raw)
        transcript = payload.get("text")
        if not isinstance(transcript, str):
            raise ValueError(f"ASR response has no text: {response_path}")
        parsed = parse_transcript(transcript)
        if not parsed:
            raise ValueError(f"ASR response has no complete segments: {response_path}")
        responses.append(
            {
                "offset_sec": offset,
                "response_sha256": hashlib.sha256(raw).hexdigest(),
                "segment_count": len(parsed),
            }
        )
        segments.extend(
            {
                "start": round(segment.start + offset, 6),
                "end": round(segment.end + offset, 6),
                "speaker": segment.speaker,
                "text": segment.text,
            }
            for segment in parsed
        )

    evidence = {
        "schema": ACOUSTIC_EVIDENCE_SCHEMA,
        "audio_sha256": hashlib.sha256(args.audio.read_bytes()).hexdigest(),
        "blind_to_reference_transcript": True,
        "method": "independent MOSS-Transcribe-Diarize ASR pass; 60-second chunks",
        "model": "OpenMOSS-Team/MOSS-Transcribe-Diarize",
        "source_revision": args.source_revision,
        "generation_date": "2026-08-03",
        "responses": responses,
        "segments": sorted(segments, key=lambda row: (row["start"], row["end"])),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "audio_sha256": evidence["audio_sha256"],
                "evidence_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
                "response_count": len(responses),
                "segment_count": len(segments),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
