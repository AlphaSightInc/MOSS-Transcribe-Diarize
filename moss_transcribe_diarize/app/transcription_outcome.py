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
