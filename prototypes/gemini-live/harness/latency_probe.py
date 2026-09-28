"""250 ms public-snapshot latency observation for a 1.0x live replay.

Run as part of run_quality.py. For an existing run:
    python latency_probe.py --run-dir <quality-out>
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

RATE = 16000


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return round(ordered[low], 3)
    return round(ordered[low] * (high - pos) + ordered[high] * (pos - low), 3)


class LatencyProbe:
    def __init__(self, duration: float):
        self.duration = duration
        self.bucket_count = math.ceil(duration)
        self.words: list[float | None] = [None] * self.bucket_count
        self.labels: list[float | None] = [None] * self.bucket_count
        self.snapshots = 0
        self.timeline: list[dict] = []

    def observe(self, snapshot: dict, elapsed: float) -> None:
        self.snapshots += 1
        session = snapshot["session"]
        segments = session.get("effective_transcript") or []
        intervals = []
        for row in segments:
            if row.get("text", "").strip():
                intervals.append((row["start_sample"], row["end_sample"],
                                  row.get("canonical_speaker") is not None
                                  and row.get("authority") != "provisional"))
        draft = snapshot.get("draft")
        if isinstance(draft, dict) and draft.get("transcript", "").strip():
            intervals.append((draft["start_sample"], draft["end_sample"], False))
        for start, end, labelled in intervals:
            first = max(0, int(start) // RATE)
            last = min(self.bucket_count, math.ceil(int(end) / RATE))
            for bucket in range(first, last):
                if int(start) >= min(int(end), (bucket + 1) * RATE) or int(end) <= bucket * RATE:
                    continue
                spoken_end = min(self.duration, bucket + 1)
                delay = round(max(0.0, elapsed - spoken_end), 3)
                if self.words[bucket] is None:
                    self.words[bucket] = delay
                if labelled and self.labels[bucket] is None:
                    self.labels[bucket] = delay
        live_boundaries = {
            int(row["start_sample"])
            for row in segments if 0 < int(row["start_sample"]) < round(self.duration * RATE)
        }
        visible_labels = {row.get("canonical_speaker") for row in segments
                          if row.get("canonical_speaker") is not None and row.get("text", "").strip()}
        point = {"elapsed_seconds": round(elapsed, 3),
                 "distinct_labels": len(visible_labels),
                 "visible_slice_boundaries_per_minute": round(len(live_boundaries) * 60 / self.duration, 3)}
        if not self.timeline or point["distinct_labels"] != self.timeline[-1]["distinct_labels"] or point["visible_slice_boundaries_per_minute"] != self.timeline[-1]["visible_slice_boundaries_per_minute"]:
            self.timeline.append(point)

    def result(self) -> dict:
        def summary(values: list[float | None]) -> dict:
            observed = [v for v in values if v is not None]
            return {"buckets": self.bucket_count, "observed": len(observed),
                    "unobserved": self.bucket_count - len(observed),
                    "p50_seconds": percentile(observed, .5),
                    "p90_seconds": percentile(observed, .9)}
        return {"paced": True, "poll_interval_seconds": .25, "snapshots": self.snapshots,
                "duration_seconds": self.duration, "words": summary(self.words),
                "labelled_rows": summary(self.labels), "distinct_labels_over_time": self.timeline}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(args.run_dir.glob("pass-*/*/latency.json"))
    rows = [json.loads(path.read_text()) for path in paths]
    print(json.dumps({"runs": len(rows),
                      "per_run": [{"pass": path.parent.parent.name, "case_id": path.parent.name,
                                   "words": row["words"], "labelled_rows": row["labelled_rows"],
                                   "snapshots": row["snapshots"],
                                   "distinct_labels_over_time": row["distinct_labels_over_time"]}
                                  for path, row in zip(paths, rows)],
                      "words": {"observed": sum(r["words"]["observed"] for r in rows),
                                "unobserved": sum(r["words"]["unobserved"] for r in rows)},
                      "labelled_rows": {"observed": sum(r["labelled_rows"]["observed"] for r in rows),
                                        "unobserved": sum(r["labelled_rows"]["unobserved"] for r in rows)}}, indent=2))


if __name__ == "__main__":
    main()
