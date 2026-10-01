"""How an Account transcript segment names its speaker, in one place for every reader.

The browser presentation and transcript export share this dependency-light leaf rule.
`app.live_session` re-exports it, so runtime callers still reach it through the session model.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence

# The speaker label a span carries when the session never established who spoke it. The
# wire grammar admits only `S` followed by digits, and canonical display labels are
# `S{index + 1:02d}`, so this marker is the one such token a canonical mapping can never
# produce. It exists because the alternative to publishing an honest "nobody attributed"
# is publishing the decoder's *local* labels as if they were canonical -- `S01` in one span
# and `S01` in the next are not the same person until identity says so.
UNATTRIBUTED_SPEAKER = "S00"
_DEFAULT_NAMED_ID = re.compile(r"(local-|speaker-|S)(\d+)")


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


def default_speaker_name(speaker: str | None) -> str:
    """The name a speaker is shown under until a person or a voiceprint names them.

    It is read off the speaker's identity alone, so it is the same in every version of a
    meeting's transcript -- live, cleaned up after Stop, saved and reopened -- and naming one
    speaker never renames another. Microphone voices (`local-N`) read `You` for the first
    and `User n` after it (`local-2` is `User 1`); a shared-audio voice (`speaker-N`, or a
    File decoder's `SN`) reads `Speaker N`. Ids are handed out in the order voices are first
    heard, and clean-up keeps the ids of the voices it recognises, so a voice that
    disappears leaves a gap and a new one takes the next unused number. The browser applies
    the same rule. Nobody attributed, or an id of neither shape, reads as the honest
    `UNATTRIBUTED_SPEAKER`.
    """

    match = _DEFAULT_NAMED_ID.fullmatch(speaker or "")
    number = int(match.group(2)) if match else 0
    if number == 0:
        return UNATTRIBUTED_SPEAKER
    if match.group(1) == "local-":
        return "You" if number == 1 else f"User {number - 1}"
    return f"Speaker {number}"


def transcript_speaker_names(
    speakers: Sequence[str | None], names: Mapping[str, str]
) -> list[str]:
    """One label per transcript row.

    `speakers` is each row's speaker, `None` where nobody is attributed or the identity was
    never established; `names` are the names a person or a voiceprint gave. A named speaker
    reads its name; every other speaker reads its `default_speaker_name`.
    """

    return [names[speaker] if speaker in names else default_speaker_name(speaker)
            for speaker in speakers]


def name_saved_speakers(segments: Sequence[dict], names: Mapping[str, str]) -> None:
    """Rename a saved transcript's rows in place by `transcript_speaker_names`.

    A row's speaker is its `speaker_entity_id`; a row without one, or one saved as
    `UNATTRIBUTED_SPEAKER` and not named, keeps what it says.
    """

    speakers = [
        segment.get("speaker_entity_id")
        if segment.get("speaker_entity_id") in names
        or segment.get("speaker") != UNATTRIBUTED_SPEAKER else None
        for segment in segments
    ]
    for segment, speaker, name in zip(segments, speakers, transcript_speaker_names(speakers, names)):
        if speaker is not None:
            segment["speaker"] = name


__all__ = ["UNATTRIBUTED_SPEAKER", "default_speaker_name", "display_speaker_label",
           "name_saved_speakers", "published_speaker_label", "transcript_speaker_names"]
