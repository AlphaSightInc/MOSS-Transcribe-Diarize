#!/usr/bin/env python3
"""PROTOTYPE — throwaway. Design doc §6 gates A and B.

A: quality-gated fingerprint album vs production latest-span overwrite — causal live
   speaker accuracy (target >=90-95%).
B: live→file convergence — does the gap between causal live accuracy and a whole-file
   clustering oracle close when retrospective sweeps rewrite history (the sibling
   project's divergence failure), and what do sweeps cost?

Uses the PRODUCTION embedder code path (moss_transcribe_diarize/app/speaker_identity.py
_OnnxWeSpeakerEmbedder via WeSpeakerResNet152LmAdapter) with the pinned ONNX asset, and
production live-path semantics: 2.5 s continuous-speech span cap, 0.5 s minimum span
evidence, per-span local speakers matched one-to-one to canonical refs with
score/margin gates, birth on low similarity, max 16 speakers.

Run: .venv/bin/python proto_ab_identity.py all   (or: build | embed | sim)
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DATA = HERE / "data"
LIBRI = DATA / "LibriSpeech" / "dev-clean"
ONNX = DATA / "voxceleb_resnet152_LM.onnx"

SR = 16000
SPAN_CAP = 2.5          # production hard_cap_samples 40000
SILENCE_SPLIT = 0.6     # VAD span break on silence
MIN_EVID = 0.5          # production min_segment_samples 8000
MAX_SPK = 16            # production max_identity_speakers
MEET_LEN = 600.0
SCENARIOS = [(2, 0), (2, 1), (3, 0), (3, 1), (4, 0), (4, 1), (6, 0), (6, 1)]  # (K, seed)
SWEEP_EVERY = 60.0
MERGE_THR = 0.70        # matches deployed tier_b_similarity


# ---------------------------------------------------------------- meeting synthesis
def list_utterances():
    utts = {}
    for spk_dir in sorted(LIBRI.iterdir()):
        if not spk_dir.is_dir():
            continue
        flacs = sorted(spk_dir.glob("*/*.flac"))
        if len(flacs) >= 20:
            utts[spk_dir.name] = flacs
    return utts


def build_meetings():
    import soundfile as sf

    utts = list_utterances()
    speakers = sorted(utts)
    for k, seed in SCENARIOS:
        rng = np.random.default_rng(seed * 100 + k)
        cast = list(rng.choice(speakers, size=k, replace=False))
        audio: list[np.ndarray] = []
        truth: list[tuple[float, float, int]] = []
        t = 0.0
        cur = -1
        pools = {s: list(rng.permutation(len(utts[s]))) for s in cast}
        while t < MEET_LEN:
            nxt = int(rng.integers(0, k))
            if nxt == cur:
                nxt = (nxt + 1) % k
            cur = nxt
            spk = cast[cur]
            short_turn = rng.random() < 0.3  # backchannels — the live-ID killer
            target = rng.uniform(0.8, 2.0) if short_turn else rng.uniform(3.0, 12.0)
            placed = 0.0
            while placed < target and t < MEET_LEN:
                if not pools[spk]:
                    pools[spk] = list(rng.permutation(len(utts[spk])))
                wav, sr = sf.read(utts[spk][pools[spk].pop()], dtype="float32")
                assert sr == SR
                need = target - placed
                if len(wav) / SR > need + 1.0:
                    dur = max(0.8, need)
                    off = rng.integers(0, max(1, len(wav) - int(dur * SR)))
                    wav = wav[off : off + int(dur * SR)]
                audio.append(wav)
                d = len(wav) / SR
                truth.append((t, t + d, cur))
                t += d
                placed += d
                if placed < target:
                    gap = float(rng.uniform(0.05, 0.25))
                    audio.append(np.zeros(int(gap * SR), np.float32))
                    t += gap
            gap = float(rng.uniform(0.2, 0.5) if rng.random() < 0.5 else rng.uniform(0.7, 1.4))
            audio.append(np.zeros(int(gap * SR), np.float32))
            t += gap
        name = f"meet_k{k}_s{seed}"
        sf.write(DATA / f"{name}.wav", np.concatenate(audio), SR)
        (DATA / f"{name}.json").write_text(json.dumps({"k": k, "truth": truth}))
        print(f"built {name}: {t:.0f}s, {len(truth)} true segments, cast={cast}")


# ---------------------------------------------------------------- span planning
@dataclass
class Piece:
    span: int
    start: float
    end: float
    true_spk: int

    @property
    def dur(self) -> float:
        return self.end - self.start


def plan_spans(truth: list[tuple[float, float, int]]) -> list[Piece]:
    """Production live semantics: spans break on >=SILENCE_SPLIT silence or at 2.5 s
    of continuous speech (mid-utterance cuts included)."""
    pieces: list[Piece] = []
    span = 0
    acc = 0.0
    prev_end = None
    for start, end, spk in truth:
        if prev_end is not None and start - prev_end >= SILENCE_SPLIT:
            span += 1
            acc = 0.0
        cur = start
        while cur < end:
            room = SPAN_CAP - acc
            cut = min(end, cur + room)
            pieces.append(Piece(span, cur, cut, spk))
            acc += cut - cur
            cur = cut
            if acc >= SPAN_CAP - 1e-9:
                span += 1
                acc = 0.0
        prev_end = end
    return pieces


# ---------------------------------------------------------------- embedding cache
def load_production_embedder():
    import types

    # Stub the package so speaker_identity's absolute import of transcript_parser
    # resolves without executing the heavy package __init__ (pulls transformers).
    pkg = types.ModuleType("moss_transcribe_diarize")
    pkg.__path__ = [str(REPO / "moss_transcribe_diarize")]
    sys.modules.setdefault("moss_transcribe_diarize", pkg)
    tp_spec = importlib.util.spec_from_file_location(
        "moss_transcribe_diarize.transcript_parser",
        REPO / "moss_transcribe_diarize" / "transcript_parser.py",
    )
    tp = importlib.util.module_from_spec(tp_spec)
    sys.modules["moss_transcribe_diarize.transcript_parser"] = tp  # before exec: slots dataclasses
    tp_spec.loader.exec_module(tp)

    spec = importlib.util.spec_from_file_location(
        "si_prod", REPO / "moss_transcribe_diarize" / "app" / "speaker_identity.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["si_prod"] = mod
    spec.loader.exec_module(mod)
    adapter = mod.WeSpeakerResNet152LmAdapter(ONNX)
    pf = adapter.preflight()
    assert pf.available, f"production preflight failed: {pf.reason}"
    return adapter


def embed_all():
    adapter = load_production_embedder()
    for k, seed in SCENARIOS:
        name = f"meet_k{k}_s{seed}"
        meta = json.loads((DATA / f"{name}.json").read_text())
        pieces = plan_spans([tuple(x) for x in meta["truth"]])
        # evidence unit = (span, local speaker): production averages a speaker's
        # intervals inside one span into a single vector
        groups: dict[tuple[int, int], list[Piece]] = {}
        for p in pieces:
            groups.setdefault((p.span, p.true_spk), []).append(p)
        keys, vecs, rows = [], [], []
        t0 = time.perf_counter()
        for (span, spk), ps in sorted(groups.items()):
            # production filters each interval by min_segment_samples individually
            # (live_provider_bundle.py:731); sub-0.5s pieces yield no evidence
            ok_ps = [p for p in ps if p.dur >= MIN_EVID]
            dur = sum(p.dur for p in ok_ps) or sum(p.dur for p in ps)
            eligible = bool(ok_ps)
            if eligible:
                v = adapter.embed(DATA / f"{name}.wav", [(p.start, p.end) for p in ok_ps])
                vecs.append(np.asarray(v, np.float32))
                keys.append(len(vecs) - 1)
            else:
                keys.append(-1)
            rows.append(
                (span, spk, min(p.start for p in ps), max(p.end for p in ps), dur, int(eligible))
            )
        dt = time.perf_counter() - t0
        np.savez(
            DATA / f"cache_{name}.npz",
            vecs=np.stack(vecs) if vecs else np.zeros((0, 256), np.float32),
            vec_idx=np.array(keys, np.int64),
            rows=np.array(rows, np.float64),
        )
        n_emb = len(vecs)
        print(
            f"embedded {name}: {len(rows)} evidence units, {n_emb} embedded, "
            f"{dt:.1f}s total ({dt / max(n_emb, 1) * 1000:.0f} ms/embed)"
        )


# ---------------------------------------------------------------- live simulation
@dataclass
class Album:
    k_max: int = 10
    admission: float = 2.0
    exemplars: list[tuple[np.ndarray, float]] = field(default_factory=list)

    def admit(self, vec: np.ndarray, dur: float) -> None:
        if dur < self.admission and self.exemplars:
            return
        self.exemplars.append((vec, dur))
        self.exemplars.sort(key=lambda e: -e[1])
        del self.exemplars[self.k_max :]

    def ref(self) -> np.ndarray:
        w = np.array([d for _, d in self.exemplars])
        m = (np.stack([v for v, _ in self.exemplars]) * (w / w.sum())[:, None]).sum(0)
        return m / (np.linalg.norm(m) + 1e-12)


def simulate(cache, *, policy: str, min_score: float, margin: float,
             admission: float = 2.0, sweep: bool = False,
             merge_thr: float | None = MERGE_THR, sticky_delta: float = 0.0,
             keep_uncertain: bool = False, birth_floor: float = 0.0):
    """`birth_floor` is candidate 55 / Phase Q1: a birth needs enrollable evidence.

    Production mints a canonical speaker for every local speaker a span's diarization
    produced that did not match an existing one, with no duration condition at all -- so a
    fragment spends a capacity slot on a voice the album can never hold. Setting this to the
    album's `admission` reproduces the shipped fix; 0.0 reproduces the policy it replaced.

    **Fidelity limit, and it runs one way.** This loop only ever sees units that cleared the
    0.5 s evidence floor (`rows[:, 5]`), so the case that dominated production -- a local
    speaker the encoder was never asked about, which is where 14 of one certification run's
    16 canonical speakers came from -- cannot be represented here at all. What the bench can
    measure is the 0.5-1.0 s half. Every canonical-count reduction it reports is therefore a
    **lower bound** on the shipped fix's effect.
    """
    rows, vecs, vec_idx = cache["rows"], cache["vecs"], cache["vec_idx"]
    order = np.argsort(rows[:, 2], kind="stable")
    refs: dict[int, np.ndarray] = {}
    albums: dict[int, Album] = {}
    assigned = np.full(len(rows), -1, np.int64)   # canonical id per evidence unit
    retro = None
    span_units: dict[int, list[int]] = {}
    for i in order:
        span_units.setdefault(int(rows[i, 0]), []).append(int(i))
    sweep_log, next_sweep, sweep_cost = [], SWEEP_EVERY, 0.0

    def run_sweep(t_now: float) -> None:
        nonlocal retro, sweep_cost
        if not refs:
            return
        t0 = time.perf_counter()
        retro = assigned.copy()
        cids = list(refs)
        cpos = {c: k for k, c in enumerate(cids)}
        R = np.stack([refs[c] for c in cids])
        sims = R @ R.T
        merged = {}
        if merge_thr is not None:
            for a in range(len(cids)):
                for b in range(a + 1, len(cids)):
                    if sims[a, b] >= merge_thr:
                        merged[cids[b]] = merged.get(cids[a], cids[a])
        past = [u for u in range(len(rows)) if rows[u, 3] <= t_now and vec_idx[u] >= 0]
        V = vecs[vec_idx[past]]
        S = V @ R.T
        win = S.argmax(1)
        okm = S.max(1) >= min_score
        for j, u in enumerate(past):
            c = cids[win[j]] if okm[j] else -1
            cur = int(assigned[u])
            if (c >= 0 and cur >= 0 and cur in cpos and c != cur
                    and S[j, win[j]] - S[j, cpos[cur]] <= sticky_delta):
                c = cur  # hysteresis: don't relabel without a decisive improvement
            if keep_uncertain and c < 0 and cur >= 0:
                c = cur  # a weak vector alone can't erase a span-context label
            retro[u] = merged.get(c, c) if c >= 0 else -1
        sweep_cost += time.perf_counter() - t0
        sweep_log.append((t_now, retro.copy()))

    for span, unit_ids in sorted(span_units.items()):
        elig = [u for u in unit_ids if rows[u, 5] > 0]
        if not elig:
            continue
        elig.sort(key=lambda u: -rows[u, 4])
        cids = list(refs)
        R = np.stack([refs[c] for c in cids]) if cids else np.zeros((0, 256), np.float32)
        taken: set[int] = set()
        pending: list[tuple[int, int, np.ndarray]] = []
        abstain = False
        for u in elig:
            v = vecs[vec_idx[u]]
            s = R @ v if len(R) else np.array([])
            open_idx = [j for j in range(len(cids)) if j not in taken]
            best = max(open_idx, key=lambda j: s[j]) if open_idx else None
            if best is not None and s[best] >= min_score:
                runners = [s[j] for j in open_idx if j != best]
                if runners and s[best] - max(runners) < margin:
                    abstain = True  # ambiguous — production abstains the span
                    break
                taken.add(best)
                pending.append((u, cids[best], v))
            else:
                if rows[u, 4] < birth_floor:
                    continue  # Q1: deferred, not born -- the unit stays unlabelled (S00)
                if len(refs) + sum(1 for _, c, _ in pending if c == -1) >= MAX_SPK:
                    abstain = True
                    break
                pending.append((u, -1, v))  # birth
        if abstain:
            continue  # no assignment, no updates; evidence stays unlabeled (counts wrong)
        for u, c, v in pending:
            if c == -1:
                c = (max(refs) + 1) if refs else 0
            assigned[u] = c
            dur = rows[u, 4]
            if policy == "overwrite":
                refs[c] = v  # production live_provider_bundle.py:597
            else:
                albums.setdefault(c, Album(admission=admission)).admit(v, dur)
                refs[c] = albums[c].ref()
        # retrospective sweep (B): rewrite history against current refs, then merge
        t_now = rows[unit_ids[-1], 3]
        if sweep and t_now >= next_sweep:
            next_sweep += SWEEP_EVERY
            run_sweep(t_now)
    if sweep:
        run_sweep(float(rows[:, 3].max()))  # final sweep at meeting end (design §3.5)
    return assigned, retro if retro is not None else assigned, sweep_log, sweep_cost


# ---------------------------------------------------------------- metrics
def accuracy(rows, labels, upto=None, elig_only=True) -> float:
    from scipy.optimize import linear_sum_assignment

    sel = (rows[:, 5] > 0) if elig_only else np.ones(len(rows), bool)
    if upto is not None:
        sel &= rows[:, 3] <= upto
    tr = rows[sel, 1].astype(int)
    lb = labels[sel]
    du = rows[sel, 4]
    cs, ts = sorted({*lb[lb >= 0]}), sorted({*tr})
    M = np.zeros((len(cs), len(ts)))
    for c, t, d in zip(lb, tr, du):
        if c >= 0:
            M[cs.index(c), ts.index(t)] += d
    if not len(cs):
        return 0.0
    ri, ci = linear_sum_assignment(-M)
    return M[ri, ci].sum() / du.sum()


def oracle_accuracy(cache, upto=None) -> float:
    """Whole-file mode: agglomerative average-link cosine clustering, K known."""
    from scipy.cluster.hierarchy import fcluster, linkage
    from scipy.spatial.distance import pdist

    rows, vecs, vec_idx = cache["rows"], cache["vecs"], cache["vec_idx"]
    sel = rows[:, 5] > 0
    if upto is not None:
        sel &= rows[:, 3] <= upto
    idx = np.where(sel)[0]
    V = vecs[vec_idx[idx]]
    k = len({int(t) for t in rows[idx, 1]})
    if len(idx) <= k:
        return 1.0
    lab = fcluster(linkage(pdist(V, "cosine"), "average"), k, "maxclust")
    labels = np.full(len(rows), -1, np.int64)
    labels[idx] = lab
    return accuracy(rows, labels, upto=upto)


# ---------------------------------------------------------------- driver
def sim_all():
    grid_scores, grid_margins, grid_adm = [0.35, 0.45, 0.55], [0.1, 0.2], [1.0, 2.0]
    print(f"{'meeting':<12} {'policy':<26} {'live%':>6} {'retro%':>7} {'oracle%':>8} "
          f"{'#spk(true)':>10} {'sweep_ms':>9}")
    summary: dict[str, list] = {}
    conv_rows = []
    for k, seed in SCENARIOS:
        name = f"meet_k{k}_s{seed}"
        cache = dict(np.load(DATA / f"cache_{name}.npz"))
        rows = cache["rows"]
        elig = rows[:, 5] > 0  # rebuild vec index from row order (robust to writer versions)
        cache["vec_idx"] = np.where(elig, np.cumsum(elig) - 1, -1).astype(np.int64)
        orc = oracle_accuracy(cache)
        best = None
        for ms in grid_scores:
            for mg in grid_margins:
                a, _, _, _ = simulate(cache, policy="overwrite", min_score=ms, margin=mg)
                acc_o = accuracy(rows, a)
                summary.setdefault(f"overwrite s={ms} m={mg}", []).append(acc_o)
                for adm in grid_adm:
                    a2, r2, slog, scost = simulate(
                        cache, policy="album", min_score=ms, margin=mg,
                        admission=adm, sweep=True,
                    )
                    acc_a, acc_r = accuracy(rows, a2), accuracy(rows, r2)
                    key = f"album s={ms} m={mg} adm={adm}"
                    summary.setdefault(key, []).append(acc_a)
                    summary.setdefault(key + " +sweep", []).append(acc_r)
                    if best is None or acc_r > best[0]:
                        nspk = len({*a2[a2 >= 0]})
                        best = (acc_r, acc_a, acc_o, ms, mg, adm, nspk, slog, scost)
        acc_r, acc_a, acc_o, ms, mg, adm, nspk, slog, scost = best
        print(f"{name:<12} best album s={ms} m={mg} adm={adm:<4} {acc_a*100:6.1f} "
              f"{acc_r*100:7.1f} {orc*100:8.1f} {nspk:>6}({k})  "
              f"{scost/max(len(slog),1)*1000:8.1f}")
        print(f"{'':<12} overwrite  s={ms} m={mg}       "
              f"{accuracy(rows, simulate(cache, policy='overwrite', min_score=ms, margin=mg)[0])*100:6.1f}")
        for t_chk, retro in slog:  # convergence curve: gap to prefix oracle
            conv_rows.append((name, t_chk,
                              accuracy(rows, retro, upto=t_chk),
                              oracle_accuracy(cache, upto=t_chk)))

    print("\n=== grid means over all meetings (gate A) ===")
    for key in sorted(summary):
        v = summary[key]
        print(f"  {key:<38} mean={np.mean(v)*100:5.1f}%  min={np.min(v)*100:5.1f}%")

    print("\n=== convergence: retro-vs-prefix-oracle gap over time (gate B) ===")
    for name in sorted({r[0] for r in conv_rows}):
        pts = [(t, rr, oo) for n, t, rr, oo in conv_rows if n == name]
        line = " ".join(f"t={t:.0f}:{(oo-rr)*100:+.1f}" for t, rr, oo in pts[:: max(1, len(pts)//6)])
        print(f"  {name:<12} gap(pp): {line}")

    json.dump(
        {"summary": {k: list(map(float, v)) for k, v in summary.items()},
         "convergence": conv_rows},
        open(DATA / "ab_results.json", "w"), default=float,
    )
    print("\nresults -> data/ab_results.json")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("build", "all"):
        build_meetings()
    if cmd in ("embed", "all"):
        embed_all()
    if cmd in ("sim", "all"):
        sim_all()
