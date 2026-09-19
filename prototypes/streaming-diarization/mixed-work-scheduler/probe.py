"""THROWAWAY P1 PROTOTYPE: replay retained canonical work through scheduler choices.

Question: which smallest policy keeps mono_javier plus a panel meeting current while a
non-preemptible File/URL window uses only spare decoder capacity?

The input is content-free production runtime evidence: canonical queue/start/processed
events.  The simulator preserves every live item and its measured service cost.  It varies
only dispatch order, worker count, and (for the deliberately risky coalescing arm) request
geometry.  It never calls a decoder.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE = Path("/private/tmp/claude-501/lag/r1/result.json")
HERE = Path(__file__).resolve().parent


@dataclass(frozen=True, slots=True)
class Work:
    key: str
    kind: str
    session: str | None
    arrival: float
    service: float
    audio_seconds: float
    audio_end: float
    source_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Started:
    work: Work
    started: float
    worker: int


@dataclass(slots=True)
class PolicyResult:
    name: str
    workers: int
    max_live_calls: int
    records: list[dict[str, object]] = field(default_factory=list)
    peak_calls: int = 0
    background_completed: int = 0
    background_cancelled_queued: int = 0
    changed_decoder_context: bool = False


def _percentile(values: Iterable[float], fraction: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    point = (len(ordered) - 1) * fraction
    lo = math.floor(point)
    hi = math.ceil(point)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (point - lo)


def load_live_work(source: Path, *, seconds: float) -> list[Work]:
    raw = json.loads(source.read_text())
    selected = {
        3: "mono_javier_intro_50s",
        4: "discussion_jamie_dimon_panel",
    }
    work: list[Work] = []
    for result in raw["session_results"]:
        ordinal = result["ordinal"]
        if ordinal not in selected:
            continue
        origin = float(result["started_monotonic"])
        queued: dict[int, float] = {}
        started: dict[int, float] = {}
        processed: dict[int, list[dict[str, object]]] = defaultdict(list)
        for event in result["events"]:
            payload = event["payload"]
            item_id = payload.get("item_id")
            if not isinstance(item_id, int):
                continue
            at = float(payload.get("runtime_monotonic_ns", 0)) / 1e9 - origin
            if event["kind"] == "canonical_queued":
                queued[item_id] = at
            elif event["kind"] == "canonical_started":
                started[item_id] = at
            elif event["kind"] == "canonical_processed":
                processed[item_id].append(payload)
        for item_id, arrival in queued.items():
            rows = processed.get(item_id, [])
            if arrival > seconds or item_id not in started or not rows:
                continue
            finished = max(float(row["runtime_monotonic_ns"]) / 1e9 - origin for row in rows)
            service = max(0.001, finished - started[item_id])
            audio_seconds = sum(float(row.get("frozen_span_duration_sec", 0)) for row in rows)
            audio_end = max(float(row.get("committed_samples", 0)) / 16000 for row in rows)
            work.append(
                Work(
                    key=f"{selected[ordinal]}:{item_id}",
                    kind="live",
                    session=selected[ordinal],
                    arrival=max(0.0, arrival),
                    service=service,
                    audio_seconds=audio_seconds,
                    audio_end=audio_end,
                    source_ids=(item_id,),
                )
            )
    if {item.session for item in work} != set(selected.values()):
        raise RuntimeError("retained trace did not contain both required stress sessions")
    return sorted(work, key=lambda item: (item.arrival, item.session or "", item.source_ids))


def background_work(
    *, window_seconds: float, count: int = 20, arrival: float = 0.0, prefix: str = "file-window"
) -> list[Work]:
    return [
        Work(
            key=f"{prefix}:{index}",
            kind="background",
            session=None,
            arrival=arrival,
            service=window_seconds,
            audio_seconds=150.0,
            audio_end=(index + 1) * 120.0,
            source_ids=(index,),
        )
        for index in range(count)
    ]


def _fit_service(live: list[Work]) -> tuple[float, float]:
    xs = [item.audio_seconds for item in live]
    ys = [item.service for item in live]
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    denominator = sum((x - x_mean) ** 2 for x in xs)
    slope = 0.0 if denominator == 0 else sum(
        (x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True)
    ) / denominator
    return max(0.001, y_mean - slope * x_mean), max(0.0, slope)


def _coalesce(queue: deque[Work], intercept: float, slope: float) -> Work:
    first = queue.popleft()
    chosen = [first]
    audio = first.audio_seconds
    while queue and audio + queue[0].audio_seconds <= 2.5:
        chosen.append(queue.popleft())
        audio += chosen[-1].audio_seconds
    if len(chosen) == 1:
        return first
    return Work(
        key="+".join(item.key for item in chosen),
        kind="live",
        session=first.session,
        arrival=min(item.arrival for item in chosen),
        service=intercept + slope * audio,
        audio_seconds=audio,
        audio_end=max(item.audio_end for item in chosen),
        source_ids=tuple(source_id for item in chosen for source_id in item.source_ids),
    )


def simulate(
    live: list[Work],
    background: list[Work],
    *,
    name: str,
    workers: int,
    max_live_calls: int,
    live_policy: str,
    cancel_background_at: float,
) -> PolicyResult:
    result = PolicyResult(
        name=name,
        workers=workers,
        max_live_calls=max_live_calls,
        changed_decoder_context=live_policy == "coalesce",
    )
    arrivals = sorted([*live, *background], key=lambda item: (item.arrival, item.kind, item.key))
    arrival_index = 0
    now = 0.0
    ready: dict[str, deque[Work]] = defaultdict(deque)
    background_ready: deque[Work] = deque()
    running: list[tuple[float, int, Started]] = []
    next_run = 0
    round_robin: deque[str] = deque()
    in_round_robin: set[str] = set()
    intercept, slope = _fit_service(live)
    cancelled = False

    def admit(item: Work) -> None:
        if item.kind == "background":
            if not cancelled:
                background_ready.append(item)
            return
        assert item.session is not None
        ready[item.session].append(item)
        if item.session not in in_round_robin:
            round_robin.append(item.session)
            in_round_robin.add(item.session)

    def choose_live() -> Work | None:
        nonlocal round_robin
        running_sessions = {
            started.work.session
            for _, _, started in running
            if started.work.kind == "live"
        }
        sessions = [
            session
            for session, queue in ready.items()
            if queue and session not in running_sessions
        ]
        if not sessions:
            return None
        if live_policy == "item_rr":
            checked = 0
            while round_robin and checked < len(round_robin):
                session = round_robin.popleft()
                in_round_robin.discard(session)
                checked += 1
                if not ready[session]:
                    continue
                if session in running_sessions:
                    round_robin.append(session)
                    in_round_robin.add(session)
                    continue
                item = ready[session].popleft()
                if ready[session]:
                    round_robin.append(session)
                    in_round_robin.add(session)
                return item
            return None
        session = min(sessions, key=lambda candidate: (ready[candidate][0].audio_end, candidate))
        if live_policy == "coalesce":
            item = _coalesce(ready[session], intercept, slope)
        else:
            item = ready[session].popleft()
        if not ready[session]:
            try:
                round_robin.remove(session)
            except ValueError:
                pass
            in_round_robin.discard(session)
        return item

    def dispatch() -> None:
        nonlocal next_run
        while len(running) < workers:
            live_running = sum(started.work.kind == "live" for _, _, started in running)
            item = choose_live() if live_running < max_live_calls else None
            if item is None:
                background_running = sum(
                    started.work.kind == "background" for _, _, started in running
                )
                if not background_ready or background_running >= 1:
                    return
                item = background_ready.popleft()
            used = {started.worker for _, _, started in running}
            worker = next(index for index in range(workers) if index not in used)
            started = Started(item, now, worker)
            heapq.heappush(running, (now + item.service, next_run, started))
            next_run += 1
            result.peak_calls = max(result.peak_calls, len(running))

    while arrival_index < len(arrivals) or running or any(ready.values()) or background_ready:
        next_arrival = arrivals[arrival_index].arrival if arrival_index < len(arrivals) else math.inf
        next_finish = running[0][0] if running else math.inf
        next_cancel = cancel_background_at if not cancelled else math.inf
        now = min(next_arrival, next_finish, next_cancel)
        if not math.isfinite(now):
            break
        while running and running[0][0] <= now + 1e-9:
            finished, _, started = heapq.heappop(running)
            work = started.work
            result.records.append(
                {
                    "key": work.key,
                    "kind": work.kind,
                    "session": work.session,
                    "arrival": work.arrival,
                    "started": started.started,
                    "displayed_or_finished": finished,
                    "queue_wait": started.started - work.arrival,
                    "service": work.service,
                    "audio_seconds": work.audio_seconds,
                    "audio_end": work.audio_end,
                    "source_ids": list(work.source_ids),
                    "worker": started.worker,
                }
            )
            if work.kind == "background":
                result.background_completed += 1
        if not cancelled and next_cancel <= now + 1e-9:
            cancelled = True
            result.background_cancelled_queued = len(background_ready)
            background_ready.clear()
        while arrival_index < len(arrivals) and arrivals[arrival_index].arrival <= now + 1e-9:
            admit(arrivals[arrival_index])
            arrival_index += 1
        dispatch()
    return result


def summarize(result: PolicyResult, expected: dict[str, list[int]], *, stop_at: float) -> dict[str, object]:
    live_records = [row for row in result.records if row["kind"] == "live"]
    by_session: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in live_records:
        by_session[str(row["session"])].append(row)
    sessions: dict[str, object] = {}
    preserved = True
    for session, rows in sorted(by_session.items()):
        observed = [source_id for row in rows for source_id in row["source_ids"]]
        preserved = preserved and observed == expected[session]
        waits = [float(row["queue_wait"]) for row in rows]
        pending_at_stop = sum(
            float(row["audio_seconds"])
            for row in rows
            if float(row["arrival"]) <= stop_at < float(row["displayed_or_finished"])
        )
        sessions[session] = {
            "items": len(observed),
            "dispatches": len(rows),
            "queue_wait_p50": _percentile(waits, 0.5),
            "queue_wait_p95": _percentile(waits, 0.95),
            "queue_wait_max": max(waits, default=0.0),
            "pending_audio_seconds_at_simultaneous_stop": pending_at_stop,
            "last_display_seconds": max(
                (float(row["displayed_or_finished"]) for row in rows), default=0.0
            ),
        }
    background = [row for row in result.records if row["kind"] == "background"]
    live_while_background = [
        row for row in live_records
        if any(
            float(bg["started"]) <= float(row["arrival"]) < float(bg["displayed_or_finished"])
            for bg in background
        )
    ]
    return {
        "policy": result.name,
        "workers": result.workers,
        "max_live_calls": result.max_live_calls,
        "peak_calls": result.peak_calls,
        "live_items_once_and_in_order": preserved,
        "changed_decoder_context": result.changed_decoder_context,
        "background_completed_before_cancel_boundary": result.background_completed,
        "background_cancelled_queued": result.background_cancelled_queued,
        "live_queue_wait_p95_while_background_running": _percentile(
            [float(row["queue_wait"]) for row in live_while_background], 0.95
        ),
        "sessions": sessions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--seconds", type=float, default=120.0)
    parser.add_argument("--background-window-seconds", type=float, default=12.0)
    parser.add_argument("--cancel-background-at", type=float, default=60.0)
    parser.add_argument("--write", type=Path, default=HERE / "results.json")
    args = parser.parse_args()

    live = load_live_work(args.source, seconds=args.seconds)
    background = background_work(window_seconds=args.background_window_seconds)
    expected = {
        session: [source_id for item in live if item.session == session for source_id in item.source_ids]
        for session in sorted({item.session for item in live if item.session is not None})
    }
    policies = [
        simulate(
            live,
            background,
            name="serial_item_round_robin",
            workers=1,
            max_live_calls=1,
            live_policy="item_rr",
            cancel_background_at=args.cancel_background_at,
        ),
        simulate(
            live,
            background,
            name="serial_audio_time",
            workers=1,
            max_live_calls=1,
            live_policy="audio_time",
            cancel_background_at=args.cancel_background_at,
        ),
        simulate(
            live,
            background,
            name="serial_coalesced_subcap",
            workers=1,
            max_live_calls=1,
            live_policy="coalesce",
            cancel_background_at=args.cancel_background_at,
        ),
        simulate(
            live,
            background,
            name="counterfactual_two_live_pumps",
            workers=2,
            max_live_calls=2,
            live_policy="audio_time",
            cancel_background_at=args.cancel_background_at,
        ),
        simulate(
            live,
            background,
            name="production_serial_live_pump_plus_background_lane",
            workers=2,
            max_live_calls=1,
            live_policy="item_rr",
            cancel_background_at=args.cancel_background_at,
        ),
    ]
    background_sweep = []
    for window_seconds in (2.0, 5.0, 10.0, 12.0, 20.0):
        policy = simulate(
            live,
            background_work(window_seconds=window_seconds),
            name="production_serial_live_pump_plus_background_lane",
            workers=2,
            max_live_calls=1,
            live_policy="item_rr",
            cancel_background_at=args.cancel_background_at,
        )
        summary = summarize(policy, expected, stop_at=args.seconds)
        background_sweep.append(
            {
                "background_window_service_seconds": window_seconds,
                "live_queue_wait_p95_while_background_running": summary[
                    "live_queue_wait_p95_while_background_running"
                ],
                "peak_calls": summary["peak_calls"],
                "live_items_once_and_in_order": summary["live_items_once_and_in_order"],
                "pending_audio_seconds_at_stop": {
                    session: values["pending_audio_seconds_at_simultaneous_stop"]
                    for session, values in summary["sessions"].items()
                },
            }
        )
    asymmetric_stop = simulate(
        live,
        background_work(
            window_seconds=30.0,
            count=2,
            arrival=45.0,
            prefix="stopped-meeting-terminal-window",
        ),
        name="one_meeting_stops_while_other_keeps_recording",
        workers=2,
        max_live_calls=1,
        live_policy="item_rr",
        cancel_background_at=args.seconds + 1.0,
    )
    asymmetric_records = asymmetric_stop.records
    first_settlement = next(
        row for row in asymmetric_records if row["key"] == "stopped-meeting-terminal-window:0"
    )
    second_settlement = next(
        row for row in asymmetric_records if row["key"] == "stopped-meeting-terminal-window:1"
    )
    live_during_first_settlement = [
        row
        for row in asymmetric_records
        if row["kind"] == "live"
        and float(first_settlement["started"])
        <= float(row["started"])
        < float(first_settlement["displayed_or_finished"])
    ]
    payload = {
        "schema": "moss-mixed-work-scheduler-prototype.v1",
        "source": str(args.source),
        "input": {
            "live_sessions": sorted(expected),
            "live_items": {session: len(ids) for session, ids in expected.items()},
            "trace_seconds": args.seconds,
            "simultaneous_stop_seconds": args.seconds,
            "background_window_service_seconds": args.background_window_seconds,
            "background_cancel_seconds": args.cancel_background_at,
            "third_live_admission": "capacity_full",
        },
        "assumptions": [
            "retained live item service times transfer to the two-session replay",
            "a File/URL safe boundary is one 150-second WindowedRunner request",
            "running decoder requests are non-preemptible",
            "production has one serial canonical pump; the second decoder slot is not a second Live pump",
            "coalescing service is a least-squares estimate and cannot establish semantic parity",
        ],
        "results": [summarize(policy, expected, stop_at=args.seconds) for policy in policies],
        "nonpreemptible_background_sweep": background_sweep,
        "asymmetric_stop_falsifier": {
            "first_settlement": first_settlement,
            "second_settlement": second_settlement,
            "second_settlement_waited_for_first": (
                float(second_settlement["started"])
                >= float(first_settlement["displayed_or_finished"])
            ),
            "live_items_dispatched_while_first_settlement_ran": len(live_during_first_settlement),
            "peak_calls": asymmetric_stop.peak_calls,
        },
        "full_records": {policy.name: policy.records for policy in policies},
    }
    args.write.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: value for key, value in payload.items() if key != "full_records"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
