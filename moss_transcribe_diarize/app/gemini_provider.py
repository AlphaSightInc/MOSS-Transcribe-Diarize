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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Sequence

from .live_span_bounds import LIVE_SAMPLE_RATE
from .live_tape import CompleteMixedTape
from .gemini_live_runtime import GeminiSegment
from .gemini_coverage import missing_witness_intervals, restore_witnessed_words
from .transcript_text import join_text

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


@dataclass(frozen=True, slots=True)
class TerminalChunk:
    index: int
    start_sample: int
    end_sample: int
    core_end_sample: int
    words: tuple[GeminiWord, ...]  # Absolute samples, Gemini annotation order.


def repair_word_timestamps(words: Sequence[GeminiWord],
                           audio_samples: int) -> tuple[tuple[GeminiWord, ...], int]:
    """Repair measured long-call offset excursions in Gemini annotation order."""
    fixed = list(words)
    changed: set[int] = set()
    jump = 10 * LIVE_SAMPLE_RATE
    long_duration = 5 * LIVE_SAMPLE_RATE
    tenth = LIVE_SAMPLE_RATE // 10
    for i in range(1, len(words) - 1):
        previous, word, following = words[i-1], words[i], words[i+1]
        isolated = (abs(word.start_sample-previous.start_sample) > jump
                    and abs(word.start_sample-following.start_sample) > jump
                    and abs(previous.start_sample-following.start_sample) <= jump
                    and previous.end_sample-previous.start_sample <= long_duration
                    and following.end_sample-following.start_sample <= long_duration)
        duration_outlier = word.end_sample-word.start_sample > long_duration
        if not (isolated or duration_outlier):
            continue
        if isolated:
            start = max(previous.start_sample,
                        min(following.start_sample,
                            round((previous.end_sample+following.start_sample)/2)))
            length = min(max(word.end_sample-word.start_sample, tenth), LIVE_SAMPLE_RATE)
            end = (min(start+length, following.start_sample)
                   if following.start_sample > start else start+length)
        else:
            start = word.start_sample
            end = (min(start+LIVE_SAMPLE_RATE, following.start_sample)
                   if following.start_sample > start else start+LIVE_SAMPLE_RATE)
        if end <= start:
            end = start+tenth
        start, end = max(0, min(start, audio_samples)), max(0, min(end, audio_samples))
        if end > start:
            fixed[i] = GeminiWord(word.text, word.speaker, start, end)
            changed.add(i)
    i = 1
    while i < len(fixed) - 1:
        first_jump = fixed[i].start_sample-fixed[i-1].start_sample
        if abs(first_jump) <= jump:
            i += 1
            continue
        end = next((j for j in range(i+1, min(i+31, len(fixed)))
                    if first_jump*(fixed[j].start_sample-fixed[j-1].start_sample) < 0
                    and abs(fixed[j].start_sample-fixed[i-1].start_sample) <= jump), None)
        if end is None or any(fixed[k].end_sample-fixed[k].start_sample > long_duration
                              for k in range(i, end)):
            i += 1
            continue
        shift = round(((fixed[i-1].end_sample+fixed[end].start_sample)
                       -(fixed[i].start_sample+fixed[end-1].end_sample))/2)
        if all(0 <= fixed[k].start_sample+shift < fixed[k].end_sample+shift <= audio_samples
               for k in range(i, end)):
            for k in range(i, end):
                word = fixed[k]
                fixed[k] = GeminiWord(word.text, word.speaker,
                                      word.start_sample+shift, word.end_sample+shift)
                changed.add(k)
            i = end
        else:
            i += 1
    return tuple(fixed), len(changed)


def ordered_segments(rows: Sequence[GeminiSegment], *, start_sample: int,
                     end_sample: int,
                     preserve_order: bool = False) -> tuple[GeminiSegment, ...]:
    """Project timestamped provider words onto LiveSession's one-owner sample line."""
    kept = (row for row in rows if row.text and row.start_sample < end_sample
            and row.end_sample > start_sample)
    ordered = list(kept) if preserve_order else sorted(
        kept, key=lambda row: (row.start_sample, row.end_sample))
    result: list[GeminiSegment] = []
    cursor = start_sample
    for row in ordered:
        start = max(cursor, row.start_sample, start_sample)
        if start >= end_sample:
            # In the rare fully overlapping tail, preserve text in the final row.
            if result:
                prior = result[-1]
                result[-1] = GeminiSegment(prior.start_sample, prior.end_sample,
                                            join_text(prior.text, row.text), prior.speaker,
                                            prior.source_lane)
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
                                      join_text(prior.text, row.text), prior.speaker, prior.source_lane)
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


def _usage_cost_parts(usage: dict) -> tuple[float, float]:
    audio_in = text_in = 0
    for row in usage.get("input_tokens_by_modality") or ():
        tokens = int(row.get("tokens") or 0)
        if str(row.get("modality", "")).lower() == "audio":
            audio_in += tokens
        else:
            text_in += tokens
    out = int(usage.get("total_output_tokens") or 0) + int(usage.get("total_thought_tokens") or 0)
    return (2 * (audio_in + text_in) / 1_000_000, 12 * out / 1_000_000)


def _usage_cost(usage: dict) -> float:
    return sum(_usage_cost_parts(usage))


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

    def __init__(self, client: object, report_usage: Callable[..., None], *, max_attempts: int = 3,
                 model: str = MODEL):
        self.client = client
        self.report_usage = report_usage
        self.max_attempts = max_attempts
        self.model = model

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
                    model=self.model,
                    input=[{"type": "audio", "data": payload, "mime_type": "audio/wav"}],
                    generation_config={"transcription_config": {"mode": mode}},
                )
                data = response.model_dump(exclude_none=True, mode="json")
                parsed = parse_words(data, audio_samples=len(pcm16) // 2)
                repaired = 0
                if kind in {"rolling", "terminal"}:
                    fixed, repaired = repair_word_timestamps(parsed.words, len(pcm16) // 2)
                    parsed = GeminiWords(fixed, parsed.clamped, parsed.dropped)
                metered_input, metered_output = _usage_cost_parts(data.get("usage") or {})
                self.report_usage(kind=kind, clamped_words=parsed.clamped, dropped_words=parsed.dropped,
                                  repaired_words=repaired,
                                  audio_seconds_sent=audio_seconds,
                                  output_cost_estimate_usd=audio_seconds / 60 * .002,
                                  cost_usd=metered_input + metered_output,
                                  metered_output_usd=metered_output)
                return parsed
            except Exception as exc:
                code = _error_code(exc)
                transient = code in {"429", "timeout"} or (code.isdigit() and 500 <= int(code) < 600)
                retry = transient and attempt + 1 < self.max_attempts
                self.report_usage(kind=kind, error_code=code, retry_code=code if retry else None,
                                  audio_seconds_sent=audio_seconds,
                                  output_cost_estimate_usd=audio_seconds / 60 * .002)
                if not retry:
                    raise
                pause = min(2 ** attempt + random.random(), max(0.0, deadline - time.monotonic()))
                if pause <= 0:
                    raise TimeoutError("Gemini request deadline expired") from exc
                time.sleep(pause)
        raise AssertionError("retry loop exhausted")


class TerminalTranscriber:
    """Whole-meeting chunk pass; overlap resolves local labels by word-time agreement."""

    def __init__(self, diarizer: WindowDiarizer, *, chunk_seconds: int = 900,
                 overlap_seconds: int = 30, identity_policy=None, word_gate=None,
                 diarize: bool = True, word_filter=None, witness_filter=None,
                 source_lane: str | None = None, fixed_speaker: str | None = None,
                 report_usage: Callable[..., None] | None = None,
                 stitcher=None, voiced_audio: Callable[[bytes], bool] | None = None):
        if not 0 < overlap_seconds < chunk_seconds <= 900:
            raise ValueError("terminal chunks must be at most 900 seconds with a smaller overlap")
        self.diarizer = diarizer
        self.identity_policy = identity_policy
        self.word_gate = word_gate
        self.diarize = diarize
        self.word_filter = word_filter
        self.witness_filter = witness_filter
        self.source_lane = source_lane
        self.fixed_speaker = fixed_speaker
        self.report_usage = report_usage
        self.stitcher = stitcher
        self.voiced_audio = voiced_audio
        self.last_words: tuple[GeminiWord, ...] = ()
        self.coverage_gaps: tuple[tuple[int, int], ...] = ()
        self._witness: tuple[GeminiSegment, ...] = ()
        self._witness_words: tuple[GeminiWord, ...] = ()
        self.chunk_samples = chunk_seconds * LIVE_SAMPLE_RATE
        self.overlap_samples = overlap_seconds * LIVE_SAMPLE_RATE

    def set_witness(self, rows: Sequence[GeminiSegment]) -> None:
        self._witness = tuple(rows)

    def set_witness_words(self, words: Sequence[GeminiWord]) -> None:
        self._witness_words = tuple(words)

    def transcribe_interval(self, tape: CompleteMixedTape, start_sample: int,
                            end_sample: int) -> tuple[GeminiSegment, ...]:
        """Run the existing terminal path on only one uncovered accepted interval."""
        if not 0 <= start_sample < end_sample <= tape.sample_count:
            raise ValueError("terminal interval is outside accepted audio")
        class IntervalTape:
            sample_count = end_sample - start_sample
            sample_offset = start_sample
            def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
                stop = self.sample_count if end_sample is None else end_sample
                if not 0 <= start_sample < stop <= self.sample_count:
                    raise ValueError("terminal interval read is out of bounds")
                return tape.read(start_sample=start_sample + self.sample_offset,
                                 end_sample=stop + self.sample_offset)
        rows = self.transcribe(IntervalTape())
        self.coverage_gaps = tuple((start + start_sample, end + start_sample)
                                   for start, end in self.coverage_gaps)
        return tuple(GeminiSegment(row.start_sample + start_sample,
                                   row.end_sample + start_sample, row.text,
                                   row.speaker, row.source_lane) for row in rows)

    def transcribe(self, tape: CompleteMixedTape) -> tuple[GeminiSegment, ...]:
        self.coverage_gaps = ()
        end = tape.sample_count
        if end == 0:
            return ()
        chunked = end > self.chunk_samples
        if chunked and self.report_usage is not None:
            self.report_usage(kind="terminal", count_call=False, chunked=True)
        all_words: list[GeminiWord] = []
        chunks: list[TerminalChunk] = []
        previous_chunk_words: list[GeminiWord] = []
        schedule: list[tuple[int, int, int]] = []
        start = 0
        while start < end:
            stop = min(end, start + self.chunk_samples)
            core_end = end if stop == end else stop - self.overlap_samples
            schedule.append((start, stop, core_end))
            if stop == end:
                break
            start = stop - self.overlap_samples
        decode = getattr(self.diarizer, "diarize_terminal", self.diarizer.diarize)
        def decode_checked(pcm: bytes, start: int, stop: int) -> tuple[GeminiWords, tuple[tuple[int, int], ...]]:
            witness = tuple((max(start, row.start_sample), min(stop, row.end_sample))
                            for row in self._witness if row.text.strip()
                            and row.start_sample < stop and row.end_sample > start)
            parsed = decode(pcm, deadline=time.monotonic() + 240,
                            kind="terminal", diarize=self.diarize)
            gaps = missing_witness_intervals(
                witness, tuple((start+w.start_sample, start+w.end_sample)
                               for w in parsed.words))
            if gaps:
                if self.report_usage is not None:
                    self.report_usage(kind="terminal", count_call=False, coverage_retry=1)
                parsed = decode(pcm, deadline=time.monotonic() + 240,
                                kind="terminal", diarize=self.diarize)
                gaps = missing_witness_intervals(
                    witness, tuple((start+w.start_sample, start+w.end_sample)
                                   for w in parsed.words))
            return parsed, gaps
        next_id = 1
        with ThreadPoolExecutor(max_workers=min(3, len(schedule)),
                                thread_name_prefix="gemini-final") as executor:
            for offset in range(0, len(schedule), 3):
                batch = schedule[offset:offset+3]
                pending = []
                for start, stop, _core_end in batch:
                    pcm = tape.read(start_sample=start, end_sample=stop)
                    pending.append(None if self.voiced_audio is not None
                                   and not self.voiced_audio(pcm) else
                                   executor.submit(decode_checked, pcm, start, stop))
                for (start, stop, core_end), future in zip(batch, pending):
                    parsed, gaps = future.result() if future is not None else (GeminiWords(()), ())
                    if gaps:
                        self.coverage_gaps += tuple((lo, min(hi, core_end))
                                                    for lo, hi in gaps if lo < core_end)
                        if self.report_usage is not None:
                            self.report_usage(kind="terminal", count_call=False,
                                              terminal_coverage_fallbacks=1)
                    local_words = [GeminiWord(w.text, w.speaker, w.start_sample + start,
                                              w.end_sample + start) for w in parsed.words]
                    chunks.append(TerminalChunk(len(chunks), start, stop, core_end,
                                                tuple(local_words)))
                    local_labels = tuple(dict.fromkeys(w.speaker for w in local_words))
                    overlaps: dict[tuple[str, str], int] = {}
                    for word in local_words:
                        if word.start_sample >= start + self.overlap_samples:
                            continue
                        for old in previous_chunk_words:
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
                    mapped_words = [GeminiWord(w.text, mapping[w.speaker], w.start_sample, w.end_sample)
                                    for w in local_words]
                    all_words.extend(w for w in mapped_words
                                     if start <= (w.start_sample+w.end_sample)/2 < core_end)
                    previous_chunk_words = mapped_words
        offset = getattr(tape, "sample_offset", 0)
        restore = bool(self._witness_words) and not hasattr(tape, "sample_offset")
        if not any(chunk.words for chunk in chunks) and not (restore and self.witness_filter):
            self.last_words = ()
            return ()
        restored = []
        if self.identity_policy is not None or self.word_gate is not None or (chunked and self.stitcher) or restore:
            pcm = tape.read(start_sample=0, end_sample=end)
            if chunked and self.stitcher is not None:
                all_words = list(self.stitcher.stitch(chunks, pcm))
            elif self.identity_policy is not None:
                all_words = list(self.identity_policy.remap(all_words, pcm))
            raw_cleanup = tuple(all_words)
            if restore and self.source_lane != "microphone":
                all_words, restored = restore_witnessed_words(
                    all_words, self._witness_words, skip=self.coverage_gaps)
            if self.word_gate is not None:
                all_words = list(self.word_gate.filter(pcm, all_words))
        if self.word_filter is not None:
            absolute = [GeminiWord(w.text, w.speaker, w.start_sample + offset,
                                   w.end_sample + offset) for w in all_words]
            all_words = [GeminiWord(w.text, w.speaker, w.start_sample - offset,
                                    w.end_sample - offset)
                         for w in self.word_filter(absolute)]
        if restore and self.source_lane == "microphone" and self.witness_filter is not None:
            all_words, restored = self.witness_filter(
                raw_cleanup, tuple(all_words), self._witness_words, self.coverage_gaps)
        if restored and self.report_usage is not None:
            self.report_usage(kind="terminal", count_call=False,
                              witness_restored_words=sum(len(run["text"]) for run in restored))
        if self.fixed_speaker is not None:
            all_words = [GeminiWord(w.text, self.fixed_speaker, w.start_sample, w.end_sample)
                         for w in all_words]
        self.last_words = tuple(GeminiWord(w.text, w.speaker, w.start_sample + offset,
                                           w.end_sample + offset) for w in all_words)
        return speaker_turns(ordered_segments(
            tuple(GeminiSegment(w.start_sample, max(w.end_sample, w.start_sample + 1),
                                w.text, w.speaker, self.source_lane) for w in all_words),
            start_sample=0, end_sample=end, preserve_order=True,
        ))
