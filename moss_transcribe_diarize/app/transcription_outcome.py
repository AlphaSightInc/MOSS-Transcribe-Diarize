"""Outcomes a transcription runner reports that are not failures of the runner.

This module is deliberately a leaf: the batch runners import heavy inference stacks and the
live adapters must not, so the one vocabulary both sides share lives on its own.
"""

from __future__ import annotations


class EmptyTranscriptionError(RuntimeError):
    """The decoder answered for this audio and produced nothing transcribable.

    It is a `RuntimeError` subclass because every batch caller already treats the condition as
    a hard failure and must keep doing so: a batch job that returns no transcript for a file
    the operator submitted is wrong. The live path needs the opposite answer -- a live span is
    a slice of a meeting chosen by an endpointer, and silence between turns is the ordinary
    case -- so it needs to tell this condition apart from a decoder that actually failed.
    That is the whole reason the type exists; the messages are unchanged.
    """


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
