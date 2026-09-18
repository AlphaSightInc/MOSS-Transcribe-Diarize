"""Is this audio exactly digital silence? One predicate, for every seam that must not decode it.

WP3 measured a deployed decoder inventing ~40 words for a span of exact digital zeros. Zeros
reach the live path legitimately and often: the mixer renders a muted, absent or
declared-`silent` lane to zero, so "there is nothing here" is a fact about the audio that is
knowable without asking a model -- and therefore a fact that must be established *before* a
model is asked, not repaired after it answers.

This module is a **predicate and nothing else**. It says what the audio is; it never says
what to do about it. That is why it holds no enum, no reason string, no telemetry and no side
effect: each seam owes its own answer (the canonical lane commits the span empty, the rolling
witness completes its window with nothing, the terminal pass refuses by name), and those three
answers are different contracts that must stay free to change independently.

Placement rule this module exists to enforce, and the reason WP10 moved the check: the
decision belongs where a decode is *dispatched*, never inside a decode seam.
`RunnerBoundedWavInference.transcribe_pcm` is the seam that turns a runner's answer into an
`InferenceTranscript` -- empty causes, the salvage gate, token-cap accounting, and the line
between a decoder that failed and a span with nothing to say. A seam that answers before
consulting its runner cannot report any of those, so every one of those contracts is a test
that hands the seam PCM and asserts on what the runner said. Zeros are the cheapest PCM to
write in a fixture, so guarding inside the seam silently voided nineteen of them.
"""

from __future__ import annotations

__all__ = ["is_digital_silence"]


def is_digital_silence(pcm: bytes | bytearray | memoryview) -> bool:
    """True when every byte of this PCM16 buffer is an exact zero.

    Exact zeros only, and deliberately not a threshold. WP3's bench falsified energy-based
    suppression at 99% explained playback energy on real quiet local speech
    (`evidence/mvpfix/wp3/`), so one nonzero least-significant bit is quiet speech that must
    still be decoded, not silence. An empty buffer is silence by the same rule: there is no
    sample in it for a model to hear.

    Counted rather than iterated. `any(pcm)` materialises a Python `int` per byte, and the
    largest buffer this predicate is asked about is a whole meeting's tape -- tens of
    megabytes -- on the stop path of a live meeting.
    """

    data = pcm if isinstance(pcm, (bytes, bytearray)) else bytes(pcm)
    return data.count(0) == len(data)
