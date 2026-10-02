"""C3 ($0): can a voice match against earlier local speech tell a 1-2 word reply from a noise event or echo?

    PYTHON f2/c3_voice.py
Production encoder (pinned WeSpeaker ONNX), one embedding per short stretch, cosine to an anchor made from a long
turn of the same local voice. Reports the cosine of real short replies, of the round-4 noise events, of
echo-cancellation residue and of plain echo, against the same anchors. Writes runs/c3-voice.json.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(HERE), str(ROOT / "prototypes/gemini-live/mic-hallucination")]
import fixtures  # noqa: E402
import ledger  # noqa: E402
import noise  # noqa: E402

MANIFEST = Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"
RATE = 16000


def encoder():
    from moss_transcribe_diarize.app.live_provider_bundle import LiveProviderBundleConfig, _identity_encoder
    return _identity_encoder(LiveProviderBundleConfig.from_manifest(MANIFEST), interval_workers=4)


def embed(enc, x: np.ndarray, spans) -> list[np.ndarray]:
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        sf.write(tmp.name, np.clip(x, -1, 1), RATE, subtype="PCM_16")
        out = []
        for start, end in spans:
            try:
                v = np.asarray(enc.embed(tmp.name, [(max(0.0, start), end)]), dtype=float)
                out.append(v / (np.linalg.norm(v) or 1))
            except Exception as error:      # the encoder refuses very short spans
                out.append(None)
        return out


def cos(a, b):
    return None if a is None or b is None else round(float(a @ b), 3)


def main():
    enc = encoder()
    tab = fixtures.system()
    anchors = {}
    for voice, turn in (("lex", (0.5, "lex", (140.0, 146.0))), ("Samantha", (0.5, "Samantha", "I think the plan is fine, but we should measure the latency of the interface before we decide anything.")),
                        ("Meijia", (0.5, "Meijia", "我觉得这个方案可以，但是我们需要先把接口的延迟测一下。"))):
        x, truth = fixtures.local([turn], -27.0) if voice != "lex" else fixtures.local([turn], -27.0)
        anchors[voice] = embed(enc, x + fixtures.floor(), [(truth[0]["start"], truth[0]["end"])])[0]
    rows = []
    # real short replies, alone and under the tab's echo at -40 dB (double-talk)
    for kind in ("varied-en", "varied-zh", "short", "zhshort"):
        for echo in (None, -40.0):
            x, truth = fixtures.cell(fixtures.KINDS[kind], echo_db=echo, level_dbfs=-27.0)
            vectors = embed(enc, x, [(p["start"], p["end"]) for p in truth])
            for p, v in zip(truth, vectors):
                voice = p["voice"]
                rows.append({"class": "local reply", "text": p["text"], "seconds": round(p["end"] - p["start"], 2),
                             "echo_db": echo, "voice": voice, "cos_own_anchor": cos(v, anchors[voice]),
                             "cos_other_anchors": [cos(v, a) for k, a in anchors.items() if k != voice]})
    # noise events and residue: round-4 pilot windows, one embedding per event
    for name, (mic, _tab, _t) in fixtures.r4_pilot(seeds=(1, 2)).items():
        kind = name.split("-")[1]
        if kind not in ("breath", "keys", "cough", "throat", "creak", "aec_en", "aec_zh", "distant_en"):
            continue
        seed = int(name.split("-")[-1])
        rng = np.random.default_rng(seed)
        noise.room_tone(30 * RATE, rng)
        if kind in ("breath", "keys", "cough", "throat", "creak"):
            _, events = noise.scatter(30 * RATE, rng, [kind] + (["smack"] if kind == "breath" else []))
            spans = [(e["start_s"], max(e["end_s"], e["start_s"] + .5)) for e in events if e["kind"] != "smack"][:6]
        else:
            spans = [(t, t + 1.0) for t in (3, 8, 13, 18, 23)]
        for v in embed(enc, mic.astype(np.float64) / 32768, spans):
            rows.append({"class": f"noise:{kind}", "cos_to_anchors": {k: cos(v, a) for k, a in anchors.items()}})
    # plain echo of the tab at -25 dB, 1 s spans
    x, _ = fixtures.cell([], echo_db=-25.0)
    for v in embed(enc, x, [(t, t + 1.0) for t in (2, 6, 10, 14, 23, 27, 31)]):
        rows.append({"class": "echo -25 dB", "cos_to_anchors": {k: cos(v, a) for k, a in anchors.items()}})
    (ledger.EV / "runs" / "c3-voice.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    local = [r for r in rows if r["class"] == "local reply" and r["cos_own_anchor"] is not None]
    def q(values):
        values = sorted(v for v in values if v is not None)
        return (len(values), values[0], values[len(values) // 2], values[-1]) if values else None
    for label, pick in (("replies under 0.6 s", lambda r: r["seconds"] < .6), ("replies 0.6-1.2 s", lambda r: .6 <= r["seconds"] < 1.2),
                        ("replies over 1.2 s", lambda r: r["seconds"] >= 1.2)):
        mine = [r for r in local if pick(r)]
        print(f"{label:22s} cos to own voice anchor (n, min, median, max): {q([r['cos_own_anchor'] for r in mine])}   "
              f"to another voice's anchor: {q([c for r in mine for c in r['cos_other_anchors']])}")
    for kind in sorted({r["class"] for r in rows if r["class"] != "local reply"}):
        mine = [r for r in rows if r["class"] == kind]
        print(f"{kind:22s} cos to any local anchor (n, min, median, max): {q([c for r in mine for c in r['cos_to_anchors'].values()])}")
    print("unembeddable spans:", sum(1 for r in rows if r.get("cos_own_anchor", 0) is None))


main()
