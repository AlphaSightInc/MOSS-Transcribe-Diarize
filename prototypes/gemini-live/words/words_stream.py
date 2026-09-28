"""Gemini Live provisional words stream; prototype API, not a qualified product adapter.

``await stream.start()``; ``await stream.push(pcm16)`` at the capture cadence;
``async for text, start, end, final in stream.updates(): ...``;
``await stream.finish()`` after the final chunk. ``gaps`` records uncertain audio at
reconnect. The Developer API does not expose a consumed-message index, so a
resumed socket cannot prove exact audio continuity.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass
from typing import AsyncIterator

from google.genai import types


@dataclass(frozen=True)
class Gap:
    start_s: float
    end_s: float
    reason: str


class WordStream:
    def __init__(self, model: str, config: types.LiveConnectConfig, *, replay_s: int = 5, client=None):
        if replay_s not in (2, 5):
            raise ValueError("replay_s must be 2 or 5")
        self.model = model
        self.config = config
        self.replay_s = replay_s
        self._client = client
        self._context = None
        self._session = None
        self._reader: asyncio.Task | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._lock = asyncio.Lock()
        self._history: deque[tuple[float, float, bytes]] = deque()
        self._audio_s = 0.0
        self._text_start_s = 0.0
        self._handle: str | None = None
        self._handle_at_s = 0.0
        self._reconnect_requested = False
        self._closed = False
        self.gaps: list[Gap] = []
        self.reconnects: list[dict] = []
        self.usage: list[dict] = []
        self.events: list[dict] = []
        self._published: list[tuple[float, float, str, bool]] = []
        self.suppressed_duplicates = 0

    async def start(self) -> None:
        if self._session is not None:
            return
        if self._client is None:
            from google import genai
            from pathlib import Path
            worktree = Path(__file__).resolve().parents[3]
            key = next(line.split("=", 1)[1].strip() for line in (worktree / ".env.local").read_text().splitlines()
                       if line.startswith("GEMINI_API_KEY="))
            self._client = genai.Client(api_key=key)
        await self._open(None)

    async def _open(self, handle: str | None) -> None:
        cfg = self.config.model_copy(deep=True)
        cfg.session_resumption = types.SessionResumptionConfig(handle=handle)
        self._context = self._client.aio.live.connect(model=self.model, config=cfg)
        self._session = await self._context.__aenter__()
        self._reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        try:
            while True:
                async for msg in self._session.receive():
                    if msg.go_away:
                        self._reconnect_requested = True
                        self.events.append({"go_away_time_left": msg.go_away.time_left, "audio_s": self._audio_s})
                    if msg.session_resumption_update:
                        update = msg.session_resumption_update
                        if update.resumable and update.new_handle:
                            self._handle = update.new_handle
                            self._handle_at_s = self._audio_s
                        self.events.append({"resumable": update.resumable,
                                            "has_handle": bool(update.new_handle),
                                            "has_consumed_index": update.last_consumed_client_message_index is not None,
                                            "audio_s": self._audio_s})
                    if msg.usage_metadata:
                        self.usage.append(msg.usage_metadata.model_dump(exclude_none=True, mode="json"))
                    sc = msg.server_content
                    if sc:
                        for name in ("interim_input_transcription", "input_transcription"):
                            tr = getattr(sc, name)
                            if tr and tr.text:
                                final = name == "input_transcription" or bool(tr.finished)
                                await self._publish(tr.text, self._text_start_s, self._audio_s, final)
                                if final:
                                    self._text_start_s = self._audio_s
                        if sc.model_turn and self.model == "gemini-3.5-transcribe-live":
                            txt = " ".join(p.text for p in sc.model_turn.parts or [] if p.text)
                            if txt:
                                await self._publish(txt, self._text_start_s, self._audio_s,
                                                    bool(sc.turn_complete))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.events.append({"receive_error": f"{type(exc).__name__}: {str(exc)[:200]}",
                                "audio_s": self._audio_s})
            self._reconnect_requested = True

    async def _publish(self, text: str, start: float, end: float, final: bool) -> None:
        # Live text has no word timestamps. Only exact repeated text in an overlapping
        # inferred audio interval is suppressed; corrections remain visible.
        norm = " ".join(text.lower().split())
        if any(prior == norm and prior_final == final and lo < end and start < hi
               for lo, hi, prior, prior_final in self._published):
            self.suppressed_duplicates += 1
            return
        self._published.append((start, end, norm, final))
        if len(self._published) > 100:
            self._published = self._published[-100:]
        await self._queue.put((text, start, end, final))

    async def _reconnect(self) -> None:
        started_wall = time.monotonic()
        # A failed send may already have been consumed by the old socket. Include
        # that pending chunk in the uncertain interval and in the replay.
        end = max(self._audio_s, self._history[-1][1] if self._history else 0.0)
        start = max(0.0, end - self.replay_s)
        handle = self._handle
        if start < end:
            self.gaps.append(Gap(start, end, "reconnect replay attempted; exact consumed boundary unknown"))
        if self._reader:
            self._reader.cancel()
            try:
                await self._reader
            except asyncio.CancelledError:
                pass
        if self._context:
            await self._context.__aexit__(None, None, None)
        await self._open(handle)
        replay = [(a, b, chunk) for a, b, chunk in self._history if b > start]
        for _, _, chunk in replay:
            await self._session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
        self.reconnects.append({"at_audio_s": end, "replay_start_s": start,
                                "replayed_chunks": len(replay), "replay_s": self.replay_s,
                                "used_handle": bool(handle), "started_monotonic": started_wall,
                                "finished_monotonic": time.monotonic()})
        self._reconnect_requested = False

    async def push(self, pcm16_bytes: bytes) -> None:
        if len(pcm16_bytes) % 2:
            raise ValueError("PCM16 chunk has odd byte count")
        if self._session is None or self._closed:
            raise RuntimeError("WordStream is not running")
        async with self._lock:
            if self._reconnect_requested:
                await self._reconnect()
            start = self._audio_s
            end = start + len(pcm16_bytes) / 32000
            self._history.append((start, end, pcm16_bytes))
            while self._history and self._history[0][1] < end - self.replay_s:
                self._history.popleft()
            try:
                await self._session.send_realtime_input(
                    audio=types.Blob(data=pcm16_bytes, mime_type="audio/pcm;rate=16000"))
            except Exception:
                self._reconnect_requested = True
                await self._reconnect()  # replays this chunk too
            self._audio_s = end

    async def reconnect(self) -> None:
        """Rotate the Live socket using its latest handle; also used by the forced-gap probe."""
        if self._session is None or self._closed:
            raise RuntimeError("WordStream is not running")
        async with self._lock:
            await self._reconnect()

    async def updates(self) -> AsyncIterator[tuple[str, float, float, bool]]:
        while True:
            item = await self._queue.get()
            if item is None:
                return
            yield item

    async def finish(self, *, drain_s: float = 8.0) -> None:
        if self._session is None or self._closed:
            return
        try:
            if self._reconnect_requested:
                await self._reconnect()
            try:
                await self._session.send_realtime_input(audio_stream_end=True)
            except Exception as exc:
                self.events.append({"stream_end_send_error": f"{type(exc).__name__}: {str(exc)[:200]}",
                                    "audio_s": self._audio_s})
                await self._reconnect()
                await self._session.send_realtime_input(audio_stream_end=True)
            await asyncio.sleep(drain_s)
            if self._reconnect_requested:
                await self._reconnect()
                await self._session.send_realtime_input(audio_stream_end=True)
                await asyncio.sleep(drain_s)
        finally:
            self._closed = True
            if self._reader:
                self._reader.cancel()
                try:
                    await self._reader
                except asyncio.CancelledError:
                    pass
            if self._context:
                await self._context.__aexit__(None, None, None)
            await self._queue.put(None)
