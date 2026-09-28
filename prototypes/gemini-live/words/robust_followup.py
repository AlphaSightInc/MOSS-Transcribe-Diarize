"""P52 robustness falsification bench. One command per phase; all audio is public/generated.

PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/words/robust_followup.py --phase prepare
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import Clip, clips  # noqa: E402
from gemini_common import diarize_window, read_wav, spend  # noqa: E402
from proto_words import run_live  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.2-STATUS.md")
AUDIO = EVIDENCE / "robust_audio"
RATE = 16000
ACCEPT6 = ["discussion_jamie_dimon_180s", "discussion_rtfl_90s", "interview_adam_frank_180s",
           "interview_bill_ackman_60s", "interview_keyu_jin_60s", "mono_javier_intro_50s"]


def status(message: str) -> None:
    with STATUS.open("a") as f:
        f.write(f"[{datetime.now().astimezone():%Y-%m-%d %H:%M:%S %Z}] {message}\n")
    print(message, flush=True)


def save_audio(name: str, pcm: np.ndarray) -> Path:
    AUDIO.mkdir(parents=True, exist_ok=True)
    path = AUDIO / f"{name}.wav"
    sf.write(str(path), np.asarray(pcm, dtype=np.int16), RATE, subtype="PCM_16")
    return path


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(np.asarray(x, dtype=np.float64) / 32768))))


def scaled(x: np.ndarray, target: float) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    x = x / max(float(np.sqrt(np.mean(x*x))), 1e-12) * (target * 32768)
    return np.clip(np.rint(x), -32768, 32767).astype(np.int16)


def prepare() -> None:
    rng = np.random.default_rng(520926)
    n = RATE * 60
    manifest = []
    manifest.append(("silence", save_audio("silence", np.zeros(n, dtype=np.int16)), "digital zero"))
    for color in ("white", "pink"):
        x = rng.normal(size=n)
        if color == "pink":
            frequency = np.fft.rfftfreq(n, 1/RATE)
            frequency[0] = 1/60
            x = np.fft.irfft(np.fft.rfft(x) / np.sqrt(frequency), n=n)
        for level in (0.0003, 0.001, 0.003):
            name = f"{color}_{level:.4f}"
            path = save_audio(name, scaled(x, level))
            manifest.append((name, path, f"{color} noise, target RMS {level}"))
    t = np.arange(n) / RATE
    envelope = 0.28 + 0.72 * (np.sin(2 * np.pi * 2 * t) > 0)
    chord = sum(np.sin(2 * np.pi * f * t) for f in (220, 277.18, 329.63, 440))
    beat = 0.3 * np.sin(2 * np.pi * 55 * t) * np.exp(-((t % 0.5) / 0.07))
    music = scaled(envelope * chord + beat, 0.018)
    manifest.append(("music_like", save_audio("music_like", music), "synthetic chord plus rhythm"))

    public = next(c for c in clips() if c.clip_id == "mono_javier_intro_50s")
    p = read_wav(public.audio)
    start = RATE * 25
    gap = np.concatenate((p[:start], np.zeros(RATE * 20, dtype=np.int16), p[start:]))
    manifest.append(("javier_gap20", save_audio("javier_gap20", gap),
                     "public Javier50 with digital zero at audio 25-45 s"))

    e1 = next(c for c in clips() if c.clip_id == "e1")
    system, mic = read_wav(e1.audio), read_wav(e1.mic_audio)
    if len(system) != len(mic):
        raise ValueError("E1 tracks differ in length")
    mix_float = system.astype(np.int32) + mic.astype(np.int32)
    mix = np.clip(mix_float, -32768, 32767).astype(np.int16)
    manifest.append(("e1_mixed", save_audio("e1_mixed", mix),
                     f"E1 system+mic at fixture gains; clipped samples {int(np.sum((mix_float < -32768) | (mix_float > 32767)))}"))
    e1_gap = np.concatenate((mix[180*RATE:200*RATE], np.zeros(20*RATE, dtype=np.int16),
                             mix[200*RATE:220*RATE]))
    manifest.append(("e1_gap20", save_audio("e1_gap20", e1_gap),
                     "E1 mixed audio 180-220s with 20s digital zero inserted at derived audio 20-40s"))

    a = next(c for c in clips("gold9") if c.clip_id == "benchmark:lex_bill_ackman")
    b = next(c for c in clips("gold9") if c.clip_id == "benchmark:lex_keyu_jin")
    pa, pb = read_wav(a.audio)[:n], read_wav(b.audio)[:n]
    length = min(len(pa), len(pb))
    pa, pb = pa[:length], pb[:length]
    aa = pa.astype(np.float64) / max(rms(pa) * 32768, 1)
    bb = pb.astype(np.float64) / max(rms(pb) * 32768, 1)
    for quiet_db in (0, -10):
        ratio = 10 ** (quiet_db / 20)
        joined = (aa + ratio * bb) * (0.07 * 32768)
        peak = float(np.max(np.abs(joined)))
        if peak > 32767:
            joined *= 32000 / peak
        name = f"overlap_keyu_{'equal' if quiet_db == 0 else 'minus10'}"
        path = save_audio(name, np.rint(joined).astype(np.int16))
        manifest.append((name, path, f"Bill:Keyu RMS ratio 0:{quiet_db} dB; common gain only"))
    rows = [{"case": name, "path": str(path), "description": description,
             "seconds": len(read_wav(path))/RATE, "rms": rms(read_wav(path))}
            for name, path, description in manifest]
    (EVIDENCE / "robust-manifest.json").write_text(json.dumps(rows, indent=2) + "\n")
    status(f"Robust audio prepared: {len(rows)} generated/public-input variants; E1 mono sum, gap20, overlap 0/-10 dB. Manifest {EVIDENCE/'robust-manifest.json'}.")


def synthetic(name: str) -> Clip:
    return Clip(name, "robust", AUDIO / f"{name}.wav", None)


def make_args(language: str, tail: float = 2.0) -> SimpleNamespace:
    return SimpleNamespace(arm="w3", language_code=language, turn=0, sensitivity="high", silence_ms=500,
                           thinking=None, max_output=None, tail_silence=tail, limit=0.0,
                           drain=12.0, quiet=True)


async def run_cases(cases: list[tuple[str, Clip, str]]) -> None:
    sem = asyncio.Semaphore(2)

    async def one(tag: str, clip: Clip, language: str) -> None:
        async with sem:
            path = EVIDENCE / f"robust-live-{tag}-{language}.json"
            if path.exists():
                status(f"Robust Live {tag}/{language}: existing receipt reused {path}.")
                return
            try:
                d = await run_live(make_args(language), clip)
                path.write_text(json.dumps(d, indent=2) + "\n")
                tokens = sum(len(u["text"].split()) for u in d["hypothesis"])
                status(f"Robust Live {tag}/{language}: sent {d['sent_s']}/{d['audio_s']}s; finals {d['selected_updates']}, whitespace tokens {tokens}, WER {(d['score'] or {}).get('wer')}, errors {d['errors']}, usage complete {d['cost_complete']}; {path}.")
            except Exception as exc:
                status(f"Robust Live {tag}/{language}: FAILED {type(exc).__name__}: {str(exc)[:300]}.")
                raise

    await asyncio.gather(*(one(*case) for case in cases))


def live_phase(phase: str) -> None:
    if phase == "nonspeech":
        names = ["silence", "white_0.0003", "white_0.0010", "white_0.0030",
                 "pink_0.0003", "pink_0.0010", "pink_0.0030", "music_like", "javier_gap20"]
        cases = [(name, synthetic(name), language) for name in names for language in ("auto", "en-US")]
    elif phase == "accept6":
        by_id = {c.clip_id: c for c in clips("accept6")}
        cases = [(name, by_id[name], language) for name in ACCEPT6 for language in ("auto", "en-US")]
    elif phase == "e1":
        e1 = next(c for c in clips() if c.clip_id == "e1")
        cases = [("e1_system", e1, "en-US"), ("e1_mixed", synthetic("e1_mixed"), "en-US"),
                 ("e1_gap20", synthetic("e1_gap20"), "en-US")]
    elif phase == "overlap":
        cases = [(name, synthetic(name), "en-US") for name in ("overlap_keyu_equal", "overlap_keyu_minus10")]
    else:
        raise ValueError(phase)
    asyncio.run(run_cases(cases))
    observed = spend("P52").get("P52", {}).get("cost_usd", 0)
    status(f"Robust Live phase {phase} complete; P52 ledger observed ${observed:.3f}, Live actual cost unmeasured.")


def batch_phase() -> None:
    for name in ("overlap_keyu_equal", "overlap_keyu_minus10"):
        path = EVIDENCE / f"robust-batch-{name}.json"
        if path.exists():
            continue
        pcm = read_wav(AUDIO / f"{name}.wav")
        result = diarize_window(pcm, use_cache=False, ledger_lane="P52", max_attempts=3)
        row = {"case": name, "words": [{"text": w.text, "speaker": w.speaker,
                                           "start": w.start, "end": w.end} for w in result.words],
               "cost_usd": result.cost_usd(), "cached": result.cached,
               "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0},
               "usage": result.usage}
        path.write_text(json.dumps(row, indent=2) + "\n")
        status(f"Robust batch {name}: {len(result.words)} words, anomalies {row['timing_anomalies']}, cost ${result.cost_usd():.6f}; {path}.")


def batch_variants_phase() -> None:
    pcm = read_wav(AUDIO / "overlap_keyu_minus10.wav")
    for name, config in (("language_en-US", {"language_codes": ["en-US"]}),
                         ("no_diarization", {"diarize": False})):
        path = EVIDENCE / f"robust-batch-overlap_keyu_minus10-{name}.json"
        if path.exists():
            continue
        result = diarize_window(pcm, use_cache=False, ledger_lane="P52", max_attempts=3, **config)
        row = {"case": "overlap_keyu_minus10", "variant": name,
               "words": [{"text": w.text, "speaker": w.speaker,
                           "start": w.start, "end": w.end} for w in result.words],
               "cost_usd": result.cost_usd(), "cached": result.cached,
               "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0},
               "usage": result.usage}
        path.write_text(json.dumps(row, indent=2) + "\n")
        status(f"Robust batch -10dB {name}: {len(result.words)} words, anomalies {row['timing_anomalies']}, cost ${result.cost_usd():.6f}; {path}.")


def rolling_overlap_phase() -> None:
    for name in ("overlap_keyu_equal", "overlap_keyu_minus10"):
        pcm = read_wav(AUDIO / f"{name}.wav")
        for end_s in (30, 40, 50, 60):
            start_s = end_s - 30
            path = EVIDENCE / f"robust-rolling-{name}-{start_s}-{end_s}.json"
            if path.exists():
                continue
            result = diarize_window(pcm[start_s*RATE:end_s*RATE], use_cache=False,
                                    ledger_lane="P52", max_attempts=3)
            row = {"case": name, "start_s": start_s, "end_s": end_s,
                   "words": [{"text": w.text, "speaker": w.speaker,
                               "start": start_s+w.start, "end": start_s+w.end} for w in result.words],
                   "cost_usd": result.cost_usd(),
                   "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0}}
            path.write_text(json.dumps(row, indent=2) + "\n")
            status(f"Robust rolling {name} {start_s}-{end_s}: {len(result.words)} words, anomalies {row['timing_anomalies']}, cost ${result.cost_usd():.6f}; {path}.")


def e1_oracle_phase() -> None:
    """Model-only lexical probe on the known synthetic operator utterances, sans system echo."""
    mic = read_wav(Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/dx-replay/fixture/M2-microphone.wav"))
    for at_s in (30, 135, 248):
        path = EVIDENCE / f"robust-e1-operator-{at_s}.json"
        if path.exists():
            continue
        # The fixture declares exactly 3 s of corpus voice at each position.
        pcm = mic[at_s*RATE:(at_s+3)*RATE]
        result = diarize_window(pcm, use_cache=False, ledger_lane="P52", max_attempts=3)
        row = {"at_s": at_s, "model_only_truth": True,
               "words": [{"text": w.text, "start": w.start, "end": w.end} for w in result.words],
               "text": result.text, "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0},
               "cost_usd": result.cost_usd()}
        path.write_text(json.dumps(row, indent=2) + "\n")
        status(f"Robust E1 operator model proxy at {at_s}s: {len(result.words)} words, anomalies {row['timing_anomalies']}, cost ${result.cost_usd():.6f}; {path}.")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--phase", choices=["prepare", "nonspeech", "accept6", "e1", "overlap", "batch", "batch_variants", "rolling_overlap", "e1_oracle"], required=True)
    args = p.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.phase == "batch":
        batch_phase()
    elif args.phase == "batch_variants":
        batch_variants_phase()
    elif args.phase == "rolling_overlap":
        rolling_overlap_phase()
    elif args.phase == "e1_oracle":
        e1_oracle_phase()
    else:
        live_phase(args.phase)


if __name__ == "__main__":
    main()
