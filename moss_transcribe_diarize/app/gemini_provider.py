"""Bounded Gemini Transcribe requests over owner-approved PCM16 audio.

The key is supplied by the composition root. This module never reads process env,
logs provider payloads, or retains a transcript cache.
"""
from __future__ import annotations

import base64
import io
import math
import random
import re
import time
import wave
from dataclasses import dataclass
from typing import Callable, Sequence

from .live_span_bounds import LIVE_SAMPLE_RATE
from .live_tape import CompleteMixedTape
from .gemini_live_runtime import GeminiSegment

MODEL = "gemini-3.5-transcribe"


@dataclass(frozen=True, slots=True)
class GeminiWord:
    text: str
    speaker: str
    start_sample: int
    end_sample: int


@dataclass(frozen=True, slots=True)
class GeminiWords:
    words: tuple[GeminiWord, ...]
    clamped: int = 0
    dropped: int = 0


def ordered_segments(rows: Sequence[GeminiSegment], *, start_sample: int,
                     end_sample: int) -> tuple[GeminiSegment, ...]:
    """Project timestamped provider words onto LiveSession's one-owner sample line."""
    ordered = sorted((row for row in rows if row.text and row.start_sample < end_sample
                      and row.end_sample > start_sample),
                     key=lambda row: (row.start_sample, row.end_sample))
    result: list[GeminiSegment] = []
    cursor = start_sample
    for row in ordered:
        start = max(cursor, row.start_sample, start_sample)
        if start >= end_sample:
            # In the rare fully overlapping tail, preserve text in the final row.
            if result:
                prior = result[-1]
                result[-1] = GeminiSegment(prior.start_sample, prior.end_sample,
                                            prior.text + " " + row.text, prior.speaker)
            continue
        end = min(end_sample, max(start + 1, row.end_sample))
        result.append(GeminiSegment(start, end, row.text, row.speaker, row.source_lane))
        cursor = end
    return tuple(result)


def speaker_turns(rows: Sequence[GeminiSegment]) -> tuple[GeminiSegment, ...]:
    """Group ordered words by speaker with the common 1.5-second gap rule."""
    turns: list[GeminiSegment] = []
    max_gap = 3 * LIVE_SAMPLE_RATE // 2
    for row in rows:
        if (turns and turns[-1].speaker == row.speaker
                and turns[-1].source_lane == row.source_lane
                and row.start_sample - turns[-1].end_sample <= max_gap):
            prior = turns[-1]
            turns[-1] = GeminiSegment(prior.start_sample, max(prior.end_sample, row.end_sample),
                                      prior.text + " " + row.text, prior.speaker, prior.source_lane)
        else:
            turns.append(row)
    return tuple(turns)


def _wav(pcm16: bytes) -> bytes:
    with io.BytesIO() as out:
        with wave.open(out, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(LIVE_SAMPLE_RATE)
            wav.writeframes(pcm16)
        return out.getvalue()


def _seconds(value: object) -> float:
    if value is None:
        return 0.0
    return float(str(value).rstrip("s"))


def parse_words(response: dict, *, audio_samples: int) -> GeminiWords:
    """Mirror the observed offset repair in gemini_common.py at bc567bb2."""
    audio_s = audio_samples / LIVE_SAMPLE_RATE
    words: list[GeminiWord] = []
    clamped = dropped = 0
    for step in response.get("steps") or ():
        for content in step.get("content") or ():
            for annotation in content.get("annotations") or ():
                if annotation.get("type") != "word_info":
                    continue
                start = _seconds(annotation.get("start_offset"))
                end = _seconds(annotation.get("end_offset"))
                if not math.isfinite(start) or start > audio_s + 0.5:
                    dropped += 1
                    continue
                if not math.isfinite(end) or end < start or end > audio_s + 0.5:
                    end = min(start + 1.0, audio_s)
                    clamped += 1
                start_sample = max(0, min(audio_samples, round(start * LIVE_SAMPLE_RATE)))
                end_sample = max(start_sample, min(audio_samples, round(end * LIVE_SAMPLE_RATE)))
                words.append(GeminiWord(str(annotation.get("text") or ""),
                                        str(annotation.get("speaker") or "spk:?"),
                                        start_sample, end_sample))
    return GeminiWords(tuple(words), clamped, dropped)


def _usage_cost(usage: dict) -> float:
    audio_in = text_in = 0
    for row in usage.get("input_tokens_by_modality") or ():
        tokens = int(row.get("tokens") or 0)
        if str(row.get("modality", "")).lower() == "audio":
            audio_in += tokens
        else:
            text_in += tokens
    out = int(usage.get("total_output_tokens") or 0) + int(usage.get("total_thought_tokens") or 0)
    return (2 * audio_in + 2 * text_in + 12 * out) / 1_000_000


def _error_code(exc: Exception) -> str:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code is not None:
        try:
            return str(int(code))
        except (TypeError, ValueError):
            pass
    name = type(exc).__name__.lower()
    if "timeout" in name or "timed out" in str(exc).lower():
        return "timeout"
    matched = re.search(r"\b(429|5\d\d)\b", str(exc))
    if matched:
        return matched.group(1)
    return "provider_error"


class WindowDiarizer:
    """One bounded request per attempt, with retries only for transient failures."""

    def __init__(self, client: object, report_usage: Callable[..., None], *, max_attempts: int = 3):
        self.client = client
        self.report_usage = report_usage
        self.max_attempts = max_attempts

    def diarize(self, pcm16: bytes, *, deadline: float, kind: str = "rolling",
                diarize: bool = True) -> GeminiWords:
        if len(pcm16) % 2:
            raise ValueError("PCM16 requires complete samples")
        if len(pcm16) > 30 * 60 * LIVE_SAMPLE_RATE * 2:
            raise ValueError("Gemini diarization request exceeds 30 minutes")
        mode = {"type": "verbatim", "timestamp_granularities": ["word"]}
        if diarize:
            mode["diarization_mode"] = "speaker"
        payload = base64.b64encode(_wav(pcm16)).decode("ascii")
        audio_seconds = len(pcm16) / (2 * LIVE_SAMPLE_RATE)
        for attempt in range(self.max_attempts):
            if time.monotonic() >= deadline:
                raise TimeoutError("Gemini request deadline expired")
            try:
                response = self.client.interactions.create(
                    model=MODEL,
                    input=[{"type": "audio", "data": payload, "mime_type": "audio/wav"}],
                    generation_config={"transcription_config": {"mode": mode}},
                )
                data = response.model_dump(exclude_none=True, mode="json")
                parsed = parse_words(data, audio_samples=len(pcm16) // 2)
                self.report_usage(kind=kind, clamped_words=parsed.clamped, dropped_words=parsed.dropped,
                                  audio_seconds_sent=audio_seconds,
                                  cost_usd=_usage_cost(data.get("usage") or {}))
                return parsed
            except Exception as exc:
                code = _error_code(exc)
                transient = code in {"429", "timeout"} or (code.isdigit() and 500 <= int(code) < 600)
                retry = transient and attempt + 1 < self.max_attempts
                self.report_usage(kind=kind, error_code=code, retry_code=code if retry else None,
                                  audio_seconds_sent=audio_seconds)
                if not retry:
                    raise
                pause = min(2 ** attempt + random.random(), max(0.0, deadline - time.monotonic()))
                if pause <= 0:
                    raise TimeoutError("Gemini request deadline expired") from exc
                time.sleep(pause)
        raise AssertionError("retry loop exhausted")


class TerminalTranscriber:
    """Whole-meeting chunk pass; overlap resolves local labels by word-time agreement."""

    def __init__(self, diarizer: WindowDiarizer, *, chunk_seconds: int = 1800,
                 overlap_seconds: int = 20, identity_policy=None, word_gate=None,
                 diarize: bool = True, word_filter=None,
                 source_lane: str | None = None, fixed_speaker: str | None = None):
        if not 0 < overlap_seconds < chunk_seconds <= 1800:
            raise ValueError("terminal chunks must be at most 30 minutes with a smaller overlap")
        self.diarizer = diarizer
        self.identity_policy = identity_policy
        self.word_gate = word_gate
        self.diarize = diarize
        self.word_filter = word_filter
        self.source_lane = source_lane
        self.fixed_speaker = fixed_speaker
        self.last_words: tuple[GeminiWord, ...] = ()
        self.chunk_samples = chunk_seconds * LIVE_SAMPLE_RATE
        self.overlap_samples = overlap_seconds * LIVE_SAMPLE_RATE

    def transcribe(self, tape: CompleteMixedTape) -> tuple[GeminiSegment, ...]:
        end = tape.sample_count
        if end == 0:
            return ()
        all_words: list[GeminiWord] = []
        start = 0
        next_id = 1
        while start < end:
            stop = min(end, start + self.chunk_samples)
            parsed = self.diarizer.diarize(tape.read(start_sample=start, end_sample=stop),
                                           deadline=time.monotonic() + 240, kind="terminal",
                                           diarize=self.diarize)
            local_words = [GeminiWord(w.text, w.speaker, w.start_sample + start,
                                      w.end_sample + start) for w in parsed.words]
            local_labels = tuple(dict.fromkeys(w.speaker for w in local_words))
            overlaps: dict[tuple[str, str], int] = {}
            for word in local_words:
                if word.start_sample >= start + self.overlap_samples:
                    continue
                for old in all_words:
                    shared = min(word.end_sample, old.end_sample) - max(word.start_sample, old.start_sample)
                    if shared > 0:
                        key = (word.speaker, old.speaker)
                        overlaps[key] = overlaps.get(key, 0) + shared
            mapping: dict[str, str] = {}
            pairs = sorted(overlaps, key=lambda pair: overlaps[pair], reverse=True)
            claimed: set[str] = set()
            for local, global_id in pairs:
                if local not in mapping and global_id not in claimed:
                    mapping[local] = global_id
                    claimed.add(global_id)
            for local in local_labels:
                if local not in mapping:
                    mapping[local] = f"terminal-{next_id:04d}"
                    next_id += 1
            # The earlier chunk owns the overlap; no duplicated final words.
            cut = start + self.overlap_samples if start else 0
            all_words.extend(GeminiWord(w.text, mapping[w.speaker], w.start_sample, w.end_sample)
                             for w in local_words if w.start_sample >= cut)
            if stop == end:
                break
            start = stop - self.overlap_samples
        if self.identity_policy is not None or self.word_gate is not None:
            pcm = tape.read(start_sample=0, end_sample=end)
            if self.identity_policy is not None:
                all_words = list(self.identity_policy.remap(all_words, pcm))
            if self.word_gate is not None:
                all_words = list(self.word_gate.filter(pcm, all_words))
        if self.word_filter is not None:
            all_words = list(self.word_filter(all_words))
        if self.fixed_speaker is not None:
            all_words = [GeminiWord(w.text, self.fixed_speaker, w.start_sample, w.end_sample)
                         for w in all_words]
        self.last_words = tuple(all_words)
        return speaker_turns(ordered_segments(
            tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                w.text, w.speaker, self.source_lane) for w in all_words),
            start_sample=0, end_sample=end,
        ))
