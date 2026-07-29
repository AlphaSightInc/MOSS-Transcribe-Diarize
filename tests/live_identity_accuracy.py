"""Replay a labelled meeting through the **production** live identity path and score it.

ADR-0002's acceptance bar for live speaker identity is a number -- ">= 90-95 % live speaker
accuracy, materially above the latest-span overwrite policy it replaces" -- and nothing in
this repository could measure one. The ADR's own 98.5 %-vs-66.4 % came from a throwaway
prototype that *re-implemented* the matcher; a green unit suite for
`live_identity_album` therefore says nothing about whether the shipped
`BoundedCausalIdentityPreparer` + `WeSpeakerLiveEvidenceProvider` + `FingerprintAlbum`
composition actually labels a meeting correctly.

This harness closes that gap. It drives the real production objects, span by span, exactly
as the live coordinator does -- one `prepare()` per span, the prepared snapshot carried
forward, the album reconciled from the *previous* span's diagnostics on the next `score()`
call -- and scores the result against ground truth.

**What is real and what is substituted.** Everything on the identity path is production
code. Only the encoder is substituted, by `CachedEncoder`, which returns the vector the
*real* pinned WeSpeaker ONNX encoder produced for that same evidence unit. So the geometry
under test is the real encoder's; what is skipped is one ONNX forward pass per unit, which
would need a GPU-class asset the test suite must not depend on. `assert_fixture_matches_production`
proves the substitution is exact: production's own interval filter has to select the same
speech, unit for unit and second for second, as the run that produced the vectors, or the
fixture is refused.

**Fidelity notes, recorded rather than hidden.**

* The corpus was embedded under a plan cut at a 0.6 s silence split, where the deployed
  endpointer splits at `min_silence_samples` 8000 (0.5 s). The plan below uses the deployed
  value, and that is not a liberty: the corpus holds **0 of 1530** inter-utterance gaps in
  `[0.5, 0.6)`, so the two constants produce the identical span plan here.
  `test_the_corpus_cannot_tell_the_two_silence_splits_apart` keeps that true.
* The corpus is LibriSpeech read speech: no overlapped speech, no noise, no reverb, and
  in-span local diarization is assumed correct. ADR-0002 §7 carries the same caveat. These
  numbers bound the identity layer in isolation; a real conversational recording is still
  required before production sign-off.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from moss_transcribe_diarize.app.live_identity import (
    BoundedCausalIdentityPreparer,
    LiveIdentityConfig,
)
from moss_transcribe_diarize.app.live_identity_album import (
    ALBUM_ADMISSION_SECONDS,
    ALBUM_EXEMPLARS_PER_SPEAKER,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
    FingerprintAlbum,
)
from moss_transcribe_diarize.app.live_provider_bundle import WeSpeakerLiveEvidenceProvider
from moss_transcribe_diarize.app.live_session import FrozenSpan, LiveIdentitySnapshot

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "live_identity_accuracy"
MEETINGS = (
    "meet_k2_s0",
    "meet_k2_s1",
    "meet_k3_s0",
    "meet_k3_s1",
    "meet_k4_s0",
    "meet_k4_s1",
    "meet_k6_s0",
    "meet_k6_s1",
)

LIVE_SAMPLE_RATE = 16000
# The deployed live endpointer's span cap, `hard_cap_samples` 40000 -- a domain-contract
# value, restated here as seconds because the fixture's plan is expressed in seconds.
SPAN_CAP_SECONDS = 40000 / LIVE_SAMPLE_RATE
# The deployed endpointer's silence split, `min_silence_samples` 8000 -- also a
# domain-contract value. See the fidelity note above for why the corpus cannot tell it apart
# from the 0.6 s the vectors were embedded under.
SILENCE_SPLIT_SECONDS = 8000 / LIVE_SAMPLE_RATE
# The split the corpus was embedded under; kept only so the node that proves the two are
# indistinguishable on this corpus has something to compare against.
FIXTURE_EMBEDDING_SILENCE_SPLIT_SECONDS = 0.6
# The deployed evidence floor, `identity_provider.min_segment_samples` 8000.
MIN_SEGMENT_SAMPLES = 8000
# The deployed identity bound, `max_identity_speakers`.
MAX_SPEAKERS = 16

# ADR-0002 §7's measured starting thresholds for the matcher, taken from the module that
# names them rather than copied: what this harness measures has to be what a deployment can
# state, or the bar below is proved about a number nothing ships.
ADR_MIN_MATCH_SCORE = ALBUM_MIN_MATCH_SCORE
ADR_MIN_MATCH_MARGIN = ALBUM_MIN_MATCH_MARGIN
# What the live runtime ships today. The album was landed without recalibrating these; the
# ADR says they need it, and `test_live_identity_accuracy` measures how much.
DEPLOYED_MIN_MATCH_SCORE = 0.5
DEPLOYED_MIN_MATCH_MARGIN = 0.2

# Column order of the fixture's `rows` array: one row per evidence unit -- one canonical
# speaker's speech inside one span, which is the granularity production embeds at.
_SPAN, _TRUE_SPEAKER, _START, _END, _DURATION, _ELIGIBLE = range(6)


@dataclass(frozen=True, slots=True)
class Piece:
    """One contiguous stretch of one true speaker's speech inside one planned span."""

    span: int
    start: float
    end: float
    true_speaker: int

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Meeting:
    name: str
    speaker_count: int
    truth: np.ndarray
    rows: np.ndarray
    vectors: np.ndarray

    @property
    def vector_index(self) -> np.ndarray:
        """Row -> row in `vectors`, or -1. Rebuilt from row order, never stored."""

        eligible = self.rows[:, _ELIGIBLE] > 0
        return np.where(eligible, np.cumsum(eligible) - 1, -1).astype(np.int64)


@dataclass(frozen=True, slots=True)
class ReplayResult:
    accuracy: float
    canonical_speaker_count: int
    prepared_spans: int
    abstained_spans: int
    failed_spans: int
    labelled_units: int
    eligible_units: int


@functools.lru_cache(maxsize=None)
def load_meeting(name: str) -> Meeting:
    with np.load(FIXTURES / f"{name}.npz") as payload:
        return Meeting(
            name=name,
            speaker_count=int(payload["k"]),
            truth=payload["truth"].astype(np.float64),
            rows=payload["rows"].astype(np.float64),
            vectors=payload["vecs"].astype(np.float32),
        )


def plan_spans(truth: np.ndarray, *, silence_split: float = SILENCE_SPLIT_SECONDS) -> list[Piece]:
    """The live endpointer's span plan: break on silence, cut at the hard cap.

    A mid-utterance cut is deliberate -- a hard-cap span exists precisely because no
    endpoint was found -- and it is what makes short, low-quality evidence units appear at
    all, which is the condition the album exists to survive.
    """

    pieces: list[Piece] = []
    span = 0
    accumulated = 0.0
    previous_end: float | None = None
    for start, end, speaker in truth:
        if previous_end is not None and start - previous_end >= silence_split:
            span += 1
            accumulated = 0.0
        cursor = float(start)
        while cursor < end:
            cut = min(float(end), cursor + (SPAN_CAP_SECONDS - accumulated))
            pieces.append(Piece(span=span, start=cursor, end=cut, true_speaker=int(speaker)))
            accumulated += cut - cursor
            cursor = cut
            if accumulated >= SPAN_CAP_SECONDS - 1e-9:
                span += 1
                accumulated = 0.0
        previous_end = float(end)
    return pieces


def evidence_units(
    meeting: Meeting,
    *,
    silence_split: float = SILENCE_SPLIT_SECONDS,
) -> list[list[Piece]]:
    """Group the plan into evidence units, in the fixture's row order.

    Production averages one speaker's intervals inside one span into a single vector, so
    `(span, speaker)` is the unit -- and sorting by that pair is what puts the units in the
    same order as the stored vectors.
    """

    grouped: dict[tuple[int, int], list[Piece]] = {}
    for piece in plan_spans(meeting.truth, silence_split=silence_split):
        grouped.setdefault((piece.span, piece.true_speaker), []).append(piece)
    return [grouped[key] for key in sorted(grouped)]


class CachedEncoder:
    """The real encoder's answers, replayed. Raises for an interval it has no answer for.

    Refusing is the point: a silent fallback would let a fixture that no longer matches
    production's interval filter score *something*, and the number would be meaningless.
    """

    def __init__(self) -> None:
        self.unit_of_start: dict[float, int] = {}
        self.vector_of_unit: dict[int, list[float]] = {}
        self.intervals_seen: dict[int, list[tuple[float, float]]] = {}

    def embed(self, wav_path, intervals):
        del wav_path
        unit = self.unit_of_start[round(float(intervals[0][0]), 6)]
        self.intervals_seen[unit] = [(float(start), float(end)) for start, end in intervals]
        return self.vector_of_unit[unit]


def replay(
    meeting: Meeting,
    *,
    policy: str,
    min_match_score: float = ADR_MIN_MATCH_SCORE,
    min_match_margin: float = ADR_MIN_MATCH_MARGIN,
    admission_seconds: float = ALBUM_ADMISSION_SECONDS,
    exemplars_per_speaker: int = ALBUM_EXEMPLARS_PER_SPEAKER,
    max_speakers: int = MAX_SPEAKERS,
    encoder: CachedEncoder | None = None,
) -> ReplayResult:
    """Drive the production identity path over one meeting.

    `policy="album"` is what ADR-0002 step 1 landed. `policy="overwrite"` is the same
    production code with `album=None`, which falls back to `_canonical_vectors` -- the
    latest-span replacement the album replaced. The old policy is still reachable, so the
    comparison needs no revert and no fork of the implementation.
    """

    if policy not in ("album", "overwrite"):
        raise ValueError(f"unknown reference policy: {policy}")

    units = evidence_units(meeting)
    vector_index = meeting.vector_index
    encoder = encoder or CachedEncoder()
    provider = WeSpeakerLiveEvidenceProvider(
        encoder=encoder,
        min_segment_samples=MIN_SEGMENT_SAMPLES,
        album=(
            FingerprintAlbum(
                admission_seconds=admission_seconds,
                exemplars_per_speaker=exemplars_per_speaker,
            )
            if policy == "album"
            else None
        ),
    )
    preparer = BoundedCausalIdentityPreparer(
        config=LiveIdentityConfig(
            max_speakers=max_speakers,
            min_match_score=min_match_score,
            min_match_margin=min_match_margin,
        ),
        evidence_provider=provider,
    )

    spans: dict[int, list[int]] = {}
    for index, pieces in enumerate(units):
        spans.setdefault(pieces[0].span, []).append(index)

    snapshot = LiveIdentitySnapshot(version=0, canonical_speakers=())
    labels = np.full(len(units), -1, np.int64)
    canonical_index: dict[str, int] = {}
    counts = {"prepared": 0, "abstain": 0, "failed": 0}

    for span_id in sorted(spans):
        members = sorted(spans[span_id], key=lambda index: units[index][0].start)
        span_start = min(piece.start for index in members for piece in units[index])
        span_end = max(piece.end for index in members for piece in units[index])
        sample_count = int(round((span_end - span_start) * LIVE_SAMPLE_RATE))
        if sample_count <= 0:
            continue

        label_of = {index: f"S{position + 1:02d}" for position, index in enumerate(members)}
        encoder.unit_of_start = {}
        encoder.vector_of_unit = {}
        segments: list[tuple[float, float, str]] = []
        for index in members:
            for piece in units[index]:
                segments.append((piece.start - span_start, piece.end - span_start, label_of[index]))
                encoder.unit_of_start[round(piece.start - span_start, 6)] = index
            if vector_index[index] >= 0:
                encoder.vector_of_unit[index] = [float(value) for value in meeting.vectors[vector_index[index]]]
        segments.sort()

        start_sample = int(round(span_start * LIVE_SAMPLE_RATE))
        preparation = preparer.prepare(
            span=FrozenSpan(
                id=span_id,
                epoch=0,
                start_sample=start_sample,
                end_sample=start_sample + sample_count,
                reason="end_silence",
            ),
            pcm=b"\0\0" * sample_count,
            transcript="".join(f"[{start:.6f}][{label}]w[{end:.6f}]" for start, end, label in segments),
            base_snapshot=snapshot,
        )
        counts[preparation.status] = counts.get(preparation.status, 0) + 1
        if preparation.status != "prepared":
            continue
        diagnostics = dict(preparation.proposed_snapshot.diagnostics)
        label_to_unit = {label: index for index, label in label_of.items()}
        for assignment in diagnostics.get("assignments", "").split(","):
            if "->" not in assignment:
                continue
            local, canonical = assignment.split("->", 1)
            labels[label_to_unit[local]] = canonical_index.setdefault(canonical, len(canonical_index))
        snapshot = preparation.proposed_snapshot

    eligible = meeting.rows[:, _ELIGIBLE] > 0
    return ReplayResult(
        accuracy=speaker_accuracy(meeting, labels),
        canonical_speaker_count=len(canonical_index),
        prepared_spans=counts["prepared"],
        abstained_spans=counts["abstain"],
        failed_spans=counts["failed"],
        labelled_units=int(np.count_nonzero(labels[eligible] >= 0)),
        eligible_units=int(np.count_nonzero(eligible)),
    )


def speaker_accuracy(meeting: Meeting, labels: np.ndarray) -> float:
    """Duration-weighted causal live speaker accuracy under the optimal canonical->true map.

    Weighted by seconds rather than by unit so a 0.6 s backchannel cannot outvote an 8 s
    turn, and the denominator is **all** eligible speech: a unit an abstained span left
    unlabelled counts against the score. That is what "live accuracy" has to mean -- the
    meeting's reader sees an unlabelled span as a span whose speaker it does not know.
    """

    eligible = meeting.rows[:, _ELIGIBLE] > 0
    truth = meeting.rows[eligible, _TRUE_SPEAKER].astype(int)
    assigned = labels[eligible]
    durations = meeting.rows[eligible, _DURATION]
    canonicals = sorted({int(value) for value in assigned if value >= 0})
    if not canonicals:
        return 0.0
    speakers = sorted({int(value) for value in truth})
    overlap = np.zeros((len(canonicals), len(speakers)))
    for canonical, speaker, duration in zip(assigned, truth, durations, strict=True):
        if canonical >= 0:
            overlap[canonicals.index(int(canonical)), speakers.index(int(speaker))] += duration
    rows, columns = linear_sum_assignment(-overlap)
    return float(overlap[rows, columns].sum() / durations.sum())


def assert_fixture_matches_production(meeting: Meeting) -> None:
    """Refuse a fixture whose span plan or evidence selection production would not reproduce.

    Three separate claims, because a single "it ran" would hide any of them:
    the replanned units are the stored rows; production's interval filter selects exactly
    the speech the stored vectors were embedded from; and every eligible unit has a vector.
    """

    units = evidence_units(meeting)
    if len(units) != len(meeting.rows):
        raise AssertionError(f"{meeting.name}: replanned {len(units)} units, fixture holds {len(meeting.rows)}")
    for index, (pieces, row) in enumerate(zip(units, meeting.rows, strict=True)):
        stored = (int(row[_SPAN]), int(row[_TRUE_SPEAKER]))
        if (pieces[0].span, pieces[0].true_speaker) != stored:
            raise AssertionError(f"{meeting.name} unit {index}: replanned {pieces[0]}, fixture says {stored}")

    encoder = CachedEncoder()
    replay(meeting, policy="album", encoder=encoder)
    eligible = meeting.rows[:, _ELIGIBLE] > 0
    for index in range(len(units)):
        seen = encoder.intervals_seen.get(index)
        if not eligible[index]:
            continue
        if seen is None:
            raise AssertionError(f"{meeting.name} unit {index}: eligible in the fixture, never embedded")
        selected = sum(end - start for start, end in seen)
        # One sample period of slack, and no more. A span holds an integer number of
        # samples, so production clamps a piece that ends exactly at the span's end onto
        # that grid -- measured worst case across the corpus is 0.504 samples. Anything
        # larger is a real disagreement: the smallest interval either side can gain or lose
        # is the 0.5 s evidence floor, four orders of magnitude above this tolerance.
        if abs(selected - meeting.rows[index, _DURATION]) > 1.0 / LIVE_SAMPLE_RATE:
            raise AssertionError(
                f"{meeting.name} unit {index}: production selected {selected:.6f} s, "
                f"the fixture was embedded from {meeting.rows[index, _DURATION]:.6f} s"
            )


def mean_accuracy(results: dict[str, ReplayResult]) -> float:
    return float(np.mean([result.accuracy for result in results.values()]))


def min_accuracy(results: dict[str, ReplayResult]) -> float:
    return float(np.min([result.accuracy for result in results.values()]))


@functools.lru_cache(maxsize=None)
def replay_all(
    *,
    policy: str,
    min_match_score: float = ADR_MIN_MATCH_SCORE,
    min_match_margin: float = ADR_MIN_MATCH_MARGIN,
    admission_seconds: float = ALBUM_ADMISSION_SECONDS,
    exemplars_per_speaker: int = ALBUM_EXEMPLARS_PER_SPEAKER,
    max_speakers: int = MAX_SPEAKERS,
) -> dict[str, ReplayResult]:
    """Every meeting under one configuration. Cached: the suite pays each config once."""

    return {
        name: replay(
            load_meeting(name),
            policy=policy,
            min_match_score=min_match_score,
            min_match_margin=min_match_margin,
            admission_seconds=admission_seconds,
            exemplars_per_speaker=exemplars_per_speaker,
            max_speakers=max_speakers,
        )
        for name in MEETINGS
    }
