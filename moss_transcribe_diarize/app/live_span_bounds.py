"""The live audio grid and the one rule for a decoder timestamp outside its own span.

Three places used to state that rule and disagree with nothing but themselves: the identity
preparer, the session's canonical validation and the provider decode path each parsed the
transcript and refused any segment outside ``[0, span duration]``. They are all one call
now, because fixing one alone relocates the failure instead of removing it.

*The rule, decided under the third prd.md amendment (J1): a timestamp outside the span is
**clamped into** the span, never refused.* A hard-cap span is 2.5 s of unbroken speech by
construction -- it exists precisely because no endpoint was found -- and the decoder places
its closing marker at approximately the end of whatever audio it is handed, so a span that
ends inside speech reports an end at or just past its own duration. A 33-span sweep against
the deployed decoder measured that on 2 of 33 spans, at +0.01 s and +0.02 s: two
quantisation ticks, so the obvious "allow one tick" tolerance would still have ended the
meeting, and any fixed epsilon is a guess about a tail nobody has sampled. A clamp cannot be
exceeded. It is also already this codebase's answer one call later --
``live_provider_bundle._speaker_intervals_by_label`` clamps these same segments before
scoring them -- so this moves an existing policy to where the value is first read rather
than inventing one.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Callable, Iterable

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

from .live_endpoint import HARD_CAP_REASON

LIVE_SAMPLE_RATE = 16000


def span_duration_seconds(sample_count: int) -> float:
    return sample_count / float(LIVE_SAMPLE_RATE)


def span_segments(transcript: str, *, sample_count: int) -> tuple[TranscriptSegment, ...]:
    """Parse ``transcript`` into segments whose timestamps lie inside the span.

    Returns ``()`` for a transcript that parses to nothing. That is a different condition
    with several right answers -- commit the span empty, abstain, refuse the provider -- so
    it stays the caller's to classify.
    """

    duration = span_duration_seconds(sample_count)
    segments: list[TranscriptSegment] = []
    for segment in parse_transcript(transcript):
        start = _clamped(segment.start, duration)
        end = max(_clamped(segment.end, duration), start)
        if (start, end) == (segment.start, segment.end):
            segments.append(segment)
        else:
            segments.append(replace(segment, start=start, end=end))
    return tuple(segments)


def render_segments(
    segments: Iterable[TranscriptSegment],
    speaker_of: Callable[[TranscriptSegment], str],
) -> str:
    """Write segments back in the span grammar ``[start][speaker]text[end]``.

    The inverse of ``span_segments``, and it lives beside it for the reason the clamp does:
    the grammar is read in one place, so it is written in one place too. A retrospective
    relabelling re-renders a transcript that ``live_identity`` first rendered -- if the two
    used different renderers, the labels a sweep corrects would travel with words a second
    implementation had quietly reformatted, which is the one thing a label rewrite must never
    do. ``live_session.revise_labels`` proves the agreement per span rather than assuming it:
    a transcript that does not re-render to itself is left exactly as it was committed.
    """

    return "".join(
        f"[{_fmt_time(segment.start)}][{speaker_of(segment)}]{segment.text}[{_fmt_time(segment.end)}]"
        for segment in segments
    )


def _fmt_time(value: float) -> str:
    return f"{value:g}"


def _clamped(value: float, duration: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(max(value, 0.0), duration)


class LiveTranscriptDisposition(str, Enum):
    """What a span's raw decode may publish, and why.

    Five answers, because "the parser returned nothing" is five different facts about the
    meeting and only one of them is silence. The names describe the *decision*; the
    observation that preceded it is `EmptyTranscriptCause`, which stays a separate vocabulary
    so the policy can change without renaming what was seen.
    """

    #: The production grammar already accepted it; nothing was repaired.
    PARSED = "parsed"
    #: The decoder returned no text at all.
    EMPTY_TEXT = "empty_text"
    #: Absent bounds were completed from the span and the result publishes.
    SALVAGED = "salvaged"
    #: The text is not the span grammar at all -- no repair is defined for it.
    REFUSED_GRAMMAR = "refused_grammar"
    #: Two adjacent turns with no boundary the decoder emitted between them.
    REFUSED_INTERIOR_BOUNDARY = "refused_interior_boundary"
    #: The completed transcript does not survive parse -> render -> parse.
    REFUSED_FIXED_POINT = "refused_fixed_point"
    #: Well formed and repairable, but this span is not one salvage is allowed on.
    REFUSED_GATE = "refused_gate"


@dataclass(frozen=True, slots=True)
class LiveTranscriptOutcome:
    """The classifier's whole answer: the decision, its reason, and what may be published."""

    disposition: LiveTranscriptDisposition
    reason: str
    segments: tuple[TranscriptSegment, ...] = ()
    transcript: str = ""

    @property
    def publishes(self) -> bool:
        return bool(self.segments) and self.disposition in (
            LiveTranscriptDisposition.PARSED,
            LiveTranscriptDisposition.SALVAGED,
        )


def classify_live_transcript(
    raw_text: str,
    *,
    sample_count: int,
    freeze_reason: str,
) -> LiveTranscriptOutcome:
    """Decide what a span whose decode did not parse is allowed to publish.

    The whole policy lives here -- parsing, bounded completion, fixed-point validation and
    the gate -- because the alternative is what this module was created to end: three callers
    each holding a piece of one rule. A caller passes the raw answer and the span it came
    from, and reads the outcome; it never re-derives any part of the decision.

    **What is repaired.** 5 of 80 trio spans were correct words the parser threw away for the
    single reason that the decoder stopped without writing its closing timestamp
    (`prototypes/live-file-gap-emptyspan/NOTES.md`; the decodes used 19-24 of 286 permitted
    tokens, so this is not truncation). Absent *outer* bounds are the span's own bounds --
    the audio is the span, so those two numbers are known rather than guessed. An absent
    *interior* boundary is filled only from a timestamp the decoder actually emitted;
    adjacent chunks sharing a speaker with nothing between them are one turn and are merged,
    which invents no boundary at all. Two *different* speaker labels with no timestamp
    between them are refused outright: the only way to publish them is to guess where one
    voice stops, and that guess would hand the identity path an interval holding another
    speaker's audio (ADR-0002; plan D5).

    **What is gated.** Only a hard-cap span may be salvaged. That is not a proxy for "loud
    enough" -- measured over the 184-span corpus, freeze reason and recomputed WebRTC speech
    ratio disagree on 14 spans -- it is the direct statement of the failure shape: a hard-cap
    span exists *because* 2.5 s of speech ran on without an endpoint, so its decode is words
    by construction, while a span frozen on silence is where the decoder was observed to
    answer a silent window with an apology. Gating on the freeze reason refuses all six
    observed hallucinations without a phrase list, and a phrase list on top of it refused
    nothing further (`evidence/live-convergence-0824/M1a-salvage-gate-comparison/`); a table
    of English refusal sentences is a fact about one decoder in one language, so the gate
    ships and the table does not. The residual it accepts, stated rather than hidden:
    boilerplate on a hard-cap span would publish, and 0 of 163 hard-cap spans produced any.

    The gate is checked last so the outcome reports both facts -- whether the text was
    repairable at all, and whether this span was allowed to. Ordering it first would be
    marginally cheaper and would answer only the second.
    """

    text = (raw_text or "").strip()
    if not text:
        return LiveTranscriptOutcome(LiveTranscriptDisposition.EMPTY_TEXT, "decoder returned no text")

    parsed = span_segments(text, sample_count=sample_count)
    if parsed:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.PARSED, "parses under the production grammar", parsed, text
        )

    tokens = _bracket_tokens(text)
    if tokens is None:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.REFUSED_GRAMMAR,
            "bracket token is neither a timestamp nor a speaker",
        )
    chunks = _speaker_chunks(tokens)
    if chunks is None:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.REFUSED_GRAMMAR, "words appear before any speaker marker"
        )
    if not chunks:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.REFUSED_GRAMMAR, "no speaker-attributed words"
        )

    chunks = _merge_adjacent_same_speaker(chunks)
    refusal = _complete_bounds(chunks, span_duration_seconds(sample_count))
    if refusal is not None:
        return LiveTranscriptOutcome(LiveTranscriptDisposition.REFUSED_INTERIOR_BOUNDARY, refusal)

    completed = render_segments(
        [
            TranscriptSegment(
                start=float(chunk.start),
                end=float(chunk.end),
                speaker=chunk.speaker,
                text=chunk.text.strip(),
            )
            for chunk in chunks
        ],
        lambda segment: segment.speaker,
    )
    segments = span_segments(completed, sample_count=sample_count)
    if not segments:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.REFUSED_FIXED_POINT, "completed transcript still parses to nothing"
        )
    rendered = render_segments(segments, lambda segment: segment.speaker)
    reparsed = span_segments(rendered, sample_count=sample_count)
    if not reparsed or render_segments(reparsed, lambda segment: segment.speaker) != rendered:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.REFUSED_FIXED_POINT, "parse -> render -> parse is not a fixed point"
        )

    if freeze_reason != HARD_CAP_REASON:
        return LiveTranscriptOutcome(
            LiveTranscriptDisposition.REFUSED_GATE,
            f"freeze reason {freeze_reason!r} is not {HARD_CAP_REASON}",
        )

    return LiveTranscriptOutcome(
        LiveTranscriptDisposition.SALVAGED, "absent bounds completed from the span", segments, rendered
    )


_BRACKET = re.compile(r"\[([^\]]*)\]")
_TIMESTAMP_TOKEN = re.compile(r"^\d+(?:\.\d+)?$")
_SPEAKER_TOKEN = re.compile(r"^S\d+$")


@dataclass(slots=True)
class _Chunk:
    speaker: str
    text: str
    start: float | None
    end: float | None


def _bracket_tokens(text: str) -> list[tuple[str, str]] | None:
    """Split into ordered ``('ts'|'speaker'|'text', value)`` runs, or ``None``.

    ``None`` means a bracket held something that is neither a timestamp nor a speaker, which
    is a decode in some other grammar -- there is no defined repair for it, and guessing one
    would be inventing content.
    """

    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in _BRACKET.finditer(text):
        if match.start() > cursor:
            parts.append(("text", text[cursor : match.start()]))
        value = match.group(1).strip()
        if _TIMESTAMP_TOKEN.match(value):
            parts.append(("ts", value))
        elif _SPEAKER_TOKEN.match(value):
            parts.append(("speaker", value))
        else:
            return None
        cursor = match.end()
    if cursor < len(text):
        parts.append(("text", text[cursor:]))
    return parts


def _speaker_chunks(tokens: Iterable[tuple[str, str]]) -> list[_Chunk] | None:
    """Group the token run into one chunk per speaker marker, or ``None``.

    A timestamp closes the chunk in front of it when that chunk is still open and has words;
    otherwise it opens the next one. ``None`` means words appeared before any speaker marker:
    the grammar names a speaker for every word, and choosing one for orphaned words is the
    same invention the interior-boundary rule refuses.
    """

    chunks: list[_Chunk] = []
    pending_start: float | None = None
    for kind, value in tokens:
        if kind == "ts":
            if chunks and chunks[-1].text.strip() and chunks[-1].end is None:
                chunks[-1].end = float(value)
            else:
                pending_start = float(value)
        elif kind == "speaker":
            chunks.append(_Chunk(speaker=value, text="", start=pending_start, end=None))
            pending_start = None
        else:
            if not chunks:
                if value.strip():
                    return None
                continue
            chunks[-1].text += value
    return [chunk for chunk in chunks if chunk.text.strip()]


def _merge_adjacent_same_speaker(chunks: list[_Chunk]) -> list[_Chunk]:
    """Join neighbouring chunks that share a speaker and have no timestamp between them.

    Lossless, and the reason the common salvage case needs no invented boundary at all: the
    decoder wrote one turn as two labelled runs, so joining them restores what it meant and
    creates no boundary where it emitted none.
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
    """Fill absent bounds; name the refusal if any boundary would have to be invented."""

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
            return (
                f"no timestamp between speakers {previous.speaker} and {current.speaker} "
                f"at chunk {index}"
            )
    for index, chunk in enumerate(chunks):
        if chunk.start is None or chunk.end is None:
            return f"chunk {index} still has an absent bound after completion"
        if chunk.end < chunk.start:
            return f"chunk {index} ends before it starts ({chunk.start} > {chunk.end})"
        if index and chunk.start < chunks[index - 1].start:
            return f"chunk {index} starts before chunk {index - 1}"
    return None


__all__ = [
    "LIVE_SAMPLE_RATE",
    "LiveTranscriptDisposition",
    "LiveTranscriptOutcome",
    "classify_live_transcript",
    "render_segments",
    "span_duration_seconds",
    "span_segments",
]
