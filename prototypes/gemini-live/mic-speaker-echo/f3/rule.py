"""Rule H — the candidate production rule, as pure functions (the only part meant to be lifted out).

A hole is a stretch of one lane's time line in which the whole-recording answer has no word. A live committed
word that lies in a hole is the witness that the hole is an omission, not silence. Consecutive witnesses in one
hole form a run; a run with more than one provider time step (0.1 s) of uncovered time is inserted into the
whole-recording words, labelled with the speaker of the nearer neighbouring whole-recording word. Every
whole-recording word is returned unchanged.

Time decides. Text is compared in one place only: a live word that a whole-recording word covers by exactly one
time step is the same word heard twice (timing jitter) when the two texts are equal, and a witness otherwise.
"""
from __future__ import annotations

import unicodedata
from bisect import bisect_left, bisect_right
from typing import NamedTuple, Sequence

S = 16000
STEP = S // 10                       # the provider's word times move in 0.1 s steps
MIN_RUN_SAMPLES = STEP * 3 // 2      # more than one time step of uncovered live speech (measured: NOTES.md)

VARIANT = {"edge": "text"}           # prototype switch for the sweep: "text" (rule as proposed) | "keep" | "drop"


class Word(NamedTuple):   # same fields and order as gemini_provider.GeminiWord
    text: str
    speaker: str
    start_sample: int
    end_sample: int


def _span(word) -> tuple[int, int]:
    """A zero-length provider word stands for one time step."""
    return word.start_sample, max(word.end_sample, word.start_sample + STEP)


def _bare(text: str) -> str:
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _number(text: str):
    """The value of a word that is one number: digits, or one numeral character of any script ("10", "十")."""
    bare = _bare(text)
    if bare.isdigit() and bare.isascii():
        return float(bare)
    return unicodedata.numeric(bare, None) if len(bare) == 1 else None


def _same(a: str, b: str) -> bool:
    """The same word written the same way, or the same number written two ways."""
    if _bare(a) == _bare(b):
        return True
    value = _number(a)
    return value is not None and value == _number(b)


def one_owner(witness: Sequence, frontiers: Sequence[int]) -> list:
    """Live words in commit order, without the words a later window restated across its frontier.

    A word committed by a later window that starts before that window's frontier was already half-heard by the
    window before; what that window wrote for the same audio (a word overlapping it, or the same text ending
    within one time step of its start) is the truncated copy and is not a witness. `frontiers[i]` is the
    frontier that was in force when `witness[i]` was committed (the end of the previous window).
    """
    kept: list = []
    for word, frontier in zip(witness, frontiers):
        if word.start_sample < frontier:
            kept = [p for p in kept if not (p.end_sample <= frontier and (
                p.end_sample > word.start_sample
                or (p.end_sample > word.start_sample - STEP and _same(p.text, word.text))))]
        kept.append(word)
    return kept


def uncovered_runs(words: Sequence, witness: Sequence, *,
                   skip: Sequence[tuple[int, int]] = ()) -> list[tuple[list, int]]:
    """Runs of consecutive live words lying in one hole of the whole-recording words, with their uncovered samples.

    `skip`: intervals another rule already owns (the existing >= 10 s coverage fallback carries live rows there).
    """
    by_start = sorted(words, key=lambda w: _span(w))
    spans = [_span(w) for w in by_start]
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    starts = [a for a, _ in merged]

    def covered(a: int, b: int) -> int:
        total, i = 0, max(0, bisect_right(starts, a) - 1)
        while i < len(merged) and merged[i][0] < b:
            total += max(0, min(b, merged[i][1]) - max(a, merged[i][0]))
            i += 1
        return total

    runs: list[list] = []          # [live word, uncovered samples] lists, one per hole
    previous = None
    for word in sorted(witness, key=lambda w: (w.start_sample, w.end_sample)):
        a, b = _span(word)
        inside = covered(a, b)
        if (not word.text.strip() or inside > STEP or inside >= b - a
                or any(lo < b and hi > a for lo, hi in skip)):
            previous = None
            continue
        hole = bisect_right(starts, a)         # whole-recording stretches that begin at or before the word
        if previous == hole:
            runs[-1].append((word, (b - a) - inside))
        else:
            runs.append([(word, (b - a) - inside)])
        previous = hole
    if VARIANT["edge"] == "text":
        # Timing jitter: the word at the edge of a run is the same word as the whole-recording word right next
        # to it (same text, within one time step) heard one step apart. It is not a witness.
        firsts = [c for c, _ in spans]

        def beside(word, after: bool) -> bool:
            a, b = _span(word)
            if after:      # a whole-recording word starting within one step of the live word's end
                lo, hi = bisect_left(firsts, b - STEP), bisect_right(firsts, b + STEP)
                return any(_same(by_start[i].text, word.text) for i in range(lo, hi))
            lo, hi = bisect_left(firsts, a - 60 * STEP), bisect_right(firsts, a + STEP)   # ... ending within one step of its start
            return any(abs(spans[i][1] - a) <= STEP and _same(by_start[i].text, word.text) for i in range(lo, hi))
        for run in runs:
            while run and beside(run[-1][0], True):
                run.pop()
            while run and beside(run[0][0], False):
                run.pop(0)
    elif VARIANT["edge"] == "drop":
        runs = [[(w, n) for w, n in run if 2 * n > _span(w)[1] - _span(w)[0]] for run in runs]
    return [([w for w, _ in run], sum(n for _, n in run)) for run in runs if run]


def fill_holes(words: Sequence, witness: Sequence, *, min_run_samples: int = MIN_RUN_SAMPLES,
               skip: Sequence[tuple[int, int]] = ()) -> tuple[tuple, list[dict]]:
    """Whole-recording words with every witnessed run of at least `min_run_samples` inserted.

    Returns (words, restored); `restored` lists what was inserted (for the diagnostics counter).
    Kept words are returned unchanged and in their original order.
    """
    words = list(words)
    if not words or not witness:
        return tuple(words), []
    make = type(words[0])
    restored: list[dict] = []
    for run, samples in uncovered_runs(words, witness, skip=skip):
        if samples < min_run_samples:
            continue
        a, b = run[0].start_sample, max(_span(w)[1] for w in run)
        middle = sum(_span(run[0])) // 2
        left = max((i for i, w in enumerate(words) if w.start_sample <= middle), default=None)   # answer order
        right = min((i for i, w in enumerate(words) if w.start_sample > middle), default=None)
        left_gap = a - words[left].end_sample if left is not None else None
        right_gap = words[right].start_sample - b if right is not None else None
        nearer = left if right is None or (left is not None and left_gap <= right_gap) else right
        speaker = words[nearer].speaker
        at = left + 1 if left is not None else 0
        words[at:at] = [make(w.text, speaker, w.start_sample, _span(w)[1]) for w in run]
        restored.append({"start_s": a / S, "end_s": b / S, "uncovered_s": samples / S,
                         "text": [w.text for w in run], "speaker": speaker,
                         "left_gap_s": None if left_gap is None else left_gap / S,
                         "right_gap_s": None if right_gap is None else right_gap / S})
    return tuple(words), restored
