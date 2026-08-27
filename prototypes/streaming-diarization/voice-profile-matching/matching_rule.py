"""PROTOTYPE ONLY — pure durable-profile acceptance rule.

The measurement shell owns audio, embeddings, and reporting.  This module owns only the
question being tested: given named-profile similarity scores, accept one name or abstain.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True, slots=True)
class MatchDecision:
    profile_id: str | None
    outcome: str
    best_profile_id: str
    best_score: float
    runner_up_score: float
    score_margin: float

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def decide(
    scores: Mapping[str, float],
    *,
    minimum_score: float,
    minimum_margin: float,
) -> MatchDecision:
    """Return the best profile or an explicit abstention."""

    if not scores:
        raise ValueError("at least one profile score is required")
    if not math.isfinite(minimum_score) or not math.isfinite(minimum_margin):
        raise ValueError("operating point must be finite")
    ranked = sorted(
        ((str(profile_id), float(score)) for profile_id, score in scores.items()),
        key=lambda item: (-item[1], item[0]),
    )
    if any(not math.isfinite(score) for _, score in ranked):
        raise ValueError("profile scores must be finite")
    best_profile_id, best_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else -1.0
    margin = best_score - runner_up_score
    if best_score < minimum_score:
        return MatchDecision(
            profile_id=None,
            outcome="abstain_below_score",
            best_profile_id=best_profile_id,
            best_score=best_score,
            runner_up_score=runner_up_score,
            score_margin=margin,
        )
    if len(ranked) > 1 and margin < minimum_margin:
        return MatchDecision(
            profile_id=None,
            outcome="abstain_below_margin",
            best_profile_id=best_profile_id,
            best_score=best_score,
            runner_up_score=runner_up_score,
            score_margin=margin,
        )
    return MatchDecision(
        profile_id=best_profile_id,
        outcome="accepted",
        best_profile_id=best_profile_id,
        best_score=best_score,
        runner_up_score=runner_up_score,
        score_margin=margin,
    )


def normalized_mean(vectors: Sequence[Sequence[float]]) -> tuple[float, ...]:
    """LiveTranscribe baseline: plain mean of stored samples, then L2 normalization."""

    if not vectors:
        raise ValueError("at least one vector is required")
    dimension = len(vectors[0])
    if dimension == 0 or any(len(vector) != dimension for vector in vectors):
        raise ValueError("vectors must share a non-zero dimension")
    totals = [0.0] * dimension
    for vector in vectors:
        for index, value in enumerate(vector):
            totals[index] += float(value)
    norm = math.sqrt(sum(value * value for value in totals))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("mean vector is not normalizable")
    return tuple(value / norm for value in totals)
