"""One-command production WeSpeaker interval timing on a public long60 window."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder

LIVE = Path(__file__).resolve().parents[4] / "MOSS-Transcribe-Diarize-wt-gemini-live"
GEMINI = LIVE / "prototypes/gemini-live"
sys.path.insert(0, str(GEMINI / "continuity"))
from measure import embedding_intervals  # noqa: E402


def main() -> None:
    source = (Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P61")
              / "c4-observations-long60-long60-S15-L180.jsonl")
    window = next(row for line in source.open() if (row := json.loads(line))["end"] == 300)
    intervals = {
        label: embedding_intervals(window["start"], window["words"], label)
        for label in {word["speaker"] for word in window["words"]}
    }
    intervals = {label: spans for label, spans in intervals.items() if spans}
    model = LIVE / "prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx"
    audio = GEMINI / ".cache/long60/audio.wav"
    observations_by_workers = {}
    for workers in (1, 3):
        encoder = _OnnxWeSpeakerEmbedder(model, device="cpu", interval_workers=workers)
        encoder.load()
        runs = []
        for _ in range(2):
            began = time.monotonic()
            vectors = {label: encoder.embed(audio, spans) for label, spans in intervals.items()}
            runs.append({"seconds": round(time.monotonic() - began, 3), "vectors": vectors})
        observations_by_workers[workers] = runs
    max_difference = max(
        abs(left-right)
        for label in intervals
        for left, right in zip(observations_by_workers[1][0]["vectors"][label],
                               observations_by_workers[3][0]["vectors"][label], strict=True)
    )
    print(json.dumps({"window": [window["start"], window["end"]],
                      "interval_counts": {k: len(v) for k, v in intervals.items()},
                      "seconds": {str(k): [run["seconds"] for run in runs]
                                  for k, runs in observations_by_workers.items()},
                      "max_vector_difference": max_difference}, indent=2))


if __name__ == "__main__":
    main()
