#!/usr/bin/env python3
"""PROTOTYPE. Design doc §7 residual caveat: real conversational audio.

Replays the m4mbp golden diarization corpora (real interview clips, 16 kHz mono WAV +
reference.jsonl speaker turns) through the same production-embedder harness as
proto_ab_identity: overwrite vs album (±sweep) vs whole-file oracle.

Corpora (fetched from ga0@m4mbp LiveTranscribe/data):
  data/real/benchmark_diarization_1min/samples/*    6 clips x 60 s
  data/real/calibration_diarization_3min/samples/*  3 clips x ~180 s

Run: .venv/bin/python proto_real_replay.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import proto_ab_identity as H

REAL = H.DATA / "real"
CONFIGS = [
    ("deployed-anchor", dict(min_score=0.5, margin=0.2, admission=2.0)),
    ("grid-best", dict(min_score=0.35, margin=0.1, admission=1.0)),
    ("deployed-margin", dict(min_score=0.35, margin=0.2, admission=1.0)),
]

# Phase Q1 (candidate 55): a birth needs evidence the album would enrol. The shipped fix sets
# the floor to the album's own admission, so this pair is the deployed configuration with the
# birth path before and after. Reported apart from CONFIGS because what it answers is not
# "which thresholds" but "how many speakers did the meeting invent", and the aggregate line
# above has to keep reproducing the 95.2 % the design doc records.
BIRTH_FLOOR_CONFIG = dict(min_score=0.35, margin=0.1, admission=1.0)


def load_truth(sample_dir: Path) -> list[tuple[float, float, int]]:
    speakers: dict[str, int] = {}
    truth = []
    prev_end = 0.0
    for line in (sample_dir / "reference.jsonl").read_text().splitlines():
        seg = json.loads(line)
        spk = speakers.setdefault(seg["speaker"], len(speakers))
        start = max(float(seg["start"]), prev_end)  # golden turns can touch; never overlap
        end = float(seg["end"])
        if end <= start:
            continue
        truth.append((start, end, spk))
        prev_end = end
    return truth


def embed_sample(adapter, sample_dir: Path) -> dict:
    cache_path = sample_dir / "harness_cache.npz"
    if cache_path.exists():
        c = dict(np.load(cache_path))
    else:
        truth = load_truth(sample_dir)
        pieces = H.plan_spans(truth)
        groups: dict[tuple[int, int], list] = {}
        for p in pieces:
            groups.setdefault((p.span, p.true_spk), []).append(p)
        vecs, keys, rows = [], [], []
        for (span, spk), ps in sorted(groups.items()):
            ok_ps = [p for p in ps if p.dur >= H.MIN_EVID]
            dur = sum(p.dur for p in ok_ps) or sum(p.dur for p in ps)
            eligible = bool(ok_ps)
            if eligible:
                v = adapter.embed(sample_dir / "audio.wav", [(p.start, p.end) for p in ok_ps])
                vecs.append(np.asarray(v, np.float32))
                keys.append(len(vecs) - 1)
            else:
                keys.append(-1)
            rows.append((span, spk, min(p.start for p in ps), max(p.end for p in ps), dur, int(eligible)))
        np.savez(cache_path,
                 vecs=np.stack(vecs) if vecs else np.zeros((0, 256), np.float32),
                 vec_idx=np.array(keys, np.int64), rows=np.array(rows, np.float64))
        c = dict(np.load(cache_path))
    elig = c["rows"][:, 5] > 0
    c["vec_idx"] = np.where(elig, np.cumsum(elig) - 1, -1).astype(np.int64)
    return c


def main() -> None:
    adapter = H.load_production_embedder()
    corpora = [
        ("1min", REAL / "benchmark_diarization_1min" / "samples", 20.0),
        ("3min", REAL / "calibration_diarization_3min" / "samples", 30.0),
    ]
    agg: dict[str, list[float]] = {}
    for corpus, root, sweep_every in corpora:
        H.SWEEP_EVERY = sweep_every
        print(f"\n===== {corpus} corpus (sweep every {sweep_every:.0f}s) =====")
        for sample_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            cache = embed_sample(adapter, sample_dir)
            rows = cache["rows"]
            k_true = len({int(t) for t in rows[:, 1]})
            orc = H.oracle_accuracy(cache)
            line = f"{sample_dir.name:<28} K={k_true} oracle={orc*100:5.1f}%"
            for cfg_name, cfg in CONFIGS:
                ov, _, _, _ = H.simulate(cache, policy="overwrite",
                                         min_score=cfg["min_score"], margin=cfg["margin"])
                al, rt, _, _ = H.simulate(cache, policy="album", sweep=True, **cfg)
                a_ov, a_al, a_rt = (H.accuracy(rows, x) for x in (ov, al, rt))
                agg.setdefault(f"{cfg_name}/overwrite", []).append(a_ov)
                agg.setdefault(f"{cfg_name}/album", []).append(a_al)
                agg.setdefault(f"{cfg_name}/album+sweep", []).append(a_rt)
                line += f" | {cfg_name}: ov={a_ov*100:4.1f} alb={a_al*100:4.1f} swp={a_rt*100:4.1f}"
            agg.setdefault("oracle", []).append(orc)
            print(line)

    print("\n===== aggregate over all 9 real clips =====")
    for key in sorted(agg):
        v = agg[key]
        print(f"  {key:<28} mean={np.mean(v)*100:5.1f}%  min={np.min(v)*100:5.1f}%")

    print("\n===== Q1 birth floor on real conversational audio (grid-best thresholds) =====")
    print("  clip                         K  born@0.0 born@1.0   swp@0.0 swp@1.0")
    born_off, born_on, acc_off, acc_on = [], [], [], []
    for corpus, root, sweep_every in corpora:
        H.SWEEP_EVERY = sweep_every
        for sample_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            cache = embed_sample(adapter, sample_dir)
            rows = cache["rows"]
            k_true = len({int(t) for t in rows[:, 1]})
            counts, accs = [], []
            for floor in (0.0, BIRTH_FLOOR_CONFIG["admission"]):
                live, retro, _, _ = H.simulate(
                    cache, policy="album", sweep=True, birth_floor=floor, **BIRTH_FLOOR_CONFIG
                )
                counts.append(len({int(c) for c in live if c >= 0}))
                accs.append(H.accuracy(rows, retro))
            born_off.append(counts[0]); born_on.append(counts[1])
            acc_off.append(accs[0]); acc_on.append(accs[1])
            print(f"  {sample_dir.name:<28} {k_true}  {counts[0]:>7}  {counts[1]:>7}   "
                  f"{accs[0]*100:6.1f}  {accs[1]*100:6.1f}")
    print(f"  {'MEAN':<28}    {np.mean(born_off):>7.2f}  {np.mean(born_on):>7.2f}   "
          f"{np.mean(acc_off)*100:6.1f}  {np.mean(acc_on)*100:6.1f}")
    print(f"  {'WORST CLIP':<28}    {max(born_off):>7}  {max(born_on):>7}   "
          f"{min(acc_off)*100:6.1f}  {min(acc_on)*100:6.1f}")


if __name__ == "__main__":
    main()
