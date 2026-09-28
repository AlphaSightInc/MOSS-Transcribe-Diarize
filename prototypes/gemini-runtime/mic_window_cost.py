"""One command: python prototypes/gemini-runtime/mic_window_cost.py.

Provider-free geometry/cost probe using production scheduler and the paced E1
usage receipt. Audio seconds and dollars here are modelled, not billed spend.
"""
from __future__ import annotations

import json
from pathlib import Path

from moss_transcribe_diarize.app.gemini_hybrid_engine import GrowingContextWindowScheduler
from moss_transcribe_diarize.app.live_span_bounds import LIVE_SAMPLE_RATE as RATE


def windows(seconds: int, *, length: int, stride: int) -> list[tuple[int, int]]:
    scheduler = GrowingContextWindowScheduler(max_seconds=length, stride_seconds=stride)
    previous = 0
    result = []
    for accepted in range(1, seconds + 1):
        planned = scheduler.next_window(accepted * RATE, previous)
        if planned is not None:
            start, end, _frontier = planned
            result.append((start // RATE, end // RATE))
            previous = end
    if previous < seconds * RATE:
        result.append((previous // RATE, seconds))  # exact idle/Stop suffix
    return result


def terminal_audio_seconds(seconds: int) -> int:
    start = total = 0
    while start < seconds:
        end = min(seconds, start + 900)
        total += end-start
        if end == seconds:
            break
        start = end-30
    return total


def main() -> None:
    receipt = json.loads((Path(__file__).resolve().parents[2] /
                          "evidence/P63/echogate-e1-http.json").read_text())
    seconds = int(receipt["source_seconds"])
    observed = receipt["engine_diagnostics"]
    live_seconds_per_lane = seconds + 2  # measured W3 terminal flush on E1
    batch_seconds = observed["audio_seconds_sent"] - 2 * live_seconds_per_lane
    batch_cost_per_second = ((observed["cost_usd"]-
                              observed["live_list_price_estimate_usd"]) / batch_seconds)
    live_cost_per_second = observed["live_list_price_estimate_usd"] / (2*live_seconds_per_lane)
    configs = {"selected_system": (180, 15), "selected_microphone": (30, 15)}
    output = {"source_seconds": seconds, "observed_batch_usd_per_second": batch_cost_per_second,
              "observed_live_estimate_usd_per_second": live_cost_per_second,
              "observed_total_usd_per_audio_hour": observed["cost_usd"] / seconds * 3600,
              "lanes": {}}
    for name, (length, stride) in configs.items():
        plan = windows(seconds, length=length, stride=stride)
        rolling_seconds = sum(end-start for start, end in plan)
        terminal_seconds = seconds
        live_seconds = live_seconds_per_lane
        cost = ((rolling_seconds+terminal_seconds)*batch_cost_per_second
                + live_seconds*live_cost_per_second)
        output["lanes"][name] = {
            "L": length, "S": stride, "windows": plan, "rolling_audio_seconds": rolling_seconds,
            "terminal_audio_seconds": terminal_seconds, "live_audio_seconds": live_seconds,
            "modeled_usd_per_e1": cost, "modeled_usd_per_audio_hour": cost/seconds*3600,
        }
    output["selected_total_usd_per_audio_hour"] = sum(
        output["lanes"][name]["modeled_usd_per_audio_hour"]
        for name in ("selected_system", "selected_microphone"))
    one_hour = {}
    for lane, length in (("system", 180), ("microphone", 30)):
        rolling_seconds = sum(end-start for start, end in windows(3600, length=length, stride=15))
        terminal_seconds = terminal_audio_seconds(3600)
        live_seconds = 3602
        one_hour[lane] = {"rolling_audio_seconds": rolling_seconds,
                          "terminal_audio_seconds": terminal_seconds,
                          "live_audio_seconds": live_seconds,
                          "modeled_usd": ((rolling_seconds+terminal_seconds)*batch_cost_per_second
                                          + live_seconds*live_cost_per_second)}
    output["one_hour_both_lanes_voiced"] = {"lanes": one_hour,
        "modeled_total_usd": sum(row["modeled_usd"] for row in one_hour.values())}
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
