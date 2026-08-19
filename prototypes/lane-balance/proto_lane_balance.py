#!/usr/bin/env python3
"""PROTOTYPE: does matching lane levels recover the quiet speaker's words?

The operator's attended runs lose almost everything they say while the shared lane transcribes
cleanly. Measured disparity is ~15 dB. A previous attempt to correct this measured WORSE and was
rejected -- but that test played the SAME audio in both lanes, where boosting one lane just doubles
the same signal. This test uses two DIFFERENT speakers, which is the real condition.

Per-lane references come from transcribing each lane clean at full level, then we measure how much
of each reference survives the mix under each policy.

  .venv/bin/python prototypes/lane-balance/proto_lane_balance.py
"""
from __future__ import annotations
import array, contextlib, json, math, re, sys, wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402

BASE = "http://127.0.0.1:18000/v1"
MODEL = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
DATA = REPO / "prototypes/streaming-diarization/data"
OUT = Path("/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/7d302197-12d3-4d32-94e9-8f38668c3764/scratchpad/lanebal")
OUT.mkdir(parents=True, exist_ok=True)
SECONDS = 12
HEADROOM = 10 ** (-6 / 20)          # live_mixer.py:16
LIMIT, RANGE = 0.98, 0.02           # live_mixer.py:17-18
QUIET_DB = -15.0                    # the measured microphone disparity


def read(path: Path, seconds: int) -> tuple[list[float], int]:
    with contextlib.closing(wave.open(str(path))) as w:
        sr = w.getframerate()
        raw = w.readframes(sr * seconds)
    ints = array.array("h"); ints.frombytes(raw)
    return [v / 32768.0 for v in ints], sr


def write(path: Path, samples: list[float], sr: int) -> None:
    out = array.array("h", (int(max(-1.0, min(1.0, s)) * 32767) for s in samples))
    with contextlib.closing(wave.open(str(path), "w")) as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(out.tobytes())


def rms(xs: list[float]) -> float:
    return math.sqrt(sum(x * x for x in xs) / len(xs)) if xs else 0.0


def mix(system: list[float], microphone: list[float]) -> list[float]:
    """Exactly live_mixer.py's soft-limited sum."""
    out = []
    for s, m in zip(system, microphone):
        v = (s * HEADROOM) + (m * HEADROOM)
        if abs(v) > LIMIT:
            v = math.copysign(LIMIT + RANGE * math.tanh((abs(v) - LIMIT) / RANGE), v)
        out.append(max(-1.0, min(1.0, v)))
    return out


def words(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def recall(reference: str, hypothesis: str) -> float:
    ref, hyp = words(reference), set(words(hypothesis))
    if not ref:
        return 0.0
    return sum(1 for w in ref if w in hyp) / len(ref)


def transcribe(runner: VllmRunner, path: Path) -> str:
    result = runner.transcribe(str(path))
    return getattr(result, "text", str(result))


def main() -> int:
    print = lambda *a, **k: __builtins__['print'](*a, **{**k, 'flush': True}) if isinstance(__builtins__, dict) else None
    runner = VllmRunner(base_url=BASE, model=MODEL, api_key=None, timeout=90)
    loud, sr = read(DATA / "meet_k2_s0.wav", SECONDS)       # stands in for the shared/tab lane
    quiet_src, _ = read(DATA / "meet_k2_s1.wav", SECONDS)   # stands in for the microphone lane

    # attenuate the microphone lane to the measured real-world disparity
    scale = 10 ** (QUIET_DB / 20)
    quiet = [s * scale for s in quiet_src]

    print(f"lane levels: shared rms {rms(loud):.4f}  microphone rms {rms(quiet):.4f} "
          f"({20*math.log10(rms(quiet)/rms(loud)):.1f} dB apart)")

    # per-lane references, each transcribed clean at full level
    write(OUT / "ref_shared.wav", loud, sr)
    write(OUT / "ref_mic.wav", quiet_src, sr)
    ref_shared = transcribe(runner, OUT / "ref_shared.wav")
    ref_mic = transcribe(runner, OUT / "ref_mic.wav")
    print(f"\nreference words: shared {len(words(ref_shared))}, microphone {len(words(ref_mic))}")

    policies = {
        "current (equal gain, mic left 15 dB down)": quiet,
        "matched (mic scaled to the shared lane's rms)":
            [s * (rms(loud) / rms(quiet)) for s in quiet] if rms(quiet) else quiet,
        "half-matched (mic brought up 7.5 dB)": [s * (10 ** (7.5 / 20)) for s in quiet],
    }

    rows = []
    for name, micro in policies.items():
        path = OUT / (re.sub(r"[^a-z]+", "_", name.lower()) + ".wav")
        write(path, mix(loud, micro), sr)
        text = transcribe(runner, path)
        r_mic, r_sh = recall(ref_mic, text), recall(ref_shared, text)
        rows.append((name, r_mic, r_sh, len(words(text))))
        print(f"\n--- {name}\n    microphone recall {r_mic:6.1%}   shared recall {r_sh:6.1%}   "
              f"words {len(words(text))}")
        (OUT / (path.stem + ".txt")).write_text(text, encoding="utf-8")

    print("\n=== SUMMARY (microphone recall is the number that matters) ===")
    for name, r_mic, r_sh, n in rows:
        print(f"  {r_mic:6.1%} mic   {r_sh:6.1%} shared   {name}")
    json.dump(
        {"seconds": SECONDS, "quiet_lane_db": QUIET_DB,
         "results": [{"policy": n, "microphone_recall": m, "shared_recall": s, "words": w}
                     for n, m, s, w in rows]},
        (OUT / "result.json").open("w"), indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
