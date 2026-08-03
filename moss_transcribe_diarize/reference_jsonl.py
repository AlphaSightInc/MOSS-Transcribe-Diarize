"""Shared dependency-free loading for speaker-reference JSONL records."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_reference_records(
    path: str | Path,
    *,
    empty_description: str = "record",
) -> list[dict[str, Any]]:
    source = Path(path)
    try:
        lines = source.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValueError(f"reference is unreadable: {source}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"reference record {line_number} is not valid JSONL") from exc
        if not isinstance(row, dict):
            raise ValueError(f"reference record {line_number} must be an object")
        rows.append(row)
    if not rows:
        raise ValueError(f"reference must contain at least one {empty_description}")
    return rows


__all__ = ["load_reference_records"]
