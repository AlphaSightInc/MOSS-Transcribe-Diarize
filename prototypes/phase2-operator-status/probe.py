"""Run the measured operator policy through the absorbed production reducer."""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize.app.live_lane_contract import LiveLane
from moss_transcribe_diarize.app.phase2_operator import (
    OPERATOR_JOURNAL_LIMIT,
    Phase2OperatorStatus,
)


FORBIDDEN = (
    "google-sub-sentinel",
    "meeting-title-sentinel",
    "transcript-sentinel",
    "/private/audio/sentinel.mp3",
    "https://source.invalid/sentinel",
    "session-secret-sentinel",
    "voiceprint-vector-sentinel",
    "prompt-sentinel",
    "summary-sentinel",
)
FIXED_NOW = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
REQUIRED_TRANSITION_CODES = (
    "account_authority_changed",
    "active_meetings_changed",
    "queue_depth_changed",
    "capture_health_changed",
)


class Store:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {
            "accounts": [],
            "active_meetings": [],
            "audio": [],
            "_forbidden_source": list(FORBIDDEN),
        }

    async def operator_snapshot(self) -> dict[str, object]:
        return deepcopy(self.payload)


class Live:
    def __init__(self) -> None:
        self.runtime = SimpleNamespace(
            descriptor=SimpleNamespace(frame_samples=160, sample_rate=16000)
        )
        self.queues: dict[str, int | bool] = {
            "batch": 0,
            "live_canonical": 0,
            "live_refinement": 0,
            "live_provisional": 0,
            "worker_busy": False,
        }
        self.meetings: dict[str, dict[str, object]] = {}

    def operator_snapshot(self) -> dict[str, object]:
        return {
            "queues": dict(self.queues),
            "meetings": deepcopy(self.meetings),
            "_forbidden_source": list(FORBIDDEN),
        }


class Files:
    def operator_snapshot(self) -> dict[str, str]:
        return {}


class Presence:
    def snapshot(self, meeting_id: str) -> object:
        del meeting_id
        return SimpleNamespace(
            state="capturing",
            lanes={
                lane.value: SimpleNamespace(state="capturing", failure_code=None)
                for lane in LiveLane
            },
        )


class V2Sessions:
    def __init__(self) -> None:
        self.health = {lane: "active" for lane in LiveLane}

    def get(self, meeting_id: str) -> "V2Sessions":
        del meeting_id
        return self

    def snapshot(self) -> object:
        return SimpleNamespace(
            status="active",
            lanes={
                lane: SimpleNamespace(
                    health=health,
                    accepted_samples=160,
                    failure_code=("browser_track_ended" if health == "failed" else None),
                )
                for lane, health in self.health.items()
            },
        )


class Journal:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def info(self, line: str) -> None:
        self.lines.append(line)


def _active_payload() -> dict[str, object]:
    return {
        "accounts": [
            {
                "email": "person@example.com",
                "display_name": "Person",
                "enabled": 1,
                "sign_in_sessions": 1,
                "active_live": 1,
                "active_file": 0,
                "meetings": 1,
                "transcripts": 0,
                "voiceprints": 0,
                "final_summaries": 0,
                "audio_available_count": 0,
                "audio_available_bytes": 0,
                "audio_partial_count": 0,
                "audio_partial_bytes": 0,
                "audio_unavailable_count": 0,
                "google_sub": FORBIDDEN[0],
                "session_secret": FORBIDDEN[5],
                "voiceprint_vector": FORBIDDEN[6],
                "prompt": FORBIDDEN[7],
                "summary": FORBIDDEN[8],
            }
        ],
        "active_meetings": [
            {
                "email": "person@example.com",
                "meeting_id": "opaque-meeting-id",
                "mode": "live",
                "status": "active",
                "created_at_ms": int(FIXED_NOW.timestamp() * 1000),
                "title": FORBIDDEN[1],
                "transcript": FORBIDDEN[2],
                "audio_path": FORBIDDEN[3],
                "source_url": FORBIDDEN[4],
            }
        ],
        "audio": [],
        "_forbidden_source": list(FORBIDDEN),
    }


async def exercise(*, suppress_event_code: str | None = None) -> dict[str, object]:
    store = Store()
    live = Live()
    presence = Presence()
    v2_sessions = V2Sessions()
    journal = Journal()
    operator = Phase2OperatorStatus(
        store,
        database_path=Path("/tmp/moss-operator-probe.sqlite3"),
        audio_root=Path("/tmp/moss-operator-probe-audio"),
        live=live,
        files=Files(),
        v2_sessions=v2_sessions,
        helper_presence=presence,
        now=lambda: FIXED_NOW,
        monotonic_ns=lambda: 1_000_000_000,
        journal_logger=journal,
    )
    await operator.start()
    baseline = await operator.snapshot()
    baseline_codes = [json.loads(line)["code"] for line in journal.lines]
    before_duplicate = len(journal.lines)
    duplicate = await operator.snapshot()
    duplicate_count = len(journal.lines) - before_duplicate

    store.payload = _active_payload()
    live.queues["live_canonical"] = 1
    live.meetings["opaque-meeting-id"] = {
        "session_status": "active",
        "pending_canonical": 1,
        "pending_limit": 4,
        "persistence_failure": None,
        "terminal_error": None,
    }
    before_change = len(journal.lines)
    changed = await operator.snapshot()
    transition_codes = [
        json.loads(line)["code"] for line in journal.lines[before_change:]
    ]

    before_lane_change = len(journal.lines)
    v2_sessions.health[LiveLane.MICROPHONE] = "failed"
    lane_changed = await operator.snapshot()
    lane_transition_codes = [
        json.loads(line)["code"] for line in journal.lines[before_lane_change:]
    ]

    restarted_journal = Journal()
    restarted = Phase2OperatorStatus(
        store,
        database_path=Path("/tmp/moss-operator-probe.sqlite3"),
        audio_root=Path("/tmp/moss-operator-probe-audio"),
        live=live,
        files=Files(),
        v2_sessions=v2_sessions,
        helper_presence=presence,
        now=lambda: FIXED_NOW,
        monotonic_ns=lambda: 1_000_000_000,
        journal_logger=restarted_journal,
    )
    await restarted.start()
    restart = await restarted.snapshot()
    restart_codes = [json.loads(line)["code"] for line in restarted_journal.lines]

    for index in range(OPERATOR_JOURNAL_LIMIT + 20):
        live.queues["live_canonical"] = index % 2
        await restarted.snapshot()
    recent = list(restarted._recent_events)

    live.meetings["opaque-meeting-id"]["persistence_failure"] = (
        "Account revoked by operator"
    )
    try:
        failed_revoke = await operator.snapshot()
        failed_revoke_outcome: dict[str, object] = {
            "status_available": True,
            "latest_error": failed_revoke["latest_error"],
        }
    except Exception as exc:
        failed_revoke_outcome = {
            "status_available": False,
            "exception_type": type(exc).__name__,
        }
    live.meetings["opaque-meeting-id"]["persistence_failure"] = None

    terminal_operator = Phase2OperatorStatus(
        store,
        database_path=Path("/tmp/moss-operator-probe.sqlite3"),
        audio_root=Path("/tmp/moss-operator-probe-audio"),
        live=live,
        files=Files(),
        v2_sessions=v2_sessions,
        helper_presence=presence,
        now=lambda: FIXED_NOW,
        monotonic_ns=lambda: 1_000_000_000,
        journal_logger=Journal(),
    )
    await terminal_operator.start()
    live.meetings["opaque-meeting-id"]["terminal_error"] = {
        "subsystem": "live",
        "code": "RuntimeError",
        "severity": "error",
        "terminal": True,
        "retryable": False,
    }
    try:
        generic_terminal = await terminal_operator.snapshot()
        generic_terminal_outcome: dict[str, object] = {
            "status_available": True,
            "latest_error": generic_terminal["latest_error"],
        }
    except Exception as exc:
        generic_terminal_outcome = {
            "status_available": False,
            "exception_type": type(exc).__name__,
        }
    live.meetings["opaque-meeting-id"]["terminal_error"] = None

    shutdown_journal = Journal()
    shutdown_operator = Phase2OperatorStatus(
        store,
        database_path=Path("/tmp/moss-operator-probe.sqlite3"),
        audio_root=Path("/tmp/moss-operator-probe-audio"),
        live=live,
        files=Files(),
        v2_sessions=v2_sessions,
        helper_presence=presence,
        now=lambda: FIXED_NOW,
        monotonic_ns=lambda: 1_000_000_000,
        journal_logger=shutdown_journal,
    )
    await shutdown_operator.start()
    shutdown_trace: list[str] = []

    async def settle_live_owner() -> None:
        shutdown_trace.append("live_settlement_started")
        live.meetings["opaque-meeting-id"]["persistence_failure"] = "service shutdown"
        shutdown_trace.append("live_settlement_finished")

    try:
        await settle_live_owner()
        await shutdown_operator.stop()
        shutdown_trace.append("operator_stopped")
        shutdown_snapshot = await shutdown_operator.snapshot()
        shutdown_outcome: dict[str, object] = {
            "status_available": True,
            "readiness": shutdown_snapshot["readiness"],
            "latest_error": shutdown_snapshot["latest_error"],
            "trace": shutdown_trace,
        }
    except Exception as exc:
        shutdown_outcome = {
            "status_available": False,
            "exception_type": type(exc).__name__,
        }
    live.meetings["opaque-meeting-id"]["persistence_failure"] = None
    source_text = json.dumps(
        {"store": store.payload, "live": live.operator_snapshot()}, sort_keys=True
    )
    status_text = json.dumps(changed, sort_keys=True)
    emitted_events = [
        json.loads(line)
        for line in journal.lines + restarted_journal.lines + shutdown_journal.lines
    ]
    journal_text = json.dumps(emitted_events, sort_keys=True)
    max_event_bytes = max(
        len(json.dumps(event, sort_keys=True).encode("utf-8"))
        for event in emitted_events
    )
    measured_transition_codes = transition_codes + lane_transition_codes
    gated_transition_codes = [
        code for code in measured_transition_codes if code != suppress_event_code
    ]
    measurements = {
        "baseline_event_codes": baseline_codes,
        "duplicate_event_count": duplicate_count,
        "transition_event_codes": transition_codes,
        "lane_health_transition_codes": lane_transition_codes,
        "required_transition_codes": list(REQUIRED_TRANSITION_CODES),
        "gated_transition_codes": gated_transition_codes,
        "suppressed_event_code": suppress_event_code,
        "restart_event_codes": restart_codes,
        "retained_event_count": len(recent),
        "journal_limit": OPERATOR_JOURNAL_LIMIT,
        "max_event_bytes": max_event_bytes,
        "bounded_event_bytes_upper": OPERATOR_JOURNAL_LIMIT * max_event_bytes,
        "forbidden_in_status": [value for value in FORBIDDEN if value in status_text],
        "forbidden_in_journal": [value for value in FORBIDDEN if value in journal_text],
        "forbidden_missing_from_sources": [
            value for value in FORBIDDEN if value not in source_text
        ],
        "failed_revoke": failed_revoke_outcome,
        "generic_terminal": generic_terminal_outcome,
        "shutdown": shutdown_outcome,
    }
    passed = (
        measurements["baseline_event_codes"] == ["service_ready"]
        and measurements["duplicate_event_count"] == 0
        and all(
            code in measurements["gated_transition_codes"]
            for code in REQUIRED_TRANSITION_CODES
        )
        and "capture_health_changed" in measurements["lane_health_transition_codes"]
        and measurements["restart_event_codes"] == ["service_ready"]
        and measurements["retained_event_count"] == OPERATOR_JOURNAL_LIMIT
        and measurements["failed_revoke"].get("status_available") is True
        and measurements["failed_revoke"]["latest_error"]["code"]
        == "meeting_authority_revoked"
        and measurements["generic_terminal"].get("status_available") is True
        and measurements["generic_terminal"]["latest_error"]["code"]
        == "live_terminal_failure"
        and measurements["shutdown"].get("status_available") is True
        and measurements["shutdown"].get("readiness") == "stopping"
        and measurements["shutdown"]["latest_error"]["code"] == "service_shutdown"
        and measurements["shutdown"]["trace"]
        == ["live_settlement_started", "live_settlement_finished", "operator_stopped"]
        and not measurements["forbidden_missing_from_sources"]
        and not measurements["forbidden_in_status"]
        and not measurements["forbidden_in_journal"]
    )
    return {
        "structural_question": (
            "Can every reachable lifecycle failure and transient lane-health change remain "
            "truthfully observable through one bounded content-free status surface?"
        ),
        "minimum_primitives": [
            "authoritative current snapshot",
            "one exact allowlisted projection",
            "canonical lifecycle-error token reducer",
            "aggregate phase and lane-health transition edge",
            "bounded in-memory recent-event buffer",
        ],
        "invariants": [
            "forbidden content and identifiers never cross projection or journal",
            "unchanged observations produce no event",
            "same-phase lane-health changes produce a capture-health edge",
            "lifecycle prose is reduced to stable safe-error tokens",
            "restart emits readiness only and invents no historical lifecycle",
            "recent event memory remains fixed",
        ],
        "assumptions_unknowns": [
            "external service-log retention is operator policy, not product state",
            "64 recent edges are diagnostic memory only and do not alter emitted events",
            "future safe lane-health tokens reduce to the explicit unknown aggregate",
            "unsupported persistence prose reduces to live_persistence_failed",
        ],
        "falsifier": (
            "a sentinel leaks, a claimed transition family is absent, lifecycle prose makes "
            "status unavailable, restart fabricates lifecycle, or retained edges exceed the cap"
        ),
        "tool_decision": (
            "the production OperatorStatus reducer plus independent verdict suppression is "
            "required because safe-error reduction, same-phase lane transitions, exclusion, "
            "deduplication, restart baseline, and the memory bound are the policies under test"
        ),
        "full_state": {
            "baseline": baseline,
            "duplicate": duplicate,
            "changed": changed,
            "lane_changed": lane_changed,
            "restart": restart,
            "recent_events": recent,
        },
        "measurements": measurements,
        "verdict": "PASS" if passed else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suppress-event-code",
        choices=REQUIRED_TRANSITION_CODES,
        help="Falsifier: remove one required family from the verdict input.",
    )
    args = parser.parse_args()
    result = asyncio.run(exercise(suppress_event_code=args.suppress_event_code))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
