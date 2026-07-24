from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from collections import deque
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Callable, Mapping

from .live_arbiter import InferenceArbiter, InferenceArbiterBackpressure
from .live_coordinator import (
    LiveCoordinator,
    LiveCoordinatorError,
    LiveIdentityPreparer,
    SpeechSignalProvider,
)
from .live_endpoint import EndpointPolicy, EndpointPolicyError
from .live_session import (
    AudioFrame,
    FrameAck,
    LIVE_SAMPLE_RATE,
    LiveSession,
    LiveSessionBackpressure,
    LiveSessionClosed,
    LiveSessionFailed,
    LiveSnapshot,
)


LIVE_SERVICE_SCHEMA_VERSION = 1
LIVE_PROTOCOL_VERSION = "moss-live-service.v1"


class LiveServiceFailureKind(str, Enum):
    INTEGRITY = "integrity"
    PROVIDER_CONFIG = "provider_config"
    IDENTITY_COMMIT = "identity_commit"
    RTF = "rtf"
    TRANSPORT_PACING = "transport_pacing"


@dataclass(frozen=True, slots=True)
class LiveServiceFailureRecord:
    kind: LiveServiceFailureKind
    code: str
    message: str
    retryable: bool = False
    detail: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.code:
            raise ValueError("failure code must be non-empty.")
        if not self.message:
            raise ValueError("failure message must be non-empty.")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        payload["detail"] = None if self.detail is None else dict(self.detail)
        return payload


class LiveServiceError(RuntimeError):
    failure_kind = LiveServiceFailureKind.INTEGRITY

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        retryable: bool = False,
        detail: Mapping[str, Any] | None = None,
    ):
        super().__init__(message)
        self.failure = LiveServiceFailureRecord(
            kind=self.failure_kind,
            code=code or self.failure_kind.value,
            message=message,
            retryable=retryable,
            detail=detail,
        )


class LiveServiceIntegrityFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.INTEGRITY


class LiveServiceProviderConfigFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.PROVIDER_CONFIG


class LiveServiceIdentityCommitFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.IDENTITY_COMMIT


class LiveServiceRtfFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.RTF


class LiveServiceTransportPacingFailure(LiveServiceError):
    failure_kind = LiveServiceFailureKind.TRANSPORT_PACING


@dataclass(frozen=True, slots=True)
class LiveServiceBounds:
    max_frame_samples: int
    max_queue_depth: int
    max_retained_samples: int
    max_identity_speakers: int
    max_events: int
    hard_cap_samples: int | None = None
    stop_drain_deadline_seconds: float | None = None

    def __post_init__(self) -> None:
        _positive(self.max_frame_samples, "max_frame_samples")
        _positive(self.max_queue_depth, "max_queue_depth")
        _positive(self.max_retained_samples, "max_retained_samples")
        _positive(self.max_identity_speakers, "max_identity_speakers")
        _positive(self.max_events, "max_events")
        if self.hard_cap_samples is not None:
            _positive(self.hard_cap_samples, "hard_cap_samples")
        if self.stop_drain_deadline_seconds is not None and self.stop_drain_deadline_seconds < 0:
            raise ValueError("stop_drain_deadline_seconds must be non-negative when provided.")


@dataclass(frozen=True, slots=True)
class LiveServiceConfigHashes:
    endpoint_config_hash: str
    identity_config_hash: str
    decoder_config_hash: str
    combined_config_hash: str

    @classmethod
    def from_parts(
        cls,
        *,
        endpoint_config: Mapping[str, Any],
        identity_config: Mapping[str, Any],
        decoder_config: Mapping[str, Any],
    ) -> "LiveServiceConfigHashes":
        endpoint_hash = hash_config(endpoint_config)
        identity_hash = hash_config(identity_config)
        decoder_hash = hash_config(decoder_config)
        return cls(
            endpoint_config_hash=endpoint_hash,
            identity_config_hash=identity_hash,
            decoder_config_hash=decoder_hash,
            combined_config_hash=hash_config(
                {
                    "decoder": decoder_hash,
                    "endpoint": endpoint_hash,
                    "identity": identity_hash,
                }
            ),
        )

    def __post_init__(self) -> None:
        for name, value in (
            ("endpoint_config_hash", self.endpoint_config_hash),
            ("identity_config_hash", self.identity_config_hash),
            ("decoder_config_hash", self.decoder_config_hash),
            ("combined_config_hash", self.combined_config_hash),
        ):
            _sha256_hex(value, name)


@dataclass(frozen=True, slots=True)
class LiveServiceDescriptor:
    source_revision: str
    provider_name: str
    provider_revision: str
    provider_manifest_hash: str
    config_hashes: LiveServiceConfigHashes
    bounds: LiveServiceBounds
    schema_version: int = LIVE_SERVICE_SCHEMA_VERSION
    live_protocol_version: str = LIVE_PROTOCOL_VERSION
    sample_rate: int = LIVE_SAMPLE_RATE
    frame_samples: int = LIVE_SAMPLE_RATE
    feature_enabled: bool = True

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported live service descriptor schema_version.")
        if self.live_protocol_version != LIVE_PROTOCOL_VERSION:
            raise ValueError("unsupported live service protocol version.")
        if self.sample_rate != LIVE_SAMPLE_RATE:
            raise ValueError(f"live service audio must be {LIVE_SAMPLE_RATE} Hz.")
        _positive(self.frame_samples, "frame_samples")
        if self.frame_samples > self.bounds.max_frame_samples:
            raise ValueError("frame_samples must not exceed max_frame_samples.")
        for name, value in (
            ("source_revision", self.source_revision),
            ("provider_name", self.provider_name),
            ("provider_revision", self.provider_revision),
        ):
            if not value:
                raise ValueError(f"{name} must be non-empty.")
        _sha256_hex(self.provider_manifest_hash, "provider_manifest_hash")
        if not self.feature_enabled:
            raise ValueError("live service descriptor is only valid for an explicitly enabled runtime.")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class LiveServiceEvent:
    seq: int
    session_id: str
    kind: str
    snapshot_version: int
    payload: Mapping[str, Any]
    schema_version: int = LIVE_SERVICE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported live service event schema_version.")
        _non_negative(self.seq, "seq")
        _non_negative(self.snapshot_version, "snapshot_version")
        if not self.session_id:
            raise ValueError("session_id must be non-empty.")
        if not self.kind:
            raise ValueError("event kind must be non-empty.")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["payload"] = _jsonable(dict(self.payload))
        return payload


@dataclass(frozen=True, slots=True)
class LiveServiceSnapshot:
    session_id: str
    descriptor: LiveServiceDescriptor
    session: LiveSnapshot
    pending_work_items: int
    terminal_failure: LiveServiceFailureRecord | None = None
    schema_version: int = LIVE_SERVICE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != LIVE_SERVICE_SCHEMA_VERSION:
            raise ValueError("unsupported live service snapshot schema_version.")
        if not self.session_id:
            raise ValueError("session_id must be non-empty.")
        _non_negative(self.pending_work_items, "pending_work_items")

    def to_dict(self) -> dict[str, Any]:
        return _jsonable(asdict(self))


@dataclass(frozen=True, slots=True)
class LiveServiceCreateResult:
    session_id: str
    descriptor: LiveServiceDescriptor
    snapshot: LiveServiceSnapshot


@dataclass(frozen=True, slots=True)
class LiveServiceFrameResult:
    ack: FrameAck
    queued_item_ids: tuple[int, ...]
    snapshot: LiveServiceSnapshot

    def __post_init__(self) -> None:
        object.__setattr__(self, "queued_item_ids", tuple(self.queued_item_ids))


@dataclass(slots=True)
class _RuntimeSession:
    session_id: str
    descriptor: LiveServiceDescriptor
    session: LiveSession
    coordinator: LiveCoordinator
    arbiter: InferenceArbiter
    events: deque[LiveServiceEvent]
    next_event_seq: int = 0
    terminal_failure: LiveServiceFailureRecord | None = None


class LiveServiceRuntime:
    """Deep default-off runtime for isolated service-backed live sessions."""

    def __init__(
        self,
        *,
        descriptor: LiveServiceDescriptor,
        endpoint_policy_factory: Callable[[], EndpointPolicy],
        speech_provider_factory: Callable[[], SpeechSignalProvider],
        decoder_factory: Callable[[], Any],
        identity_preparer_factory: Callable[[], LiveIdentityPreparer],
        session_id_factory: Callable[[], str] | None = None,
    ):
        self.descriptor = descriptor
        self._endpoint_policy_factory = endpoint_policy_factory
        self._speech_provider_factory = speech_provider_factory
        self._decoder_factory = decoder_factory
        self._identity_preparer_factory = identity_preparer_factory
        self._session_id_factory = session_id_factory or (lambda: uuid.uuid4().hex)
        self._sessions: dict[str, _RuntimeSession] = {}

    def create(self) -> LiveServiceCreateResult:
        session_id = self._new_session_id()
        session = LiveSession(
            max_retained_samples=self.descriptor.bounds.max_retained_samples,
            hard_cap_samples=self.descriptor.bounds.hard_cap_samples,
        )
        arbiter = InferenceArbiter(max_live_canonical_items=self.descriptor.bounds.max_queue_depth)
        coordinator = LiveCoordinator(
            session_key=session_id,
            session=session,
            endpoint_policy=self._endpoint_policy_factory(),
            speech_provider=self._speech_provider_factory(),
            decoder=self._decoder_factory(),
            identity_preparer=self._identity_preparer_factory(),
            arbiter=arbiter,
        )
        state = _RuntimeSession(
            session_id=session_id,
            descriptor=self.descriptor,
            session=session,
            coordinator=coordinator,
            arbiter=arbiter,
            events=deque(maxlen=self.descriptor.bounds.max_events),
        )
        self._sessions[session_id] = state
        self._record_event(state, "session_created", {})
        snapshot = self._snapshot(state)
        return LiveServiceCreateResult(session_id=session_id, descriptor=self.descriptor, snapshot=snapshot)

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        state = self._get(session_id)
        self._raise_terminal(state)
        try:
            result = state.coordinator.accept_frame(frame)
        except Exception as exc:
            self._fail(state, self._failure_from_exception(exc))
            raise

        session_snapshot = state.session.snapshot()
        ack = FrameAck(
            sequence=frame.sequence,
            start_sample=result.accepted_start_sample,
            end_sample=result.accepted_end_sample,
            accepted_samples=session_snapshot.accepted_samples,
            retained_samples=session_snapshot.retained_samples,
            frozen_span_ids=tuple(span.id for span in result.frozen_spans),
        )
        self._record_event(
            state,
            "frame_accepted",
            {
                "sequence": frame.sequence,
                "start_sample": result.accepted_start_sample,
                "end_sample": result.accepted_end_sample,
                "queued_item_ids": result.queued_item_ids,
            },
        )
        for span in result.frozen_spans:
            self._record_event(
                state,
                "span_frozen",
                {
                    "span_id": span.id,
                    "start_sample": span.start_sample,
                    "end_sample": span.end_sample,
                    "reason": span.reason,
                },
            )
        for item_id in result.queued_item_ids:
            self._record_event(state, "canonical_queued", {"item_id": item_id})
        return LiveServiceFrameResult(
            ack=ack,
            queued_item_ids=result.queued_item_ids,
            snapshot=self._snapshot(state),
        )

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        state = self._get(session_id)
        _non_negative(since_seq, "since_seq")
        return tuple(event for event in state.events if event.seq >= since_seq)

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        state = self._get(session_id)
        snapshot = self._snapshot(state)
        if since_version is not None and snapshot.session.version <= since_version:
            return None
        return snapshot

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        state = self._get(session_id)
        self._raise_terminal(state)
        loop = asyncio.get_running_loop()
        end_time = loop.time() + max(0.0, float(deadline))
        try:
            queued = state.coordinator.stop_endpoint()
            for item_id in queued:
                self._record_event(state, "canonical_queued", {"item_id": item_id, "reason": "stop"})
            while self._pending_work_items(state) or state.session.snapshot().pending_span_ids:
                if loop.time() > end_time:
                    raise TimeoutError("live service stop deadline expired with unresolved work.")
                self._pump_one(state)
            remaining = max(0.0, end_time - loop.time())
            snapshot = await state.session.stop(remaining)
        except Exception as exc:
            failure = self._failure_from_exception(exc)
            self._fail(state, failure)
            if not isinstance(exc, TimeoutError):
                raise
            raise
        snapshot = self._snapshot(state, session_snapshot=snapshot)
        if snapshot.session.accepted_samples != snapshot.session.accounted_samples or snapshot.pending_work_items:
            failure = LiveServiceIntegrityFailure(
                "live service stop completed without exact accepted/accounted equality.",
                code="stop_accounting_mismatch",
            ).failure
            self._fail(state, failure)
            raise LiveServiceIntegrityFailure(failure.message, code=failure.code)
        self._record_event(state, "session_closed", {"accepted_samples": snapshot.session.accepted_samples})
        return self._snapshot(state)

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        state = self._get(session_id)
        reason = reason or "aborted"
        if state.terminal_failure is None:
            self._fail(
                state,
                LiveServiceTransportPacingFailure(reason, code="aborted").failure,
                event_kind="session_aborted",
            )
        snapshot = await state.session.abort(reason)
        return self._snapshot(state, session_snapshot=snapshot)

    def _new_session_id(self) -> str:
        session_id = self._session_id_factory()
        if not session_id:
            raise ValueError("session_id_factory returned an empty id.")
        if session_id in self._sessions:
            raise ValueError(f"duplicate live session id {session_id}.")
        return session_id

    def _get(self, session_id: str) -> _RuntimeSession:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown live service session {session_id}") from exc

    def _snapshot(
        self,
        state: _RuntimeSession,
        *,
        session_snapshot: LiveSnapshot | None = None,
    ) -> LiveServiceSnapshot:
        return LiveServiceSnapshot(
            session_id=state.session_id,
            descriptor=state.descriptor,
            session=session_snapshot or state.session.snapshot(),
            pending_work_items=self._pending_work_items(state),
            terminal_failure=state.terminal_failure,
        )

    def _pending_work_items(self, state: _RuntimeSession) -> int:
        return state.arbiter.snapshot().live_canonical

    def _pump_one(self, state: _RuntimeSession) -> None:
        item = state.arbiter.next_work()
        if item is None:
            if state.session.snapshot().pending_span_ids:
                raise LiveServiceIdentityCommitFailure(
                    "live service has unresolved frozen spans without queued work.",
                    code="unqueued_frozen_span",
                )
            return
        try:
            result = state.coordinator.process_work_item(item)
        except Exception as exc:
            self._fail(state, self._failure_from_exception(exc))
            raise
        self._record_event(
            state,
            "canonical_processed",
            {
                "item_id": item.id,
                "span_id": result.span_id,
                "submitted": result.submitted,
                "identity_status": result.identity_status,
                "committed_samples": result.committed_samples,
            },
        )
        if not result.submitted:
            failure = LiveServiceIdentityCommitFailure(
                "canonical work did not atomically publish.",
                code="canonical_not_submitted",
                detail={"span_id": result.span_id, "identity_status": result.identity_status},
            ).failure
            self._fail(state, failure)
            raise LiveServiceIdentityCommitFailure(
                failure.message,
                code=failure.code,
                detail=failure.detail,
            )

    def _record_event(self, state: _RuntimeSession, kind: str, payload: Mapping[str, Any]) -> None:
        event = LiveServiceEvent(
            seq=state.next_event_seq,
            session_id=state.session_id,
            kind=kind,
            snapshot_version=state.session.snapshot().version,
            payload=payload,
        )
        state.events.append(event)
        state.next_event_seq += 1

    def _fail(
        self,
        state: _RuntimeSession,
        failure: LiveServiceFailureRecord,
        *,
        event_kind: str = "terminal_failure",
    ) -> None:
        if state.terminal_failure is not None:
            return
        state.terminal_failure = failure
        self._record_event(state, event_kind, {"failure": failure.to_dict()})

    def _raise_terminal(self, state: _RuntimeSession) -> None:
        if state.terminal_failure is not None:
            raise _error_from_failure(state.terminal_failure)

    def _failure_from_exception(self, exc: Exception) -> LiveServiceFailureRecord:
        if isinstance(exc, LiveServiceError):
            return exc.failure
        if isinstance(exc, (LiveSessionBackpressure, InferenceArbiterBackpressure, TimeoutError)):
            return LiveServiceTransportPacingFailure(str(exc), code="backpressure_or_deadline").failure
        if isinstance(exc, (LiveSessionFailed, LiveCoordinatorError, EndpointPolicyError)):
            return LiveServiceIdentityCommitFailure(str(exc), code="identity_commit_failed").failure
        if isinstance(exc, (LiveSessionClosed, ValueError)):
            return LiveServiceIntegrityFailure(str(exc), code="integrity_error").failure
        return LiveServiceIntegrityFailure(str(exc), code=exc.__class__.__name__).failure


def _error_from_failure(failure: LiveServiceFailureRecord) -> LiveServiceError:
    error_type: type[LiveServiceError]
    if failure.kind == LiveServiceFailureKind.PROVIDER_CONFIG:
        error_type = LiveServiceProviderConfigFailure
    elif failure.kind == LiveServiceFailureKind.IDENTITY_COMMIT:
        error_type = LiveServiceIdentityCommitFailure
    elif failure.kind == LiveServiceFailureKind.RTF:
        error_type = LiveServiceRtfFailure
    elif failure.kind == LiveServiceFailureKind.TRANSPORT_PACING:
        error_type = LiveServiceTransportPacingFailure
    else:
        error_type = LiveServiceIntegrityFailure
    return error_type(
        failure.message,
        code=failure.code,
        retryable=failure.retryable,
        detail=failure.detail,
    )


def hash_config(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(_jsonable(dict(payload)), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return value


def _positive(value: int, name: str) -> None:
    if int(value) <= 0:
        raise ValueError(f"{name} must be positive.")


def _non_negative(value: int, name: str) -> None:
    if int(value) < 0:
        raise ValueError(f"{name} must be non-negative.")


def _sha256_hex(value: str, name: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase sha256 hex digest.")
