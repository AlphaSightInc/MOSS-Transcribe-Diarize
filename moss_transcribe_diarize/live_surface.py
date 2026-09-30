"""How an Account transcript segment names its speaker, in one place for every reader.

The browser presentation and transcript export share this dependency-light leaf rule.
`app.live_session` re-exports it, so runtime callers still reach it through the session model.
"""

from __future__ import annotations

from typing import Sequence

# The speaker label a span carries when the session never established who spoke it. The
# wire grammar admits only `S` followed by digits, and canonical display labels are
# `S{index + 1:02d}`, so this marker is the one such token a canonical mapping can never
# produce. It exists because the alternative to publishing an honest "nobody attributed"
# is publishing the decoder's *local* labels as if they were canonical -- `S01` in one span
# and `S01` in the next are not the same person until identity says so.
UNATTRIBUTED_SPEAKER = "S00"


def display_speaker_label(canonical_speaker: str, canonical_speakers: Sequence[str]) -> str:
    """The `Sxx` token a canonical speaker is published as.

    One rule, in one place, because several readers now depend on it: the identity preparer
    writes the label when a span is first published, and `revise_labels` rewrites it when a
    retrospective sweep moves that speech onto a different speaker. The mapping is positional
    and the canonical list only ever grows by appending, which is what makes a label written
    in minute one still name the same speaker in minute seventeen.

    Raises `ValueError` for a speaker the session has never established; the caller decides
    what that means, and both callers refuse rather than invent a label.
    """

    return f"S{tuple(canonical_speakers).index(canonical_speaker) + 1:02d}"


def published_speaker_label(
    canonical_speaker: str | None, canonical_speakers: Sequence[str]
) -> str:
    """The `Sxx` a *surface* segment is scored and exported as. Total, never raises.

    `display_speaker_label` is the strict primitive: it answers only for a speaker this
    session established, and refuses otherwise so a writer cannot invent a name. A reader of
    the surface has two more cases to survive, and both mean the same thing -- nobody was
    attributed (`canonical_speaker is None`), and an identity this snapshot never established,
    which is what an older snapshot's words look like after an epoch or from a truncated
    payload. Neither may be rendered as a guess, so both read as the honest
    `UNATTRIBUTED_SPEAKER`.

    It is total because two readers depend on it -- the scored hypothesis and the evaluator
    export -- and both must read the same token the committed spans carry. The name a person
    is shown is `default_speaker_name`.
    """

    if canonical_speaker is None:
        return UNATTRIBUTED_SPEAKER
    try:
        return display_speaker_label(canonical_speaker, canonical_speakers)
    except ValueError:
        return UNATTRIBUTED_SPEAKER


def default_speaker_name(canonical_speaker: str | None, first_spoken: Sequence[str]) -> str:
    """The name a speaker is shown under until a person or a voiceprint names them.

    Microphone voices (`local-N`) read `You` for the first and `User n` after it (`local-2`
    is `User 1`); every other speaker reads `Speaker n`, numbered by its place among the
    non-local speakers of `first_spoken` -- the unnamed speakers in the order they first
    speak. The browser applies the same rule to the live view, so the screen and the saved
    transcript agree. Nobody attributed, or an identity not in `first_spoken`, reads as the
    honest `UNATTRIBUTED_SPEAKER`.
    """

    if canonical_speaker is None or canonical_speaker not in first_spoken:
        return UNATTRIBUTED_SPEAKER
    if _is_local(canonical_speaker):
        number = int(canonical_speaker[6:])
        return "You" if number == 1 else f"User {number - 1}"
    shared = [speaker for speaker in first_spoken if not _is_local(speaker)]
    return f"Speaker {shared.index(canonical_speaker) + 1}"


def _is_local(canonical_speaker: str) -> bool:
    return canonical_speaker.startswith("local-") and canonical_speaker[6:].isdigit()


__all__ = ["UNATTRIBUTED_SPEAKER", "default_speaker_name", "display_speaker_label",
           "published_speaker_label"]
