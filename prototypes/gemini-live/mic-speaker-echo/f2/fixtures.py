"""R5-F2 fixtures: every lane the gates need, with the truth of where the local person speaks (throwaway, $0).

    PYTHON prototypes/gemini-live/mic-speaker-echo/f2/fixtures.py          # builds and prints the inventory

Public or generated audio only. Three families:
- `d:*`     R5-D's 37 s cells, rebuilt by R5-D's own builder functions with the local level and the echo level as
            parameters (tab = R5-D's `sys-zhlatin-en.wav`, speech at -17 dBFS).
- `r4:*`    round 4's lanes rebuilt from the committed builders (micfixture, mic-hallucination v1/v2, listen-only,
            noise pilot). Their provider answers were deleted; the audio is what the audio-only gate needs.
- `f2:*`    new 37 s cells on R5-D's tab: varied short replies, short replies beside a long turn, room noise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
GL = ROOT / "prototypes/gemini-live"
sys.path[:0] = [str(HERE), str(HERE.parent), str(GL / "mic-hallucination")]
import build as d_build  # noqa: E402  (R5-D)
import ledger  # noqa: E402
import noise  # noqa: E402  (round 4)
import tts  # noqa: E402  (round 4)

RATE = 16000
FIX = ledger.EV / "fixtures"
D_FIX = ledger.D_EV / "fixtures"
MH = GL / "mic-hallucination" / "out"
QMIC = GL / "micfixture" / "out"
TOTAL = 37.0
TAB_DBFS = -17.0
n = d_build.n

SHORT = [(5.0, 96.0, 97.1), (20.3, 96.0, 97.1), (35.2, 96.0, 97.1)]      # R5-D: "Can you elaborate on that?"
LONG = [(9.0, 140.0, 146.0), (34.3, 221.0, 223.6)]                        # R5-D: 6 s under the tab, 2.6 s after it
ZH_SHORT = [(5.0, "好的，没问题。"), (20.3, "好的，没问题。"), (35.0, "好的，没问题。")]
ZH_LONG = [(9.0, "我觉得这个方案可以，但是我们需要先把接口的延迟测一下。"), (33.9, "那我们下周五之前再开会讨论一下。")]
TEXT = {(96.0, 97.1): "Can you elaborate on that?",
        (140.0, 146.0): "So there is some element that we have in the West of freedom of the individual so that a little bit of the",
        (221.0, 223.6): "Well, let's stay on the big picture"}       # reference turn text up to the cut (approximate)
# f2 cells. Double-talk first: every phrase but the last is said while the tab is talking.
VARIED_EN = [(3.0, "Samantha", "Yeah."), (6.5, "Daniel", "Okay, sounds good."), (10.5, "lex", (96.0, 97.1)),
             (14.0, "Samantha", "I agree with that."), (23.5, "Daniel", "Could you say that again?"),
             (27.5, "Samantha", "Right."), (31.0, "Daniel", "Let me check and get back to you."),
             (35.6, "Samantha", "Thanks everyone.")]
VARIED_ZH = [(3.0, "好的。"), (6.5, "对，没问题。"), (10.5, "我同意这个方案。"), (14.0, "可以。"),
             (23.5, "你能再说一遍吗？"), (27.5, "明白。"), (31.0, "我回去确认一下再回复你。"), (35.6, "谢谢大家。")]
MIXED = [(4.0, "lex", (140.0, 146.0)), (12.5, "lex", (96.0, 97.1)), (24.0, "Samantha", "Okay, sounds good."),
         (29.0, "lex", (96.0, 97.1)), (35.5, "Samantha", "Yeah.")]
DOUBLE_LONG = [(3.0, "lex", (140.0, 146.0)), (23.0, "lex", (140.0, 146.0))]   # two 6 s turns, both under the tab


def system() -> np.ndarray:
    return d_build.read(D_FIX / "sys-zhlatin-en.wav")


def floor() -> np.ndarray:
    return np.random.default_rng(72).normal(0, 10 ** (-63 / 20), n(TOTAL))


def _say(text: str, voice: str) -> np.ndarray:
    cache = FIX / "tts"
    cache.mkdir(parents=True, exist_ok=True)
    import hashlib
    path = cache / f"{voice}-{hashlib.sha1(text.encode()).hexdigest()[:10]}.wav"
    if not path.is_file():
        sf.write(str(path), d_build.say(text, voice, 185), RATE, subtype="DOUBLE")
    return sf.read(str(path), dtype="float64")[0]


def local(turns, level_dbfs: float) -> tuple[np.ndarray, list[dict]]:
    """Turns: (at, "lex", (lo, hi)) public Lex Fridman cut; (at, voice, text) macOS speech; R5-D tuples accepted."""
    src = d_build.read(d_build.B5 / "lex_keyu_jin" / "audio.wav")
    out, truth = np.zeros(n(TOTAL)), []
    for turn in turns:
        if len(turn) == 3 and isinstance(turn[1], float):
            turn = (turn[0], "lex", (turn[1], turn[2]))
        if len(turn) == 2:
            turn = (turn[0], "Meijia", turn[1])
        at, voice, what = turn
        cut = d_build.fade(src[n(what[0]):n(what[1])]) if voice == "lex" else d_build.fade(_say(what, voice))
        cut = d_build.speech_level(cut, level_dbfs)[:len(out) - n(at)]
        out[n(at):n(at) + len(cut)] += cut
        truth.append({"start": at, "end": at + len(cut) / RATE, "text": TEXT[what] if voice == "lex" else what,
                      "voice": voice})
    return out, truth


def cell(turns, *, echo_db: float | None, level_dbfs: float = -27.0, events_seed: int | None = None):
    """(mic float lane, truth rows) of one 37 s cell on R5-D's tab."""
    tab = system()
    mic = floor()
    if echo_db is not None:
        mic = mic + d_build.echo_of(tab, echo_db)
    speech, truth = local(turns, level_dbfs)
    if events_seed is not None:
        rng = np.random.default_rng(events_seed)
        events, _ = noise.scatter(n(TOTAL), rng, list(noise.EVENTS), every=(1.0, 3.0),
                                  avoid=[(r["start"], r["end"]) for r in truth])
        mic = mic + events + noise.room_tone(n(TOTAL), rng)
    return np.clip(mic + speech, -1, 1), truth


KINDS = {"short": SHORT, "long": LONG, "zhshort": ZH_SHORT, "zhlong": ZH_LONG, "listen": [],
         "varied-en": VARIED_EN, "varied-zh": VARIED_ZH, "mixed": MIXED, "dlong": DOUBLE_LONG}


def pcm(x: np.ndarray) -> np.ndarray:
    """The int16 samples a PCM_16 wav of this float lane holds."""
    return np.clip(np.rint(np.clip(x, -1, 1) * 32767), -32768, 32767).astype(np.int16)


def write(name: str, x: np.ndarray, truth: list[dict], *, system_wav: Path, **meta) -> Path:
    FIX.mkdir(parents=True, exist_ok=True)
    path = FIX / f"{name}.wav"
    sf.write(str(path), np.clip(x, -1, 1), RATE, subtype="PCM_16")
    (FIX / f"{name}.json").write_text(json.dumps({"system_wav": str(system_wav), "truth": truth, **meta},
                                                 ensure_ascii=False, indent=1) + "\n")
    return path


def d_cell(kind: str, echo_db: float | None, level_dbfs: float = -27.0, events_seed: int | None = None) -> Path:
    """Write (once) a 37 s cell and return its wav path."""
    echo = "noecho" if echo_db is None else f"e{-int(echo_db)}"
    name = f"mic-{kind}-{echo}-L{-int(level_dbfs)}" + (f"-n{events_seed}" if events_seed is not None else "")
    path = FIX / f"{name}.wav"
    if not path.is_file():
        x, truth = cell(KINDS[kind], echo_db=echo_db, level_dbfs=level_dbfs, events_seed=events_seed)
        write(name, x, truth, system_wav=D_FIX / "sys-zhlatin-en.wav", kind=kind, echo_db=echo_db,
              local_dbfs=level_dbfs, below_tab_db=level_dbfs - TAB_DBFS, events_seed=events_seed)
    return path


# ---- round 4 lanes (audio only) -------------------------------------------------------------------------------

def r4_listen_only() -> dict[str, tuple[Path, Path, list]]:
    """Round 4 `listen_only.py`, audio part: events + room tone + echo-cancellation residue, no local speech."""
    sys.path[:0] = [str(GL / "mic-hallucination")]
    import build2
    out = {}
    for case, system_fn in (("A", build2.en_system), ("B", build2.zh_system)):
        path = FIX / f"r4-{case}-listen-mic.wav"
        if not path.is_file():
            rng = np.random.default_rng({"A": 31, "B": 32}[case])
            tab, _ = system_fn()
            events, _ = noise.scatter(build2.N, rng, list(noise.EVENTS), every=(1.5, 5.0))
            mic = events + noise.room_tone(build2.N, rng) + noise.aec_residual(tab, rng)
            FIX.mkdir(parents=True, exist_ok=True)
            sf.write(str(path), np.clip(mic, -1, 1), RATE, subtype="PCM_16")
        out[f"r4:{case}-listen-sp"] = (path, MH / "fixture2" / f"{case}-system.wav", [])
    return out


def r4_lanes() -> dict[str, tuple[Path, Path, list]]:
    """name -> (mic wav, system wav, local-speech truth rows)."""
    lanes = dict(r4_listen_only())
    for fixture, cases in (("fixture2", ("A", "B")), ("fixture", ("en", "zh"))):
        ref = json.loads((MH / fixture / "reference.json").read_text())
        for name, v in ref["variants"].items():
            case = v.get("case", name.split("-")[0])
            truth = [dict(r, backchannel=False) for r in ref[case]["local_turns"]] + \
                    [dict(r, backchannel=True) for r in ref[case]["backchannels"]]
            lanes[f"r4:{name}"] = (MH / fixture / v["microphone"], MH / fixture / v["system"], truth)
    ref = json.loads((QMIC / "reference.json").read_text())
    for name, v in ref["variants"].items():
        lanes[f"r4:qmic-{name}"] = (QMIC / v["microphone"], QMIC / v["system"],
                                    [dict(r, backchannel=False) for r in ref["local_turns"]])
    return lanes


def r4_pilot(seeds=(1, 2, 3, 4)) -> dict[str, tuple[np.ndarray, np.ndarray, list]]:
    """Round 4 `pilot.py` 30 s noise-only windows, with the tab lane each residue came from."""
    N = 30 * RATE
    bench = d_build.B5

    def speech(clip, offset_s):
        x, sr = sf.read(str(bench / clip / "audio.wav"), dtype="float32")
        return x[int(offset_s * sr):int(offset_s * sr) + N].astype(np.float64)

    def zh_stream(voice):
        parts = [x for _, x in tts.zh_sentences(voice)]
        return np.resize(np.concatenate([np.concatenate([p, np.zeros(int(.4 * RATE))]) for p in parts]), N)
    out = {}
    for kind in ("room", "fan", "breath", "keys", "cough", "throat", "creak", "mix", "distant_en", "distant_zh",
                 "aec_en", "aec_zh"):
        for seed in seeds:
            rng = np.random.default_rng(seed)
            base, tab = noise.room_tone(N, rng), np.zeros(N)
            if kind == "room":
                x = base
            elif kind == "fan":
                x = base + noise.fan(N, rng)
            elif kind in ("breath", "keys", "cough", "throat", "creak"):
                x = base + noise.scatter(N, rng, [kind] + (["smack"] if kind == "breath" else []))[0]
            elif kind == "mix":
                x = base + noise.scatter(N, rng, list(noise.EVENTS))[0]
            elif kind == "distant_en":
                x = base + noise.distant(speech("acquired_nfl", 60 + 30 * seed % 200), rng)
            elif kind == "distant_zh":
                x = base + noise.distant(zh_stream("Meijia"), rng)
            elif kind == "aec_en":
                tab = speech("acquired_alphabet", 30 + 30 * seed % 200)
                x = base + noise.aec_residual(tab, rng)
            else:
                tab = zh_stream("Tingting")
                x = base + noise.aec_residual(tab, rng)
            out[f"r4:pilot-{kind}-{seed}"] = (pcm(x), pcm(tab), [])
    return out


def main():
    inventory = {}
    for kind in ("short", "zhshort"):       # the rebuilt cells against R5-D's own files
        mine = sf.read(str(d_cell(kind, -40.0)), dtype="int16")[0]
        theirs = sf.read(str(D_FIX / f"mic-{kind}-aec40.wav"), dtype="int16")[0]
        diff = np.abs(mine.astype(int) - theirs.astype(int))   # R5-D echoed the tab before the wav clipped its peaks
        inventory[f"rebuild_vs_r5d:{kind}-aec40"] = {"samples_differing": int((diff > 0).sum()), "of": len(diff),
                                                     "max_lsb": int(diff.max())}
    for name, (mic, tab, truth) in r4_lanes().items():
        inventory[name] = {"mic": mic.name, "seconds": round(sf.info(str(mic)).duration, 1), "local_rows": len(truth)}
    inventory["r4:pilot"] = len(r4_pilot())
    print(json.dumps(inventory, indent=1))


if __name__ == "__main__":
    main()
