"""Find wordless stretches witnessed by a different transcript pass."""
from __future__ import annotations

from typing import Sequence

from .live_span_bounds import LIVE_SAMPLE_RATE


def missing_witness_intervals(
    witness: Sequence[tuple[int, int]], result: Sequence[tuple[int, int]], *,
    minimum_samples: int = 10 * LIVE_SAMPLE_RATE,
) -> tuple[tuple[int, int], ...]:
    """Return witnessed intervals absent from result (all if result is empty)."""
    merged: list[list[int]] = []
    for start, end in sorted(witness):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if not result:
        return tuple((start, end) for start, end in merged)
    gaps = []
    for start, end in merged:
        cursor = start
        for lo, hi in sorted(result):
            if hi <= cursor or lo >= end:
                continue
            if lo - cursor >= minimum_samples:
                gaps.append((cursor, lo))
            cursor = max(cursor, hi)
        if end - cursor >= minimum_samples:
            gaps.append((cursor, end))
    return tuple(gaps)
