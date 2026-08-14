from __future__ import annotations

import json
import math
import os
import stat
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence


JOURNAL_DIRECTORY_MODE = 0o700
JOURNAL_FILE_MODE = 0o600


class LiveVectorJournalObservation(Protocol):
    speaker_label: str
    centroid: tuple[float, ...]
    sample_seconds: float
    exemplar_count: int
    provisional: bool
    embedder_id: str
    embedder_state_sha: str


@dataclass(frozen=True, slots=True)
class LiveVectorJournalRefusal:
    speaker_label: str
    reason: str


@dataclass(frozen=True, slots=True)
class LiveVectorJournalAppendResult:
    written: int
    refusals: tuple[LiveVectorJournalRefusal, ...]


class LiveVectorJournal:
    """Append complete session batches to one private JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    @classmethod
    def declared(
        cls,
        path: str | Path,
        *,
        checkout_root: str | Path,
    ) -> "LiveVectorJournal":
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            raise ValueError(f"vector journal must be an absolute path: {candidate}")
        resolved = candidate.resolve()
        checkout = Path(checkout_root).expanduser().resolve()
        if resolved == checkout or resolved.is_relative_to(checkout):
            raise ValueError(
                f"vector journal must be outside the repository checkout: {resolved}"
            )
        _prepare_private_directory(resolved.parent)
        _prepare_private_file(resolved)
        return cls(resolved)

    def append_session(
        self,
        *,
        session_id: str,
        echo_mode: str,
        created_at: float,
        observations: Sequence[LiveVectorJournalObservation],
    ) -> LiveVectorJournalAppendResult:
        rows: list[dict[str, object]] = []
        refusals: list[LiveVectorJournalRefusal] = []
        for observation in observations:
            values, reason = _observation_values(observation)
            if reason is not None:
                refusals.append(
                    LiveVectorJournalRefusal(
                        speaker_label=_refusal_speaker_label(values),
                        reason=reason,
                    )
                )
                continue
            assert values is not None
            rows.append(
                {
                    "session_id": session_id,
                    "speaker_label": values["speaker_label"],
                    "centroid": list(values["centroid"]),
                    "sample_seconds": values["sample_seconds"],
                    "exemplar_count": values["exemplar_count"],
                    "provisional": values["provisional"],
                    "embedder_id": values["embedder_id"],
                    "embedder_state_sha": values["embedder_state_sha"],
                    "created_at": created_at,
                    "echo_mode": echo_mode,
                }
            )

        if rows:
            payload = b"".join(
                (
                    json.dumps(row, allow_nan=False, separators=(",", ":"), sort_keys=True)
                    + "\n"
                ).encode("utf-8")
                for row in rows
            )
            with self._lock:
                descriptor = os.open(
                    self.path,
                    os.O_APPEND | os.O_CREAT | os.O_WRONLY,
                    JOURNAL_FILE_MODE,
                )
                try:
                    _enforce_file_mode(descriptor)
                    _write_all(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        return LiveVectorJournalAppendResult(written=len(rows), refusals=tuple(refusals))


def _observation_values(
    observation: LiveVectorJournalObservation,
) -> tuple[dict[str, object] | None, str | None]:
    """Read the structural protocol once so one stale provider cannot abort its batch."""

    values: dict[str, object] = {}
    for field in (
        "speaker_label",
        "centroid",
        "sample_seconds",
        "exemplar_count",
        "provisional",
        "embedder_id",
        "embedder_state_sha",
    ):
        try:
            values[field] = getattr(observation, field)
        except AttributeError:
            return values, f"{field}_missing"
    return values, _observation_refusal(values)


def _refusal_speaker_label(values: dict[str, object] | None) -> str:
    if values is None:
        return "<unnamed>"
    speaker_label = values.get("speaker_label")
    return speaker_label if isinstance(speaker_label, str) and speaker_label else "<unnamed>"


def _observation_refusal(values: dict[str, object]) -> str | None:
    centroid = values["centroid"]
    if not centroid:
        return "centroid_empty"
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in centroid):
        return "centroid_not_numeric"
    if any(not math.isfinite(value) for value in centroid):
        return "centroid_non_finite"
    sample_seconds = values["sample_seconds"]
    if (
        isinstance(sample_seconds, bool)
        or not isinstance(sample_seconds, (int, float))
        or not math.isfinite(sample_seconds)
        or sample_seconds <= 0
    ):
        return "sample_seconds_invalid"
    exemplar_count = values["exemplar_count"]
    if (
        isinstance(exemplar_count, bool)
        or not isinstance(exemplar_count, int)
        or exemplar_count < 0
    ):
        return "exemplar_count_invalid"
    if not isinstance(values["provisional"], bool):
        return "provisional_invalid"
    embedder_id = values["embedder_id"]
    if not isinstance(embedder_id, str) or not embedder_id:
        return "embedder_id_missing"
    embedder_state_sha = values["embedder_state_sha"]
    if not isinstance(embedder_state_sha, str) or len(embedder_state_sha) != 64 or any(
        character not in "0123456789abcdef" for character in embedder_state_sha
    ):
        return "embedder_state_sha_invalid"
    return None


def _write_all(descriptor: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(descriptor, view)
        if written <= 0:
            raise OSError("vector journal append made no progress")
        view = view[written:]


def _prepare_private_directory(directory: Path) -> None:
    """Create a private leaf and reject unsafe existing ancestors.

    The journal leaf is always 0700. Directories created on the way to it are
    individually chmoded because ``mkdir(..., parents=True)`` otherwise leaves
    intermediate components at the process umask. An existing non-sticky
    group/world-writable ancestor could be swapped by another principal, so
    starting with that location is refused rather than silently trusting it.
    """

    missing: list[Path] = []
    existing = directory
    while not existing.exists():
        missing.append(existing)
        existing = existing.parent

    # An already-existing leaf is repairable. Its parent and every more distant
    # ancestor are the trust boundary for constructing or reopening that leaf.
    _refuse_loose_ancestors(directory.parent if not missing else existing)
    for path in reversed(missing):
        path.mkdir(mode=JOURNAL_DIRECTORY_MODE)
        _enforce_directory_mode(path)
    _enforce_directory_mode(directory)


def _refuse_loose_ancestors(start: Path) -> None:
    for ancestor in (start, *start.parents):
        mode = ancestor.stat().st_mode
        writable_by_peer = mode & 0o022
        if writable_by_peer and not mode & stat.S_ISVTX:
            raise ValueError(
                "vector journal ancestor is group- or world-writable: "
                f"{ancestor}"
            )


def _enforce_directory_mode(directory: Path) -> None:
    os.chmod(directory, JOURNAL_DIRECTORY_MODE)
    observed = directory.stat().st_mode & 0o777
    if observed != JOURNAL_DIRECTORY_MODE:
        raise OSError(
            "vector journal directory filesystem does not enforce private mode "
            f"(requested {JOURNAL_DIRECTORY_MODE:o}, reads {observed:o}): {directory}"
        )


def _enforce_file_mode(descriptor: int) -> None:
    # The mode argument to O_CREAT is masked by umask and is ignored when the
    # journal already exists, so assert the postcondition through the descriptor.
    os.fchmod(descriptor, JOURNAL_FILE_MODE)
    observed = os.fstat(descriptor).st_mode & 0o777
    if observed != JOURNAL_FILE_MODE:
        raise OSError(
            "vector journal filesystem does not enforce private file mode "
            f"(requested {JOURNAL_FILE_MODE:o}, reads {observed:o})"
        )


def _prepare_private_file(path: Path) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise ValueError(f"vector journal must be a regular file: {path}")
    descriptor = os.open(path, os.O_APPEND | os.O_WRONLY)
    try:
        _enforce_file_mode(descriptor)
    finally:
        os.close(descriptor)
