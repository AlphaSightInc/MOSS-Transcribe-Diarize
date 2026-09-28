"""Shared Gemini helpers for the gemini-live bake-off prototypes (throwaway; not product code).

- load_key(): GEMINI_API_KEY from the worktree .env.local (never printed).
- diarize_window(pcm16, ...): one Gemini 3.5 Transcribe call (verbatim + speaker diarization + word
  timestamps) over a PCM16 16 kHz mono slice; returns words with window-local speaker labels.
  Results are cached on disk keyed by (audio bytes, model, config) so re-running an offline
  simulation never re-pays an identical call.
- words_to_segments(): contiguous same-speaker words -> segments.
- ledger(): append usage/cost/latency rows for spend accounting.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import random
import time
import warnings
import wave
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", message=".*Interactions usage is experimental.*")

WORKTREE = Path(__file__).resolve().parents[3]
CACHE_DIR = WORKTREE / "prototypes" / "gemini-live" / ".cache"
LEDGER_DIR = WORKTREE / "prototypes" / "gemini-live" / ".ledger"
SAMPLE_RATE = 16000

# USD per 1M tokens, paid tier (ai.google.dev/gemini-api/docs/pricing, read 2026-09-28).
PRICES = {
    "gemini-3.5-transcribe": {"audio_in": 2.00, "text_in": 2.00, "text_out": 12.00},
    "gemini-3.5-transcribe-live": {"audio_in": 3.50, "text_in": 3.50, "text_out": 21.00},
    "gemini-3.8-live": {"audio_in": 3.00, "text_in": 0.75, "text_out": 4.50, "audio_out": 12.00},
    "gemini-3.8-flash": {"audio_in": 0.75, "text_in": 0.75, "text_out": 4.50},
}


def load_key() -> str:
    # The worktree .env.local is authoritative: the login shell exports an unrelated
    # GEMINI_API_KEY (sk-…) that Google rejects as API_KEY_INVALID.
    for line in (WORKTREE / ".env.local").read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("GEMINI_API_KEY missing (worktree .env.local)")


_client = None


def client():
    global _client
    if _client is None:
        from google import genai
        _client = genai.Client(api_key=load_key())
    return _client


def read_wav(path: str | Path) -> np.ndarray:
    """PCM16 mono 16 kHz samples as int16 array."""
    import soundfile as sf
    audio, sr = sf.read(str(path), dtype="int16", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1).astype(np.int16)
    if sr != SAMPLE_RATE:
        raise ValueError(f"{path}: sample rate {sr} != 16000")
    return audio


def wav_bytes(pcm16: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(np.asarray(pcm16, dtype=np.int16).tobytes())
    return buf.getvalue()


@dataclass(frozen=True)
class Word:
    text: str
    speaker: str  # window-local label, e.g. "spk:0"
    start: float  # seconds relative to the window start
    end: float


@dataclass
class WindowResult:
    words: list[Word]
    text: str
    latency_s: float  # wall time of the (uncached) call
    usage: dict
    cached: bool
    model: str

    def cost_usd(self) -> float:
        return usage_cost(self.model, self.usage)


def _secs(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value).rstrip("s"))


def usage_cost(model: str, usage: dict) -> float:
    p = PRICES.get(model)
    if not p or not usage:
        return 0.0
    audio_in = text_in = 0
    for row in usage.get("input_tokens_by_modality") or []:
        if row.get("modality") == "audio":
            audio_in += int(row.get("tokens") or 0)
        else:
            text_in += int(row.get("tokens") or 0)
    out = int(usage.get("total_output_tokens") or 0) + int(usage.get("total_thought_tokens") or 0)
    return (audio_in * p["audio_in"] + text_in * p["text_in"] + out * p["text_out"]) / 1e6


def diarize_window(
    pcm16: np.ndarray,
    *,
    model: str = "gemini-3.5-transcribe",
    diarize: bool = True,
    word_timestamps: bool = True,
    language_codes: list[str] | None = None,
    use_cache: bool = True,
    max_attempts: int = 6,
    ledger_lane: str | None = None,
) -> WindowResult:
    audio = wav_bytes(pcm16)
    mode: dict = {"type": "verbatim"}
    if diarize:
        mode["diarization_mode"] = "speaker"
    if word_timestamps:
        mode["timestamp_granularities"] = ["word"]
    tc: dict = {"mode": mode}
    if language_codes:
        tc["language_codes"] = language_codes
    config = {"transcription_config": tc}
    key = hashlib.sha256(audio + json.dumps([model, config], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / key[:2] / f"{key}.json"
    if use_cache and path.exists():
        raw = json.loads(path.read_text())
        return _parse(raw, cached=True)
    payload = base64.b64encode(audio).decode()
    last: Exception | None = None
    for attempt in range(max_attempts):
        t0 = time.monotonic()
        try:
            r = client().interactions.create(
                model=model,
                input=[{"type": "audio", "data": payload, "mime_type": "audio/wav"}],
                generation_config=config,
            )
            latency = time.monotonic() - t0
            d = r.model_dump(exclude_none=True, mode="json")
            raw = {"model": model, "latency_s": latency, "response": d,
                   "audio_seconds": len(pcm16) / SAMPLE_RATE}
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(raw))
            res = _parse(raw, cached=False)
            if ledger_lane:
                ledger(ledger_lane, {"kind": "diarize_window", "model": model,
                                     "audio_s": len(pcm16) / SAMPLE_RATE, "latency_s": latency,
                                     "cost_usd": res.cost_usd(), "usage": res.usage})
            return res
        except Exception as exc:  # retry transient API failures with jittered backoff
            last = exc
            msg = str(exc)
            transient = any(s in msg for s in ("429", "500", "502", "503", "504", "RESOURCE_EXHAUSTED",
                                                "UNAVAILABLE", "DEADLINE", "timed out", "Timeout"))
            if ledger_lane:
                ledger(ledger_lane, {"kind": "error", "model": model, "attempt": attempt,
                                     "error": msg[:300]})
            if not transient or attempt == max_attempts - 1:
                raise
            time.sleep(min(60.0, 2 ** attempt + random.random()))
    raise RuntimeError(f"unreachable: {last}")


def _parse(raw: dict, *, cached: bool) -> WindowResult:
    d = raw["response"]
    words: list[Word] = []
    for step in d.get("steps") or []:
        for content in step.get("content") or []:
            for a in content.get("annotations") or []:
                if a.get("type") != "word_info":
                    continue
                words.append(Word(text=a.get("text", ""), speaker=str(a.get("speaker", "spk:?")),
                                  start=_secs(a.get("start_offset")), end=_secs(a.get("end_offset"))))
    return WindowResult(words=words, text=d.get("output_text") or "", latency_s=raw.get("latency_s", 0.0),
                        usage=d.get("usage") or {}, cached=cached, model=raw.get("model", ""))


def words_to_segments(words: list[Word], *, offset: float = 0.0, max_gap: float = 1.5,
                      speaker_map: dict[str, str] | None = None) -> list[dict]:
    """Group contiguous same-speaker words into segments {start,end,speaker,text} (absolute seconds)."""
    segs: list[dict] = []
    for w in words:
        spk = speaker_map.get(w.speaker, w.speaker) if speaker_map else w.speaker
        s, e = offset + w.start, offset + max(w.end, w.start)
        if segs and segs[-1]["speaker"] == spk and s - segs[-1]["end"] <= max_gap:
            segs[-1]["end"] = max(segs[-1]["end"], e)
            segs[-1]["text"] += " " + w.text
        else:
            segs.append({"start": s, "end": e, "speaker": spk, "text": w.text})
    return segs


def ledger(lane: str, row: dict) -> None:
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    row = {"t": time.time(), **row}
    with open(LEDGER_DIR / f"{lane}.jsonl", "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


def spend(lane: str | None = None) -> dict:
    """Total recorded spend (USD) and audio seconds per lane from the ledger."""
    out: dict = {}
    for p in sorted(LEDGER_DIR.glob("*.jsonl")) if LEDGER_DIR.exists() else []:
        if lane and p.stem != lane:
            continue
        cost = audio = 0.0
        n = err = 0
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r.get("kind") == "error":
                err += 1
                continue
            n += 1
            cost += float(r.get("cost_usd") or 0)
            audio += float(r.get("audio_s") or 0)
        out[p.stem] = {"calls": n, "errors": err, "cost_usd": round(cost, 4), "audio_s": round(audio, 1)}
    return out


if __name__ == "__main__":
    print(json.dumps(spend(), indent=1))
