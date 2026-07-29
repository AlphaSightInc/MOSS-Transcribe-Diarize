#!/usr/bin/env python3
"""PROTOTYPE. Library extension: 5-minute tier (8 real cases) + 30-minute long-form
tier (2 cases) from the full benchmark_diarization corpus on m4mbp (goldens aligned
from the shows' own timestamped transcripts).

Closes the design doc's duration gap: previous longest real golden was 180 s; the user's
production sessions run 1-3 h. The 30 m tier measures convergence (retro accuracy vs
prefix oracle over time) at 10x the previous horizon. Reported standalone — the 9-clip
binding aggregate (95.2%) is unchanged.

Run: .venv/bin/python proto_corpus_5m30m.py
"""
from __future__ import annotations

import numpy as np

import proto_ab_identity as H
from proto_real_replay import CONFIGS, REAL, embed_sample


def main() -> None:
    adapter = H.load_production_embedder()
    agg: dict[str, list[float]] = {}
    for corpus, root in [("5m", REAL / "benchmark_5m"), ("30m", REAL / "benchmark_30m")]:
        H.SWEEP_EVERY = 60.0
        print(f"\n===== {corpus} tier =====", flush=True)
        for sample_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            cache = embed_sample(adapter, sample_dir)
            rows = cache["rows"]
            k_true = len({int(t) for t in rows[:, 1]})
            orc = H.oracle_accuracy(cache)
            line = f"{sample_dir.name:<24} K={k_true} oracle={orc*100:5.1f}%"
            for cfg_name, cfg in CONFIGS:
                if cfg_name == "deployed-anchor":
                    continue  # 0.5 cap already established on every other tier
                ov, _, _, _ = H.simulate(cache, policy="overwrite",
                                         min_score=cfg["min_score"], margin=cfg["margin"])
                al, rt, slog, scost = H.simulate(cache, policy="album", sweep=True, **cfg)
                a_ov, a_al, a_rt = (H.accuracy(rows, x) for x in (ov, al, rt))
                agg.setdefault(f"{corpus}/{cfg_name}/overwrite", []).append(a_ov)
                agg.setdefault(f"{corpus}/{cfg_name}/album", []).append(a_al)
                agg.setdefault(f"{corpus}/{cfg_name}/album+sweep", []).append(a_rt)
                line += (f" | {cfg_name}: ov={a_ov*100:4.1f} alb={a_al*100:4.1f} "
                         f"swp={a_rt*100:4.1f}")
            agg.setdefault(f"{corpus}/oracle", []).append(orc)
            print(line, flush=True)
            if corpus == "30m":  # convergence trajectory at the long horizon
                _, _, slog, scost = H.simulate(cache, policy="album", sweep=True,
                                               min_score=0.35, margin=0.1, admission=1.0)
                pts = slog[:: max(1, len(slog) // 8)]
                traj = " ".join(
                    f"t={t:>4.0f}s:{H.accuracy(rows, r, upto=t)*100:.1f}" for t, r in pts
                )
                print(f"  retro accuracy over time: {traj}")
                print(f"  total sweep compute for 30 min: {scost*1000:.1f} ms "
                      f"({len(slog)} sweeps)")

    print("\n===== aggregates =====")
    for key in sorted(agg):
        v = agg[key]
        print(f"  {key:<34} mean={np.mean(v)*100:5.1f}%  min={np.min(v)*100:5.1f}%")


if __name__ == "__main__":
    main()
