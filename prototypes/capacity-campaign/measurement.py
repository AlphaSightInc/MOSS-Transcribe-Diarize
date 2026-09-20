"""PROTOTYPE ONLY: attributed projections for the S7/S8 fix campaign."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from moss_transcribe_diarize.app.inference_scheduler import InferenceDispatchTiming
from tools.qualify.scheduler_timing import project_dispatch_timings


_FIELDS = {
    "owner_kind",
    "owner_key",
    "window_index",
    "accepted_monotonic_ns",
    "wait_started_monotonic_ns",
    "started_monotonic_ns",
    "ended_monotonic_ns",
}


def _timings(rows: Iterable[Mapping[str, object]]) -> tuple[InferenceDispatchTiming, ...]:
    result = []
    for row in rows:
        if not _FIELDS.issubset(row):
            raise ValueError("dispatch evidence must contain attributed in-process stage clocks")
        result.append(InferenceDispatchTiming(**{name: row[name] for name in _FIELDS}))
    return tuple(result)


def _maximum_inflight(
    rows: Iterable[InferenceDispatchTiming], *, background_only: bool = False
) -> int:
    edges = []
    for row in rows:
        if row.started_monotonic_ns is None or row.ended_monotonic_ns is None:
            continue
        if background_only and row.owner_kind != "background":
            continue
        edges.extend(((row.started_monotonic_ns, 1, 1), (row.ended_monotonic_ns, 0, -1)))
    active = maximum = 0
    for _at, _end_before_start, change in sorted(edges):
        active += change
        maximum = max(maximum, active)
    return maximum


def summarize_dispatch(
    rows: Iterable[Mapping[str, object]],
    *,
    file_acceptances_ns: Mapping[str, int],
    terminal_keys: Iterable[str],
    first_dispatch_limit_sec: float,
) -> dict[str, object]:
    """Project only clocks that carry an in-process owner and complete denominator."""

    timings = _timings(rows)
    file_keys = frozenset(file_acceptances_ns)
    terminals = frozenset(terminal_keys)
    projection = project_dispatch_timings(
        timings,
        file_keys=file_keys,
        terminal_keys=terminals,
    )
    first_starts = {
        key: min(
            row.started_monotonic_ns
            for row in timings
            if row.owner_key == key and row.started_monotonic_ns is not None
        )
        for key in file_keys
        if any(row.owner_key == key and row.started_monotonic_ns is not None for row in timings)
    }
    acceptance_to_first = {
        key: max(0, first_starts[key] - accepted) / 1_000_000_000
        for key, accepted in file_acceptances_ns.items()
        if key in first_starts
    }
    last_terminal_end = max(
        (
            row.ended_monotonic_ns
            for row in timings
            if row.owner_key in terminals and row.ended_monotonic_ns is not None
        ),
        default=None,
    )
    interleaving = {
        key: last_terminal_end is not None and started < last_terminal_end
        for key, started in first_starts.items()
    }
    live_opportunities = []
    for background in timings:
        if background.owner_kind != "background" or background.started_monotonic_ns is None:
            continue
        for live in timings:
            if live.owner_kind != "live" or live.started_monotonic_ns is None:
                continue
            if (
                background.wait_started_monotonic_ns
                <= live.accepted_monotonic_ns
                < background.started_monotonic_ns
            ):
                live_opportunities.append(live.started_monotonic_ns < background.started_monotonic_ns)
    maximum_total = _maximum_inflight(timings)
    maximum_background = _maximum_inflight(timings, background_only=True)
    completed = projection["completed_windows"]
    denominator = projection["full_denominator"]
    passes = (
        bool(file_keys)
        and set(acceptance_to_first) == set(file_keys)
        and all(value <= first_dispatch_limit_sec for value in acceptance_to_first.values())
        and all(interleaving.values())
        and maximum_total <= 2
        and maximum_background <= 1
        and completed == denominator
        and bool(live_opportunities)
        and all(live_opportunities)
    )
    return {
        **projection,
        "file_acceptance_to_first_dispatch_sec": acceptance_to_first,
        "fair_file_interleaving": interleaving,
        "maximum_total_inflight": maximum_total,
        "maximum_background_inflight": maximum_background,
        "live_preemptions": {
            "observed": len(live_opportunities),
            "passed": sum(live_opportunities),
        },
        "first_dispatch_limit_sec": first_dispatch_limit_sec,
        "passes": passes,
    }


__all__ = ["summarize_dispatch"]
