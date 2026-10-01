"""Public/synthetic fixtures shaped like the real session's measured properties (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-d.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/build.py

Measured on the real meeting's saved mix (numbers only, real_facts.json): Chinese narration with
Latin names 0.1-20 s, 1.3 s pause, English two-speaker speech 21.5-34 s, 3 s of floor; system
lane about -17 dBFS rms; microphone floor about -63 dBFS; no echo path stronger than about
-35 dB detectable (echo cancellation on); the user's own microphone speech in a microphone-only
meeting was about -27 dBFS rms.

System lane  = macOS `say` Tingting (Mandarin with Latin names) + benchmark_5m/acquired_alphabet
               2-15 s (public podcast, two speakers).
Microphone   = floor + echo of the system lane (P69 taps) at a chosen level + public local speech
               (benchmark_5m/lex_keyu_jin, Lex Fridman) at -27 dBFS.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

RATE = 16000
ROOT = Path(__file__).resolve().parents[3]
B5 = ROOT / "prototypes/streaming-diarization/data/real/benchmark_5m"
OUT = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/mic-speaker-echo/fixtures"

ZH = ("一直在研究这个问题的是麻省理工学院 Media Lab 的计算机教授 Alan Turing。他研究神经网络的训练方法已经八九年，"
      "合作者 Grace Hopper 在 Microsoft 上班。Google 宣布之前，他跟 Google 的人开了一次视频会议。"
      "这是科技频道 Computerphile 十月初上架的专访，他从头讲那次会议，也讲学术界为什么开始不愿公开自己的研究问题。")
ZH_ONLY = ("一直在研究这个问题的是清华大学计算机系的一位教授。他研究神经网络的训练方法已经八九年，"
           "合作者在一家软件公司上班。公司宣布之前，他跟公司的人开了一次视频会议。"
           "这是科技频道十月初上架的专访，他从头讲那次会议，也讲学术界为什么开始不愿公开自己的研究问题。")


def n(seconds: float) -> int:
    return int(round(seconds * RATE))


def rms(x) -> float:
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def db(v: float) -> float:
    return 20 * np.log10(max(v, 1e-12))


def say(text: str, voice: str, rate: int) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "x.aiff"
        subprocess.run(["say", "-v", voice, "-r", str(rate), "-o", str(aiff), text], check=True)
        x, sr = sf.read(str(aiff), dtype="float64")
    x = x if x.ndim == 1 else x.mean(axis=1)
    x = resample_poly(x, RATE, sr) if sr != RATE else x
    loud = np.flatnonzero(np.abs(x) > 10 ** (-45 / 20))
    return x[max(0, loud[0] - n(.02)):loud[-1] + n(.05)]


def say_within(text: str, voice: str, seconds: float) -> tuple[np.ndarray, int]:
    """The slowest speaking rate that fits the real narration's length (it ran about 5.5 units/s)."""
    rate = 185
    x = say(text, voice, rate)
    while len(x) > n(seconds):
        rate = int(np.ceil(rate * len(x) / n(seconds) * 1.01))
        x = say(text, voice, rate)
    return x, rate


def read(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float64")
    assert sr == RATE, (path, sr)
    return x if x.ndim == 1 else x.mean(axis=1)


def speech_level(x: np.ndarray, target_dbfs: float) -> np.ndarray:
    """Scale so the rms over the 100 ms blocks louder than -50 dBFS (the speech) is the target."""
    blocks = x[:len(x) // 1600 * 1600].reshape(-1, 1600)
    level = np.sqrt((blocks ** 2).mean(axis=1))
    active = blocks[level > 10 ** (-50 / 20)]
    return x * 10 ** (target_dbfs / 20) / rms(active.ravel())


def fade(x: np.ndarray, seconds: float = .04) -> np.ndarray:
    x, k = x.copy(), min(n(seconds), len(x) // 2)
    x[:k] *= np.linspace(0, 1, k)
    x[-k:] *= np.linspace(1, 0, k)
    return x


def system_lane(zh: np.ndarray, total: float = 37.0, english_at: float | None = 21.5) -> np.ndarray:
    lane = np.zeros(n(total))
    zh = speech_level(zh, -17)
    assert len(zh) <= n(20.3), len(zh) / RATE
    lane[n(.1):n(.1) + len(zh)] = zh
    if english_at is not None:
        en = speech_level(fade(read(B5 / "acquired_alphabet" / "audio.wav")[n(1.6):n(15.4)]), -17)
        lane[n(english_at):n(english_at) + len(en)] = en[:len(lane) - n(english_at)]
    return lane


def echo_of(system: np.ndarray, level_db: float) -> np.ndarray:
    echo = np.zeros(len(system))
    for delay, gain in ((0.040, 1.0), (0.071, .22), (0.119, .10)):  # the P69 room
        echo[n(delay):] += gain * system[:len(system) - n(delay)]
    return echo * 10 ** (level_db / 20)


def local_speech(total: float, turns: list[tuple[float, float, float]]) -> np.ndarray:
    """(place_at, source_start, source_end) cuts of Lex Fridman, each at -27 dBFS speech rms."""
    src = read(B5 / "lex_keyu_jin" / "audio.wav")
    out = np.zeros(n(total))
    for at, lo, hi in turns:
        cut = speech_level(fade(src[n(lo):n(hi)]), -27)
        out[n(at):n(at) + len(cut)] += cut[:len(out) - n(at)]
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    floor = np.random.default_rng(72).normal(0, 10 ** (-63 / 20), n(37.0))
    zh, zh_rate = say_within(ZH, "Tingting", 19.9)
    zh_only, zh_only_rate = say_within(ZH_ONLY, "Tingting", 19.9)
    lanes = {"sys-zhlatin-en": system_lane(zh), "sys-zhlatin": system_lane(zh, english_at=None),
             "sys-zhonly-en": system_lane(zh_only)}
    system = lanes["sys-zhlatin-en"]
    # Local turns (Lex Fridman): "Can you elaborate on that?" is 1 s; 140-146 s is a 6 s sentence.
    short = [(5.0, 96.0, 97.1), (20.3, 96.0, 97.1), (35.2, 96.0, 97.1)]      # all under 2 s
    long_ = [(9.0, 140.0, 146.0), (34.3, 221.0, 223.6)]                      # 6 s under the tab, 2.6 s after it
    mics = {
        "mic-listen-aec40": floor + echo_of(system, -40),
        "mic-short-aec40": floor + echo_of(system, -40) + local_speech(37.0, short),
        "mic-long-aec40": floor + echo_of(system, -40) + local_speech(37.0, long_),
        "mic-listen-echo25": floor + echo_of(system, -25),
        "mic-short-echo25": floor + echo_of(system, -25) + local_speech(37.0, short),
        "mic-long-echo25": floor + echo_of(system, -25) + local_speech(37.0, long_),
        "mic-short-noecho": floor + local_speech(37.0, short),
    }
    report = {"zh_seconds": len(zh) / RATE, "zh_only_seconds": len(zh_only) / RATE,
              "say_rate": {"zh": zh_rate, "zh_only": zh_only_rate},
              "local_turns": {"short": short, "long": long_}, "text": {"zh": ZH, "zh_only": ZH_ONLY}, "files": {}}
    for name, x in {**lanes, **mics}.items():
        sf.write(str(OUT / f"{name}.wav"), np.clip(x, -1, 1), RATE, subtype="PCM_16")
        report["files"][f"{name}.wav"] = {
            "seconds": len(x) / RATE, "rms_dbfs": round(db(rms(x)), 1),
            "rms_dbfs_0_20": round(db(rms(x[:n(20)])), 1), "rms_dbfs_35_37": round(db(rms(x[n(36.3):])), 1),
            "sha256": hashlib.sha256((OUT / f"{name}.wav").read_bytes()).hexdigest()}
    (OUT / "fixtures.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "text"}, indent=1))


main()
