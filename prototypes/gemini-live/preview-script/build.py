"""Mic fixtures for the preview script rule (two genuinely different Mandarin TTS voices: Tingting
for the far end, Meijia for the local person; human English from the public Lex/Acquired corpus).

zh2-sp : Mandarin meeting, speakers route: local Meijia turns + backchannels, room noise events,
         and the browser-AEC residual of the Tingting far end (hallucination source).
zh2-echo: the same local speech with the Tingting far end as raw -25 dB echo (mic-preview-echo case).
en2zh  : English meeting (Acquired far end); local Lex English, then switches to Mandarin at 110 s
         (Meijia: two short replies, then pure-Mandarin sentences).
zh2en  : pure-Mandarin meeting (no Latin anywhere before the switch); local Meijia Mandarin, then
         switches to English at 110 s (Samantha/Daniel short replies, then a human Lex turn).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MH = HERE.parent / "mic-hallucination"
sys.path[:0] = [str(MH)]
import noise  # noqa: E402
import tts  # noqa: E402

RATE = 16000
OUT = HERE / "out"
BENCH = ROOT / "prototypes/streaming-diarization/data/real/benchmark_5m"


def rms_to(x, dbfs):
    return x * 10 ** (dbfs / 20) / (np.sqrt(np.mean(x ** 2)) or 1)


def place(lane, x, at_s, rows, text, speaker, level=-20):
    s = int(at_s * RATE)
    x = rms_to(x, level)[:len(lane) - s]
    lane[s:s + len(x)] += x
    rows.append({"start": at_s, "end": at_s + len(x) / RATE, "text": text, "speaker": speaker})
    return at_s + len(x) / RATE


def clip(name):
    x = sf.read(str(BENCH / name / "audio.wav"), dtype="float64")[0]
    rows = [json.loads(l) for l in (BENCH / name / "reference.jsonl").read_text().splitlines() if l.strip()]
    return x, rows


def sentences(texts, voice, tag, lane, rows, start, end, speaker, gap=.4):
    t = start
    for i, (text, x) in enumerate(tts.utterances(texts, voice, tag)):
        if t + len(x) / RATE > end:
            break
        t = place(lane, x, t, rows, text, speaker) + gap
    return t


def zh_system(seconds):
    lane, rows = np.zeros(seconds * RATE), []
    sentences(tts.ZH_SYSTEM * 3, "Tingting", "sys", lane, rows, .5, seconds - .5, "A", gap=.6)
    return lane, rows


def finish(name, system, sys_rows, local, local_rows, seed, speakers):
    rng = np.random.default_rng(seed)
    n = len(local)
    events, ev_rows = noise.scatter(n, rng, list(noise.EVENTS), every=(2.0, 6.0),
                                    avoid=[(r["start"], r["end"]) for r in local_rows])
    mic = local + events + noise.room_tone(n, rng)
    if speakers:
        mic = mic + noise.aec_residual(system, rng)
    OUT.mkdir(exist_ok=True)
    sf.write(str(OUT / f"{name}-mic.wav"), np.clip(mic, -1, 1), RATE, subtype="PCM_16")
    sf.write(str(OUT / f"{name}-system.wav"), np.clip(system, -1, 1), RATE, subtype="PCM_16")
    return {"local": local_rows, "system": sys_rows, "noise_events": len(ev_rows), "speakers": speakers}


def main():
    manifest = {}
    plain_zh = [s for s in tts.ZH + tts.ZH_LOCAL_MORE if not re.search("[A-Za-z]", s)]
    # zh2-sp (300 s)
    system, sys_rows = zh_system(300)
    local, rows = np.zeros(300 * RATE), []
    sentences(tts.ZH + tts.ZH_LOCAL_MORE, "Meijia", "loc", local, rows, 15, 60, "L")
    sentences(tts.ZH_LOCAL_MORE[3:], "Meijia", "loc2", local, rows, 140, 170, "L")
    for j, (at, text) in enumerate(zip((95, 120, 200, 230, 280), tts.ZH_BACKCHANNEL)):
        x = tts.load(tts.say(text, "Meijia", f"Meijia-bc-{j}"))
        place(local, x, at, rows, text, "L", -25)
    manifest["zh2-sp"] = finish("zh2-sp", system, sys_rows, local, rows, 51, True)
    # zh2-echo (300 s): the same local speech with the far end at -25 dB (40 ms + reflections), no AEC
    rng = np.random.default_rng(54)
    heard = sf.read(str(OUT / "zh2-sp-system.wav"), dtype="float64")[0]  # the far end as played (PCM16)
    echo = np.zeros_like(heard)
    for delay, gain in ((0.040, 1.0), (0.071, .22), (0.119, .10)):
        shift = round(delay * RATE)
        echo[shift:] += gain * heard[:len(heard) - shift]
    mic = local + noise.room_tone(len(local), rng) + echo * 10 ** (-25 / 20)
    OUT.mkdir(exist_ok=True)
    sf.write(str(OUT / "zh2-echo-mic.wav"), np.clip(mic, -1, 1), RATE, subtype="PCM_16")
    manifest["zh2-echo"] = {"local": rows, "system": sys_rows, "speakers": True, "echo_db": -25}
    # en2zh (240 s): English far end, local English then Mandarin
    a, _ = clip("acquired_alphabet")
    _, a_rows = clip("acquired_alphabet")
    system = rms_to(a[:240 * RATE], -19.5)
    sys_rows = [r for r in a_rows if r["end"] <= 240]
    lex, lex_rows = clip("lex_keyu_jin")
    local, rows = np.zeros(240 * RATE), []
    t = 10.0
    for r in lex_rows:
        if 140 <= r["start"] < 170:
            t = place(local, lex[int(r["start"] * RATE):int(r["end"] * RATE)], t, rows, r["text"], "L")
    for j, (at, text) in enumerate(((110, "好的。"), (125, "对，没问题。"))):
        place(local, tts.load(tts.say(text, "Meijia", f"Meijia-sw-{j}")), at, rows, text, "L", -22)
    sentences(plain_zh, "Meijia", "plain", local, rows, 140, 235, "L")
    manifest["en2zh"] = finish("en2zh", system, sys_rows, local, rows, 52, False)
    # zh2en (240 s): pure-Mandarin far end and local, local switches to English
    system, sys_rows = zh_system(240)
    local, rows = np.zeros(240 * RATE), []
    sentences(plain_zh, "Meijia", "plain", local, rows, 10, 90, "L")
    for j, (at, text, voice) in enumerate(((110, "Okay.", "Samantha"), (125, "Right, sounds good.", "Daniel"))):
        place(local, tts.load(tts.say(text, voice, f"{voice}-sw-{j}")), at, rows, text, "L", -22)
    t = 140.0
    for r in lex_rows:
        if r["start"] == 221.0:
            place(local, lex[int(r["start"] * RATE):int(r["end"] * RATE)], t, rows, r["text"], "L")
    manifest["zh2en"] = finish("zh2en", system, sys_rows, local, rows, 53, False)
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print({k: (len(v["local"]), len(v["system"])) for k, v in manifest.items()})


if __name__ == "__main__":
    main()
