"""Measured POLICY-LONG stitch for 900-second terminal Gemini calls."""
from __future__ import annotations

import tempfile
import wave
from collections import defaultdict
from typing import Sequence

from .gemini_final_policy import FinalWordPolicy
from .gemini_live_runtime import GeminiSegment
from .gemini_provider import GeminiWord, TerminalChunk, speaker_turns
from .live_span_bounds import LIVE_SAMPLE_RATE

S = LIVE_SAMPLE_RATE
TAU = .65


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x*y for x, y in zip(a, b))


class LongFinalStitcher:
    """Join chunk-local labels by gated seam co-occurrence, then gated cosine."""

    def __init__(self, encoder):
        self.encoder = encoder

    def stitch(self, chunks: Sequence[TerminalChunk], pcm16: bytes) -> tuple[GeminiWord, ...]:
        words_by_chunk: list[tuple[GeminiWord, ...]] = []
        nodes: set[str] = set()
        excluded: set[tuple[str, str]] = set()
        core: list[GeminiWord] = []
        for chunk in chunks:
            tagged = tuple(GeminiWord(w.text, f"c{chunk.index}:{w.speaker}",
                                      w.start_sample, w.end_sample) for w in chunk.words)
            words_by_chunk.append(tagged)
            nodes.update(w.speaker for w in tagged)
            core.extend(w for w in tagged
                        if chunk.start_sample <= (w.start_sample+w.end_sample)/2
                        < chunk.core_end_sample)
            turns = speaker_turns(tuple(GeminiSegment(w.start_sample, w.end_sample,
                                                      w.text, w.speaker) for w in tagged))
            ordered_turns = sorted(turns, key=lambda row: (row.start_sample, row.end_sample))
            for a, b, c in zip(ordered_turns, ordered_turns[1:], ordered_turns[2:]):
                if (a.speaker == c.speaker and a.speaker != b.speaker
                        and b.start_sample-a.end_sample <= 2*S
                        and c.start_sample-b.end_sample <= 2*S):
                    excluded.add(tuple(sorted((a.speaker, b.speaker))))

        centroids: dict[str, tuple[float, ...]] = {}
        if nodes:
            with tempfile.NamedTemporaryFile(suffix=".wav") as file:
                with wave.open(file.name, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(S)
                    wav.writeframes(pcm16)
                for tagged in words_by_chunk:
                    for node in sorted({w.speaker for w in tagged}):
                        intervals = FinalWordPolicy._intervals(tagged, node)
                        if intervals:
                            vectors = self.encoder.embed_intervals(file.name, intervals)
                            if vectors:
                                centroids[node] = FinalWordPolicy._unit(vectors)

        groups = {node: {node} for node in nodes}
        member = {node: node for node in nodes}

        def compatible(a: str, b: str) -> bool:
            return not any(tuple(sorted((left, right))) in excluded
                           for left in groups[a] for right in groups[b])

        def union(a: str, b: str) -> None:
            groups[a].update(groups.pop(b))
            for node in groups[a]:
                member[node] = a

        for index in range(1, len(chunks)):
            prior, current = chunks[index-1], chunks[index]
            left = (w for w in words_by_chunk[index-1]
                    if w.end_sample > current.start_sample and w.start_sample < prior.end_sample)
            right = tuple(w for w in words_by_chunk[index]
                          if w.end_sample > current.start_sample and w.start_sample < prior.end_sample)
            weights: dict[tuple[str, str], int] = defaultdict(int)
            for a in left:
                for b in right:
                    shared = min(a.end_sample, b.end_sample)-max(a.start_sample, b.start_sample)
                    if shared > 0:
                        weights[(a.speaker, b.speaker)] += shared
            used_left: set[str] = set()
            used_right: set[str] = set()
            for (a, b), weight in sorted(weights.items(), key=lambda item: (-item[1], item[0])):
                if weight <= 0 or a in used_left or b in used_right:
                    continue
                used_left.add(a)
                used_right.add(b)
                if (a in centroids and b in centroids
                        and _cosine(centroids[a], centroids[b]) < TAU):
                    continue
                ga, gb = member[a], member[b]
                if ga != gb and compatible(ga, gb):
                    union(ga, gb)

        eligible = sorted(centroids)
        pairs = [(_cosine(centroids[a], centroids[b]), a, b)
                 for i, a in enumerate(eligible) for b in eligible[i+1:]]
        for similarity, a, b in sorted(pairs, key=lambda item: (-item[0], item[1], item[2])):
            if similarity < TAU:
                break
            ga, gb = member[a], member[b]
            if ga != gb and compatible(ga, gb):
                union(ga, gb)

        stable: dict[str, str] = {}
        result = []
        for word in core:
            root = member[word.speaker]
            if root not in stable:
                stable[root] = f"terminal-{len(stable)+1:04d}"
            result.append(GeminiWord(word.text, stable[root],
                                     word.start_sample, word.end_sample))
        return tuple(result)
