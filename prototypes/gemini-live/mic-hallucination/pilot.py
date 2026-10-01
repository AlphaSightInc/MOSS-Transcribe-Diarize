"""Pilot: does Gemini 3.5 Transcribe (production mic-window config) invent words on mic noise?"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE.parent / "common"), str(HERE)]
from gemini_common import diarize_window, spend  # noqa: E402
import noise  # noqa: E402
import tts  # noqa: E402

RATE = 16000
N = 30 * RATE
LANE = "r4c-mic-halluc"
BENCH = ROOT / "prototypes/streaming-diarization/data/real/benchmark_5m"


def speech(clip: str, offset_s: float, n: int) -> np.ndarray:
    x, sr = sf.read(str(BENCH / clip / "audio.wav"), dtype="float32")
    s = int(offset_s * sr)
    return x[s:s + n].astype(np.float64)


def zh_stream(n: int, voice="Meijia") -> np.ndarray:
    parts = [x for _, x in tts.zh_sentences(voice)]
    y = np.concatenate([np.concatenate([p, np.zeros(int(.4 * RATE))]) for p in parts])
    return np.resize(y, n)


def build(kind: str, seed: int) -> tuple[np.ndarray, list]:
    rng = np.random.default_rng(seed)
    base = noise.room_tone(N, rng)
    events = []
    if kind == "room":
        x = base
    elif kind == "fan":
        x = base + noise.fan(N, rng)
    elif kind in ("breath", "keys", "cough", "throat", "creak"):
        ev, events = noise.scatter(N, rng, [kind] + (["smack"] if kind == "breath" else []))
        x = base + ev
    elif kind == "mix":
        ev, events = noise.scatter(N, rng, list(noise.EVENTS))
        x = base + ev
    elif kind == "distant_en":
        x = base + noise.distant(speech("acquired_nfl", 60 + 30 * seed % 200, N), rng)
    elif kind == "distant_zh":
        x = base + noise.distant(zh_stream(N), rng)
    elif kind == "aec_en":
        x = base + noise.aec_residual(speech("acquired_alphabet", 30 + 30 * seed % 200, N), rng)
    elif kind == "aec_zh":
        x = base + noise.aec_residual(zh_stream(N, "Tingting"), rng)
    else:
        raise ValueError(kind)
    return np.clip(np.rint(x * 32767), -32768, 32767).astype(np.int16), events


def main() -> None:
    kinds = sys.argv[1].split(",")
    seeds = [int(s) for s in sys.argv[2].split(",")]
    out = HERE / "out" / "pilot"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for kind in kinds:
        for seed in seeds:
            pcm, events = build(kind, seed)
            sf.write(str(out / f"{kind}-{seed}.wav"), pcm, RATE, subtype="PCM_16")
            r = diarize_window(pcm, ledger_lane=LANE)
            words = [(w.text, round(w.start, 2), round(w.end, 2)) for w in r.words]
            rows.append({"kind": kind, "seed": seed, "cached": r.cached, "cost": r.cost_usd(),
                         "words": words, "events": len(events)})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    (out / f"pilot-{'-'.join(kinds)}.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(json.dumps(spend(LANE)))


if __name__ == "__main__":
    main()
