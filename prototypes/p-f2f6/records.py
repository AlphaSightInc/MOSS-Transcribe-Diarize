"""Immutable prototype records shared by the native decision and pure observer."""

from __future__ import annotations

from dataclasses import dataclass


SCHEMA_VERSION = "moss.terminal-identity-diagnostics.v3"


@dataclass(frozen=True, slots=True)
class RawTerminalSpan:
    raw_index: int
    terminal_local_label: str
    start: int
    end: int
    samples: int


@dataclass(frozen=True, slots=True)
class RawToNormalized:
    raw_index: int
    normalized_partition_id: str | None
    disposition: str


@dataclass(frozen=True, slots=True)
class NormalizedPartitionRecord:
    schema_version: str
    meeting_owner: str
    run_owner: str
    partition_id: str
    terminal_local_label: str
    member_raw_indexes: tuple[int, ...]
    start: int
    end: int
    samples: int
    eligibility_floor_samples: int
    eligible: bool
    score_by_canonical: tuple[tuple[str, float], ...]
    margin: float | None
    decision: str
    published_identity: str | None


@dataclass(frozen=True, slots=True)
class TerminalDecisionDiagnostics:
    raw_spans: tuple[RawTerminalSpan, ...]
    raw_to_normalized: tuple[RawToNormalized, ...]
    normalized_partitions: tuple[NormalizedPartitionRecord, ...]


@dataclass(frozen=True, slots=True)
class NativeDecisionResult:
    published_proposal_bytes: bytes
    diagnostics: TerminalDecisionDiagnostics
