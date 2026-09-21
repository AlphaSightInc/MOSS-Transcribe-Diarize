#!/usr/bin/env python3
"""R4 summary-only row: two File Meetings, six provider trials, owned counters."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.qualify.decoder import read_events, summarize_events

PYTHON = sys.executable
CLIP_SECONDS = (50, 180)
TRANSCRIPTS = 2
PROVIDER_TRIALS = 3
PROVIDER_CALLS_ALREADY_SPENT = 2
PROVIDER_CALL_CAP = 10


@dataclass(frozen=True, slots=True)
class ProxyCounters:
    accepted: int = 0
    completed: int = 0
    upstream_failed: int = 0
    rejected: int = 0
    active: int = 0
    peak_in_flight: int = 0
    event_count: int = 0
    row_attempted: int = 0
    row_completed: int = 0
    row_upstream_failed: int = 0
    row_rejected: int = 0
    distinct_request_ids: int = 0
    distinct_completed_request_ids: int = 0
    duplicate_attempts: int = 0
    unowned_events: int = 0
    missing_request_ids: int = 0
    wrong_row_events: int = 0
    row_owners: tuple[str, ...] = ()
    row_reconciled: bool = True


def proxy_counters(path: Path, *, peak_since: int = 0) -> ProxyCounters:
    events = read_events(path)
    cumulative = summarize_events(events)
    row = summarize_events(events[peak_since:], expected_row="summaries")
    return ProxyCounters(
        accepted=cumulative.attempted,
        completed=cumulative.completed,
        upstream_failed=cumulative.upstream_failed,
        rejected=cumulative.rejected,
        active=cumulative.active,
        peak_in_flight=row.peak_in_flight,
        event_count=cumulative.event_count,
        row_attempted=row.attempted,
        row_completed=row.completed,
        row_upstream_failed=row.upstream_failed,
        row_rejected=row.rejected,
        distinct_request_ids=row.distinct_request_ids,
        distinct_completed_request_ids=row.distinct_completed_request_ids,
        duplicate_attempts=row.duplicate_attempts,
        unowned_events=row.unowned_events,
        missing_request_ids=row.missing_request_ids,
        wrong_row_events=row.wrong_row_events,
        row_owners=row.row_owners,
        row_reconciled=row.reconciled,
    )


def summary_plan() -> dict[str, object]:
    from moss_transcribe_diarize.app.windowed_transcription import plan_windows
    from tools.qualify.run import request_plan

    merged = request_plan(False)
    window_seconds = float(merged["population"]["window_seconds"])
    stride_seconds = float(merged["population"]["stride_seconds"])
    clips = []
    for seconds in CLIP_SECONDS:
        windows = plan_windows(
            seconds,
            window_seconds=window_seconds,
            stride_seconds=stride_seconds,
        )
        clips.append(
            {
                "seconds": seconds,
                "meetings": 1,
                "windows": [
                    {"index": window.index, "start": window.start, "end": window.end}
                    for window in windows
                ],
                "planned_decoder": len(windows),
            }
        )
    planned_decoder = sum(int(clip["planned_decoder"]) for clip in clips)
    planned_provider = TRANSCRIPTS * PROVIDER_TRIALS
    cumulative_provider = PROVIDER_CALLS_ALREADY_SPENT + planned_provider
    assert planned_decoder == 3
    assert planned_provider == 6
    assert cumulative_provider == 8 <= PROVIDER_CALL_CAP
    return {
        "schema": "moss-r4-summary-row.v1",
        "mode": "PLAN_ONLY",
        "clips": clips,
        "window_seconds": window_seconds,
        "stride_seconds": stride_seconds,
        "meeting_reuse": "each File Meeting is transcribed once and reused for all trials",
        "planned_decoder": planned_decoder,
        "planned_provider": planned_provider,
        "provider_cap": {
            "already_spent": PROVIDER_CALLS_ALREADY_SPENT,
            "this_row": planned_provider,
            "cumulative": cumulative_provider,
            "cap": PROVIDER_CALL_CAP,
        },
        "capacity_2x1800": "REQUIRED-NOT-RUN",
        "mismatch_status": "INCOMPLETE",
        "actual_calls": {"decoder": 0, "provider": 0},
    }


def decoder_accounting(
    before: ProxyCounters,
    after: ProxyCounters,
    *,
    planned_decoder: int,
) -> tuple[dict[str, object], bool]:
    receipt = {
        "decoder_proxy_counter_deltas": {
            "accepted": after.accepted - before.accepted,
            "completed": after.completed - before.completed,
            "upstream_failed": after.upstream_failed - before.upstream_failed,
            "rejected": after.rejected - before.rejected,
            "peak_in_flight": after.peak_in_flight,
            "distinct_request_ids": after.distinct_request_ids,
            "distinct_completed_request_ids": after.distinct_completed_request_ids,
            "duplicate_attempts": after.duplicate_attempts,
            "unowned_events": after.unowned_events,
            "missing_request_ids": after.missing_request_ids,
            "wrong_row_events": after.wrong_row_events,
            "row_owners": list(after.row_owners),
            "reconciled": after.row_reconciled,
        }
    }
    delta = receipt["decoder_proxy_counter_deltas"]
    matches = (
        delta["accepted"] == planned_decoder
        and delta["completed"] == planned_decoder
        and delta["upstream_failed"] == 0
        and delta["rejected"] == 0
        and after.row_attempted == delta["accepted"]
        and after.row_completed == delta["completed"]
        and after.row_upstream_failed == 0
        and after.row_rejected == 0
        and delta["distinct_request_ids"] == planned_decoder
        and delta["distinct_completed_request_ids"] == planned_decoder
        and delta["duplicate_attempts"] == 0
        and delta["unowned_events"] == 0
        and delta["missing_request_ids"] == 0
        and delta["wrong_row_events"] == 0
        and delta["row_owners"] == ["summaries"]
        and delta["reconciled"] is True
        and int(delta["peak_in_flight"]) <= 2
    )
    return receipt, matches


def execute(args: argparse.Namespace, plan: dict[str, object]) -> tuple[dict[str, object], int]:
    missing = []
    if not args.allow_decoder:
        missing.append("--allow-decoder")
    if not args.allow_provider:
        missing.append("--allow-provider")
    if not args.base:
        missing.append("--base")
    if args.decoder_proxy_log is None:
        missing.append("--decoder-proxy-log")
    if not os.environ.get("OPENROUTER_API_KEY"):
        missing.append("exported OPENROUTER_API_KEY")
    if missing:
        return {
            **plan,
            "mode": "EXECUTION_REFUSED",
            "status": "INCOMPLETE",
            "reason": "Missing explicit row authority: " + ", ".join(missing),
        }, 2

    before = proxy_counters(args.decoder_proxy_log)
    environment = dict(
        os.environ,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=".",
        MOSS_BASE=args.base,
        MOSS_SUMMARY_PROVIDERS="external",
        TRIALS=str(PROVIDER_TRIALS),
    )
    started = time.monotonic()
    completed = subprocess.run(
        [PYTHON, "tests/e2e/verify_summaries.py"],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=1800,
    )
    after = proxy_counters(args.decoder_proxy_log, peak_since=before.event_count)
    accounting, decoder_matches = decoder_accounting(
        before,
        after,
        planned_decoder=int(plan["planned_decoder"]),
    )
    provider_attempts = len(
        re.findall(r"^\s*(?:PASS|FAIL)\s+", completed.stdout, flags=re.MULTILINE)
    )
    population_complete = provider_attempts == int(plan["planned_provider"])
    if not decoder_matches or not population_complete:
        status = "INCOMPLETE"
    else:
        status = "PASS" if completed.returncode == 0 else "FAIL"
    receipt = {
        **plan,
        "mode": "EXECUTED",
        "status": status,
        **accounting,
        "proxy_before": asdict(before),
        "proxy_after": asdict(after),
        "provider_attempts": provider_attempts,
        "actual_calls": {
            "decoder": accounting["decoder_proxy_counter_deltas"][
                "distinct_completed_request_ids"
            ],
            "provider": provider_attempts,
        },
        "command_exit": completed.returncode,
        "seconds": round(time.monotonic() - started, 3),
    }
    if status == "INCOMPLETE":
        receipt["reason"] = "Decoder counters or provider population did not match the plan."
    return receipt, 0 if status == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--decoder-proxy-log", type=Path)
    parser.add_argument("--allow-decoder", action="store_true")
    parser.add_argument("--allow-provider", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if args.base:
        parsed = urlsplit(args.base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            parser.error("--base must be an HTTP(S) origin")
        args.base = args.base.rstrip("/")
    plan = summary_plan()
    if args.plan_only:
        receipt, code = plan, 0
    else:
        receipt, code = execute(args, plan)
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
