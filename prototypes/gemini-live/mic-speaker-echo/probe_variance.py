"""S3b: how often does one whole-recording request lose the Latin words of a Chinese passage?  (throwaway)

    with_key.sh PYTHON prototypes/gemini-live/mic-speaker-echo/probe_variance.py <label> <system.wav> <kind> <prefix_s,...> [repeats]

One production request (WindowDiarizer, kind = terminal or rolling, diarization on) per leading-silence
variant of the same public/synthetic audio; raw responses are recorded and replayed at $0. Prints, per
request: Latin words kept in the Chinese passage (of the 10 spoken), punctuation marks, Han script
(simplified/traditional), timing anomalies, and what the production word gate drops.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2]), str(HERE)]
import ledger  # noqa: E402
from probe_batch import RecordingClient, S  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import WindowDiarizer  # noqa: E402

NAMES = ["media", "lab", "alan", "turing", "grace", "hopper", "microsoft", "google", "google", "computerphile"]
TRADITIONAL = set("這個問題學院計算機經網絡訓練經會議頻道專訪從頭講為什麼開願術們")
SIMPLIFIED = set("这个问题学院计算机经网络训练会议频道专访从头讲为什么开愿术们")


def measure(words, zh_end_sample: int) -> dict:
    zh = [w for w in words if w.start_sample < zh_end_sample]
    text = "".join(w.text for w in zh)
    latin = [re.sub(r"[^a-z]", "", w.text.lower()) for w in zh if re.search(r"[A-Za-z]", w.text)]
    joined = "".join(latin)
    kept = sum(1 for name in set(NAMES) if name in joined or (name == "computerphile" and "computer" in joined))
    return {"zh_words": len(zh), "latin_tokens_in_zh": len(latin), "distinct_names_kept_of_9": kept,
            "han": sum(1 for ch in text if "一" <= ch <= "鿿"),
            "punctuation": sum(1 for ch in text if unicodedata.category(ch).startswith("P")),
            "script": ("traditional" if sum(ch in TRADITIONAL for ch in text) > sum(ch in SIMPLIFIED for ch in text)
                       else "simplified"),
            "speakers_in_zh": len({w.speaker for w in zh}),
            "zero_length": sum(1 for w in zh if w.end_sample <= w.start_sample)}


def main():
    label, wav, kind = sys.argv[1], sys.argv[2], sys.argv[3]
    prefixes = [float(v) for v in sys.argv[4].split(",")]
    repeats = int(sys.argv[5]) if len(sys.argv) > 5 else 1
    audio = sf.read(wav, dtype="int16")[0]
    rows = []
    for prefix in prefixes:
        for repeat in range(repeats):
            pcm = np.concatenate([np.zeros(int(prefix * S), dtype=np.int16), audio]).tobytes()
            tag = f"{label}-{kind}-p{prefix:g}-r{repeat}"
            client = RecordingClient(tag)
            usage = []
            parsed = WindowDiarizer(client, lambda **row: usage.append(row)).diarize(
                pcm, deadline=time.monotonic() + 240, kind=kind, diarize=True)
            gated = WebRtcWordGate().filter(pcm, parsed.words)
            row = {"variant": tag, "seconds": len(pcm) / 2 / S, "replayed": client.calls[0]["replayed"],
                   "clamped": parsed.clamped, "dropped_by_parser": parsed.dropped,
                   "dropped_by_word_gate": len(parsed.words) - len(gated),
                   **measure(gated, int((prefix + 20.6) * S)),
                   "zh_text": "".join(w.text if not re.search(r"[A-Za-z]", w.text) else f" {w.text} "
                                      for w in gated if w.start_sample < int((prefix + 20.6) * S))}
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "zh_text"}, ensure_ascii=False), flush=True)
    out = ledger.EV / "runs" / f"variance-{label}-{kind}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
    kept = [r["distinct_names_kept_of_9"] for r in rows]
    print(json.dumps({"requests": len(rows), "names_kept_min_median_max": [min(kept), sorted(kept)[len(kept) // 2], max(kept)],
                      "requests_losing_>=1_name": sum(k < 9 for k in kept),
                      "requests_traditional": sum(r["script"] == "traditional" for r in rows),
                      "punctuation_min_max": [min(r["punctuation"] for r in rows), max(r["punctuation"] for r in rows)]}))


main()
