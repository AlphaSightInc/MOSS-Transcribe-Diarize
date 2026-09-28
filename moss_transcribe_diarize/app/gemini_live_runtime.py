"""Session-local Gemini engine seam behind the existing Live service contract.

The engine is injected. This phase contains a deterministic fake, not a Google client.
An engine may publish updates from its own worker; `push_audio` must return promptly and
`finish` must await its last live updates before returning the terminal transcript.
"""

from __future__ import annotations

import asyncio
import math
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Protocol, Sequence

from moss_transcribe_diarize.transcript_parser import TranscriptSegment

from .live_service_runtime import (
    LIVE_TERMINAL_SESSION_STATUSES,
    LiveServiceCreateResult,
    LiveServiceDescriptor,
    LiveServiceEvent,
    LiveServiceFailureKind,
    LiveServiceFailureRecord,
    LiveServiceFrameResult,
    LiveServiceRuntime,
    LiveServiceSnapshot,
    LiveServiceStopPending,
)
from .live_session import (
    AudioFrame,
    EffectiveTranscriptSegment,
    LiveSession,
    LiveSessionClosed,
    TextRevisionProposal,
)
from .live_span_bounds import LIVE_SAMPLE_RATE, render_segments
from .live_tape import CompleteMixedTape


@dataclass(frozen=True, slots=True)
class GeminiSegment:
    start_sample: int
    end_sample: int
    text: str
    speaker: str | None = None
    source_lane: str | None = None


@dataclass(frozen=True, slots=True)
class GeminiPreview:
    end_sample: int
    segments: tuple[GeminiSegment, ...]


@dataclass(frozen=True, slots=True)
class GeminiBase:
    through_sample: int
    segments: tuple[GeminiSegment, ...]


@dataclass(frozen=True, slots=True)
class GeminiRolling:
    start_sample: int
    end_sample: int
    segments: tuple[GeminiSegment, ...]


@dataclass(frozen=True, slots=True)
class GeminiRelabel:
    start_sample: int
    end_sample: int
    segments: tuple[GeminiSegment, ...]


GeminiUpdate = GeminiPreview | GeminiBase | GeminiRolling | GeminiRelabel


class GeminiEngine(Protocol):
    """One engine per meeting. All positions are absolute mixed-track sample indices."""

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        """Enqueue accepted 16 kHz mono PCM; publish via the supplied callback."""

    async def finish(self, tape: CompleteMixedTape) -> Sequence[GeminiSegment]:
        """Flush live work, then return the whole-recording transcript."""


class ScriptedGeminiEngine:
    """Offline engine exercising the same publication callback as a provider engine."""

    def __init__(
        self,
        publish: Callable[[GeminiUpdate], None],
        *,
        batches: Sequence[Sequence[GeminiUpdate]],
        terminal: Sequence[GeminiSegment],
    ) -> None:
        self._publish = publish
        self._batches = tuple(tuple(batch) for batch in batches)
        self._terminal = tuple(terminal)
        self._frame_index = 0

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        del start_sample, pcm16
        if self._frame_index < len(self._batches):
            for update in self._batches[self._frame_index]:
                self._publish(update)
        self._frame_index += 1

    async def finish(self, tape: CompleteMixedTape) -> Sequence[GeminiSegment]:
        del tape
        return self._terminal


@dataclass(slots=True)
class _GeminiState:
    session_id: str
    session: LiveSession
    engine: GeminiEngine | None
    tape: CompleteMixedTape | None
    events: deque[LiveServiceEvent]
    next_event_seq: int = 0
    terminal_failure: LiveServiceFailureRecord | None = None
    stop_task: asyncio.Task[LiveServiceSnapshot] | None = None
    terminal_task: asyncio.Task[None] | None = None
    calls_by_kind: dict[str, int] = field(default_factory=dict)
    errors_by_code: dict[str, int] = field(default_factory=dict)
    retries_by_code: dict[str, int] = field(default_factory=dict)
    clamped_words: int = 0
    dropped_words: int = 0
    audio_seconds_sent: float = 0.0
    cost_usd: float = 0.0


class GeminiLiveSnapshot(LiveServiceSnapshot):
    def to_dict(self) -> dict:
        payload = super().to_dict()
        for row in payload["session"]["effective_transcript"]:
            if row.get("source_lane") is None:
                row.pop("source_lane", None)
        return payload


class GeminiLiveRuntime(LiveServiceRuntime):
    """Reuse LiveSession publication and LiveService wire types; replace speech inference."""

    def __init__(
        self,
        *,
        descriptor: LiveServiceDescriptor,
        engine_factory: Callable[[str, Callable[[GeminiUpdate], None], Callable[..., None]], GeminiEngine],
        tape_storage_root: str | Path,
    ) -> None:
        self.descriptor = descriptor
        self._engine_factory = engine_factory
        self._tape_storage_root = Path(tape_storage_root)
        self._sessions: dict[str, _GeminiState] = {}
        self._lock = threading.RLock()
        self._publication_observer = None
        # Phase 2 binds the real finalizer. The sentinel tells Account publication that
        # terminal status must settle after session_closed, just as the MOSS path does.
        self._terminal_finalizer = object()
        self._voiceprint_embedder_identity = None

    def create(self, *, echo_mode: str | None = None, session_id: str | None = None) -> LiveServiceCreateResult:
        if echo_mode is not None and echo_mode not in {"headphones", "speakers"}:
            raise ValueError("echo_mode must be headphones or speakers.")
        with self._lock:
            session_id = session_id or uuid.uuid4().hex
            if session_id in self._sessions:
                raise ValueError("live session id already exists.")
            session = LiveSession(max_retained_samples=self.descriptor.bounds.max_retained_samples)
            tape = (
                CompleteMixedTape(epoch=session.epoch,
                    capacity_bytes=self.descriptor.bounds.max_tape_bytes,
                    storage_root=self._tape_storage_root)
                if self.descriptor.bounds.max_tape_bytes is not None else None
            )
            state = _GeminiState(session_id, session, None, tape,
                                 deque(maxlen=self.descriptor.bounds.max_events))
            self._sessions[session_id] = state
            try:
                state.engine = self._engine_factory(
                    session_id, lambda update: self.publish_update(session_id, update),
                    lambda **usage: self.record_engine_call(session_id, **usage),
                )
            except BaseException:
                self._sessions.pop(session_id)
                if tape is not None:
                    tape.release()
                raise
            self._record_event(state, "session_created", {})
            return LiveServiceCreateResult(session_id, self.descriptor, self._snapshot(state))

    def accept_frame(
        self, session_id: str, frame: AudioFrame, *, retryable_queue_backpressure: bool = False
    ) -> LiveServiceFrameResult:
        del retryable_queue_backpressure
        with self._lock:
            state = self._get(session_id)
            self._raise_terminal(state)
            if state.stop_task is not None:
                raise LiveSessionClosed("live session is stopping; no new frames are accepted.")
            ack = state.session.accept_frame(frame)
            if state.tape is not None:
                state.tape.append(start_sample=ack.start_sample, pcm=frame.pcm)
            self._record_event(state, "frame_accepted", {
                "sequence": frame.sequence, "start_sample": ack.start_sample,
                "end_sample": ack.end_sample, "queued_item_ids": (),
            })
            try:
                assert state.engine is not None
                state.engine.push_audio(ack.start_sample, frame.pcm)
            except Exception as exc:
                self._fail(state, "gemini_live_failed", exc)
                raise
            return LiveServiceFrameResult(ack=ack, queued_item_ids=(), snapshot=self._snapshot(state))

    def publish_update(self, session_id: str, update: GeminiUpdate) -> None:
        """Thread-safe engine callback; each accepted update advances the same public stream."""

        with self._lock:
            state = self._get(session_id)
            if state.terminal_failure is not None or state.session.lifecycle_status in LIVE_TERMINAL_SESSION_STATUSES:
                return
            session = state.session
            try:
                if isinstance(update, GeminiPreview):
                    epoch, generation, start = session.begin_provisional()
                    transcript = _unlabelled_transcript(update.segments, start)
                    if not session.publish_provisional(
                        epoch=epoch, generation=generation, start_sample=start,
                        end_sample=update.end_sample, transcript=transcript,
                    ):
                        return
                    kind = "provisional_published"
                elif isinstance(update, GeminiBase):
                    start = session.snapshot().committed_samples
                    span = session.freeze_until(update.through_sample, reason="gemini_base")
                    transcript = _unlabelled_transcript(update.segments, start)
                    if transcript:
                        outcome = session.submit_unlabeled_canonical(
                            span_id=span.id, epoch=span.epoch, start_sample=start,
                            end_sample=update.through_sample, transcript=transcript,
                        )
                    else:
                        outcome = session.submit_empty_canonical(
                            span_id=span.id, epoch=span.epoch, start_sample=start,
                            end_sample=update.through_sample,
                        )
                    if not outcome.submitted:
                        raise ValueError(f"base commit refused: {outcome.refusal}")
                    kind = "canonical_published"
                elif isinstance(update, GeminiRolling):
                    _register_speakers(session, update.segments)
                    snapshot = session.snapshot()
                    outcome = session.apply_text_revision(TextRevisionProposal(
                        epoch=session.epoch, base_text_revision_version=snapshot.text_revision_version,
                        source="rolling", start_sample=update.start_sample,
                        end_sample=update.end_sample,
                        segments=_surface_segments(update.segments, "rolling"),
                    ))
                    if not outcome.applied:
                        raise ValueError(f"rolling update refused: {outcome.refusal}")
                    kind = "text_revision_applied"
                elif isinstance(update, GeminiRelabel):
                    _register_speakers(session, update.segments)
                    outcome = session.revise_rolling_interval(
                        start_sample=update.start_sample, end_sample=update.end_sample,
                        base_text_revision_version=session.snapshot().text_revision_version,
                        segments=_surface_segments(update.segments, "rolling"),
                    )
                    if not outcome.applied:
                        raise ValueError(f"rolling relabel refused: {outcome.refusal}")
                    kind = "label_revision_applied"
                else:
                    raise TypeError("unknown Gemini engine update")
            except Exception as exc:
                self._fail(state, "gemini_update_failed", exc)
                raise
            self._record_event(state, kind, {"source": "gemini"})

    def record_engine_call(
        self,
        session_id: str,
        *,
        kind: str,
        error_code: str | None = None,
        retry_code: str | None = None,
        clamped_words: int = 0,
        dropped_words: int = 0,
        audio_seconds_sent: float = 0.0,
        cost_usd: float = 0.0,
    ) -> None:
        """Record one provider request attempt, with operational metadata only."""

        for value in (kind, error_code, retry_code):
            if value is not None and not re.fullmatch(r"[A-Za-z0-9_:-]{1,64}", value):
                raise ValueError("engine usage kind and codes must be stable metadata tokens.")
        if any(not isinstance(value, int) or value < 0 for value in (clamped_words, dropped_words)):
            raise ValueError("word-timing anomaly counts must be nonnegative integers.")
        if any(not math.isfinite(value) or value < 0 for value in (audio_seconds_sent, cost_usd)):
            raise ValueError("engine audio seconds and cost must be finite and nonnegative.")
        with self._lock:
            state = self._get(session_id)
            state.calls_by_kind[kind] = state.calls_by_kind.get(kind, 0) + 1
            for counters, code in ((state.errors_by_code, error_code),
                                   (state.retries_by_code, retry_code)):
                if code is not None:
                    counters[code] = counters.get(code, 0) + 1
            state.clamped_words += clamped_words
            state.dropped_words += dropped_words
            state.audio_seconds_sent += audio_seconds_sent
            state.cost_usd += cost_usd

    def engine_diagnostics(self, session_id: str) -> dict[str, object]:
        """Copy one meeting's content-free provider totals for QA and operator harnesses."""

        with self._lock:
            state = self._get(session_id)
            return {
                "calls_by_kind": dict(state.calls_by_kind),
                "errors_by_code": dict(state.errors_by_code),
                "retries_by_code": dict(state.retries_by_code),
                "timing_anomalies": {"clamped": state.clamped_words, "dropped": state.dropped_words},
                "audio_seconds_sent": state.audio_seconds_sent,
                "cost_usd": state.cost_usd,
            }

    def snapshot(self, session_id: str, since_version: int | None = None) -> LiveServiceSnapshot | None:
        with self._lock:
            state = self._get(session_id)
            snapshot = self._snapshot(state)
            if (since_version is not None and snapshot.session.version <= since_version
                and state.terminal_failure is None):
                return None
            return snapshot

    def events(self, session_id: str, since_seq: int = 0) -> tuple[LiveServiceEvent, ...]:
        if since_seq < -1:
            raise ValueError("since_seq must be at least -1.")
        with self._lock:
            return tuple(event for event in self._get(session_id).events if event.seq >= since_seq)

    def _events_with_observation(self, session_id: str, since_seq: int = 0):
        return self.events(session_id, since_seq), time.monotonic_ns()

    def _identity_observations(self, session_id: str) -> tuple[object, ...]:
        self._get(session_id)
        return ()

    def _identity_match_observations(self, session_id: str) -> tuple[object, ...]:
        self._get(session_id)
        return ()

    def _operator_queue_snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            return {"batch": 0, "live_canonical": 0, "live_refinement": 0,
                    "live_provisional": 0,
                    "worker_busy": any(state.terminal_task is not None and not state.terminal_task.done()
                                       for state in self._sessions.values())}

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        with self._lock:
            state = self._get(session_id)
            self._raise_terminal(state)
            if state.stop_task is None:
                self._record_event(state, "stop_requested", {})
                state.stop_task = asyncio.create_task(self._finish_stop(state))
            task = state.stop_task
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, deadline))
        except TimeoutError as exc:
            if task.done():
                return task.result()
            raise LiveServiceStopPending("live service stop deadline expired; drain continues on the server.") from exc

    async def _finish_stop(self, state: _GeminiState) -> LiveServiceSnapshot:
        with self._lock:
            snapshot = state.session.snapshot()
            if snapshot.accepted_samples > snapshot.committed_samples:
                span = state.session.freeze_until(snapshot.accepted_samples, reason="stop_flush")
                outcome = state.session.submit_empty_canonical(
                    span_id=span.id, epoch=span.epoch, start_sample=span.start_sample,
                    end_sample=span.end_sample,
                )
                if not outcome.submitted:
                    raise ValueError(f"stop tail refused: {outcome.refusal}")
        await state.session.stop(1.0)
        with self._lock:
            self._record_event(state, "session_closed", {
                "accepted_samples": state.session.snapshot().accepted_samples,
            })
            if state.tape is None or not state.tape.accounting(
                through_sample=state.session.snapshot().accepted_samples
            ).complete:
                state.session.note_finalization("unavailable")
                self._record_event(state, "terminal_finalization_unavailable", {
                    "outcome": "unavailable", "reason": "complete_tape_unavailable"})
                self._release_tape(state)
            elif state.session.snapshot().accepted_samples == 0:
                state.session.note_finalization("unavailable")
                self._record_event(state, "terminal_finalization_unavailable", {
                    "outcome": "no_transcript", "reason": "digital_silence"})
                self._release_tape(state)
            else:
                state.session.note_finalization("running")
                self._record_event(state, "terminal_finalization_started", {})
                state.terminal_task = asyncio.create_task(self._run_terminal(state))
            return self._snapshot(state)

    async def _run_terminal(self, state: _GeminiState) -> None:
        assert state.tape is not None
        assert state.engine is not None
        try:
            rows = tuple(await state.engine.finish(state.tape))
            with self._lock:
                _register_speakers(state.session, rows)
                snapshot = state.session.snapshot()
                outcome = state.session.apply_text_revision(TextRevisionProposal(
                    epoch=state.session.epoch,
                    base_text_revision_version=snapshot.text_revision_version,
                    source="terminal", start_sample=0,
                    end_sample=snapshot.committed_samples,
                    segments=_surface_segments(rows, "terminal"),
                ))
                if not outcome.applied:
                    raise ValueError(f"terminal revision refused: {outcome.refusal}")
                self._record_event(state, "text_revision_applied", {"source": "terminal"})
                self._record_event(state, "terminal_finalization_completed", {"outcome": "final"})
        except Exception as exc:
            with self._lock:
                state.session.note_finalization("failed")
                self._record_event(state, "terminal_finalization_failed", {
                    "outcome": "decode_failed", "reason": type(exc).__name__,
                })
        finally:
            with self._lock:
                self._release_tape(state)

    async def wait_terminal(self, session_id: str) -> None:
        with self._lock:
            task = self._get(session_id).terminal_task
        if task is not None:
            await task

    async def abort(self, session_id: str, reason: str, *, detail=None) -> LiveServiceSnapshot:
        del detail
        self._fence_session(session_id, reason)
        with self._lock:
            state = self._get(session_id)
            await state.session.abort(reason)
            return self._snapshot(state)

    def _fence_session(self, session_id: str, reason: str, *, detail=None) -> None:
        del detail
        with self._lock:
            state = self._get(session_id)
            if state.terminal_failure is None and state.session.lifecycle_status not in LIVE_TERMINAL_SESSION_STATUSES:
                self._fail(state, "aborted", RuntimeError(reason), kind=LiveServiceFailureKind.TRANSPORT_PACING,
                           event_kind="session_aborted")

    def _get(self, session_id: str) -> _GeminiState:
        try:
            return self._sessions[session_id]
        except KeyError as exc:
            raise KeyError(f"unknown live service session {session_id}") from exc

    def _snapshot(self, state: _GeminiState) -> LiveServiceSnapshot:
        session = state.session.snapshot()
        if state.terminal_failure is not None and session.status not in LIVE_TERMINAL_SESSION_STATUSES:
            session = replace(session, status="failed", failure_reason=state.terminal_failure.message)
        return GeminiLiveSnapshot(
            session_id=state.session_id, descriptor=self.descriptor, session=session,
            pending_work_items=0, terminal_failure=state.terminal_failure,
        )

    def _record_event(self, state: _GeminiState, kind: str, payload: dict) -> None:
        if kind.startswith("terminal_") or kind in {"stop_requested", "session_closed", "session_aborted"}:
            payload = {"runtime_monotonic_ns": time.monotonic_ns(), **payload}
        event = LiveServiceEvent(state.next_event_seq, state.session_id, kind,
                                 state.session.snapshot().version, payload)
        state.events.append(event)
        state.next_event_seq += 1
        if self._publication_observer is not None:
            self._publication_observer(state.session_id, self._snapshot(state), tuple(state.events))

    def _fail(self, state: _GeminiState, code: str, exc: Exception,
              *, kind: LiveServiceFailureKind = LiveServiceFailureKind.INTEGRITY,
              event_kind: str = "terminal_failure") -> None:
        if state.terminal_failure is not None:
            return
        if state.session.snapshot().finalization_status not in {"final", "failed"}:
            state.session.note_finalization("failed")
        state.terminal_failure = LiveServiceFailureRecord(kind=kind, code=code,
            message=str(exc) or type(exc).__name__)
        self._record_event(state, event_kind, {"failure": state.terminal_failure.to_dict()})
        self._release_tape(state)

    def _raise_terminal(self, state: _GeminiState) -> None:
        if state.terminal_failure is not None:
            raise RuntimeError(state.terminal_failure.message)

    def _release_tape(self, state: _GeminiState) -> None:
        if (state.tape is not None and not state.tape.accounting(
            through_sample=state.session.snapshot().accepted_samples
        ).released):
            state.tape.release()
            self._record_event(state, "session_tape_released", state.tape.accounting(
                through_sample=state.session.snapshot().accepted_samples
            ).to_dict())


def _unlabelled_transcript(segments: Sequence[GeminiSegment], start_sample: int) -> str:
    return render_segments(
        (
            TranscriptSegment((row.start_sample - start_sample) / LIVE_SAMPLE_RATE,
                              (row.end_sample - start_sample) / LIVE_SAMPLE_RATE,
                              "S00", row.text)
            for row in segments
        ), lambda _row: "S00",
    )


def _surface_segments(segments: Sequence[GeminiSegment], authority: str) -> tuple[EffectiveTranscriptSegment, ...]:
    return tuple(EffectiveTranscriptSegment(row.start_sample, row.end_sample, row.text,
                                            row.speaker, authority, row.source_lane)
                 for row in segments)


def _register_speakers(session: LiveSession, segments: Sequence[GeminiSegment]) -> None:
    speakers = tuple(dict.fromkeys(row.speaker for row in segments if row.speaker is not None))
    session.register_canonical_speakers(speakers)
