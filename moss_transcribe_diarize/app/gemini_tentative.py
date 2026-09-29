"""Ephemeral voice guesses for Gemini preview words.

Only settled canonical observations seed the centroids. Nothing here changes a
LiveSession identity, a transcript row, or a durable event.
"""
from __future__ import annotations

import math
import tempfile
import threading
import time
import wave
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .live_span_bounds import LIVE_SAMPLE_RATE

_STEP = LIVE_SAMPLE_RATE // 2
_SNIPPET = LIVE_SAMPLE_RATE


def _unit(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    length = math.sqrt(sum(value * value for value in values))
    return tuple(value / length for value in values) if length else ()


@dataclass
class _Lane:
    accepted: int = 0
    next_tick: int = _STEP
    audio: bytearray = field(default_factory=bytearray)
    ticks: deque[tuple[int, str | None]] = field(default_factory=lambda: deque(maxlen=720))


class GeminiTentativeLabeler:
    """Embed at most one voiced 1 s snippet at a time; skip queued ticks."""

    def __init__(self, encoder: object, *, voiced_audio: Callable[[bytes], bool] | None = None):
        self.encoder = encoder
        self._voiced_audio = voiced_audio or _webrtc_voiced
        self._centroids: dict[str, tuple[float, ...]] = {}
        self._lanes: dict[str, _Lane] = {}
        self._lock = threading.RLock()
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemini-tentative")
        self._pending: Future | None = None
        self._latencies_ms: list[float] = []
        self._shown_ticks = 0
        self._abstained_ticks = 0
        self._busy_ticks = 0

    def observe(self, observations: Sequence[object]) -> None:
        with self._lock:
            for item in observations:
                if (getattr(item, "provisional", True) or
                    getattr(item, "sample_seconds", 0) < 2.0):
                    continue
                speaker = getattr(item, "speaker_label", None)
                vector = _unit(getattr(item, "centroid", ()))
                if not speaker or not vector:
                    continue
                old = self._centroids.get(speaker)
                self._centroids[speaker] = (vector if old is None else _unit(
                    tuple(.8 * left + .2 * right for left, right in zip(old, vector))))

    def accept_audio(self, lane: str, start_sample: int, pcm16: bytes) -> None:
        with self._lock:
            state = self._lanes.setdefault(lane, _Lane(accepted=start_sample,
                next_tick=((start_sample // _STEP) + 1) * _STEP))
            if start_sample != state.accepted:
                raise ValueError("tentative lane audio is not contiguous")
            count = len(pcm16) // 2
            position = 0
            while position < count:
                until_tick = min(count - position, state.next_tick - state.accepted)
                state.audio.extend(pcm16[position * 2:(position + until_tick) * 2])
                state.accepted += until_tick
                position += until_tick
                if len(state.audio) > _SNIPPET * 2:
                    del state.audio[:len(state.audio) - _SNIPPET * 2]
                if state.accepted != state.next_tick:
                    continue
                tick = state.next_tick
                state.next_tick += _STEP
                if len(state.audio) < _SNIPPET * 2 or not self._centroids:
                    continue
                if not self._voiced_audio(bytes(state.audio[-_STEP * 2:])):
                    continue
                if self._pending is not None and not self._pending.done():
                    state.ticks.append((tick, None))
                    self._abstained_ticks += 1
                    self._busy_ticks += 1
                    continue
                snippet = bytes(state.audio)
                centroids = dict(self._centroids)
                self._pending = self._worker.submit(self._embed, snippet, centroids)
                self._pending.add_done_callback(
                    lambda future, lane=lane, tick=tick: self._finish(lane, tick, future))

    def _embed(self, pcm16: bytes, centroids: dict[str, tuple[float, ...]]):
        started = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".wav") as path:
            with wave.open(path.name, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(LIVE_SAMPLE_RATE)
                wav.writeframes(pcm16)
            probe = _unit(self.encoder.embed(path.name, [(0.0, 1.0)]))
        ranked = sorted(((sum(a * b for a, b in zip(probe, vector)), speaker)
                         for speaker, vector in centroids.items()), reverse=True)
        speaker = ranked[0][1] if ranked and ranked[0][0] >= .40 else None
        return speaker, (time.perf_counter() - started) * 1000

    def _finish(self, lane: str, tick: int, future: Future) -> None:
        try:
            speaker, latency_ms = future.result()
        except Exception:
            speaker, latency_ms = None, None
        with self._lock:
            self._lanes[lane].ticks.append((tick, speaker))
            if latency_ms is not None:
                self._latencies_ms.append(latency_ms)
            if speaker is None:
                self._abstained_ticks += 1
            else:
                self._shown_ticks += 1

    def spans(self, lane: str, start_sample: int, end_sample: int) -> tuple[dict[str, object], ...]:
        with self._lock:
            ticks = tuple(self._lanes.get(lane, _Lane()).ticks)
        return tuple({"start_sample": max(start_sample, tick - _STEP),
                      "end_sample": min(end_sample, tick),
                      "source_lane": lane, "speaker": speaker}
                     for tick, speaker in ticks if speaker is not None
                     and tick > start_sample and tick - _STEP < end_sample)

    def diagnostics(self) -> dict[str, float | int | None]:
        with self._lock:
            times = sorted(self._latencies_ms)
            percentile = lambda p: times[min(len(times) - 1, math.ceil(p * len(times)) - 1)] if times else None
            return {"tentative_shown_s": self._shown_ticks * .5,
                    "tentative_abstained_s": self._abstained_ticks * .5,
                    "tentative_embed_p50_ms": percentile(.50),
                    "tentative_embed_p95_ms": percentile(.95),
                    "tentative_busy_ticks": self._busy_ticks}

    def wait_idle(self, timeout: float) -> bool:
        with self._lock:
            future = self._pending
        if future is None:
            return True
        try:
            future.result(timeout=timeout)
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._worker.shutdown(wait=True, cancel_futures=True)


def _webrtc_voiced(pcm16: bytes) -> bool:
    import webrtcvad
    vad = webrtcvad.Vad(1)
    return any(vad.is_speech(pcm16[offset:offset + 640], LIVE_SAMPLE_RATE)
               for offset in range(0, len(pcm16) - 639, 640))
