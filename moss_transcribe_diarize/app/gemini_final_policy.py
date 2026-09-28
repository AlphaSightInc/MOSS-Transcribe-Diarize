"""Measured Gemini final identity policy and speech-supported word gate."""
from __future__ import annotations

import math
import tempfile
import wave
from typing import Sequence

from .gemini_provider import GeminiWord
from .live_span_bounds import LIVE_SAMPLE_RATE

S = LIVE_SAMPLE_RATE


class WebRtcWordGate:
    """Keep a word only when its padded interval contains a voiced 10 ms frame."""

    def __init__(self, vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(1)
        self.vad = vad

    def filter(self, pcm16: bytes, words: Sequence[GeminiWord], *,
               offset_sample: int = 0) -> tuple[GeminiWord, ...]:
        frame_samples = S // 100
        count = len(pcm16) // (frame_samples * 2)
        voiced = [self.vad.is_speech(pcm16[i*320:(i+1)*320], S)
                  for i in range(count)]
        kept = []
        for word in words:
            lo = max(0, math.floor((word.start_sample - offset_sample) / frame_samples - 20))
            hi = min(count, math.ceil((word.end_sample - offset_sample) / frame_samples + 20))
            if any(voiced[lo:hi]):
                kept.append(word)
        return tuple(kept)


class FinalWordPolicy:
    """Constrained single-link union of Gemini labels using production WeSpeaker."""

    def __init__(self, encoder):
        self.encoder = encoder

    @staticmethod
    def _intervals(words: Sequence[GeminiWord], label: str) -> list[tuple[float, float]]:
        spans = sorted((w.start_sample, w.end_sample) for w in words
                       if w.speaker == label and w.end_sample > w.start_sample)
        merged: list[tuple[int, int]] = []
        for start, end in spans:
            if merged and start - merged[-1][1] <= int(.6*S):
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return [(start/S, min(end, start+10*S)/S)
                for start, end in merged if end-start >= 2*S][:3]

    @staticmethod
    def _unit(vectors):
        mean = [sum(vector[i] for vector in vectors)/len(vectors)
                for i in range(len(vectors[0]))]
        norm = math.sqrt(sum(v*v for v in mean))
        return tuple(v/norm for v in mean) if norm else tuple(mean)

    @staticmethod
    def _excluded(words: Sequence[GeminiWord]) -> set[tuple[str, str]]:
        ordered = sorted(words, key=lambda w: (w.start_sample, w.end_sample))
        turns: list[tuple[str, int, int]] = []
        for word in ordered:
            if (turns and turns[-1][0] == word.speaker
                    and word.start_sample - turns[-1][2] <= int(1.5*S)):
                label, start, end = turns[-1]
                turns[-1] = label, start, max(end, word.end_sample)
            else:
                turns.append((word.speaker, word.start_sample, word.end_sample))
        excluded = set()
        for a, b, c in zip(turns, turns[1:], turns[2:]):
            if (a[0] == c[0] and a[0] != b[0]
                    and b[1]-a[2] <= 2*S and c[1]-b[2] <= 2*S):
                excluded.add(tuple(sorted((a[0], b[0]))))
        return excluded

    def remap(self, words: Sequence[GeminiWord], pcm16: bytes) -> tuple[GeminiWord, ...]:
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
        excluded = self._excluded(words)
        groups = {label: {label} for label in labels}
        member = {label: label for label in labels}
        pairs = []
        eligible = sorted(centroids)
        for i, a in enumerate(eligible):
            for b in eligible[i+1:]:
                cosine = sum(x*y for x, y in zip(centroids[a], centroids[b]))
                pairs.append((cosine, a, b))
        for cosine, a, b in sorted(pairs, key=lambda x: (-x[0], x[1], x[2])):
            if cosine < .65:
                break
            ga, gb = member[a], member[b]
            if ga == gb or any(tuple(sorted((x, y))) in excluded
                               for x in groups[ga] for y in groups[gb]):
                continue
            groups[ga].update(groups.pop(gb))
            for label in groups[ga]:
                member[label] = ga
        return tuple(GeminiWord(w.text, member[w.speaker], w.start_sample, w.end_sample)
                     for w in words)
