#!/usr/bin/env python3
"""Preserve and classify the 2026-08-19 attended latency baseline.

One command (from the repository root):

    python3 prototypes/live-latency/preserve_baseline.py \
      --output evidence/phase1/g3-attended/live-latency-baseline-20260819.json

The three capture files and the sanitized canonical-event file are deliberately
inputs, not measurements recreated by this program.  The program prints the
entire evidence document it writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


DEFAULT_RUNS = (
    ("initial_short", Path("/tmp/moss-latency-baseline-raw.txt")),
    ("restart_lifecycle_fault", Path("/tmp/moss-latency-baseline-long-raw.txt")),
    ("fresh_app_relaunch", Path("/tmp/moss-latency-baseline-relaunch-raw.txt")),
)
DEFAULT_EVENTS = Path("/tmp/moss-latency-canonical-events-20260819.json")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def nearest_rank(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(fraction * len(ordered))
    return ordered[max(1, rank) - 1]


def distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "p50": nearest_rank(values, 0.50),
        "p95": nearest_rank(values, 0.95),
        "max": max(values) if values else None,
    }


def parse_capture(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    records: list[dict[str, Any]] = []
    timestamp: str | None = None
    for line_number, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("20") and stripped.endswith("Z"):
            timestamp = stripped
            records.append({"line": line_number, "timestamp": timestamp})
            continue
        if stripped.startswith("fixture_pass="):
            records.append(
                {
                    "line": line_number,
                    "timestamp": timestamp,
                    "fixture_pass": int(stripped.split("=", 1)[1]),
                }
            )
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            records.append({"line": line_number, "timestamp": timestamp, "text": stripped})
        else:
            records.append({"line": line_number, "timestamp": timestamp, "payload": payload})

    reports = [
        record["payload"]["latency"]
        for record in records
        if isinstance(record.get("payload"), dict)
        and isinstance(record["payload"].get("latency"), dict)
    ]
    final = reports[-1] if reports else None
    if final and final.get("sufficientSamples") is True:
        classification = "VALID_BASELINE"
    elif final and final.get("mixerOriginResolved") is False:
        classification = "LIFECYCLE_FAULT_NO_MIXER_ORIGIN"
    else:
        classification = "INSUFFICIENT_SAMPLE"
    return {
        "path": str(path),
        "sha256": sha256_bytes(raw),
        "classification": classification,
        "latency_report_count": len(reports),
        "final_latency_report": final,
        "raw_records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    runs = {name: parse_capture(path) for name, path in DEFAULT_RUNS}
    events_raw = args.events.read_bytes()
    events_payload = json.loads(events_raw)
    canonical = [
        item["payload"]
        for item in events_payload["events"]
        if item["kind"] == "canonical_processed"
    ]
    span_seconds = [float(item["frozen_span_duration_sec"]) for item in canonical]
    decode_seconds = [float(item["canonical_decode_elapsed_sec"]) for item in canonical]
    decode_rtf = [float(item["canonical_decode_rtf"]) for item in canonical]
    full_cap_count = sum(math.isclose(value, 2.5, abs_tol=1e-9) for value in span_seconds)
    capped_count = sum(bool(item["canonical_decode_capped"]) for item in canonical)

    valid = runs["fresh_app_relaunch"]["final_latency_report"]
    if not isinstance(valid, dict) or valid.get("sufficientSamples") is not True:
        raise SystemExit("fresh_app_relaunch is not a sufficient baseline")
    end_p95_ms = float(valid["committedLatency"]["p95MS"])
    render_bound_ms = float(valid["renderBoundMS"])
    span_p95_ms = float(nearest_rank(span_seconds, 0.95) or 0.0) * 1_000

    document = {
        "schema": "moss-live-latency-baseline.v1",
        "recorded_date": "2026-08-19",
        "question": "Where does the attended 3-5 second word-to-screen delay accrue before policy changes?",
        "scope": (
            "Diagnostic baseline only. No server/browser clock subtraction is made. "
            "The capture-to-fetch figures use the M4 capture clock; decode durations use "
            "the server clock; the served-reader term is an analytic bound, not an observed render."
        ),
        "attended_path": {
            "capture_host": "M4 MacBook Pro",
            "capture_app": "/Applications/MOSSCapture.app",
            "reader_route": "/live",
            "reader_implementation": "moss_transcribe_diarize/app/live_portal.py",
            "poll_cadence_ms": 500,
            "react_reader_active_for_this_path": False,
            "react_poller_cadence_ms": 250,
            "basis": "MOSSCapture's portal handoff appends /live to the paired server URL.",
        },
        "capture_runs": runs,
        "canonical_events": {
            "path": str(args.events),
            "sha256": sha256_bytes(events_raw),
            "sanitized_payload": events_payload,
            "processed_span_count": len(canonical),
            "span_duration_seconds": distribution(span_seconds),
            "full_2_5_second_span_count": full_cap_count,
            "full_2_5_second_span_fraction": full_cap_count / len(canonical),
            "decode_seconds": distribution(decode_seconds),
            "decode_rtf": distribution(decode_rtf),
            "decode_capped_count": capped_count,
        },
        "stage_budget": {
            "first_sample_to_span_end": {
                "status": "MEASURED_FROM_SPAN_BOUNDARIES",
                "p95_ms": span_p95_ms,
                "clock": "sample timeline",
            },
            "span_end_to_probe_fetch_observation": {
                "status": "MEASURED",
                "distribution_ms": valid["committedLatency"],
                "clock": "M4 capture host clock",
            },
            "queue_wait": {"status": "NOT_YET_INSTRUMENTED"},
            "decode": {
                "status": "MEASURED",
                "distribution_seconds": distribution(decode_seconds),
                "clock": "server monotonic duration",
            },
            "commit_to_fetch": {"status": "NOT_YET_SEPARATED_FROM_POST_SPAN_AGE"},
            "fetch_to_dom_render": {
                "status": "ANALYTIC_BOUND_ONLY",
                "p95_bound_ms": render_bound_ms,
                "components": {
                    "reader_poll_cadence_ms": valid["portalCycleMS"],
                    "paired_fetch_p95_ms": valid["portalFetchCycle"]["p95MS"],
                },
            },
            "last_sample_to_visible": {
                "status": "ANALYTIC_BOUND_ONLY",
                "p95_bound_ms": valid["userVisibleMS"],
            },
            "first_sample_to_visible": {
                "status": "ADDITIVE_P95_BOUND_ONLY",
                "p95_bound_ms": span_p95_ms + end_p95_ms + render_bound_ms,
                "warning": "Sum of component p95 values, not an observed end-to-end percentile.",
            },
        },
        "attribution": {
            "verdict": "SPAN_ACCUMULATION_PLUS_POST_SPAN_VISIBILITY_DOMINATE",
            "evidence": [
                f"{full_cap_count}/{len(canonical)} canonical spans ran to the 2.5 s hard cap.",
                f"Canonical decode p95 was {nearest_rank(decode_seconds, 0.95):.3f} s and max was {max(decode_seconds):.3f} s.",
                f"Paired fetch p95 was {valid['portalFetchCycle']['p95MS']:.3f} ms and max was {valid['portalFetchCycle']['maxMS']:.3f} ms.",
                f"Last-sample-to-visible analytic p95 bound was {valid['userVisibleMS']:.3f} ms.",
                f"First-sample-to-visible additive p95 bound was {span_p95_ms + end_p95_ms + render_bound_ms:.3f} ms.",
            ],
            "next_measurement": (
                "Add queue, commit-to-fetch, actual DOM-render, and start/end span ages before "
                "selecting a cap or silence policy."
            ),
        },
    }
    encoded = json.dumps(document, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
