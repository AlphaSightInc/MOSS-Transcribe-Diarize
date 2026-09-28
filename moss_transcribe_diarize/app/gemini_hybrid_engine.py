"""Gemini live composition: replace one policy object when bake-off results arrive."""
from __future__ import annotations

import asyncio
import tempfile
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Protocol, Sequence

from scipy.optimize import linear_sum_assignment

from .gemini_live_runtime import GeminiBase, GeminiPreview, GeminiRolling, GeminiSegment, GeminiUpdate
from .gemini_provider import GeminiWord, WindowDiarizer, TerminalTranscriber, ordered_segments, speaker_turns
from .live_span_bounds import LIVE_SAMPLE_RATE
from .live_tape import CompleteMixedTape
from .live_provider_bundle import LiveSpeakerJournalObservation


class WordSource(Protocol):
    def words(self, pcm16: bytes, *, deadline: float) -> Sequence[GeminiWord]: ...


class WindowScheduler(Protocol):
    max_samples: int
    stride_samples: int
    cache_seconds: int
    def next_window(self, accepted_sample: int, last_end_sample: int) -> tuple[int, int, int] | None: ...


class SpeakerRegistry(Protocol):
    def observe_window(self, window_start_s: float, words: Sequence[GeminiWord],
                       embeddings: object | None = None) -> tuple[dict[str, str], tuple[GeminiUpdate, ...]]: ...


class WeSpeakerWindowEmbeddings:
    """One pinned encoder observation per eligible Gemini-local voice interval."""

    def __init__(self, encoder: object):
        self.encoder = encoder

    def __call__(self, pcm16: bytes, window_start_sample: int,
                 words: Sequence[GeminiWord]) -> dict[str, tuple[tuple[float, ...], float]]:
        candidates: dict[str, list[GeminiWord]] = {}
        for word in words:
            if word.end_sample > word.start_sample:
                candidates.setdefault(word.speaker, []).append(word)
        intervals: dict[str, tuple[int, int]] = {}
        for label, rows in candidates.items():
            rows.sort(key=lambda row: row.start_sample)
            begin = end = 0
            for row in rows:
                if begin == end or row.start_sample > end + LIVE_SAMPLE_RATE // 2:
                    begin, end = row.start_sample, row.end_sample
                else:
                    end = max(end, row.end_sample)
                if end - begin >= 2 * LIVE_SAMPLE_RATE:
                    intervals[label] = (begin, end)
                    break
        if not intervals:
            return {}
        result: dict[str, tuple[tuple[float, ...], float]] = {}
        with tempfile.NamedTemporaryFile(suffix=".wav") as path:
            with wave.open(path.name, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(LIVE_SAMPLE_RATE)
                wav.writeframes(pcm16)
            for label, (begin, end) in intervals.items():
                relative = ((begin - window_start_sample) / LIVE_SAMPLE_RATE,
                            (end - window_start_sample) / LIVE_SAMPLE_RATE)
                try:
                    vector = tuple(float(v) for v in self.encoder.embed(path.name, [relative]))
                except Exception:
                    continue
                if len(vector) == self.encoder.spec.embedding_dimension:
                    result[label] = (vector, (end - begin) / LIVE_SAMPLE_RATE)
        return result


class BatchTailWordSource:
    """Placeholder preview source; pane 5.2 replaces this class in this file."""

    def __init__(self, diarizer: WindowDiarizer):
        self.diarizer = diarizer

    def words(self, pcm16: bytes, *, deadline: float) -> Sequence[GeminiWord]:
        return self.diarizer.diarize(pcm16, deadline=deadline, kind="preview", diarize=False).words


class FixedWindowScheduler:
    """Placeholder L=60s, S=10s, H=10s; window ownership stays monotone."""

    max_samples = 60 * LIVE_SAMPLE_RATE
    stride_samples = 10 * LIVE_SAMPLE_RATE
    stride_seconds = 10
    cache_seconds = 70

    def next_window(self, accepted_sample: int, last_end_sample: int) -> tuple[int, int, int] | None:
        length = 60 * LIVE_SAMPLE_RATE
        stride = 10 * LIVE_SAMPLE_RATE
        if accepted_sample < 2 * stride or accepted_sample < last_end_sample + stride:
            return None
        end = (accepted_sample // stride) * stride
        return max(0, end - length), end, end - stride


class GrowingContextWindowScheduler:
    """Use the latest stride tick with context growing to a bounded recent span."""

    def __init__(self, *, max_seconds: int, stride_seconds: int):
        if not 0 < stride_seconds <= max_seconds <= 300:
            raise ValueError("Gemini growing window requires 0 < S <= Lmax <= 300 seconds")
        self.max_seconds = max_seconds
        self.stride_seconds = stride_seconds
        self.stride_samples = stride_seconds * LIVE_SAMPLE_RATE
        self.max_samples = max_seconds * LIVE_SAMPLE_RATE
        self.cache_seconds = max_seconds + stride_seconds
        self.idle_seconds = stride_seconds

    def next_window(self, accepted_sample: int,
                    last_end_sample: int) -> tuple[int, int, int] | None:
        end = (accepted_sample // self.stride_samples) * self.stride_samples
        if end < self.stride_samples or end <= last_end_sample:
            return None
        return max(0, end - self.max_samples), end, end


class OverlapRegistry:
    """Placeholder Hungarian overlap mapping; pane 6.1 replaces this class in this file."""

    def __init__(self):
        self._seen: list[GeminiWord] = []
        self._next_id = 1

    def observe_window(self, window_start_s: float, words: Sequence[GeminiWord],
                       embeddings: object | None = None) -> tuple[dict[str, str], tuple[GeminiUpdate, ...]]:
        del window_start_s, embeddings
        local = tuple(dict.fromkeys(word.speaker for word in words))
        old = tuple(dict.fromkeys(word.speaker for word in self._seen))
        weights = [[0 for _ in old] for _ in local]
        for i, label in enumerate(local):
            for word in (w for w in words if w.speaker == label):
                for prior in self._seen:
                    if prior.speaker in old:
                        weights[i][old.index(prior.speaker)] += max(
                            0, min(word.end_sample, prior.end_sample) - max(word.start_sample, prior.start_sample))
        mapping: dict[str, str] = {}
        if local and old:
            rows, columns = linear_sum_assignment([[-value for value in row] for row in weights])
            for row, column in zip(rows, columns, strict=True):
                if weights[row][column] > 0:
                    mapping[local[row]] = old[column]
        for label in local:
            if label not in mapping:
                mapping[label] = f"speaker-{self._next_id:04d}"
                self._next_id += 1
        self._seen = [GeminiWord(w.text, mapping[w.speaker], w.start_sample, w.end_sample) for w in words]
        return mapping, ()


class SingleMicrophoneRegistry:
    """One local participant identity, created only after the mic word gates pass."""

    def observe_window(self, window_start_s: float, words: Sequence[GeminiWord],
                       embeddings: object | None = None) -> tuple[dict[str, str], tuple[GeminiUpdate, ...]]:
        del window_start_s, embeddings
        return ({label: "speaker-microphone" for label in dict.fromkeys(w.speaker for w in words)}, ())


class GeminiHybridEngine:
    """A session owns a bounded live cache and coalesced background provider work."""

    _IDLE_SECONDS = 10  # The rolling stride S; one final window after ingress pauses.

    def __init__(self, publish: Callable[[GeminiUpdate], None], *, word_source: WordSource,
                 window_scheduler: WindowScheduler, registry: SpeakerRegistry,
                 diarizer: WindowDiarizer, terminal: TerminalTranscriber,
                 embedding_source: Callable[[bytes, int, Sequence[GeminiWord]],
                                            dict[str, tuple[tuple[float, ...], float]]] | None = None,
                 encoder_spec: object | None = None, word_gate=None,
                 report_usage: Callable[..., None] | None = None,
                 source_lane: str | None = None,
                 voiced_audio: Callable[[bytes], bool] | None = None,
                 diarize_windows: bool = True,
                 word_observer: Callable[[Sequence[GeminiWord], int], None] | None = None):
        self.publish = publish
        self.word_source = word_source
        self.window_scheduler = window_scheduler
        self.registry = registry
        self.diarizer = diarizer
        self.terminal = terminal
        self.embedding_source = embedding_source
        self.encoder_spec = encoder_spec
        self.word_gate = word_gate
        self.report_usage = report_usage
        self.source_lane = source_lane
        self.voiced_audio = voiced_audio
        self.diarize_windows = diarize_windows
        self.word_observer = word_observer
        self._window_max_samples = window_scheduler.max_samples
        self._cache_samples = window_scheduler.cache_seconds * LIVE_SAMPLE_RATE
        self._stride_samples = window_scheduler.stride_samples
        self._idle_seconds = getattr(window_scheduler, "idle_seconds", self._IDLE_SECONDS)
        self._recent_audio = bytearray()
        self._recent_start = 0
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini-hybrid")
        self._future: Future | None = None
        self._accepted = 0
        self._committed = 0
        self._rolling_frontier = 0
        self._last_window_end = 0
        self._last_preview_end = 0
        self._fast_words: list[GeminiWord] = []
        self._live_finals: list[GeminiWord] = []
        self._live_interim: GeminiWord | None = None
        self._stopping = False
        self._closed = False
        self._last_ingress_at = 0.0
        self._idle_timer: threading.Timer | None = None
        self._idle_due = False
        self._streaming_words = callable(getattr(word_source, "bind", None))
        if self._streaming_words:
            word_source.bind(self._on_live_text)

    def _on_live_text(self, text: str, start_sample: int, end_sample: int,
                      final: bool) -> None:
        if not text.strip():
            return
        with self._lock:
            if self._closed or end_sample <= self._committed:
                return
            row = GeminiWord(text.strip(), "spk:?", start_sample, end_sample)
            if final:
                self._live_finals.append(row)
                self._live_interim = None
            else:
                self._live_interim = row
            self._live_finals = [w for w in self._live_finals if w.end_sample > self._committed]
            self._fast_words = list(self._live_finals)
            if self._live_interim is not None:
                self._fast_words.append(self._live_interim)
            self._degrade_if_needed()
            end = min(self._accepted, max(self._committed, end_sample))
            if end <= self._committed:
                return
            preview = ordered_segments(
                tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                    w.text, source_lane=self.source_lane)
                      for w in self._fast_words if w.end_sample > self._committed),
                start_sample=self._committed, end_sample=end,
            )
            self.publish(GeminiPreview(end, preview))

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        with self._lock:
            if self._closed or start_sample != self._accepted:
                raise ValueError("Gemini engine audio is not contiguous")
            self._recent_audio.extend(pcm16)
            self._accepted += len(pcm16) // 2
            self._last_ingress_at = time.monotonic()
            self._idle_due = False
            if self._idle_timer is None:
                self._arm_idle_locked(self._idle_seconds)
            # Retain one extra stride so a delayed tick can still read Lmax.
            excess = len(self._recent_audio) - self._cache_samples * 2
            if excess > 0:
                del self._recent_audio[:excess]
                self._recent_start += excess // 2
            self._degrade_if_needed()
            if self._future is None or self._future.done():
                self._future = self._executor.submit(self._work)
        if self._streaming_words:
            self.word_source.push_audio(start_sample, pcm16)

    def _arm_idle_locked(self, delay: float) -> None:
        timer = threading.Timer(delay, self._on_idle)
        timer.daemon = True
        self._idle_timer = timer
        timer.start()

    def _on_idle(self) -> None:
        with self._lock:
            self._idle_timer = None
            if self._closed or self._stopping:
                return
            remaining = self._idle_seconds - (time.monotonic() - self._last_ingress_at)
            if remaining > 0:
                self._arm_idle_locked(remaining)
            elif self._rolling_frontier < self._accepted:
                self._idle_due = True
                if self._future is None or self._future.done():
                    self._future = self._executor.submit(self._work)

    def _read_locked(self, start: int, end: int) -> bytes:
        if start < self._recent_start or end > self._accepted:
            raise ValueError("Gemini live window is outside the bounded cache")
        low = (start - self._recent_start) * 2
        return bytes(self._recent_audio[low:low + (end - start) * 2])

    def _degrade_if_needed(self) -> None:
        if self._accepted - self._committed <= 45 * LIVE_SAMPLE_RATE:
            return
        through = max(self._committed, self._accepted - 40 * LIVE_SAMPLE_RATE)
        rows = ordered_segments(
            tuple(GeminiSegment(w.start_sample, min(through, max(w.end_sample, w.start_sample + 1)),
                                w.text, source_lane=self.source_lane)
                  for w in self._fast_words if self._committed <= w.start_sample < through),
            start_sample=self._committed, end_sample=through,
        )
        self.publish(GeminiBase(through, rows, degraded=True))
        self._committed = through
        self._fast_words = [w for w in self._fast_words if w.start_sample >= through]
        self._live_finals = [w for w in self._live_finals if w.end_sample > through]

    def _work(self) -> None:
        # Every loop inspects the latest accepted position. Slow calls are coalesced, not queued.
        while True:
            with self._lock:
                if self._closed or self._stopping:
                    return
                accepted = self._accepted
                if self._idle_due and self._rolling_frontier < accepted:
                    window = (max(0, accepted - self._window_max_samples), accepted, accepted)
                    self._idle_due = False
                else:
                    window = self.window_scheduler.next_window(accepted, self._last_window_end)
                preview_due = (not self._streaming_words and accepted >= 10 * LIVE_SAMPLE_RATE
                               and accepted - self._last_preview_end >= 3 * LIVE_SAMPLE_RATE)
                if window is None and not preview_due:
                    return
                if window is not None:
                    start, end, frontier = window
                    skipped = max(0, (end - self._last_window_end) // self._stride_samples - 1)
                    self._last_window_end = end
                else:
                    skipped = 0
                    end = accepted
                    start = max(0, end - 10 * LIVE_SAMPLE_RATE)
                    self._last_preview_end = end
                pcm = self._read_locked(start, end)
            if skipped and self.report_usage is not None:
                self.report_usage(kind="rolling", count_call=False,
                                  skipped_window_ticks=skipped)
            if window is not None:
                words = (() if self.voiced_audio is not None and not self.voiced_audio(pcm)
                         else self.diarizer.diarize(pcm, deadline=time.monotonic() + 120,
                                                     kind="rolling", diarize=self.diarize_windows).words)
                with self._lock:
                    if (self._stopping or self._idle_due) and end == self._accepted:
                        # This in-flight call already spans the Stop suffix.
                        # Publish its held-back ten seconds instead of making
                        # a second sequential request under the Stop deadline.
                        frontier = end
                        self._idle_due = False
                self._publish_window(start, frontier, pcm, words)
                continue
            words = self.word_source.words(pcm, deadline=time.monotonic() + 60)
            absolute = [GeminiWord(w.text, w.speaker, w.start_sample + start,
                                   w.end_sample + start) for w in words]
            with self._lock:
                known = {(w.start_sample, w.text) for w in self._fast_words}
                self._fast_words.extend(w for w in absolute if (w.start_sample, w.text) not in known)
                self._degrade_if_needed()
                preview = ordered_segments(
                    tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                        w.text, source_lane=self.source_lane)
                          for w in absolute if w.start_sample >= self._committed),
                    start_sample=self._committed, end_sample=end,
                )
                self.publish(GeminiPreview(end, preview))

    def _publish_window(self, start: int, frontier: int, pcm: bytes,
                        words: Sequence[GeminiWord]) -> None:
        absolute = tuple(GeminiWord(w.text, w.speaker, w.start_sample + start,
                                     w.end_sample + start) for w in words)
        if self.word_gate is not None:
            absolute = self.word_gate.filter(pcm, absolute, offset_sample=start)
        if self.word_observer is not None:
            self.word_observer(absolute, frontier)
        embeddings = (self.embedding_source(pcm, start, absolute)
                      if self.embedding_source is not None else {})
        mapping, relabels = self.registry.observe_window(start / LIVE_SAMPLE_RATE,
                                                         absolute, embeddings)
        observations = ()
        if self.encoder_spec is not None:
            spec = self.encoder_spec
            observations = tuple(LiveSpeakerJournalObservation(
                speaker_label=mapping[local], centroid=vector, sample_seconds=seconds,
                exemplar_count=1, provisional=False,
                embedder_id=f"{spec.provider}:{spec.revision}",
                embedder_state_sha=spec.state_sha256,
            ) for local, (vector, seconds) in embeddings.items() if local in mapping)
        with self._lock:
            old = self._rolling_frontier
            if frontier > old:
                if frontier > self._committed:
                    self.publish(GeminiBase(frontier, ()))
                    self._committed = frontier
                rows = speaker_turns(ordered_segments(
                    tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                        w.text, mapping[w.speaker], self.source_lane) for w in absolute
                          if old <= w.start_sample < frontier),
                    start_sample=old, end_sample=frontier,
                ))
                visible = {row.speaker for row in rows}
                self.publish(GeminiRolling(old, frontier, rows,
                                           tuple(obs for obs in observations
                                                 if obs.speaker_label in visible),
                                           (self.source_lane,) if self.source_lane else ()))
                self._rolling_frontier = frontier
                self._live_finals = [w for w in self._live_finals if w.end_sample > self._committed]
                self._fast_words = [w for w in self._fast_words if w.end_sample > self._committed]
            for update in relabels:
                self.publish(update)

    async def drain_tail(self, deadline: float) -> bool:
        expires = time.monotonic() + deadline
        with self._lock:
            self._stopping = True
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            future = self._future
        if future is not None:
            try:
                await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)),
                                       timeout=max(0.0, expires - time.monotonic()))
            except Exception:
                return False
        with self._lock:
            accepted = self._accepted
            if self._rolling_frontier >= accepted:
                return True
            start = max(0, accepted - self._window_max_samples)
            pcm = self._read_locked(start, accepted)
        try:
            if self.voiced_audio is not None and not self.voiced_audio(pcm):
                words = ()
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(self.diarizer.diarize, pcm, deadline=expires,
                                      kind="rolling", diarize=self.diarize_windows),
                    timeout=max(0.0, expires - time.monotonic()),
                )
                words = result.words
        except Exception:
            return False
        self._publish_window(start, accepted, pcm, words)
        return self._rolling_frontier >= accepted

    async def finish(self, tape: CompleteMixedTape) -> Sequence[GeminiSegment]:
        with self._lock:
            self._closed = True
            if self._idle_timer is not None:
                self._idle_timer.cancel()
                self._idle_timer = None
            future = self._future
        if future is not None:
            await asyncio.to_thread(future.result)
        self._executor.shutdown(wait=True)
        if self._streaming_words:
            await self.word_source.finish()
        return await asyncio.to_thread(self.terminal.transcribe, tape)

    def close(self) -> None:
        """Fence an aborted/failed meeting without waiting on a provider request."""
        # Do not take the engine lock: a provider worker may be publishing while
        # the runtime holds its lock on this failure path.
        self._closed = True
        if self._idle_timer is not None:
            self._idle_timer.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self._streaming_words:
            self.word_source.close()
