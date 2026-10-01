"""R5-F1 T4 (PAID once, <= $0.08 planned, cap $0.10): provider answers for the synthetic Mandarin lane.

    prototypes/gemini-live/mic-speaker-echo/with_key.sh ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/record_zh.py

1. The production instant-word source (`GeminiLiveWordSource`, model and config as shipped) on the lane,
   paced in real time, 0.5 s frames; every event is recorded (text, turn start, sent position, final).
2. The production batch request (`WindowDiarizer.diarize(kind="rolling")`) for a 30 s window ending at
   every 15 s tick. The product sends up to 90 s of context per tick; 30 s keeps this recording under
   the cap and still gives one independent provider answer per commit frontier.
Synthetic speech only. Re-running replays the recorded answers ($0). R5-D's ledger method
(known + 1.25 x planned <= cap before every paid action), pointed at this prototype's evidence folder.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
F1EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1"
sys.path[:0] = [str(ROOT), str(HERE.parent)]
import ledger  # noqa: E402

ledger.EV, ledger.LEDGER, ledger.CAP = F1EV, F1EV / "spend.jsonl", 0.10     # before probe_batch reads them
import probe_batch  # noqa: E402
import moss_transcribe_diarize.app.phase2_web_cli as cli  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_words import GeminiLiveWordSource  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import WindowDiarizer  # noqa: E402

S, FRAME, STRIDE, WINDOW = 16000, 8000, 15, 30
assert probe_batch.RAW == F1EV / "provider-responses"
W3 = probe_batch.RAW / "zh-long-w3.json"
WORDS = F1EV / "runs" / "zh-long-windows.json"


async def record_w3(pcm: bytes) -> dict:
    events, usage = [], []
    source = GeminiLiveWordSource(cli._gemini_client(os.environ.get("GEMINI_API_KEY")), lambda **row: usage.append(row))
    source.bind(lambda text, start, end, final: events.append([text, start, end, final]))
    started = time.monotonic()
    total = len(pcm) // 2
    for at in range(0, total - FRAME + 1, FRAME):
        source.push_audio(at, pcm[at * 2:(at + FRAME) * 2])
        delay = started + (at + FRAME) / S - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
    await source.finish()
    seconds = total / S
    ledger.add("zh-long w3 system", seconds * ledger.LIVE_PER_S, seconds=seconds, basis="list_price_plus_output_estimate")
    errors = [row for row in usage if row.get("error_code")]
    out = {"system": events, "microphone": []}
    W3.parent.mkdir(parents=True, exist_ok=True)
    W3.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({"w3_events": len(events), "finals": sum(1 for e in events if e[3]), "seconds": seconds,
                      "errors": [row.get("error_code") for row in errors]}))
    return out


def record_windows(pcm: bytes) -> list[dict]:
    usage: list = []
    client = probe_batch.RecordingClient("zh-long")
    diarizer = WindowDiarizer(client, lambda **row: usage.append(row))
    total = len(pcm) // 2
    out = []
    for tick in range(STRIDE, total // S + 1, STRIDE):
        start = max(0, tick - WINDOW)
        parsed = diarizer.diarize(pcm[start * S * 2:tick * S * 2], deadline=time.monotonic() + 120, kind="rolling", diarize=True)
        out.append({"start_s": start, "end_s": tick, "clamped": parsed.clamped, "dropped": parsed.dropped,
                    "words": [[w.text, w.speaker, w.start_sample + start * S, w.end_sample + start * S] for w in parsed.words]})
        print(json.dumps({"window": [start, tick], "words": len(parsed.words), "replayed": client.calls[-1]["replayed"]}))
    WORDS.parent.mkdir(parents=True, exist_ok=True)
    WORDS.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def main():
    pcm = sf.read(str(F1EV / "fixtures/zh-long.wav"), dtype="int16")[0].tobytes()
    seconds = len(pcm) / 2 / S
    ticks = list(range(STRIDE, int(seconds) + 1, STRIDE))
    batch_seconds = sum(tick - max(0, tick - WINDOW) for tick in ticks)
    if not W3.is_file():
        ledger.check(seconds * ledger.LIVE_PER_S + batch_seconds * ledger.BATCH_PER_S, "zh-long w3 + windows (whole plan)")
        asyncio.run(record_w3(pcm))
    record_windows(pcm)
    print(json.dumps({"total_usd": round(ledger.total(), 4), "cap": ledger.CAP}))


main()
