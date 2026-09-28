"""Paced public-audio forced reconnect test for WordStream replay=2 or 5 seconds."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402
from gemini_common import ledger, read_wav  # noqa: E402
from score import score  # noqa: E402
from proto_words import live_config, mono  # noqa: E402
from words_stream import WordStream  # noqa: E402


async def run(args):
    clip = next(c for c in clips() if c.clip_id == args.clip)
    pcm = read_wav(clip.audio)
    cfg = live_config("w3", 0, "high", 500, None, None)
    stream = WordStream("gemini-3.5-transcribe-live", cfg, replay_s=args.replay)
    await stream.start()
    t0 = time.monotonic()
    updates = []

    async def collect():
        async for text, start, end, final in stream.updates():
            updates.append({"text": text, "start": start, "end": end,
                            "final": final, "wall_s": time.monotonic() - t0})

    collector = asyncio.create_task(collect())
    forced = False
    for i in range(0, len(pcm), 1600):
        await asyncio.sleep(max(0, t0 + i / 16000 - time.monotonic()))
        if args.at > 0 and not forced and i / 16000 >= args.at:
            await stream.reconnect()
            forced = True
        await stream.push(pcm[i:i + 1600].tobytes())
    await stream.finish(drain_s=args.drain)
    await collector
    final = [u for u in updates if u["final"]]
    hyp = [{"start": u["start"], "end": max(u["end"], u["start"] + 0.001),
            "speaker": "one", "text": u["text"]} for u in final]
    holes = []
    reconnects = []
    for r in stream.reconnects:
        at_wall = r["started_monotonic"] - t0
        before = [u["wall_s"] for u in updates if u["wall_s"] <= at_wall]
        after = [u["wall_s"] for u in updates if u["wall_s"] > at_wall]
        hole = min(after) - max(before) if before and after else None
        holes.append(hole)
        reconnects.append({**{k: v for k, v in r.items() if not k.endswith("monotonic")},
                           "started_wall_s": at_wall, "connection_pause_s": r["finished_monotonic"] - r["started_monotonic"],
                           "on_screen_no_update_hole_s": hole})
    result = {"clip": clip.clip_id, "duration_s": len(pcm) / 16000, "forced_reconnect_s": args.at,
              "replay_s": args.replay, "sent_s": stream._audio_s, "reconnects": reconnects,
              "gap_records": [g.__dict__ for g in stream.gaps],
              "suppressed_exact_duplicates": stream.suppressed_duplicates,
              "on_screen_no_update_hole_s": holes, "updates": len(updates), "final_updates": len(final),
              "score": score(mono(clip.reference_segments()), hyp),
              "usage_observations": stream.usage, "events": stream.events,
              "updates_full": updates, "hypothesis": hyp}
    ledger("P52", {"kind": "live_reconnect", "model": "gemini-3.5-transcribe-live",
                   "audio_s": stream._audio_s, "cost_usd": 0.0, "cost_unmeasured": True,
                   "clip": clip.clip_id, "replay_s": args.replay})
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clip", default="mono_javier_intro_50s")
    p.add_argument("--replay", type=int, choices=[2, 5], required=True)
    p.add_argument("--at", type=float, default=25.0)
    p.add_argument("--drain", type=float, default=10.0)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = asyncio.run(run(args))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in
                      ("updates_full", "hypothesis", "usage_observations", "events")}, indent=2))


if __name__ == "__main__":
    main()
