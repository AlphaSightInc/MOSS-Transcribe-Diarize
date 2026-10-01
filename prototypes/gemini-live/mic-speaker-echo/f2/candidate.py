"""R5-F2 candidate applied to the product's MicrophoneWordGate as a patch inside the prototype (throwaway).

The product's `filter` (live window) and `filter_terminal` (saved pass) are re-stated here with two additions,
both built on one fact - `local stretches`: contiguous voiced microphone audio the tab cannot explain
(evidence.py), at least MIN_FRAMES long:

  A. level gate:  a word the fixed -15 dB test dropped is kept when it lies in a local stretch.
  B. anchor:      a window / lane with no 2 s span keeps the words of local stretches that hold at least
                  MIN_WORDS surviving words, instead of dropping everything.

Everything else (voice-activity word gate, voice guard, text guard, the 2 s anchor, `local_speech_seen`) is the
product's code path, called unchanged.
"""
from __future__ import annotations

import time

import numpy as np

import evidence
from moss_transcribe_diarize.app import gemini_lane_engine as lane_engine
from moss_transcribe_diarize.app.gemini_hybrid_engine import attributed_embedding_intervals
from moss_transcribe_diarize.app.gemini_lane_engine import TextEchoGuard

RATE = 16000
PARAMS = {"quantile": .5, "margin_db": 6.0, "gap_frames": 5, "min_frames": 40, "min_words": 3,
          "pad_frames": 20, "context_s": 30, "stride_s": 15, "rescue_level": True, "rescue_anchor": True}
LOG: list[dict] = []          # one row per gate call: stretches, rescued words, added time
COUNTS = {"kept_by_local_voice_level": 0, "kept_by_local_voice_unanchored": 0, "added_ms": []}


def _stretches(flags: np.ndarray, gap: int, minimum: int) -> list[tuple[int, int]]:
    out, start, last = [], None, None
    for index in np.flatnonzero(flags):
        if start is None:
            start = index
        elif index - last - 1 > gap:
            out.append((start, last + 1))
            start = index
        last = index
    if start is not None:
        out.append((start, last + 1))
    return [(a, b) for a, b in out if b - a >= minimum]


def local_stretches(mic_pcm16: bytes, system_pcm16: bytes, offset_sample: int, *, whole_lane: bool) -> list[tuple[int, int]]:
    """Absolute (start_sample, end_sample) of local stretches. A live window is one context; the saved pass walks
    the lane in the live windows' own contexts (30 s, every 15 s) so both passes judge a frame the same way."""
    mic = np.frombuffer(mic_pcm16, dtype="<i2")
    tab = np.frombuffer(system_pcm16, dtype="<i2")
    n = min(len(mic), len(tab)) // evidence.FRAME
    p = PARAMS
    if not whole_lane:
        facts = evidence.Facts(mic, tab)
        flags = evidence.unexplained(facts, evidence.echo_return_db(facts, p["quantile"]), p["margin_db"])
    else:
        flags = np.zeros(n, dtype=bool)
        stride, context = p["stride_s"] * 100, p["context_s"] * 100
        ends = list(range(stride, n + 1, stride))
        if not ends or ends[-1] < n:
            ends.append(n)
        done = 0
        for end in ends:
            lo = max(0, end - context)
            facts = evidence.Facts(mic[lo * evidence.FRAME:end * evidence.FRAME], tab[lo * evidence.FRAME:end * evidence.FRAME])
            part = evidence.unexplained(facts, evidence.echo_return_db(facts, p["quantile"]), p["margin_db"])
            flags[done:end] = part[done - lo:end - lo]
            done = end
    return [(offset_sample + a * evidence.FRAME, offset_sample + b * evidence.FRAME)
            for a, b in _stretches(flags, p["gap_frames"], p["min_frames"])]


def _stretch_of(word, stretches) -> int | None:
    middle = (word.start_sample + word.end_sample) // 2
    pad = PARAMS["pad_frames"] * evidence.FRAME
    for index, (start, end) in enumerate(stretches):
        if start - pad <= middle < end + pad:
            return index
    return None


def _level(self, pcm16, voiced, offset_sample, stretches):
    """Today's level gate, plus words lying in a local stretch (A)."""
    today = (self.acoustic_gate.filter(pcm16, voiced, offset_sample=offset_sample)
             if self.acoustic_gate is not None else tuple(voiced))
    if not PARAMS["rescue_level"] or not stretches:
        return today, 0
    kept_ids = {id(word) for word in today}
    merged = tuple(word for word in voiced if id(word) in kept_ids or _stretch_of(word, stretches) is not None)
    return merged, len(merged) - len(today)


def _evidenced(kept, stretches):
    """Words of local stretches that hold at least MIN_WORDS surviving words (B)."""
    if not PARAMS["rescue_anchor"]:
        return ()
    by_stretch: dict[int, list] = {}
    for word in kept:
        index = _stretch_of(word, stretches)
        if index is not None:
            by_stretch.setdefault(index, []).append(word)
    keep = {id(word) for words in by_stretch.values() if len(words) >= PARAMS["min_words"] for word in words}
    return tuple(word for word in kept if id(word) in keep)


def _words(words):
    return [[w.text, w.speaker, round(w.start_sample / RATE, 2), round(w.end_sample / RATE, 2)] for w in words]


def filter_live(self, pcm16, words, *, offset_sample=0):
    voiced = self.webrtc_gate.filter(pcm16, words, offset_sample=offset_sample)
    if not voiced:
        return ()
    started = time.perf_counter()
    end_sample = offset_sample + len(pcm16) // 2
    stretches = local_stretches(pcm16, self.acoustic_gate.system_read(offset_sample, end_sample), offset_sample,
                                whole_lane=False)
    added = time.perf_counter() - started
    acoustic, by_level = _level(self, pcm16, voiced, offset_sample, stretches)
    through_sample = end_sample
    system = self.system_words.words_through(through_sample)
    kept = acoustic
    if self.voice_guard is not None and kept:
        vectors = self.embedding_source(pcm16, offset_sample, kept)
        kept = self.voice_guard.filter_mic(kept, vectors, through_sample=through_sample)
        after_voice = len(kept)
        kept = TextEchoGuard().filter_voice_aware(kept, system, vectors)
    else:
        after_voice = len(kept)
        kept = TextEchoGuard().filter(kept, system)
    after_text = len(kept)
    unanchored, by_anchor, before_anchor = 0, 0, kept
    if kept and not attributed_embedding_intervals(kept):
        started = time.perf_counter()
        rescued = _evidenced(kept, stretches)
        added += time.perf_counter() - started
        unanchored, by_anchor, kept = len(kept) - len(rescued), len(rescued), rescued
    elif kept:
        self.local_speech_seen = True
    COUNTS["kept_by_local_voice_level"] += by_level
    COUNTS["kept_by_local_voice_unanchored"] += by_anchor
    COUNTS["added_ms"].append(round(added * 1000, 2))
    LOG.append({"stage": "f2_window", "offset_s": offset_sample / RATE, "seconds": len(pcm16) / 2 / RATE,
                "stretches": [[round(a / RATE, 2), round(b / RATE, 2)] for a, b in stretches],
                "kept_by_level": by_level, "kept_by_anchor_evidence": by_anchor, "dropped_unanchored": unanchored,
                "before_anchor": _words(before_anchor), "kept": _words(kept), "added_ms": round(added * 1000, 2)})
    self._record(len(voiced), len(acoustic), after_voice, after_text, unanchored)
    return kept


def filter_terminal(self, mic_pcm16, words, system_words, *, system_pcm16=None):
    started = time.perf_counter()
    stretches = (local_stretches(mic_pcm16, system_pcm16, 0, whole_lane=True) if system_pcm16 is not None else [])
    added = time.perf_counter() - started
    acoustic, by_level = _level(self, mic_pcm16, words, 0, stretches)
    kept = acoustic
    if self.voice_guard is not None and kept and system_pcm16 is not None:
        mic_vectors = self.embedding_source(mic_pcm16, 0, kept)
        system_vectors = self.embedding_source(system_pcm16, 0, system_words)
        kept = self.voice_guard.filter_terminal(kept, mic_vectors, system_words, system_vectors)
        after_voice = len(kept)
        kept = TextEchoGuard().filter_voice_aware(kept, system_words, mic_vectors)
    else:
        after_voice = len(kept)
        kept = TextEchoGuard().filter(kept, system_words)
    after_text = len(kept)
    withheld, by_anchor, before_anchor = 0, 0, kept
    if kept and not self.local_speech_seen:
        if attributed_embedding_intervals(kept):
            self.local_speech_seen = True
        else:
            rescued = _evidenced(kept, stretches)
            withheld, by_anchor, kept = len(kept) - len(rescued), len(rescued), rescued
            self.lane_withheld_words += withheld
    COUNTS["kept_by_local_voice_level"] += by_level
    COUNTS["kept_by_local_voice_unanchored"] += by_anchor
    LOG.append({"stage": "f2_cleanup", "seconds": len(mic_pcm16) / 2 / RATE,
                "stretches": [[round(a / RATE, 2), round(b / RATE, 2)] for a, b in stretches],
                "kept_by_level": by_level, "kept_by_anchor_evidence": by_anchor, "withheld_lane": withheld,
                "before_anchor": _words(before_anchor), "kept": _words(kept), "added_ms": round(added * 1000, 2)})
    self._record(len(words), len(acoustic), after_voice, after_text, lane_withheld=withheld)
    return kept


def install(**params) -> None:
    PARAMS.update(params)
    lane_engine.MicrophoneWordGate.filter = filter_live
    lane_engine.MicrophoneWordGate.filter_terminal = filter_terminal
