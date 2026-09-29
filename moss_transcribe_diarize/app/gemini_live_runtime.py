"""Session-local Gemini engine seam behind the existing Live service contract.

The engine is injected. Its worker may publish updates; `push_audio` must return promptly
and `finish` must await live updates before returning the terminal transcript.
"""

from __future__ import annotations

import asyncio
import difflib
import math
import re
import tempfile
import threading
import time
import uuid
import wave
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
from .gemini_tentative import GeminiTentativeLabeler
from .live_session import (
    AudioFrame,
    EffectiveTranscriptSegment,
    LiveSession,
    LiveSessionClosed,
    TextRevisionProposal,
)
from .live_span_bounds import LIVE_SAMPLE_RATE, render_segments
from .live_tape import CompleteMixedTape, CompleteMixedTapeUnavailable


class _AccountStageTape:
    """Read-only terminal view over Account's already-owned canonical mixed stage."""

    def __init__(self, stage: object, *, capacity_bytes: int):
        self.stage = stage
        self.capacity_bytes = capacity_bytes
        self._released = False

    @property
    def sample_count(self) -> int:
        try:
            return self.stage.path.stat().st_size // 2
        except OSError:
            return 0

    @property
    def taping(self) -> bool:
        return not self._released and not self.stage.degraded

    def covers(self, start_sample: int, end_sample: int) -> bool:
        return self.taping and 0 <= start_sample < end_sample <= self.sample_count

    def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
        end = self.sample_count if end_sample is None else end_sample
        if not self.covers(start_sample, end):
            raise CompleteMixedTapeUnavailable("Account mixed stage does not cover requested audio")
        with self.stage.path.open("rb") as source:
            source.seek(start_sample * 2)
            pcm = source.read((end - start_sample) * 2)
        if len(pcm) != (end - start_sample) * 2:
            raise CompleteMixedTapeUnavailable("Account mixed stage returned a short read")
        return pcm

    def write_wav(self, destination: str | Path, *, start_sample: int = 0,
                  end_sample: int | None = None) -> int:
        end = self.sample_count if end_sample is None else end_sample
        pcm = self.read(start_sample=start_sample, end_sample=end)
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(LIVE_SAMPLE_RATE)
            wav.writeframes(pcm)
        return end - start_sample

    def accounting(self, *, through_sample: int):
        stage = self
        class Accounting:
            sample_count = stage.sample_count
            released = stage._released
            complete = (not stage.stage.degraded and sample_count == through_sample)
            def to_dict(self):
                return {
                    "sample_count": self.sample_count,
                    "through_sample": through_sample,
                    "retained_bytes": self.sample_count * 2,
                    "capacity_bytes": stage.capacity_bytes,
                    "released": self.released,
                    "complete": self.complete,
                    "degradation": "account_stage_unavailable" if stage.stage.degraded else None,
                    "source": "account_mixed_stage",
                }
        return Accounting()

    def release(self) -> None:
        # Account retains and later settles this canonical stage independently.
        self._released = True


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
    degraded: bool = False


@dataclass(frozen=True, slots=True)
class GeminiRolling:
    start_sample: int
    end_sample: int
    segments: tuple[GeminiSegment, ...]
    observations: tuple[object, ...] = ()
    revision_lanes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GeminiRelabel:
    start_sample: int
    end_sample: int
    segments: tuple[GeminiSegment, ...]


@dataclass(frozen=True, slots=True)
class GeminiTurnBridge:
    prior_start_sample: int
    prior_end_sample: int
    new_end_sample: int
    source_lane: str | None = None


GeminiUpdate = GeminiPreview | GeminiBase | GeminiRolling | GeminiRelabel | GeminiTurnBridge

GEMINI_DEFAULT_ENGINE_SETTINGS = {"speaker_window": "balanced", "cleanup_after_stop": False}
GEMINI_SPEAKER_WINDOW_PRESETS = {"balanced": (15, 90), "economy": (30, 90),
                                 "max": (15, 180)}


def validate_engine_settings(value: object) -> dict[str, object]:
    if value is None:
        return GEMINI_DEFAULT_ENGINE_SETTINGS.copy()
    if not isinstance(value, dict) or set(value) - set(GEMINI_DEFAULT_ENGINE_SETTINGS):
        raise ValueError("engine_settings contains unknown keys or is not an object.")
    settings = {**GEMINI_DEFAULT_ENGINE_SETTINGS, **value}
    if (not isinstance(settings["speaker_window"], str) or
            settings["speaker_window"] not in GEMINI_SPEAKER_WINDOW_PRESETS or
            type(settings["cleanup_after_stop"]) is not bool):
        raise ValueError("engine_settings contains an unsupported value.")
    return settings


class GeminiEngine(Protocol):
    """One engine per meeting. All positions are absolute mixed-track sample indices."""

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        """Enqueue accepted 16 kHz mono PCM; publish via the supplied callback."""

    async def drain_tail(self, deadline: float) -> bool:
        """Try to label the accepted suffix before the session closes."""

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

    async def drain_tail(self, deadline: float) -> bool:
        del deadline
        return False

    async def finish(self, tape: CompleteMixedTape) -> Sequence[GeminiSegment]:
        del tape
        return self._terminal


@dataclass(slots=True)
class _GeminiState:
    session_id: str
    session: LiveSession
    engine: GeminiEngine | None
    tape: CompleteMixedTape | _AccountStageTape | None
    events: deque[LiveServiceEvent]
    engine_settings: dict[str, object] = field(default_factory=dict)
    tentative: GeminiTentativeLabeler | None = None
    tentative_closed: bool = False
    ingress_lock: threading.RLock = field(default_factory=threading.RLock)
    next_event_seq: int = 0
    terminal_failure: LiveServiceFailureRecord | None = None
    stop_task: asyncio.Task[LiveServiceSnapshot] | None = None
    terminal_task: asyncio.Task[None] | None = None
    calls_by_kind: dict[str, int] = field(default_factory=dict)
    errors_by_code: dict[str, int] = field(default_factory=dict)
    retries_by_code: dict[str, int] = field(default_factory=dict)
    clamped_words: int = 0
    dropped_words: int = 0
    repaired_words: int = 0
    mic_words_dropped_by_acoustic_gate: int = 0
    mic_words_dropped_by_text_guard: int = 0
    mic_echo_dropped_by_voice: int = 0
    veto_fired: int = 0
    chunked: bool = False
    audio_seconds_sent: float = 0.0
    cost_usd: float = 0.0
    output_cost_estimate_usd: float = 0.0
    live_list_price_estimate_usd: float = 0.0
    skipped_window_ticks: int = 0
    preview_stall_restarts: int = 0
    coverage_retries: int = 0
    coverage_preview_fallbacks: int = 0
    terminal_coverage_fallbacks: int = 0
    degraded_path_activations: int = 0
    window_lag_samples: list[int] = field(default_factory=list)
    preview_lag_samples: list[int] = field(default_factory=list)
    rolling_frontier: int = 0
    voice_observations: dict[str, object] = field(default_factory=dict)
    voiceprint_errors: int = 0
    f13_relabels: int = 0
    f13_relabel_refused: int = 0
    orphan_speakers_absorbed: int = 0
    orphan_relabel_refused: int = 0
    manually_named_speakers: set[str] = field(default_factory=set)
    lane_counters: dict[str, dict[str, object]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class GeminiLiveSnapshot(LiveServiceSnapshot):
    diagnostics: dict[str, object] | None = None

    def to_dict(self) -> dict:
        payload = LiveServiceSnapshot.to_dict(self)
        payload["engine_diagnostics"] = payload.pop("diagnostics")
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
        voiceprint_encoder: object | None = None,
    ) -> None:
        # The same bound governs our scratch tape and Account's canonical audio stage.
        # PCM16 mono at 16 kHz takes 115.2 MB for the supported 60-minute meeting.
        self.descriptor = replace(
            descriptor, bounds=replace(
                descriptor.bounds,
                max_retained_samples=max(descriptor.bounds.max_retained_samples, 960_000),
                max_tape_bytes=max(descriptor.bounds.max_tape_bytes or 0, 115_200_000),
            ),
        )
        self._engine_factory = engine_factory
        self._tape_storage_root = Path(tape_storage_root)
        self._account_audio_stages = None
        self._voiceprint_encoder = voiceprint_encoder
        self._sessions: dict[str, _GeminiState] = {}
        self._lock = threading.RLock()
        self._publication_observer = None
        # Phase 2 binds the real finalizer. The sentinel tells Account publication that
        # terminal status must settle after session_closed, just as the MOSS path does.
        self._terminal_finalizer = object()
        spec = getattr(voiceprint_encoder, "spec", None)
        self._voiceprint_embedder_identity = None if spec is None else (
            f"{spec.provider}:{spec.revision}", spec.embedding_dimension,
        )

    def bind_account_audio_stages(self, stages: object) -> None:
        """Use Account's reserved mixed stage for HTTP meetings before any create."""
        if self._sessions:
            raise RuntimeError("Account audio stages must bind before meeting creation")
        self._account_audio_stages = stages

    def note_manual_speaker(self, session_id: str, speaker_id: str) -> None:
        with self._lock:
            state = self._sessions.get(session_id)
            if state is not None:
                state.manually_named_speakers.add(speaker_id)

    def create(self, *, echo_mode: str | None = None, session_id: str | None = None,
               engine_settings: object = None) -> LiveServiceCreateResult:
        if echo_mode is not None and echo_mode not in {"headphones", "speakers"}:
            raise ValueError("echo_mode must be headphones or speakers.")
        settings = validate_engine_settings(engine_settings)
        with self._lock:
            session_id = session_id or uuid.uuid4().hex
            if session_id in self._sessions:
                raise ValueError("live session id already exists.")
            session = LiveSession(max_retained_samples=self.descriptor.bounds.max_retained_samples)
            stage = (None if self._account_audio_stages is None
                     else self._account_audio_stages.get(session_id))
            if stage is not None:
                tape = _AccountStageTape(stage, capacity_bytes=self.descriptor.bounds.max_tape_bytes)
            elif self.descriptor.bounds.max_tape_bytes is not None:
                tape = CompleteMixedTape(epoch=session.epoch,
                    capacity_bytes=self.descriptor.bounds.max_tape_bytes,
                    storage_root=self._tape_storage_root)
            else:
                tape = None
            state = _GeminiState(session_id, session, None, tape,
                                 deque(maxlen=self.descriptor.bounds.max_events), settings,
                                 GeminiTentativeLabeler(self._voiceprint_encoder)
                                 if self._voiceprint_encoder is not None else None)
            self._sessions[session_id] = state
            try:
                factory_args = (session_id, lambda update: self.publish_update(session_id, update),
                                lambda **usage: self.record_engine_call(session_id, **usage))
                state.engine = (self._engine_factory(*factory_args, settings) if engine_settings is not None
                                else self._engine_factory(*factory_args))
            except BaseException:
                self._sessions.pop(session_id)
                if state.tentative is not None:
                    state.tentative.close()
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
        with state.ingress_lock:
            with self._lock:
                self._raise_terminal(state)
                if state.stop_task is not None:
                    raise LiveSessionClosed("live session is stopping; no new frames are accepted.")
                ack = state.session.accept_frame(frame)
                if isinstance(state.tape, CompleteMixedTape):
                    state.tape.append(start_sample=ack.start_sample, pcm=frame.pcm)
                elif isinstance(state.tape, _AccountStageTape) and not frame.lane_pcm:
                    state.tape.stage.append_mixed(
                        pcm=frame.pcm, start_timestamp_ns=ack.start_sample * 1_000_000_000 // LIVE_SAMPLE_RATE,
                        sample_count=frame.sample_count, sample_rate=frame.sample_rate,
                    )
                self._record_event(state, "frame_accepted", {
                    "sequence": frame.sequence, "start_sample": ack.start_sample,
                    "end_sample": ack.end_sample, "queued_item_ids": (),
                })
            try:
                if state.tentative is not None:
                    for lane, pcm in (frame.lane_pcm or (("system", frame.pcm),)):
                        state.tentative.accept_audio(lane, ack.start_sample, pcm)
                assert state.engine is not None
                push_lanes = getattr(state.engine, "push_lanes", None)
                if frame.lane_pcm and callable(push_lanes):
                    push_lanes(ack.start_sample, frame.lane_pcm)
                else:
                    state.engine.push_audio(ack.start_sample, frame.pcm)
            except Exception as exc:
                with self._lock:
                    self._fail(state, "gemini_live_failed", exc)
                raise
            with self._lock:
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
                    if update.end_sample < start:
                        return
                    segments = _trim_committed_preview(
                        update.segments, session.snapshot().effective_transcript)
                    transcript = _unlabelled_transcript(segments, start)
                    spans = ()
                    if state.tentative is not None:
                        spans = tuple(span for lane in dict.fromkeys(
                            row.source_lane or "system" for row in segments)
                            for span in state.tentative.spans(lane, start, update.end_sample))
                    preview_segments = tuple({
                        "start_sample": row.start_sample, "end_sample": row.end_sample,
                        "text": row.text, "source_lane": row.source_lane or "system",
                        "tentative_speaker": _tentative_speaker(row, spans),
                    } for row in segments)
                    if not session.publish_provisional(
                        epoch=epoch, generation=generation, start_sample=start,
                        end_sample=update.end_sample, transcript=transcript,
                        tentative_spans=spans, segments=preview_segments,
                    ):
                        return
                    kind = "provisional_published"
                    state.preview_lag_samples.append(max(0, session.snapshot().accepted_samples - update.end_sample))
                elif isinstance(update, GeminiBase):
                    if update.degraded:
                        state.degraded_path_activations += 1
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
                        revision_lanes=update.revision_lanes,
                    ))
                    if not outcome.applied:
                        raise ValueError(f"rolling update refused: {outcome.refusal}")
                    kind = "text_revision_applied"
                    state.rolling_frontier = max(state.rolling_frontier, update.end_sample)
                    state.window_lag_samples.append(max(0, session.snapshot().accepted_samples - state.rolling_frontier))
                    for observation in update.observations:
                        state.voice_observations.setdefault(observation.speaker_label, observation)
                    if state.tentative is not None:
                        lanes_by_speaker = {row.speaker: row.source_lane or "system"
                                            for row in update.segments if row.speaker is not None}
                        for observation in update.observations:
                            lane = lanes_by_speaker.get(observation.speaker_label)
                            if lane is not None:
                                state.tentative.observe((observation,), lane=lane)
                    new_voiceprints = self._observe_voiceprints(state, update.segments)
                    if state.tentative is not None:
                        for lane, observation in new_voiceprints:
                            state.tentative.observe((observation,), lane=lane)
                elif isinstance(update, GeminiRelabel):
                    _register_speakers(session, update.segments)
                    lane = update.segments[0].source_lane if update.segments else None
                    speakerless = sum(1 for row in session.snapshot().effective_transcript
                                      if row.authority == "rolling" and row.canonical_speaker is None
                                      and row.source_lane == lane
                                      and row.start_sample >= update.start_sample
                                      and row.end_sample <= update.end_sample)
                    outcome = session.revise_rolling_interval(
                        start_sample=update.start_sample, end_sample=update.end_sample,
                        base_text_revision_version=session.snapshot().text_revision_version,
                        segments=_surface_segments(update.segments, "rolling"),
                        source_lane=lane,
                    )
                    if not outcome.applied:
                        state.f13_relabel_refused += 1
                        return
                    state.f13_relabels += speakerless
                    new_voiceprints = self._observe_voiceprints(state, update.segments)
                    if state.tentative is not None:
                        for lane, observation in new_voiceprints:
                            state.tentative.observe((observation,), lane=lane)
                    kind = "label_revision_applied"
                elif isinstance(update, GeminiTurnBridge):
                    outcome = session.bridge_rolling_turn(
                        prior_start_sample=update.prior_start_sample,
                        prior_end_sample=update.prior_end_sample,
                        new_end_sample=update.new_end_sample,
                        source_lane=update.source_lane,
                        base_text_revision_version=session.snapshot().text_revision_version,
                    )
                    if not outcome.applied:
                        raise ValueError(f"rolling turn bridge refused: {outcome.refusal}")
                    kind = "turn_bridge_applied"
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
        repaired_words: int = 0,
        acoustic_gate_dropped_words: int = 0,
        text_guard_dropped_words: int = 0,
        mic_echo_dropped_by_voice: int = 0,
        veto_fired: int = 0,
        chunked: bool = False,
        audio_seconds_sent: float = 0.0,
        cost_usd: float = 0.0,
        output_cost_estimate_usd: float = 0.0,
        count_call: bool = True,
        cost_basis: str = "provider_usage",
        skipped_window_ticks: int = 0,
        preview_stall_restarts: int = 0,
        coverage_retry: int = 0,
        coverage_preview_fallbacks: int = 0,
        terminal_coverage_fallbacks: int = 0,
    ) -> None:
        """Record one provider request attempt, with operational metadata only."""

        for value in (kind, error_code, retry_code):
            if value is not None and not re.fullmatch(r"[A-Za-z0-9_:-]{1,64}", value):
                raise ValueError("engine usage kind and codes must be stable metadata tokens.")
        if any(not isinstance(value, int) or value < 0
               for value in (clamped_words, dropped_words, repaired_words, skipped_window_ticks,
                             preview_stall_restarts, coverage_retry, coverage_preview_fallbacks,
                             terminal_coverage_fallbacks,
                             acoustic_gate_dropped_words, text_guard_dropped_words,
                             mic_echo_dropped_by_voice, veto_fired)):
            raise ValueError("word-timing anomaly counts must be nonnegative integers.")
        if any(not math.isfinite(value) or value < 0 for value in
               (audio_seconds_sent, cost_usd, output_cost_estimate_usd)):
            raise ValueError("engine audio seconds and cost must be finite and nonnegative.")
        if (not isinstance(count_call, bool) or not isinstance(chunked, bool)
                or cost_basis not in {"provider_usage", "list_price_estimate"}):
            raise ValueError("engine call count and cost basis must be operational metadata.")
        with self._lock:
            state = self._get(session_id)
            if count_call:
                state.calls_by_kind[kind] = state.calls_by_kind.get(kind, 0) + 1
            for counters, code in ((state.errors_by_code, error_code),
                                   (state.retries_by_code, retry_code)):
                if code is not None:
                    counters[code] = counters.get(code, 0) + 1
            state.clamped_words += clamped_words
            state.dropped_words += dropped_words
            state.repaired_words += repaired_words
            state.mic_words_dropped_by_acoustic_gate += acoustic_gate_dropped_words
            state.mic_words_dropped_by_text_guard += text_guard_dropped_words
            state.mic_echo_dropped_by_voice += mic_echo_dropped_by_voice
            state.veto_fired += veto_fired
            state.chunked = state.chunked or chunked
            state.skipped_window_ticks += skipped_window_ticks
            state.preview_stall_restarts += preview_stall_restarts
            state.coverage_retries += coverage_retry
            state.coverage_preview_fallbacks += coverage_preview_fallbacks
            state.terminal_coverage_fallbacks += terminal_coverage_fallbacks
            state.audio_seconds_sent += audio_seconds_sent
            state.cost_usd += cost_usd
            state.output_cost_estimate_usd += output_cost_estimate_usd
            if cost_basis == "list_price_estimate":
                state.live_list_price_estimate_usd += cost_usd
            lane, separator, lane_kind = kind.partition("_")
            if separator and lane in {"system", "microphone"}:
                totals = state.lane_counters.setdefault(lane, {
                    "calls_by_kind": {}, "errors_by_code": {}, "retries_by_code": {},
                    "timing_anomalies": {"clamped": 0, "dropped": 0},
                    "repaired_words": 0, "chunked": False,
                    "mic_words_dropped_by_acoustic_gate": 0,
                    "mic_words_dropped_by_text_guard": 0,
                    "mic_echo_dropped_by_voice": 0, "veto_fired": 0,
                    "audio_seconds_sent": 0.0, "cost_usd": 0.0,
                    "output_cost_estimate_usd": 0.0,
                    "skipped_window_ticks": 0})
                totals.setdefault("preview_stall_restarts", 0)
                totals.setdefault("coverage_retries", 0)
                totals.setdefault("coverage_preview_fallbacks", 0)
                totals.setdefault("terminal_coverage_fallbacks", 0)
                if count_call:
                    calls = totals["calls_by_kind"]
                    calls[lane_kind] = calls.get(lane_kind, 0) + 1
                for key, code in (("errors_by_code", error_code),
                                  ("retries_by_code", retry_code)):
                    if code is not None:
                        codes = totals[key]
                        codes[code] = codes.get(code, 0) + 1
                totals["timing_anomalies"]["clamped"] += clamped_words
                totals["timing_anomalies"]["dropped"] += dropped_words
                totals["repaired_words"] += repaired_words
                totals["mic_words_dropped_by_acoustic_gate"] += acoustic_gate_dropped_words
                totals["mic_words_dropped_by_text_guard"] += text_guard_dropped_words
                totals["mic_echo_dropped_by_voice"] += mic_echo_dropped_by_voice
                totals["veto_fired"] += veto_fired
                totals["chunked"] = totals["chunked"] or chunked
                totals["audio_seconds_sent"] += audio_seconds_sent
                totals["cost_usd"] += cost_usd
                totals["output_cost_estimate_usd"] += output_cost_estimate_usd
                totals["skipped_window_ticks"] += skipped_window_ticks
                totals["preview_stall_restarts"] += preview_stall_restarts
                totals["coverage_retries"] += coverage_retry
                totals["coverage_preview_fallbacks"] += coverage_preview_fallbacks
                totals["terminal_coverage_fallbacks"] += terminal_coverage_fallbacks

    def engine_diagnostics(self, session_id: str) -> dict[str, object]:
        """Copy one meeting's content-free provider totals for QA and operator harnesses."""

        with self._lock:
            state = self._get(session_id)
            return {
                "engine_settings": dict(state.engine_settings),
                **(state.tentative.diagnostics() if state.tentative is not None else {
                    "tentative_shown_s": 0.0, "tentative_abstained_s": 0.0,
                    "tentative_embed_p50_ms": None, "tentative_embed_p95_ms": None,
                    "tentative_embed_wall_s": 0.0, "tentative_busy_ticks": 0}),
                "calls_by_kind": dict(state.calls_by_kind),
                "errors_by_code": dict(state.errors_by_code),
                "retries_by_code": dict(state.retries_by_code),
                "timing_anomalies": {"clamped": state.clamped_words, "dropped": state.dropped_words},
                "repaired_words": state.repaired_words,
                "mic_words_dropped_by_acoustic_gate": state.mic_words_dropped_by_acoustic_gate,
                "mic_words_dropped_by_text_guard": state.mic_words_dropped_by_text_guard,
                "mic_echo_dropped_by_voice": state.mic_echo_dropped_by_voice,
                "veto_fired": state.veto_fired,
                "chunked": state.chunked,
                "audio_seconds_sent": state.audio_seconds_sent,
                "cost_usd": state.cost_usd,
                "output_cost_estimate_usd": state.output_cost_estimate_usd,
                "cost_usd_basis": ("provider_usage_plus_live_list_price_estimate"
                                   if state.live_list_price_estimate_usd else "provider_usage"),
                "live_list_price_estimate_usd": state.live_list_price_estimate_usd,
                "skipped_window_ticks": state.skipped_window_ticks,
                "preview_stall_restarts": state.preview_stall_restarts,
                "coverage_retries": state.coverage_retries,
                "coverage_preview_fallbacks": state.coverage_preview_fallbacks,
                "terminal_coverage_fallbacks": state.terminal_coverage_fallbacks,
                "degraded_path_activations": state.degraded_path_activations,
                "window_lag_seconds": _lag_summary(state.window_lag_samples),
                "preview_lag_seconds": _lag_summary(state.preview_lag_samples),
                "voiceprint_errors": state.voiceprint_errors,
                "f13_relabels": state.f13_relabels,
                "f13_relabel_refused": state.f13_relabel_refused,
                "orphan_speakers_absorbed": state.orphan_speakers_absorbed,
                "orphan_relabel_refused": state.orphan_relabel_refused,
                "lanes": {lane: {
                    key: (dict(value) if isinstance(value, dict) else value)
                    for key, value in totals.items()}
                    for lane, totals in state.lane_counters.items()},
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
        with self._lock:
            return tuple(self._get(session_id).voice_observations.values())

    def _identity_match_observations(self, session_id: str) -> tuple[object, ...]:
        return self._identity_observations(session_id)

    def _observe_voiceprints(
        self, state: _GeminiState, segments: Sequence[GeminiSegment]
    ) -> tuple[tuple[str, object], ...]:
        encoder = self._voiceprint_encoder
        tape = state.tape
        if encoder is None or tape is None:
            return ()
        from .live_provider_bundle import LiveSpeakerJournalObservation
        spec = encoder.spec
        seeded: list[tuple[str, object]] = []
        grouped: dict[str, list[GeminiSegment]] = {}
        for row in segments:
            if row.speaker is not None and row.end_sample > row.start_sample:
                grouped.setdefault(row.speaker, []).append(row)
        for speaker, rows in grouped.items():
            if speaker in state.voice_observations:
                continue
            rows.sort(key=lambda row: row.start_sample)
            lane_tape = getattr(state.engine, "lane_tape", None)
            source_tape = (lane_tape(rows[0].source_lane)
                           if rows[0].source_lane in {"system", "microphone"}
                           and callable(lane_tape) else tape)
            start = end = 0
            for row in rows:
                if start == end or row.start_sample > end + LIVE_SAMPLE_RATE // 2:
                    start, end = row.start_sample, row.end_sample
                else:
                    end = max(end, row.end_sample)
                if end - start >= 2 * LIVE_SAMPLE_RATE:
                    break
            if end - start < 2 * LIVE_SAMPLE_RATE or not source_tape.covers(start, end):
                continue
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", dir=self._tape_storage_root) as wav:
                    source_tape.write_wav(wav.name, start_sample=start, end_sample=end)
                    vector = tuple(float(value) for value in encoder.embed(
                        wav.name, [(0.0, (end - start) / LIVE_SAMPLE_RATE)]))
                if len(vector) != spec.embedding_dimension or any(not math.isfinite(v) for v in vector):
                    raise ValueError("voiceprint encoder returned invalid vector")
                observation = LiveSpeakerJournalObservation(
                    speaker_label=speaker, centroid=vector,
                    sample_seconds=(end - start) / LIVE_SAMPLE_RATE,
                    exemplar_count=1, provisional=False,
                    embedder_id=f"{spec.provider}:{spec.revision}",
                    embedder_state_sha=spec.state_sha256,
                )
                state.voice_observations[speaker] = observation
                seeded.append((rows[0].source_lane or "system", observation))
            except Exception:
                state.voiceprint_errors += 1
        return tuple(seeded)

    def _operator_queue_snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            return {"batch": 0, "live_canonical": 0, "live_refinement": 0,
                    "live_provisional": 0,
                    "worker_busy": any(state.terminal_task is not None and not state.terminal_task.done()
                                       for state in self._sessions.values())}

    async def stop(self, session_id: str, deadline: float) -> LiveServiceSnapshot:
        with self._lock:
            state = self._get(session_id)
        with state.ingress_lock:
            with self._lock:
                self._raise_terminal(state)
                if state.stop_task is None:
                    self._record_event(state, "stop_requested", {})
                    state.stop_task = asyncio.create_task(self._finish_stop(state, deadline))
                task = state.stop_task
        try:
            return await asyncio.wait_for(asyncio.shield(task), timeout=max(0.0, deadline))
        except TimeoutError as exc:
            if task.done():
                return task.result()
            raise LiveServiceStopPending("live service stop deadline expired; drain continues on the server.") from exc

    async def _finish_stop(self, state: _GeminiState, deadline: float) -> LiveServiceSnapshot:
        drained = False
        if state.engine is not None and deadline > 0:
            try:
                drained = await asyncio.wait_for(state.engine.drain_tail(deadline), timeout=deadline)
            except Exception:
                pass  # Preserve the existing empty-base Stop fallback.
        with self._lock:
            self._record_event(state, "stop_tail_drain", {"drained": drained})
            snapshot = state.session.snapshot()
            if snapshot.accepted_samples > snapshot.committed_samples:
                span = state.session.freeze_until(snapshot.accepted_samples, reason="stop_flush")
                outcome = state.session.submit_empty_canonical(
                    span_id=span.id, epoch=span.epoch, start_sample=span.start_sample,
                    end_sample=span.end_sample,
                )
                if not outcome.submitted:
                    raise ValueError(f"stop tail refused: {outcome.refusal}")
        await self._final_relabel_speakerless(state)
        if not state.engine_settings["cleanup_after_stop"]:
            await self._absorb_orphan_speakers(state)
        await state.session.stop(1.0)
        with self._lock:
            self._record_event(state, "session_closed", {
                "accepted_samples": state.session.snapshot().accepted_samples,
            })
            if (not state.engine_settings["cleanup_after_stop"] and
                    state.session.snapshot().accepted_samples > 0):
                before = state.session.snapshot()
                outcome = state.session.apply_text_revision(TextRevisionProposal(
                    epoch=state.session.epoch,
                    base_text_revision_version=before.text_revision_version,
                    source="terminal", start_sample=0,
                    end_sample=before.committed_samples,
                    segments=tuple(replace(row, authority="terminal")
                                   for row in before.effective_transcript),
                ))
                if not outcome.applied:
                    raise ValueError(f"live final revision refused: {outcome.refusal}")
                self._record_event(state, "text_revision_applied", {
                    "source": "live", "start_sample": 0,
                    "end_sample": before.committed_samples,
                    "finalization_status": "final",
                })
                self._record_event(state, "terminal_finalization_completed", {"outcome": "final"})
                closer = getattr(state.engine, "close", None)
                if callable(closer):
                    closer()
                self._release_tape(state)
            elif state.tape is None or not state.tape.taping or not state.tape.accounting(
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

    async def _final_relabel_speakerless(self, state: _GeminiState) -> None:
        """Use the saved lane audio for rows that the final live window could not name."""
        if self._voiceprint_encoder is None or state.tape is None or not state.voice_observations:
            return
        from .gemini_continuity_registry import _cosine
        rows = tuple(row for row in state.session.snapshot().effective_transcript
                     if row.authority == "rolling" and row.canonical_speaker is None)
        for row in rows:
            candidates = ((speaker, observation.centroid)
                          for speaker, observation in state.voice_observations.items()
                          if (row.source_lane is None or
                              (row.source_lane == "microphone") ==
                              (speaker.startswith("local-") or speaker == "speaker-microphone")))
            try:
                vector = await self._fingerprint_row(state, row)
                cosine, speaker = max(((_cosine(vector, centroid), speaker)
                                       for speaker, centroid in candidates), default=(-1.0, None))
                if cosine >= .46 and speaker is not None:
                    self.publish_update(state.session_id, GeminiRelabel(
                        row.start_sample, row.end_sample,
                        (GeminiSegment(row.start_sample, row.end_sample, row.text,
                                       speaker, row.source_lane),)))
            except Exception:
                state.voiceprint_errors += 1

    async def _fingerprint_row(self, state: _GeminiState,
                               row: EffectiveTranscriptSegment) -> Sequence[float]:
        if self._voiceprint_encoder is None or state.tape is None:
            raise ValueError("saved-audio fingerprint unavailable")
        lane_tape = getattr(state.engine, "lane_tape", None)
        tape = lane_tape(row.source_lane) if callable(lane_tape) and row.source_lane else state.tape
        pcm = tape.read(start_sample=row.start_sample, end_sample=row.end_sample)
        with tempfile.NamedTemporaryFile(suffix=".wav") as wav_file:
            with wave.open(wav_file.name, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(LIVE_SAMPLE_RATE)
                wav.writeframes(pcm)
            return await asyncio.to_thread(
                self._voiceprint_encoder.embed, wav_file.name,
                [(0.0, (row.end_sample - row.start_sample) / LIVE_SAMPLE_RATE)])

    async def _absorb_orphan_speakers(self, state: _GeminiState) -> None:
        """Resolve short, unnamed canonical IDs before saving the live transcript."""
        from .gemini_continuity_registry import _cosine
        rows = tuple(row for row in state.session.snapshot().effective_transcript
                     if row.authority == "rolling" and row.canonical_speaker is not None)
        totals: dict[str, int] = {}
        lanes: dict[str, set[str | None]] = {}
        for row in rows:
            speaker = row.canonical_speaker
            assert speaker is not None
            totals[speaker] = totals.get(speaker, 0) + row.end_sample - row.start_sample
            lanes.setdefault(speaker, set()).add(row.source_lane)
        minimum = 2 * LIVE_SAMPLE_RATE
        established = {speaker for speaker, samples in totals.items() if samples >= minimum}
        orphans = {speaker for speaker, samples in totals.items()
                   if samples < minimum and speaker not in state.manually_named_speakers}
        for orphan in sorted(orphans):
            matched = False
            for row in (row for row in rows if row.canonical_speaker == orphan):
                target = None
                candidates = ((speaker, state.voice_observations[speaker].centroid)
                              for speaker in established if row.source_lane in lanes[speaker]
                              and speaker in state.voice_observations)
                try:
                    vector = await self._fingerprint_row(state, row)
                    cosine, nearest = max(((_cosine(vector, centroid), speaker)
                                           for speaker, centroid in candidates),
                                          default=(-1.0, None))
                    if cosine >= .46:
                        target = nearest
                except Exception:
                    state.voiceprint_errors += 1
                refused_before = state.f13_relabel_refused
                self.publish_update(state.session_id, GeminiRelabel(
                    row.start_sample, row.end_sample,
                    (GeminiSegment(row.start_sample, row.end_sample, row.text,
                                   target, row.source_lane),)))
                if state.f13_relabel_refused > refused_before:
                    state.orphan_relabel_refused += 1
                elif target is not None:
                    matched = True
            remaining = any(row.canonical_speaker == orphan
                            for row in state.session.snapshot().effective_transcript)
            if matched and not remaining:
                state.orphan_speakers_absorbed += 1

    async def _run_terminal(self, state: _GeminiState) -> None:
        assert state.tape is not None
        assert state.engine is not None
        try:
            rows = tuple(await state.engine.finish(state.tape))
            with self._lock:
                from .live_transcript_convergence import terminal_speaker_mapping
                before = state.session.snapshot()
                mapping = {}
                for lane in dict.fromkeys(row.source_lane for row in rows):
                    surface = tuple(s for s in before.effective_transcript
                                    if s.source_lane == lane)
                    speakers = tuple(dict.fromkeys(s.canonical_speaker for s in surface
                                                   if s.canonical_speaker is not None))
                    mapping.update(terminal_speaker_mapping(
                        tuple((row.speaker, row.start_sample, row.end_sample, row.text)
                              for row in rows if row.speaker is not None
                              and row.source_lane == lane),
                        base_surface=surface, canonical_speakers=speakers))
                next_id = 1
                for label in dict.fromkeys(row.speaker for row in rows if row.speaker is not None):
                    if label not in mapping:
                        while f"speaker-{next_id:04d}" in before.identity_snapshot.canonical_speakers or f"speaker-{next_id:04d}" in mapping.values():
                            next_id += 1
                        mapping[label] = f"speaker-{next_id:04d}"
                        next_id += 1
                rows = tuple(replace(row, speaker=mapping.get(row.speaker) if row.speaker is not None else None)
                             for row in rows)
                for lane, start, end in getattr(state.engine, "terminal_coverage_gaps", ()):
                    rows += tuple(GeminiSegment(
                        max(row.start_sample, start), min(row.end_sample, end), row.text,
                        row.canonical_speaker, row.source_lane)
                        for row in before.effective_transcript
                        if row.source_lane == lane and row.end_sample > start
                        and row.start_sample < end)
                rows = tuple(sorted(rows, key=lambda row: (row.start_sample, row.end_sample)))
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
                self._record_event(state, "text_revision_applied", {
                    "source": "terminal", "start_sample": 0,
                    "end_sample": snapshot.committed_samples,
                    "finalization_status": "final",
                })
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
        # One final rolling window can cover the entire uncovered accepted suffix.
        # The recorded rolling frontier moves only after the revision succeeds.
        rolling_pending = int(session.status == "active" and
                              state.rolling_frontier < session.accepted_samples)
        return GeminiLiveSnapshot(
            session_id=state.session_id, descriptor=self.descriptor, session=session,
            pending_work_items=rolling_pending, terminal_failure=state.terminal_failure,
            diagnostics=self.engine_diagnostics(state.session_id),
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
        close = getattr(state.engine, "close", None)
        if callable(close):
            close()
        self._release_tape(state)

    def _raise_terminal(self, state: _GeminiState) -> None:
        if state.terminal_failure is not None:
            raise RuntimeError(state.terminal_failure.message)

    def _release_tape(self, state: _GeminiState) -> None:
        if state.tentative is not None and not state.tentative_closed:
            state.tentative.close()
            state.tentative_closed = True
        if (state.tape is not None and not state.tape.accounting(
            through_sample=state.session.snapshot().accepted_samples
        ).released):
            state.tape.release()
            self._record_event(state, "session_tape_released", state.tape.accounting(
                through_sample=state.session.snapshot().accepted_samples
            ).to_dict())


def _tentative_speaker(row: GeminiSegment, spans: Sequence[dict[str, object]]) -> str | None:
    lane = row.source_lane or "system"
    best = max(((min(row.end_sample, int(span["end_sample"])) -
                 max(row.start_sample, int(span["start_sample"])), str(span["speaker"]))
                for span in spans if span["source_lane"] == lane), default=(0, ""))
    return best[1] if best[0] > 0 else None


def _unlabelled_transcript(segments: Sequence[GeminiSegment], start_sample: int) -> str:
    return render_segments(
        (
            TranscriptSegment((row.start_sample - start_sample) / LIVE_SAMPLE_RATE,
                              (row.end_sample - start_sample) / LIVE_SAMPLE_RATE,
                              "S00", row.text)
            for row in segments
        ), lambda _row: "S00",
    )


_PREVIEW_NUMBERS = {word: str(index) for index, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen "
    "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_PREVIEW_WORD = re.compile(r"[^\W_\d]+|\d+")


def _trim_committed_preview(
    segments: Sequence[GeminiSegment], committed: Sequence[EffectiveTranscriptSegment]
) -> tuple[GeminiSegment, ...]:
    """Remove a W3 chunk's already committed head, using only its capture lane."""
    tails: dict[str | None, list[str]] = {}
    result = []
    for segment in segments:
        if segment.source_lane not in tails:
            parts = []
            count = 0
            for row in reversed(committed):
                if row.source_lane != segment.source_lane:
                    continue
                parts.append(row.text)
                count += len(_PREVIEW_WORD.findall(row.text))
                if count >= 60:
                    break
            tail = " ".join(reversed(parts))
            tails[segment.source_lane] = [
                _PREVIEW_NUMBERS.get(word, word)
                for word in _PREVIEW_WORD.findall(tail.casefold())][-60:]
        matches = list(_PREVIEW_WORD.finditer(segment.text.casefold()))
        words = [_PREVIEW_NUMBERS.get(match.group(), match.group()) for match in matches]
        tail = tails[segment.source_lane]
        blocks = [block for block in difflib.SequenceMatcher(
            None, tail, words, autojunk=False
        ).get_matching_blocks() if block.size]
        # Only a near-contiguous run anchored at the chunk's head counts as repeated speech:
        # scattered common words ("and", "you", "the") also match and must not trim new words.
        # Small insertions/deletions between the two models' wording are allowed (gaps of up
        # to 8 words); the run must still be dense (>= 60 % of its span matched).
        chain_end = matched = 0
        first = previous = None
        for block in blocks:
            if previous is None:
                if block.b > 3:
                    break
                first = block
            elif (block.b - (previous.b + previous.size) > 8
                  or block.a - (previous.a + previous.size) > 8):
                break
            matched += block.size
            chain_end = block.b + block.size
            previous = block
        dense = first is not None and matched >= 0.6 * (chain_end - first.b)
        repeats_tail_end = previous is not None and previous.a + previous.size >= len(tail) - 3
        repeats_whole_chunk = previous is not None and chain_end >= len(words) - 1
        text = segment.text
        if matched >= 5 and dense and (repeats_tail_end or repeats_whole_chunk):
            text = text[matches[chain_end - 1].end():]
            text = text.lstrip(" \t\r\n,.;:!?")
        if text:
            result.append(replace(segment, text=text))
    return tuple(result)


def _surface_segments(segments: Sequence[GeminiSegment], authority: str) -> tuple[EffectiveTranscriptSegment, ...]:
    return tuple(EffectiveTranscriptSegment(row.start_sample, row.end_sample, row.text,
                                            row.speaker, authority, row.source_lane)
                 for row in segments)


def _register_speakers(session: LiveSession, segments: Sequence[GeminiSegment]) -> None:
    speakers = tuple(dict.fromkeys(row.speaker for row in segments if row.speaker is not None))
    session.register_canonical_speakers(speakers)


def _lag_summary(samples: Sequence[int]) -> dict[str, float | int]:
    if not samples:
        return {"count": 0, "p50": 0.0, "max": 0.0}
    ordered = sorted(samples)
    return {"count": len(ordered), "p50": ordered[(len(ordered) - 1) // 2] / LIVE_SAMPLE_RATE,
            "max": ordered[-1] / LIVE_SAMPLE_RATE}
