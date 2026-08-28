"""Content-free current-state projection behind the Phase-2 product control plane."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import sys
import time
from collections import Counter, deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from .live_capture_status import LiveCaptureHealthPolicy, project_live_capture_status
from .live_lane_contract import LiveLane


OPERATOR_STATUS_SCHEMA = "moss-operator-status.v1"
OPERATOR_EVENT_SCHEMA = "moss-operator-event.v1"
OPERATOR_JOURNAL_LIMIT = 64
LIVE_MEETING_LIMIT = 4
LOGGER = logging.getLogger("moss_transcribe_diarize.operator")

_STATUS_KEYS = frozenset(
    {
        "schema",
        "observed_at_utc",
        "readiness",
        "capacity",
        "live",
        "active",
        "limit",
        "file",
        "inference_worker",
        "queues",
        "live_canonical",
        "live_refinement",
        "live_provisional",
        "batch",
        "backpressured_meetings",
        "accounts",
        "email",
        "display_name",
        "enabled",
        "sign_in_sessions",
        "active_meetings",
        "audio",
        "available",
        "partial",
        "unavailable",
        "count",
        "bytes",
        "logical",
        "meetings",
        "transcripts",
        "voiceprints",
        "final_summaries",
        "meeting_id",
        "mode",
        "lifecycle",
        "started_at_utc",
        "elapsed_seconds",
        "safe_error",
        "capture",
        "phase",
        "lanes",
        "microphone",
        "system",
        "health",
        "age_seconds",
        "pending_canonical",
        "backpressure",
        "state",
        "storage",
        "filesystems",
        "sqlite_free_bytes",
        "audio_free_bytes",
        "sqlite",
        "database_bytes",
        "wal_bytes",
        "latest_error",
        "occurred_at_utc",
        "subsystem",
        "code",
        "severity",
        "terminal",
        "retryable",
        "occurrence_count",
        "context",
        "command",
    }
)
_EVENT_KEYS = frozenset(
    {
        "schema",
        "sequence",
        "occurred_at_utc",
        "kind",
        "code",
        "severity",
        "terminal",
        "retryable",
        "occurrence_count",
        "context",
        "state",
        "enabled_accounts",
        "sign_in_sessions",
        "active_live",
        "active_file",
        "live_canonical",
        "live_refinement",
        "live_provisional",
        "batch",
        "backpressured_meetings",
        "starting",
        "awaiting_audio",
        "recording",
        "stopped",
        "failed",
        "healthy_lanes",
        "degraded_lanes",
        "failed_lanes",
        "inactive_lanes",
        "unknown_lanes",
        "available_count",
        "available_bytes",
        "partial_count",
        "partial_bytes",
        "unavailable_count",
        "command",
        "outcome",
        "subsystem",
    }
)


class OperatorProjectionError(RuntimeError):
    pass


class Phase2OperatorStatus:
    """Compose existing owners into one exact, content-free operator snapshot."""

    def __init__(
        self,
        store: Any,
        *,
        database_path: str | Path,
        audio_root: str | Path,
        live: Any | None,
        files: Any | None,
        v2_sessions: Any | None = None,
        helper_presence: Any | None = None,
        capture_observations: Any | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic_ns: Callable[[], int] | None = None,
        journal_logger: logging.Logger | None = None,
    ) -> None:
        self._store = store
        self._database_path = Path(database_path).expanduser()
        self._audio_root = Path(audio_root).expanduser()
        self._live = live
        self._files = files
        self._v2_sessions = v2_sessions
        self._helper_presence = helper_presence
        self._capture_observations = capture_observations
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._logger = journal_logger or LOGGER
        self._readiness = "starting"
        self._lock = asyncio.Lock()
        self._previous_edges: dict[str, object] | None = None
        self._recent_events: deque[dict[str, object]] = deque(
            maxlen=OPERATOR_JOURNAL_LIMIT
        )
        self._event_sequence = 0
        self._event_occurrences: Counter[tuple[str, str]] = Counter()
        self._latest_error: dict[str, object] | None = None
        self._active_error_fingerprint: tuple[object, ...] | None = None
        self._error_occurrences: Counter[tuple[object, object]] = Counter()

    async def start(self) -> None:
        self._readiness = "ready"
        await self.snapshot()

    async def stop(self) -> None:
        self._readiness = "stopping"
        await self.snapshot()

    async def snapshot(
        self,
        *,
        operator_mutation: str | None = None,
        mutation_outcome: str | None = None,
        mutation_error: str | None = None,
    ) -> dict[str, object]:
        """Return one allowlisted observation and journal only newly observed edges."""

        async with self._lock:
            now = _utc(self._now())
            persistence = await self._store.operator_snapshot()
            file_phases = {} if self._files is None else self._files.operator_snapshot()
            live = (
                {"queues": _zero_live_queues(), "meetings": {}}
                if self._live is None
                else self._live.operator_snapshot()
            )
            payload, current_error = self._project(
                persistence,
                file_phases=file_phases,
                live=live,
                now=now,
            )
            if mutation_error is not None:
                current_error = {
                    "subsystem": "operator_control",
                    "code": mutation_error,
                    "severity": "error",
                    "terminal": False,
                    "retryable": True,
                    "context": {"command": operator_mutation or "unknown"},
                }
            payload["latest_error"] = self._observe_error(current_error, now)
            sanitized = serialize_operator_payload("status", payload)
            events = self._reduce_edges(
                sanitized,
                operator_mutation=operator_mutation,
                mutation_outcome=mutation_outcome,
            )
            for event in events:
                allowed = serialize_operator_payload("event", event)
                self._recent_events.append(allowed)
                self._logger.info(json.dumps(allowed, sort_keys=True, separators=(",", ":")))
            return sanitized

    def _project(
        self,
        persistence: Mapping[str, object],
        *,
        file_phases: Mapping[str, str],
        live: Mapping[str, object],
        now: datetime,
    ) -> tuple[dict[str, object], dict[str, object] | None]:
        account_rows = _mapping_rows(persistence.get("accounts"))
        meeting_rows = _mapping_rows(persistence.get("active_meetings"))
        audio_rows = _mapping_rows(persistence.get("audio"))
        live_meetings = _mapping(live.get("meetings"))
        live_queues = _mapping(live.get("queues"))
        accounts = [self._account(row) for row in account_rows]
        active_meetings: list[dict[str, object]] = []
        latest_current_error: dict[str, object] | None = None
        backpressured = 0
        for row in meeting_rows:
            meeting_id = _string(row, "meeting_id")
            mode = _string(row, "mode")
            created_at_ms = _integer(row, "created_at_ms")
            meeting = {
                "email": _string(row, "email"),
                "meeting_id": meeting_id,
                "mode": mode,
                "lifecycle": _string(row, "status"),
                "started_at_utc": _utc_from_ms(created_at_ms),
                "elapsed_seconds": max(
                    0, int(now.timestamp() - created_at_ms / 1000)
                ),
                "safe_error": None,
            }
            if mode == "live":
                raw = _mapping(live_meetings.get(meeting_id))
                capture = self._live_capture(meeting_id, raw)
                meeting["capture"] = capture
                if capture["backpressure"]["state"] == "backpressured":
                    backpressured += 1
                error = _safe_live_error(raw)
                meeting["safe_error"] = error
                latest_current_error = error or latest_current_error
            active_meetings.append(meeting)

        active_live = sum(1 for row in meeting_rows if row.get("mode") == "live")
        active_file = sum(1 for row in meeting_rows if row.get("mode") == "file")
        file_running = any(phase == "running" for phase in file_phases.values())
        worker_busy = bool(live_queues.get("worker_busy")) or file_running
        worker_available = self._live is not None or self._files is not None
        queues = {
            "live_canonical": _non_negative(live_queues.get("live_canonical", 0)),
            "live_refinement": _non_negative(live_queues.get("live_refinement", 0)),
            "live_provisional": _non_negative(live_queues.get("live_provisional", 0)),
            "batch": (
                _non_negative(live_queues.get("batch", 0))
                + sum(phase == "queued" for phase in file_phases.values())
            ),
        }
        payload = {
            "schema": OPERATOR_STATUS_SCHEMA,
            "observed_at_utc": _utc_text(now),
            "readiness": self._readiness,
            "capacity": {
                "live": {"active": active_live, "limit": LIVE_MEETING_LIMIT},
                "file": {"active": active_file},
                "inference_worker": (
                    "unavailable"
                    if not worker_available
                    else "busy" if worker_busy else "idle"
                ),
                "queues": queues,
                "backpressured_meetings": backpressured,
            },
            "accounts": accounts,
            "active_meetings": active_meetings,
            "storage": {
                "filesystems": {
                    "sqlite_free_bytes": _free_bytes(self._database_path.parent),
                    "audio_free_bytes": _free_bytes(self._audio_root),
                },
                "sqlite": {
                    "database_bytes": _file_bytes(self._database_path),
                    "wal_bytes": _file_bytes(Path(f"{self._database_path}-wal")),
                },
                "audio": _audio_totals(audio_rows),
            },
            "latest_error": None,
        }
        return payload, latest_current_error

    def _account(self, row: Mapping[str, object]) -> dict[str, object]:
        return {
            "email": _string(row, "email"),
            "display_name": _string(row, "display_name"),
            "enabled": bool(row.get("enabled")),
            "sign_in_sessions": _integer(row, "sign_in_sessions"),
            "active_meetings": {
                "live": _integer(row, "active_live"),
                "file": _integer(row, "active_file"),
            },
            "audio": {
                "available": {
                    "count": _integer(row, "audio_available_count"),
                    "bytes": _integer(row, "audio_available_bytes"),
                },
                "partial": {
                    "count": _integer(row, "audio_partial_count"),
                    "bytes": _integer(row, "audio_partial_bytes"),
                },
                "unavailable": {
                    "count": _integer(row, "audio_unavailable_count"),
                    "bytes": 0,
                },
            },
            "logical": {
                "meetings": _integer(row, "meetings"),
                "transcripts": _integer(row, "transcripts"),
                "voiceprints": _integer(row, "voiceprints"),
                "final_summaries": _integer(row, "final_summaries"),
            },
        }

    def _live_capture(
        self,
        meeting_id: str,
        raw: Mapping[str, object],
    ) -> dict[str, object]:
        presence = (
            None
            if self._helper_presence is None
            else self._helper_presence.snapshot(meeting_id)
        )
        v2 = None
        if self._v2_sessions is not None:
            try:
                v2 = self._v2_sessions.get(meeting_id).snapshot()
            except KeyError:
                pass
        observations = None
        if self._capture_observations is not None:
            try:
                observations = self._capture_observations.snapshot(meeting_id)
            except KeyError:
                pass
        policy = None
        if self._live is not None:
            descriptor = self._live.runtime.descriptor
            policy = LiveCaptureHealthPolicy(
                frame_samples=descriptor.frame_samples,
                sample_rate=descriptor.sample_rate,
            )
        capture_status = project_live_capture_status(
            presence,
            v2_session=v2,
            observations=observations,
            policy=policy,
            monotonic_ns=self._monotonic_ns,
            terminal_session_status=(
                raw.get("session_status")
                if isinstance(raw.get("session_status"), str)
                else None
            ),
        )
        lanes: dict[str, object] = {}
        now_ns = self._monotonic_ns()
        for lane in (LiveLane.MICROPHONE, LiveLane.SYSTEM):
            health = "unknown"
            if v2 is not None and lane in v2.lanes:
                health = v2.lanes[lane].health
            elif presence is not None and lane.value in presence.lanes:
                health = presence.lanes[lane.value].state
            arrival = None
            if observations is not None and lane in observations.lanes:
                arrival = observations.lanes[lane].last_server_arrival_monotonic_ns
            age = None if arrival is None else max(0.0, (now_ns - arrival) / 1_000_000_000)
            lanes[lane.value] = {
                "health": health,
                "age_seconds": None if age is None else round(age, 3),
            }
        pending = _non_negative(raw.get("pending_canonical", 0))
        limit = _non_negative(raw.get("pending_limit", 0))
        rejected = bool(
            observations is not None
            and any(
                observation.consecutive_backpressure_rejections > 0
                for observation in observations.lanes.values()
            )
        )
        return {
            "phase": capture_status.capture_phase,
            "lanes": lanes,
            "pending_canonical": {"count": pending, "limit": limit},
            "backpressure": {
                "state": (
                    "backpressured"
                    if rejected or limit > 0 and pending >= limit
                    else "clear"
                )
            },
        }

    def _observe_error(
        self,
        current: Mapping[str, object] | None,
        now: datetime,
    ) -> dict[str, object] | None:
        if current is None:
            self._active_error_fingerprint = None
            return deepcopy(self._latest_error)
        context = _mapping(current.get("context"))
        fingerprint = (
            current.get("subsystem"),
            current.get("code"),
            current.get("severity"),
            current.get("terminal"),
            current.get("retryable"),
            tuple(sorted(context.items())),
        )
        if fingerprint != self._active_error_fingerprint:
            occurrence_key = (current.get("subsystem"), current.get("code"))
            self._error_occurrences[occurrence_key] += 1
            self._latest_error = {
                "occurred_at_utc": _utc_text(now),
                "subsystem": current["subsystem"],
                "code": current["code"],
                "severity": current["severity"],
                "terminal": bool(current["terminal"]),
                "retryable": bool(current["retryable"]),
                "occurrence_count": self._error_occurrences[occurrence_key],
                "context": context,
            }
        self._active_error_fingerprint = fingerprint
        return deepcopy(self._latest_error)

    def _reduce_edges(
        self,
        status: Mapping[str, object],
        *,
        operator_mutation: str | None,
        mutation_outcome: str | None,
    ) -> list[dict[str, object]]:
        state = _edge_state(status)
        observed_at = _string(status, "observed_at_utc")
        changes: list[tuple[str, str, Mapping[str, object], str, bool, bool]] = []
        if self._previous_edges is None:
            changes.append(
                (
                    "readiness",
                    "service_ready",
                    {"state": status["readiness"]},
                    "info",
                    False,
                    False,
                )
            )
        else:
            for key, kind, code in (
                ("readiness", "readiness", "readiness_changed"),
                ("accounts", "account_authority", "account_authority_changed"),
                ("meetings", "meeting_lifecycle", "active_meetings_changed"),
                ("queues", "capacity", "queue_depth_changed"),
                ("capture", "capture_health", "capture_health_changed"),
                ("backpressure", "backpressure", "backpressure_changed"),
                ("audio", "artifact_state", "retained_audio_changed"),
                ("latest_error", "safe_error", "latest_error_changed"),
            ):
                if self._previous_edges[key] != state[key]:
                    changes.append(
                        (kind, code, _event_context(key, state[key]), "info", False, False)
                    )
        self._previous_edges = deepcopy(state)
        if operator_mutation is not None:
            changes.append(
                (
                    "operator_mutation",
                    "operator_mutation",
                    {
                        "command": operator_mutation,
                        "outcome": mutation_outcome or "unknown",
                    },
                    "info" if mutation_error_free(mutation_outcome) else "error",
                    False,
                    not mutation_error_free(mutation_outcome),
                )
            )
        events = []
        for kind, code, context, severity, terminal, retryable in changes:
            occurrence_key = (kind, code)
            self._event_occurrences[occurrence_key] += 1
            events.append(
                {
                    "schema": OPERATOR_EVENT_SCHEMA,
                    "sequence": self._event_sequence,
                    "occurred_at_utc": observed_at,
                    "kind": kind,
                    "code": code,
                    "severity": severity,
                    "terminal": terminal,
                    "retryable": retryable,
                    "occurrence_count": self._event_occurrences[occurrence_key],
                    "context": dict(context),
                }
            )
            self._event_sequence += 1
        return events


def serialize_operator_payload(kind: str, payload: Mapping[str, object]) -> dict[str, object]:
    """The sole allowlist crossing JSON, human rendering, and service journal output."""

    if kind == "status":
        allowed = _STATUS_KEYS
        expected_schema = OPERATOR_STATUS_SCHEMA
    elif kind == "event":
        allowed = _EVENT_KEYS
        expected_schema = OPERATOR_EVENT_SCHEMA
    else:
        raise OperatorProjectionError("Unknown operator payload kind.")
    if payload.get("schema") != expected_schema:
        raise OperatorProjectionError("Operator payload schema is invalid.")
    copied = json.loads(json.dumps(payload, sort_keys=True))

    def validate(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key not in allowed:
                    raise OperatorProjectionError(
                        f"Operator payload field is not allowlisted: {key}"
                    )
                validate(item)
        elif isinstance(value, list):
            for item in value:
                validate(item)
        elif value is not None and not isinstance(value, (str, int, float, bool)):
            raise OperatorProjectionError("Operator payload value is not JSON-safe.")

    validate(copied)
    if kind == "status":
        _validate_status_scopes(copied)
    else:
        _validate_event_scope(copied)
    return copied


def render_operator_status(payload: Mapping[str, object]) -> str:
    status = serialize_operator_payload("status", payload)
    capacity = _mapping(status["capacity"])
    live = _mapping(capacity["live"])
    file_capacity = _mapping(capacity["file"])
    queues = _mapping(capacity["queues"])
    storage = _mapping(status["storage"])
    sqlite = _mapping(storage["sqlite"])
    filesystems = _mapping(storage["filesystems"])
    lines = [
        f"Observed: {status['observed_at_utc']}",
        f"Readiness: {status['readiness']}",
        f"Live: {live['active']}/{live['limit']} active",
        f"File: {file_capacity['active']} active",
        f"Inference worker: {capacity['inference_worker']}",
        (
            "Queues: "
            f"live_canonical={queues['live_canonical']} "
            f"live_refinement={queues['live_refinement']} "
            f"live_provisional={queues['live_provisional']} batch={queues['batch']}"
        ),
        f"Backpressured Meetings: {capacity['backpressured_meetings']}",
        (
            "Storage: "
            f"sqlite={sqlite['database_bytes']}B wal={sqlite['wal_bytes']}B "
            f"sqlite_free={filesystems['sqlite_free_bytes']}B "
            f"audio_free={filesystems['audio_free_bytes']}B"
        ),
    ]
    host_audio = _mapping(storage["audio"])
    lines.append("Retained audio: " + _audio_human(host_audio))
    accounts = status["accounts"]
    assert isinstance(accounts, list)
    lines.append(f"Accounts: {len(accounts)}")
    for account in accounts:
        row = _mapping(account)
        active = _mapping(row["active_meetings"])
        logical = _mapping(row["logical"])
        audio = _mapping(row["audio"])
        lines.append(
            f"  {row['email']} | {row['display_name']} | enabled={str(row['enabled']).lower()} "
            f"sessions={row['sign_in_sessions']} active_live={active['live']} "
            f"active_file={active['file']} meetings={logical['meetings']} "
            f"transcripts={logical['transcripts']} voiceprints={logical['voiceprints']} "
            f"final_summaries={logical['final_summaries']} audio={_audio_human(audio)}"
        )
    meetings = status["active_meetings"]
    assert isinstance(meetings, list)
    lines.append(f"Active Meetings: {len(meetings)}")
    for meeting in meetings:
        row = _mapping(meeting)
        parts = [
            f"  {row['meeting_id']}",
            str(row["email"]),
            str(row["mode"]),
            str(row["lifecycle"]),
            str(row["started_at_utc"]),
            f"{row['elapsed_seconds']}s",
        ]
        if row["mode"] == "live":
            parts.append(_live_human(row))
        parts.append(f"safe_error={_safe_error_human(row['safe_error'])}")
        lines.append(" | ".join(parts))
    latest = status["latest_error"]
    if latest is None:
        lines.append("Latest safe error: none")
    else:
        error = _mapping(latest)
        lines.append(
            f"Latest safe error: {error['occurred_at_utc']} {error['subsystem']} "
            f"{error['code']} severity={error['severity']} terminal={error['terminal']} "
            f"retryable={error['retryable']} occurrences={error['occurrence_count']} "
            f"context={json.dumps(error['context'], sort_keys=True, separators=(',', ':'))}"
        )
    return "\n".join(lines)


def configure_operator_journal() -> None:
    """Keep allowlisted service events visible when Uvicorn leaves root logging unconfigured."""

    if not LOGGER.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def _safe_error_human(value: object) -> str:
    if value is None:
        return "none"
    error = _mapping(value)
    return (
        f"subsystem={error['subsystem']} code={error['code']} "
        f"severity={error['severity']} terminal={str(error['terminal']).lower()} "
        f"retryable={str(error['retryable']).lower()}"
    )


def _live_human(row: Mapping[str, object]) -> str:
    capture = _mapping(row["capture"])
    pending = _mapping(capture["pending_canonical"])
    backpressure = _mapping(capture["backpressure"])
    lanes = _mapping(capture["lanes"])
    microphone = _mapping(lanes["microphone"])
    system = _mapping(lanes["system"])
    return (
        f"capture={capture['phase']} mic={microphone['health']}/{microphone['age_seconds']}s "
        f"system={system['health']}/{system['age_seconds']}s "
        f"canonical={pending['count']}/{pending['limit']} "
        f"backpressure={backpressure['state']}"
    )


def _audio_human(audio: Mapping[str, object]) -> str:
    return ",".join(
        f"{state}={_mapping(audio[state])['count']}/{_mapping(audio[state])['bytes']}B"
        for state in ("available", "partial", "unavailable")
    )


def _validate_status_scopes(payload: Mapping[str, object]) -> None:
    _exact_keys(
        payload,
        {
            "schema",
            "observed_at_utc",
            "readiness",
            "capacity",
            "accounts",
            "active_meetings",
            "storage",
            "latest_error",
        },
        "status",
    )
    if payload["readiness"] not in {"starting", "ready", "stopping"}:
        raise OperatorProjectionError("Operator readiness is invalid.")
    if not isinstance(payload["observed_at_utc"], str):
        raise OperatorProjectionError("Operator observation time is invalid.")
    capacity = _mapping(payload["capacity"])
    _exact_keys(
        capacity,
        {"live", "file", "inference_worker", "queues", "backpressured_meetings"},
        "capacity",
    )
    live_capacity = _mapping(capacity["live"])
    file_capacity = _mapping(capacity["file"])
    queues = _mapping(capacity["queues"])
    _exact_keys(live_capacity, {"active", "limit"}, "live capacity")
    _exact_keys(file_capacity, {"active"}, "File capacity")
    _exact_keys(
        queues,
        {"live_canonical", "live_refinement", "live_provisional", "batch"},
        "queue depth",
    )
    for value in (
        live_capacity["active"],
        live_capacity["limit"],
        file_capacity["active"],
        capacity["backpressured_meetings"],
        *queues.values(),
    ):
        _non_negative(value)
    if capacity["inference_worker"] not in {"unavailable", "idle", "busy"}:
        raise OperatorProjectionError("Operator inference worker state is invalid.")

    accounts = payload.get("accounts")
    if not isinstance(accounts, list):
        raise OperatorProjectionError("Operator accounts must be a list.")
    for value in accounts:
        account = _mapping(value)
        _exact_keys(
            account,
            {
                "email",
                "display_name",
                "enabled",
                "sign_in_sessions",
                "active_meetings",
                "audio",
                "logical",
            },
            "Account status",
        )
        if not isinstance(account["email"], str) or not isinstance(
            account["display_name"], str
        ):
            raise OperatorProjectionError("Operator Account identity is invalid.")
        if not isinstance(account["enabled"], bool):
            raise OperatorProjectionError("Operator Account enabled state is invalid.")
        _non_negative(account["sign_in_sessions"])
        active = _mapping(account["active_meetings"])
        _exact_keys(active, {"live", "file"}, "Account active Meeting counts")
        _non_negative(active["live"])
        _non_negative(active["file"])
        _validate_audio(_mapping(account["audio"]), "Account audio")
        logical = _mapping(account["logical"])
        _exact_keys(
            logical,
            {"meetings", "transcripts", "voiceprints", "final_summaries"},
            "Account logical counts",
        )
        for count in logical.values():
            _non_negative(count)

    latest = payload.get("latest_error")
    if latest is not None:
        _validate_safe_error(_mapping(latest), latest=True)
    meetings = payload.get("active_meetings")
    if not isinstance(meetings, list):
        raise OperatorProjectionError("Operator active_meetings must be a list.")
    for value in meetings:
        meeting = _mapping(value)
        base = {
            "email",
            "meeting_id",
            "mode",
            "lifecycle",
            "started_at_utc",
            "elapsed_seconds",
            "safe_error",
        }
        mode = meeting.get("mode")
        if mode == "file":
            _exact_keys(meeting, base, "active File Meeting")
        elif mode == "live":
            _exact_keys(meeting, base | {"capture"}, "active Live Meeting")
            capture = _mapping(meeting["capture"])
            _exact_keys(
                capture,
                {"phase", "lanes", "pending_canonical", "backpressure"},
                "Live capture",
            )
            if capture["phase"] not in {
                "starting",
                "awaiting_audio",
                "recording",
                "stopped",
                "failed",
            }:
                raise OperatorProjectionError("Operator capture phase is invalid.")
            lanes = _mapping(capture["lanes"])
            _exact_keys(lanes, {"microphone", "system"}, "Live capture lanes")
            for lane_value in lanes.values():
                lane = _mapping(lane_value)
                _exact_keys(lane, {"health", "age_seconds"}, "Live capture lane")
                _safe_token(lane["health"], "capture lane health")
                age = lane["age_seconds"]
                if age is not None and (
                    not isinstance(age, (int, float))
                    or isinstance(age, bool)
                    or age < 0
                ):
                    raise OperatorProjectionError("Operator capture lane age is invalid.")
            pending = _mapping(capture["pending_canonical"])
            _exact_keys(pending, {"count", "limit"}, "Live pending canonical")
            _non_negative(pending["count"])
            _non_negative(pending["limit"])
            backpressure = _mapping(capture["backpressure"])
            _exact_keys(backpressure, {"state"}, "Live backpressure")
            if backpressure["state"] not in {"clear", "backpressured"}:
                raise OperatorProjectionError("Operator backpressure state is invalid.")
        else:
            raise OperatorProjectionError("Operator active Meeting mode is invalid.")
        for key in ("email", "meeting_id", "lifecycle", "started_at_utc"):
            if not isinstance(meeting[key], str):
                raise OperatorProjectionError("Operator active Meeting field is invalid.")
        if meeting["lifecycle"] != "active":
            raise OperatorProjectionError("Operator active Meeting lifecycle is invalid.")
        _non_negative(meeting["elapsed_seconds"])
        safe_error = meeting.get("safe_error")
        if safe_error is not None:
            _validate_safe_error(_mapping(safe_error), latest=False)

    storage = _mapping(payload["storage"])
    _exact_keys(storage, {"filesystems", "sqlite", "audio"}, "storage")
    filesystems = _mapping(storage["filesystems"])
    _exact_keys(
        filesystems,
        {"sqlite_free_bytes", "audio_free_bytes"},
        "filesystem storage",
    )
    sqlite = _mapping(storage["sqlite"])
    _exact_keys(sqlite, {"database_bytes", "wal_bytes"}, "SQLite storage")
    for count in (*filesystems.values(), *sqlite.values()):
        _non_negative(count)
    _validate_audio(_mapping(storage["audio"]), "host audio")


def _validate_audio(audio: Mapping[str, object], name: str) -> None:
    _exact_keys(audio, {"available", "partial", "unavailable"}, name)
    for value in audio.values():
        totals = _mapping(value)
        _exact_keys(totals, {"count", "bytes"}, name)
        _non_negative(totals["count"])
        _non_negative(totals["bytes"])


def _exact_keys(
    value: Mapping[str, object],
    expected: set[str],
    name: str,
) -> None:
    if set(value) != expected:
        raise OperatorProjectionError(f"Operator {name} fields do not match the allowlist.")


def _validate_safe_error(error: Mapping[str, object], *, latest: bool) -> None:
    required = {"subsystem", "code", "severity", "terminal", "retryable"}
    if latest:
        required |= {"occurred_at_utc", "occurrence_count", "context"}
    if set(error) != required:
        raise OperatorProjectionError("Operator safe-error fields do not match the allowlist.")
    _safe_token(error["subsystem"], "safe-error subsystem")
    _safe_token(error["code"], "safe-error code")
    if error["severity"] not in {"info", "warning", "error"}:
        raise OperatorProjectionError("Operator safe-error severity is invalid.")
    if not isinstance(error["terminal"], bool) or not isinstance(error["retryable"], bool):
        raise OperatorProjectionError("Operator safe-error flags are invalid.")
    if latest:
        if not isinstance(error["occurred_at_utc"], str):
            raise OperatorProjectionError("Operator safe-error occurrence is invalid.")
        _non_negative(error["occurrence_count"])
        context = _mapping(error["context"])
        if set(context) not in (set(), {"command"}):
            raise OperatorProjectionError("Operator safe-error context is not allowlisted.")
        if "command" in context and context["command"] not in {
            "accounts.allow",
            "accounts.revoke",
            "meetings.interrupt",
            "unknown",
        }:
            raise OperatorProjectionError("Operator safe-error command is invalid.")


def _validate_event_scope(event: Mapping[str, object]) -> None:
    if set(event) != {
        "schema",
        "sequence",
        "occurred_at_utc",
        "kind",
        "code",
        "severity",
        "terminal",
        "retryable",
        "occurrence_count",
        "context",
    }:
        raise OperatorProjectionError("Operator event fields do not match the allowlist.")
    kind = event["kind"]
    if kind not in {
        "readiness",
        "account_authority",
        "meeting_lifecycle",
        "capacity",
        "capture_health",
        "backpressure",
        "artifact_state",
        "safe_error",
        "operator_mutation",
    }:
        raise OperatorProjectionError("Operator event kind is invalid.")
    _safe_token(event["code"], "event code")
    if event["severity"] not in {"info", "warning", "error"}:
        raise OperatorProjectionError("Operator event severity is invalid.")
    if not isinstance(event["terminal"], bool) or not isinstance(event["retryable"], bool):
        raise OperatorProjectionError("Operator event flags are invalid.")
    _non_negative(event["sequence"])
    _non_negative(event["occurrence_count"])
    context = _mapping(event["context"])
    expected = {
        "readiness": {"state"},
        "account_authority": {"enabled_accounts", "sign_in_sessions"},
        "meeting_lifecycle": {"active_live", "active_file"},
        "capacity": {
            "live_canonical",
            "live_refinement",
            "live_provisional",
            "batch",
        },
        "capture_health": {
            "starting",
            "awaiting_audio",
            "recording",
            "stopped",
            "failed",
            "healthy_lanes",
            "degraded_lanes",
            "failed_lanes",
            "inactive_lanes",
            "unknown_lanes",
        },
        "backpressure": {"backpressured_meetings"},
        "artifact_state": {
            "available_count",
            "available_bytes",
            "partial_count",
            "partial_bytes",
            "unavailable_count",
        },
        "safe_error": {"subsystem", "state"},
        "operator_mutation": {"command", "outcome"},
    }[str(kind)]
    if set(context) != expected:
        raise OperatorProjectionError("Operator event context does not match its kind.")
    if kind == "readiness":
        if context["state"] not in {"starting", "ready", "stopping"}:
            raise OperatorProjectionError("Operator readiness event state is invalid.")
    elif kind == "safe_error":
        _safe_token(context["subsystem"], "event error subsystem")
        if context["state"] != "clear":
            _safe_token(context["state"], "event error code")
    elif kind == "operator_mutation":
        if context["command"] not in {
            "accounts.allow",
            "accounts.revoke",
            "meetings.interrupt",
        }:
            raise OperatorProjectionError("Operator mutation command is invalid.")
        if context["outcome"] not in {"succeeded", "no_change", "failed"}:
            raise OperatorProjectionError("Operator mutation outcome is invalid.")
    else:
        for value in context.values():
            _non_negative(value)


def _safe_token(value: object, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) > 80
        or re.fullmatch(r"[a-z][a-z0-9_]*", value) is None
    ):
        raise OperatorProjectionError(f"Operator {name} is invalid.")
    return value


def _safe_live_error(raw: Mapping[str, object]) -> dict[str, object] | None:
    terminal = raw.get("terminal_error")
    if isinstance(terminal, Mapping):
        error = dict(terminal)
        error["code"] = _canonical_live_terminal_error(error.get("code"))
        return error
    persistence = raw.get("persistence_failure")
    if isinstance(persistence, str) and persistence:
        return {
            "subsystem": "persistence",
            "code": _canonical_live_persistence_error(persistence),
            "severity": "error",
            "terminal": False,
            "retryable": True,
        }
    return None


def _canonical_live_terminal_error(code: object) -> str:
    if (
        isinstance(code, str)
        and len(code) <= 80
        and re.fullmatch(r"[a-z][a-z0-9_]*", code) is not None
    ):
        return code
    return "live_terminal_failure"


def _canonical_live_persistence_error(reason: str) -> str:
    known = {
        "Account revoked by operator": "meeting_authority_revoked",
        "service shutdown": "service_shutdown",
    }
    mapped = known.get(reason)
    if mapped is not None:
        return mapped
    if len(reason) <= 80 and re.fullmatch(r"[a-z][a-z0-9_]*", reason) is not None:
        return reason
    return "live_persistence_failed"


def _edge_state(status: Mapping[str, object]) -> dict[str, object]:
    capacity = _mapping(status["capacity"])
    accounts = status["accounts"]
    meetings = status["active_meetings"]
    storage = _mapping(status["storage"])
    assert isinstance(accounts, list) and isinstance(meetings, list)
    enabled_accounts = sum(bool(_mapping(row)["enabled"]) for row in accounts)
    sessions = sum(int(_mapping(row)["sign_in_sessions"]) for row in accounts)
    live_phases = Counter(
        _mapping(_mapping(row)["capture"])["phase"]
        for row in meetings
        if _mapping(row)["mode"] == "live"
    )
    lane_health = Counter(
        _lane_health_class(_string(_mapping(lane), "health"))
        for row in meetings
        if _mapping(row)["mode"] == "live"
        for lane in _mapping(
            _mapping(_mapping(row)["capture"])["lanes"]
        ).values()
    )
    return {
        "readiness": status["readiness"],
        "accounts": {
            "enabled_accounts": enabled_accounts,
            "sign_in_sessions": sessions,
        },
        "meetings": {
            "active_live": _mapping(capacity["live"])["active"],
            "active_file": _mapping(capacity["file"])["active"],
        },
        "queues": capacity["queues"],
        "capture": {
            **{
                name: live_phases[name]
                for name in (
                    "starting",
                    "awaiting_audio",
                    "recording",
                    "stopped",
                    "failed",
                )
            },
            **{
                f"{name}_lanes": lane_health[name]
                for name in ("healthy", "degraded", "failed", "inactive", "unknown")
            },
        },
        "backpressure": {
            "backpressured_meetings": capacity["backpressured_meetings"]
        },
        "audio": storage["audio"],
        "latest_error": status["latest_error"],
    }


def _lane_health_class(health: str) -> str:
    if health in {"active", "capturing"}:
        return "healthy"
    if health in {"degraded", "recovering"}:
        return "degraded"
    if health == "failed":
        return "failed"
    if health in {"starting", "stopped"}:
        return "inactive"
    return "unknown"


def _event_context(key: str, value: object) -> Mapping[str, object]:
    if key == "readiness":
        return {"state": value}
    if key == "audio":
        audio = _mapping(value)
        available = _mapping(audio["available"])
        partial = _mapping(audio["partial"])
        unavailable = _mapping(audio["unavailable"])
        return {
            "available_count": available["count"],
            "available_bytes": available["bytes"],
            "partial_count": partial["count"],
            "partial_bytes": partial["bytes"],
            "unavailable_count": unavailable["count"],
        }
    if key == "latest_error":
        if value is None:
            return {"state": "clear"}
        error = _mapping(value)
        return {"subsystem": error["subsystem"], "state": error["code"]}
    return _mapping(value)


def _audio_totals(rows: list[Mapping[str, object]]) -> dict[str, object]:
    found = {str(row["state"]): row for row in rows}
    return {
        state: {
            "count": _non_negative(found.get(state, {}).get("count", 0)),
            "bytes": _non_negative(found.get(state, {}).get("bytes", 0)),
        }
        for state in ("available", "partial", "unavailable")
    }


def _zero_live_queues() -> dict[str, int | bool]:
    return {
        "batch": 0,
        "live_canonical": 0,
        "live_refinement": 0,
        "live_provisional": 0,
        "worker_busy": False,
    }


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_rows(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise OperatorProjectionError("Operator persistence rows are invalid.")
    if not all(isinstance(row, Mapping) for row in value):
        raise OperatorProjectionError("Operator persistence row is invalid.")
    return list(value)


def _string(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str):
        raise OperatorProjectionError(f"Operator source field is not a string: {key}")
    return value


def _integer(row: Mapping[str, object], key: str) -> int:
    return _non_negative(row.get(key))


def _non_negative(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise OperatorProjectionError("Operator count must be a non-negative integer.")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise OperatorProjectionError("Operator clock must be timezone-aware.")
    return value.astimezone(timezone.utc)


def _utc_text(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _utc_from_ms(value: int) -> str:
    return _utc_text(datetime.fromtimestamp(value / 1000, timezone.utc))


def _existing_ancestor(path: Path) -> Path:
    current = path
    while not current.exists() and current != current.parent:
        current = current.parent
    return current


def _free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(_existing_ancestor(path)).free
    except OSError as exc:
        raise OperatorProjectionError("Operator filesystem capacity is unavailable.") from exc


def _file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0
    except OSError as exc:
        raise OperatorProjectionError("Operator SQLite size is unavailable.") from exc


def mutation_error_free(outcome: str | None) -> bool:
    return outcome in {"succeeded", "no_change"}


__all__ = [
    "OPERATOR_EVENT_SCHEMA",
    "OPERATOR_JOURNAL_LIMIT",
    "OPERATOR_STATUS_SCHEMA",
    "OperatorProjectionError",
    "Phase2OperatorStatus",
    "configure_operator_journal",
    "render_operator_status",
    "serialize_operator_payload",
]
