"""Map Gemini window-local speaker labels to stable meeting identities."""
from __future__ import annotations

import math
from typing import Sequence

from scipy.optimize import linear_sum_assignment

from .gemini_provider import GeminiWord
from .live_span_bounds import LIVE_SAMPLE_RATE


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    norm = math.sqrt(sum(x*x for x in left) * sum(x*x for x in right))
    return sum(x*y for x, y in zip(left, right)) / norm if norm else -1.0


class ContinuityRegistry:
    """One session's overlap evidence and visible-birth state."""

    def __init__(self, *, embedding_threshold: float, within_window_threshold: float,
                 birth_min_seconds: float, min_overlap_seconds: float = .3):
        self.embedding_threshold = embedding_threshold
        self.within_window_threshold = within_window_threshold
        self.birth_min_samples = round(birth_min_seconds * LIVE_SAMPLE_RATE)
        self.min_overlap_samples = round(min_overlap_seconds * LIVE_SAMPLE_RATE)
        self._previous: list[GeminiWord] = []
        self._centroids: dict[str, tuple[float, ...]] = {}
        self._next_id = 1

    def _groups(self, words: Sequence[GeminiWord], labels: list[str],
                vectors: dict[str, tuple[float, ...]]) -> list[set[str]]:
        groups = [{label} for label in labels]
        spans = {label: [(word.start_sample, word.end_sample) for word in words
                         if word.speaker == label] for label in labels}
        while True:
            candidates = []
            for i, left in enumerate(groups):
                for j in range(i + 1, len(groups)):
                    right = groups[j]
                    pairs = [(a, b) for a in left for b in right]
                    if any(a not in vectors or b not in vectors or
                           _cosine(vectors[a], vectors[b]) < self.within_window_threshold or
                           any(min(ae, be) - max(asz, bsz) > round(.15*LIVE_SAMPLE_RATE)
                               for asz, ae in spans[a] for bsz, be in spans[b])
                           for a, b in pairs):
                        continue
                    candidates.append((min(_cosine(vectors[a], vectors[b])
                                           for a, b in pairs), i, j))
            if not candidates:
                return groups
            _, i, j = max(candidates)
            groups[i].update(groups[j])
            del groups[j]

    def observe_window(self, window_start_s: float, words: Sequence[GeminiWord],
                       embeddings=None, *, committed_through_sample: int | None = None):
        del window_start_s
        vectors = {label: tuple(vector) for label, (vector, _seconds) in (embeddings or {}).items()}
        labels = sorted({word.speaker for word in words})
        groups = self._groups(words, labels, vectors)
        group_by_label = {label: min(group) for group in groups for label in group}
        representatives = sorted({min(group) for group in groups})
        group_vectors = {}
        for group in groups:
            available = [vectors[label] for label in group if label in vectors]
            if available:
                group_vectors[min(group)] = tuple(sum(vector[i] for vector in available) / len(available)
                                                 for i in range(len(available[0])))
        old_ids = sorted({word.speaker for word in self._previous} | set(self._centroids))
        support = {(label, mid): 0 for label in representatives for mid in old_ids}
        for word in words:
            candidates = [(min(word.end_sample, old.end_sample)
                           - max(word.start_sample, old.start_sample), old.speaker)
                          for old in self._previous]
            if candidates:
                duration, mid = max(candidates)
                if duration > 0:
                    support[(group_by_label[word.speaker], mid)] += duration
        weights = [[(support[(label, mid)] / LIVE_SAMPLE_RATE
                     if support[(label, mid)] >= self.min_overlap_samples
                     else _cosine(group_vectors[label], self._centroids[mid])
                     if label in group_vectors and mid in self._centroids
                     and _cosine(group_vectors[label], self._centroids[mid]) >= self.embedding_threshold
                     else 0)
                    for mid in old_ids] + [0] * len(representatives) for label in representatives]
        mapped_groups: dict[str, str | None] = {}
        if representatives:
            rows, columns = linear_sum_assignment([[-value for value in row] for row in weights])
            for row, column in zip(rows, columns, strict=True):
                if column < len(old_ids) and weights[row][column] > 0:
                    mapped_groups[representatives[row]] = old_ids[column]
        for label in representatives:
            if label in mapped_groups:
                continue
            speech = sum(max(0, word.end_sample - word.start_sample)
                         for word in words if group_by_label[word.speaker] == label)
            if speech >= self.birth_min_samples:
                mapped_groups[label] = f"speaker-{self._next_id:04d}"
                self._next_id += 1
            else:
                closest = max(((support[(label, mid)], mid) for mid in old_ids),
                              default=(0, None))
                mapped_groups[label] = closest[1] if closest[0] > 0 else None
        mapping = {label: mapped_groups[group_by_label[label]] for label in labels}
        # C4 retains the entire last Gemini observation as overlap evidence;
        # publication ownership is a separate word-end frontier decision.
        del committed_through_sample
        self._previous = [GeminiWord(word.text, mapping[word.speaker],
                                     word.start_sample, word.end_sample)
                          for word in words if mapping[word.speaker] is not None]
        for label, vector in group_vectors.items():
            mid = mapped_groups[label]
            if mid is None:
                continue
            old = self._centroids.get(mid)
            self._centroids[mid] = (vector if old is None else
                                    tuple(.8*a + .2*b for a, b in zip(old, vector)))
        return mapping, ()
