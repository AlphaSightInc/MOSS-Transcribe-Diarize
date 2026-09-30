"""Build 480 s two-lane *listener* fixtures: long local-silent stretches with room noise events.

A: far-end English (public Acquired audio), local Mandarin (TTS Tingting/Meijia).
B: far-end Mandarin (TTS Tingting/Meijia), local English (public Lex/Keyu turns) + English TTS backchannels.
Routes: hp (headphones, raw mic) and sp (speakers + browser AEC residual of the far end at -38 dBFS).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE)]
import noise  # noqa: E402
import tts  # noqa: E402

RATE = 16000
SECONDS = 480
N = SECONDS * RATE
BENCH = ROOT / "prototypes/streaming-diarization/data/real/benchmark_5m"
OUT = HERE / "out" / "fixture2"
BACKCHANNELS = [(46.0, -30), (70.0, -20), (190.0, -30), (266.0, -20), (330.0, -20), (450.0, -30)]


def rms_to(x, dbfs):
    return x * 10 ** (dbfs / 20) / (np.sqrt(np.mean(x ** 2)) or 1)


def place(lane, x, at_s):
    s = int(at_s * RATE)
    x = x[:N - s]
    lane[s:s + len(x)] += x
    return at_s + len(x) / RATE


def clip(name):
    x = sf.read(str(BENCH / name / "audio.wav"), dtype="float64")[0]
    rows = [json.loads(line) for line in (BENCH / name / "reference.jsonl").read_text().splitlines() if line.strip()]
    return x, rows


def en_system():
    a, ra = clip("acquired_alphabet")
    b, rb = clip("acquired_coca_cola")
    lane = np.concatenate([a[:300 * RATE], b[:180 * RATE]])[:N]
    rows = [r for r in ra if r["end"] <= 300] + [dict(r, start=r["start"] + 300, end=r["end"] + 300)
                                                 for r in rb if r["end"] <= 180]
    return rms_to(lane, -19.5), rows


def zh_system():
    voices = {"A": tts.utterances(tts.ZH_SYSTEM, "Tingting", "sys"),
              "B": tts.utterances(tts.ZH_SYSTEM[::-1], "Meijia", "sysm")}
    lane = np.zeros(N)
    rows, t, i = [], .5, 0
    rng = np.random.default_rng(7)
    while True:
        speaker = "AB"[(i // 2) % 2]
        text, x = voices[speaker][i % len(tts.ZH_SYSTEM)]
        if t + len(x) / RATE > SECONDS - .5:
            break
        stop = place(lane, rms_to(x, -19.5), t)
        rows.append({"start": t, "end": stop, "speaker": speaker, "text": text})
        t = stop + rng.uniform(.25, .8)
        i += 1
    return lane, rows


def zh_local():
    pool = {"C": tts.utterances(tts.ZH + tts.ZH_LOCAL_MORE, "Tingting", "loc"),
            "D": tts.utterances((tts.ZH + tts.ZH_LOCAL_MORE)[::-1], "Meijia", "locm")}
    lane = np.zeros(N)
    rows, k = [], {"C": 0, "D": 0}
    for start, end, speaker in ((15, 45, "C"), (250, 264, "D")):
        t = start
        while True:
            text, x = pool[speaker][k[speaker]]
            if t + len(x) / RATE > end:
                break
            stop = place(lane, rms_to(x, -20), t)
            rows.append({"start": t, "end": stop, "speaker": speaker, "text": text})
            t = stop + .35
            k[speaker] += 1
    return lane, rows


def en_local():
    x, rows = clip("lex_keyu_jin")
    lane = np.zeros(N)
    out = []
    t = 15.0
    for r in rows:
        if 140 <= r["start"] < 170:
            seg = x[int(r["start"] * RATE):int(r["end"] * RATE)]
            stop = place(lane, rms_to(seg, -20), t)
            out.append({"start": t, "end": stop, "speaker": r["speaker"], "text": r["text"]})
            t = stop
    for r in rows:
        if r["start"] == 221.0:
            seg = x[int(r["start"] * RATE):int(r["end"] * RATE)]
            stop = place(lane, rms_to(seg, -20), 250.0)
            out.append({"start": 250.0, "end": stop, "speaker": r["speaker"], "text": r["text"]})
    return lane, out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"duration_s": SECONDS, "sample_rate": RATE, "variants": {}}
    for case, (system_fn, local_fn, texts, voices) in {
        "A": (en_system, zh_local, tts.ZH_BACKCHANNEL, ["Tingting", "Meijia"]),
        "B": (zh_system, en_local, tts.EN_BACKCHANNEL, ["Daniel", "Moira"]),
    }.items():
        rng = np.random.default_rng({"A": 21, "B": 22}[case])
        system, system_rows = system_fn()
        local, local_rows = local_fn()
        backs = []
        for j, (at, level) in enumerate(BACKCHANNELS):
            text = texts[j]
            x = tts.load(tts.say(text, voices[j % 2], f"{voices[j % 2]}-bc2-{case}-{j:02d}"))
            stop = place(local, rms_to(x, level), at)
            backs.append({"start": at, "end": stop, "speaker": "CD"[j % 2], "text": text, "level_dbfs": level})
        speech = [(r["start"], r["end"]) for r in local_rows + backs]
        events, event_rows = noise.scatter(N, rng, list(noise.EVENTS), every=(1.5, 5.0), avoid=speech)
        headphones = local + events + noise.room_tone(N, rng)
        speakers = headphones + noise.aec_residual(system, rng)
        sf.write(str(OUT / f"{case}-system.wav"), np.clip(system, -1, 1), RATE, subtype="PCM_16")
        for route, mic in (("hp", headphones), ("sp", speakers)):
            name = f"{case}-{route}"
            sf.write(str(OUT / f"{name}-mic.wav"), np.clip(mic, -1, 1), RATE, subtype="PCM_16")
            manifest["variants"][name] = {"system": f"{case}-system.wav", "microphone": f"{name}-mic.wav",
                                          "case": case, "aec_residual_dbfs": None if route == "hp" else -38}
        manifest[case] = {"local_turns": local_rows, "backchannels": backs, "system_turns": system_rows,
                          "noise_events": event_rows}
    (OUT / "reference.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(json.dumps({k: {"local": len(manifest[k]["local_turns"]), "back": len(manifest[k]["backchannels"]),
                          "events": len(manifest[k]["noise_events"])} for k in "AB"}))


if __name__ == "__main__":
    main()
