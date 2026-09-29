"""Build 300 s public two-lane R2 mic fixture; run from the worktree root."""
from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
from corpus import clips  # noqa: E402

RATE = 16_000
SECONDS = 300
SAMPLES = RATE * SECONDS


def pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, RATE)
        data = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2")
    assert len(data) >= SAMPLES
    return data[:SAMPLES].astype(np.float32)


def write(path: Path, data: np.ndarray) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(np.clip(np.rint(data), -32768, 32767).astype("<i2").tobytes())


def main() -> None:
    by_id = {clip.clip_id: clip for clip in clips("bench5m")}
    system = by_id["benchmark_5m:acquired_alphabet"]
    local = by_id["benchmark_5m:lex_keyu_jin"]
    system_pcm = pcm(system.audio)
    source_local_pcm = pcm(local.audio)
    # Keep whole referenced turns, leaving two long mic-quiet spans where only
    # the meeting-audio echo can be heard by the mic provider.
    selected_turns = [local.reference_segments()[i] for i in (0, 1, 4, 5, 8)]
    local_pcm = np.zeros(SAMPLES, dtype=np.float32)
    fade = round(.04 * RATE)
    for row in selected_turns:
        start, end = round(row["start"] * RATE), round(row["end"] * RATE)
        chunk = source_local_pcm[start:end].copy()
        edge = min(fade, len(chunk) // 2)
        chunk[:edge] *= np.linspace(0, 1, edge)
        chunk[-edge:] *= np.linspace(1, 0, edge)
        local_pcm[start:end] = chunk
    out = HERE / "out"
    out.mkdir(exist_ok=True)
    write(out / "system.wav", system_pcm)
    write(out / "headphones-mic.wav", local_pcm)
    # Delayed direct sound plus two quiet reflections: fixed light synthetic room tail.
    echo = np.zeros(SAMPLES, dtype=np.float32)
    for delay, gain in ((0.040, 1.0), (0.071, .22), (0.119, .10)):
        shift = round(delay * RATE)
        echo[shift:] += gain * system_pcm[:SAMPLES-shift]
    for db in (-20, -10):
        mixed = local_pcm + echo * 10 ** (db / 20)
        write(out / f"speakers-{db}-mic.wav", mixed)
    system_turns = [dict(row, speaker={"Ben": "A", "David": "B"}[row["speaker"]])
                    for row in system.reference_segments() if row["speaker"] in ("Ben", "David")]
    local_turns = [dict(row, speaker={"Lex Fridman": "C", "Keyu Jin": "D"}[row["speaker"]])
                   for row in selected_turns]
    reference = {
        "duration_s": SECONDS, "sample_rate": RATE,
        "sources": {"system": system.clip_id, "microphone": local.clip_id},
        "system_turns": system_turns, "local_turns": local_turns,
        "variants": {
            "headphones": {"system": "system.wav", "microphone": "headphones-mic.wav",
                           "echo_db": None, "echo_delay_ms": None, "echo_intervals": []},
            **{f"speakers-{db}": {"system": "system.wav",
                                 "microphone": f"speakers-{db}-mic.wav", "echo_db": db,
                                 "echo_delay_ms": 40,
                                 "echo_intervals": [[max(0, row["start"] + .04), min(SECONDS, row["end"] + .119)]
                                                    for row in system_turns]}
               for db in (-20, -10)},
        },
    }
    (out / "reference.json").write_text(json.dumps(reference, indent=2) + "\n")
    print(json.dumps({"output": str(out), "duration_s": SECONDS,
                      "system_turns": len(system_turns), "local_turns": len(local_turns),
                      "local_by_voice": {s: sum(row["speaker"] == s for row in local_turns)
                                         for s in ("C", "D")},
                      "variants": list(reference["variants"])}, indent=2))


if __name__ == "__main__":
    main()
