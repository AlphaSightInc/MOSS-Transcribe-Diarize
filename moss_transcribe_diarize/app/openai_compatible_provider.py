"""OpenAI-compatible `/audio/transcriptions` behind the WindowDiarizer call surface.

One request turns a PCM16 window into `GeminiWords`: timed words with request-local
speaker labels. Labels come from the model when it returns them (`diarized_json`);
otherwise every returned segment gets its own provisional label and the existing
WeSpeaker linking (ContinuityRegistry live, FinalWordPolicy terminal) joins voices.
Text without word times is spread over the request's voiced 10 ms frames, the same
mode-1 WebRTC frames the word gates keep, so placed words survive those gates.

The key is supplied by the caller, sent only as a Bearer header, and never logged,
reported, or put in an exception message.
"""
from __future__ import annotations

import math
import random
import time
from bisect import bisect_left, bisect_right
from typing import Callable, Sequence

import httpx

from .gemini_provider import GeminiWord, GeminiWords, _wav
from .live_span_bounds import LIVE_SAMPLE_RATE

# OpenAI accepts uploads up to 25 MB; 16 kHz PCM16 WAV is 32 kB/s, so 819 s at most.
# The terminal pass sends up to 900 s, which this adapter splits into equal pieces.
MAX_REQUEST_SECONDS = 600
_ATTEMPT_TIMEOUT_SECONDS = 120.0  # Same per-attempt bound as the Gemini HTTP client.
_FRAME = LIVE_SAMPLE_RATE // 100
_FORMAT_WORDS = ("response_format", "verbose_json", "diarized_json", "timestamp_granularities")
_REASONS = {"401": "the service rejected the API key", "403": "the service rejected the API key",
            "404": "URL or model not found", "413": "audio too large for the service",
            "429": "rate limited by the service"}


class OpenAICompatibleError(RuntimeError):
    """A content-free provider failure; `code` feeds `errors_by_code`."""

    def __init__(self, code: str, reason: str, *, format_refused: bool = False):
        super().__init__(f"OpenAI-compatible transcription failed: {reason} ({code})")
        self.code = code
        self.format_refused = format_refused


def first_response_format(model: str) -> str:
    """Speaker labels only exist in `diarized_json`; word times only in `verbose_json`."""
    return "diarized_json" if "diarize" in model.lower() else "verbose_json"


def _form(model: str, response_format: str) -> dict[str, object]:
    form: dict[str, object] = {"model": model, "response_format": response_format}
    if response_format == "diarized_json":
        form["chunking_strategy"] = "auto"  # Required above 30 s of audio.
    elif response_format == "verbose_json":
        form["timestamp_granularities[]"] = ["word", "segment"]
    return form


def _number(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return math.nan


def _voiced_frames(pcm16: bytes, vad) -> list[int]:
    return [i for i in range(len(pcm16) // (2 * _FRAME))
            if vad.is_speech(pcm16[i * 2 * _FRAME:(i + 1) * 2 * _FRAME], LIVE_SAMPLE_RATE)]


def spread_tokens(tokens: Sequence[str], start: int, end: int,
                  voiced: Sequence[int]) -> list[tuple[str, int, int]]:
    """Place ordered tokens over voiced frames in [start, end), by character share."""
    if not tokens or end <= start:
        return []
    frames = voiced[bisect_left(voiced, -(-start // _FRAME)):
                    bisect_right(voiced, end // _FRAME - 1)]
    weights = [len(token) + 1 for token in tokens]
    total = sum(weights)
    if not frames:  # No voice in the span: fall back to uniform time.
        cursor, placed = 0, []
        for token, weight in zip(tokens, weights):
            lo = start + (end - start) * cursor // total
            cursor += weight
            placed.append((token, lo, max(lo + 1, start + (end - start) * cursor // total)))
        return placed

    def at(voiced_sample: int) -> int:
        frame, offset = divmod(min(voiced_sample, len(frames) * _FRAME - 1), _FRAME)
        return frames[frame] * _FRAME + offset

    span = len(frames) * _FRAME
    cursor, placed = 0, []
    for token, weight in zip(tokens, weights):
        lo = span * cursor // total
        cursor += weight
        hi = max(lo + 1, span * cursor // total)
        placed.append((token, at(lo), at(hi - 1) + 1))
    return placed


def parse_transcription(data: dict, *, pcm16: bytes, label_prefix: str = "",
                        vad=None) -> GeminiWords:
    """Map json / verbose_json / diarized_json onto timed, request-local labelled words."""
    samples = len(pcm16) // 2
    limit = samples / LIVE_SAMPLE_RATE + .5
    raw_segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    segments = [row for row in raw_segments if isinstance(row, dict)]
    if not segments and str(data.get("text") or "").strip():
        segments = [{"start": 0, "end": samples / LIVE_SAMPLE_RATE, "text": data["text"]}]

    def label(index: int) -> str:
        speaker = str(segments[index].get("speaker") or "").strip()
        return f"{label_prefix}spk:{speaker}" if speaker else f"{label_prefix}seg:{index}"

    def bounds(row: dict) -> tuple[float, float]:
        return _number(row.get("start")), _number(row.get("end"))

    words: list[GeminiWord] = []
    clamped = dropped = 0
    timed = [row for row in (data.get("words") or ()) if isinstance(row, dict)]
    if timed:  # verbose_json word timestamps; each word takes its nearest segment's label.
        spans = [bounds(row) for row in segments]
        for row in timed:
            text = str(row.get("word") or row.get("text") or "").strip()
            start, end = bounds(row)
            if not text:
                continue
            if not math.isfinite(start) or start > limit:
                dropped += 1
                continue
            if not math.isfinite(end) or end < start or end > limit:
                end = min(start + 1.0, samples / LIVE_SAMPLE_RATE)
                clamped += 1
            middle = (start + end) / 2
            distance = [max(lo - middle, middle - hi, 0.0)
                        if math.isfinite(lo) and math.isfinite(hi) else math.inf
                        for lo, hi in spans]
            owner = (label(distance.index(min(distance))) if distance
                     else f"{label_prefix}seg:0")
            start_sample = max(0, min(samples, round(start * LIVE_SAMPLE_RATE)))
            end_sample = max(start_sample, min(samples, round(end * LIVE_SAMPLE_RATE)))
            words.append(GeminiWord(text, owner, start_sample, end_sample))
        return GeminiWords(tuple(words), clamped, dropped)

    if vad is None:
        import webrtcvad
        vad = webrtcvad.Vad(1)
    voiced = _voiced_frames(pcm16, vad)
    for index, row in enumerate(segments):
        tokens = str(row.get("text") or "").split()
        start, end = bounds(row)
        if not tokens:
            continue
        if not math.isfinite(start) or start > limit:
            dropped += len(tokens)
            continue
        if not math.isfinite(end) or end <= start or end > limit:
            end = samples / LIVE_SAMPLE_RATE
            clamped += len(tokens)
        lo = max(0, min(samples, round(start * LIVE_SAMPLE_RATE)))
        hi = max(0, min(samples, round(end * LIVE_SAMPLE_RATE)))
        if hi <= lo:
            dropped += len(tokens)
            continue
        words.extend(GeminiWord(text, label(index), first, last)
                     for text, first, last in spread_tokens(tokens, lo, hi, voiced))
    return GeminiWords(tuple(words), clamped, dropped)


class OpenAICompatibleDiarizer:
    """WindowDiarizer's surface for `{url}/audio/transcriptions`; sole owner of retries."""

    def __init__(self, url: str, model: str, api_key: str | None,
                 report_usage: Callable[..., None], *, max_attempts: int = 3, vad=None):
        if not url.startswith(("http://", "https://")) or not model.strip():
            raise ValueError("OpenAI-compatible transcription needs an http(s) URL and a model")
        self.endpoint = url.rstrip("/") + "/audio/transcriptions"
        self.model = model.strip()
        self.report_usage = report_usage
        self.max_attempts = max_attempts
        self.response_format = first_response_format(self.model)
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._vad = vad

    def diarize(self, pcm16: bytes, *, deadline: float, kind: str = "rolling",
                diarize: bool = True) -> GeminiWords:
        if len(pcm16) % 2:
            raise ValueError("PCM16 requires complete samples")
        samples = len(pcm16) // 2
        pieces = max(1, math.ceil(samples / (MAX_REQUEST_SECONDS * LIVE_SAMPLE_RATE)))
        size = math.ceil(samples / pieces) if samples else 0
        words: list[GeminiWord] = []
        clamped = dropped = 0
        for piece in range(pieces):
            offset = piece * size
            parsed = self._decode(pcm16[offset * 2:(offset + size) * 2], deadline=deadline,
                                  kind=kind, label_prefix=f"p{piece}:" if pieces > 1 else "")
            words.extend(GeminiWord(w.text, w.speaker if diarize else "spk:?",
                                    w.start_sample + offset, w.end_sample + offset)
                         for w in parsed.words)
            clamped += parsed.clamped
            dropped += parsed.dropped
        return GeminiWords(tuple(words), clamped, dropped)

    def _decode(self, pcm16: bytes, *, deadline: float, kind: str,
                label_prefix: str) -> GeminiWords:
        wav = _wav(pcm16)
        audio_seconds = len(pcm16) / (2 * LIVE_SAMPLE_RATE)
        for attempt in range(self.max_attempts):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("OpenAI-compatible request deadline expired")
            response_format = self.response_format
            try:
                data = self._post(wav, response_format,
                                  timeout=min(_ATTEMPT_TIMEOUT_SECONDS, remaining))
                parsed = parse_transcription(data, pcm16=pcm16, label_prefix=label_prefix,
                                             vad=self._vad)
                self.report_usage(kind=kind, clamped_words=parsed.clamped,
                                  dropped_words=parsed.dropped,
                                  audio_seconds_sent=audio_seconds, cost_usd=0.0)
                return parsed
            except OpenAICompatibleError as exc:
                # A format refusal falls back once to plain json, sticky for this meeting.
                fallback = exc.format_refused and response_format != "json"
                transient = exc.code in {"429", "timeout"} or exc.code.startswith("5")
                retry = (fallback or transient) and attempt + 1 < self.max_attempts
                retry_code = ("response_format" if fallback else exc.code) if retry else None
                self.report_usage(kind=kind, error_code=exc.code, retry_code=retry_code,
                                  audio_seconds_sent=audio_seconds)
                if fallback:
                    self.response_format = "json"
                if not retry:
                    raise
                if fallback:
                    continue
                pause = min(2 ** attempt + random.random(), max(0.0, deadline - time.monotonic()))
                if pause <= 0:
                    raise TimeoutError("OpenAI-compatible request deadline expired") from exc
                time.sleep(pause)
        raise AssertionError("retry loop exhausted")

    def _post(self, wav: bytes, response_format: str, *, timeout: float) -> dict:
        try:
            response = httpx.post(self.endpoint, headers=self._headers,
                                  data=_form(self.model, response_format),
                                  files={"file": ("window.wav", wav, "audio/wav")},
                                  timeout=timeout)
        except httpx.TimeoutException:
            raise OpenAICompatibleError("timeout", "the service did not answer in time") from None
        except httpx.HTTPError as exc:
            raise OpenAICompatibleError(
                "connection_error", f"could not reach the service ({type(exc).__name__})") from None
        if response.status_code != 200:
            code = str(response.status_code)
            raise OpenAICompatibleError(code, _REASONS.get(code, f"HTTP {code}"), format_refused=(
                code == "400" and any(word in response.text for word in _FORMAT_WORDS)))
        try:
            data = response.json()
        except ValueError:
            raise OpenAICompatibleError("bad_response", "the answer was not JSON") from None
        if not isinstance(data, dict):
            raise OpenAICompatibleError("bad_response", "the answer was not a JSON object")
        return data


class NoPreviewWords:
    """Streaming word-source stand-in: this vendor offers no instant preview words."""

    def bind(self, listener) -> None:
        del listener

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        del start_sample, pcm16

    async def finish(self) -> None:
        return None

    def close(self) -> None:
        return None


def probe(url: str, model: str, api_key: str | None, *, timeout: float = 10.0) -> str | None:
    """Settings Test: `GET {url}/models`; None when usable, else a human reason."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        response = httpx.get(url.rstrip("/") + "/models", headers=headers, timeout=timeout)
    except httpx.HTTPError:
        return "Could not reach the transcription service at this URL."
    if response.status_code in {401, 403}:
        return "The transcription service rejected the API key."
    if response.status_code == 404:
        return "No models list at this URL — check it (it usually ends in /v1)."
    if response.status_code != 200:
        return f"The transcription service answered HTTP {response.status_code}."
    try:
        listed = [str(row.get("id")) for row in response.json().get("data") or ()
                  if isinstance(row, dict)]
    except (ValueError, AttributeError):
        listed = []
    if listed and model.strip() not in listed:
        return f"Model {model.strip()} is not offered by this service."
    return None
