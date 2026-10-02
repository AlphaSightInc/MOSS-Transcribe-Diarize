"""Throwaway frontier candidates; no production edits."""
from dataclasses import replace
import difflib
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from moss_transcribe_diarize.app import gemini_live_runtime as rt

BASE = rt._trim_committed_preview
STRIP = ' \t\r\n,.;:!?，。；：！？、'

def anchor(tail, words, earliest=True):
    # Local matches ending near the solid frontier; the old rule supplies fuzzy acceptance.
    candidates = []
    blocks = [b for b in difflib.SequenceMatcher(None, tail, words, autojunk=False).get_matching_blocks() if b.size]
    for b in blocks:
        if b.a + b.size < len(tail) - 8:
            continue
        for start in range(b.b, max(-1, b.b - 8), -1):
            cut = rt._repeated_head(tail, words[start:])
            if cut:
                candidates.append(start + cut)
    return (min(candidates) if earliest else max(candidates)) if candidates else 0

class Trim:
    def __init__(self, mode='progress'):
        self.mode = mode
        self.previous = []
    def __call__(self, segments, committed):
        baseline = BASE(segments, committed)
        by_key = {(r.source_lane, r.start_sample, r.end_sample):r for r in baseline}
        out, now = [], []
        for row in segments:
            spans = rt._preview_units(row.text)
            words = [u for u,_,_ in spans]
            kept = by_key.get((row.source_lane,row.start_sample,row.end_sample))
            cut = len(words) - len(rt._preview_units(kept.text)) if kept else len(words)
            lane_rows = [r for r in committed if r.source_lane == row.source_lane]
            frontier = max((r.end_sample for r in lane_rows), default=0)
            old = next((p for p in reversed(self.previous) if p['lane']==row.source_lane
                        and row.start_sample < p['end'] and row.end_sample >= p['end']
                        and words[:len(p['prefix'])] == p['prefix']), None)
            if self.mode in ('local','latest'):
                tail = [u for r in lane_rows for u,_,_ in rt._preview_units(r.text)]
                cut = max(cut, anchor(tail[-max(60,len(words)*5//4+8):], words, self.mode=='local'))
            elif self.mode == 'split':
                tail = [u for r in lane_rows for u,_,_ in rt._preview_units(r.text)][-max(60,len(words)*5//4+8):]
                blocks = [b for b in difflib.SequenceMatcher(None, tail, words, autojunk=False).get_matching_blocks() if b.size]
                if blocks and blocks[0].b <= 8 and sum(rt._unit_weight(u) for u in words[blocks[0].b:blocks[0].b+blocks[0].size]) >= 25:
                    cut = max(cut, anchor(tail, words))
            elif old:
                floor = len(old['prefix'])
                cut = max(cut, floor)
                if self.mode == 'progress' and frontier > old['frontier']:
                    tail = [u for r in lane_rows if r.end_sample > old['frontier'] for u,_,_ in rt._preview_units(r.text)]
                    extra = anchor(tail, words[floor:])
                    if extra:
                        cut = max(cut, floor + extra)
            text = row.text[spans[cut-1][2]:].lstrip(STRIP) if cut else row.text
            if text: out.append(replace(row,text=text))
            now.append(dict(lane=row.source_lane, end=row.end_sample, frontier=frontier, prefix=words[:cut]))
        self.previous = now
        return tuple(out)

class RememberedTrim:
    """Never re-align the shortened suffix: only retain an already-witnessed cut."""
    def __init__(self): self.cuts=[]
    def trim(self, segments, committed, degraded=False):
        kept=BASE(segments,committed)
        by_key={(r.source_lane,r.start_sample,r.end_sample):r for r in kept}
        out,now=[],[]
        for row in segments:
            spans=rt._preview_units(row.text)
            units=[u for u,_,_ in spans]
            shown=by_key.get((row.source_lane,row.start_sample,row.end_sample))
            cut=len(units)-len(rt._preview_units(shown.text)) if shown else len(units)
            prior=[(end,prefix) for lane,end,prefix in self.cuts
                   if lane==row.source_lane and row.start_sample < end
                   and (degraded or row.end_sample >= end)
                   and units[:len(prefix)]==prefix]
            cut=max([cut]+[len(prefix) for end,prefix in prior])
            text=row.text[spans[cut-1][2]:].lstrip(STRIP) if cut else row.text
            if text:out.append(replace(row,text=text))
            end=max([row.end_sample]+[end for end,prefix in prior])
            now.append((row.source_lane,end,units if degraded else units[:cut]))
        self.cuts=now
        return tuple(out)
