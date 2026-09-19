"""Bounded terminal audio and the shared live capture recorder.

Phase 2 owns durable Meeting audio staging. This module retains only two neutral
primitives: a complete mixed spill-to-disk tape for terminal transcript convergence and a
failure-isolating recorder over an injected capture-stage sink. It contains no retention
root, TTL, product authority, or legacy filesystem store.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
import threading
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol, Sequence

from .live_lane_contract import LiveV2Frame
from .live_session import LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE
from .live_silence import is_digital_silence

_TAPE_LOG = logging.getLogger("moss_transcribe_diarize.live.tape")

TAPE_CAPACITY_EXHAUSTED = "tape_capacity_exhausted"
TAPE_FRAME_NOT_ADMISSIBLE = "tape_frame_not_admissible"
TAPE_STORAGE_FAILED = "tape_storage_failed"


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


class CompleteMixedTapeUnavailable(RuntimeError):
    """The complete tape cannot serve the audio a reader asked for.

    Raised at a *reader*, never at a frame (D5): the terminal finalizer asking for audio a
    short, holed or released tape does not hold gets a refusal, and that refusal is what
    makes finalization report itself unavailable instead of decoding fabricated silence.
    """


@dataclass(frozen=True, slots=True)
class CompleteMixedTapeAccounting:
    """What one meeting's complete tape retained, and what it cost. No audio, by contract.

    `sample_count` is what the tape holds; `through_sample` is the extent it was asked
    about -- the session's own `accepted_samples` -- and `gaps` is the difference, computed
    from the intervals the tape recorded rather than inferred from the two counts. A reader
    that wants "is this tape a faithful record of the meeting" reads `complete`; a reader
    that wants "and is it the same audio" compares `pcm_sha256` with the digest of what the
    transport accepted.
    """

    epoch: int
    sample_count: int
    through_sample: int
    retained_bytes: int
    capacity_bytes: int
    peak_retained_bytes: int
    refused_samples: int
    gaps: tuple[LiveTapeGap, ...]
    pcm_sha256: str
    released: bool
    degradation: LiveTapeDegradation | None

    @property
    def complete(self) -> bool:
        """The tape covers every sample the session accepted, with no hole and no stop."""

        return not self.gaps and self.degradation is None and self.sample_count == self.through_sample

    def to_dict(self) -> dict[str, object]:
        return {
            "epoch": self.epoch,
            "sample_count": self.sample_count,
            "through_sample": self.through_sample,
            "retained_bytes": self.retained_bytes,
            "capacity_bytes": self.capacity_bytes,
            "peak_retained_bytes": self.peak_retained_bytes,
            "refused_samples": self.refused_samples,
            "gaps": [gap.to_dict() for gap in self.gaps],
            "pcm_sha256": self.pcm_sha256,
            "released": self.released,
            "complete": self.complete,
            "degradation": None if self.degradation is None else self.degradation.to_dict(),
        }


class CompleteMixedTape:
    """One meeting's whole mixed track, in bounded-memory scratch, on its sample clock.

    This tape answers one question -- *give me `[0, meeting_end)` of what this session
    decoded* -- which is the only thing a terminal finalization pass needs, and it answers
    it without retaining whole-source PCM in Python memory:

    * **D2 -- opt-in.** There is no default capacity. A deployment that declares none never
      constructs one, and the service retains exactly what it retains today. The campaign's
      measured worst case is a five-minute meeting at 9 600 000 bytes, but the number is the
      deployment's to state: a storage posture must not arrive as a side effect either.
    * **D5 -- pressure degrades the tape, never the meeting.** `append` never raises. A
      frame past the declared capacity, a frame that is not the tape's next sample, or a
      partial sample records a typed degradation naming the reason and the byte counts,
      stops taping, and returns. The meeting keeps publishing; only terminal convergence is
      lost, and it is lost *stated* rather than silently.
    * **D3 -- the tape dies with the meeting.** `release` drops the audio and keeps the
      accounting, so the evidence that the tape was faithful outlives the samples.

    Two properties are structural rather than documented. Audio is only ever appended at
    the tape's own next sample, so the tape can never contain a splice -- a hole is refused,
    not zero-filled, because zero-filled PCM is silence and a terminal pass may not decode
    silence the meeting never contained. And the digest is computed as the bytes arrive, so
    a fidelity check costs nothing at the end and cannot be recomputed from a tape that has
    already been released.
    """

    def __init__(
        self,
        *,
        epoch: int,
        capacity_bytes: int,
        sample_rate: int = LIVE_SAMPLE_RATE,
    ):
        if capacity_bytes <= 0:
            raise ValueError("complete tape capacity_bytes must be positive.")
        if sample_rate <= 0:
            raise ValueError("complete tape sample_rate must be positive.")
        self.epoch = int(epoch)
        self.capacity_bytes = int(capacity_bytes)
        self.sample_rate = int(sample_rate)
        self._lock = threading.RLock()
        # The source grows with meeting duration, but Python resident memory does not. This
        # scratch tape is intentionally not durable authority; Phase 2's owner-derived capture
        # stage separately owns restart recovery. TemporaryFile also removes itself on close.
        self._file = tempfile.TemporaryFile(mode="w+b")
        self._retained_bytes = 0
        self._covered: list[tuple[int, int]] = []
        self._sample_count = 0
        self._refused_samples = 0
        self._peak_retained_bytes = 0
        self._digest = hashlib.sha256()
        self._degradation: LiveTapeDegradation | None = None
        self._released = False
        self._has_signal = False

    # -- state -------------------------------------------------------------------

    @property
    def has_signal(self) -> bool:
        """Did any sample this tape ever accepted differ from an exact digital zero?

        The tape is the only object that sees every byte of the meeting exactly once, so it is
        the only one that can answer this for free; a reader would have to materialise the
        whole meeting again to ask. It survives `release`, because "this meeting was silence"
        is an accounting fact about audio that is gone, exactly like the digest beside it.

        It is an observation, never a policy: the terminal pass decides what to do about a
        meeting with no signal (it refuses by name rather than decoding zeros, plan §5.2), and
        nothing else here is entitled to that decision.
        """

        return self._has_signal

    @property
    def taping(self) -> bool:
        return self._degradation is None and not self._released

    @property
    def degradation(self) -> LiveTapeDegradation | None:
        return self._degradation

    @property
    def sample_count(self) -> int:
        return self._sample_count

    @property
    def retained_bytes(self) -> int:
        return self._retained_bytes

    @property
    def peak_retained_bytes(self) -> int:
        return self._peak_retained_bytes

    def covers(self, start_sample: int, end_sample: int) -> bool:
        if end_sample <= start_sample:
            return False
        if self._released:
            return False
        return any(low <= start_sample and end_sample <= high for low, high in self._covered)

    def gaps(self, through_sample: int) -> tuple[LiveTapeGap, ...]:
        """Everything in `[0, through_sample)` this tape does not hold -- plan §6 M6's manifest.

        Computed from the intervals actually recorded, so it names a hole and a short tail
        the same way and neither can be inferred away by subtracting two counts.
        """

        return tuple(
            LiveTapeGap(start_sample=start, end_sample=end)
            for start, end in _complement(self._covered, max(0, int(through_sample)))
        )

    def accounting(self, *, through_sample: int) -> CompleteMixedTapeAccounting:
        with self._lock:
            return CompleteMixedTapeAccounting(
                epoch=self.epoch,
                sample_count=self._sample_count,
                through_sample=int(through_sample),
                retained_bytes=self._retained_bytes,
                capacity_bytes=self.capacity_bytes,
                peak_retained_bytes=self._peak_retained_bytes,
                refused_samples=self._refused_samples,
                gaps=self.gaps(through_sample),
                pcm_sha256=self._digest.hexdigest(),
                released=self._released,
                degradation=self._degradation,
            )

    # -- appending ---------------------------------------------------------------

    def append(self, *, start_sample: int, pcm: bytes) -> LiveTapeAppendResult:
        """Retain the meeting's newest mixed audio. Never raises, by D5."""

        with self._lock:
            samples = len(pcm) // PCM16_BYTES_PER_SAMPLE
            if self._released:
                self._refused_samples += samples
                return LiveTapeAppendResult(
                    taping=False, written=False, duplicate=False, degradation=self._degradation
                )
            if self._degradation is not None:
                self._refused_samples += samples
                return LiveTapeAppendResult(
                    taping=False, written=False, duplicate=False, degradation=self._degradation
                )
            if len(pcm) % PCM16_BYTES_PER_SAMPLE:
                self._refused_samples += samples
                return self._degrade(
                    TAPE_FRAME_NOT_ADMISSIBLE,
                    {"condition": "pcm length", "bytes": len(pcm)},
                )
            if start_sample != self._sample_count:
                # The one placement rule: audio goes where the tape ends. A frame that
                # claims a later sample would leave a hole no reader may decode, and one
                # that claims an earlier sample would rewrite audio already digested.
                self._refused_samples += samples
                return self._degrade(
                    TAPE_FRAME_NOT_ADMISSIBLE,
                    {
                        "condition": "non-contiguous",
                        "expected_start_sample": self._sample_count,
                        "received_start_sample": int(start_sample),
                    },
                )
            if not samples:
                return LiveTapeAppendResult(taping=True, written=False, duplicate=False)
            if self._retained_bytes + len(pcm) > self.capacity_bytes:
                self._refused_samples += samples
                return self._degrade(
                    TAPE_CAPACITY_EXHAUSTED,
                    {
                        "capacity_bytes": self.capacity_bytes,
                        "retained_bytes": self._retained_bytes,
                        "requested_bytes": len(pcm),
                    },
                )
            operation = "seek"
            try:
                self._file.seek(0, 2)
                remaining = memoryview(pcm)
                while remaining:
                    operation = "write"
                    written = self._file.write(remaining)
                    if not written:
                        raise OSError("temporary tape write made no progress")
                    remaining = remaining[written:]
                # Buffered files may defer ENOSPC until flush or close. The frame is not
                # part of the tape's accounting until its bytes have crossed that boundary.
                operation = "flush"
                self._file.flush()
            except OSError:
                self._refused_samples += samples
                return self._degrade(
                    TAPE_STORAGE_FAILED,
                    {
                        "operation": operation,
                        "retained_bytes": self._retained_bytes,
                        "requested_bytes": len(pcm),
                    },
                )
            self._retained_bytes += len(pcm)
            self._digest.update(pcm)
            # Established while the audio is in hand and never recomputed. The alternative is
            # scanning tens of megabytes on the stop path of a meeting that is being polled,
            # and -- worse -- scanning audio that has already been released, which would make
            # the answer depend on when it was asked.
            self._has_signal = self._has_signal or not is_digital_silence(pcm)
            self._covered = _merge(self._covered, self._sample_count, self._sample_count + samples)
            self._sample_count += samples
            self._peak_retained_bytes = max(self._peak_retained_bytes, self._retained_bytes)
            return LiveTapeAppendResult(taping=True, written=True, duplicate=False)

    # -- reading -----------------------------------------------------------------

    def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
        """The seam: the mixed PCM of `[start_sample, end_sample)`, or a refusal by name."""

        with self._lock:
            end = self._sample_count if end_sample is None else int(end_sample)
            start = int(start_sample)
            if self._released:
                raise CompleteMixedTapeUnavailable("the complete tape has been released.")
            if self._degradation is not None:
                raise CompleteMixedTapeUnavailable(
                    f"the complete tape stopped: {self._degradation.reason}."
                )
            if not self.covers(start, end):
                raise CompleteMixedTapeUnavailable(
                    f"the complete tape does not cover [{start}, {end})."
                )
            byte_count = (end - start) * PCM16_BYTES_PER_SAMPLE
            try:
                self._file.seek(start * PCM16_BYTES_PER_SAMPLE)
                pcm = self._file.read(byte_count)
            except OSError as exc:
                raise CompleteMixedTapeUnavailable("the complete tape could not be read.") from exc
            if len(pcm) != byte_count:
                raise CompleteMixedTapeUnavailable("the complete tape returned a short read.")
            return pcm

    def write_wav(
        self,
        destination: str | Path,
        *,
        start_sample: int = 0,
        end_sample: int | None = None,
    ) -> int:
        """Stream one complete range to mono PCM16 WAV without materializing it in memory."""

        with self._lock:
            end = self._sample_count if end_sample is None else int(end_sample)
            start = int(start_sample)
            if self._released:
                raise CompleteMixedTapeUnavailable("the complete tape has been released.")
            if self._degradation is not None:
                raise CompleteMixedTapeUnavailable(
                    f"the complete tape stopped: {self._degradation.reason}."
                )
            if not self.covers(start, end):
                raise CompleteMixedTapeUnavailable(
                    f"the complete tape does not cover [{start}, {end})."
                )
            remaining = (end - start) * PCM16_BYTES_PER_SAMPLE
            try:
                self._file.seek(start * PCM16_BYTES_PER_SAMPLE)
                with wave.open(str(Path(destination)), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(PCM16_BYTES_PER_SAMPLE)
                    output.setframerate(self.sample_rate)
                    while remaining:
                        chunk = self._file.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise OSError("temporary tape returned a short read")
                        output.writeframesraw(chunk)
                        remaining -= len(chunk)
            except (OSError, wave.Error) as exc:
                raise CompleteMixedTapeUnavailable(
                    "the complete tape could not be materialized."
                ) from exc
            return end - start

    # -- lifecycle ---------------------------------------------------------------

    def release(self) -> None:
        """Drop the audio and keep the accounting. Idempotent, and never raises."""

        with self._lock:
            if not self._released:
                try:
                    self._file.close()
                except OSError:
                    if self._degradation is None:
                        self._degrade(
                            TAPE_STORAGE_FAILED,
                            {
                                "operation": "close",
                                "retained_bytes": self._retained_bytes,
                            },
                        )
                finally:
                    self._retained_bytes = 0
                    self._released = True

    def _degrade(self, reason: str, detail: Mapping[str, object]) -> LiveTapeAppendResult:
        degradation = LiveTapeDegradation(reason=reason, detail=detail)
        self._degradation = degradation
        _TAPE_LOG.warning(
            "live complete tape degraded: epoch=%s reason=%s detail=%r",
            self.epoch,
            reason,
            dict(detail),
        )
        return LiveTapeAppendResult(
            taping=False, written=False, duplicate=False, degradation=degradation
        )


class LiveCaptureTape(Protocol):
    """One authority-owned capture stage; storage details remain behind its owner."""

    def append_lane_frame(self, frame: LiveV2Frame) -> object: ...

    def append_mixed(
        self,
        *,
        pcm: bytes,
        start_timestamp_ns: int,
        sample_count: int,
        sample_rate: int,
    ) -> object: ...


class LiveCaptureTapeStore(Protocol):
    """Minimal stage lifecycle consumed by the shared transport."""

    def create(self, session_id: str) -> LiveCaptureTape: ...

    def get(self, session_id: str) -> LiveCaptureTape | None: ...

    def release(self, session_id: str) -> LiveCaptureTape | None: ...

    def reap(self, *, active_session_ids: Sequence[str] = ()) -> tuple[str, ...]: ...


class LiveCaptureTapeRecorder:
    """The wired side of the tape: one guard for every call site on the live path.

    Constructed with the audio stage owned by the Account Meeting. `None` keeps capture
    available when durable audio staging is intentionally absent.

    **Nothing here raises.** the capture tape already promises that no *frame* ends a
    meeting, but the store's own calls -- create, release, reap -- touch a filesystem and
    can, and a route that lets a disk error escape ends the meeting with a 500. That would
    be ADR-0003 D5 violated by the very substrate it was written for, so the rule is
    enforced once, here, rather than at each of the eight call sites.
    """

    __slots__ = ("_store",)

    def __init__(self, store: LiveCaptureTapeStore | None):
        self._store = store

    @property
    def enabled(self) -> bool:
        return self._store is not None

    def create(self, session_id: str) -> None:
        if self._store is None:
            return
        try:
            self._store.create(session_id)
        except Exception as exc:  # noqa: BLE001 - D5: a tape never ends a meeting
            self._failed("create", session_id, exc)

    def append_lane_frame(self, session_id: str, frame: LiveV2Frame) -> None:
        """Tee one *acknowledged* lane frame.

        Acknowledged, not received: the tape records what the session accepted, so a frame
        the ingress refused is absent from both the meeting and the tape. A replay the
        ingress re-acks arrives here too and lands as a duplicate, because placement is by
        capture timestamp -- the same reason a retried outbox cannot double-write.
        """

        tape = self._tape(session_id)
        if tape is None:
            return
        try:
            tape.append_lane_frame(frame)
        except Exception as exc:  # noqa: BLE001 - D5
            self._failed("append", session_id, exc)

    def append_mixed(
        self,
        session_id: str,
        *,
        pcm: bytes,
        start_timestamp_ns: int,
        sample_count: int,
        sample_rate: int = LIVE_SAMPLE_RATE,
    ) -> None:
        tape = self._tape(session_id)
        if tape is None:
            return
        try:
            tape.append_mixed(
                pcm=pcm,
                start_timestamp_ns=start_timestamp_ns,
                sample_count=sample_count,
                sample_rate=sample_rate,
            )
        except Exception as exc:  # noqa: BLE001 - D5
            self._failed("append", session_id, exc)

    def release(self, session_id: str) -> None:
        """End this session's tape, on every path that ends the session.

        Including lease expiry and application shutdown: once the mixer is gone no later
        mixed audio may enter the stage.
        """

        if self._store is None:
            return
        try:
            self._store.release(session_id)
        except Exception as exc:  # noqa: BLE001 - D5
            self._failed("release", session_id, exc)

    def reap(self, *, active_session_ids: Sequence[str] = ()) -> tuple[str, ...]:
        if self._store is None:
            return ()
        try:
            return self._store.reap(active_session_ids=active_session_ids)
        except Exception as exc:  # noqa: BLE001 - D5
            self._failed("reap", "-", exc)
            return ()

    def _tape(self, session_id: str) -> LiveCaptureTape | None:
        if self._store is None:
            return None
        try:
            return self._store.get(session_id)
        except Exception as exc:  # noqa: BLE001 - D5
            self._failed("lookup", session_id, exc)
            return None

    @staticmethod
    def _failed(action: str, session_id: str, exc: BaseException) -> None:
        _TAPE_LOG.warning(
            "live session tape %s failed: session_id=%s error=%s: %s",
            action,
            session_id,
            type(exc).__name__,
            exc,
        )


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
