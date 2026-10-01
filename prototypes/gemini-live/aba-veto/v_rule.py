"""PROTOTYPE — rule V in the form it would take in production (contract: NOTES.md "Raw-label pass").

A label pair seen in A–B–A turns vetoes a merge only if one of its alternations is voice-consistent: none of
its turns of >= 2 s scores below TURN_MATCH_FLOOR against its own label's centroid. Checked lazily, only when
the pair blocks a candidate merge. The two classes below are copies of the shipped remap/stitch with that veto.
"""
from __future__ import annotations

import tempfile
import wave
from collections import defaultdict

from moss_transcribe_diarize.app.gemini_final_policy import FinalWordPolicy
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment
from moss_transcribe_diarize.app.gemini_long_final import LongFinalStitcher, TAU, _cosine
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, speaker_turns
from moss_transcribe_diarize.app.live_span_bounds import LIVE_SAMPLE_RATE

S = LIVE_SAMPLE_RATE
TURN_MATCH_FLOOR = .46


class ConversationVeto:
    """A–B–A alternations per label pair; `blocks` is true only for a voice-consistent alternation."""

    def __init__(self, encoder, wav_path: str, centroids: dict, *, min_alternations: int = 1,
                 voice_check: bool = True):
        self.encoder, self.wav_path, self.centroids = encoder, wav_path, centroids
        self.min_alternations, self.voice_check = min_alternations, voice_check
        self.alternations: dict[tuple[str, str], list] = defaultdict(list)
        self._genuine: dict[tuple[str, str], bool] = {}
        self._disagrees: dict[tuple, bool] = {}
        self.embeddings = 0

    def observe(self, turns) -> None:
        """turns: (label, start_sample, end_sample) in time order, one call or one chunk."""
        for a, b, c in zip(turns, turns[1:], turns[2:]):
            if a[0] == c[0] and a[0] != b[0] and b[1] - a[2] <= 2 * S and c[1] - b[2] <= 2 * S:
                self.alternations[tuple(sorted((a[0], b[0])))].append((a, b, c))

    def blocks(self, left: set, right: set) -> bool:
        return any(self.genuine(tuple(sorted((x, y)))) for x in left for y in right)

    def genuine(self, pair) -> bool:
        seen = self.alternations.get(pair)
        if not seen:
            return False
        if pair not in self._genuine:
            if not self.voice_check:
                self._genuine[pair] = len(seen) >= self.min_alternations
            else:
                self._genuine[pair] = any(not any(self.disagrees(turn) for turn in triple) for triple in seen)
        return self._genuine[pair]

    def disagrees(self, turn) -> bool:
        label, start, end = turn
        if end - start < 2 * S or label not in self.centroids:
            return False  # too short to check, or no voice on record: the alternation stands
        if turn not in self._disagrees:
            vectors = self.encoder.embed_intervals(self.wav_path, [(start / S, min(end, start + 10 * S) / S)])
            self.embeddings += 1
            self._disagrees[turn] = bool(vectors) and _cosine(
                FinalWordPolicy._unit(vectors), self.centroids[label]) < TURN_MATCH_FLOOR
        return self._disagrees[turn]


def word_turns(words):
    """The shipped FinalWordPolicy._excluded turn rule: same label, gap <= 1.5 s."""
    turns: list[tuple[str, int, int]] = []
    for word in sorted(words, key=lambda w: (w.start_sample, w.end_sample)):
        if turns and turns[-1][0] == word.speaker and word.start_sample - turns[-1][2] <= int(1.5 * S):
            label, start, end = turns[-1]
            turns[-1] = label, start, max(end, word.end_sample)
        else:
            turns.append((word.speaker, word.start_sample, word.end_sample))
    return turns


class RulePolicy(FinalWordPolicy):
    """FinalWordPolicy.remap with a configurable veto: A (shipped), B (>= 2 alternations), V (voice-checked)."""

    def __init__(self, encoder, rule: str = "V"):
        super().__init__(encoder)
        self.rule = rule
        self.last_veto: ConversationVeto | None = None
        self.last_centroids: dict = {}

    def remap(self, words, pcm16: bytes):
        self.last_words = tuple(words)
        labels = sorted({w.speaker for w in words})
        if len(labels) < 2:
            return tuple(words)
        centroids = {}
        with tempfile.NamedTemporaryFile(suffix='.wav') as file:
            with wave.open(file.name, 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(S)
                wav.writeframes(pcm16)
            for label in labels:
                intervals = self._intervals(words, label)
                if intervals:
                    vectors = self.encoder.embed_intervals(file.name, intervals)
                    if vectors:
                        centroids[label] = self._unit(vectors)
            veto = ConversationVeto(self.encoder, file.name, centroids,
                                    min_alternations=2 if self.rule == "B" else 1, voice_check=self.rule == "V")
            veto.observe(word_turns(words))
            groups = {label: {label} for label in labels}
            member = {label: label for label in labels}
            eligible = sorted(centroids)
            pairs = [(sum(x*y for x, y in zip(centroids[a], centroids[b])), a, b)
                     for i, a in enumerate(eligible) for b in eligible[i+1:]]
            for cosine, a, b in sorted(pairs, key=lambda x: (-x[0], x[1], x[2])):
                if cosine < .65:
                    break
                ga, gb = member[a], member[b]
                if ga == gb or veto.blocks(groups[ga], groups[gb]):
                    continue
                groups[ga].update(groups.pop(gb))
                for label in groups[ga]:
                    member[label] = ga
        self.last_veto, self.last_centroids, self.last_member = veto, centroids, member
        return tuple(GeminiWord(w.text, member[w.speaker], w.start_sample, w.end_sample) for w in words)


class RuleStitcher(LongFinalStitcher):
    """LongFinalStitcher.stitch with the same configurable veto."""

    def __init__(self, encoder, rule: str = "V"):
        super().__init__(encoder)
        self.rule = rule
        self.last_veto: ConversationVeto | None = None

    def stitch(self, chunks, pcm16: bytes):
        words_by_chunk, nodes, core, chunk_turns = [], set(), [], []
        for chunk in chunks:
            tagged = tuple(GeminiWord(w.text, f"c{chunk.index}:{w.speaker}", w.start_sample, w.end_sample)
                           for w in chunk.words)
            words_by_chunk.append(tagged)
            nodes.update(w.speaker for w in tagged)
            core.extend(w for w in tagged
                        if chunk.start_sample <= (w.start_sample+w.end_sample)/2 < chunk.core_end_sample)
            turns = speaker_turns(tuple(GeminiSegment(w.start_sample, w.end_sample, w.text, w.speaker)
                                        for w in tagged))
            chunk_turns.append([(row.speaker, row.start_sample, row.end_sample)
                                for row in sorted(turns, key=lambda row: (row.start_sample, row.end_sample))])
        centroids: dict[str, tuple[float, ...]] = {}
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
            veto = ConversationVeto(self.encoder, file.name, centroids,
                                    min_alternations=2 if self.rule == "B" else 1, voice_check=self.rule == "V")
            for turns in chunk_turns:
                veto.observe(turns)
            groups = {node: {node} for node in nodes}
            member = {node: node for node in nodes}

            def union(a: str, b: str) -> None:
                groups[a].update(groups.pop(b))
                for node in groups[a]:
                    member[node] = a

            for index in range(1, len(chunks)):
                prior, current = chunks[index-1], chunks[index]
                left = [w for w in words_by_chunk[index-1]
                        if w.end_sample > current.start_sample and w.start_sample < prior.end_sample]
                right = [w for w in words_by_chunk[index]
                         if w.end_sample > current.start_sample and w.start_sample < prior.end_sample]
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
                    if ga != gb and not veto.blocks(groups[ga], groups[gb]):
                        union(ga, gb)
            eligible = sorted(centroids)
            pairs = [(_cosine(centroids[a], centroids[b]), a, b)
                     for i, a in enumerate(eligible) for b in eligible[i+1:]]
            for similarity, a, b in sorted(pairs, key=lambda item: (-item[0], item[1], item[2])):
                if similarity < TAU:
                    break
                ga, gb = member[a], member[b]
                if ga != gb and not veto.blocks(groups[ga], groups[gb]):
                    union(ga, gb)
        self.last_veto = veto
        stable: dict[str, str] = {}
        result = []
        for word in core:
            root = member[word.speaker]
            if root not in stable:
                stable[root] = f"terminal-{len(stable)+1:04d}"
            result.append(GeminiWord(word.text, stable[root], word.start_sample, word.end_sample))
        return tuple(result)
