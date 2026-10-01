"""Compose two Gemini capture-lane engines on one public LiveSession frontier."""
from __future__ import annotations

import asyncio
import math
import re
import tempfile
import threading
import time
import unicodedata
import wave
from pathlib import Path
from array import array
from typing import Callable, Sequence

from .gemini_hybrid_engine import attributed_embedding_intervals
from .gemini_live_runtime import (GeminiBase, GeminiPreview, GeminiRelabel, GeminiTurnBridge,
                                  GeminiRolling, GeminiSegment, GeminiUpdate,
                                  _preview_units, _unit_weight)
from .gemini_provider import GeminiWord
from .gemini_coverage import MIN_RUN_SAMPLES, _span, uncovered_runs
from .live_span_bounds import LIVE_SAMPLE_RATE

GEMINI_MIC_WINDOW_SECONDS = 30
GEMINI_MIC_WINDOW_STRIDE_SECONDS = 15


def _token(text: str) -> str:
    return "".join(re.findall(r"[^\W_]+(?:'[^\W_]+)?", text.lower(), flags=re.UNICODE))


def _repeated_units(reference: Sequence[str], units: Sequence[str]) -> set[int]:
    """Indexes of `units` inside runs of at least three words (five CJK characters) of `reference`.

    Each run is the longest stretch starting there that occurs anywhere in the reference. One
    in-order alignment of the two texts is not used: the reference repeats itself (committed
    rows and the preview restate the same speech; speakers repeat sentences), and a single
    alignment anchored on the wrong copy leaves the rest of an echoed row unmatched.
    """
    places: dict[str, list[int]] = {}
    for index, unit in enumerate(reference):
        places.setdefault(unit, []).append(index)
    repeated: set[int] = set()
    index = 0
    while index < len(units):
        longest = 0
        for at in places.get(units[index], ()):
            size = 1
            while (index + size < len(units) and at + size < len(reference)
                   and units[index + size] == reference[at + size]):
                size += 1
            longest = max(longest, size)
        if sum(_unit_weight(unit) for unit in units[index:index + longest]) >= 15:
            repeated.update(range(index, index + longest))
            index += longest
        else:
            index += 1
    return repeated


def _without_echo(row: GeminiSegment, heard: Sequence[GeminiSegment],
                  own: Sequence[GeminiSegment]) -> GeminiSegment | None:
    """A mic preview row minus the runs that repeat what the system lane said around it.

    A W3 mic turn under continuous speaker echo grows for minutes, while its row is clipped to
    the mic frontier and the system preview covers only the uncommitted suffix. So the row is
    compared, in order, with the system words it could repeat: committed system rows and the
    system preview ending within n/1.5 + 5 s of it (speech runs faster than 1.5 units/s).
    Leftover runs under four units are echo the two models heard differently; a row that held
    echo also drops leftovers that repeat the lane's own committed words, already shown above.
    Measured on recorded W3 streams: prototypes/gemini-live/mic-preview-echo/NOTES.md.
    """
    spans = _preview_units(row.text)
    units = [unit for unit, _, _ in spans]
    since = row.end_sample - round((len(units) / 1.5 + 5) * LIVE_SAMPLE_RATE)
    until = row.end_sample + 2 * LIVE_SAMPLE_RATE
    def nearby(rows):
        return [unit for other in rows if other.end_sample >= since and other.start_sample < until
                for unit, _, _ in _preview_units(other.text)]
    echo = _repeated_units(nearby(heard), units)
    if not echo:
        return row
    runs: list[list[int]] = []
    for index in range(len(units)):
        if index in echo:
            continue
        if runs and runs[-1][-1] == index - 1:
            runs[-1].append(index)
        else:
            runs.append([index])
    mine = nearby(own)
    runs = [run for run in runs if len(run) >= 4
            and 2 * len(_repeated_units(mine, [units[i] for i in run])) < len(run)]
    if not runs:
        return None
    text = " … ".join(row.text[spans[run[0]][1]:spans[run[-1]][2]] for run in runs)
    return GeminiSegment(row.start_sample, row.end_sample, text, row.speaker, row.source_lane)


_SUSTAINED_SCRIPT = 20  # four words, or seven CJK-like characters, of one script


def _script(char: str) -> str | None:
    """The writing system of a letter (Hiragana and Katakana are one); None for other characters."""
    if not char.isalpha():
        return None
    head = unicodedata.name(char, "").split(" ")[0]
    return "KANA" if head in ("HIRAGANA", "KATAKANA") else head


def _script_runs(text: str) -> list[tuple[str, int, int, int]]:
    """(script, weight, start, end) per maximal same-script stretch of letters in `text`.

    Weight is 3 per Han/kana/Hangul character and 5 per word of any other script (a word
    keeps its combining marks); digits and punctuation carry no script. A run's span reaches
    the next run, so removing it removes its trailing punctuation too.
    """
    runs: list[list] = []
    index = 0
    while index < len(text):
        script = _script(text[index])
        if script is None:
            index += 1
            continue
        stop = index + 1
        while stop < len(text) and (_script(text[stop]) == script
                                    or unicodedata.category(text[stop]).startswith("M")):
            stop += 1
        weight = (3 * sum(char.isalpha() for char in text[index:stop])
                  if script in ("CJK", "KANA", "HANGUL") else 5)
        if runs and runs[-1][0] == script:
            runs[-1][1] += weight
        else:
            if runs:
                runs[-1][3] = index
            runs.append([script, weight, index, len(text)])
        index = stop
    return [tuple(run) for run in runs]


def _sustained_scripts(text: str) -> set[str]:
    """Scripts with at least four words (seven CJK-like characters) in `text`."""
    totals: dict[str, int] = {}
    for script, weight, _, _ in _script_runs(text):
        totals[script] = totals.get(script, 0) + weight
    return {script for script, total in totals.items() if total >= _SUSTAINED_SCRIPT}


def _without_foreign_script(row: GeminiSegment, established: set[str]) -> GeminiSegment | None:
    """A short mic preview row minus the words in a script the meeting has not used.

    Noise and echo residue make W3 emit isolated words in unrelated scripts (kana, Devanagari,
    Hangul in a Mandarin or English meeting). A row that itself holds sustained speech in some
    script is left whole, so code-switched terms inside a sentence are never touched; a
    genuine first short reply in a new language waits for its commit instead.
    Measured: prototypes/gemini-live/preview-script/NOTES.md.
    """
    if _sustained_scripts(row.text):
        return row
    runs = _script_runs(row.text)
    foreign = [run for run in runs if run[0] not in established]
    if not foreign:
        return row
    text = row.text
    for _, _, start, end in reversed(foreign):
        text = text[:start] + text[end:]
    text = text.strip()
    if len(foreign) == len(runs) or not text:
        return None
    return GeminiSegment(row.start_sample, row.end_sample, text, row.speaker, row.source_lane)


class TextEchoGuard:
    """Drop timed echo phrases, or single matches without a usable mic voice."""

    _TOLERANCE = 3 * LIVE_SAMPLE_RATE // 2

    def filter(self, microphone: Sequence[GeminiWord],
               system: Sequence[GeminiWord]) -> tuple[GeminiWord, ...]:
        reference = [(_token(w.text), (w.start_sample + w.end_sample) // 2) for w in system]
        kept = []
        for word in microphone:
            token = _token(word.text)
            middle = (word.start_sample + word.end_sample) // 2
            if token and any(token == other and abs(middle - at) <= self._TOLERANCE
                             for other, at in reference):
                continue
            kept.append(word)
        return tuple(kept)

    def filter_voice_aware(self, microphone: Sequence[GeminiWord],
                           system: Sequence[GeminiWord], embeddings
                           ) -> tuple[GeminiWord, ...]:
        mic_tokens = [_token(word.text) for word in microphone]
        sys_tokens = [_token(word.text) for word in system]
        phrase = set()
        for i in range(len(microphone)-1):
            if (microphone[i].speaker != microphone[i+1].speaker
                    or not mic_tokens[i] or not mic_tokens[i+1]):
                continue
            for j in range(len(system)-1):
                if (system[j].speaker != system[j+1].speaker
                        or mic_tokens[i] != sys_tokens[j]
                        or mic_tokens[i+1] != sys_tokens[j+1]):
                    continue
                if all(abs((microphone[i+k].start_sample + microphone[i+k].end_sample)//2
                           - (system[j+k].start_sample + system[j+k].end_sample)//2)
                       <= self._TOLERANCE for k in (0, 1)):
                    phrase.update((i, i+1))
        vectorless = tuple(word for i, word in enumerate(microphone)
                           if i not in phrase and word.speaker not in embeddings)
        fallback_kept = {id(word) for word in self.filter(vectorless, system)}
        return tuple(word for i, word in enumerate(microphone)
                     if i not in phrase and (word.speaker in embeddings
                                             or id(word) in fallback_kept))


class SystemWordLedger:
    """Recent timed system words and a completed frontier for the mic echo guard."""

    def __init__(self):
        self._ready = threading.Condition()
        self._frontier = 0
        self._words: list[GeminiWord] = []
        self._guard = TextEchoGuard()

    def observe(self, words: Sequence[GeminiWord], frontier: int) -> None:
        with self._ready:
            self._words.extend(words)
            self._frontier = max(self._frontier, frontier)
            self._words = [w for w in self._words
                           if w.end_sample >= self._frontier - 305 * LIVE_SAMPLE_RATE]
            self._ready.notify_all()

    def filter_mic(self, words: Sequence[GeminiWord], *,
                   through_sample: int) -> tuple[GeminiWord, ...]:
        return self._guard.filter(words, self.words_through(through_sample))

    def words_through(self, through_sample: int) -> tuple[GeminiWord, ...]:
        with self._ready:
            self._ready.wait_for(lambda: self._frontier >= through_sample, timeout=30)
            return tuple(self._words)


class CrossLaneVoiceEchoGuard:
    """Reject mic words only when their voice and time match system speech."""

    _TOLERANCE = round(.4 * LIVE_SAMPLE_RATE)

    def __init__(self, *, threshold: float):
        self.threshold = threshold
        self.dropped = 0
        self._ready = threading.Condition()
        self._frontier = 0
        self._system: list[tuple[GeminiWord, tuple[float, ...]]] = []

    def observe_system(self, words: Sequence[GeminiWord], embeddings, *, frontier: int) -> None:
        with self._ready:
            self._system.extend((word, tuple(embeddings[word.speaker][0]))
                                for word in words if word.speaker in embeddings)
            self._frontier = max(self._frontier, frontier)
            self._system = [(word, vector) for word, vector in self._system
                            if word.end_sample >= self._frontier - 305 * LIVE_SAMPLE_RATE]
            self._ready.notify_all()

    def _filter(self, words: Sequence[GeminiWord], embeddings,
                system: Sequence[tuple[GeminiWord, tuple[float, ...]]]) -> tuple[GeminiWord, ...]:
        kept = []
        for word in words:
            entry = embeddings.get(word.speaker)
            vector = tuple(entry[0]) if entry is not None else None
            if vector is not None and any(
                other.start_sample <= word.end_sample + self._TOLERANCE
                and word.start_sample <= other.end_sample + self._TOLERANCE
                and self._cosine(vector, other_vector) >= self.threshold
                for other, other_vector in system):
                self.dropped += 1
            else:
                kept.append(word)
        return tuple(kept)

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        dot = sum(a*b for a, b in zip(left, right))
        norm = math.sqrt(sum(a*a for a in left) * sum(b*b for b in right))
        return dot / norm if norm else -1.0

    def filter_mic(self, words: Sequence[GeminiWord], embeddings, *,
                   through_sample: int) -> tuple[GeminiWord, ...]:
        with self._ready:
            self._ready.wait_for(lambda: self._frontier >= through_sample, timeout=30)
            return self._filter(words, embeddings, self._system)

    def filter_terminal(self, words: Sequence[GeminiWord], embeddings,
                        system_words: Sequence[GeminiWord], system_embeddings
                        ) -> tuple[GeminiWord, ...]:
        system = [(word, tuple(system_embeddings[word.speaker][0]))
                  for word in system_words if word.speaker in system_embeddings]
        return self._filter(words, embeddings, system)


class AcousticEchoGuard:
    """Keep mic words with no competing system voice or sufficient local level."""

    def __init__(self, system_read: Callable[[int, int], bytes], *, vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(1)
        self.system_read = system_read
        self.vad = vad

    @staticmethod
    def _rms(pcm16: bytes) -> float:
        samples = array("h")
        samples.frombytes(pcm16)
        return math.sqrt(sum(value * value for value in samples) / len(samples)) if samples else 0.0

    def filter(self, mic_pcm16: bytes, words: Sequence[GeminiWord], *,
               offset_sample: int = 0) -> tuple[GeminiWord, ...]:
        end_sample = offset_sample + len(mic_pcm16) // 2
        kept = []
        frame = LIVE_SAMPLE_RATE // 100
        max_lag = LIVE_SAMPLE_RATE // 10
        threshold = 10 ** (-15 / 20)
        for word in words:
            start = max(offset_sample, min(end_sample - 1, word.start_sample))
            end = min(end_sample, max(start + 1, word.end_sample))
            if end <= start:
                continue
            system_start = max(0, start - max_lag)
            system_end = min(end_sample, math.ceil(end / frame) * frame)
            system = self.system_read(system_start, system_end)
            first_frame = start // frame
            last_frame = math.ceil(end / frame)
            system_voiced = any(
                self.vad.is_speech(system[(i*frame-system_start)*2:
                                          ((i+1)*frame-system_start)*2], LIVE_SAMPLE_RATE)
                for i in range(first_frame, last_frame)
                if (i+1)*frame <= system_end)
            if not system_voiced:
                kept.append(word)
                continue
            mic = mic_pcm16[(start-offset_sample)*2:(end-offset_sample)*2]
            mic_rms = self._rms(mic)
            duration = end - start
            system_rms = max(self._rms(system[(max(0, start-lag)-system_start)*2:
                                          (min(system_end, max(0, start-lag)+duration)-system_start)*2])
                             for lag in range(0, max_lag+1, frame))
            if mic_rms >= system_rms * threshold:
                kept.append(word)
        return tuple(kept)


def _local_text_weight(words: Sequence[GeminiWord]) -> int:
    return sum(_unit_weight(unit) for word in words for unit, _, _ in _preview_units(word.text))


class LocalVoiceEvidence:
    """Sustained microphone speech above the tab's measured echo return.

    Runs use provider labels and 0.6 s joins, before the level/voice/text guards.
    Short local runs admit only themselves; they do not establish the lane's 2 s anchor.
    """

    def __init__(self, system_read: Callable[[int, int], bytes], *, vad_factory=None):
        if vad_factory is None:
            import webrtcvad
            vad_factory = lambda: webrtcvad.Vad(3)
        self.system_read = system_read
        self.vad_factory = vad_factory
        self.echo_return_db: float | None = None
        self.sustained_seconds = 0.0
        self._seen_stretches: list[tuple[int, int]] = []

    def _frames(self, mic_pcm16: bytes, system_pcm16: bytes):
        import numpy as np
        frame = LIVE_SAMPLE_RATE // 100
        mic = np.frombuffer(mic_pcm16, dtype="<i2")
        tab = np.frombuffer(system_pcm16, dtype="<i2")
        n = min(len(mic), len(tab)) // frame
        if not n:
            return np.zeros(0, dtype=bool)
        mic, tab = mic[:n*frame], tab[:n*frame]
        mic_vad, tab_vad = self.vad_factory(), self.vad_factory()
        step = frame*2
        mic_voice = np.fromiter((mic_vad.is_speech(mic_pcm16[i*step:(i+1)*step], LIVE_SAMPLE_RATE)
                                for i in range(n)), dtype=bool, count=n)
        tab_voice = np.fromiter((tab_vad.is_speech(system_pcm16[i*step:(i+1)*step], LIVE_SAMPLE_RATE)
                                for i in range(n)), dtype=bool, count=n)
        mic_rms = np.sqrt((mic.astype(np.float64).reshape(n, frame)**2).mean(axis=1))
        tab_rms = np.sqrt((tab.astype(np.float64).reshape(n, frame)**2).mean(axis=1))
        pad_rms = np.concatenate([np.zeros(10), tab_rms])
        pad_voice = np.concatenate([np.zeros(10, dtype=bool), tab_voice])
        best = np.max(np.stack([pad_rms[k:k+n] for k in range(11)]), axis=0)
        near = np.any(np.stack([pad_voice[k:k+n] for k in range(11)]), axis=0)
        measured = near & (best > 0)
        if measured.sum() >= 100:
            echo_return = float(np.median(20*np.log10(np.maximum(mic_rms[measured], 1e-3)/best[measured])))
            self.echo_return_db = echo_return
            return mic_voice & (~near | (mic_rms > best*10**((echo_return+6)/20)))
        return mic_voice & (~near | (mic_rms >= best*10**(-15/20)))

    def _audio(self, mic_pcm16: bytes, words: Sequence[GeminiWord], offset_sample: int,
               whole_lane: bool):
        import numpy as np
        frame = LIVE_SAMPLE_RATE // 100
        n = len(mic_pcm16)//2//frame
        flags = np.zeros(n, dtype=bool)
        if not whole_lane:
            part = self._frames(mic_pcm16, self.system_read(offset_sample, offset_sample+len(mic_pcm16)//2))
            flags[:len(part)] = part
            return flags
        stride, context = GEMINI_MIC_WINDOW_STRIDE_SECONDS*100, GEMINI_MIC_WINDOW_SECONDS*100
        ends = list(range(stride, n+1, stride))
        if not ends or ends[-1] < n:
            ends.append(n)
        # Include the 0.2 s word pad plus the 0.4 s evidence stretch at either frontier.
        first = min((w.start_sample+w.end_sample)//2 for w in words)//frame-60
        last = max((w.start_sample+w.end_sample)//2 for w in words)//frame+61
        done = 0
        for end in ends:
            lo = max(0, end-context)
            if end > first and done < last:
                part = self._frames(mic_pcm16[lo*frame*2:end*frame*2],
                                    self.system_read(lo*frame, end*frame))
                flags[done:end] = part[done-lo:end-lo]
            done = end
        return flags

    @staticmethod
    def _runs(words: Sequence[GeminiWord]) -> list[list[GeminiWord]]:
        by_label: dict[str, list[GeminiWord]] = {}
        for word in words:
            by_label.setdefault(word.speaker, []).append(word)
        runs = []
        for rows in by_label.values():
            end = None
            for word in sorted(rows, key=lambda w: w.start_sample):
                if end is not None and word.start_sample-end <= .6*LIVE_SAMPLE_RATE:
                    runs[-1].append(word)
                    end = max(end, word.end_sample)
                else:
                    runs.append([word])
                    end = word.end_sample
        return runs

    def local_words(self, mic_pcm16: bytes, words: Sequence[GeminiWord], *,
                    offset_sample: int = 0, whole_lane: bool = False) -> dict[int, int]:
        import numpy as np
        if not words:
            return {}
        flags = self._audio(mic_pcm16, words, offset_sample, whole_lane)
        stretches, start, last = [], None, None
        for index in np.flatnonzero(flags):
            if start is None:
                start = index
            elif index-last-1 > 5:
                stretches.append((int(start), int(last)+1))
                start = index
            last = index
        if start is not None:
            stretches.append((int(start), int(last)+1))
        stretches = [(a, b) for a, b in stretches if b-a >= 40]
        sustained = np.zeros(len(flags), dtype=bool)
        frame = LIVE_SAMPLE_RATE//100
        for a, b in stretches:
            sustained[a:b] = True
        seen = sorted(self._seen_stretches + [(offset_sample+a*frame, offset_sample+b*frame)
                                             for a, b in stretches])
        merged = []
        for a, b in seen:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        self._seen_stretches = merged
        self.sustained_seconds = sum(b-a for a, b in merged)/LIVE_SAMPLE_RATE

        def on(mask, word):
            middle = ((word.start_sample+word.end_sample)//2-offset_sample)//frame
            return bool(mask[max(0, middle-20):max(0, middle+21)].any())
        local = {}
        for number, run in enumerate(self._runs(words)):
            on_audio = [w for w in run if on(flags, w)]
            if (any(on(sustained, w) and _local_text_weight((w,)) > 0 for w in run)
                    and len(on_audio) >= .8*len(run) and _local_text_weight(on_audio) >= 15):
                local.update((id(w), number) for w in on_audio)
        return local

    def is_local_run(self, mic_pcm16: bytes, words: Sequence[GeminiWord], *,
                     offset_sample: int = 0, whole_lane: bool = False) -> bool:
        """Judge one candidate run alone, independent of lane memory or neighbouring words."""
        local = self.local_words(mic_pcm16, words, offset_sample=offset_sample, whole_lane=whole_lane)
        return bool(words) and len(local) >= .8*len(words) and _local_text_weight(
            tuple(w for w in words if id(w) in local)) >= 15


class MicrophoneWordGate:
    """One meeting's microphone admission: existing 2 s anchor or measured local run."""

    def __init__(self, webrtc_gate, system_words: SystemWordLedger,
                 acoustic_gate=None, report_drops=None,
                 voice_guard: CrossLaneVoiceEchoGuard | None = None,
                 embedding_source=None, local_voice: LocalVoiceEvidence | None = None):
        self.local_voice = local_voice
        self._local_level_kept = self._local_unanchored_kept = 0
        self.webrtc_gate = webrtc_gate
        self.system_words = system_words
        self.acoustic_gate = acoustic_gate
        self.report_drops = report_drops
        self.voice_guard = voice_guard
        self.embedding_source = embedding_source
        self.local_speech_seen = False
        self.lane_withheld_words = 0

    def _record(self, before: int, acoustic: int, after_voice: int,
                after_text: int, unanchored: int = 0, lane_withheld: int = 0) -> None:
        if self.report_drops is not None:
            counts = {"acoustic_gate_dropped_words": before-acoustic,
                      "text_guard_dropped_words": after_voice-after_text}
            if self.voice_guard is not None and acoustic > after_voice:
                counts["mic_echo_dropped_by_voice"] = acoustic-after_voice
            if unanchored:
                counts["unanchored_window_dropped_words"] = unanchored
            if lane_withheld:
                counts["unanchored_lane_withheld_words"] = lane_withheld
            if self.local_voice is not None:
                counts.update(mic_words_from_provider=before,
                              mic_words_kept_by_local_voice_level=self._local_level_kept,
                              mic_words_kept_unanchored_by_local_voice=self._local_unanchored_kept,
                              mic_local_voice_seconds=self.local_voice.sustained_seconds)
                if self.local_voice.echo_return_db is not None:
                    counts["mic_echo_return_db"] = self.local_voice.echo_return_db
            self.report_drops(counts)

    def _level(self, pcm16, words, offset_sample, local):
        today = (self.acoustic_gate.filter(pcm16, words, offset_sample=offset_sample)
                 if self.acoustic_gate is not None else tuple(words))
        kept_ids = {id(word) for word in today}
        kept = tuple(word for word in words if id(word) in kept_ids or id(word) in local)
        self._local_level_kept = len(kept)-len(today)
        self._local_unanchored_kept = 0
        return kept

    @staticmethod
    def _text(kept, system, vectors, local):
        guard = TextEchoGuard()
        today = guard.filter_voice_aware(kept, system, vectors)
        if not local:
            return today
        phrase_only = {id(w) for w in guard.filter_voice_aware(
            kept, system, {w.speaker: None for w in kept})}
        passed = {id(w) for w in today}
        return tuple(w for w in kept if id(w) in passed or (id(w) in local and id(w) in phrase_only))

    def _evidenced(self, kept, local):
        by_run = {}
        for word in kept:
            if id(word) in local:
                by_run.setdefault(local[id(word)], []).append(word)
        ids = {id(w) for run in by_run.values() if _local_text_weight(run) >= 15 for w in run}
        rescued = tuple(w for w in kept if id(w) in ids)
        self._local_unanchored_kept = len(rescued)
        return rescued

    def filter(self, pcm16: bytes, words: Sequence[GeminiWord], *,
               offset_sample: int = 0) -> tuple[GeminiWord, ...]:
        voiced = self.webrtc_gate.filter(pcm16, words, offset_sample=offset_sample)
        if not voiced:
            return ()
        local = (self.local_voice.local_words(pcm16, voiced, offset_sample=offset_sample)
                 if self.local_voice is not None else {})
        acoustic = self._level(pcm16, voiced, offset_sample, local)
        through_sample = offset_sample + len(pcm16) // 2
        system = self.system_words.words_through(through_sample)
        kept = acoustic
        if self.voice_guard is not None and kept:
            vectors = self.embedding_source(pcm16, offset_sample, kept)
            kept = self.voice_guard.filter_mic(
                kept, vectors, through_sample=through_sample)
            after_voice = len(kept)
            kept = self._text(kept, system, vectors, local)
        else:
            after_voice = len(kept)
            kept = TextEchoGuard().filter(kept, system)
        after_text = len(kept)
        # Short local runs admit only their surviving words; only a 2 s span opens the lane.
        unanchored = 0
        if kept and not attributed_embedding_intervals(kept):
            rescued = self._evidenced(kept, local)
            unanchored, kept = len(kept)-len(rescued), rescued
        elif kept:
            self.local_speech_seen = True
        self._record(len(voiced), len(acoustic), after_voice, after_text, unanchored)
        return kept

    def filter_terminal(self, mic_pcm16: bytes, words: Sequence[GeminiWord],
                        system_words: Sequence[GeminiWord], *,
                        system_pcm16: bytes | None = None) -> tuple[GeminiWord, ...]:
        # TerminalTranscriber has already applied the mic WebRTC word gate.
        local = (self.local_voice.local_words(mic_pcm16, words, whole_lane=True)
                 if self.local_voice is not None else {})
        acoustic = self._level(mic_pcm16, words, 0, local)
        kept = acoustic
        if self.voice_guard is not None and kept and system_pcm16 is not None:
            mic_vectors = self.embedding_source(mic_pcm16, 0, kept)
            system_vectors = self.embedding_source(system_pcm16, 0, system_words)
            kept = self.voice_guard.filter_terminal(
                kept, mic_vectors, system_words, system_vectors)
            after_voice = len(kept)
            kept = self._text(kept, system_words, mic_vectors, local)
        else:
            after_voice = len(kept)
            kept = TextEchoGuard().filter(kept, system_words)
        after_text = len(kept)
        # Lane memory retains its 2 s meaning. Without it, each local run earns admission.
        withheld = 0
        if kept and not self.local_speech_seen:
            if attributed_embedding_intervals(kept):
                self.local_speech_seen = True
            else:
                rescued = self._evidenced(kept, local)
                withheld, kept = len(kept)-len(rescued), rescued
                self.lane_withheld_words += withheld
        self._record(len(words), len(acoustic), after_voice, after_text, lane_withheld=withheld)
        return kept

    def restore_witnessed_words(self, mic_pcm16: bytes, cleanup: Sequence[GeminiWord],
                               kept: Sequence[GeminiWord], witness: Sequence[GeminiWord],
                               system_words: Sequence[GeminiWord], *, system_pcm16: bytes,
                               skip=(), local_speaker: str = "local"):
        """Judge each provider-hole candidate alone, then copy a kept neighbour's label."""
        output, restored = list(kept), []
        if self.local_voice is None:
            return tuple(output), restored
        for run, samples in uncovered_runs(cleanup, witness, skip=skip):
            if samples < MIN_RUN_SAMPLES:
                continue
            voiced = tuple(self.webrtc_gate.filter(mic_pcm16, run))
            if not self.local_voice.is_local_run(mic_pcm16, voiced, whole_lane=True):
                continue
            local = self.local_voice.local_words(mic_pcm16, voiced, whole_lane=True)
            admitted = self._evidenced(voiced, local)
            admitted = self.filter_terminal(mic_pcm16, admitted, system_words,
                                            system_pcm16=system_pcm16)
            admitted = self._evidenced(admitted, local)
            if not admitted:
                continue
            a, b = admitted[0].start_sample, max(_span(w)[1] for w in admitted)
            neighbours = [w for w in kept if w.end_sample <= a or w.start_sample >= b]
            speaker = min(neighbours, key=lambda w: (
                max(a-w.end_sample, w.start_sample-b, 0), w.start_sample)).speaker if neighbours else local_speaker
            output.extend(GeminiWord(w.text, speaker, w.start_sample, _span(w)[1]) for w in admitted)
            restored.append({"text": [w.text for w in admitted], "start_s": a/LIVE_SAMPLE_RATE,
                             "end_s": b/LIVE_SAMPLE_RATE, "uncovered_s": samples/LIVE_SAMPLE_RATE,
                             "speaker": speaker})
        return tuple(sorted(output, key=lambda w: (w.start_sample, w.end_sample))), restored


class WebRtcSpeechDetector:
    """Mode-1, 10 ms voiced-frame fact for mic socket and batch activation."""

    def __init__(self, vad=None):
        if vad is None:
            import webrtcvad
            vad = webrtcvad.Vad(1)
        self.vad = vad

    def __call__(self, pcm16: bytes) -> bool:
        return any(self.vad.is_speech(pcm16[i:i+320], LIVE_SAMPLE_RATE)
                   for i in range(0, len(pcm16)-319, 320))


class VoicedLiveWords:
    """Open a lane's W3 socket on voice; close after 60 s without voice."""

    def __init__(self, source_factory: Callable[[], object], *, voiced_audio: Callable[[bytes], bool]):
        self.source_factory = source_factory
        self.voiced_audio = voiced_audio
        self._listener: Callable[[str, int, int, bool], None] | None = None
        self._active = None
        self._origin = 0
        self._last_voice_end = 0
        self._expected = 0
        self.ever_voiced = False

    def bind(self, listener: Callable[[str, int, int, bool], None]) -> None:
        self._listener = listener

    def push_audio(self, start_sample: int, pcm16: bytes) -> None:
        if start_sample != self._expected:
            raise ValueError("Live preview audio is not contiguous")
        end = start_sample + len(pcm16) // 2
        self._expected = end
        voiced = self.voiced_audio(pcm16)
        if voiced:
            self.ever_voiced = True
            self._last_voice_end = end
            if self._active is None:
                source = self.source_factory()
                self._origin = start_sample
                source.bind(lambda text, start, stop, final: self._emit(
                    source, text, start, stop, final))
                self._active = source
        elif self._active is not None and end - self._last_voice_end >= 60 * LIVE_SAMPLE_RATE:
            self._active.close()
            self._active = None
        if self._active is not None:
            self._active.push_audio(start_sample - self._origin, pcm16)

    def _emit(self, source, text: str, start: int, end: int, final: bool) -> None:
        if source is self._active and self._listener is not None:
            self._listener(text, self._origin + start, self._origin + end, final)

    def observe_batch_words(self, spans: Sequence[tuple[int, int]]) -> None:
        if self._active is not None:
            observe = getattr(self._active, "observe_batch_words", None)
            if callable(observe):
                observe(tuple((start - self._origin, end - self._origin)
                              for start, end in spans))

    async def finish(self) -> None:
        if self._active is not None:
            source = self._active
            await source.finish()
            self._active = None

    def close(self) -> None:
        if self._active is not None:
            self._active.close()
            self._active = None


class ConditionalMicrophoneTerminal:
    """A digital-silent mic has no terminal provider request."""

    def __init__(self, source: VoicedLiveWords, terminal):
        self.source = source
        self.terminal = terminal

    def transcribe(self, tape) -> tuple[GeminiSegment, ...]:
        return self.terminal.transcribe(tape) if self.source.ever_voiced else ()

    def transcribe_interval(self, tape, start_sample: int,
                            end_sample: int) -> tuple[GeminiSegment, ...]:
        return (self.terminal.transcribe_interval(tape, start_sample, end_sample)
                if self.source.ever_voiced else ())

    def set_witness(self, rows: Sequence[GeminiSegment]) -> None:
        self.terminal.set_witness(rows)

    def set_witness_words(self, words: Sequence[GeminiWord]) -> None:
        self.terminal.set_witness_words(words)

    @property
    def coverage_gaps(self) -> tuple[tuple[int, int], ...]:
        return self.terminal.coverage_gaps if self.source.ever_voiced else ()


class SerializedDiarizer:
    """One provider batch window in flight across both lanes of a meeting."""

    def __init__(self, diarizer, lock: threading.Lock | None = None):
        self.diarizer = diarizer
        self._lock = lock or threading.Lock()

    def diarize(self, pcm16: bytes, *, deadline: float, kind: str,
                diarize: bool = True):
        with self._lock:
            return self.diarizer.diarize(pcm16, deadline=deadline,
                                         kind=kind, diarize=diarize)

    def diarize_terminal(self, pcm16: bytes, *, deadline: float, kind: str,
                         diarize: bool = True):
        # Stop drained rolling work before the final pass. Its independent
        # chunks may use the shared HTTP client concurrently (bounded by the
        # TerminalTranscriber) without reopening live-window concurrency.
        return self.diarizer.diarize(pcm16, deadline=deadline,
                                     kind=kind, diarize=diarize)


class _LaneTape:
    """Temporary complete accepted source PCM; Account's mixed stage remains untouched."""

    def __init__(self, root: Path):
        root.mkdir(parents=True, exist_ok=True)
        self._file = tempfile.TemporaryFile(dir=root)
        self._lock = threading.RLock()
        self.sample_count = 0

    def append(self, start_sample: int, pcm16: bytes) -> None:
        with self._lock:
            if start_sample != self.sample_count:
                raise ValueError("Gemini lane tape is not contiguous")
            self._file.seek(0, 2)
            self._file.write(pcm16)
            self.sample_count += len(pcm16) // 2

    def covers(self, start_sample: int, end_sample: int) -> bool:
        return 0 <= start_sample < end_sample <= self.sample_count

    def read(self, *, start_sample: int = 0, end_sample: int | None = None) -> bytes:
        with self._lock:
            end = self.sample_count if end_sample is None else end_sample
            if not self.covers(start_sample, end):
                raise ValueError("Gemini lane tape does not cover interval")
            self._file.seek(start_sample * 2)
            data = self._file.read((end - start_sample) * 2)
            if len(data) != (end - start_sample) * 2:
                raise ValueError("Gemini lane tape short read")
            return data

    def write_wav(self, destination, *, start_sample: int = 0,
                  end_sample: int | None = None) -> int:
        end = self.sample_count if end_sample is None else end_sample
        pcm = self.read(start_sample=start_sample, end_sample=end)
        with wave.open(str(destination), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(LIVE_SAMPLE_RATE)
            wav.writeframes(pcm)
        return end - start_sample

    def close(self) -> None:
        self._file.close()


class LaneGeminiEngine:
    """Combine completed lane windows; no lane may revise behind the public frontier."""

    LANES = ("system", "microphone")

    def __init__(self, publish: Callable[[GeminiUpdate], None], *,
                 system_factory: Callable[[Callable[[GeminiUpdate], None]], object],
                 microphone_factory: Callable[[Callable[[GeminiUpdate], None]], object],
                 tape_root: Path):
        self.publish = publish
        self._lock = threading.RLock()
        self._accepted = 0
        self._base_committed = 0
        self._frontier = 0
        self._lane_frontiers = {lane: 0 for lane in self.LANES}
        self._rows: dict[str, list[GeminiSegment]] = {lane: [] for lane in self.LANES}
        self._pending_turn_bridges: list[GeminiTurnBridge] = []
        self._previews: dict[str, GeminiPreview | None] = {lane: None for lane in self.LANES}
        # Scripts this meeting has used: >= _SUSTAINED_SCRIPT committed on either lane in
        # total, or once in one preview run of either lane.
        self._committed_script_weight: dict[str, int] = {}
        self._scripts: set[str] = set()
        self.terminal_coverage_gaps: tuple[tuple[str | None, int, int], ...] = ()
        self._observations: dict[str, object] = {}
        self._tapes = {lane: _LaneTape(tape_root) for lane in self.LANES}
        self._engines = {
            "system": system_factory(lambda update: self._on_update("system", update)),
            "microphone": microphone_factory(lambda update: self._on_update("microphone", update)),
        }

    def lane_tape(self, lane: str) -> _LaneTape:
        return self._tapes[lane]

    def push_audio(self, start_sample: int, pcm16: bytes,
                   lane_pcm: tuple[tuple[str, bytes], ...] = ()) -> None:
        lanes = dict(lane_pcm) if lane_pcm else {
            "system": pcm16, "microphone": bytes(len(pcm16))}
        with self._lock:
            if start_sample != self._accepted:
                raise ValueError("Gemini lane audio is not contiguous")
            self._accepted += len(pcm16) // 2
            for lane in self.LANES:
                self._tapes[lane].append(start_sample, lanes[lane])
        # The system task is enqueued first so its timed words can guard microphone echo.
        for lane in self.LANES:
            self._engines[lane].push_audio(start_sample, lanes[lane])
        with self._lock:
            if self._accepted - self._base_committed > 45 * LIVE_SAMPLE_RATE:
                through = max(self._base_committed, self._accepted - 40 * LIVE_SAMPLE_RATE)
                self.publish(GeminiBase(through,
                    self._preview_rows(self._base_committed, through), degraded=True))
                self._base_committed = through

    def push_lanes(self, start_sample: int,
                   lane_pcm: tuple[tuple[str, bytes], ...]) -> None:
        lanes = dict(lane_pcm)
        if set(lanes) != set(self.LANES):
            raise ValueError("Gemini lane engine requires both aligned source lanes")
        self.push_audio(start_sample, bytes(len(lanes["system"])), lane_pcm)

    def _on_update(self, lane: str, update: GeminiUpdate) -> None:
        with self._lock:
            if isinstance(update, GeminiPreview):
                self._previews[lane] = update
                end = max(p.end_sample for p in self._previews.values() if p is not None)
                if end > self._base_committed:
                    self.publish(GeminiPreview(end,
                        self._preview_rows(self._base_committed, end)))
            elif isinstance(update, GeminiBase):
                # Inner engines account locally. The public base advances only when
                # both lane windows are ready, except for the bounded lag fallback.
                pass
            elif isinstance(update, GeminiRolling):
                self._rows[lane].extend(update.segments)
                for row in update.segments:
                    for script, weight, _, _ in _script_runs(row.text):
                        total = self._committed_script_weight.get(script, 0) + weight
                        self._committed_script_weight[script] = total
                        if total >= _SUSTAINED_SCRIPT:
                            self._scripts.add(script)
                self._lane_frontiers[lane] = update.end_sample
                for observation in update.observations:
                    self._observations[observation.speaker_label] = observation
                self._publish_ready()
            elif isinstance(update, GeminiRelabel):
                self._rows[lane] = [row for row in self._rows[lane]
                                    if row.end_sample <= update.start_sample
                                    or row.start_sample >= update.end_sample] + list(update.segments)
                if update.end_sample <= self._frontier:
                    rows = tuple(row for row in self._rows_in(update.start_sample, update.end_sample)
                                 if row.source_lane == lane)
                    self.publish(GeminiRelabel(update.start_sample, update.end_sample, rows))
            elif isinstance(update, GeminiTurnBridge):
                self._pending_turn_bridges.append(update)
                self._publish_turn_bridges()

    def _preview_rows(self, start: int, end: int) -> tuple[GeminiSegment, ...]:
        segments: list[GeminiSegment] = []
        for lane_name in self.LANES:
            preview = self._previews[lane_name]
            if preview is None:
                continue
            for row in preview.segments:
                if row.end_sample <= start or row.start_sample >= end:
                    continue
                current = GeminiSegment(max(row.start_sample, start),
                                        min(row.end_sample, end), row.text, None, lane_name)
                segments = [prior for prior in segments
                            if prior.source_lane != lane_name
                            or prior.end_sample <= current.start_sample
                            or prior.start_sample >= current.end_sample]
                segments.append(current)
        heard = self._rows["system"] + [row for row in segments if row.source_lane == "system"]
        heard_rows = []
        for row in segments:
            if row.source_lane == "microphone":
                row = _without_echo(row, heard, self._rows["microphone"])
            if row is not None:
                heard_rows.append(row)
        for row in heard_rows:
            self._scripts |= _sustained_scripts(row.text)
        unique = []
        for row in heard_rows:
            if row.source_lane == "microphone":
                row = _without_foreign_script(row, self._scripts)
            if row is not None:
                unique.append(row)
        return tuple(sorted(unique, key=lambda row: (row.start_sample,
                         self.LANES.index(row.source_lane))))

    def _rows_in(self, start: int, end: int) -> tuple[GeminiSegment, ...]:
        return tuple(sorted((row for lane in self.LANES for row in self._rows[lane]
                             if start <= row.start_sample < end),
                            key=lambda row: (row.start_sample,
                                             self.LANES.index(row.source_lane), row.end_sample)))

    def _publish_ready(self) -> None:
        through = min(self._lane_frontiers.values())
        if through <= self._frontier:
            return
        if through > self._base_committed:
            self.publish(GeminiBase(through, ()))
            self._base_committed = through
        rows = self._rows_in(self._frontier, through)
        visible = {row.speaker for row in rows}
        observations = tuple(value for key, value in self._observations.items() if key in visible)
        self.publish(GeminiRolling(self._frontier, through, rows, observations,
                                   revision_lanes=self.LANES))
        self._frontier = through
        self._publish_turn_bridges()

    def _publish_turn_bridges(self) -> None:
        ready = [row for row in self._pending_turn_bridges
                 if row.new_end_sample < self._frontier]
        self._pending_turn_bridges = [row for row in self._pending_turn_bridges
                                      if row.new_end_sample >= self._frontier]
        for row in ready:
            self.publish(row)

    async def drain_tail(self, deadline: float) -> bool:
        started = time.monotonic()
        for lane in self.LANES:
            remaining = deadline - (time.monotonic() - started)
            if remaining <= 0 or not await self._engines[lane].drain_tail(remaining):
                return False
        with self._lock:
            return self._frontier >= self._accepted

    async def recover_tail(self, deadline: float) -> bool:
        started = time.monotonic()
        for lane in self.LANES:
            with self._lock:
                missing = self._lane_frontiers[lane] < self._accepted
            if not missing:
                continue
            remaining = deadline - (time.monotonic() - started)
            if remaining <= 0:
                return False
            try:
                if not await self._engines[lane].recover_tail(self._tapes[lane], remaining):
                    return False
            except Exception:
                return False
        with self._lock:
            return self._frontier >= self._accepted

    async def finish(self, _mixed_tape) -> Sequence[GeminiSegment]:
        try:
            rows = []
            gaps = []
            for lane in self.LANES:
                witness = getattr(self._engines[lane], "set_terminal_witness", None)
                if callable(witness):
                    witness(self._rows[lane])
                rows.extend(await self._engines[lane].finish(self._tapes[lane]))
                gaps.extend(getattr(self._engines[lane], "terminal_coverage_gaps", ()))
            self.terminal_coverage_gaps = tuple(gaps)
            return tuple(sorted(rows, key=lambda row: (row.start_sample,
                self.LANES.index(row.source_lane), row.end_sample)))
        finally:
            for tape in self._tapes.values():
                tape.close()

    def close(self) -> None:
        for engine in self._engines.values():
            engine.close()
        for tape in self._tapes.values():
            tape.close()
