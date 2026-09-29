"""Measure Stop orphan fingerprint viability on a saved public E1 surface."""

from __future__ import annotations

import argparse
import json
import tempfile
import wave
from collections import defaultdict
from pathlib import Path

from moss_transcribe_diarize.app.gemini_continuity_registry import _cosine
from moss_transcribe_diarize.app.speaker_identity import WeSpeakerResNet152LmAdapter


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    rows = json.loads(args.snapshot.read_text())["session"]["effective_transcript"]
    rows = [row for row in rows if row.get("source_lane") == "system"
            and row.get("canonical_speaker")]
    totals = defaultdict(int)
    for row in rows:
        totals[row["canonical_speaker"]] += row["end_sample"] - row["start_sample"]
    orphans = [speaker for speaker, samples in totals.items() if samples < 2 * 16000]
    established = [speaker for speaker, samples in totals.items() if samples >= 2 * 16000]
    encoder = WeSpeakerResNet152LmAdapter(args.model, device="cpu")
    vectors = {}
    with wave.open(str(args.audio), "rb") as source, tempfile.TemporaryDirectory() as temp:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, 16000)
        for speaker in [*orphans, *established]:
            selected = ([row for row in rows if row["canonical_speaker"] == speaker]
                        if speaker in orphans else
                        [row for row in rows if row["canonical_speaker"] == speaker
                         and row["end_sample"] - row["start_sample"] >= 16000][:3])
            parts = []
            for index, row in enumerate(selected):
                start = row["start_sample"]
                end = min(row["end_sample"], start + 2 * 16000)
                source.setpos(start)
                pcm = source.readframes(end - start)
                path = Path(temp) / f"{speaker}-{index}.wav"
                with wave.open(str(path), "wb") as target:
                    target.setnchannels(1)
                    target.setsampwidth(2)
                    target.setframerate(16000)
                    target.writeframes(pcm)
                try:
                    parts.append(encoder.embed(path, [(0.0, (end - start) / 16000)]))
                except Exception as exc:
                    print(json.dumps({"speaker": speaker, "duration_seconds": (end-start)/16000,
                                      "embedding_error": type(exc).__name__}))
            if parts:
                vectors[speaker] = [sum(values) / len(values) for values in zip(*parts)]
    print(json.dumps({"totals_seconds": {k: v / 16000 for k, v in totals.items()},
                      "orphans": orphans, "established": established,
                      "vector_speakers": sorted(vectors)}, sort_keys=True))
    for orphan in orphans:
        print(json.dumps({"orphan": orphan, "cosines": {
            speaker: round(_cosine(vectors[orphan], vectors[speaker]), 4)
            for speaker in established if orphan in vectors and speaker in vectors}},
            sort_keys=True))


if __name__ == "__main__":
    main()
