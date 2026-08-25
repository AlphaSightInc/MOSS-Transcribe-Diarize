"""P1 - repair a decode that `parse_transcript` would discard.

The decoder emitted words; it omitted the closing `[end]` timestamp (and sometimes the
opening one), which the production parser requires. This reconstructs the missing timestamps
from the span's own bounds instead of throwing the words away. No new decode request.
"""
from __future__ import annotations

import re

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

_TOKEN = re.compile(r"\[([^\]]*)\]")
_TS = re.compile(r"^\d+(\.\d+)?$")
_SPK = re.compile(r"^S\d+$")

# Refusal / instruction-following artefacts the decoder emits when handed near-silence. They
# are never speech, and a salvage policy that commits them injects words that were not said.
REFUSAL_MARKERS = (
    "i'm sorry, i can't assist",
    "i cannot assist",
    "抱歉",
)


def looks_like_refusal(text: str) -> bool:
    low = text.strip().lower()
    return any(m in low for m in REFUSAL_MARKERS)


def salvage(text: str, *, duration_s: float) -> list[TranscriptSegment]:
    """Best-effort segments for a transcript the production parser drops."""

    text = (text or "").strip()
    if not text:
        return []
    already = parse_transcript(text)
    if already:
        return already

    # Split into (kind, value) tokens and the plain text between them.
    parts: list[tuple[str, str]] = []
    cursor = 0
    for m in _TOKEN.finditer(text):
        if m.start() > cursor:
            parts.append(("text", text[cursor : m.start()]))
        value = m.group(1)
        if _TS.match(value):
            parts.append(("ts", value))
        elif _SPK.match(value.strip()):
            parts.append(("spk", value.strip()))
        else:
            parts.append(("text", m.group(0)))
        cursor = m.end()
    if cursor < len(text):
        parts.append(("text", text[cursor:]))

    # Group into speaker-led chunks: [ts?][Sxx] text [ts?]
    chunks: list[dict] = []
    pending_ts: float | None = None
    for kind, value in parts:
        if kind == "ts":
            if chunks and chunks[-1]["text"] and chunks[-1]["end"] is None:
                chunks[-1]["end"] = float(value)
            else:
                pending_ts = float(value)
        elif kind == "spk":
            chunks.append({"speaker": value, "start": pending_ts, "end": None, "text": ""})
            pending_ts = None
        else:
            if not chunks:
                chunks.append({"speaker": "S01", "start": pending_ts, "end": None, "text": ""})
                pending_ts = None
            chunks[-1]["text"] += value

    chunks = [c for c in chunks if c["text"].strip()]
    if not chunks:
        return []

    # Fill missing bounds: unknown starts/ends interpolate over the span by text length.
    lengths = [max(len(c["text"].strip()), 1) for c in chunks]
    total = sum(lengths)
    edges = [0.0]
    for length in lengths:
        edges.append(edges[-1] + duration_s * length / total)
    out: list[TranscriptSegment] = []
    for i, c in enumerate(chunks):
        start = c["start"] if c["start"] is not None else edges[i]
        end = c["end"] if c["end"] is not None else edges[i + 1]
        start = min(max(0.0, float(start)), duration_s)
        end = min(max(float(end), start), duration_s)
        if end <= start:
            end = min(duration_s, start + 0.01)
        out.append(TranscriptSegment(start=start, end=end, speaker=c["speaker"], text=c["text"].strip()))
    return out
