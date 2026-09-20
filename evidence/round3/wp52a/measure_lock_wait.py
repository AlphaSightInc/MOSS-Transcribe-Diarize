"""Measure capture-frame latency while lifecycle admission polling holds the runtime lock."""

from __future__ import annotations

import json
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tests"))

from test_live_service_runtime import _frame, _runtime  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import active_live_session_count  # noqa: E402


def distribution(values_ns: list[int]) -> dict[str, float | int]:
    ordered = sorted(values_ns)

    def percentile(value: float) -> float:
        index = min(len(ordered) - 1, max(0, round(value * (len(ordered) - 1))))
        return ordered[index] / 1_000_000

    return {
        "n": len(ordered),
        "median_ms": statistics.median(ordered) / 1_000_000,
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "max_ms": ordered[-1] / 1_000_000,
    }


def measure_frames(
    runtime,
    session_id: str,
    *,
    count: int,
    yield_after: bool = False,
) -> list[int]:
    elapsed: list[int] = []
    for sequence in range(count):
        started = time.perf_counter_ns()
        runtime.accept_frame(session_id, _frame(sequence, samples=1))
        elapsed.append(time.perf_counter_ns() - started)
        if yield_after:
            time.sleep(0)
    return elapsed


def main() -> None:
    history_count = 1_000
    frame_count = 2_000
    session_ids = tuple(f"history-{index}" for index in range(history_count)) + (
        "baseline-capture",
        "polled-capture",
    )
    runtime = _runtime(
        speech=(False,) * frame_count,
        session_ids=session_ids,
    )
    for _ in session_ids:
        runtime.create()
    for state in tuple(runtime._sessions.values())[:history_count]:
        state.session._status = "closed"

    baseline = measure_frames(runtime, "baseline-capture", count=frame_count)

    start = threading.Event()
    stop = threading.Event()
    polls: list[int] = []

    def poll() -> None:
        start.wait()
        while not stop.is_set():
            started = time.perf_counter_ns()
            assert active_live_session_count(runtime) == 2
            polls.append(time.perf_counter_ns() - started)
            time.sleep(0)

    thread = threading.Thread(target=poll, name="wp52a-operator-poll")
    thread.start()
    start.set()
    under_poll = measure_frames(
        runtime,
        "polled-capture",
        count=frame_count,
        yield_after=True,
    )
    stop.set()
    thread.join()

    print(
        json.dumps(
            {
                "base_sha": "a7a738cf9f9ff246f64c52c112e0bf597ba58241",
                "history_sessions": history_count,
                "active_sessions": 2,
                "capture_frames_per_arm": frame_count,
                "capture_without_poll": distribution(baseline),
                "capture_during_poll": distribution(under_poll),
                "lifecycle_poll": distribution(polls),
                "notes": "Capture numbers are whole accept_frame calls; excess over the no-poll arm includes runtime-lock wait. No product threshold is asserted.",
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
