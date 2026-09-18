"""Outcomes a transcription runner reports that are not failures of the runner.

This module is deliberately a leaf: the batch runners import heavy inference stacks and the
live adapters must not, so the one vocabulary both sides share lives on its own.
"""

from __future__ import annotations

from enum import Enum


class EmptyTranscriptCause(str, Enum):
    """Which ending produced nothing transcribable.

    "Nothing transcribable" is one answer to the batch caller and several different facts to a
    reader of a live meeting: a decoder that emitted no tokens at all was not asked the same
    question as one that emitted a sentence in the wrong grammar. Collapsing them is what made
    every empty live span report `decoder_returned_no_transcript`, including the spans where
    the model said words that simply did not parse.

    Three of the causes are answers a decoder gave; the fourth is the live path recording that
    it never asked. Both belong in one vocabulary because both are what a reader is shown for
    a span with no words, and a reader who cannot tell a muted lane from a silent model has
    the same problem this enum was created to fix.

    The cause names the *observation* -- what came back, or what was in the audio -- not the
    policy that follows from it.
    Deciding what to publish for an unparseable answer is a separate question with a separate
    home (`live_span_bounds`), and that decision must be free to change without renaming what
    was seen.
    """

    NO_GENERATED_TOKENS = "no_generated_tokens"
    EMPTY_TEXT = "empty_text"
    UNPARSEABLE_TEXT = "unparseable_text"
    #: Nothing was asked. The audio was exact digital zeros, so there was no question to put
    #: to a decoder and no answer of its to report. It is a cause of an empty transcript like
    #: the three above -- a reader of a live meeting needs to tell "the microphone was muted"
    #: apart from "the model said nothing" -- but it is the only one that names the *audio*
    #: rather than the answer, which is exactly why it can be established before dispatch and
    #: why the three above cannot. A decode seam never produces it; only the dispatch guard
    #: (`live_silence.is_digital_silence`) does.
    DIGITAL_SILENCE = "digital_silence"


class EmptyTranscriptionError(RuntimeError):
    """The decoder answered for this audio and produced nothing transcribable.

    It is a `RuntimeError` subclass because every batch caller already treats the condition as
    a hard failure and must keep doing so: a batch job that returns no transcript for a file
    the operator submitted is wrong. The live path needs the opposite answer -- a live span is
    a slice of a meeting chosen by an endpointer, and silence between turns is the ordinary
    case -- so it needs to tell this condition apart from a decoder that actually failed.
    That is the whole reason the type exists; the messages are unchanged.

    It carries the `cause` and the decode's own token count so the live path can report what
    was actually observed. Batch callers see exactly what they saw before -- same type, same
    message -- because the facts travel as attributes, not in the sentence.
    """

    def __init__(
        self,
        message: str,
        *,
        cause: EmptyTranscriptCause,
        text: str = "",
        generated_tokens: int = 0,
    ):
        super().__init__(message)
        self.cause = cause
        # The raw answer is kept on the exception and never rendered into an event: a live
        # trace that quoted the model's words would leak meeting content into telemetry. The
        # salvage policy is the one caller entitled to read it.
        self.text = text
        self.generated_tokens = int(generated_tokens)


class TransientTranscriptionError(RuntimeError):
    """The decoder never answered for this audio, and a later attempt may.

    The distinction is about the *answer*, not about the audio: a dropped connection, a
    request that timed out, a backend that said "not now" all leave the same bytes
    undecoded and would decode normally a moment later. A request the backend refuses on
    its merits -- a rejected payload, a missing route, a refused key -- would be refused
    identically forever and is not this.

    A `RuntimeError` subclass for the same reason as `EmptyTranscriptionError`: batch
    callers that already treat any runner failure as fatal keep doing so unchanged. The
    live path is the one that needs the distinction, because a meeting must survive its
    decoder blinking.
    """
