"""R5-F2 candidate applied to the product's MicrophoneWordGate as a patch inside the prototype (throwaway).

The product's `filter` (live window) and `filter_terminal` (saved pass) are re-stated here with one added fact,
`local words`, used in two places. It is built from the two lane tapes and the provider's own speaker labels:

  unexplained frame   voiced microphone audio the tab cannot explain (evidence.py: the meeting's echo return)
  sustained stretch   at least MIN_FRAMES of them in a row (holes of GAP_FRAMES bridged)
  run                 one provider speaker label's words joined across gaps of at most 0.6 s (the product's own
                      merge), taken BEFORE the level gate, so an echoed voice keeps its full length
  weight              the product's unit weights: 5 per word, 3 per CJK character (15 = three words / five characters)
  local run           a run that (1) touches a sustained stretch, (2) has at least COVERAGE of all its words on
                      unexplained audio (an echoed voice that merely overlaps local speech fails this), and
                      (3) whose words on unexplained audio weigh at least MIN_WEIGHT
  local words         the words of local runs that sit on unexplained audio

  A. level gate:  a local word the fixed -15 dB test dropped is kept.
  C. text guard:  a local word is judged like a word with a usable voice vector: dropped only as part of a
                  two-word echo phrase, not for sharing one common word with the tab ("的", "the").
  B. anchor:      a window / lane with no 2 s span keeps the local words of each local run that still weighs
                  MIN_WEIGHT after the voice and text guards, instead of dropping everything.

Everything else (voice-activity word gate, voice guard, text guard, the 2 s anchor, `local_speech_seen`) is the
product's code path, called unchanged.
"""
from __future__ import annotations

import time

import numpy as np

import evidence
from moss_transcribe_diarize.app import gemini_lane_engine as lane_engine
from moss_transcribe_diarize.app.gemini_hybrid_engine import attributed_embedding_intervals
from moss_transcribe_diarize.app.gemini_lane_engine import TextEchoGuard, _CJK, _preview_units
import unicodedata

RATE = 16000
PARAMS = {"vad_mode": 3, "quantile": .5, "margin_db": 6.0, "gap_frames": 5, "min_frames": 40, "min_weight": 15,
          "coverage": .8, "join_s": .6, "pad_frames": 20, "context_s": 30, "stride_s": 15,
          "reference": "echo_return", "rescue_level": True, "rescue_anchor": True, "local_text_phrase_only": True,
          "stress_text_guard_blind_to_cjk": False}
LOG: list[dict] = []          # one row per gate call: stretches, rescued words, added time
COUNTS = {"kept_by_local_voice_level": 0, "kept_by_local_voice_unanchored": 0, "added_ms": []}


def stretches_of(flags: np.ndarray, gap: int, minimum: int) -> list[tuple[int, int]]:
    out, start, last = [], None, None
    for index in np.flatnonzero(flags):
        if start is None:
            start = index
        elif index - last - 1 > gap:
            out.append((int(start), int(last) + 1))
            start = index
        last = index
    if start is not None:
        out.append((int(start), int(last) + 1))
    return [(a, b) for a, b in out if b - a >= minimum]


def local_audio(mic_pcm16: bytes, system_pcm16: bytes, *, whole_lane: bool) -> np.ndarray:
    """Per 10 ms frame: unexplained voiced microphone audio. A live window is one context; the saved pass walks the
    lane in the live windows' own contexts (30 s, every 15 s) so both passes judge a frame the same way."""
    mic = np.frombuffer(mic_pcm16, dtype="<i2")
    tab = np.frombuffer(system_pcm16, dtype="<i2")
    n = min(len(mic), len(tab)) // evidence.FRAME
    p = PARAMS
    def flags_of(facts):
        if p["reference"] == "fixed_-15dB":          # ablation: the level gate's fixed reference
            return evidence.fixed_level(facts)
        return evidence.unexplained(facts, evidence.echo_return_db(facts, p["quantile"]), p["margin_db"])
    if not whole_lane:
        return flags_of(evidence.Facts(mic, tab, vad_mode=p["vad_mode"]))
    flags = np.zeros(n, dtype=bool)
    stride, context = p["stride_s"] * 100, p["context_s"] * 100
    ends = list(range(stride, n + 1, stride))
    if not ends or ends[-1] < n:
        ends.append(n)
    done = 0
    for end in ends:
        lo = max(0, end - context)
        facts = evidence.Facts(mic[lo * evidence.FRAME:end * evidence.FRAME], tab[lo * evidence.FRAME:end * evidence.FRAME],
                               vad_mode=p["vad_mode"])
        part = flags_of(facts)
        flags[done:end] = part[done - lo:end - lo]
        done = end
    return flags


def label_runs(words) -> list[list]:
    """The product's attributed-span merge: one speaker label's words joined across gaps of at most 0.6 s."""
    by_label: dict[str, list] = {}
    for word in words:
        by_label.setdefault(word.speaker, []).append(word)
    runs = []
    for rows in by_label.values():
        rows.sort(key=lambda w: w.start_sample)
        end = None
        for word in rows:
            if end is not None and word.start_sample - end <= PARAMS["join_s"] * RATE:
                runs[-1].append(word)
                end = max(end, word.end_sample)
            else:
                runs.append([word])
                end = word.end_sample
    return runs


def weight(words) -> int:
    """The product's unit weights (`_repeated_units`): 5 per word, 3 per CJK-like character."""
    return sum(3 if len(unit) == 1 and unicodedata.name(unit, "").startswith(_CJK) else 5
               for word in words for unit, _, _ in _preview_units(word.text))


def local_words(flags: np.ndarray, voiced, offset_sample: int) -> tuple[dict[int, int], list, list]:
    """Local words among the voice-gated words as {id(word): run number}; the sustained stretches (absolute
    samples); a row per run that touches unexplained audio."""
    p = PARAMS
    stretches = stretches_of(flags, p["gap_frames"], p["min_frames"])
    sustained = np.zeros(len(flags), dtype=bool)
    for a, b in stretches:
        sustained[a:b] = True

    def on(mask, word) -> bool:
        middle = ((word.start_sample + word.end_sample) // 2 - offset_sample) // evidence.FRAME
        return bool(mask[max(0, middle - p["pad_frames"]):max(0, middle + p["pad_frames"] + 1)].any())
    local: dict[int, int] = {}
    rows = []
    for number, run in enumerate(label_runs(voiced)):
        on_audio = [word for word in run if on(flags, word)]
        on_sustained = weight([word for word in run if on(sustained, word)])
        is_local = (on_sustained > 0 and len(on_audio) >= p["coverage"] * len(run)
                    and weight(on_audio) >= p["min_weight"])
        if is_local:
            local.update((id(word), number) for word in on_audio)
        if on_audio:
            rows.append({"label": run[0].speaker, "start_s": round(run[0].start_sample / RATE, 2),
                         "end_s": round(run[-1].end_sample / RATE, 2), "words": len(run), "on_unexplained": len(on_audio),
                         "weight_on_sustained": on_sustained, "weight_on_unexplained": weight(on_audio),
                         "longest_stretch_frames": max((b - a for a, b in stretches if any(
                             a - p["pad_frames"] <= ((w.start_sample + w.end_sample) // 2 - offset_sample) // evidence.FRAME
                             < b + p["pad_frames"] for w in run)), default=0),
                         "local": is_local,
                         "text": " ".join(word.text for word in run)[:80]})
    return local, [(offset_sample + a * evidence.FRAME, offset_sample + b * evidence.FRAME) for a, b in stretches], rows


def _level(self, pcm16, voiced, offset_sample, local):
    """Today's level gate, plus the local words it dropped (A)."""
    today = (self.acoustic_gate.filter(pcm16, voiced, offset_sample=offset_sample)
             if self.acoustic_gate is not None else tuple(voiced))
    if not PARAMS["rescue_level"] or not local:
        return today, 0
    kept_ids = {id(word) for word in today}
    merged = tuple(word for word in voiced if id(word) in kept_ids or id(word) in local)
    return merged, len(merged) - len(today)


def _text_guard(kept, system, vectors, local):
    """The product's text guard; a local word is dropped only as part of a two-word echo phrase (C)."""
    if PARAMS["stress_text_guard_blind_to_cjk"]:
        # [stress] The provider answers the two lanes in different Chinese scripts (seen in 2 of 4 live probes):
        # worst case, no Chinese token of the tab equals the microphone's. Not a product behaviour.
        from moss_transcribe_diarize.app.gemini_provider import GeminiWord
        system = tuple(GeminiWord("#" if any(unicodedata.name(ch, "").startswith(_CJK) for ch in w.text) else w.text,
                                  w.speaker, w.start_sample, w.end_sample) for w in system)
    default = TextEchoGuard().filter_voice_aware(kept, system, vectors)
    if not PARAMS["local_text_phrase_only"] or not local:
        return default
    everyone = {word.speaker: None for word in kept}           # every label "has a vector": phrase matches only
    phrase_only = {id(word) for word in TextEchoGuard().filter_voice_aware(kept, system, everyone)}
    passed = {id(word) for word in default}
    return tuple(word for word in kept if id(word) in passed or (id(word) in local and id(word) in phrase_only))


def _evidenced(kept, local):
    """The surviving local words of each local run that still weighs MIN_WEIGHT after the guards (B)."""
    if not PARAMS["rescue_anchor"]:
        return ()
    by_run: dict[int, list] = {}
    for word in kept:
        if id(word) in local:
            by_run.setdefault(local[id(word)], []).append(word)
    keep = {id(word) for words in by_run.values() if weight(words) >= PARAMS["min_weight"] for word in words}
    return tuple(word for word in kept if id(word) in keep)


def _words(words):
    return [[w.text, w.speaker, round(w.start_sample / RATE, 2), round(w.end_sample / RATE, 2)] for w in words]


def _spans(stretches):
    return [[round(a / RATE, 2), round(b / RATE, 2)] for a, b in stretches]


def filter_live(self, pcm16, words, *, offset_sample=0):
    voiced = self.webrtc_gate.filter(pcm16, words, offset_sample=offset_sample)
    if not voiced:
        return ()
    started = time.perf_counter()
    end_sample = offset_sample + len(pcm16) // 2
    flags = local_audio(pcm16, self.acoustic_gate.system_read(offset_sample, end_sample), whole_lane=False)
    local, stretches, runs = local_words(flags, voiced, offset_sample)
    added = time.perf_counter() - started
    acoustic, by_level = _level(self, pcm16, voiced, offset_sample, local)
    through_sample = end_sample
    system = self.system_words.words_through(through_sample)
    kept = acoustic
    if self.voice_guard is not None and kept:
        vectors = self.embedding_source(pcm16, offset_sample, kept)
        kept = self.voice_guard.filter_mic(kept, vectors, through_sample=through_sample)
        after_voice = len(kept)
        kept = _text_guard(kept, system, vectors, local)
    else:
        after_voice = len(kept)
        kept = TextEchoGuard().filter(kept, system)
    after_text = len(kept)
    unanchored, by_anchor, before_anchor = 0, 0, kept
    if kept and not attributed_embedding_intervals(kept):
        rescued = _evidenced(kept, local)
        unanchored, by_anchor, kept = len(kept) - len(rescued), len(rescued), rescued
    elif kept:
        self.local_speech_seen = True
    COUNTS["kept_by_local_voice_level"] += by_level
    COUNTS["kept_by_local_voice_unanchored"] += by_anchor
    COUNTS["added_ms"].append(round(added * 1000, 2))
    probe = TextEchoGuard().filter(voiced, system)      # [probe] what the text guard alone would let through
    LOG.append({"stage": "f2_window", "offset_s": offset_sample / RATE, "seconds": len(pcm16) / 2 / RATE,
                "text_guard_alone": [len(voiced), len(probe), " ".join(w.text for w in probe)[:400]],
                "system_text": " ".join(w.text for w in system)[:300],
                "stretches": _spans(stretches), "runs": runs, "kept_by_level": by_level,
                "kept_by_anchor_evidence": by_anchor, "dropped_unanchored": unanchored,
                "before_anchor": _words(before_anchor), "kept": _words(kept), "added_ms": round(added * 1000, 2)})
    self._record(len(voiced), len(acoustic), after_voice, after_text, unanchored)
    return kept


def filter_terminal(self, mic_pcm16, words, system_words, *, system_pcm16=None):
    started = time.perf_counter()
    local, stretches, runs = (local_words(local_audio(mic_pcm16, system_pcm16, whole_lane=True), words, 0)
                              if system_pcm16 is not None else ({}, [], []))
    added = time.perf_counter() - started
    acoustic, by_level = _level(self, mic_pcm16, words, 0, local)
    kept = acoustic
    if self.voice_guard is not None and kept and system_pcm16 is not None:
        mic_vectors = self.embedding_source(mic_pcm16, 0, kept)
        system_vectors = self.embedding_source(system_pcm16, 0, system_words)
        kept = self.voice_guard.filter_terminal(kept, mic_vectors, system_words, system_vectors)
        after_voice = len(kept)
        kept = _text_guard(kept, system_words, mic_vectors, local)
    else:
        after_voice = len(kept)
        kept = TextEchoGuard().filter(kept, system_words)
    after_text = len(kept)
    withheld, by_anchor, before_anchor = 0, 0, kept
    if kept and not self.local_speech_seen:
        if attributed_embedding_intervals(kept):
            self.local_speech_seen = True
        else:
            rescued = _evidenced(kept, local)
            withheld, by_anchor, kept = len(kept) - len(rescued), len(rescued), rescued
            self.lane_withheld_words += withheld
    COUNTS["kept_by_local_voice_level"] += by_level
    COUNTS["kept_by_local_voice_unanchored"] += by_anchor
    COUNTS["added_ms"].append(round(added * 1000, 2))
    probe = TextEchoGuard().filter(words, system_words)
    LOG.append({"stage": "f2_cleanup", "seconds": len(mic_pcm16) / 2 / RATE, "stretches": _spans(stretches),
                "text_guard_alone": [len(words), len(probe), " ".join(w.text for w in probe)[:400]],
                "system_text": " ".join(w.text for w in system_words)[:300],
                "runs": runs, "kept_by_level": by_level, "kept_by_anchor_evidence": by_anchor,
                "withheld_lane": withheld, "before_anchor": _words(before_anchor), "kept": _words(kept),
                "added_ms": round(added * 1000, 2)})
    self._record(len(words), len(acoustic), after_voice, after_text, lane_withheld=withheld)
    return kept


def install(**params) -> None:
    PARAMS.update(params)
    lane_engine.MicrophoneWordGate.filter = filter_live
    lane_engine.MicrophoneWordGate.filter_terminal = filter_terminal
