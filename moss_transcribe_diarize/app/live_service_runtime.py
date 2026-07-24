from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from .live_session import AudioFrame, FrameAck, LIVE_SAMPLE_RATE, LiveSnapshot


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


class LiveServiceRuntime(Protocol):
    def create(self) -> LiveServiceCreateResult:
        ...

    def accept_frame(self, session_id: str, frame: AudioFrame) -> LiveServiceFrameResult:
        ...

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        ...

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        ...

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        ...

    async def abort(self, session_id: str, reason: str) -> LiveServiceSnapshot:
        ...


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
