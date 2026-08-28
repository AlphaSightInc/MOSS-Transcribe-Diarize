from __future__ import annotations

import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PHASE1_CREATION_QUIESCED = "phase1_creation_quiesced"
PHASE1_CREATION_GATE_UNAVAILABLE = "phase1_creation_gate_unavailable"
_MARKER_BYTES = b"moss-phase1-creation-quiesced-v1\n"


def default_phase1_creation_marker() -> Path:
    """The one host fact shared by both legacy web processes and a reboot."""

    return Path.home() / ".local/state/moss-transcribe-diarize/phase1-creation-quiesced"


@dataclass(frozen=True, slots=True)
class Phase1CreationSnapshot:
    state: str
    entrants: int

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state, "entrants": self.entrants}


class Phase1CreationRefused(RuntimeError):
    def __init__(self, *, state: str) -> None:
        code = (
            PHASE1_CREATION_QUIESCED
            if state == "quiesced"
            else PHASE1_CREATION_GATE_UNAVAILABLE
        )
        super().__init__(code)
        self.code = code
        self.state = state

    def response_body(self) -> dict[str, Any]:
        detail = (
            "Phase-1 creation is quiesced for cutover."
            if self.state == "quiesced"
            else "Phase-1 creation state is unavailable; creation is fail-closed."
        )
        return {
            "detail": detail,
            "failure": {
                "code": self.code,
                "retryable": True,
                "state": self.state,
            },
        }


class Phase1CreationAdmission:
    """One already-admitted request; closing it decrements its process exactly once."""

    def __init__(self, gate: "Phase1CreationGate") -> None:
        self._gate = gate
        self._closed = False

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._gate._release()

    def __enter__(self) -> "Phase1CreationAdmission":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class Phase1CreationGate:
    """Compose a reboot-durable marker with this process's in-flight admissions."""

    def __init__(self, marker_path: str | Path) -> None:
        self.marker_path = Path(marker_path).expanduser()
        self._lock = threading.Lock()
        self._entrants = 0

    def enter(self) -> Phase1CreationAdmission:
        """Admit before request-body wait and hold through durable work registration."""

        with self._lock:
            self._entrants += 1
        try:
            state = self._marker_state()
            if state != "open":
                raise Phase1CreationRefused(state=state)
        except BaseException:
            self._release()
            raise
        return Phase1CreationAdmission(self)

    def snapshot(self) -> Phase1CreationSnapshot:
        state = self._marker_state()
        with self._lock:
            entrants = self._entrants
        return Phase1CreationSnapshot(state=state, entrants=entrants)

    def _marker_state(self) -> str:
        try:
            os.stat(self.marker_path)
        except FileNotFoundError:
            return "open"
        except OSError:
            return "error"
        return "quiesced"

    def _release(self) -> None:
        with self._lock:
            if self._entrants <= 0:
                raise RuntimeError("Phase-1 creation admission released without an entrant.")
            self._entrants -= 1


def enable_phase1_creation_quiesce(marker_path: str | Path) -> None:
    """Durably and idempotently publish the host marker with private permissions."""

    marker = Path(marker_path).expanduser()
    marker.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(marker.parent, 0o700)
    try:
        os.stat(marker)
    except FileNotFoundError:
        pass
    else:
        os.chmod(marker, 0o600)
        return

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{marker.name}.",
        suffix=".tmp",
        dir=marker.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        written = os.write(descriptor, _MARKER_BYTES)
        if written != len(_MARKER_BYTES):
            raise OSError("short write while creating Phase-1 quiesce marker")
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, marker)
        os.chmod(marker, 0o600)
        _fsync_directory(marker.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def disable_phase1_creation_quiesce(marker_path: str | Path) -> None:
    """Durably and idempotently remove the host marker."""

    marker = Path(marker_path).expanduser()
    try:
        marker.unlink()
    except FileNotFoundError:
        return
    _fsync_directory(marker.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
