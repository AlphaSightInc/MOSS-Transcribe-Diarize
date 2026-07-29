#!/usr/bin/env python3
"""PROTOTYPE. Standalone measurement of the youtube_rtfl_first_90s regression fixture
(golden updated on m4mbp 2026-07-29 10:53; fetched fresh after that update).

Deliberately NOT part of proto_real_replay's 9-clip aggregate — that 95.2% figure is
recorded as binding evidence in the PRD and must stay reproducible. This fixture is
reported standalone: hardest clip in the collection (K=4 in 90 s incl. a
single-appearance speaker, decisecond golden boundaries, sub-floor micro-turns).

Run: .venv/bin/python proto_fixture_90s.py
"""
from __future__ import annotations

import proto_ab_identity as H
from proto_real_replay import CONFIGS, REAL, embed_sample


def main() -> None:
    H.SWEEP_EVERY = 30.0
    d = REAL / "regression_fixtures" / "youtube_rtfl_first_90s"
    adapter = H.load_production_embedder()
    cache = embed_sample(adapter, d)
    rows = cache["rows"]
    k = len({int(t) for t in rows[:, 1]})
    elig = rows[:, 5] > 0
    print(f"{d.name}: K={k}, {len(rows)} units, {int(elig.sum())} eligible, "
          f"{rows[~elig, 4].sum():.1f}s below evidence floor")
    print(f"whole-file oracle: {H.oracle_accuracy(cache)*100:.1f}%")
    for name, cfg in CONFIGS:
        ov, _, _, _ = H.simulate(cache, policy="overwrite",
                                 min_score=cfg["min_score"], margin=cfg["margin"])
        al, rt, _, _ = H.simulate(cache, policy="album", sweep=True, **cfg)
        print(f"{name:<16} overwrite={H.accuracy(rows, ov)*100:5.1f}  "
              f"album={H.accuracy(rows, al)*100:5.1f}  album+sweep={H.accuracy(rows, rt)*100:5.1f}")
    for floor in (0.0, 1.0):
        live, retro, _, _ = H.simulate(cache, policy="album", sweep=True, birth_floor=floor,
                                       min_score=0.35, margin=0.1, admission=1.0)
        born = len({int(c) for c in live if c >= 0})
        print(f"birth_floor={floor}: minted={born} (true K={k}), "
              f"album+sweep={H.accuracy(rows, retro)*100:.1f}%")


if __name__ == "__main__":
    main()
