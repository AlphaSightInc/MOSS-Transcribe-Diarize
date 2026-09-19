"""Deterministic live transcript-growth probe; no network, GPU, or microphone."""

from __future__ import annotations

import asyncio
import json
import time
import tracemalloc
from pathlib import Path

from moss_transcribe_diarize.app.live_service_runtime import _ManualCanonicalPumpScheduler
from moss_transcribe_diarize.app.live_session import AudioFrame, LIVE_SAMPLE_RATE
from tests.test_live_rolling_wiring import _decoders, _runtime


HERE = Path(__file__).resolve().parent


async def _stop(runtime, scheduler, session_id: str):
    task = asyncio.create_task(runtime.stop(session_id, 30.0))
    while not task.done():
        scheduler.drain()
        await asyncio.sleep(0)
    return await task


def measure(seconds: int) -> dict[str, object]:
    scheduler = _ManualCanonicalPumpScheduler()
    base, _ = _decoders(rolling=False)
    runtime = _runtime(base=base, rolling=None, scheduler=scheduler)
    created = runtime.create()
    pcm = b"\x11\x22" * LIVE_SAMPLE_RATE

    tracemalloc.start()
    feed_started = time.perf_counter()
    for sequence in range(seconds):
        runtime.accept_frame(
            created.session_id,
            AudioFrame(sequence=sequence, pcm=pcm, sample_count=LIVE_SAMPLE_RATE),
        )
        # Model an inference worker that keeps pace. This avoids measuring an artificial
        # zero-delay producer backlog while preserving every production publication step.
        scheduler.drain()
    feed_elapsed = time.perf_counter() - feed_started

    snapshot_started = time.perf_counter()
    before = runtime.snapshot(created.session_id)
    snapshot_elapsed = time.perf_counter() - snapshot_started
    stop_started = time.perf_counter()
    stopped = asyncio.run(_stop(runtime, scheduler, created.session_id))
    stop_elapsed = time.perf_counter() - stop_started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "seconds": seconds,
        "frames": seconds,
        "canonical_calls": len(base.calls),
        "published_segments": len(before.session.effective_transcript),
        "retained_events": len(runtime.events(created.session_id)),
        "feed_elapsed_seconds": feed_elapsed,
        "snapshot_elapsed_seconds": snapshot_elapsed,
        "stop_elapsed_seconds": stop_elapsed,
        "peak_python_bytes": peak,
        "final_status": stopped.session.status,
    }


def main() -> int:
    rows = [measure(seconds) for seconds in (300, 900, 1_800, 12_060)]
    report = {
        "schema_version": 1,
        "decoder_calls": 0,
        "scope": "deterministic speech publication scaling; not acoustic qualification",
        "rows": rows,
        "growth": {
            "peak_bytes_30m_over_5m": rows[2]["peak_python_bytes"] / rows[0]["peak_python_bytes"],
            "feed_time_30m_over_5m": rows[2]["feed_elapsed_seconds"] / rows[0]["feed_elapsed_seconds"],
            "segments_30m_over_5m": rows[2]["published_segments"] / rows[0]["published_segments"],
            "feed_time_201m_over_30m": rows[3]["feed_elapsed_seconds"] / rows[2]["feed_elapsed_seconds"],
            "segments_201m_over_30m": rows[3]["published_segments"] / rows[2]["published_segments"],
        },
    }
    (HERE / "speech-scaling-results.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
