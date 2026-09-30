"""Candidate suppression rules applied after the production mic chain (throwaway)."""
from __future__ import annotations

from chain import RATE


def runs(words, gap_s=1.0):
    words = sorted(words, key=lambda w: w.start_sample)
    out, cur = [], []
    for w in words:
        if cur and w.start_sample - cur[-1].end_sample > gap_s * RATE:
            out.append(cur)
            cur = []
        cur.append(w)
    if cur:
        out.append(cur)
    return out


def anchored(anchor_s, min_words=1, gap_s=1.0):
    """Keep a window's words only when one of its word runs spans >= anchor_s (and >= min_words)."""
    def rule(words, pcm, span, kind):
        rs = runs(words, gap_s)
        ok = any((r[-1].end_sample - r[0].start_sample) >= anchor_s * RATE and len(r) >= min_words for r in rs)
        return tuple(words) if ok else ()
    return rule


def run_level(anchor_s, gap_s=1.0):
    """Keep only word runs that themselves span >= anchor_s."""
    def rule(words, pcm, span, kind):
        return tuple(w for r in runs(words, gap_s)
                     if (r[-1].end_sample - r[0].start_sample) >= anchor_s * RATE for w in r)
    return rule
