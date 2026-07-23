from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from dataclasses import dataclass
from typing import Any

from moss_transcribe_diarize.transcript_parser import parse_transcript


LIVE_SAMPLE_RATE = 16000
PCM16_BYTES_PER_SAMPLE = 2


class LiveSessionError(RuntimeError):
    pass


class LiveSessionBackpressure(LiveSessionError):
    pass


class LiveSessionClosed(LiveSessionError):
    pass


class LiveSessionFailed(LiveSessionError):
    pass


@dataclass(frozen=True, slots=True)
class AudioFrame:
    sequence: int
    pcm: bytes
    sample_count: int
    sample_rate: int = LIVE_SAMPLE_RATE


@dataclass(frozen=True, slots=True)
class FrameAck:
    sequence: int
    start_sample: int
    end_sample: int
    accepted_samples: int
    retained_samples: int
    frozen_span_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FrozenSpan:
    id: int
    epoch: int
    start_sample: int
    end_sample: int
    reason: str

    @property
    def sample_count(self) -> int:
        return self.end_sample - self.start_sample


@dataclass(frozen=True, slots=True)
class CanonicalResult:
    span_id: int
    epoch: int
    start_sample: int
    end_sample: int
    transcript: str
    identity_confirmed: bool = True


@dataclass(frozen=True, slots=True)
class CanonicalCommit:
    span_id: int
    start_sample: int
    end_sample: int
    transcript: str
    prefix_hash: str


@dataclass(frozen=True, slots=True)
class ProvisionalSuffix:
    generation: int
    start_sample: int
    end_sample: int
    transcript: str


@dataclass(frozen=True, slots=True)
class LiveSnapshot:
    status: str
    epoch: int
    version: int
    accepted_samples: int
    accounted_samples: int
    retained_samples: int
    committed_samples: int
    committed_prefix_hash: str
    committed: tuple[CanonicalCommit, ...]
    provisional: ProvisionalSuffix | None
    next_frame_sequence: int
    frozen_until_sample: int
    pending_span_ids: tuple[int, ...]
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _RetainedFrame:
    sequence: int
    start_sample: int
    end_sample: int


class LiveSession:
    """Default-off live session state machine for ordered 16 kHz PCM."""

    def __init__(
        self,
        *,
        max_retained_samples: int,
        hard_cap_samples: int | None = None,
        session_epoch: int = 0,
    ):
        if max_retained_samples <= 0:
            raise ValueError("max_retained_samples must be positive.")
        if hard_cap_samples is not None and hard_cap_samples <= 0:
            raise ValueError("hard_cap_samples must be positive when provided.")
        self.max_retained_samples = int(max_retained_samples)
        self.hard_cap_samples = None if hard_cap_samples is None else int(hard_cap_samples)
        self._epoch = int(session_epoch)
        self._version = 0
        self._status = "active"
        self._failure_reason: str | None = None
        self._next_frame_sequence = 0
        self._accepted_samples = 0
        self._committed_samples = 0
        self._frozen_until_sample = 0
        self._next_span_id = 0
        self._frames: deque[_RetainedFrame] = deque()
        self._retained_samples = 0
        self._frozen_spans: dict[int, FrozenSpan] = {}
        self._span_order: list[int] = []
        self._pending_results: dict[int, CanonicalResult] = {}
        self._committed: list[CanonicalCommit] = []
        self._prefix_hash = _hash_payload({"schema_version": 1, "prefix": []})
        self._provisional_generation = 0
        self._provisional: ProvisionalSuffix | None = None
        self._waiters: list[asyncio.Event] = []

    @property
    def epoch(self) -> int:
        return self._epoch

    def accept_frame(self, frame: AudioFrame) -> FrameAck:
        self._ensure_accepting()
        _validate_frame(frame)
        if frame.sequence != self._next_frame_sequence:
            raise ValueError(f"expected frame sequence {self._next_frame_sequence}, got {frame.sequence}.")

        self._prune_committed_frames()
        if frame.sample_count > self.max_retained_samples:
            raise LiveSessionBackpressure("frame exceeds live retention capacity.")
        if self._retained_samples + frame.sample_count > self.max_retained_samples:
            raise LiveSessionBackpressure("live retention capacity reached.")

        start_sample = self._accepted_samples
        end_sample = start_sample + frame.sample_count
        self._frames.append(_RetainedFrame(frame.sequence, start_sample, end_sample))
        self._retained_samples += frame.sample_count
        self._accepted_samples = end_sample
        self._next_frame_sequence += 1
        frozen = self._freeze_hard_cap_spans()
        self._bump()
        return FrameAck(
            sequence=frame.sequence,
            start_sample=start_sample,
            end_sample=end_sample,
            accepted_samples=self._accepted_samples,
            retained_samples=self._retained_samples,
            frozen_span_ids=tuple(span.id for span in frozen),
        )

    def begin_provisional(self) -> tuple[int, int, int]:
        self._ensure_accepting_or_closing()
        self._provisional_generation += 1
        return (self._epoch, self._provisional_generation, self._committed_samples)

    def publish_provisional(
        self,
        *,
        epoch: int,
        generation: int,
        start_sample: int,
        end_sample: int,
        transcript: str,
    ) -> bool:
        if epoch != self._epoch or generation != self._provisional_generation:
            return False
        self._ensure_accepting_or_closing()
        if start_sample != self._committed_samples:
            raise ValueError("provisional suffix must start at the committed prefix.")
        if end_sample < start_sample or end_sample > self._accepted_samples:
            raise ValueError("provisional suffix must stay within accepted audio.")
        self._provisional = ProvisionalSuffix(generation, start_sample, end_sample, transcript)
        self._bump()
        return True

    def freeze_until(self, end_sample: int, *, reason: str) -> FrozenSpan:
        self._ensure_accepting_or_closing()
        if end_sample <= self._frozen_until_sample:
            raise ValueError("frozen span end must advance.")
        if end_sample > self._accepted_samples:
            raise ValueError("cannot freeze samples that have not been accepted.")
        return self._freeze_span(end_sample, reason=reason)

    def submit_canonical(self, result: CanonicalResult) -> bool:
        if result.epoch != self._epoch:
            return False
        self._ensure_accepting_or_closing()
        span = self._frozen_spans.get(result.span_id)
        if span is None:
            return False
        if result.start_sample != span.start_sample or result.end_sample != span.end_sample:
            self._fail(f"canonical result does not match frozen span {result.span_id}.")
            raise LiveSessionFailed(self._failure_reason or "canonical result mismatch.")
        self._validate_canonical(result, span)
        self._pending_results[result.span_id] = result
        self._publish_ready_prefix()
        self._bump()
        self._notify_waiters()
        return True

    def snapshot(self) -> LiveSnapshot:
        return LiveSnapshot(
            status=self._status,
            epoch=self._epoch,
            version=self._version,
            accepted_samples=self._accepted_samples,
            accounted_samples=self._committed_samples,
            retained_samples=self._retained_samples,
            committed_samples=self._committed_samples,
            committed_prefix_hash=self._prefix_hash,
            committed=tuple(self._committed),
            provisional=self._provisional,
            next_frame_sequence=self._next_frame_sequence,
            frozen_until_sample=self._frozen_until_sample,
            pending_span_ids=tuple(self._span_order),
            failure_reason=self._failure_reason,
        )

    async def stop(self, deadline: float) -> LiveSnapshot:
        self._ensure_accepting_or_closing()
        self._status = "closing"
        if self._accepted_samples > self._frozen_until_sample:
            self._freeze_span(self._accepted_samples, reason="stop_flush")
        self._bump()
        self._notify_waiters()

        loop = asyncio.get_running_loop()
        end_time = loop.time() + max(0.0, float(deadline))
        while self._committed_samples != self._accepted_samples:
            if self._status == "failed":
                raise LiveSessionFailed(self._failure_reason or "live session failed.")
            remaining = end_time - loop.time()
            if remaining <= 0:
                raise TimeoutError("live session stop deadline expired with unresolved samples.")
            waiter = asyncio.Event()
            self._waiters.append(waiter)
            try:
                await asyncio.wait_for(waiter.wait(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise TimeoutError("live session stop deadline expired with unresolved samples.") from exc
            finally:
                if waiter in self._waiters:
                    self._waiters.remove(waiter)

        self._status = "closed"
        self._provisional = None
        self._prune_committed_frames(force=True)
        self._bump()
        return self.snapshot()

    async def abort(self, reason: str) -> LiveSnapshot:
        if self._status in {"closed", "aborted", "failed"}:
            return self.snapshot()
        self._status = "aborted"
        self._failure_reason = reason
        self._provisional = None
        self._pending_results.clear()
        self._bump()
        self._notify_waiters()
        return self.snapshot()

    def _ensure_accepting(self) -> None:
        if self._status != "active":
            raise LiveSessionClosed(f"live session is {self._status}.")

    def _ensure_accepting_or_closing(self) -> None:
        if self._status not in {"active", "closing"}:
            raise LiveSessionClosed(f"live session is {self._status}.")

    def _freeze_hard_cap_spans(self) -> list[FrozenSpan]:
        if self.hard_cap_samples is None:
            return []
        frozen: list[FrozenSpan] = []
        while self._accepted_samples - self._frozen_until_sample >= self.hard_cap_samples:
            frozen.append(self._freeze_span(self._frozen_until_sample + self.hard_cap_samples, reason="hard_cap"))
        return frozen

    def _freeze_span(self, end_sample: int, *, reason: str) -> FrozenSpan:
        span = FrozenSpan(
            id=self._next_span_id,
            epoch=self._epoch,
            start_sample=self._frozen_until_sample,
            end_sample=end_sample,
            reason=reason,
        )
        self._next_span_id += 1
        self._frozen_until_sample = end_sample
        self._frozen_spans[span.id] = span
        self._span_order.append(span.id)
        return span

    def _validate_canonical(self, result: CanonicalResult, span: FrozenSpan) -> None:
        if not result.identity_confirmed:
            self._fail(f"canonical span {span.id} is missing stable session identity.")
            raise LiveSessionFailed(self._failure_reason or "missing stable session identity.")
        if not result.transcript.strip():
            self._fail(f"canonical span {span.id} returned empty transcript.")
            raise LiveSessionFailed(self._failure_reason or "empty canonical transcript.")
        segments = parse_transcript(result.transcript)
        if not segments:
            self._fail(f"canonical span {span.id} returned zero parsed segments.")
            raise LiveSessionFailed(self._failure_reason or "unparseable canonical transcript.")
        duration = span.sample_count / float(LIVE_SAMPLE_RATE)
        for segment in segments:
            if segment.start < 0 or segment.end > duration:
                self._fail(f"canonical span {span.id} returned timestamps outside frozen span.")
                raise LiveSessionFailed(self._failure_reason or "canonical timestamp bounds failed.")

    def _publish_ready_prefix(self) -> None:
        while self._span_order:
            span_id = self._span_order[0]
            result = self._pending_results.get(span_id)
            if result is None:
                return
            span = self._frozen_spans[span_id]
            if span.start_sample != self._committed_samples:
                return
            self._pending_results.pop(span_id)
            self._span_order.pop(0)
            self._frozen_spans.pop(span_id)
            prefix_hash = _hash_payload(
                {
                    "previous": self._prefix_hash,
                    "span_id": span.id,
                    "start_sample": span.start_sample,
                    "end_sample": span.end_sample,
                    "transcript": result.transcript,
                }
            )
            commit = CanonicalCommit(
                span_id=span.id,
                start_sample=span.start_sample,
                end_sample=span.end_sample,
                transcript=result.transcript,
                prefix_hash=prefix_hash,
            )
            self._committed.append(commit)
            self._committed_samples = span.end_sample
            self._prefix_hash = prefix_hash
            if self._provisional is not None and self._provisional.start_sample < self._committed_samples:
                self._provisional = None
            self._prune_committed_frames()

    def _prune_committed_frames(self, *, force: bool = False) -> None:
        while self._frames and self._frames[0].end_sample <= self._committed_samples:
            frame = self._frames.popleft()
            self._retained_samples -= frame.end_sample - frame.start_sample
            if not force and self._retained_samples <= self.max_retained_samples:
                continue

    def _fail(self, reason: str) -> None:
        self._status = "failed"
        self._failure_reason = reason
        self._provisional = None
        self._notify_waiters()

    def _bump(self) -> None:
        self._version += 1

    def _notify_waiters(self) -> None:
        for waiter in list(self._waiters):
            waiter.set()


def _validate_frame(frame: AudioFrame) -> None:
    if frame.sequence < 0:
        raise ValueError("frame sequence must be non-negative.")
    if frame.sample_rate != LIVE_SAMPLE_RATE:
        raise ValueError(f"live audio must be {LIVE_SAMPLE_RATE} Hz PCM.")
    if frame.sample_count <= 0:
        raise ValueError("frame sample_count must be positive.")
    if len(frame.pcm) != frame.sample_count * PCM16_BYTES_PER_SAMPLE:
        raise ValueError("frame pcm length must match 16-bit mono sample_count.")


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
