#!/usr/bin/env python3
"""Measure the proposed session-end vector-journal append primitive.

Question: can one service process append complete per-session JSONL batches durably,
without interleaving concurrent clean stops, while declining an unusable observation
by name instead of losing the usable speakers beside it?

Run:
    python3 prototypes/streaming-diarization/proto_vector_journal.py \
      --json-output evidence/phase1/t6/iteration-5-journal-prototype.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import statistics
import tempfile
import threading
import time
from pathlib import Path


REQUIRED_FIELDS = {
    "session_id",
    "speaker_label",
    "centroid",
    "sample_seconds",
    "embedder_id",
    "embedder_state_sha",
    "created_at",
    "echo_mode",
}


class JournalProbe:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def append_session(self, observations: list[dict[str, object]]) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        refusals: dict[str, int] = {}
        for observation in observations:
            refusal = _observation_refusal(observation)
            if refusal is not None:
                refusals[refusal] = refusals.get(refusal, 0) + 1
                continue
            rows.append(observation)

        payload = b"".join(
            (json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
            for row in rows
        )
        with self._lock:
            descriptor = os.open(self.path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
            try:
                _write_all(descriptor, payload)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return {"written": len(rows), "refusals": refusals, "fsync_completed": True}


def _observation_refusal(observation: dict[str, object]) -> str | None:
    centroid = observation.get("centroid")
    if not isinstance(centroid, list) or not centroid:
        return "centroid_empty"
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in centroid):
        return "centroid_non_finite"
    return None


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("journal append made no progress")
        view = view[written:]


def _observations(session_index: int, speakers: int, dimensions: int) -> list[dict[str, object]]:
    session_id = f"probe-session-{session_index:04d}"
    common = {
        "session_id": session_id,
        "embedder_id": "probe-embedder:probe-revision",
        "embedder_state_sha": "ab" * 32,
        "created_at": 1_800_000_000.0 + session_index,
        "echo_mode": "headphones" if session_index % 2 == 0 else "speakers",
    }
    rows = [
        {
            **common,
            "speaker_label": f"speaker-{speaker_index + 1:04d}",
            "centroid": [
                (session_index + speaker_index + dimension_index + 1) / 10_000
                for dimension_index in range(dimensions)
            ],
            "sample_seconds": float(speaker_index + 1),
        }
        for speaker_index in range(speakers)
    ]
    rows.append(
        {
            **common,
            "speaker_label": "unusable-observation",
            "centroid": [float("nan")],
            "sample_seconds": 1.0,
        }
    )
    return rows


def run(*, sessions: int, speakers: int, dimensions: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="moss-vector-journal-") as directory:
        journal_path = Path(directory) / "speaker-vectors.jsonl"
        journal = JournalProbe(journal_path)
        barrier = threading.Barrier(sessions)

        def append(session_index: int) -> tuple[int, dict[str, object], float]:
            observations = _observations(session_index, speakers, dimensions)
            barrier.wait()
            started = time.perf_counter()
            result = journal.append_session(observations)
            return session_index, result, (time.perf_counter() - started) * 1_000

        started = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=sessions) as executor:
            results = list(executor.map(append, range(sessions)))
        elapsed_ms = (time.perf_counter() - started) * 1_000

        journal_bytes = journal_path.read_bytes()
        raw_lines = journal_bytes.splitlines()
        rows = [json.loads(line) for line in raw_lines]
        session_order = [str(row["session_id"]) for row in rows]
        positions: dict[str, list[int]] = {}
        for index, session_id in enumerate(session_order):
            positions.setdefault(session_id, []).append(index)
        contiguous_batches = all(
            indexes == list(range(indexes[0], indexes[0] + speakers))
            for indexes in positions.values()
        )
        latencies_ms = [latency for _, _, latency in results]
        refusal_total = sum(
            int(result["refusals"].get("centroid_non_finite", 0))
            for _, result, _ in results
        )

        checks = {
            "all_rows_parseable": len(rows) == sessions * speakers,
            "all_session_batches_contiguous": contiguous_batches,
            "all_required_fields_exact": all(set(row) == REQUIRED_FIELDS for row in rows),
            "centroids_finite_and_full_width": all(
                len(row["centroid"]) == dimensions
                and all(math.isfinite(value) for value in row["centroid"])
                for row in rows
            ),
            "embedder_identity_on_every_row": all(
                row["embedder_id"] and len(row["embedder_state_sha"]) == 64 for row in rows
            ),
            "no_device_key": all("device_id" not in row for row in rows),
            "one_named_refusal_per_session": refusal_total == sessions,
            "one_fsync_per_session": all(result["fsync_completed"] for _, result, _ in results),
            "private_file_mode": (journal_path.stat().st_mode & 0o777) == 0o600,
        }
        return {
            "question": (
                "Can one service process durably append complete session-keyed JSONL batches "
                "under concurrent clean stops and decline an unusable observation by name?"
            ),
            "mechanism": "process lock + pre-encoded batch + O_APPEND + write-all + fsync",
            "dimensions": dimensions,
            "sessions": sessions,
            "speakers_per_session": speakers,
            "concurrent_workers": sessions,
            "journal_rows": len(rows),
            "journal_bytes": len(journal_bytes),
            "journal_sha256": hashlib.sha256(journal_bytes).hexdigest(),
            "named_refusals": {"centroid_non_finite": refusal_total},
            "session_batch_order": list(positions),
            "append_latency_ms": {
                "min": min(latencies_ms),
                "median": statistics.median(latencies_ms),
                "max": max(latencies_ms),
            },
            "total_elapsed_ms": elapsed_ms,
            "checks": checks,
            "verdict": "PASS" if all(checks.values()) else "FAIL",
            "limits": [
                "One process only; the product forbids multiple Uvicorn workers.",
                "Successful fsync is observed, not a simulated power-loss test.",
                "This probe does not configure the operator journal path or integrate session stop.",
            ],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sessions", type=int, default=32)
    parser.add_argument("--speakers", type=int, default=16)
    parser.add_argument("--dimensions", type=int, default=256)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    if min(args.sessions, args.speakers, args.dimensions) <= 0:
        parser.error("sessions, speakers, and dimensions must be positive")

    result = run(sessions=args.sessions, speakers=args.speakers, dimensions=args.dimensions)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
