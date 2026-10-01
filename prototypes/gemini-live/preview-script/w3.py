"""Stream one mic WAV through the production W3 preview source at 1.0x; ledger lane r4c-preview-script."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE.parent / "common")]
from gemini_common import client, ledger  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_words import GeminiLiveWordSource  # noqa: E402

RATE = 16000


def main():
    out, wav = Path(sys.argv[1]), sys.argv[2]
    pcm = sf.read(wav, dtype="int16")[0]
    events, usage = [], {"audio_s": 0.0, "errors": []}

    def report(**row):
        usage["audio_s"] += float(row.get("audio_seconds_sent") or 0)
        if row.get("error_code"):
            usage["errors"].append(row["error_code"])

    source = GeminiLiveWordSource(client(), report)
    source.bind(lambda text, s, e, final: events.append(
        {"text": text, "start_s": s / RATE, "end_s": e / RATE, "final": final}))
    t0, chunk = time.monotonic(), RATE // 10
    for i in range(0, len(pcm), chunk):
        source.push_audio(i, pcm[i:i + chunk].tobytes())
        delay = t0 + (i + chunk) / RATE - time.monotonic()
        if delay > 0:
            time.sleep(delay)
    asyncio.run(source.finish())
    ledger("r4c-preview-script", {"kind": "w3_stream", "label": out.stem, "audio_s": usage["audio_s"],
                                  "cost_usd": usage["audio_s"] * .005 / 60, "cost_basis": "list_price_estimate",
                                  "errors": usage["errors"]})
    out.write_text(json.dumps({"wav": wav, "events": events}, ensure_ascii=False, indent=1))
    print(len(events), "events")


if __name__ == "__main__":
    main()
