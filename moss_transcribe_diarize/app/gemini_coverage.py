"""Find wordless stretches witnessed by a different transcript pass."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass, replace
from itertools import accumulate
import unicodedata
from typing import Sequence

from .gemini_live_runtime import _preview_units
from .live_span_bounds import LIVE_SAMPLE_RATE


def missing_witness_intervals(
    witness: Sequence[tuple[int, int]], result: Sequence[tuple[int, int]], *,
    minimum_samples: int = 10 * LIVE_SAMPLE_RATE,
) -> tuple[tuple[int, int], ...]:
    """Return witnessed intervals absent from result (all if result is empty)."""
    merged: list[list[int]] = []
    for start, end in sorted(witness):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if not result:
        return tuple((start, end) for start, end in merged)
    gaps = []
    for start, end in merged:
        cursor = start
        for lo, hi in sorted(result):
            if hi <= cursor or lo >= end:
                continue
            if lo - cursor >= minimum_samples:
                gaps.append((cursor, lo))
            cursor = max(cursor, hi)
        if end - cursor >= minimum_samples:
            gaps.append((cursor, end))
    return tuple(gaps)


STEP = LIVE_SAMPLE_RATE // 10
MIN_RUN_SAMPLES = STEP * 3 // 2
SHIFT_NEIGHBOUR_SAMPLES = LIVE_SAMPLE_RATE
SHIFT_NEIGHBOUR_UNITS = 12


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


def _already_beside(run, words, spans, starts) -> bool:
    """A whole run repeated just beside its hole is a time shift, not an omission."""
    units = [unit for word, _ in run for unit, _, _ in _preview_units(word.text)]
    if not units or len(units) > SHIFT_NEIGHBOUR_UNITS:
        return False
    a, b = _span(run[0][0])[0], _span(run[-1][0])[1]
    left = []
    for i in range(bisect_right(starts, a + STEP) - 1, -1, -1):
        if spans[i][1] < a - SHIFT_NEIGHBOUR_SAMPLES:
            break
        if spans[i][1] <= a + STEP:
            left[:0] = [unit for unit, _, _ in _preview_units(words[i].text)]
            if len(left) >= SHIFT_NEIGHBOUR_UNITS:
                break
    right = []
    for i in range(bisect_left(starts, b - STEP), len(words)):
        if spans[i][0] > b + SHIFT_NEIGHBOUR_SAMPLES:
            break
        right.extend(unit for unit, _, _ in _preview_units(words[i].text))
        if len(right) >= SHIFT_NEIGHBOUR_UNITS:
            break
    left, right = left[-SHIFT_NEIGHBOUR_UNITS:], right[:SHIFT_NEIGHBOUR_UNITS]
    return any(len(edge) == len(units) and all(_same(x, y) for x, y in zip(units, edge))
               for edge in (left[-len(units):], right[:len(units)]))


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
    return [([w for w, _ in run], sum(n for _, n in run)) for run in runs
            if run and not _already_beside(run, by_start, spans, firsts)]


def restore_witnessed_words(words: Sequence, witness: Sequence, *, min_run_samples: int = MIN_RUN_SAMPLES,
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
        restored.append({"start_s": a / LIVE_SAMPLE_RATE, "end_s": b / LIVE_SAMPLE_RATE, "uncovered_s": samples / LIVE_SAMPLE_RATE,
                         "text": [w.text for w in run], "speaker": speaker,
                         "left_gap_s": None if left_gap is None else left_gap / LIVE_SAMPLE_RATE,
                         "right_gap_s": None if right_gap is None else right_gap / LIVE_SAMPLE_RATE})
    return tuple(words), restored


def drop_restated(witness: Sequence, committed: Sequence, frontier: int) -> list:
    """Replace truncated frontier copies with the later window's committed words."""
    words = list(witness) + list(committed)
    return one_owner(words, [0]*len(witness) + [frontier]*len(committed))


@dataclass(frozen=True, slots=True)
class WitnessWord:
    text: str
    speaker: str
    start_sample: int
    end_sample: int
    source_partition: str


def source_partitions(witness: Sequence, previous: Sequence, words: Sequence, request: int):
    """Continue source evidence through two re-heard words, splitting ambiguous old groups."""
    prior = sorted(previous, key=lambda w: w.start_sample)
    starts = [w.start_sample for w in prior]
    pairs = defaultdict(set)
    matches = defaultdict(set)
    qualified = set()
    continuing = defaultdict(set)
    for word in words:
        for old in prior[bisect_left(starts, word.start_sample-STEP):bisect_right(starts, word.start_sample+STEP)]:
            if abs(old.end_sample-word.end_sample) <= STEP and _same(old.text, word.text):
                matches[word.speaker].add(old.source_partition)
                pairs[(word.speaker, old.source_partition)].add((
                    (old.text, old.start_sample, old.end_sample),
                    (word.text, word.start_sample, word.end_sample)))
    for (label, partition), heard in pairs.items():
        if len({old for old, _ in heard}) < 2 or len({new for _, new in heard}) < 2:
            continue
        qualified.add((label, partition))
        for (text, a, b), _ in heard:
            continuing[(text, a, b, partition)].add(label)
    reverse = defaultdict(set)
    for label, partitions in matches.items():
        for partition in partitions:
            reverse[partition].add(label)
    mapping = {}
    for label in dict.fromkeys(w.speaker for w in words):
        partitions = matches[label]
        if (len(partitions) == 1 and len(reverse[next(iter(partitions))]) == 1
                and (label, next(iter(partitions))) in qualified):
            mapping[label] = next(iter(partitions))
        else:
            mapping[label] = f'source-{request}-{label}'
    updated = []
    for old in witness:
        labels = continuing.get((old.text, old.start_sample, old.end_sample, old.source_partition), ())
        if len(labels) == 1:
            label = next(iter(labels))
            if len(matches[label]) == 1:
                old = replace(old, source_partition=mapping[label])
        updated.append(old)
    heard = {(text,a,b) for text,a,b,_ in continuing}
    context = [w for w in updated if (w.text,w.start_sample,w.end_sample) in heard]
    return updated, mapping, context


def relabel_witnesses(witness: Sequence, rows: Sequence) -> list:
    """Published identity changes with a published row; source evidence never changes here."""
    updated = []
    for word in witness:
        overlaps = [(min(word.end_sample, row.end_sample)-max(word.start_sample,row.start_sample),row.speaker)
                    for row in rows]
        samples, speaker = max(overlaps, key=lambda pair: pair[0], default=(0,None))
        updated.append(replace(word,speaker=speaker or f'unassigned-{word.source_partition}') if samples>0 else word)
    return updated


def restore_system_witnessed_words(words: Sequence, witness: Sequence, *, skip=()):
    """Restore H words, bridging each published identity to its nearest kept final label.

    A published speaker absent from all kept words gets one separate final label; the
    existing final-to-live overlap mapping can then preserve its name. Source partitions
    govern microphone evidence only. Kept words never change or borrow restored evidence.
    """
    filled, restored = restore_witnessed_words(words, witness, skip=skip)
    if not restored:
        return filled, restored
    kept = sorted(words, key=lambda w: _span(w))
    starts = [w.start_sample for w in kept]
    ends = list(accumulate((_span(w)[1] for w in kept), max))
    bridge = defaultdict(dict)
    for live in witness:
        if live.speaker.startswith('unassigned-'):
            continue
        a, b = _span(live)
        for index in range(bisect_right(ends, a), bisect_left(starts, b)):
            word = kept[index]
            if min(b, _span(word)[1]) > max(a, word.start_sample):
                bridge[live.speaker][index] = word
    indexed = {}
    for speaker, candidates in bridge.items():
        items = sorted(candidates.items())
        positions = [word.start_sample for _, word in items]
        max_ends, owners = [], []
        for i, (_, word) in enumerate(items):
            end = _span(word)[1]
            if not max_ends or end > max_ends[-1]:
                max_ends.append(end)
                owners.append(i)
            else:
                max_ends.append(max_ends[-1])
                owners.append(owners[-1])
        indexed[speaker] = (items, positions, max_ends, owners)
    live_by_word = defaultdict(deque)
    for w in sorted(witness, key=lambda w: (w.start_sample, w.end_sample)):
        live_by_word[(w.text, w.start_sample, _span(w)[1])].append(w.speaker)
    kept_ids = {id(w) for w in words}
    make = type(words[0])
    output = []
    labels = {}
    inserted = []
    for word in filled:
        if id(word) in kept_ids:
            output.append(word)
            continue
        live = live_by_word[(word.text, word.start_sample, word.end_sample)].popleft()
        speaker = word.speaker
        if not live.startswith('unassigned-'):
            if live in indexed:
                items, positions, max_ends, owners = indexed[live]
                overlap = bisect_left(max_ends, word.start_sample)
                if overlap < len(items) and positions[overlap] <= word.end_sample:
                    nearest = overlap
                else:
                    right = bisect_right(positions, word.start_sample)
                    choices = ([owners[right-1]] if right else []) + ([right] if right < len(items) else [])
                    nearest = min(choices, key=lambda i: (
                        max(0, word.start_sample - _span(items[i][1])[1],
                            items[i][1].start_sample - word.end_sample), items[i][0]))
                speaker = items[nearest][1].speaker
            else:
                speaker = f'witness-{live}'
        output.append(make(word.text, speaker, word.start_sample, word.end_sample))
        inserted.append(word)
        labels[id(word)] = speaker
    inserted.sort(key=lambda w: (w.start_sample, w.end_sample))
    inserted_starts = [w.start_sample for w in inserted]
    for run in restored:
        lo = bisect_left(inserted_starts, round(run['start_s']*LIVE_SAMPLE_RATE))
        hi = bisect_left(inserted_starts, round(run['end_s']*LIVE_SAMPLE_RATE))
        run['speakers'] = [labels[id(w)] for w in inserted[lo:hi]]
        run['speaker'] = run['speakers'][0]
    return tuple(output), restored
