"""Stream a mic WAV through the production W3 preview source (GeminiLiveWordSource), paced 1.0x."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE.parent / "common")]
from gemini_common import client, ledger  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_words import GeminiLiveWordSource  # noqa: E402

RATE = 16000
LANE = "r4c-mic-halluc"


def run(pcm: np.ndarray, label: str) -> list[dict]:
    events: list[dict] = []
    usage = {"audio_s": 0.0, "errors": []}

    def report(**row):
        usage["audio_s"] += float(row.get("audio_seconds_sent") or 0)
        if row.get("error_code"):
            usage["errors"].append(row["error_code"])

    source = GeminiLiveWordSource(client(), report)
    source.bind(lambda text, start, end, final: events.append(
        {"text": text, "start_s": start / RATE, "end_s": end / RATE, "final": final,
         "wall": time.monotonic()}))
    chunk = RATE // 10
    t0 = time.monotonic()
    for i in range(0, len(pcm), chunk):
        source.push_audio(i, pcm[i:i + chunk].tobytes())
        delay = t0 + (i + chunk) / RATE - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    asyncio.run(source.finish())
    cost = usage["audio_s"] * 0.005 / 60
    ledger(LANE, {"kind": "w3_stream", "model": "gemini-3.5-transcribe-live", "label": label,
                  "audio_s": usage["audio_s"], "cost_usd": cost, "cost_basis": "list_price_estimate",
                  "errors": usage["errors"]})
    return events


def main() -> None:
    out = Path(sys.argv[1])
    parts = sys.argv[2:]
    pcm = np.concatenate([sf.read(p, dtype="int16")[0] for p in parts])
    events = run(pcm, out.stem)
    out.write_text(json.dumps({"parts": parts, "events": events}, ensure_ascii=False, indent=1))
    for e in events:
        if e["final"]:
            print(round(e["start_s"], 1), round(e["end_s"], 1), repr(e["text"]))
    print(len(events), "events", sum(e["final"] for e in events), "final")


if __name__ == "__main__":
    main()
