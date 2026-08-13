from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


class LiveVectorJournalObservation(Protocol):
    speaker_label: str
    centroid: tuple[float, ...]
    sample_seconds: float
    embedder_id: str
    embedder_state_sha: str


@dataclass(frozen=True, slots=True)
class LiveVectorJournalRefusal:
    speaker_label: str
    reason: str


@dataclass(frozen=True, slots=True)
class LiveVectorJournalAppendResult:
    written: int
    refusals: tuple[LiveVectorJournalRefusal, ...]


class LiveVectorJournal:
    """Append complete session batches to one private JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def append_session(
        self,
        *,
        session_id: str,
        echo_mode: str,
        created_at: float,
        observations: Sequence[LiveVectorJournalObservation],
    ) -> LiveVectorJournalAppendResult:
        rows: list[dict[str, object]] = []
        refusals: list[LiveVectorJournalRefusal] = []
        for observation in observations:
            reason = _observation_refusal(observation)
            if reason is not None:
                refusals.append(
                    LiveVectorJournalRefusal(
                        speaker_label=observation.speaker_label or "<unnamed>",
                        reason=reason,
                    )
                )
                continue
            rows.append(
                {
                    "session_id": session_id,
                    "speaker_label": observation.speaker_label,
                    "centroid": list(observation.centroid),
                    "sample_seconds": observation.sample_seconds,
                    "embedder_id": observation.embedder_id,
                    "embedder_state_sha": observation.embedder_state_sha,
                    "created_at": created_at,
                    "echo_mode": echo_mode,
                }
            )

        if rows:
            payload = b"".join(
                (
                    json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True)
                    + "\n"
                ).encode("utf-8")
                for row in rows
            )
            with self._lock:
                descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
                try:
                    _write_all(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        return LiveVectorJournalAppendResult(written=len(rows), refusals=tuple(refusals))


def _observation_refusal(observation: LiveVectorJournalObservation) -> str | None:
    centroid = observation.centroid
    if not centroid:
        return "centroid_empty"
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in centroid):
        return "centroid_not_numeric"
    if any(not math.isfinite(value) for value in centroid):
        return "centroid_non_finite"
    if not math.isfinite(observation.sample_seconds) or observation.sample_seconds <= 0:
        return "sample_seconds_invalid"
    if not observation.embedder_id:
        return "embedder_id_missing"
    if len(observation.embedder_state_sha) != 64 or any(
        character not in "0123456789abcdef" for character in observation.embedder_state_sha
    ):
        return "embedder_state_sha_invalid"
    return None


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("vector journal append made no progress")
        view = view[written:]
