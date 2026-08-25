"""Where do two live replay runs of the same audio first disagree?

Two runs that hit the same service with the same PCM should agree. When they do not,
the useful question is not "how much" but "where first" -- the earliest differing
span is the root; everything after it is cascade. This walks both traces span by
span, excludes wall-clock fields (timings are never expected to match), and reports
the first divergence plus a per-field tally.

It also reports whether either trace was truncated by the service's `max_events`
ring buffer, because a truncated trace makes every span-level claim about the
missing prefix unfalsifiable.

  python diff_live_runs.py <trace-a.jsonl> <trace-b.jsonl> [--output out.json]

Exit 0 always -- this is a measurement, not a gate.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

# Wall-clock and queue-latency fields: expected to differ, never evidence of divergence.
TIMING_FIELDS = {
    "canonical_decode_elapsed_sec",
    "canonical_decode_rtf",
    "canonical_processing_elapsed_ms",
    "queue_wait_ms",
    "queued_to_processed_ms",
    "runtime_monotonic_ns",
}


def read_trace(path: Path) -> dict:
    spans: dict[int, dict] = {}
    canonical: dict[int, dict] = {}
    frames: list[int] = []
    kinds: collections.Counter = collections.Counter()
    terminal: dict | None = None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        if entry.get("kind") == "terminal":
            terminal = entry.get("snapshot")
            continue
        if entry.get("kind") != "service_event":
            continue
        event = entry["event"]
        payload = {k: v for k, v in (event.get("payload") or {}).items() if k not in TIMING_FIELDS}
        kind = event.get("kind")
        kinds[kind] += 1
        if kind == "span_frozen":
            spans[payload["span_id"]] = payload
        elif kind == "canonical_processed":
            canonical[payload["span_id"]] = payload
        elif kind == "frame_accepted":
            frames.append(payload.get("sequence"))
    return {
        "path": str(path),
        "kinds": dict(kinds),
        "event_count": sum(kinds.values()),
        "spans": spans,
        "canonical": canonical,
        "first_frame_sequence": min(frames) if frames else None,
        "last_frame_sequence": max(frames) if frames else None,
        "first_span_id": min(spans) if spans else None,
        "terminal_label_revision_version": ((terminal or {}).get("session") or {}).get("label_revision_version"),
    }


def compare(a: dict, b: dict) -> dict:
    span_ids = sorted(set(a["spans"]) | set(b["spans"]))
    bounds_identical = all(a["spans"].get(i) == b["spans"].get(i) for i in span_ids)

    field_tally: collections.Counter = collections.Counter()
    differing: list[dict] = []
    for span_id in sorted(set(a["canonical"]) | set(b["canonical"])):
        left, right = a["canonical"].get(span_id, {}), b["canonical"].get(span_id, {})
        if left == right:
            continue
        fields = sorted(k for k in set(left) | set(right) if left.get(k) != right.get(k))
        field_tally.update(fields)
        differing.append({"span_id": span_id, "fields": {k: [left.get(k), right.get(k)] for k in fields}})

    truncated = {
        side["path"]: {
            "event_count": side["event_count"],
            "first_frame_sequence": side["first_frame_sequence"],
            "first_span_id": side["first_span_id"],
            # The service holds events in a bounded deque; a stream that starts above
            # zero means the prefix was evicted before the client drained it.
            "prefix_evicted": bool(side["first_frame_sequence"]) or bool(side["first_span_id"]),
        }
        for side in (a, b)
    }
    return {
        "span_bounds_identical": bounds_identical,
        "span_count": [len(a["spans"]), len(b["spans"])],
        "canonical_spans_compared": len(set(a["canonical"]) | set(b["canonical"])),
        "canonical_spans_differing": len(differing),
        "earliest_differing_span": differing[0] if differing else None,
        "differing_field_tally": field_tally.most_common(),
        "terminal_label_revision_version": [
            a["terminal_label_revision_version"],
            b["terminal_label_revision_version"],
        ],
        "trace_truncation": truncated,
        "differing_spans": differing,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_a", type=Path)
    parser.add_argument("trace_b", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    a, b = read_trace(args.trace_a), read_trace(args.trace_b)
    report = compare(a, b)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    print(f"span bounds identical : {report['span_bounds_identical']}  (counts {report['span_count']})")
    print(f"spans compared        : {report['canonical_spans_compared']}")
    print(f"spans differing       : {report['canonical_spans_differing']}")
    print(f"terminal revisions    : {report['terminal_label_revision_version']}")
    earliest = report["earliest_differing_span"]
    print(f"earliest divergence   : {json.dumps(earliest) if earliest else 'none'}")
    print(f"field tally           : {report['differing_field_tally']}")
    for path, info in report["trace_truncation"].items():
        flag = "TRUNCATED" if info["prefix_evicted"] else "complete"
        print(f"trace {flag:9s}    : {path} events={info['event_count']} "
              f"first_frame={info['first_frame_sequence']} first_span={info['first_span_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
