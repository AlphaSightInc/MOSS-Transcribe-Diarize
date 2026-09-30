"""Build the 300 s two-lane noisy-listener fixture (public Q-MIC speech + local TTS + generated noise)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import noise  # noqa: E402
import tts  # noqa: E402

RATE = 16000
N = 300 * RATE
QMIC = HERE.parent / "micfixture" / "out"  # built by micfixture/build.py (byte-identical to R2-WP2)
OUT = HERE / "out" / "fixture"
BACKCHANNEL_AT = [(104, -20), (117, -30), (131, -20), (179, -30), (193, -20),
                  (208, -30), (244, -20), (259, -30), (275, -20), (290, -30)]


def rms_to(x, dbfs):
    return x * 10 ** (dbfs / 20) / (np.sqrt(np.mean(x ** 2)) or 1)


def place(lane, x, at_s):
    s = int(at_s * RATE)
    x = x[:N - s]
    lane[s:s + len(x)] += x
    return at_s + len(x) / RATE


def fill_turns(turns, pool, voices):
    """Fill each (start, end, speaker) turn with sequential sentences in that speaker's voice."""
    lane = np.zeros(N)
    rows = []
    k = 0
    for start, end, speaker in turns:
        t = start + .2
        while k < len(pool[speaker]):
            text, x = pool[speaker][k % len(pool[speaker])]
            if t + len(x) / RATE > end - .1:
                break
            stop = place(lane, rms_to(x, -20), t)
            rows.append({"start": t, "end": stop, "speaker": speaker, "text": text})
            t = stop + .35
            k += 1
    return lane, rows


def zh_system():
    voices = {"A": tts.utterances(tts.ZH_SYSTEM, "Tingting", "sys"),
              "B": tts.utterances(tts.ZH_SYSTEM[::-1], "Eddy (Chinese (China mainland))", "sysb")}
    lane = np.zeros(N)
    rows = []
    t, i = .5, 0
    rng = np.random.default_rng(7)
    while True:
        speaker = "AB"[(i // 2) % 2]
        text, x = voices[speaker][i % len(tts.ZH_SYSTEM)]
        if t + len(x) / RATE > 299.5:
            break
        stop = place(lane, rms_to(x, -19.5), t)
        rows.append({"start": t, "end": stop, "speaker": speaker, "text": text})
        t = stop + rng.uniform(.25, .8)
        i += 1
    return lane, rows


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ref = json.loads((QMIC / "reference.json").read_text())
    en_system = sf.read(str(QMIC / "system.wav"), dtype="float64")[0]
    en_local = sf.read(str(QMIC / "headphones-mic.wav"), dtype="float64")[0]
    turns = [(r["start"], r["end"], r["speaker"]) for r in ref["local_turns"]]
    zh_local_pool = {"C": tts.utterances(tts.ZH + tts.ZH_LOCAL_MORE, "Flo (Chinese (China mainland))", "loc"),
                     "D": tts.utterances((tts.ZH + tts.ZH_LOCAL_MORE)[::-1], "Reed (Chinese (China mainland))", "locd")}
    zh_local, zh_local_rows = fill_turns(turns, zh_local_pool, None)
    zh_sys, zh_sys_rows = zh_system()
    manifest = {"duration_s": 300, "sample_rate": RATE, "variants": {}}
    for lang in ("en", "zh"):
        rng = np.random.default_rng({"en": 11, "zh": 12}[lang])
        local = en_local.copy() if lang == "en" else zh_local
        local_rows = ([dict(r) for r in ref["local_turns"]] if lang == "en" else zh_local_rows)
        texts = tts.EN_BACKCHANNEL if lang == "en" else tts.ZH_BACKCHANNEL
        voice = ["Samantha", "Daniel"] if lang == "en" else ["Flo (Chinese (China mainland))", "Reed (Chinese (China mainland))"]
        backs = []
        for j, ((at, level), text) in enumerate(zip(BACKCHANNEL_AT, texts)):
            x = tts.load(tts.say(text, voice[j % 2], f"{voice[j % 2]}-bc-{lang}-{j:02d}"))
            stop = place(local, rms_to(x, level), at)
            backs.append({"start": at, "end": stop, "speaker": "CD"[j % 2], "text": text, "level_dbfs": level})
        speech = [(r["start"], r["end"]) for r in local_rows + backs]
        events, event_rows = noise.scatter(N, rng, list(noise.EVENTS), every=(1.5, 5.0), avoid=speech)
        floor = noise.room_tone(N, rng)
        system = en_system if lang == "en" else zh_sys
        system_rows = ([r for r in ref["system_turns"]] if lang == "en" else zh_sys_rows)
        sf.write(str(OUT / f"{lang}-system.wav"), np.clip(system, -1, 1), RATE, subtype="PCM_16")
        headphones = local + events + floor
        speakers = headphones + noise.aec_residual(system, rng)
        for route, mic in (("hp", headphones), ("sp", speakers)):
            name = f"{lang}-{route}"
            sf.write(str(OUT / f"{name}-mic.wav"), np.clip(mic, -1, 1), RATE, subtype="PCM_16")
            manifest["variants"][name] = {"system": f"{lang}-system.wav", "microphone": f"{name}-mic.wav",
                                          "aec_residual_dbfs": None if route == "hp" else -38}
        manifest[lang] = {"local_turns": local_rows, "backchannels": backs, "system_turns": system_rows,
                          "noise_events": event_rows}
    (OUT / "reference.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(json.dumps({k: {"local": len(manifest[k]["local_turns"]), "back": len(manifest[k]["backchannels"]),
                          "events": len(manifest[k]["noise_events"]), "system": len(manifest[k]["system_turns"])}
                      for k in ("en", "zh")}))


if __name__ == "__main__":
    main()
