#!/usr/bin/env python3
"""PROTOTYPE. Tune the retrospective sweep's merge threshold + reassignment hysteresis
on the REAL golden corpora, after proto_real_replay falsified merge_thr=0.70 (it
false-merges same-gender podcast co-hosts; production live_identity_sweep.py:80 ships
the same 0.70). Uses cached embeddings — runs in seconds.

Run: .venv/bin/python proto_sweep_tuning.py
"""
from __future__ import annotations

import numpy as np

import proto_ab_identity as H
from proto_real_replay import REAL, embed_sample

CFG = dict(min_score=0.35, margin=0.1, admission=1.0)
VARIANTS = [  # (label, kwargs)
    ("drop-uncertain m=0.70", dict(merge_thr=0.70, keep_uncertain=False)),
    ("keep-uncertain m=0.70", dict(merge_thr=0.70, keep_uncertain=True)),
    ("keep-uncertain m=0.70 sticky", dict(merge_thr=0.70, keep_uncertain=True, sticky_delta=0.05)),
    ("keep-uncertain m=off", dict(merge_thr=None, keep_uncertain=True)),
]


def true_centroid_stats(cache) -> tuple[float, float]:
    """(max cross-speaker sim, min same... n/a) of TRUE per-speaker centroids."""
    rows, vecs, vec_idx = cache["rows"], cache["vecs"], cache["vec_idx"]
    cents = {}
    for spk in {int(t) for t in rows[:, 1]}:
        sel = (rows[:, 1] == spk) & (rows[:, 5] > 0)
        if sel.any():
            m = vecs[vec_idx[np.where(sel)[0]]].mean(0)
            cents[spk] = m / (np.linalg.norm(m) + 1e-12)
    ks = sorted(cents)
    cross = [float(cents[a] @ cents[b]) for i, a in enumerate(ks) for b in ks[i + 1:]]
    return (max(cross) if cross else float("nan")), len(ks)


def main() -> None:
    adapter = H.load_production_embedder()
    samples = []
    for corpus, root, sweep_every in [("1min", REAL / "benchmark_diarization_1min" / "samples", 20.0),
                                      ("3min", REAL / "calibration_diarization_3min" / "samples", 30.0)]:
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            samples.append((corpus, d.name, embed_sample(adapter, d), sweep_every))

    print("=== TRUE cross-speaker centroid similarity per clip (merge threshold must exceed ALL of these) ===")
    worst = 0.0
    for corpus, name, cache, _ in samples:
        mx, k = true_centroid_stats(cache)
        worst = max(worst, mx)
        print(f"  {name:<28} K={k}  max cross-speaker centroid sim = {mx:.3f}")
    print(f"  -> highest observed cross-speaker centroid sim: {worst:.3f}")

    print("\n=== sweep variants on real corpora (config grid-best; album baseline vs album+sweep) ===")
    print(f"{'variant':<24} {'swp mean':>9} {'swp min':>8}   (album baseline: fixed)")
    base = []
    for corpus, name, cache, sweep_every in samples:
        H.SWEEP_EVERY = sweep_every
        al, _, _, _ = H.simulate(cache, policy="album", sweep=False, **CFG)
        base.append(H.accuracy(cache["rows"], al))
    print(f"{'album (no sweep)':<24} {np.mean(base)*100:8.1f}% {np.min(base)*100:7.1f}%")
    results = {}
    for label, kw in VARIANTS:
        accs = []
        for corpus, name, cache, sweep_every in samples:
            H.SWEEP_EVERY = sweep_every
            _, rt, _, _ = H.simulate(cache, policy="album", sweep=True, **kw, **CFG)
            accs.append(H.accuracy(cache["rows"], rt))
        results[label] = (accs, kw)
        print(f"{label:<30} {np.mean(accs)*100:8.1f}% {np.min(accs)*100:7.1f}%")

    best_key = max(results, key=lambda k: (np.min(results[k][0]), np.mean(results[k][0])))
    best_kw = results[best_key][1]
    print(f"\nbest variant by worst-clip then mean: {best_key}")

    print("\n=== regression check: winning variant on the 8 SYNTHETIC meetings ===")
    H.SWEEP_EVERY = 60.0
    for pol_name, kwargs in [("album (no sweep)", dict(sweep=False)),
                             (f"sweep {best_key}", dict(sweep=True, **best_kw)),
                             ("sweep old drop-uncertain", dict(sweep=True, merge_thr=0.70))]:
        accs = []
        for k, seed in H.SCENARIOS:
            cache = dict(np.load(H.DATA / f"cache_meet_k{k}_s{seed}.npz"))
            rows = cache["rows"]
            elig = rows[:, 5] > 0
            cache["vec_idx"] = np.where(elig, np.cumsum(elig) - 1, -1).astype(np.int64)
            a, rt, _, _ = H.simulate(cache, policy="album", **CFG, **kwargs)
            accs.append(H.accuracy(rows, rt if kwargs.get("sweep") else a))
        print(f"  {pol_name:<24} mean={np.mean(accs)*100:5.1f}%  min={np.min(accs)*100:5.1f}%")


if __name__ == "__main__":
    main()
