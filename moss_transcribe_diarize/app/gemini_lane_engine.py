"""Compose two Gemini capture-lane engines on one public LiveSession frontier."""
from __future__ import annotations

import asyncio
import math
import re
import tempfile
import threading
import time
import wave
from pathlib import Path
from array import array
from typing import Callable, Sequence

from .gemini_live_runtime import (GeminiBase, GeminiPreview, GeminiRelabel, GeminiTurnBridge,
                                  GeminiRolling, GeminiSegment, GeminiUpdate)
from .gemini_provider import GeminiWord
from .live_span_bounds import LIVE_SAMPLE_RATE


def _token(text: str) -> str:
    return "".join(re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.lower(), flags=re.UNICODE))


def _preview_words(text: str) -> list[str]:
    return re.findall(r"[^\W_\d]+|\d+", text.casefold())


def _echoed_preview(row: GeminiSegment, system: Sequence[GeminiSegment]) -> bool:
    """A mic phrase repeats the union of nearby system preview phrases."""
    words = _preview_words(row.text)
    if not words:
        return False
    tolerance = 2 * LIVE_SAMPLE_RATE
    other = {word for segment in system
             if segment.start_sample <= row.end_sample + tolerance
             and segment.end_sample + tolerance >= row.start_sample
             for word in _preview_words(segment.text)}
    return 5 * sum(word in other for word in words) >= 3 * len(words)


class TextEchoGuard:
    """Drop an exact normalized mic token near a system token in audio time."""

    _TOLERANCE = 3 * LIVE_SAMPLE_RATE // 2

    def filter(self, microphone: Sequence[GeminiWord],
               system: Sequence[GeminiWord]) -> tuple[GeminiWord, ...]:
        reference = [(_token(w.text), (w.start_sample + w.end_sample) // 2) for w in system]
        kept = []
        for word in microphone:
            token = _token(word.text)
            middle = (word.start_sample + word.end_sample) // 2
            if token and any(token == other and abs(middle - at) <= self._TOLERANCE
                             for other, at in reference):
                continue
            kept.append(word)
        return tuple(kept)


class SystemWordLedger:
    """Recent timed system words and a completed frontier for the mic echo guard."""

    def __init__(self):
        self._ready = threading.Condition()
        self._frontier = 0
        self._words: list[GeminiWord] = []
        self._guard = TextEchoGuard()

    def observe(self, words: Sequence[GeminiWord], frontier: int) -> None:
        with self._ready:
            self._words.extend(words)
            self._frontier = max(self._frontier, frontier)
            self._words = [w for w in self._words
                           if w.end_sample >= self._frontier - 305 * LIVE_SAMPLE_RATE]
            self._ready.notify_all()

    def filter_mic(self, words: Sequence[GeminiWord], *,
                   through_sample: int) -> tuple[GeminiWord, ...]:
        with self._ready:
            self._ready.wait_for(lambda: self._frontier >= through_sample, timeout=30)
            return self._guard.filter(words, self._words)


class AcousticEchoGuard:
    """Keep mic words with no competing system voice or sufficient local level."""

    def __init__(self, system_read: Callable[[int, int], bytes], *, vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(1)
        self.system_read = system_read
        self.vad = vad

    @staticmethod
    def _rms(pcm16: bytes) -> float:
        samples = array("h")
        samples.frombytes(pcm16)
        return math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0

    def filter(self, mic_pcm16: bytes, words: Sequence[GeminiWord], *,
               offset_sample: int = 0) -> tuple[GeminiWord, ...]:
        end_sample = offset_sample + len(mic_pcm16) // 2
        kept = []
        frame = LIVE_SAMPLE_RATE // 100
        max_lag = LIVE_SAMPLE_RATE // 10
        threshold = 10 ** (-15 / 20)
        for word in words:
            start = max(offset_sample, min(end_sample - 1, word.start_sample))
            end = min(end_sample, max(start + 1, word.end_sample))
            if end <= start:
                continue
            system_start = max(0, start - max_lag)
            system_end = min(end_sample, math.ceil(end / frame) * frame)
            system = self.system_read(system_start, system_end)
            first_frame = start // frame
            last_frame = math.ceil(end / frame)
            system_voiced = any(
                self.vad.is_speech(system[(i*frame-system_start)*2:
                                          ((i+1)*frame-system_start)*2], LIVE_SAMPLE_RATE)
                for i in range(first_frame, last_frame)
                if (i+1)*frame <= system_end)
            if not system_voiced:
                kept.append(word)
                continue
            mic = mic_pcm16[(start-offset_sample)*2:(end-offset_sample)*2]
            mic_rms = self._rms(mic)
            duration = end - start
            system_rms = max(self._rms(system[(max(0, start-lag)-system_start)*2:
                                          (min(system_end, max(0, start-lag)+duration)-system_start)*2])
                             for lag in range(0, max_lag+1, frame))
            if mic_rms >= system_rms * threshold:
                kept.append(word)
        return tuple(kept)


class MicrophoneWordGate:
    def __init__(self, webrtc_gate, system_words: SystemWordLedger,
                 acoustic_gate=None, report_drops=None):
        self.webrtc_gate = webrtc_gate
        self.system_words = system_words
        self.acoustic_gate = acoustic_gate
        self.report_drops = report_drops

    def _record(self, before: int, acoustic: int, after: int) -> None:
        if self.report_drops is not None:
            self.report_drops({"acoustic_gate_dropped_words": before-acoustic,
                               "text_guard_dropped_words": acoustic-after})

    def filter(self, pcm16: bytes, words: Sequence[GeminiWord], *,
               offset_sample: int = 0) -> tuple[GeminiWord, ...]:
        voiced = self.webrtc_gate.filter(pcm16, words, offset_sample=offset_sample)
        if not voiced:
            return ()
        acoustic = (self.acoustic_gate.filter(pcm16, voiced, offset_sample=offset_sample)
                    if self.acoustic_gate is not None else voiced)
        kept = self.system_words.filter_mic(
            acoustic, through_sample=offset_sample + len(pcm16) // 2)
        self._record(len(voiced), len(acoustic), len(kept))
        return kept

    def filter_terminal(self, mic_pcm16: bytes, words: Sequence[GeminiWord],
                        system_words: Sequence[GeminiWord]) -> tuple[GeminiWord, ...]:
        # TerminalTranscriber has already applied the mic WebRTC word gate.
        acoustic = (self.acoustic_gate.filter(mic_pcm16, words)
                    if self.acoustic_gate is not None else tuple(words))
        kept = TextEchoGuard().filter(acoustic, system_words)
        self._record(len(words), len(acoustic), len(kept))
        return kept


class WebRtcSpeechDetector:
    """Mode-1, 10 ms voiced-frame fact for mic socket and batch activation."""

    def __init__(self, vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(1)
        self.vad = vad

    def __call__(self, pcm16: bytes) -> bool:
        return any(self.vad.is_speech(pcm16[i:i+320], LIVE_SAMPLE_RATE)
                   for i in range(0, len(pcm16)-319, 320))


class VoicedLiveWords:
    """Open a lane's W3 socket on voice; close after 60 s without voice."""

    def __init__(self, source_factory: Callable[[], object], *, voiced_audio: Callable[[bytes], bool]):
        self.source_factory = source_factory
        self.voiced_audio = voiced_audio
        self._listener: Callable[[str, int, int, bool], None] | None = None
        self._active = None
        self._origin = 0
        self._last_voice_end = 0
        self._expected = 0
        self.ever_voiced = False

    def bind(self, listener: Callable[[str, int, int, bool], None]) -> None:
        self._listener = listener

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        if start_sample != self._expected:
            raise ValueError("Live preview audio is not contiguous")
        end = start_sample + len(pcm16) // 2
        self._expected = end
        voiced = self.voiced_audio(pcm16)
        if voiced:
            self.ever_voiced = True
            self._last_voice_end = end
            if self._active is None:
                source = self.source_factory()
                self._origin = start_sample
                source.bind(lambda text, start, stop, final: self._emit(
                    source, text, start, stop, final))
                self._active = source
        elif self._active is not None and end - self._last_voice_end >= 60 * LIVE_SAMPLE_RATE:
            self._active.close()
            self._active = None
        if self._active is not None:
            self._active.push_audio(start_sample - self._origin, pcm16)

    def _emit(self, source, text: str, start: int, end: int, final: bool) -> None:
        if source is self._active and self._listener is not None:
            self._listener(text, self._origin + start, self._origin + end, final)

    def observe_batch_words(self, spans: Sequence[tuple[int, int]]) -> None:
        if self._active is not None:
            observe = getattr(self._active, "observe_batch_words", None)
            if callable(observe):
                observe(tuple((start - self._origin, end - self._origin)
                              for start, end in spans))

    async def finish(self) -> None:
        if self._active is not None:
            source = self._active
            await source.finish()
            self._active = None

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
            self._active = None


class ConditionalMicrophoneTerminal:
    """A digital-silent mic has no terminal provider request."""

    def __init__(self, source: VoicedLiveWords, terminal):
        self.source = source
        self.terminal = terminal

    def transcribe(self, tape) -> tuple[GeminiSegment, ...]:
        return self.terminal.transcribe(tape) if self.source.ever_voiced else ()

    def set_witness(self, rows: Sequence[GeminiSegment]) -> None:
        self.terminal.set_witness(rows)

    @property
    def coverage_gaps(self) -> tuple[tuple[int, int], ...]:
        return self.terminal.coverage_gaps if self.source.ever_voiced else ()


class SerializedDiarizer:
    """One provider batch window in flight across both lanes of a meeting."""

    def __init__(self, diarizer, lock: threading.Lock | None = None):
        self.diarizer = diarizer
        self._lock = lock or threading.Lock()

    def diarize(self, pcm16: bytes, *, deadline: float, kind: str,
                diarize: bool = True):
        with self._lock:
            return self.diarizer.diarize(pcm16, deadline=deadline,
                                         kind=kind, diarize=diarize)

    def diarize_terminal(self, pcm16: bytes, *, deadline: float, kind: str,
                         diarize: bool = True):
        # Stop drained rolling work before the final pass. Its independent
        # chunks may use the shared HTTP client concurrently (bounded by the
        # TerminalTranscriber) without reopening live-window concurrency.
        return self.diarizer.diarize(pcm16, deadline=deadline,
                                     kind=kind, diarize=diarize)


class _LaneTape:
    """Temporary complete accepted source PCM; Account's mixed stage remains untouched."""

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self._file = tempfile.TemporaryFile(dir=root)
        self._lock = threading.RLock()
        self.sample_count = 0

    def append(self, start_sample: int, pcm16: bytes) -> None:
        with self._lock:
            if start_sample != self.sample_count:
                raise ValueError("Gemini lane tape is not contiguous")
            self._file.seek(0, 2)
            self._file.write(pcm16)
            self.sample_count += len(pcm16) // 2

    def covers(self, start_sample: int, end_sample: int) -> bool:
        return 0 <= start_sample < end_sample <= self.sample_count

    def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
        with self._lock:
            end = self.sample_count if end_sample is None else end_sample
            if not self.covers(start_sample, end):
                raise ValueError("Gemini lane tape does not cover interval")
            self._file.seek(start_sample * 2)
            data = self._file.read((end - start_sample) * 2)
            if len(data) != (end - start_sample) * 2:
                raise ValueError("Gemini lane tape short read")
            return data

    def write_wav(self, destination, *, start_sample: int = 0,
                  end_sample: int | None = None) -> int:
        end = self.sample_count if end_sample is None else end_sample
        pcm = self.read(start_sample=start_sample, end_sample=end)
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(LIVE_SAMPLE_RATE)
            wav.writeframes(pcm)
        return end - start_sample

    def close(self) -> None:
        self._file.close()


class LaneGeminiEngine:
    """Combine completed lane windows; no lane may revise behind the public frontier."""

    LANES = ("system", "microphone")

    def __init__(self, publish: Callable[[GeminiUpdate], None], *,
                 system_factory: Callable[[Callable[[GeminiUpdate], None]], object],
                 microphone_factory: Callable[[Callable[[GeminiUpdate], None]], object],
                 tape_root: Path):
        self.publish = publish
        self._lock = threading.RLock()
        self._accepted = 0
        self._base_committed = 0
        self._frontier = 0
        self._lane_frontiers = {lane: 0 for lane in self.LANES}
        self._rows: dict[str, list[GeminiSegment]] = {lane: [] for lane in self.LANES}
        self._pending_turn_bridges: list[GeminiTurnBridge] = []
        self._previews: dict[str, GeminiPreview | None] = {lane: None for lane in self.LANES}
        self.terminal_coverage_gaps: tuple[tuple[str | None, int, int], ...] = ()
        self._observations: dict[str, object] = {}
        self._tapes = {lane: _LaneTape(tape_root) for lane in self.LANES}
        self._engines = {
            "system": system_factory(lambda update: self._on_update("system", update)),
            "microphone": microphone_factory(lambda update: self._on_update("microphone", update)),
        }

    def lane_tape(self, lane: str) -> _LaneTape:
        return self._tapes[lane]

    def push_audio(self, start_sample: int, pcm16: bytes,
                   lane_pcm: tuple[tuple[str, bytes], ...] = ()) -> None:
        lanes = dict(lane_pcm) if lane_pcm else {
            "system": pcm16, "microphone": bytes(len(pcm16))}
        with self._lock:
            if start_sample != self._accepted:
                raise ValueError("Gemini lane audio is not contiguous")
            self._accepted += len(pcm16) // 2
            for lane in self.LANES:
                self._tapes[lane].append(start_sample, lanes[lane])
        # The system task is enqueued first so its timed words can guard microphone echo.
        for lane in self.LANES:
            self._engines[lane].push_audio(start_sample, lanes[lane])
        with self._lock:
            if self._accepted - self._base_committed > 45 * LIVE_SAMPLE_RATE:
                through = max(self._base_committed, self._accepted - 40 * LIVE_SAMPLE_RATE)
                self.publish(GeminiBase(through, (), degraded=True))
                self._base_committed = through

    def push_lanes(self, start_sample: int,
                   lane_pcm: tuple[tuple[str, bytes], ...]) -> None:
        lanes = dict(lane_pcm)
        if set(lanes) != set(self.LANES):
            raise ValueError("Gemini lane engine requires both aligned source lanes")
        self.push_audio(start_sample, bytes(len(lanes["system"])), lane_pcm)

    def _on_update(self, lane: str, update: GeminiUpdate) -> None:
        with self._lock:
            if isinstance(update, GeminiPreview):
                self._previews[lane] = update
                end = max(p.end_sample for p in self._previews.values() if p is not None)
                segments: list[GeminiSegment] = []
                for lane_name in self.LANES:
                    preview = self._previews[lane_name]
                    if preview is None:
                        continue
                    for row in preview.segments:
                        if row.end_sample <= self._base_committed:
                            continue
                        current = GeminiSegment(max(row.start_sample, self._base_committed),
                                                row.end_sample, row.text, row.speaker, lane_name)
                        segments = [prior for prior in segments
                                    if prior.source_lane != lane_name
                                    or prior.end_sample <= current.start_sample
                                    or prior.start_sample >= current.end_sample]
                        segments.append(current)
                system = [row for row in segments if row.source_lane == "system"]
                unique = [row for row in segments
                          if row.source_lane == "system" or not _echoed_preview(row, system)]
                if end > self._base_committed:
                    self.publish(GeminiPreview(end, tuple(sorted(
                        unique, key=lambda row: (row.start_sample,
                                                 self.LANES.index(row.source_lane))))))
            elif isinstance(update, GeminiBase):
                # Inner engines account locally. The public base advances only when
                # both lane windows are ready, except for the bounded lag fallback.
                pass
            elif isinstance(update, GeminiRolling):
                self._rows[lane].extend(update.segments)
                self._lane_frontiers[lane] = update.end_sample
                for observation in update.observations:
                    self._observations[observation.speaker_label] = observation
                self._publish_ready()
            elif isinstance(update, GeminiRelabel):
                self._rows[lane] = [row for row in self._rows[lane]
                                    if row.end_sample <= update.start_sample
                                    or row.start_sample >= update.end_sample] + list(update.segments)
                if update.end_sample <= self._frontier:
                    rows = tuple(row for row in self._rows_in(update.start_sample, update.end_sample)
                                 if row.source_lane == lane)
                    self.publish(GeminiRelabel(update.start_sample, update.end_sample, rows))
            elif isinstance(update, GeminiTurnBridge):
                self._pending_turn_bridges.append(update)
                self._publish_turn_bridges()

    def _rows_in(self, start: int, end: int) -> tuple[GeminiSegment, ...]:
        return tuple(sorted((row for lane in self.LANES for row in self._rows[lane]
                             if start <= row.start_sample < end),
                            key=lambda row: (row.start_sample,
                                             self.LANES.index(row.source_lane), row.end_sample)))

    def _publish_ready(self) -> None:
        through = min(self._lane_frontiers.values())
        if through <= self._frontier:
            return
        if through > self._base_committed:
            self.publish(GeminiBase(through, ()))
            self._base_committed = through
        rows = self._rows_in(self._frontier, through)
        visible = {row.speaker for row in rows}
        observations = tuple(value for key, value in self._observations.items() if key in visible)
        self.publish(GeminiRolling(self._frontier, through, rows, observations,
                                   revision_lanes=self.LANES))
        self._frontier = through
        self._publish_turn_bridges()

    def _publish_turn_bridges(self) -> None:
        ready = [row for row in self._pending_turn_bridges
                 if row.new_end_sample < self._frontier]
        self._pending_turn_bridges = [row for row in self._pending_turn_bridges
                                      if row.new_end_sample >= self._frontier]
        for row in ready:
            self.publish(row)

    async def drain_tail(self, deadline: float) -> bool:
        started = time.monotonic()
        for lane in self.LANES:
            remaining = deadline - (time.monotonic() - started)
            if remaining <= 0 or not await self._engines[lane].drain_tail(remaining):
                return False
        with self._lock:
            return self._frontier >= self._accepted

    async def finish(self, _mixed_tape) -> Sequence[GeminiSegment]:
        try:
            rows = []
            gaps = []
            for lane in self.LANES:
                witness = getattr(self._engines[lane], "set_terminal_witness", None)
                if callable(witness):
                    witness(self._rows[lane])
                rows.extend(await self._engines[lane].finish(self._tapes[lane]))
                gaps.extend(getattr(self._engines[lane], "terminal_coverage_gaps", ()))
            self.terminal_coverage_gaps = tuple(gaps)
            return tuple(sorted(rows, key=lambda row: (row.start_sample,
                self.LANES.index(row.source_lane), row.end_sample)))
        finally:
            for tape in self._tapes.values():
                tape.close()

    def close(self) -> None:
        for engine in self._engines.values():
            engine.close()
        for tape in self._tapes.values():
            tape.close()
