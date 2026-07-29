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
from dataclasses import replace
from typing import Callable, Iterable

from moss_transcribe_diarize.transcript_parser import TranscriptSegment, parse_transcript

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


__all__ = [
    "LIVE_SAMPLE_RATE",
    "render_segments",
    "span_duration_seconds",
    "span_segments",
]
