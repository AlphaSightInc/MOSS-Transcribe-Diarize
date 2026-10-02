"""Throwaway bounded original-turn snapshot reducer; lifted only after measurement."""
from collections import deque
from dataclasses import dataclass, field, replace
from moss_transcribe_diarize.app.gemini_live_runtime import _preview_units


@dataclass
class TurnSnapshot:
    pending: deque = field(default_factory=lambda: deque(maxlen=64))
    snapshot: tuple | None = None
    lost_through: int = -1


class PreviewSnapshots:
    def __init__(self):
        self.turns = {}
        self.clocks = {}
        self.frontiers = {}
        self.max_pending = 0
        self.overflows = 0

    def advance(self, solid):
        lanes = set(self.frontiers) | {r.source_lane for r in solid}
        for lane in lanes:
            through = max((r.end_sample for r in solid if r.source_lane == lane), default=0)
            if through < self.frontiers.get(lane, 0):
                for key in list(self.turns):
                    if key[0] == lane:
                        del self.turns[key]
            self.frontiers[lane] = through
            for key, turn in self.turns.items():
                if key[0] != lane:
                    continue
                eligible = [p for p in turn.pending if p[0] <= through]
                if eligible:
                    turn.snapshot = eligible[-1]
                elif turn.snapshot is not None and turn.lost_through > turn.snapshot[0]:
                    turn.snapshot = None
                turn.pending = deque((p for p in turn.pending if p[0] > through), maxlen=64)

    def publication(self, origins, clocks, finished=()):
        finished = set(finished)
        for lane, clock in clocks:
            if clock <= self.clocks.get(lane, -1):
                continue
            self.clocks[lane] = clock
            rows = [r for r in origins if r.source_lane == lane]
            keys = {(lane, r.start_sample) for r in rows}
            for key in list(self.turns):
                if key[0] == lane and key not in keys:
                    del self.turns[key]
            for row in rows:
                key = (lane, row.start_sample)
                if sum(r.start_sample == row.start_sample for r in rows) != 1:
                    self.turns.pop(key, None)
                    continue
                if key in finished and key not in self.turns:
                    continue
                turn = self.turns.setdefault(key, TurnSnapshot())
                units = tuple(u for u, _, _ in _preview_units(row.text))
                through = self.frontiers.get(lane, 0)
                if clock <= through:
                    turn.snapshot = clock, units
                else:
                    if len(turn.pending) == turn.pending.maxlen:
                        turn.lost_through = turn.pending[0][0]
                        self.overflows += 1
                    turn.pending.append((clock, units))
                    self.max_pending = max(self.max_pending, len(turn.pending))

    def cuts(self, segments, origins):
        cuts = []
        for row in segments:
            matches = [r for r in origins if r.source_lane == row.source_lane
                       and r.text == row.text and r.start_sample <= row.start_sample
                       and r.end_sample >= row.end_sample]
            if len(matches) != 1:
                cuts.append(0)
                continue
            origin = matches[0]
            if sum(r.source_lane == origin.source_lane and r.start_sample == origin.start_sample
                   for r in origins) != 1:
                cuts.append(0)
                continue
            turn = self.turns.get((row.source_lane, origin.start_sample))
            snapshot = turn.snapshot if turn is not None else None
            if snapshot is None or snapshot[0] > self.frontiers.get(row.source_lane, 0):
                cuts.append(0)
                continue
            units = [u for u, _, _ in _preview_units(row.text)]
            cuts.append(next((i for i, (a, b) in enumerate(zip(snapshot[1], units)) if a != b),
                             min(len(snapshot[1]), len(units))))
        return cuts

    def finish(self, keys):
        for key in keys:
            self.turns.pop(key, None)

    def reset(self, lane):
        for key in list(self.turns):
            if key[0] == lane:
                del self.turns[key]

    def clear(self):
        self.turns.clear()
        self.clocks.clear()
        self.frontiers.clear()

    def state(self):
        return dict(clocks=dict(self.clocks), frontiers=dict(self.frontiers), max_pending=self.max_pending,
                    overflows=self.overflows, turns=[dict(lane=k[0], start=k[1],
                    snapshot=v.snapshot, pending=list(v.pending), lost_through=v.lost_through)
                    for k,v in self.turns.items()])


def apply_time_cuts(segments, text_rows, cuts):
    """Leave the text rule byte-identical; remove only a longer witnessed snapshot prefix."""
    shown, at = [], 0
    for row, cut in zip(segments, cuts):
        text_row = None
        if at < len(text_rows):
            current = text_rows[at]
            if ((current.start_sample, current.end_sample, current.source_lane) ==
                    (row.start_sample, row.end_sample, row.source_lane)
                    and row.text.endswith(current.text)):
                text_row = current
                at += 1
        if text_row is None:
            continue
        if not cut:
            shown.append(text_row)
            continue
        spans = _preview_units(row.text)
        boundary = len(row.text) - len(text_row.text)
        text_cut = sum(end <= boundary for _, _, end in spans)
        if cut <= text_cut:
            shown.append(text_row)
            continue
        text = row.text[spans[cut-1][2]:].lstrip(' \t\r\n,.;:!?，。；：！？、')
        if text:
            shown.append(replace(row, text=text))
    return tuple(shown)
