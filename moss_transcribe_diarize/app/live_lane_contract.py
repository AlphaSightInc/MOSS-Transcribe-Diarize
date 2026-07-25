from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


V2_PROTOCOL_NAME = "moss-live-service.v2"
V2_PROTOCOL_VERSION = 2
PCM16_BYTES_PER_SAMPLE = 2


class LiveLane(str, Enum):
    SYSTEM = "system"
    MICROPHONE = "microphone"


@dataclass(frozen=True, slots=True)
class LiveV2Capabilities:
    lanes: bool = True
    binary: bool = False
    idempotent_frames: bool = True
    resumable: bool = True

    def __post_init__(self) -> None:
        _exact_bool(self.lanes, "lanes")
        _exact_bool(self.binary, "binary")
        _exact_bool(self.idempotent_frames, "idempotent_frames")
        _exact_bool(self.resumable, "resumable")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LiveV2Capabilities":
        _assert_exact_keys(
            payload,
            {
                "lanes",
                "binary",
                "idempotent_frames",
                "resumable",
            },
            "v2 capabilities",
        )
        return cls(
            lanes=payload["lanes"],
            binary=payload["binary"],
            idempotent_frames=payload["idempotent_frames"],
            resumable=payload["resumable"],
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "lanes": self.lanes,
            "binary": self.binary,
            "idempotent_frames": self.idempotent_frames,
            "resumable": self.resumable,
        }


@dataclass(frozen=True, slots=True)
class LiveV2Descriptor:
    protocol: str = V2_PROTOCOL_NAME
    min_protocol_version: int = V2_PROTOCOL_VERSION
    max_protocol_version: int = V2_PROTOCOL_VERSION
    capabilities: LiveV2Capabilities | None = None

    def __post_init__(self) -> None:
        if self.protocol != V2_PROTOCOL_NAME:
            raise ValueError("v2 descriptor protocol must be moss-live-service.v2.")
        _positive_int(self.min_protocol_version, "min_protocol_version")
        _positive_int(self.max_protocol_version, "max_protocol_version")
        if self.min_protocol_version != V2_PROTOCOL_VERSION or self.max_protocol_version != V2_PROTOCOL_VERSION:
            raise ValueError("v2 descriptor protocol range must be exactly 2..2.")
        if self.capabilities is None:
            object.__setattr__(self, "capabilities", LiveV2Capabilities())
        if not isinstance(self.capabilities, LiveV2Capabilities):
            raise ValueError("capabilities must be LiveV2Capabilities.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LiveV2Descriptor":
        _assert_exact_keys(
            payload,
            {
                "protocol",
                "min_protocol_version",
                "max_protocol_version",
                "capabilities",
            },
            "v2 descriptor",
        )
        capabilities = payload["capabilities"]
        if not isinstance(capabilities, Mapping):
            raise ValueError("capabilities must be a JSON object.")
        return cls(
            protocol=payload["protocol"],
            min_protocol_version=payload["min_protocol_version"],
            max_protocol_version=payload["max_protocol_version"],
            capabilities=LiveV2Capabilities.from_dict(capabilities),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "min_protocol_version": self.min_protocol_version,
            "max_protocol_version": self.max_protocol_version,
            "capabilities": self.capabilities.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class LiveV2Frame:
    lane: LiveLane
    sequence: int
    capture_timestamp_ns: int
    device_epoch: int
    silent: bool
    discontinuity: bool
    sample_rate: int
    sample_count: int
    pcm: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.lane, LiveLane):
            raise ValueError("lane must be a canonical v2 live lane.")
        _non_negative_int(self.sequence, "sequence")
        _non_negative_int(self.capture_timestamp_ns, "capture_timestamp_ns")
        _non_negative_int(self.device_epoch, "device_epoch")
        _exact_bool(self.silent, "silent")
        _exact_bool(self.discontinuity, "discontinuity")
        _positive_int(self.sample_rate, "sample_rate")
        _positive_int(self.sample_count, "sample_count")
        if not isinstance(self.pcm, bytes):
            raise ValueError("pcm must be bytes.")
        if len(self.pcm) != self.sample_count * PCM16_BYTES_PER_SAMPLE:
            raise ValueError("pcm length must match 16-bit mono sample_count.")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LiveV2Frame":
        _assert_exact_keys(
            payload,
            {
                "lane",
                "sequence",
                "capture_timestamp_ns",
                "device_epoch",
                "silent",
                "discontinuity",
                "sample_rate",
                "sample_count",
                "pcm_base64",
            },
            "v2 frame",
        )
        return cls(
            lane=_lane(payload["lane"]),
            sequence=_required_int(payload["sequence"], "sequence"),
            capture_timestamp_ns=_required_int(payload["capture_timestamp_ns"], "capture_timestamp_ns"),
            device_epoch=_required_int(payload["device_epoch"], "device_epoch"),
            silent=payload["silent"],
            discontinuity=payload["discontinuity"],
            sample_rate=_required_int(payload["sample_rate"], "sample_rate"),
            sample_count=_required_int(payload["sample_count"], "sample_count"),
            pcm=_decode_pcm_base64(payload["pcm_base64"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane.value,
            "sequence": self.sequence,
            "capture_timestamp_ns": self.capture_timestamp_ns,
            "device_epoch": self.device_epoch,
            "silent": self.silent,
            "discontinuity": self.discontinuity,
            "sample_rate": self.sample_rate,
            "sample_count": self.sample_count,
            "pcm_base64": base64.b64encode(self.pcm).decode("ascii"),
        }


@dataclass(frozen=True, slots=True)
class LiveV2Ack:
    lane: LiveLane
    sequence: int
    start_sample: int
    end_sample: int
    accepted_samples: int
    retained_samples: int
    frozen_span_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.lane, LiveLane):
            raise ValueError("lane must be a canonical v2 live lane.")
        _non_negative_int(self.sequence, "sequence")
        _non_negative_int(self.start_sample, "start_sample")
        _non_negative_int(self.end_sample, "end_sample")
        _non_negative_int(self.accepted_samples, "accepted_samples")
        _non_negative_int(self.retained_samples, "retained_samples")
        if self.end_sample < self.start_sample:
            raise ValueError("end_sample must be greater than or equal to start_sample.")
        if not isinstance(self.frozen_span_ids, tuple):
            object.__setattr__(self, "frozen_span_ids", tuple(self.frozen_span_ids))
        for span_id in self.frozen_span_ids:
            _non_negative_int(span_id, "frozen_span_ids")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LiveV2Ack":
        _assert_exact_keys(
            payload,
            {
                "lane",
                "sequence",
                "start_sample",
                "end_sample",
                "accepted_samples",
                "retained_samples",
                "frozen_span_ids",
            },
            "v2 acknowledgement",
        )
        frozen_span_ids = payload["frozen_span_ids"]
        if not isinstance(frozen_span_ids, list):
            raise ValueError("frozen_span_ids must be a JSON array.")
        return cls(
            lane=_lane(payload["lane"]),
            sequence=_required_int(payload["sequence"], "sequence"),
            start_sample=_required_int(payload["start_sample"], "start_sample"),
            end_sample=_required_int(payload["end_sample"], "end_sample"),
            accepted_samples=_required_int(payload["accepted_samples"], "accepted_samples"),
            retained_samples=_required_int(payload["retained_samples"], "retained_samples"),
            frozen_span_ids=tuple(_required_int(span_id, "frozen_span_ids") for span_id in frozen_span_ids),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane.value,
            "sequence": self.sequence,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "accepted_samples": self.accepted_samples,
            "retained_samples": self.retained_samples,
            "frozen_span_ids": list(self.frozen_span_ids),
        }


def _assert_exact_keys(payload: Mapping[str, Any], expected: set[str], label: str) -> None:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{label} must be a JSON object.")
    actual = set(payload)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        parts = []
        if missing:
            parts.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            parts.append(f"unknown fields: {', '.join(unknown)}")
        raise ValueError(f"{label} has invalid fields ({'; '.join(parts)}).")


def _lane(value: Any) -> LiveLane:
    if not isinstance(value, str):
        raise ValueError("lane must be a string.")
    try:
        return LiveLane(value)
    except ValueError as exc:
        raise ValueError("lane must be one of: system, microphone.") from exc


def _required_int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    return value


def _non_negative_int(value: Any, name: str) -> None:
    value = _required_int(value, name)
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _positive_int(value: Any, name: str) -> None:
    value = _required_int(value, name)
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _exact_bool(value: Any, name: str) -> None:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a boolean.")


def _decode_pcm_base64(value: Any) -> bytes:
    if not isinstance(value, str):
        raise ValueError("pcm_base64 must be a base64 string.")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("pcm_base64 must be valid base64.") from exc
