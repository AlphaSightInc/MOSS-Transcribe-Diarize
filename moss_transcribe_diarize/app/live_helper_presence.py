from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Literal


HELPER_HEALTH_SCHEMA = "moss-live-helper-health.v1"
HELPER_LANES = frozenset(("system", "microphone"))
HELPER_STATES = frozenset(
    ("starting", "capturing", "degraded", "recovering", "failed", "stopped")
)

HelperState = Literal["starting", "capturing", "degraded", "recovering", "failed", "stopped"]


class HelperPresenceConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HelperLaneHealth:
    state: HelperState
    device_epoch: int
    dropped_frames: int
    discontinuities: int
    failure_code: str | None

    @classmethod
    def from_dict(cls, payload: Any) -> "HelperLaneHealth":
        if not isinstance(payload, dict):
            raise ValueError("helper lane health must be a JSON object.")
        _require_exact_keys(
            payload,
            {
                "state",
                "device_epoch",
                "dropped_frames",
                "discontinuities",
                "failure_code",
            },
        )
        state = _parse_state(payload["state"], "lane state")
        failure_code = payload["failure_code"]
        if failure_code is not None and not isinstance(failure_code, str):
            raise ValueError("helper lane failure_code must be null or string.")
        if failure_code == "":
            raise ValueError("helper lane failure_code must be non-empty when provided.")
        if state == "failed" and failure_code is None:
            raise ValueError("failed helper lane requires failure_code.")
        return cls(
            state=state,
            device_epoch=_parse_non_negative_int(payload["device_epoch"], "device_epoch"),
            dropped_frames=_parse_non_negative_int(payload["dropped_frames"], "dropped_frames"),
            discontinuities=_parse_non_negative_int(payload["discontinuities"], "discontinuities"),
            failure_code=failure_code,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "device_epoch": self.device_epoch,
            "dropped_frames": self.dropped_frames,
            "discontinuities": self.discontinuities,
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True, slots=True)
class HelperHeartbeat:
    schema: str
    instance_id: str
    sequence: int
    sent_monotonic_ns: int
    helper_version: str
    state: HelperState
    lanes: dict[str, HelperLaneHealth]

    @classmethod
    def from_dict(cls, payload: Any) -> "HelperHeartbeat":
        if not isinstance(payload, dict):
            raise ValueError("helper heartbeat must be a JSON object.")
        _require_exact_keys(
            payload,
            {
                "schema",
                "instance_id",
                "sequence",
                "sent_monotonic_ns",
                "helper_version",
                "state",
                "lanes",
            },
        )
        schema = payload["schema"]
        if schema != HELPER_HEALTH_SCHEMA:
            raise ValueError("unsupported helper health schema.")
        instance_id = payload["instance_id"]
        helper_version = payload["helper_version"]
        if not isinstance(instance_id, str) or not instance_id:
            raise ValueError("helper instance_id must be a non-empty string.")
        if not isinstance(helper_version, str) or not helper_version:
            raise ValueError("helper_version must be a non-empty string.")
        lanes = payload["lanes"]
        if not isinstance(lanes, dict):
            raise ValueError("helper lanes must be a JSON object.")
        _require_exact_keys(lanes, HELPER_LANES)
        return cls(
            schema=schema,
            instance_id=instance_id,
            sequence=_parse_non_negative_int(payload["sequence"], "sequence"),
            sent_monotonic_ns=_parse_non_negative_int(
                payload["sent_monotonic_ns"],
                "sent_monotonic_ns",
            ),
            helper_version=helper_version,
            state=_parse_state(payload["state"], "helper state"),
            lanes={lane: HelperLaneHealth.from_dict(lanes[lane]) for lane in sorted(HELPER_LANES)},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "instance_id": self.instance_id,
            "sequence": self.sequence,
            "sent_monotonic_ns": self.sent_monotonic_ns,
            "helper_version": self.helper_version,
            "state": self.state,
            "lanes": {lane: self.lanes[lane].to_dict() for lane in sorted(HELPER_LANES)},
        }


@dataclass(frozen=True, slots=True)
class HelperPresenceSnapshot:
    schema: str
    instance_id: str
    sequence: int
    sent_monotonic_ns: int
    last_seen_monotonic_ns: int
    helper_version: str
    state: HelperState
    lanes: dict[str, HelperLaneHealth]

    @classmethod
    def from_heartbeat(
        cls,
        heartbeat: HelperHeartbeat,
        *,
        last_seen_monotonic_ns: int,
    ) -> "HelperPresenceSnapshot":
        return cls(
            schema=heartbeat.schema,
            instance_id=heartbeat.instance_id,
            sequence=heartbeat.sequence,
            sent_monotonic_ns=heartbeat.sent_monotonic_ns,
            last_seen_monotonic_ns=last_seen_monotonic_ns,
            helper_version=heartbeat.helper_version,
            state=heartbeat.state,
            lanes=heartbeat.lanes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "instance_id": self.instance_id,
            "sequence": self.sequence,
            "sent_monotonic_ns": self.sent_monotonic_ns,
            "last_seen_monotonic_ns": self.last_seen_monotonic_ns,
            "helper_version": self.helper_version,
            "state": self.state,
            "lanes": {lane: self.lanes[lane].to_dict() for lane in sorted(HELPER_LANES)},
        }


@dataclass(frozen=True, slots=True)
class _ObservedPresence:
    heartbeat: HelperHeartbeat
    snapshot: HelperPresenceSnapshot


class HelperPresenceRegistry:
    """Observation-only helper health store for strict latest-heartbeat facts."""

    def __init__(self, *, monotonic_ns: Callable[[], int] | None = None) -> None:
        self._monotonic_ns = monotonic_ns or time.monotonic_ns
        self._sessions: dict[str, _ObservedPresence] = {}

    def observe(self, session_id: str, heartbeat: HelperHeartbeat) -> HelperPresenceSnapshot:
        if not session_id:
            raise ValueError("session_id is required.")
        received_monotonic_ns = _parse_non_negative_int(
            self._monotonic_ns(),
            "received_monotonic_ns",
        )
        current = self._sessions.get(session_id)
        if current is None:
            snapshot = HelperPresenceSnapshot.from_heartbeat(
                heartbeat,
                last_seen_monotonic_ns=received_monotonic_ns,
            )
            self._sessions[session_id] = _ObservedPresence(heartbeat=heartbeat, snapshot=snapshot)
            return snapshot
        if heartbeat.instance_id != current.heartbeat.instance_id:
            raise HelperPresenceConflict("helper instance switched.")
        if heartbeat.sequence == current.heartbeat.sequence:
            if heartbeat != current.heartbeat:
                raise HelperPresenceConflict("helper heartbeat duplicate changed payload.")
            return current.snapshot
        if heartbeat.sequence < current.heartbeat.sequence:
            raise HelperPresenceConflict("helper heartbeat sequence regressed.")
        if heartbeat.sent_monotonic_ns <= current.heartbeat.sent_monotonic_ns:
            raise HelperPresenceConflict("helper heartbeat monotonic time did not advance.")
        snapshot = HelperPresenceSnapshot.from_heartbeat(
            heartbeat,
            last_seen_monotonic_ns=received_monotonic_ns,
        )
        self._sessions[session_id] = _ObservedPresence(heartbeat=heartbeat, snapshot=snapshot)
        return snapshot

    def snapshot(self, session_id: str) -> HelperPresenceSnapshot | None:
        current = self._sessions.get(session_id)
        return None if current is None else current.snapshot

    def release(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)


def _require_exact_keys(payload: dict[str, Any], expected: set[str] | frozenset[str]) -> None:
    keys = set(payload)
    if keys != set(expected):
        missing = sorted(set(expected) - keys)
        extra = sorted(keys - set(expected))
        detail = []
        if missing:
            detail.append(f"missing {', '.join(missing)}")
        if extra:
            detail.append(f"unknown {', '.join(extra)}")
        raise ValueError("helper health keys must match exactly: " + "; ".join(detail))


def _parse_state(value: Any, field: str) -> HelperState:
    if value not in HELPER_STATES:
        raise ValueError(f"{field} is not a valid helper state.")
    return value


def _parse_non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer.")
    return value
