"""Gemini Live TEXT preview source; rolling and terminal passes own canonical text."""
from __future__ import annotations

import asyncio
import random
import threading
from collections import deque
from concurrent.futures import Future
from functools import reduce
from typing import Callable

from google.genai import types

from .live_span_bounds import LIVE_SAMPLE_RATE
from .gemini_provider import _error_code
from .transcript_text import join_text


_MODEL = "gemini-3.5-transcribe-live"


def _config(handle: str | None = None) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        # No language lock: auto-detect matched English accuracy in the bake-off (accept6 WER
        # .133 auto vs .135 en) and keeps non-English meetings usable, like the batch passes.
        input_audio_transcription=types.AudioTranscriptionConfig(
            mode="VERBATIM", word_timestamp=True),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                disabled=False, end_of_speech_sensitivity="END_SENSITIVITY_LOW",
                silence_duration_ms=500, prefix_padding_ms=100),
            activity_handling="NO_INTERRUPTION", turn_coverage="TURN_INCLUDES_ALL_INPUT"),
        session_resumption=types.SessionResumptionConfig(handle=handle),
        system_instruction="Transcribe the input audio verbatim. Output only transcription text.",
    )


class _LiveCore:
    def __init__(self, client: object, report: Callable[..., None],
                 on_text: Callable[[str, int, int, bool], None]):
        self.client = client
        self.report = report
        self.on_text = on_text
        self.context = None
        self.session = None
        self.reader: asyncio.Task | None = None
        self.sent_samples = 0
        self.turn_start = 0
        self._published: list[tuple[int, int, str, bool]] = []
        self._history: deque[tuple[int, int, bytes]] = deque()
        self._handle: str | None = None
        self._reconnect_requested = False
        self._last_text_at_sample = 0
        self._open_at_sample = 0

    async def start(self) -> None:
        await self._open(None)

    async def _open(self, handle: str | None) -> None:
        for attempt in range(3):
            try:
                context = self.client.aio.live.connect(model=_MODEL, config=_config(handle))
                session = await context.__aenter__()
                self.context, self.session = context, session
                self._open_at_sample = self.sent_samples
                self._last_text_at_sample = self.sent_samples
                self.report(kind="live_preview")
                self.reader = asyncio.create_task(self._read())
                return
            except Exception as exc:
                code = _error_code(exc)
                self.report(kind="live_preview", error_code=code,
                            retry_code=code if attempt < 2 else None)
                if attempt == 2:
                    raise
                await asyncio.sleep(0.2 * 2**attempt + random.random() * 0.1)

    async def _read(self) -> None:
        assert self.session is not None
        try:
            while True:
                async for message in self.session.receive():
                    resume = getattr(message, "session_resumption_update", None)
                    if resume and resume.resumable and resume.new_handle:
                        self._handle = resume.new_handle
                    if getattr(message, "go_away", None):
                        self._reconnect_requested = True
                        self.report(kind="live_preview", count_call=False, error_code="go_away",
                                    retry_code="go_away")
                    content = getattr(message, "server_content", None)
                    if content is None:
                        continue
                    transcriptions = (
                        (getattr(content, "interim_input_transcription", None), False),
                        (getattr(content, "input_transcription", None), True),
                    )
                    for transcript, final_kind in transcriptions:
                        if transcript is not None and getattr(transcript, "text", ""):
                            self._publish(transcript.text, final_kind or bool(
                                getattr(transcript, "finished", False)))
                    model_turn = getattr(content, "model_turn", None)
                    if model_turn:
                        text = reduce(join_text, (part.text for part in model_turn.parts or []
                                                  if part.text), "")
                        if text:
                            self._publish(text, bool(getattr(content, "turn_complete", False)))
                if self._reconnect_requested:
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            code = _error_code(exc)
            self._reconnect_requested = True
            self.report(kind="live_preview", count_call=False, error_code=code,
                        retry_code=code)

    def _publish(self, text: str, final: bool) -> None:
        self._last_text_at_sample = self.sent_samples
        start, end = self.turn_start, self.sent_samples
        norm = " ".join(text.lower().split())
        if not any(lo < end and start < hi and prior == norm and was_final == final
                   for lo, hi, prior, was_final in self._published):
            self._published.append((start, end, norm, final))
            self._published = self._published[-100:]
            self.on_text(text, start, end, final)
        if final:
            self.turn_start = end

    async def _rotate(self) -> None:
        end = self._history[-1][1] if self._history else self.sent_samples
        replay_start = max(0, end - 5 * LIVE_SAMPLE_RATE)
        await self.close()
        await self._open(self._handle)
        self.turn_start = min(self.turn_start, replay_start)
        for start, stop, chunk in self._history:
            if stop > replay_start:
                await self._send_audio(chunk, end_sample=stop)
        self._reconnect_requested = False

    async def _send_audio(self, pcm16: bytes, *, end_sample: int) -> None:
        assert self.session is not None
        self.sent_samples = max(self.sent_samples, end_sample)
        seconds = len(pcm16) / (2 * LIVE_SAMPLE_RATE)
        self.report(kind="live_preview", count_call=False, audio_seconds_sent=seconds,
                    cost_usd=seconds * 0.005 / 60, cost_basis="list_price_estimate",
                    output_cost_estimate_usd=seconds * .004 / 60)
        await self.session.send_realtime_input(
            audio=types.Blob(data=pcm16, mime_type="audio/pcm;rate=16000"))

    async def push(self, start_sample: int, pcm16: bytes) -> None:
        if self._reconnect_requested:
            await self._rotate()
        end_sample = start_sample + len(pcm16) // 2
        self._history.append((start_sample, end_sample, pcm16))
        while self._history and self._history[0][1] <= end_sample - 5 * LIVE_SAMPLE_RATE:
            self._history.popleft()
        try:
            await self._send_audio(pcm16, end_sample=end_sample)
        except Exception as exc:
            code = _error_code(exc)
            self.report(kind="live_preview", count_call=False, error_code=code,
                        retry_code=code)
            await self._rotate()  # The failed chunk is already in the replay buffer.
            return

    async def observe_batch_words(self, spans: tuple[tuple[int, int], ...]) -> None:
        if self.session is None:
            return
        boundary = max(self._open_at_sample, self._last_text_at_sample)
        merged = []
        for start, end in sorted(spans):
            start = max(start, boundary)
            if end <= start:
                continue
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        if sum(end-start for start, end in merged) >= 10*LIVE_SAMPLE_RATE:
            self.report(kind="live_preview", count_call=False, preview_stall_restarts=1)
            await self._rotate()

    async def finish(self) -> None:
        if self.session is None:
            return
        if self._reconnect_requested:
            await self._rotate()
        await self._send_audio(bytes(2 * LIVE_SAMPLE_RATE * 2),
                               end_sample=self.sent_samples + 2 * LIVE_SAMPLE_RATE)
        await self.session.send_realtime_input(audio_stream_end=True)
        await asyncio.sleep(2)
        await self.close()

    async def close(self) -> None:
        if self.reader is not None:
            self.reader.cancel()
            try:
                await self.reader
            except asyncio.CancelledError:
                pass
        if self.context is not None:
            await self.context.__aexit__(None, None, None)


class GeminiLiveWordSource:
    """Synchronous, nonblocking ingress bridge to one asynchronous Live socket."""

    def __init__(self, client: object, report_usage: Callable[..., None]):
        self.client = client
        self.report_usage = report_usage
        self._listener: Callable[[str, int, int, bool], None] | None = None
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="gemini-live-preview", daemon=True)
        self._tail: Future | None = None
        self._core: _LiveCore | None = None
        self._expected_sample = 0
        self._closed = False
        self._pending_slots = threading.BoundedSemaphore(64)

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
        tasks = asyncio.all_tasks(self._loop)
        for task in tasks:
            task.cancel()
        if tasks:
            self._loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
        self._loop.close()

    def bind(self, listener: Callable[[str, int, int, bool], None]) -> None:
        self._listener = listener
        self._thread.start()
        async def start():
            self._core = _LiveCore(self.client, self.report_usage, listener)
            await self._core.start()
        self._tail = asyncio.run_coroutine_threadsafe(start(), self._loop)

    def _submit(self, operation: Callable[[], object]) -> Future:
        previous = self._tail
        async def ordered():
            if previous is not None:
                await asyncio.wrap_future(previous)
            await operation()
        future = asyncio.run_coroutine_threadsafe(ordered(), self._loop)
        self._tail = future
        return future

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        if start_sample != self._expected_sample:
            raise ValueError("Live preview audio must be contiguous")
        self._expected_sample += len(pcm16) // 2
        if self._closed:
            return
        if not self._pending_slots.acquire(blocking=False):
            # Shed the chunk, not the socket: a capture replaying its backlog after an outage
            # (during a reconnect) overflowed here, and closing kept preview off for the rest
            # of a talking meeting. Rolling and terminal passes still own the skipped audio.
            self.report_usage(kind="live_preview", count_call=False,
                              error_code="preview_backpressure")
            return
        async def send():
            assert self._core is not None
            await self._core.push(start_sample, pcm16)
        self._submit(send).add_done_callback(lambda _done: self._pending_slots.release())

    def observe_batch_words(self, spans: tuple[tuple[int, int], ...]) -> None:
        if not self._closed:
            async def check():
                assert self._core is not None
                await self._core.observe_batch_words(spans)
            self._submit(check)

    async def finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        async def flush():
            assert self._core is not None
            await self._core.finish()
        future = self._submit(flush)
        try:
            try:
                await asyncio.to_thread(future.result, 10)
            except Exception:
                pass  # Preview failure cannot block the terminal text authority.
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            await asyncio.to_thread(self._thread.join, 2)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._core is not None:
            asyncio.run_coroutine_threadsafe(self._core.close(), self._loop).add_done_callback(
                lambda _done: self._loop.call_soon_threadsafe(self._loop.stop))
        else:
            self._loop.call_soon_threadsafe(self._loop.stop)
