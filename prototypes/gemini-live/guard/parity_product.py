"""Zero-send replay of P4 cached windows through the product registry.

Run from the WP1 worktree root with PYTHONDONTWRITEBYTECODE=1:
  ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python prototypes/gemini-live/guard/parity_product.py
"""
from __future__ import annotations

import json
from pathlib import Path

import run as guard
from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
from moss_transcribe_diarize.app.gemini_provider import GeminiWord

S = 16_000
CASES = ("A5bill", "A3bill", "A3long60", "A0bill", "A0long60", "A2bill", "A2long60")
EXPECTED = {row["case"]: row["T0.46M0.2"] for row in json.loads(
    (guard.OUT / "sweep.json").read_text())}


class ProductAdapter:
    """Adapt only prototype word units and ID spelling to the product public method."""

    def __init__(self, *, min_overlap_s, embedding_threshold, within_window_threshold,
                 reuse_overlap, birth_min_s):
        assert not reuse_overlap
        self.product = ContinuityRegistry(min_overlap_seconds=min_overlap_s,
                                          embedding_threshold=embedding_threshold,
                                          within_window_threshold=within_window_threshold,
                                          birth_min_seconds=birth_min_s)
        self.births = self.merges = self.local_merges = self.overlap_reuses = 0

    def observe_window(self, start, words, embeddings=None):
        absolute = tuple(GeminiWord(w["text"], w["speaker"],
                                    round((start + w["start"]) * S),
                                    round((start + w["end"]) * S)) for w in words)
        vectors = {label: (tuple(vector), 2.) for label, vector in (embeddings or {}).items()}
        mapping, relabels = self.product.observe_window(start, absolute, vectors)
        self.births = self.product._next_id - 1
        return {label: ("S00" if mid is None else f"M{int(mid.rsplit('-', 1)[1])}")
                for label, mid in mapping.items()}, relabels


def main():
    guard.measure.SpeakerRegistry = ProductAdapter
    rows = []
    for key in CASES:
        clip, observations, reference, masks = guard.load(key)
        state = guard.measure.evaluate([], observations, 0, .3, .46, .6,
                                       include_segments=True, stop_drain=True, birth_min_s=2)
        scored = guard.c4.score_view(clip, reference, masks, state, "first")
        actual = {"der": scored["metrics"]["der"], "ids": state["speaker_count"],
                  "last_ids": state["last_speaker_count"]}
        expected = EXPECTED[key]
        passed = (abs(actual["der"] - expected["der"]) <= .001 and
                  actual["ids"] == expected["ids"] and
                  actual["last_ids"] == expected["last_ids"])
        row = {"case": key, "windows": len(observations), "actual": actual,
               "expected": expected, "pass": passed}
        rows.append(row)
        print(json.dumps(row), flush=True)
    path = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P66/wp1/parity-product.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2) + "\n")
    if not all(row["pass"] for row in rows):
        raise SystemExit("P4 product parity mismatch")


if __name__ == "__main__":
    main()
