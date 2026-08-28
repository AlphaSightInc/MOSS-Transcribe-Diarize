"""Run the measured operator policy through the absorbed production reducer."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

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


class Store:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {
            "accounts": [],
            "active_meetings": [],
            "audio": [],
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
        return {"queues": dict(self.queues), "meetings": deepcopy(self.meetings)}


class Files:
    def operator_snapshot(self) -> dict[str, str]:
        return {}


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
            }
        ],
        "active_meetings": [
            {
                "email": "person@example.com",
                "meeting_id": "opaque-meeting-id",
                "mode": "live",
                "status": "active",
                "created_at_ms": int(FIXED_NOW.timestamp() * 1000),
            }
        ],
        "audio": [],
    }


async def exercise() -> dict[str, object]:
    store = Store()
    live = Live()
    journal = Journal()
    operator = Phase2OperatorStatus(
        store,
        database_path=Path("/tmp/moss-operator-probe.sqlite3"),
        audio_root=Path("/tmp/moss-operator-probe-audio"),
        live=live,
        files=Files(),
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

    restarted_journal = Journal()
    restarted = Phase2OperatorStatus(
        store,
        database_path=Path("/tmp/moss-operator-probe.sqlite3"),
        audio_root=Path("/tmp/moss-operator-probe-audio"),
        live=live,
        files=Files(),
        now=lambda: FIXED_NOW,
        monotonic_ns=lambda: 1_000_000_000,
        journal_logger=restarted_journal,
    )
    await restarted.start()
    restart = await restarted.snapshot()
    restart_codes = [json.loads(line)["code"] for line in restarted_journal.lines]

    for index in range(OPERATOR_JOURNAL_LIMIT + 20):
        live.queues["live_canonical"] = index % 2
        await operator.snapshot()
    recent = list(operator._recent_events)
    status_text = json.dumps(changed, sort_keys=True)
    journal_text = json.dumps(recent, sort_keys=True)
    max_event_bytes = max(
        len(json.dumps(event, sort_keys=True).encode("utf-8")) for event in recent
    )
    measurements = {
        "baseline_event_codes": baseline_codes,
        "duplicate_event_count": duplicate_count,
        "transition_event_codes": transition_codes,
        "restart_event_codes": restart_codes,
        "retained_event_count": len(recent),
        "journal_limit": OPERATOR_JOURNAL_LIMIT,
        "max_event_bytes": max_event_bytes,
        "bounded_event_bytes_upper": OPERATOR_JOURNAL_LIMIT * max_event_bytes,
        "forbidden_in_status": [value for value in FORBIDDEN if value in status_text],
        "forbidden_in_journal": [value for value in FORBIDDEN if value in journal_text],
    }
    passed = (
        measurements["baseline_event_codes"] == ["service_ready"]
        and measurements["duplicate_event_count"] == 0
        and "active_meetings_changed" in measurements["transition_event_codes"]
        and "queue_depth_changed" in measurements["transition_event_codes"]
        and measurements["restart_event_codes"] == ["service_ready"]
        and measurements["retained_event_count"] == OPERATOR_JOURNAL_LIMIT
        and not measurements["forbidden_in_status"]
        and not measurements["forbidden_in_journal"]
    )
    return {
        "structural_question": (
            "Can one current-state projection and bounded aggregate edge reducer expose truthful "
            "operations without becoming a second content or Account-audit surface?"
        ),
        "minimum_primitives": [
            "authoritative current snapshot",
            "one exact allowlisted projection",
            "aggregate transition edge",
            "bounded in-memory recent-event buffer",
        ],
        "invariants": [
            "forbidden content and identifiers never cross projection or journal",
            "unchanged observations produce no event",
            "restart emits readiness only and invents no historical lifecycle",
            "recent event memory remains fixed",
        ],
        "assumptions_unknowns": [
            "external service-log retention is operator policy, not product state",
            "64 recent edges are diagnostic memory only and do not alter emitted events",
        ],
        "falsifier": (
            "a sentinel leaks, a no-op emits, restart fabricates lifecycle, or retained edges "
            "exceed the cap"
        ),
        "tool_decision": (
            "the production OperatorStatus reducer is required because deduplication, restart "
            "baseline, and the memory bound are the new policies under test"
        ),
        "full_state": {
            "baseline": baseline,
            "duplicate": duplicate,
            "changed": changed,
            "restart": restart,
            "recent_events": recent,
        },
        "measurements": measurements,
        "verdict": "PASS" if passed else "FAIL",
    }


def main() -> int:
    result = asyncio.run(exercise())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
