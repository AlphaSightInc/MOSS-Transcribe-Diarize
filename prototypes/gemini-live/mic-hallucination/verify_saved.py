"""D2: the saved-lane rule through the production MicrophoneWordGate, cached words only ($0)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "common")]
import chain  # noqa: E402
from chain import RATE, gw  # noqa: E402
from gemini_common import diarize_window, read_wav  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate  # noqa: E402

LANES = {"fixture": ["en-hp", "en-sp"], "fixture2": ["A-hp", "A-sp", "B-hp", "B-sp"]}


def longest_attributed_run(words) -> float:
    """Longest same-label span joined across gaps <= 0.6 s (attributed_embedding_intervals' merge)."""
    best = 0.0
    for label in {w.speaker for w in words}:
        merged = []
        for w in sorted((w for w in words if w.speaker == label and w.end_sample > w.start_sample),
                        key=lambda w: w.start_sample):
            if merged and w.start_sample - merged[-1][1] <= .6 * RATE:
                merged[-1][1] = max(merged[-1][1], w.end_sample)
            else:
                merged.append([w.start_sample, w.end_sample])
        best = max([best] + [(b - a) / RATE for a, b in merged])
    return round(best, 2)


def saved(v, gate, sysw):
    mic = v.mic.tobytes()
    words = WebRtcWordGate().filter(mic, gw(v.gemini["whole_mic"]))
    return gate.filter_terminal(mic, words, sysw, system_pcm16=v.system.tobytes())


def main():
    listen_only = "--listen-only" in sys.argv
    path = HERE / "out" / "verify-saved.json"
    out = [r for r in json.loads(path.read_text()) if r["has_local_speech"]] if listen_only else []
    for fixture, names in ({} if listen_only else LANES).items():
        chain.FIX = HERE / "out" / fixture
        for name in names:
            v = chain.Variant(name)
            gate, sysw = v.gate()
            live = v.rolling(gate)            # production live gate: sets local_speech_seen
            with_live = saved(v, gate, sysw)
            fresh, sysw2 = v.gate()           # saved pass alone, no live memory
            alone = saved(v, fresh, sysw2)
            row = {"lane": name, "has_local_speech": True,
                   "live_anchor_seen": gate.local_speech_seen,
                   "saved": v.score(with_live), "saved_without_live_memory": v.score(alone),
                   "withheld": gate.lane_withheld_words, "withheld_without_live_memory": fresh.lane_withheld_words,
                   "longest_saved_run_s": longest_attributed_run(alone)}
            for k in ("saved", "saved_without_live_memory"):
                s = row[k]
                row[k] = {"nonbc": s["retained"] - s["backchannel_units_kept"],
                          "nonbc_ref": s["reference"] - s["backchannel_units"],
                          "bc": s["backchannel_units_kept"], "bc_ref": s["backchannel_units"], "stray": s["stray_words"]}
            out.append(row)
            print(json.dumps(row), flush=True)
    chain.FIX = HERE / "out" / "fixture2"
    for case in ("A", "B"):
        v = chain.Variant(f"{case}-sp")
        v.mic = read_wav(chain.FIX / f"{case}-listen-mic.wav")
        r = diarize_window(v.mic)
        assert r.cached, "listen-only terminal response must be cached ($0)"
        v.gemini = dict(v.gemini, whole_mic=[{"text": w.text, "speaker": w.speaker, "start": w.start,
                                              "end": w.end} for w in r.words])
        gate, sysw = v.gate()
        mic = v.mic.tobytes()
        raw = gw(v.gemini["whole_mic"])
        gated = WebRtcWordGate().filter(mic, raw)
        kept = gate.filter_terminal(mic, gated, sysw, system_pcm16=v.system.tobytes())
        row = {"lane": f"{case}-listen-sp", "has_local_speech": False, "raw_words": len(raw),
               "survived_echo_gates": gate.lane_withheld_words + len(kept), "saved_words": len(kept),
               "withheld": gate.lane_withheld_words,
               "longest_run_after_gates_s": None}
        fresh, _ = v.gate()
        fresh.local_speech_seen = True  # what the old chain kept, for the margin
        survivors = fresh.filter_terminal(mic, gated, sysw, system_pcm16=v.system.tobytes())
        row["longest_run_after_gates_s"] = longest_attributed_run(survivors)
        out.append(row)
        print(json.dumps(row), flush=True)
    path.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
