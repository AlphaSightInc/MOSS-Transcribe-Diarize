"""P61 prototype: map one window's local speaker labels to meeting IDs.

Words have ``speaker``, ``start``, and ``end`` attributes or dict keys; times are
relative to ``window_start_s``. Embeddings, when supplied, map local label to a
unit vector. This is a measurement prototype, not production code.
"""
from __future__ import annotations

from math import sqrt


def field(word, name):
    return word[name] if isinstance(word, dict) else getattr(word, name)


def cosine(a, b):
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else -1.0


def assignment(weights):
    """Maximum-weight one-to-one assignment, O(rows * columns squared).

    Zero-weight dummy columns permit unmatched local labels (new births).
    """
    if not weights:
        return ()
    n = len(weights)
    real_columns = len(weights[0])
    m = real_columns + n
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float("inf")] * (m + 1)
        used = [False] * (m + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float("inf")
            j1 = 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                weight = weights[i0 - 1][j - 1] if j <= real_columns else 0.0
                cur = -weight - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j] = cur
                    way[j] = j0
                if minv[j] < delta:
                    delta = minv[j]
                    j1 = j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    result = [None] * n
    for j in range(1, real_columns + 1):
        if p[j] and weights[p[j] - 1][j - 1] > 0:
            result[p[j] - 1] = j - 1
    return tuple(result)


class SpeakerRegistry:
    def __init__(self, *, min_overlap_s=0.6, embedding_threshold=None,
                 within_window_threshold=None, reuse_overlap=False):
        self.min_overlap_s = min_overlap_s
        self.embedding_threshold = embedding_threshold
        self.within_window_threshold = within_window_threshold
        self.reuse_overlap = reuse_overlap
        self.next_id = 1
        self.previous = []  # (absolute start, end, meeting ID)
        self.centroids = {}  # meeting ID -> vector; optional acoustic evidence
        self.births = 0
        self.merges = 0
        self.local_merges = 0
        self.overlap_reuses = 0

    def _groups(self, words, labels, embeddings):
        groups = [{label} for label in labels]
        if self.within_window_threshold is None or not embeddings:
            return groups
        spans = {label: [(float(field(w, "start")), float(field(w, "end")))
                         for w in words if str(field(w, "speaker")) == label] for label in labels}

        def compatible(left, right):
            for a in left:
                for b in right:
                    if a not in embeddings or b not in embeddings:
                        return False
                    if cosine(embeddings[a], embeddings[b]) < self.within_window_threshold:
                        return False
                    if any(min(ae, be) - max(asz, bsz) > 0.15
                           for asz, ae in spans[a] for bsz, be in spans[b]):
                        return False
            return True

        while True:
            candidates = [(min(cosine(embeddings[a], embeddings[b]) for a in left for b in right), i, j)
                          for i, left in enumerate(groups) for j, right in enumerate(groups)
                          if i < j and compatible(left, right)]
            if not candidates:
                break
            _, i, j = max(candidates)
            groups[i] |= groups[j]
            del groups[j]
            self.local_merges += 1
        return groups

    def observe_window(self, window_start_s, words, embeddings=None):
        labels = sorted({str(field(w, "speaker")) for w in words})
        groups = self._groups(words, labels, embeddings)
        group_by_label = {label: min(group) for group in groups for label in group}
        representatives = sorted({min(group) for group in groups})
        group_embeddings = {}
        if embeddings:
            for group in groups:
                vectors = [embeddings[label] for label in group if label in embeddings]
                if vectors:
                    group_embeddings[min(group)] = [sum(v[i] for v in vectors) / len(vectors)
                                                    for i in range(len(vectors[0]))]
        previous_ids = sorted({row[2] for row in self.previous})
        available_ids = sorted(set(previous_ids) | set(self.centroids))
        support = {(label, mid): 0.0 for label in representatives for mid in available_ids}
        for w in words:
            label = group_by_label[str(field(w, "speaker"))]
            start = window_start_s + float(field(w, "start"))
            end = window_start_s + float(field(w, "end"))
            candidates = [(min(end, pe) - max(start, ps), mid)
                          for ps, pe, mid in self.previous]
            if candidates:
                duration, mid = max(candidates)
                if duration > 0:
                    support[(label, mid)] += duration

        weights = []
        for label in representatives:
            row = []
            for mid in available_ids:
                overlap = support[(label, mid)]
                acoustic = -1.0
                if label in group_embeddings and mid in self.centroids:
                    acoustic = cosine(group_embeddings[label], self.centroids[mid])
                if overlap >= self.min_overlap_s:
                    row.append(overlap)
                elif self.embedding_threshold is not None and acoustic >= self.embedding_threshold:
                    row.append(acoustic)  # tie break uses cosine
                else:
                    row.append(0.0)
            weights.append(row)
        chosen = assignment(weights)
        mapped_groups = {}
        for label, col in zip(representatives, chosen):
            if col is None:
                mapped_groups[label] = f"M{self.next_id}"
                self.next_id += 1
                self.births += 1
            else:
                mapped_groups[label] = available_ids[col]
        if self.reuse_overlap:
            spans = {label: [(float(field(w, "start")), float(field(w, "end")))
                             for w in words if group_by_label[str(field(w, "speaker"))] == label]
                     for label in representatives}
            for label, col in zip(representatives, chosen):
                if col is not None:
                    continue
                candidates = sorted(((support[(label, mid)], mid) for mid in set(mapped_groups.values())
                                     if mid in available_ids and support[(label, mid)] >= self.min_overlap_s),
                                    reverse=True)
                for _, mid in candidates:
                    others = [other for other, assigned in mapped_groups.items()
                              if other != label and assigned == mid]
                    if any(min(ae, be) - max(asz, bsz) > 0.15
                           for other in others for asz, ae in spans[label]
                           for bsz, be in spans[other]):
                        continue
                    mapped_groups[label] = mid
                    self.births -= 1
                    self.overlap_reuses += 1
                    break
        mapped = {label: mapped_groups[group_by_label[label]] for label in labels}
        self.previous = [
            (window_start_s + float(field(w, "start")),
             window_start_s + float(field(w, "end")), mapped[str(field(w, "speaker"))])
            for w in words
        ]
        for label, vector in group_embeddings.items():
            mid = mapped_groups[label]
            old = self.centroids.get(mid)
            self.centroids[mid] = list(vector) if old is None else [
                0.8 * a + 0.2 * b for a, b in zip(old, vector)
            ]
        return mapped, []
