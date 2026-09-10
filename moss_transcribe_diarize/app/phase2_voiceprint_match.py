"""ADR-0009's measured profile rule, independent of storage and providers."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .live_identity_album import cosine_similarity

MATCH_MIN_SECONDS = 1.0
MATCH_MIN_SCORE = 0.46


@dataclass(frozen=True, slots=True)
class VoiceprintProfile:
    voiceprint_id: str
    label: str
    embedder_id: str
    vector: tuple[float, ...]


def normalized_mean(vectors: Sequence[Sequence[float]]) -> tuple[float, ...] | None:
    if not vectors or not vectors[0]:
        return None
    dimension = len(vectors[0])
    if any(len(vector) != dimension for vector in vectors):
        return None
    totals = tuple(sum(float(vector[i]) for vector in vectors) for i in range(dimension))
    norm = math.sqrt(sum(value * value for value in totals))
    if not math.isfinite(norm) or norm <= 0:
        return None
    return tuple(value / norm for value in totals)


def match_voiceprint(observation: object, profiles: Sequence[VoiceprintProfile]) -> VoiceprintProfile | None:
    """Match an original causal unit or terminal album, never enroll from a match."""
    seconds = getattr(observation, "sample_seconds", 0)
    vector = getattr(observation, "centroid", ())
    if (not isinstance(seconds, (int, float)) or not math.isfinite(seconds)
        or seconds < MATCH_MIN_SECONDS or getattr(observation, "provisional", True)):
        return None
    if not vector or any(not math.isfinite(value) for value in vector):
        return None
    scores = []
    for profile in profiles:
        if profile.embedder_id != getattr(observation, "embedder_id", None) or len(profile.vector) != len(vector):
            continue
        score = cosine_similarity(vector, profile.vector)
        if score is not None:
            scores.append((score, profile.voiceprint_id, profile))
    if not scores:
        return None
    score, _, profile = min(scores, key=lambda item: (-item[0], item[1]))
    return profile if score >= MATCH_MIN_SCORE else None
