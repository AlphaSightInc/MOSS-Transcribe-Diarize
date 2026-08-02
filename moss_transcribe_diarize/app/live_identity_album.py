"""ADR-0002's quality-gated fingerprint album: the live path's reference-vector policy.

The replaced live policy stored the **latest** span's embedding per canonical speaker, so one noisy
0.5 s fragment overwrites a good voice reference. ADR-0002 measured that policy at
**66.4 % mean** live speaker accuracy against **98.5 %** for a quality-gated album, over
eight LibriSpeech meetings driven through production live semantics (2.5 s span cap,
0.6 s silence split, one-to-one score/margin matching, abstain, birth, 16-speaker cap).

The album is the asymmetry the old policy lacked: **matching is not enrollment.** A short
span may still be *labelled* against a reference -- the evidence floor
(`identity_provider.min_segment_samples`) deliberately does not move, or short spans would
stop being labelled at all -- but it may never *become* one. Enrollment needs ADR-0002's
admission duration; anything shorter can only stand in provisionally for a speaker that has
no admitted exemplar yet.

Two tiers, because ADR-0002 requires that birth semantics stay unchanged:

* **Exemplars** -- up to `exemplars_per_speaker`, each from a span carrying at least
  `admission_seconds` of that speaker's speech. Matching uses their duration-weighted
  centroid. This is the album proper.
* **Provisional** -- exactly one sub-admission observation, kept only while a speaker has no
  exemplars. Without it a speaker born from a 0.6 s span would have no reference at all,
  would never be matchable, and every recurrence of that voice would birth another canonical
  id -- strictly worse capacity exhaustion than the overwrite policy it replaces. It is
  discarded, never averaged, the moment a real exemplar is admitted.

Neither tier is recency-driven, so "a noisy short utterance destroys a good reference" is
dead in both: the bank keeps its longest observations, the stand-in keeps the first-best.

Every refusal is named. On the live path nothing here raises: an unusable observation is
declined by name and the meeting continues, per the live path's terminal-failure policy.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence


# Phase N's real-encoder duration curve separates matching from enrollment: the deployed
# 8,000-sample (0.5 s) evidence floor remains matchable, but only 32,000 samples (2.0 s)
# may enter the canonical album. Birth has its own, lower floor because the real 9-clip
# corpus shows that coupling birth to 2.0 s collapses one cold-start clip to 49.4 %.
ALBUM_ADMISSION_SECONDS = 2.0
ALBUM_BIRTH_MIN_SECONDS = 1.0
ALBUM_EXEMPLARS_PER_SPEAKER = 10

# The matcher thresholds ADR-0002 §7 measured *against album centroid statistics*. Nothing in
# this module reads them: they belong to `identity_config` in the deployed manifest, which a
# deployment states explicitly. They are named here because they are calibrated to this
# policy and are wrong for the one it replaces -- at the pre-album 0.5 / 0.2 the album
# measures 75.0 % mean live speaker accuracy, below ADR-0002's >= 90 % bar, against 93.4 %
# at these values (`tests/live_identity_accuracy.py`). Recording them beside the policy they
# calibrate is what keeps the measured pair and the deployed pair the same pair.
ALBUM_MIN_MATCH_SCORE = 0.35
ALBUM_MIN_MATCH_MARGIN = 0.1

# Dispositions. `observe` returns one of these rather than a bool, because a verdict word has
# to name the thing it decides -- "rejected" alone cannot tell a fragment that was too short
# from one that lost to a better exemplar.
ADMITTED = "admitted"
PROVISIONAL = "provisional"
REJECTED_BELOW_ADMISSION = "rejected_below_admission"
REJECTED_WEAKER_THAN_BANK = "rejected_weaker_than_bank"
REJECTED_WEAKER_THAN_PROVISIONAL = "rejected_weaker_than_provisional"
REJECTED_INVALID_VECTOR = "rejected_invalid_vector"
REJECTED_INVALID_DURATION = "rejected_invalid_duration"


@dataclass(frozen=True, slots=True)
class AlbumExemplar:
    """One retained voiceprint and the evidence that earned it its place."""

    vector: tuple[float, ...]
    duration_sec: float
    span_id: int


class FingerprintAlbum:
    """Per canonical speaker: top-k exemplars, matched against a duration-weighted centroid.

    Bounded by construction -- `max_speakers` (16 deployed) times `exemplars_per_speaker`
    vectors -- so a three-hour meeting costs the same memory as a one-minute one.
    """

    def __init__(
        self,
        *,
        admission_seconds: float = ALBUM_ADMISSION_SECONDS,
        exemplars_per_speaker: int = ALBUM_EXEMPLARS_PER_SPEAKER,
    ):
        if not math.isfinite(admission_seconds) or admission_seconds <= 0.0:
            raise ValueError("album admission_seconds must be positive and finite.")
        if exemplars_per_speaker <= 0:
            raise ValueError("album exemplars_per_speaker must be positive.")
        self.admission_seconds = float(admission_seconds)
        self.exemplars_per_speaker = int(exemplars_per_speaker)
        self._exemplars: dict[str, list[AlbumExemplar]] = {}
        self._provisional: dict[str, AlbumExemplar] = {}

    def observe(
        self,
        *,
        canonical_speaker: str,
        vector: Sequence[float],
        duration_sec: float,
        span_id: int,
    ) -> str:
        """Offer one span's evidence for a canonical speaker; return the disposition.

        The caller offers only assignments from a **prepared** preparation, which is where
        the other half of ADR-0002's admission rule -- "sufficient match margin" -- is already
        enforced: `BoundedCausalIdentityPreparer` abstains for the whole span when a match
        fails `min_match_score` or `min_match_margin`, so an assignment that reaches here
        carries the margin by construction. Duration is the only gate left to apply.
        """

        values = _finite_vector(vector)
        if values is None:
            return REJECTED_INVALID_VECTOR
        if not math.isfinite(duration_sec) or duration_sec <= 0.0:
            return REJECTED_INVALID_DURATION
        candidate = AlbumExemplar(
            vector=values,
            duration_sec=float(duration_sec),
            span_id=int(span_id),
        )
        if candidate.duration_sec >= self.admission_seconds:
            return self._admit(canonical_speaker, candidate)
        return self._hold_provisional(canonical_speaker, candidate)

    def reference(self, canonical_speaker: str) -> tuple[float, ...] | None:
        """The vector a live span is matched against, or `None` if this speaker has none yet."""

        bank = self._exemplars.get(canonical_speaker)
        if bank:
            centroid = duration_weighted_centroid(bank)
            if centroid is not None:
                return centroid
        held = self._provisional.get(canonical_speaker)
        return held.vector if held is not None else None

    def exemplars(self, canonical_speaker: str) -> tuple[AlbumExemplar, ...]:
        """This speaker's admitted bank, read-only.

        `reference()` answers "what do I match against"; a retrospective sweep needs the
        evidence *behind* that answer, because a centroid over the union of two speakers'
        banks is not the average of their two centroids -- the exemplars carry the durations
        that weight it. The provisional stand-in is deliberately not exposed: it is one
        sub-admission fragment, and every consumer of this accessor is making a claim
        stronger than matching.
        """

        return tuple(self._exemplars.get(canonical_speaker, ()))

    def reference_support(self, canonical_speaker: str) -> tuple[AlbumExemplar, ...]:
        """Observations behind `reference()`, including a provisional stand-in.

        A retrospective scorer needs provenance as well as the reduced vector: otherwise an
        early birth is compared to the exact observation that created it and wins with a
        meaningless cosine of 1.0 forever. Merge policy must keep using `exemplars()` because
        provisional evidence is still too weak to collapse two canonical speakers.
        """

        bank = self._exemplars.get(canonical_speaker)
        if bank:
            return tuple(bank)
        held = self._provisional.get(canonical_speaker)
        return () if held is None else (held,)

    def exemplar_count(self, canonical_speaker: str) -> int:
        return len(self._exemplars.get(canonical_speaker, ()))

    def has_provisional(self, canonical_speaker: str) -> bool:
        return canonical_speaker in self._provisional

    def speakers(self) -> tuple[str, ...]:
        return tuple(sorted(set(self._exemplars) | set(self._provisional)))

    def _admit(self, canonical_speaker: str, candidate: AlbumExemplar) -> str:
        bank = self._exemplars.setdefault(canonical_speaker, [])
        # A real exemplar retires the stand-in outright. Averaging the two would let the very
        # fragment the admission gate refused back into the centroid through the side door.
        self._provisional.pop(canonical_speaker, None)
        if len(bank) < self.exemplars_per_speaker:
            bank.append(candidate)
            return ADMITTED
        # Evict the shortest; among equally short ones the oldest, so a bank that filled in the
        # first minute still tracks the meeting rather than freezing on its opening exemplars.
        weakest = min(range(len(bank)), key=lambda index: (bank[index].duration_sec, bank[index].span_id))
        if candidate.duration_sec < bank[weakest].duration_sec:
            return REJECTED_WEAKER_THAN_BANK
        bank[weakest] = candidate
        return ADMITTED

    def _hold_provisional(self, canonical_speaker: str, candidate: AlbumExemplar) -> str:
        if self._exemplars.get(canonical_speaker):
            # The asymmetry, in one line: this span may be labelled, and it just was, but it
            # cannot touch a reference that real evidence has already earned.
            return REJECTED_BELOW_ADMISSION
        held = self._provisional.get(canonical_speaker)
        # Ties keep the incumbent here, the opposite of the bank's rule and for the opposite
        # reason: an exemplar is a *sample* of a voice and benefits from recency, a stand-in is
        # a placeholder and benefits from not churning.
        if held is not None and candidate.duration_sec <= held.duration_sec:
            return REJECTED_WEAKER_THAN_PROVISIONAL
        self._provisional[canonical_speaker] = candidate
        return PROVISIONAL


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float | None:
    """The identity layer's one similarity rule, clamped to `[0, 1]`.

    Clamping is not cosmetic: `BoundedCausalIdentityPreparer` refuses evidence outside `[0, 1]`
    outright, and two voiceprints that point away from each other are *no* evidence of a link,
    not negative evidence of one -- the matcher's floor already says "unmatched".

    Returns `None` -- never raises -- when the similarity is undefined: mismatched dimensions,
    or a vector with no length. Callers on the live path turn that into a named refusal; the
    live evidence provider, whose contract is older, wraps it back into its typed admission
    error so nothing about the deployed matcher changes.
    """

    if len(left) != len(right):
        return None
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    if not math.isfinite(left_norm) or not math.isfinite(right_norm):
        return None
    if left_norm <= 0.0 or right_norm <= 0.0:
        return None
    score = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    if not math.isfinite(score):
        return None
    return max(0.0, min(1.0, score))


def _finite_vector(vector: Sequence[float]) -> tuple[float, ...] | None:
    try:
        values = tuple(float(item) for item in vector)
    except (TypeError, ValueError):
        return None
    if not values or any(not math.isfinite(item) for item in values):
        return None
    return values


def duration_weighted_centroid(bank: Sequence[AlbumExemplar]) -> tuple[float, ...] | None:
    """Strategy C: weight each exemplar by the seconds of speech that produced it.

    Returns `None` -- never raises -- for an empty bank, one whose exemplars disagree on
    dimension, or one whose weighted sum is degenerate, so a corrupt album costs a speaker its
    reference for one span instead of costing the meeting its session.
    """

    if not bank:
        return None
    dimension = len(bank[0].vector)
    if any(len(item.vector) != dimension for item in bank):
        return None
    totals = [0.0] * dimension
    for item in bank:
        weight = item.duration_sec
        for index, value in enumerate(item.vector):
            totals[index] += weight * value
    if not math.isfinite(sum(totals)) or all(value == 0.0 for value in totals):
        return None
    norm = math.sqrt(sum(value * value for value in totals))
    if not math.isfinite(norm) or norm <= 0.0:
        return None
    return tuple(value / norm for value in totals)


__all__ = [
    "ADMITTED",
    "ALBUM_ADMISSION_SECONDS",
    "ALBUM_BIRTH_MIN_SECONDS",
    "ALBUM_EXEMPLARS_PER_SPEAKER",
    "ALBUM_MIN_MATCH_MARGIN",
    "ALBUM_MIN_MATCH_SCORE",
    "AlbumExemplar",
    "FingerprintAlbum",
    "PROVISIONAL",
    "cosine_similarity",
    "duration_weighted_centroid",
    "REJECTED_BELOW_ADMISSION",
    "REJECTED_INVALID_DURATION",
    "REJECTED_INVALID_VECTOR",
    "REJECTED_WEAKER_THAN_BANK",
    "REJECTED_WEAKER_THAN_PROVISIONAL",
]
