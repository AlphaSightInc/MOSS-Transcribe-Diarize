"""Content-free projections of server-local decoder dispatch clocks."""

from __future__ import annotations

from collections.abc import Iterable

from moss_transcribe_diarize.app.inference_scheduler import InferenceDispatchTiming


def _elapsed(start_ns: int, end_ns: int | None) -> float | None:
    if end_ns is None:
        return None
    return max(0, end_ns - start_ns) / 1_000_000_000


def _covered_ns(start_ns: int, end_ns: int, intervals: Iterable[tuple[int, int]]) -> int:
    covered = sorted(
        (max(start_ns, left), min(end_ns, right))
        for left, right in intervals
        if left < end_ns and right > start_ns
    )
    if not covered:
        return 0
    total = 0
    left, right = covered[0]
    for next_left, next_right in covered[1:]:
        if next_left <= right:
            right = max(right, next_right)
        else:
            total += right - left
            left, right = next_left, next_right
    return total + right - left


def project_dispatch_timings(
    timings: Iterable[InferenceDispatchTiming],
    *,
    file_keys: Iterable[str] = (),
    terminal_keys: Iterable[str] = (),
) -> dict[str, object]:
    """Project wait/service durations without subtracting clocks from another host."""

    rows = tuple(timings)
    files = frozenset(file_keys)
    terminals = frozenset(terminal_keys)
    projected = [
        {
            "owner_kind": row.owner_kind,
            "owner_key": row.owner_key,
            "window_index": row.window_index,
            "accepted_monotonic_ns": row.accepted_monotonic_ns,
            "wait_started_monotonic_ns": row.wait_started_monotonic_ns,
            "started_monotonic_ns": row.started_monotonic_ns,
            "ended_monotonic_ns": row.ended_monotonic_ns,
            "acceptance_to_dispatch_sec": _elapsed(
                row.accepted_monotonic_ns, row.started_monotonic_ns
            ),
            "wait_sec": _elapsed(
                row.wait_started_monotonic_ns, row.started_monotonic_ns
            ),
            "service_sec": (
                None
                if row.started_monotonic_ns is None
                else _elapsed(row.started_monotonic_ns, row.ended_monotonic_ns)
            ),
        }
        for row in rows
    ]
    first_file_dispatch = {
        key: _elapsed(
            min(row.accepted_monotonic_ns for row in rows if row.owner_key == key),
            min(
                row.started_monotonic_ns
                for row in rows
                if row.owner_key == key and row.started_monotonic_ns is not None
            ),
        )
        for key in files
        if any(
            row.owner_key == key and row.started_monotonic_ns is not None
            for row in rows
        )
    }
    terminal_service = {
        key: tuple(
            (row.started_monotonic_ns, row.ended_monotonic_ns)
            for row in rows
            if row.owner_key == key
            and row.started_monotonic_ns is not None
            and row.ended_monotonic_ns is not None
        )
        for key in terminals
    }
    terminal_wait_by_owner = {
        key: sum(
            _covered_ns(
                row.wait_started_monotonic_ns,
                row.started_monotonic_ns,
                (
                    interval
                    for other_key, intervals in terminal_service.items()
                    if other_key != key
                    for interval in intervals
                ),
            )
            for row in rows
            if row.owner_key == key and row.started_monotonic_ns is not None
        )
        / 1_000_000_000
        for key in terminals
    }
    return {
        "windows": projected,
        "file_acceptance_to_first_dispatch_sec": first_file_dispatch,
        "terminal_wait_by_owner_sec": terminal_wait_by_owner,
        "terminal_vs_terminal_wait_sec": sum(terminal_wait_by_owner.values()),
        "completed_windows": sum(
            item["ended_monotonic_ns"] is not None for item in projected
        ),
        "full_denominator": len(projected),
    }


def detects_whole_batch_hold(
    timings: Iterable[InferenceDispatchTiming],
    *,
    terminal_key: str,
    file_key: str,
) -> bool:
    """True when File starts only after the terminal owner's last retained call ends."""

    rows = tuple(timings)
    terminal_ends = [
        row.ended_monotonic_ns
        for row in rows
        if row.owner_key == terminal_key and row.ended_monotonic_ns is not None
    ]
    file_starts = [
        row.started_monotonic_ns
        for row in rows
        if row.owner_key == file_key and row.started_monotonic_ns is not None
    ]
    return bool(terminal_ends and file_starts and min(file_starts) >= max(terminal_ends))


__all__ = ["detects_whole_batch_hold", "project_dispatch_timings"]
