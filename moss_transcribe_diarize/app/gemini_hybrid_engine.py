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
from .gemini_provider import GeminiWord, WindowDiarizer, TerminalTranscriber, ordered_segments
from .live_span_bounds import LIVE_SAMPLE_RATE
from .live_tape import CompleteMixedTape
from .live_provider_bundle import LiveSpeakerJournalObservation


class WordSource(Protocol):
    def words(self, pcm16: bytes, *, deadline: float) -> Sequence[GeminiWord]: ...


class WindowScheduler(Protocol):
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

    def next_window(self, accepted_sample: int, last_end_sample: int) -> tuple[int, int, int] | None:
        length = 60 * LIVE_SAMPLE_RATE
        stride = 10 * LIVE_SAMPLE_RATE
        if accepted_sample < 2 * stride or accepted_sample < last_end_sample + stride:
            return None
        end = (accepted_sample // stride) * stride
        return max(0, end - length), end, end - stride


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


class GeminiHybridEngine:
    """A session owns a bounded live cache and coalesced background provider work."""

    def __init__(self, publish: Callable[[GeminiUpdate], None], *, word_source: WordSource,
                 window_scheduler: WindowScheduler, registry: SpeakerRegistry,
                 diarizer: WindowDiarizer, terminal: TerminalTranscriber,
                 embedding_source: Callable[[bytes, int, Sequence[GeminiWord]],
                                            dict[str, tuple[tuple[float, ...], float]]] | None = None,
                 encoder_spec: object | None = None):
        self.publish = publish
        self.word_source = word_source
        self.window_scheduler = window_scheduler
        self.registry = registry
        self.diarizer = diarizer
        self.terminal = terminal
        self.embedding_source = embedding_source
        self.encoder_spec = encoder_spec
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
        self._closed = False

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        with self._lock:
            if self._closed or start_sample != self._accepted:
                raise ValueError("Gemini engine audio is not contiguous")
            self._recent_audio.extend(pcm16)
            self._accepted += len(pcm16) // 2
            # A 60-second window ends on a 10-second boundary. Keep that extra
            # stride so a window is still readable between boundaries.
            excess = len(self._recent_audio) - 70 * LIVE_SAMPLE_RATE * 2
            if excess > 0:
                del self._recent_audio[:excess]
                self._recent_start += excess // 2
            self._degrade_if_needed()
            if self._future is None or self._future.done():
                self._future = self._executor.submit(self._work)

    def _read_locked(self, start: int, end: int) -> bytes:
        if start < self._recent_start or end > self._accepted:
            raise ValueError("Gemini live window is outside the 70-second cache")
        low = (start - self._recent_start) * 2
        return bytes(self._recent_audio[low:low + (end - start) * 2])

    def _degrade_if_needed(self) -> None:
        if self._accepted - self._committed <= 45 * LIVE_SAMPLE_RATE:
            return
        through = max(self._committed, self._accepted - 40 * LIVE_SAMPLE_RATE)
        rows = ordered_segments(
            tuple(GeminiSegment(w.start_sample, min(through, max(w.end_sample, w.start_sample + 1)), w.text)
                  for w in self._fast_words if self._committed <= w.start_sample < through),
            start_sample=self._committed, end_sample=through,
        )
        self.publish(GeminiBase(through, rows, degraded=True))
        self._committed = through
        self._fast_words = [w for w in self._fast_words if w.start_sample >= through]

    def _work(self) -> None:
        # Every loop inspects the latest accepted position. Slow calls are coalesced, not queued.
        while True:
            with self._lock:
                if self._closed:
                    return
                accepted = self._accepted
                window = self.window_scheduler.next_window(accepted, self._last_window_end)
                preview_due = accepted >= 10 * LIVE_SAMPLE_RATE and accepted - self._last_preview_end >= 3 * LIVE_SAMPLE_RATE
                if window is None and not preview_due:
                    return
                if window is not None:
                    start, end, frontier = window
                    self._last_window_end = end
                else:
                    end = accepted
                    start = max(0, end - 10 * LIVE_SAMPLE_RATE)
                    self._last_preview_end = end
                pcm = self._read_locked(start, end)
            if window is not None:
                words = self.diarizer.diarize(pcm, deadline=time.monotonic() + 120,
                                              kind="rolling").words
                absolute = tuple(GeminiWord(w.text, w.speaker, w.start_sample + start,
                                             w.end_sample + start) for w in words)
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
                        rows = ordered_segments(
                            tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                                w.text, mapping[w.speaker]) for w in absolute
                                  if old <= w.start_sample < frontier),
                            start_sample=old, end_sample=frontier,
                        )
                        visible = {row.speaker for row in rows}
                        self.publish(GeminiRolling(old, frontier, rows,
                                                   tuple(obs for obs in observations
                                                         if obs.speaker_label in visible)))
                        self._rolling_frontier = frontier
                    for update in relabels:
                        self.publish(update)
                continue
            words = self.word_source.words(pcm, deadline=time.monotonic() + 60)
            absolute = [GeminiWord(w.text, w.speaker, w.start_sample + start,
                                   w.end_sample + start) for w in words]
            with self._lock:
                known = {(w.start_sample, w.text) for w in self._fast_words}
                self._fast_words.extend(w for w in absolute if (w.start_sample, w.text) not in known)
                self._degrade_if_needed()
                preview = ordered_segments(
                    tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1), w.text)
                          for w in absolute if w.start_sample >= self._committed),
                    start_sample=self._committed, end_sample=end,
                )
                self.publish(GeminiPreview(end, preview))

    async def finish(self, tape: CompleteMixedTape) -> Sequence[GeminiSegment]:
        with self._lock:
            self._closed = True
            future = self._future
        if future is not None:
            await asyncio.to_thread(future.result)
        self._executor.shutdown(wait=True)
        return await asyncio.to_thread(self.terminal.transcribe, tape)

    def close(self) -> None:
        """Fence an aborted/failed meeting without waiting on a provider request."""
        # Do not take the engine lock: a provider worker may be publishing while
        # the runtime holds its lock on this failure path.
        self._closed = True
        self._executor.shutdown(wait=False, cancel_futures=True)
