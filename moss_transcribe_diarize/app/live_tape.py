"""The tape recorder -- ADR-0002 implementation step 2, bounded by ADR-0003.

A *tape* is the durable substrate a retrospective sweep needs: the meeting's audio, on
disk, addressable by wall-clock offset, for as long as the meeting (and no longer, unless
the deployment says otherwise). Three tracks per session -- one per capture lane plus the
mixed track the runtime actually decodes -- as raw PCM16 mono at the canonical live sample
rate, with a JSON index carrying the gap manifest. WAV is rendered on demand elsewhere;
nothing here transcodes.

Four rules out of `docs/adr/0003-live-session-audio-retention.md` are structural here, not
incidental, and each is enforced rather than documented:

* **D2 -- opt-in.** There is no default root. A deployment that declares none simply never
  constructs a store, and the service writes exactly what it writes today. Every gate this
  loop has recorded was measured against a no-tape service; a privacy posture must not
  arrive as a side effect of upgrading a binary.
* **D4 -- one declared root, where modes are real.** `LiveSessionTapeStore.declared`
  refuses a root inside the repo checkout, a root sharing a filesystem with a directory the
  deployment names as its batch runs tree, and a filesystem that does not enforce modes.
  The last is not theoretical: the deployed server's Windows drive is a 9p `drvfs` mount
  without `metadata`, where `chmod` is a silent no-op.
* **D5 -- storage pressure degrades the tape, never the meeting.** No method here raises
  because of a frame. Reaching the declared cap, a write that fails, or a frame the tape
  cannot place records a *typed degradation* naming the reason and the byte counts, stops
  taping, and returns. The meeting continues on live labels alone.
* **D6 -- the service reaps, at startup too.** `reap()` is driven by session state plus
  TTL and is safe to call before any session exists, which is what makes a tape left by a
  crashed process mortal.

Time note, because this repo has a shipped contract about it (P1/P2, the *Duration vs
timestamp* row): the TTL comparison here subtracts two `time.time()` readings. That is the
deliberate exception P4 recorded -- a retention deadline has to survive a process restart,
and `time.monotonic()` does not. The direction of the host's known clock steps is safe for
this use: a backward step can only *delay* a reap, never make one premature.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .live_lane_contract import LiveLane, LiveV2Frame
from .live_session import LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE


_TAPE_LOG = logging.getLogger("moss_transcribe_diarize.live.tape")

#: The mixed track's name. Lane tracks are named by the lane's own wire value, so a track
#: name is readable on disk without a decoder ring.
MIXED_TRACK = "mixed"

TAPE_INDEX_FILENAME = "index.json"
TAPE_INDEX_VERSION = 1

#: The posture `live.key` and `live-auth.json` already have on the deployed host.
TAPE_DIRECTORY_MODE = 0o700
TAPE_FILE_MODE = 0o600

#: Typed degradation reasons. A tape that stops taping always names why, in the manifest
#: and in one log line, because a substrate that silently disappears is indistinguishable
#: from one that was never enabled.
TAPE_CAPACITY_EXHAUSTED = "tape_capacity_exhausted"
TAPE_WRITE_FAILED = "tape_write_failed"
TAPE_FRAME_NOT_ADMISSIBLE = "tape_frame_not_admissible"

_REBASE_CHUNK_BYTES = 1 << 20


class LiveTapeRootError(ValueError):
    """Raised when a declared retention root does not satisfy ADR-0003 D4.

    This is a *deployment* refusal, raised once at construction where an operator can read
    it, and deliberately not a degradation: a root that cannot hold audio safely must stop
    the service from starting with retention enabled, not quietly disable it.
    """


@dataclass(frozen=True, slots=True)
class LiveTapeDegradation:
    reason: str
    detail: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason:
            raise ValueError("degradation reason must be a non-empty string.")
        object.__setattr__(self, "detail", dict(self.detail))

    def to_dict(self) -> dict[str, object]:
        return {"reason": self.reason, "detail": dict(self.detail)}


@dataclass(frozen=True, slots=True)
class LiveTapeAppendResult:
    """What one append did, in the vocabulary the caller can act on.

    `taping` is the only field a live caller needs: once it is false the tape has stopped
    and the meeting carries on. The rest is evidence.
    """

    taping: bool
    written: bool
    duplicate: bool
    degradation: LiveTapeDegradation | None = None


@dataclass(frozen=True, slots=True)
class LiveTapeGap:
    start_sample: int
    end_sample: int

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample

    def to_dict(self) -> dict[str, int]:
        return {
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "sample_count": self.sample_count,
        }


class _Track:
    """One PCM file plus the coverage that makes its gaps computable.

    Offsets are derived from capture timestamps, never from arrival order, which is what
    keeps wall-clock offsets true when frames are dropped, duplicated or replayed. Coverage
    is stored as merged half-open sample intervals; the gap manifest is its complement, so
    a late frame that fills a hole removes the gap rather than adding a correction.
    """

    __slots__ = (
        "name",
        "path",
        "sample_rate",
        "origin_ns",
        "_covered",
        "frames_written",
        "duplicate_frames",
        "overlapped_samples",
        "rebases",
        "_fd",
    )

    def __init__(self, *, name: str, path: Path, sample_rate: int):
        self.name = name
        self.path = path
        self.sample_rate = sample_rate
        self.origin_ns: int | None = None
        self._covered: list[tuple[int, int]] = []
        self.frames_written = 0
        self.duplicate_frames = 0
        self.overlapped_samples = 0
        self.rebases = 0
        self._fd: int | None = None

    # -- persistence -------------------------------------------------------------

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.path.name,
            "origin_timestamp_ns": self.origin_ns,
            "sample_count": self.sample_count,
            "bytes": self.byte_size,
            "frames_written": self.frames_written,
            "duplicate_frames": self.duplicate_frames,
            "overlapped_samples": self.overlapped_samples,
            "rebases": self.rebases,
            "gaps": [gap.to_dict() for gap in self.gaps],
        }

    def restore(self, payload: Mapping[str, object]) -> None:
        self.origin_ns = payload.get("origin_timestamp_ns")  # type: ignore[assignment]
        self.frames_written = int(payload.get("frames_written", 0))
        self.duplicate_frames = int(payload.get("duplicate_frames", 0))
        self.overlapped_samples = int(payload.get("overlapped_samples", 0))
        self.rebases = int(payload.get("rebases", 0))
        total = int(payload.get("sample_count", 0))
        gaps = [
            (int(item["start_sample"]), int(item["end_sample"]))
            for item in payload.get("gaps", ())  # type: ignore[union-attr]
        ]
        # Coverage is the complement of the persisted gaps, so resume needs no second
        # representation of the same fact and the two can never disagree.
        self._covered = _complement(gaps, total)

    # -- geometry ----------------------------------------------------------------

    @property
    def sample_count(self) -> int:
        return self._covered[-1][1] if self._covered else 0

    @property
    def byte_size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except FileNotFoundError:
            return 0

    @property
    def gaps(self) -> tuple[LiveTapeGap, ...]:
        return tuple(
            LiveTapeGap(start_sample=start, end_sample=end)
            for start, end in _complement(self._covered, self.sample_count)
        )

    def offset_samples(self, timestamp_ns: int) -> int:
        if self.origin_ns is None:
            return 0
        return round(
            (timestamp_ns - self.origin_ns) * self.sample_rate / 1_000_000_000
        )

    def covers(self, start: int, end: int) -> bool:
        return any(low <= start and end <= high for low, high in self._covered)

    # -- writing -----------------------------------------------------------------

    def projected_growth(self, start_sample: int, sample_count: int) -> int:
        """Bytes this placement would add to the file, before it is attempted."""

        end_byte = (start_sample + sample_count) * PCM16_BYTES_PER_SAMPLE
        return max(0, end_byte - self.byte_size)

    def rebase_growth(self, shift_samples: int) -> int:
        return shift_samples * PCM16_BYTES_PER_SAMPLE

    def place(self, *, pcm: bytes, start_sample: int, sample_count: int) -> None:
        fd = self._fileno()
        os.pwrite(fd, pcm, start_sample * PCM16_BYTES_PER_SAMPLE)
        self.overlapped_samples += _overlap(self._covered, start_sample, start_sample + sample_count)
        self._covered = _merge(self._covered, start_sample, start_sample + sample_count)
        self.frames_written += 1

    def rebase(self, shift_samples: int) -> None:
        """Move every recorded sample forward so an earlier timestamp can become sample 0.

        Reached only when a frame arrives whose capture timestamp precedes everything the
        track has seen. Downstream of the v2 ingress that is impossible -- the ingress
        refuses a frame that is not the lane's next sequence -- so this exists for the
        appender's own contract (ADR-0002 gate C replays raw outbox retry order into it),
        not for the wired path. Copied from the end backwards in chunks so the whole tape
        never has to be resident.
        """

        fd = self._fileno()
        shift_bytes = shift_samples * PCM16_BYTES_PER_SAMPLE
        position = os.fstat(fd).st_size
        while position > 0:
            take = min(_REBASE_CHUNK_BYTES, position)
            position -= take
            os.pwrite(fd, os.pread(fd, take, position), position + shift_bytes)
        written = 0
        while written < shift_bytes:
            chunk = min(_REBASE_CHUNK_BYTES, shift_bytes - written)
            os.pwrite(fd, b"\x00" * chunk, written)
            written += chunk
        self._covered = [(low + shift_samples, high + shift_samples) for low, high in self._covered]
        self.rebases += 1

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _fileno(self) -> int:
        if self._fd is None:
            fd = os.open(self.path, os.O_RDWR | os.O_CREAT, TAPE_FILE_MODE)
            # O_CREAT's mode is masked by the umask, so the posture is asserted rather
            # than requested. D4(1) is a rule about what is on disk, not about intent.
            os.fchmod(fd, TAPE_FILE_MODE)
            self._fd = fd
        return self._fd


class LiveSessionTape:
    """One meeting's tape: three tracks, one gap manifest, one degradation state."""

    def __init__(
        self,
        *,
        directory: Path,
        session_id: str,
        sample_rate: int,
        max_bytes: int,
        created_at: float,
    ):
        self.directory = directory
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.max_bytes = max_bytes
        self.created_at = created_at
        self.updated_at = created_at
        self.ended_at: float | None = None
        self._degradation: LiveTapeDegradation | None = None
        self._lock = threading.RLock()
        self._tracks: dict[str, _Track] = {
            name: _Track(name=name, path=directory / f"{name}.pcm", sample_rate=sample_rate)
            for name in (LiveLane.SYSTEM.value, LiveLane.MICROPHONE.value, MIXED_TRACK)
        }

    # -- state -------------------------------------------------------------------

    @property
    def degradation(self) -> LiveTapeDegradation | None:
        return self._degradation

    @property
    def taping(self) -> bool:
        return self._degradation is None and self.ended_at is None

    @property
    def index_path(self) -> Path:
        return self.directory / TAPE_INDEX_FILENAME

    def total_bytes(self) -> int:
        return sum(track.byte_size for track in self._tracks.values())

    def manifest(self) -> dict[str, object]:
        return {
            "version": TAPE_INDEX_VERSION,
            "session_id": self.session_id,
            "sample_rate": self.sample_rate,
            "max_bytes": self.max_bytes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ended_at": self.ended_at,
            "total_bytes": self.total_bytes(),
            "degradation": None if self._degradation is None else self._degradation.to_dict(),
            "tracks": {name: track.to_dict() for name, track in self._tracks.items()},
        }

    def track_path(self, name: str) -> Path:
        return self._track(name).path

    def gaps(self, name: str) -> tuple[LiveTapeGap, ...]:
        return self._track(name).gaps

    def read_track(self, name: str) -> bytes:
        path = self._track(name).path
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return b""

    # -- appending ---------------------------------------------------------------

    def append_lane_frame(self, frame: LiveV2Frame) -> LiveTapeAppendResult:
        """Tee one acknowledged lane frame onto its lane track.

        A silent frame carries real zero PCM by the wire contract, so it is written like
        any other: a silence that was *captured* and a silence that was *dropped* must not
        become the same fact on disk, and only the gap manifest can tell them apart.
        """

        return self._append(
            track_name=frame.lane.value,
            pcm=frame.pcm,
            timestamp_ns=frame.capture_timestamp_ns,
            sample_count=frame.sample_count,
            sample_rate=frame.sample_rate,
            detail={"lane": frame.lane.value, "sequence": frame.sequence},
        )

    def append_mixed(
        self,
        *,
        pcm: bytes,
        start_timestamp_ns: int,
        sample_count: int,
        sample_rate: int = LIVE_SAMPLE_RATE,
    ) -> LiveTapeAppendResult:
        """Tee one sealed mixer interval onto the mixed track.

        The tee point ADR-0002 names. The mixer's cursor is monotone and its intervals
        tile, so this track is contiguous by construction -- but it is placed by timestamp
        like the lanes, so a mixer that ever skips leaves a gap rather than a splice.
        """

        return self._append(
            track_name=MIXED_TRACK,
            pcm=pcm,
            timestamp_ns=start_timestamp_ns,
            sample_count=sample_count,
            sample_rate=sample_rate,
            detail={"track": MIXED_TRACK},
        )

    def _append(
        self,
        *,
        track_name: str,
        pcm: bytes,
        timestamp_ns: int,
        sample_count: int,
        sample_rate: int,
        detail: Mapping[str, object],
    ) -> LiveTapeAppendResult:
        with self._lock:
            if self._degradation is not None:
                return LiveTapeAppendResult(
                    taping=False, written=False, duplicate=False, degradation=self._degradation
                )
            if self.ended_at is not None:
                return self._degrade(
                    TAPE_FRAME_NOT_ADMISSIBLE,
                    {**detail, "condition": "tape already ended"},
                )
            track = self._tracks.get(track_name)
            if track is None:
                return self._degrade(
                    TAPE_FRAME_NOT_ADMISSIBLE, {**detail, "condition": "unknown track"}
                )
            if sample_rate != self.sample_rate:
                return self._degrade(
                    TAPE_FRAME_NOT_ADMISSIBLE,
                    {**detail, "condition": "sample rate", "expected": self.sample_rate, "received": sample_rate},
                )
            if sample_count <= 0 or len(pcm) != sample_count * PCM16_BYTES_PER_SAMPLE:
                return self._degrade(
                    TAPE_FRAME_NOT_ADMISSIBLE,
                    {**detail, "condition": "pcm length", "sample_count": sample_count, "bytes": len(pcm)},
                )

            shift_samples = 0
            start_sample = track.offset_samples(timestamp_ns)
            if start_sample < 0:
                shift_samples = -start_sample
                start_sample = 0
            end_sample = start_sample + sample_count

            if shift_samples == 0 and track.covers(start_sample, end_sample):
                track.duplicate_frames += 1
                self._touch()
                return LiveTapeAppendResult(taping=True, written=False, duplicate=True)

            growth = track.projected_growth(start_sample, sample_count)
            if shift_samples:
                growth += track.rebase_growth(shift_samples)
            if self.total_bytes() + growth > self.max_bytes:
                return self._degrade(
                    TAPE_CAPACITY_EXHAUSTED,
                    {
                        **detail,
                        "max_bytes": self.max_bytes,
                        "total_bytes": self.total_bytes(),
                        "requested_bytes": growth,
                    },
                )

            try:
                if shift_samples:
                    track.rebase(shift_samples)
                    track.origin_ns = timestamp_ns
                elif track.origin_ns is None:
                    track.origin_ns = timestamp_ns
                track.place(pcm=pcm, start_sample=start_sample, sample_count=sample_count)
            except OSError as exc:
                return self._degrade(
                    TAPE_WRITE_FAILED,
                    {**detail, "error": f"{type(exc).__name__}: {exc}", "total_bytes": self.total_bytes()},
                )
            self._touch()
            return LiveTapeAppendResult(taping=True, written=True, duplicate=False)

    # -- lifecycle ---------------------------------------------------------------

    def end(self, *, now: float | None = None) -> None:
        """Close the tape. Idempotent, and never raises: a meeting ends either way."""

        with self._lock:
            if self.ended_at is None:
                self.ended_at = time.time() if now is None else now
            for track in self._tracks.values():
                track.close()
            self._flush_index()

    def _degrade(self, reason: str, detail: Mapping[str, object]) -> LiveTapeAppendResult:
        degradation = LiveTapeDegradation(reason=reason, detail=detail)
        self._degradation = degradation
        for track in self._tracks.values():
            track.close()
        _TAPE_LOG.warning(
            "live session tape degraded: session_id=%s reason=%s detail=%r",
            self.session_id,
            reason,
            dict(detail),
        )
        self._flush_index()
        return LiveTapeAppendResult(
            taping=False, written=False, duplicate=False, degradation=degradation
        )

    def _touch(self) -> None:
        self.updated_at = time.time()
        self._flush_index()

    def _flush_index(self) -> None:
        """Publish the manifest atomically, on every append.

        Staging plus `os.replace` rather than `write_text`, for the reason the port-publish
        race already cost this repo a merge: existence and completeness have to be one
        event, or a reader (here, a resume after a crash) sees a file that exists and is
        empty. Flushing every append is what makes checkpoint/resume exact at any frame.
        """

        payload = json.dumps(self.manifest(), indent=2, sort_keys=True)
        staged = self.directory / f"{TAPE_INDEX_FILENAME}.staged"
        try:
            staged.write_text(payload, encoding="utf-8")
            os.chmod(staged, TAPE_FILE_MODE)
            os.replace(staged, self.index_path)
        except OSError as exc:  # pragma: no cover - the degrade path below covers intent
            _TAPE_LOG.warning(
                "live session tape index unwritable: session_id=%s error=%s",
                self.session_id,
                exc,
            )

    def _track(self, name: str) -> _Track:
        try:
            return self._tracks[name]
        except KeyError as exc:
            raise KeyError(name) from exc

    # -- resume ------------------------------------------------------------------

    @classmethod
    def resume(cls, directory: Path) -> "LiveSessionTape":
        """Reopen an existing tape and continue it, from the index alone.

        ADR-0002 lists the tape as the crash/resume checkpoint. Everything needed to place
        the next frame -- each track's origin and coverage -- is in the manifest, so a
        resumed tape produces the same bytes as one that was never interrupted.
        """

        payload = json.loads((directory / TAPE_INDEX_FILENAME).read_text(encoding="utf-8"))
        tape = cls(
            directory=directory,
            session_id=str(payload["session_id"]),
            sample_rate=int(payload["sample_rate"]),
            max_bytes=int(payload["max_bytes"]),
            created_at=float(payload["created_at"]),
        )
        tape.updated_at = float(payload["updated_at"])
        tape.ended_at = None if payload.get("ended_at") is None else float(payload["ended_at"])
        degraded = payload.get("degradation")
        if degraded:
            tape._degradation = LiveTapeDegradation(
                reason=str(degraded["reason"]), detail=degraded.get("detail", {})
            )
        for name, track_payload in payload.get("tracks", {}).items():
            track = tape._tracks.get(name)
            if track is not None:
                track.restore(track_payload)
        return tape


class LiveSessionTapeStore:
    """The declared retention root, its admission rules, and the reaper.

    Constructed only when a deployment declares a root (D2). There is no default
    constructor and no fallback path: a caller holds `LiveSessionTapeStore | None`, and
    `None` is a service that behaves exactly as it does today.
    """

    def __init__(
        self,
        *,
        root: Path,
        retention_ttl_seconds: float,
        max_bytes_per_session: int,
        sample_rate: int = LIVE_SAMPLE_RATE,
    ):
        self.root = root
        self.retention_ttl_seconds = retention_ttl_seconds
        self.max_bytes_per_session = max_bytes_per_session
        self.sample_rate = sample_rate
        self._tapes: dict[str, LiveSessionTape] = {}
        self._lock = threading.RLock()

    @classmethod
    def declared(
        cls,
        *,
        root: str | os.PathLike[str],
        max_bytes_per_session: int,
        retention_ttl_seconds: float = 0.0,
        sample_rate: int = LIVE_SAMPLE_RATE,
        runs_directories: Iterable[str | os.PathLike[str]] = (),
    ) -> "LiveSessionTapeStore":
        """Admit a declared root, or refuse it by name (ADR-0003 D3/D4/D5).

        `retention_ttl_seconds` defaults to **0** -- the tape is deleted when the meeting
        ends -- which is the only value a tool may choose for a deployment, because it is
        the reading under which the PRD's audio clause still holds literally at every
        boundary an operator can observe after a meeting. A *positive* TTL is stated by
        the deployment, exactly as candidate 63 ruled for the matcher thresholds. There is
        no default cap for the same reason in reverse: zero would mean "never tape" and
        unbounded would be the runaway D4(3) exists to prevent, so it is required.
        """

        if not isinstance(max_bytes_per_session, int) or isinstance(max_bytes_per_session, bool):
            raise LiveTapeRootError("max_bytes_per_session must be an integer.")
        if max_bytes_per_session <= 0:
            raise LiveTapeRootError("max_bytes_per_session must be positive.")
        if not isinstance(retention_ttl_seconds, (int, float)) or isinstance(retention_ttl_seconds, bool):
            raise LiveTapeRootError("retention_ttl_seconds must be a number.")
        if retention_ttl_seconds < 0:
            raise LiveTapeRootError("retention_ttl_seconds must not be negative.")

        resolved = Path(root).expanduser()
        if not resolved.is_absolute():
            raise LiveTapeRootError(f"retention root must be an absolute path: {root}")
        resolved = resolved.resolve()

        # D4(2): a rollback is `git checkout <sha>` and `git clean` must never be a reaper.
        # The checkout is derived from this package's own location rather than named, so
        # the rule holds for any checkout on any host.
        checkout = Path(__file__).resolve().parents[2]
        if resolved == checkout or checkout in resolved.parents:
            raise LiveTapeRootError(
                f"retention root must be outside the repository checkout: {resolved}"
            )

        resolved.mkdir(mode=TAPE_DIRECTORY_MODE, parents=True, exist_ok=True)
        os.chmod(resolved, TAPE_DIRECTORY_MODE)
        # D4(4): asserted by reading the mode back. A filesystem where `chmod` is a silent
        # no-op cannot hold audio at 0700, and saying so at startup is the whole point.
        observed = resolved.stat().st_mode & 0o777
        if observed != TAPE_DIRECTORY_MODE:
            raise LiveTapeRootError(
                "retention root filesystem does not enforce modes "
                f"(requested {TAPE_DIRECTORY_MODE:o}, reads {observed:o}): {resolved}"
            )

        # D4(3): a runaway tape would answer 507 to the *batch* service's uploads without
        # ever touching it, so sharing a filesystem with a runs tree is refused -- and so
        # is living inside one, which no device comparison would catch on its own.
        root_device = resolved.stat().st_dev
        for candidate in runs_directories:
            runs = Path(candidate).expanduser()
            try:
                runs = runs.resolve()
                runs_device = runs.stat().st_dev
            except OSError:
                continue
            if resolved == runs or runs in resolved.parents:
                raise LiveTapeRootError(
                    f"retention root must not be inside a runs directory: {runs}"
                )
            if runs_device == root_device:
                raise LiveTapeRootError(
                    "retention root must not share a filesystem with a runs directory: "
                    f"{runs}"
                )

        return cls(
            root=resolved,
            retention_ttl_seconds=float(retention_ttl_seconds),
            max_bytes_per_session=max_bytes_per_session,
            sample_rate=sample_rate,
        )

    # -- tapes -------------------------------------------------------------------

    def create(self, session_id: str, *, now: float | None = None) -> LiveSessionTape:
        _session_id(session_id)
        with self._lock:
            if session_id in self._tapes:
                raise ValueError(f"session tape {session_id} already exists.")
            directory = self.root / session_id
            directory.mkdir(mode=TAPE_DIRECTORY_MODE, parents=True, exist_ok=True)
            os.chmod(directory, TAPE_DIRECTORY_MODE)
            tape = LiveSessionTape(
                directory=directory,
                session_id=session_id,
                sample_rate=self.sample_rate,
                max_bytes=self.max_bytes_per_session,
                created_at=time.time() if now is None else now,
            )
            tape._flush_index()
            self._tapes[session_id] = tape
            return tape

    def get(self, session_id: str) -> LiveSessionTape | None:
        _session_id(session_id)
        with self._lock:
            return self._tapes.get(session_id)

    def release(self, session_id: str, *, now: float | None = None) -> LiveSessionTape | None:
        """End the session's tape and hand it to the retention rule.

        Release does not delete: deletion is `reap`'s job and is driven by TTL, so a
        deployment that declared a positive TTL keeps its substrate and one that declared
        none loses it at the next reap -- one rule, one place.
        """

        _session_id(session_id)
        with self._lock:
            tape = self._tapes.pop(session_id, None)
        if tape is not None:
            tape.end(now=now)
        return tape

    # -- retention ---------------------------------------------------------------

    def reap(
        self,
        *,
        active_session_ids: Sequence[str] | None = None,
        now: float | None = None,
    ) -> tuple[str, ...]:
        """Delete every tape whose session is over and whose TTL has elapsed (D6).

        Safe to call before any session exists, which is how a tape left by a crashed
        process becomes mortal: with no active sessions, an unfinished tape is aged from
        its last append rather than treated as immortal. A directory this store cannot
        read as a tape is *never* deleted -- a reaper that removes what it does not
        understand is a worse failure than a tape that outlives its TTL.
        """

        moment = time.time() if now is None else now
        active = set(active_session_ids or ())
        with self._lock:
            active.update(self._tapes)
        reaped: list[str] = []
        if not self.root.exists():
            return ()
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir():
                continue
            session_id = directory.name
            if session_id in active:
                continue
            index = directory / TAPE_INDEX_FILENAME
            try:
                payload = json.loads(index.read_text(encoding="utf-8"))
                ended_at = payload.get("ended_at")
                if ended_at is None:
                    ended_at = payload["updated_at"]
                ended_at = float(ended_at)
            except (OSError, ValueError, KeyError, TypeError):
                _TAPE_LOG.warning(
                    "live session tape not reaped, index unreadable: path=%s", directory
                )
                continue
            if moment - ended_at < self.retention_ttl_seconds:
                continue
            shutil.rmtree(directory, ignore_errors=True)
            reaped.append(session_id)
        return tuple(reaped)


def _merge(intervals: Sequence[tuple[int, int]], start: int, end: int) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for item_low, item_high in sorted([*intervals, (start, end)]):
        if not merged:
            merged.append((item_low, item_high))
            continue
        last_low, last_high = merged[-1]
        if item_low <= last_high:
            merged[-1] = (last_low, max(last_high, item_high))
        else:
            merged.append((item_low, item_high))
    return merged


def _complement(intervals: Sequence[tuple[int, int]], total: int) -> list[tuple[int, int]]:
    holes: list[tuple[int, int]] = []
    cursor = 0
    for low, high in sorted(intervals):
        if low > cursor:
            holes.append((cursor, low))
        cursor = max(cursor, high)
    if cursor < total:
        holes.append((cursor, total))
    return holes


def _overlap(intervals: Sequence[tuple[int, int]], start: int, end: int) -> int:
    return sum(
        max(0, min(end, high) - max(start, low)) for low, high in intervals
    )


def _session_id(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("session_id must be a non-empty string.")
    if value != Path(value).name or value in {".", ".."}:
        # The session id becomes a directory name under the declared root, so it has to
        # be a name and not a path. Refusing here keeps the root's boundary a property of
        # the store rather than of every caller.
        raise ValueError("session_id must be a single path component.")
