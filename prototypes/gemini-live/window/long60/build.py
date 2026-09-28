"""PROTOTYPE — build the complete-reference public long-meeting stitch fixture.

One command from the worktree root:
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/gemini-live/window/long60/build.py

The generated WAV is ignored; reference.jsonl is the retained truth artifact.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[1] / "common"))
from corpus import clips  # noqa: E402
from gemini_common import SAMPLE_RATE, read_wav  # noqa: E402

AUDIO = ROOT / "prototypes/gemini-live/.cache/long60/audio.wav"
REFERENCE = HERE / "reference.jsonl"
SOURCE_IDS = (
    "benchmark_30m:lex_bill_ackman",
    "benchmark_5m:lex_keyu_jin",
    "benchmark_5m:lex_javier_milei",
    "calibration:lex_adam_frank",
)
SILENCE_S = 2


def coverage(rows: list[dict]) -> float:
    merged: list[list[float]] = []
    for row in sorted(rows, key=lambda x: (x["start"], x["end"])):
        start, end = float(row["start"]), float(row["end"])
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(end, merged[-1][1])
        else:
            merged.append([start, end])
    return sum(end - start for start, end in merged)


def main() -> None:
    by_id = {clip.clip_id: clip for clip in clips()}
    selected = [by_id[clip_id] for clip_id in SOURCE_IDS]
    AUDIO.parent.mkdir(parents=True, exist_ok=True)
    reference: list[dict] = []
    offset_samples = 0
    with sf.SoundFile(AUDIO, mode="w", samplerate=SAMPLE_RATE, channels=1, subtype="PCM_16") as out:
        for index, clip in enumerate(selected):
            audio = read_wav(clip.audio)
            duration = len(audio) / SAMPLE_RATE
            source_rows = clip.reference_segments()
            assert source_rows and abs(coverage(source_rows) - duration) < .02, clip.clip_id
            assert min(row["start"] for row in source_rows) >= 0
            assert max(row["end"] for row in source_rows) <= duration + .02
            offset = offset_samples / SAMPLE_RATE
            for row in source_rows:
                speaker = "Lex Fridman" if row["speaker"] in {"Lex", "Lex Fridman"} else row["speaker"]
                reference.append({"start": round(offset + row["start"], 6),
                                  "end": round(offset + row["end"], 6),
                                  "speaker": speaker, "text": row["text"],
                                  "source_clip": clip.clip_id})
            out.write(audio)
            offset_samples += len(audio)
            print(f"SOURCE {index} {clip.clip_id} offset={offset:.3f}s duration={duration:.3f}s "
                  f"reference={coverage(source_rows):.3f}s rows={len(source_rows)}", flush=True)
            if index < len(selected) - 1:
                out.write(np.zeros(SILENCE_S * SAMPLE_RATE, dtype=np.int16))
                offset_samples += SILENCE_S * SAMPLE_RATE
    reference.sort(key=lambda row: (row["start"], row["end"], row["speaker"]))
    REFERENCE.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in reference))
    total_s = offset_samples / SAMPLE_RATE
    reference_s = coverage(reference)
    assert abs(reference_s - (total_s - SILENCE_S * (len(selected) - 1))) < .02
    assert sf.info(AUDIO).frames == offset_samples
    print(f"BUILT audio={AUDIO} reference={REFERENCE} duration={total_s:.3f}s "
          f"timed_reference={reference_s:.3f}s silence={total_s-reference_s:.3f}s "
          f"rows={len(reference)} speakers={sorted({row['speaker'] for row in reference})}", flush=True)


if __name__ == "__main__":
    main()
