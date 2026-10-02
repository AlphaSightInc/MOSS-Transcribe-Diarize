"""Capture gaps are timeline metadata, never speech or speaker rows."""
from __future__ import annotations


def interruption_fields(gaps: list[dict], sample_rate: int = 16000) -> dict:
    if not gaps:
        return {}
    return {
        "capture_interruptions": [dict(gap) for gap in gaps if gap["end_sample"] is not None],
        "sample_rate": sample_rate,
    }
