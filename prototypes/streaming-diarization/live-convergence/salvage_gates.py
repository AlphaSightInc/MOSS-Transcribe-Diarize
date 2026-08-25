"""Candidate `classify_live_transcript`, built to answer plan §9.1 (O1 vs O2).

Throwaway prototype. It exists so the two proposed gates can be run over the saved 184-span
corpus without shipping either of them; the winner is ported into
`moss_transcribe_diarize/app/live_span_bounds.py` by plan §9.3.

The completion rule is preregistered in `PREREGISTRATION-M1a.md`. In one sentence: absent
*outer* bounds are supplied from the span's own bounds, absent *interior* boundaries are
supplied only from a timestamp the decoder actually emitted, and a span whose two adjacent
speaker labels differ with no timestamp between them is refused rather than guessed — a guessed
cross-speaker boundary would hand the identity path an interval holding another speaker's audio.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_span_bounds import (  # noqa: E402
    render_segments,
    span_duration_seconds,
    span_segments,
)
from moss_transcribe_diarize.transcript_parser import TranscriptSegment  # noqa: E402

_BRACKET = re.compile(r"\[([^\]]*)\]")
_TIMESTAMP = re.compile(r"^\d+(?:\.\d+)?$")
_SPEAKER = re.compile(r"^S\d+$")

#: Gate names as plan §9.1 words them.
GATE_O1 = "O1_hard_cap"
GATE_O2 = "O2_speech_ratio"
O2_SPEECH_RATIO_FLOOR = 0.5

#: Every disposition this classifier can return.  `parsed` and `empty_text` are today's
#: behaviour restated; the rest are the ones M1 adds.
PARSED = "parsed"
EMPTY_TEXT = "empty_text"
SALVAGED = "salvaged"
REFUSED_GRAMMAR = "refused_grammar"
REFUSED_INTERIOR_BOUNDARY = "refused_interior_boundary"
REFUSED_FIXED_POINT = "refused_fixed_point"
REFUSED_GATE = "refused_gate"
REFUSED_BOILERPLATE = "refused_boilerplate"


@dataclass(frozen=True)
class SalvageOutcome:
    disposition: str
    reason: str
    segments: tuple[TranscriptSegment, ...] = ()
    rendered: str = ""

    @property
    def publishes(self) -> bool:
        return self.disposition in (PARSED, SALVAGED) and bool(self.segments)


@dataclass
class _Chunk:
    speaker: str
    text: str
    start: float | None
    end: float | None


def _tokenize(text: str) -> list[tuple[str, str]] | None:
    """Split into ('ts'|'spk'|'text', value) runs, or None if a bracket is neither."""
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in _BRACKET.finditer(text):
        if match.start() > cursor:
            parts.append(("text", text[cursor : match.start()]))
        value = match.group(1).strip()
        if _TIMESTAMP.match(value):
            parts.append(("ts", value))
        elif _SPEAKER.match(value):
            parts.append(("spk", value))
        else:
            return None
        cursor = match.end()
    if cursor < len(text):
        parts.append(("text", text[cursor:]))
    return parts


def _chunks(parts: Sequence[tuple[str, str]]) -> list[_Chunk] | None:
    chunks: list[_Chunk] = []
    pending_start: float | None = None
    for kind, value in parts:
        if kind == "ts":
            if chunks and chunks[-1].text.strip() and chunks[-1].end is None:
                chunks[-1].end = float(value)
            else:
                pending_start = float(value)
        elif kind == "spk":
            chunks.append(_Chunk(speaker=value, text="", start=pending_start, end=None))
            pending_start = None
        else:
            if not chunks:
                # Words before any speaker marker: the grammar names a speaker for every word,
                # and inventing one is exactly what this module refuses to do.
                if value.strip():
                    return None
                continue
            chunks[-1].text += value
    return [chunk for chunk in chunks if chunk.text.strip()]


def _merge_same_speaker(chunks: list[_Chunk]) -> list[_Chunk]:
    """Join adjacent same-speaker chunks that have no timestamp between them.

    Lossless: same words, same label, and no boundary is created where the decoder emitted none.
    """
    merged: list[_Chunk] = []
    for chunk in chunks:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.speaker == chunk.speaker
            and previous.end is None
            and chunk.start is None
        ):
            previous.text += chunk.text
            previous.end = chunk.end
            continue
        merged.append(_Chunk(chunk.speaker, chunk.text, chunk.start, chunk.end))
    return merged


def _complete_bounds(chunks: list[_Chunk], duration: float) -> str | None:
    """Fill absent bounds; return a refusal reason if any boundary would have to be invented."""
    if chunks[0].start is None:
        chunks[0].start = 0.0
    if chunks[-1].end is None:
        chunks[-1].end = duration
    for index in range(1, len(chunks)):
        previous, current = chunks[index - 1], chunks[index]
        if current.start is None and previous.end is not None:
            current.start = previous.end
        elif previous.end is None and current.start is not None:
            previous.end = current.start
        if previous.end is None or current.start is None:
            return f"chunk {index} boundary absent between speakers {previous.speaker}/{current.speaker}"
    for index, chunk in enumerate(chunks):
        if chunk.start is None or chunk.end is None:
            return f"chunk {index} has an absent bound after completion"
        if chunk.end < chunk.start:
            return f"chunk {index} ends before it starts ({chunk.start} > {chunk.end})"
        if index and chunk.start < chunks[index - 1].start:
            return f"chunk {index} starts before chunk {index - 1}"
    return None


def _fixed_point(segments: Sequence[TranscriptSegment], sample_count: int) -> tuple[bool, str]:
    rendered = render_segments(segments, lambda segment: segment.speaker)
    reparsed = span_segments(rendered, sample_count=sample_count)
    if not reparsed:
        return False, rendered
    again = render_segments(reparsed, lambda segment: segment.speaker)
    return again == rendered, rendered


def classify(
    raw_text: str,
    *,
    sample_count: int,
    freeze_reason: str,
    speech_ratio: float | None,
    gate: str,
    is_boilerplate: Callable[[str], bool] | None = None,
) -> SalvageOutcome:
    """Decide what a span's raw decode may publish under ``gate``."""

    text = (raw_text or "").strip()
    if not text:
        return SalvageOutcome(EMPTY_TEXT, "decoder returned no text")

    parsed = span_segments(text, sample_count=sample_count)
    if parsed:
        return SalvageOutcome(PARSED, "parses under the production grammar", parsed, text)

    parts = _tokenize(text)
    if parts is None:
        return SalvageOutcome(REFUSED_GRAMMAR, "bracket token is neither a timestamp nor a speaker")
    chunks = _chunks(parts)
    if chunks is None:
        return SalvageOutcome(REFUSED_GRAMMAR, "words appear before any speaker marker")
    if not chunks:
        return SalvageOutcome(REFUSED_GRAMMAR, "no speaker-attributed words")

    chunks = _merge_same_speaker(chunks)
    duration = span_duration_seconds(sample_count)
    refusal = _complete_bounds(chunks, duration)
    if refusal is not None:
        return SalvageOutcome(REFUSED_INTERIOR_BOUNDARY, refusal)

    segments = span_segments(
        render_segments(
            [
                TranscriptSegment(
                    start=float(chunk.start), end=float(chunk.end), speaker=chunk.speaker, text=chunk.text.strip()
                )
                for chunk in chunks
            ],
            lambda segment: segment.speaker,
        ),
        sample_count=sample_count,
    )
    if not segments:
        return SalvageOutcome(REFUSED_FIXED_POINT, "completed transcript still parses to nothing")
    held, rendered = _fixed_point(segments, sample_count)
    if not held:
        return SalvageOutcome(REFUSED_FIXED_POINT, "parse -> render -> parse is not a fixed point")

    if is_boilerplate is not None and is_boilerplate(" ".join(s.text for s in segments)):
        return SalvageOutcome(REFUSED_BOILERPLATE, "text matches known non-speech boilerplate", (), rendered)

    if gate == GATE_O1:
        if freeze_reason != "hard_cap":
            return SalvageOutcome(REFUSED_GATE, f"freeze reason {freeze_reason!r} is not hard_cap", (), rendered)
    elif gate == GATE_O2:
        if speech_ratio is None:
            return SalvageOutcome(REFUSED_GATE, "no speech ratio available", (), rendered)
        if speech_ratio < O2_SPEECH_RATIO_FLOOR:
            return SalvageOutcome(
                REFUSED_GATE, f"speech ratio {speech_ratio:.3f} < {O2_SPEECH_RATIO_FLOOR}", (), rendered
            )
    else:
        raise ValueError(f"unknown gate: {gate}")

    return SalvageOutcome(SALVAGED, "absent bounds completed from the span", segments, rendered)


__all__ = [
    "GATE_O1",
    "GATE_O2",
    "O2_SPEECH_RATIO_FLOOR",
    "SalvageOutcome",
    "classify",
]
