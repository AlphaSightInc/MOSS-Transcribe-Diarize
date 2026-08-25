#!/usr/bin/env python3
"""Does the rolling witness tell its whole story on the event stream, and does it survive the wire?

Plan §10.5 step 5: "add snapshot/event serialization". Steps 1-4 built the rolling authority and
put it inside the real runtime, where -- until this change -- a stopped converger, a failed window
and an admission refusal were visible only in the process log and in a private counter. §10.6's
soak has to measure queue delay, stale/coalesced refinements and rolling correction latency from
*outside* the process, and §7.3's snapshot fields have to reach a portal and a replay trace
unchanged. Both are read here, on real audio, through the deployed configuration:

    audio frames -> LiveServiceRuntime.accept_frame -> ... -> LiveSession.apply_text_revision
      -> runtime.events(session_id) -> LiveServiceEvent.to_dict() -> json -> replay reconstruction
      -> snapshot().to_dict() -> json -> replay reconstruction

The driver is step 4's (`verify_runtime_rolling.run_case`, with `collect_events=True`), so the
runtime, the endpoint configuration, the real `webrtcvad`, the real arbiter and the replayed
decode seam are the same ones that verifier measured -- and the arm it lands on is re-checked
here, because an event that changed what is published would not be serialization.

Zero MOSS requests by construction (the decoder replays the §10.2 grid's recorded answers through
the production response validator). Reviewers can run this with no GPU:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \\
      prototypes/streaming-diarization/live-convergence/verify_rolling_events.py

Exit 0 iff every gate passes. Gates, fixed before the run:

- G1 every planned window is announced exactly once: `rolling_decode_queued` count equals the
  converger's `windows_planned`, window indices arrive in order from 0, item ids are unique,
  each announcement carries the window's extent and `window_samples` equals the geometry's.
- G2 every admitted window is closed exactly once: the `rolling_decode_completed` item-id set
  equals the admitted queued set, and every completion carries plan §7.4's required record --
  window samples, owned samples, queue delay, decode elapsed, generated tokens, cap status and
  RTF -- with no field missing on a window that decoded.
- G3 the revision events reconcile with the session itself: `text_revision_applied` count equals
  the snapshot's `text_revision_version`, `text_revision_refused` counts the refusals, and the
  last applied event's version and `canonical_through_sample` equal the snapshot's.
- G4 no event payload carries transcript text: every string value in a §7.4 payload is a
  snake_case name drawn from a vocabulary read out of the production sources (the refusal names
  in `LiveSession._text_revision_refusal`, `RollingStatus`, `LiveTranscriptDisposition`, the
  finalization statuses, the runtime's own outcome names).
- G5 the §7.3 snapshot fields survive the wire: `to_dict()` JSON round-trips, carries all four
  fields and the five §7.1 segment fields, and `live_service_replay` reconstructs a `LiveSnapshot`
  equal to the one the session produced.
- G6 the events survive the wire: every event JSON round-trips and `live_service_replay`
  reconstructs an equal `LiveServiceEvent`.
- G7 the arm is unchanged: per-case WER to 6 dp and the trio means `.131861` / `.943916`.
- G8 salvage is named where it happened and nowhere else: `decode_salvaged` count equals the
  number of `canonical_processed` events reporting the `salvaged` disposition. Reported rather
  than asserted positive: whether this instrument's recorded decodes reach the salvage gate at
  all is a property of the decode cache, and the positive control for the event lives in
  `tests/test_live_rolling_wiring.py`.
- G9 zero fresh MOSS requests.
"""

from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "prototypes/live-file-gap-context"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import proto_context_arms as bench  # noqa: E402
import verify_runtime_rolling as runtime_rolling  # noqa: E402
import verify_session_text_authority as authority  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import _jsonable  # noqa: E402
from moss_transcribe_diarize.app.live_session import LiveSession  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import LiveTranscriptDisposition  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
    RollingStatus,
)
from moss_transcribe_diarize.live_service_replay import (  # noqa: E402
    _event_from_dict,
    _live_snapshot_from_dict,
)

PLACES = authority.PLACES
SELECTED_ARM = authority.SELECTED_ARM
GRID = runtime_rolling.GRID

# The five §7.4 events this phase has a producer for. The three terminal ones are E4's and are
# deliberately absent: an event kind with no producer is a contract, not a serialization.
ROLLING_EVENT_KINDS = (
    "rolling_decode_queued",
    "rolling_decode_completed",
    "text_revision_applied",
    "text_revision_refused",
    "decode_salvaged",
)

# Plan §7.4: "Every completion event records window samples, owned samples, queue delay, decode
# elapsed time, generated tokens, cap status, and inference RTF when trustworthy."
COMPLETION_REQUIRED_FIELDS = (
    "window_samples",
    "owned_samples",
    "queue_wait_ms",
    "rolling_decode_elapsed_sec",
    "rolling_decode_generated_tokens",
    "rolling_decode_capped",
    "rolling_decode_token_cap",
    "rolling_decode_rtf",
)

SNAPSHOT_REQUIRED_FIELDS = (
    "text_revision_version",
    "canonical_through_sample",
    "effective_transcript",
    "finalization_status",
)

SEGMENT_REQUIRED_FIELDS = (
    "start_sample",
    "end_sample",
    "text",
    "canonical_speaker",
    "authority",
)

NAME_SHAPE = re.compile(r"^[a-z][a-z0-9_]*$")


def payload_vocabulary() -> set[str]:
    """Every name a §7.4 payload is allowed to carry, read out of the production sources.

    Read rather than listed so the gate cannot rot: a refusal name added to the session, a
    rolling status added to the converger or an outcome added to the refinement pump extends
    this set automatically, while a payload that started carrying a word somebody said does
    not. `_text_revision_refusal` and `_process_refinement_item` are parsed for their string
    literals because their names are returns and assignments, not an enum -- and an enum built
    only to satisfy this check would be scaffolding.
    """

    from moss_transcribe_diarize.app.live_service_runtime import LiveServiceRuntime

    names = {status.value for status in RollingStatus}
    names |= {item.value for item in LiveTranscriptDisposition}
    names |= {"not_started", "running", "final", "failed", "unavailable"}
    names |= {"rolling", "terminal"}
    names |= set(
        re.findall(r'return "([a-z0-9_]+)"', inspect.getsource(LiveSession._text_revision_refusal))
    )
    names |= set(
        re.findall(
            r'(?:outcome = |"|\')([a-z0-9_]+)(?:"|\')',
            inspect.getsource(LiveServiceRuntime._process_refinement_item),
        )
    )
    from moss_transcribe_diarize.app import live_coordinator

    names |= {live_coordinator.ROLLING_DECODE_DID_NOT_ANSWER, live_coordinator.ROLLING_DECODE_FAILED}
    return names


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for entry in value.values() for item in _strings(entry)]
    if isinstance(value, (list, tuple)):
        return [item for entry in value for item in _strings(entry)]
    return []


def check_case(case: str, arm: dict[str, Any], vocabulary: set[str]) -> tuple[dict[str, Any], list[str]]:
    """Read one case's event stream and snapshot against the nine gates."""

    failures: list[str] = []
    events = arm["events"]
    kinds = Counter(event["kind"] for event in events)
    snapshot = arm["service_snapshot"]["session"]
    rolling = arm["rolling"] or {}

    queued = [event for event in events if event["kind"] == "rolling_decode_queued"]
    completed = [event for event in events if event["kind"] == "rolling_decode_completed"]
    applied = [event for event in events if event["kind"] == "text_revision_applied"]
    refused = [event for event in events if event["kind"] == "text_revision_refused"]
    salvaged = [event for event in events if event["kind"] == "decode_salvaged"]

    # ---- G1: every planned window is announced exactly once, in order.
    planned = rolling.get("windows_planned")
    if len(queued) != planned:
        failures.append(f"G1 {case} announced {len(queued)} windows, converger planned {planned}")
    if [event["payload"]["window_index"] for event in queued] != list(range(len(queued))):
        failures.append(f"G1 {case} window indices are not 0..n in order")
    admitted = [event["payload"]["item_id"] for event in queued if event["payload"]["admitted"]]
    if len(set(admitted)) != len(admitted):
        failures.append(f"G1 {case} announced the same item id twice")
    for event in queued:
        payload = event["payload"]
        extent = payload["end_sample"] - payload["start_sample"]
        if payload["window_samples"] != extent:
            failures.append(f"G1 {case} window {payload['window_index']} extent disagrees with itself")
        if payload["window_samples"] != DEFAULT_ROLLING_GEOMETRY.window_samples:
            failures.append(
                f"G1 {case} window {payload['window_index']} is {payload['window_samples']} samples, "
                f"geometry is {DEFAULT_ROLLING_GEOMETRY.window_samples}"
            )

    # ---- G2: every admitted window is closed exactly once, with §7.4's completion record.
    closed = [event["payload"]["item_id"] for event in completed]
    if sorted(closed) != sorted(admitted):
        failures.append(f"G2 {case} closed {sorted(closed)} but admitted {sorted(admitted)}")
    if len(set(closed)) != len(closed):
        failures.append(f"G2 {case} closed the same window twice")
    for event in completed:
        payload = event["payload"]
        if payload["outcome"] != "applied":
            failures.append(f"G2 {case} window {payload['window_index']} ended {payload['outcome']}")
            continue
        missing = [field for field in COMPLETION_REQUIRED_FIELDS if payload.get(field) is None]
        if missing:
            failures.append(f"G2 {case} window {payload['window_index']} completion omits {missing}")
        if payload["queue_wait_ms"] < 0 or payload["queued_to_completed_ms"] < payload["queue_wait_ms"]:
            failures.append(f"G2 {case} window {payload['window_index']} has impossible timing")

    # ---- G3: the revision events reconcile with the session's own counters.
    if len(applied) != snapshot["text_revision_version"]:
        failures.append(
            f"G3 {case} {len(applied)} applied events vs text_revision_version "
            f"{snapshot['text_revision_version']}"
        )
    refusal_completions = [event for event in completed if event["payload"]["outcome"] == "refused"]
    if len(refused) != len(refusal_completions):
        failures.append(
            f"G3 {case} {len(refused)} refusal events vs {len(refusal_completions)} refused completions"
        )
    if applied:
        last = applied[-1]["payload"]
        if last["text_revision_version"] != snapshot["text_revision_version"]:
            failures.append(f"G3 {case} last applied event version != snapshot version")
        if last["canonical_through_sample"] != snapshot["canonical_through_sample"]:
            failures.append(f"G3 {case} last applied event frontier != snapshot frontier")

    # ---- G4: no payload carries transcript text.
    for event in events:
        if event["kind"] not in ROLLING_EVENT_KINDS:
            continue
        for value in _strings(event["payload"]):
            if not NAME_SHAPE.match(value):
                failures.append(f"G4 {case} {event['kind']} carries a non-name string {value!r}")
            elif value not in vocabulary:
                failures.append(f"G4 {case} {event['kind']} carries unknown name {value!r}")

    # ---- G5: the §7.3 snapshot fields survive the wire.
    for field in SNAPSHOT_REQUIRED_FIELDS:
        if field not in snapshot:
            failures.append(f"G5 {case} snapshot omits {field}")
    if json.loads(json.dumps(snapshot)) != snapshot:
        failures.append(f"G5 {case} snapshot does not survive a JSON round trip")
    for segment in snapshot.get("effective_transcript", []):
        missing = [field for field in SEGMENT_REQUIRED_FIELDS if field not in segment]
        if missing:
            failures.append(f"G5 {case} effective segment omits {missing}")
            break
    reconstructed = _live_snapshot_from_dict(json.loads(json.dumps(snapshot)))
    if _jsonable(asdict(reconstructed)) != snapshot:
        failures.append(f"G5 {case} replay reconstruction is not equal to the snapshot it read")

    # ---- G6: the events survive the wire.
    for event in events:
        if json.loads(json.dumps(event)) != event:
            failures.append(f"G6 {case} event {event['seq']} does not survive a JSON round trip")
            break
        rebuilt = _event_from_dict(json.loads(json.dumps(event)))
        if rebuilt.to_dict() != event:
            failures.append(f"G6 {case} event {event['seq']} does not reconstruct equal")
            break

    # ---- G8: salvage is named where it happened and nowhere else.
    salvage_spans = [
        event["payload"]["span_id"]
        for event in events
        if event["kind"] == "canonical_processed"
        and event["payload"].get("canonical_decode_salvage") == LiveTranscriptDisposition.SALVAGED.value
    ]
    if len(salvaged) != len(salvage_spans):
        failures.append(
            f"G8 {case} {len(salvaged)} decode_salvaged events vs {len(salvage_spans)} salvaged spans"
        )
    if [event["payload"]["span_id"] for event in salvaged] != salvage_spans:
        failures.append(f"G8 {case} decode_salvaged span ids do not match the salvaged spans")

    report = {
        "event_kinds": dict(kinds),
        "windows_announced": len(queued),
        "windows_admitted": len(admitted),
        "windows_closed": len(completed),
        "text_revisions_applied": len(applied),
        "text_revisions_refused": len(refused),
        "decode_salvaged": len(salvaged),
        "salvaged_spans": salvage_spans,
        "text_revision_version": snapshot["text_revision_version"],
        "canonical_through_sample": snapshot["canonical_through_sample"],
        "finalization_status": snapshot["finalization_status"],
        "effective_segments": len(snapshot["effective_transcript"]),
        "completion_queue_wait_ms": [event["payload"]["queue_wait_ms"] for event in completed],
        "completion_rtf": [event["payload"]["rolling_decode_rtf"] for event in completed],
        "completion_generated_tokens": [
            event["payload"]["rolling_decode_generated_tokens"] for event in completed
        ],
        "rolling_status_on_last_commit": next(
            (
                event["payload"].get("rolling_status")
                for event in reversed(events)
                if event["kind"] == "canonical_processed"
            ),
            None,
        ),
    }
    return report, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=",".join(bench.CASES))
    parser.add_argument("--grid", type=Path, default=GRID / "grid.json")
    parser.add_argument("--cache", type=Path, default=GRID / "decode-cache/run0.json")
    parser.add_argument("--output", type=Path, default=None)
    cli = parser.parse_args()

    names = [item for item in cli.cases.split(",") if item]
    grid = json.loads(cli.grid.read_text(encoding="utf-8"))
    expected = grid["summary"]["arms"][SELECTED_ARM]
    config = runtime_rolling.deployed_configuration()
    runner = runtime_rolling.ReplayRunner(runtime_rolling.load_replay_entries(cli.cache, names))
    vocabulary = payload_vocabulary()

    document: dict[str, Any] = {
        "schema": "moss-live-convergence-rolling-events.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "modules": [
            "moss_transcribe_diarize/app/live_coordinator.py",
            "moss_transcribe_diarize/app/live_service_runtime.py",
        ],
        "grid": {"path": str(cli.grid.relative_to(REPO)), "arm": SELECTED_ARM},
        "payload_vocabulary": sorted(vocabulary),
        "cases": {},
    }
    failures: list[str] = []

    def close(actual: float, want: float) -> bool:
        return round(float(actual), PLACES) == round(float(want), PLACES)

    for case in names:
        arm = runtime_rolling.run_case(config, runner, case, rolling=True, collect_events=True)
        report, case_failures = check_case(case, arm, vocabulary)
        report["wer"] = arm["scores"]["wer"]
        report["content_recall"] = arm["scores"]["content_recall"]
        if not close(arm["scores"]["wer"], expected["per_case"][case]["wer_mean"]):
            case_failures.append(
                f"G7 {case} wer {arm['scores']['wer']:.6f} != grid "
                f"{expected['per_case'][case]['wer_mean']:.6f}"
            )
        document["cases"][case] = report
        failures.extend(case_failures)

    mean_wer = sum(document["cases"][case]["wer"] for case in names) / len(names)
    mean_recall = sum(document["cases"][case]["content_recall"] for case in names) / len(names)
    document["trio"] = {"wer_mean": mean_wer, "content_recall_mean": mean_recall}
    if len(names) == len(bench.CASES):
        if not close(mean_wer, expected["wer"]["mean"]):
            failures.append(f"G7 trio wer {mean_wer:.6f} != grid {expected['wer']['mean']:.6f}")
        if not close(mean_recall, expected["content_recall"]["mean"]):
            failures.append(
                f"G7 trio recall {mean_recall:.6f} != grid {expected['content_recall']['mean']:.6f}"
            )

    document["decode_cost"] = {"requests": runner.requests, "fresh_requests": runner.fresh_requests}
    if runner.fresh_requests:
        failures.append(f"G9 {runner.fresh_requests} fresh MOSS requests")

    document["failures"] = failures
    document["passed"] = not failures

    for case in names:
        report = document["cases"][case]
        print(
            f"{case:<18} queued={report['windows_announced']} closed={report['windows_closed']} "
            f"applied={report['text_revisions_applied']} refused={report['text_revisions_refused']} "
            f"salvaged={report['decode_salvaged']} "
            f"frontier={report['canonical_through_sample']} "
            f"segments={report['effective_segments']} wer={report['wer']:.6f}"
        )
    print(
        f"{'TRIO':<18} wer={mean_wer:.6f} (grid {expected['wer']['mean']:.6f}) "
        f"recall={mean_recall:.6f} (grid {expected['content_recall']['mean']:.6f})"
    )
    print(f"payload vocabulary: {len(vocabulary)} names")
    print(f"decode cost: {document['decode_cost']}")
    if cli.output:
        cli.output.parent.mkdir(parents=True, exist_ok=True)
        cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for failure in failures:
        print(f"FAIL {failure}")
    print("PASS" if not failures else f"FAILED {len(failures)} gate(s)")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
