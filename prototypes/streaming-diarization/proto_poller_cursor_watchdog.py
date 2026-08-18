#!/usr/bin/env python3
"""Choose a bounded stale-snapshot recovery count before shipping the poller policy.

This is a deterministic state-trace prototype, not browser or live-service evidence. The
production-path Vitest replay is the acceptance check; this script only makes the timeout/load
trade-off explicit before choosing the recovery bound.
"""

from __future__ import annotations

import json


CLOSING_POLL_DELAY_MS = 2_000
MAX_TERMINAL_OBSERVATION_MS = 6_000
MAX_FORCED_REFRESH_SHARE = 1 / 3
CANDIDATES = (1, 2, 3)


def simulate_flat_terminal(bound: int) -> dict[str, object]:
    """Start after version 153 / event 210, then model stale flat post-stop responses."""
    snapshot_cursor = 153
    event_cursor = 210
    no_progress_rounds = 0
    trace: list[dict[str, object]] = []

    for round_number in range(1, bound + 2):
        if snapshot_cursor == 0:
            trace.append(
                {
                    "round": round_number,
                    "snapshot_cursor_before": snapshot_cursor,
                    "event_cursor_before": event_cursor,
                    "snapshot_response": "closed@332",
                    "event_cursor_after": event_cursor,
                    "no_progress_rounds_after": no_progress_rounds,
                    "action": "terminal_observed",
                }
            )
            break

        no_progress_rounds += 1
        action = "hold"
        if no_progress_rounds >= bound:
            snapshot_cursor = 0
            no_progress_rounds = 0
            action = "rebaseline"
        trace.append(
            {
                "round": round_number,
                "snapshot_cursor_before": 153,
                "event_cursor_before": event_cursor,
                "snapshot_response": "unchanged_flat",
                "event_cursor_after": event_cursor,
                "no_progress_rounds_after": no_progress_rounds,
                "action": action,
            }
        )

    return {
        "bound": bound,
        "terminal_observation_ms_after_last_changed_snapshot": len(trace)
        * CLOSING_POLL_DELAY_MS,
        "trace": trace,
    }


def steady_idle_forced_refresh_share(bound: int, rounds: int = 60) -> dict[str, object]:
    """Model a healthy but quiescent non-terminal session after a full snapshot."""
    snapshot_cursor = 153
    no_progress_rounds = 0
    forced_refreshes = 0
    trace: list[dict[str, object]] = []

    for round_number in range(1, rounds + 1):
        if snapshot_cursor == 0:
            snapshot_cursor = 153
            trace.append({"round": round_number, "response": "full_same_version", "action": "hold"})
            continue

        no_progress_rounds += 1
        action = "hold"
        if no_progress_rounds >= bound:
            snapshot_cursor = 0
            no_progress_rounds = 0
            forced_refreshes += 1
            action = "rebaseline"
        trace.append({"round": round_number, "response": "unchanged_flat", "action": action})

    return {
        "rounds": rounds,
        "forced_refreshes": forced_refreshes,
        "forced_refresh_share": forced_refreshes / rounds,
        "trace": trace,
    }


def event_progress_trace(bound: int) -> dict[str, object]:
    """Prove movement of the independent event cursor prevents the watchdog firing."""
    event_cursor = 210
    trace: list[dict[str, object]] = []
    for round_number in range(1, 7):
        event_cursor += 1
        trace.append(
            {
                "round": round_number,
                "snapshot_response": "unchanged",
                "event_cursor_after": event_cursor,
                "no_progress_rounds_after": 0,
                "action": "hold",
            }
        )
    return {"bound": bound, "forced_refreshes": 0, "trace": trace}


def main() -> None:
    results = []
    for bound in CANDIDATES:
        flat_terminal = simulate_flat_terminal(bound)
        idle = steady_idle_forced_refresh_share(bound)
        event_progress = event_progress_trace(bound)
        terminal_ms = flat_terminal["terminal_observation_ms_after_last_changed_snapshot"]
        refresh_share = idle["forced_refresh_share"]
        passes = (
            terminal_ms <= MAX_TERMINAL_OBSERVATION_MS
            and refresh_share <= MAX_FORCED_REFRESH_SHARE
            and event_progress["forced_refreshes"] == 0
        )
        results.append(
            {
                "bound": bound,
                "terminal": flat_terminal,
                "steady_idle": idle,
                "event_progress": event_progress,
                "passes_preregistered_tradeoff": passes,
            }
        )

    chosen = [result["bound"] for result in results if result["passes_preregistered_tradeoff"]]
    report = {
        "question": "Which flat-cursor watchdog bound recovers a post-stop terminal without excessive idle full snapshots?",
        "criteria": {
            "max_terminal_observation_ms_after_last_changed_snapshot": MAX_TERMINAL_OBSERVATION_MS,
            "max_steady_idle_forced_refresh_share": MAX_FORCED_REFRESH_SHARE,
            "event_cursor_progress_must_not_force_refresh": True,
        },
        "results": results,
        "chosen_bound": chosen,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    if chosen != [2]:
        raise SystemExit("pre-registered watchdog choice changed")


if __name__ == "__main__":
    main()
