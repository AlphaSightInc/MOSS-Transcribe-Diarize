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
    rejected: int = 0
    active: int = 0
    peak_in_flight: int = 0
    event_count: int = 0


def proxy_counters(path: Path, *, peak_since: int = 0) -> ProxyCounters:
    if not path.is_file():
        return ProxyCounters()
    events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    row_events = events[peak_since:]
    return ProxyCounters(
        accepted=sum(event.get("kind") == "start" for event in events),
        completed=sum(event.get("kind") == "end" for event in events),
        rejected=sum(event.get("kind") == "reject" for event in events),
        active=int(events[-1].get("active", 0)) if events else 0,
        peak_in_flight=max((int(event.get("active", 0)) for event in row_events), default=0),
        event_count=len(events),
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
            "rejected": after.rejected - before.rejected,
            "peak_in_flight": after.peak_in_flight,
        }
    }
    delta = receipt["decoder_proxy_counter_deltas"]
    matches = (
        delta["accepted"] == planned_decoder
        and delta["completed"] == planned_decoder
        and delta["rejected"] == 0
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
            "decoder": accounting["decoder_proxy_counter_deltas"]["accepted"],
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
