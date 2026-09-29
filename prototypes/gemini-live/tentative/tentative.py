"""PROTOTYPE (throwaway) — P3 tentative fingerprint names on fresh preview words. See NOTES.md.

One command (from the worktree):
    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
        prototypes/gemini-live/tentative/tentative.py
No Gemini calls: canonical lane = P61 C4 S15/L180 cached observations + vector receipts.
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
GL = HERE.parent
WT = GL.parents[1]
sys.path.insert(0, str(GL))
sys.path.insert(0, str(WT))
from common.corpus import clips  # noqa: E402
from common.gemini_common import read_wav  # noqa: E402

P61 = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P61")
OUT = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/tentative")
CACHE = GL / ".cache" / "tentative"
ONNX = WT / "prototypes" / "streaming-diarization" / "data" / "voxceleb_resnet152_LM.onnx"
RATE = 16000
S, L = 15, 180
WS = (1.0, 1.5, 2.0, 3.0)
TS = (.40, .46, .50, .55, .60)
MS = (0.0, .05, .10)
STEP = 0.5
LONGFORM = {"accept6", "bench5m", "long30m", "long60"}


def selected():
    out = []
    for c in clips():
        if c.tier == "accept6" or c.tier == "long60" or c.tier == "e1":
            out.append(c)
        elif c.tier == "bench5m" and ":lex_" in c.clip_id:
            out.append(c)
        elif c.tier == "long30m" and c.clip_id.endswith("lex_bill_ackman"):
            out.append(c)
    return out


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = np.linalg.norm(v)
    return v / n if n else v


# ---------------------------------------------------------------- canonical replay (production registry)
def canonical(clip, duration):
    from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry
    from moss_transcribe_diarize.app.gemini_provider import GeminiWord
    safe = clip.clip_id.replace(":", "_")
    obs_path = P61 / f"c4-observations-{clip.tier}-{safe}-S{S}-L{L}.jsonl"
    vec_path = P61 / f"vectors-span2s-{clip.tier}-{clip.clip_id}-S{S}-L{L}.json"
    if not obs_path.exists() or not vec_path.exists():
        return None
    rows = [json.loads(line) for line in obs_path.read_text().splitlines()]
    vecs = json.loads(vec_path.read_text())
    ends = list(np.arange(S, duration, S))  # periodic ticks; the final (duration) window is the Stop drain
    rows, vecs = rows[:len(ends)], vecs[:len(ends)]
    for r, v, e in zip(rows, vecs, ends):
        if abs(r["end"] - e) > 1e-3 or (r["start"], r["end"]) != (v["start"], v["end"]):
            raise ValueError(f"schedule mismatch {clip.clip_id}")
    reg = ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60, birth_min_seconds=2)
    prev_end, busy_until = 0.0, 0.0
    snaps = []  # (settle_time, frontier, {mid: ema unit}, {mid: mean unit}, sticky_mid)
    settled = []  # (start, end, mid or None)
    sums: dict[str, np.ndarray] = {}
    sticky = None
    for r, v in zip(rows, vecs):
        start = r["start"]
        words = [GeminiWord(w["text"], w["speaker"], round((start + w["start"]) * RATE),
                            round((start + w["end"]) * RATE)) for w in r["words"]]
        emb = {label: (vector, 0.0) for label, vector in v["embeddings"].items()}
        mapping, _ = reg.observe_window(start, words, emb, committed_through_sample=round(r["end"] * RATE))
        new = [(w.start_sample / RATE, w.end_sample / RATE, mapping[w.speaker]) for w in words
               if prev_end < w.end_sample / RATE <= r["end"]]
        settled.extend(new)
        for label, vector in v["embeddings"].items():
            mid = mapping.get(label)
            if mid is not None:
                sums[mid] = sums.get(mid, np.zeros(256)) + unit(vector)
        labelled = [row for row in sorted(new, key=lambda x: x[1]) if row[2] is not None]
        if labelled:
            sticky = labelled[-1][2]
        call_start = max(r["end"], busy_until)
        busy_until = call_start + float(r.get("api_latency_s") or 0.0)
        snaps.append((busy_until, r["end"],
                       {m: unit(c) for m, c in reg._centroids.items()},
                       {m: unit(s) for m, s in sums.items()}, sticky))
        prev_end = r["end"]
    return {"snaps": snaps, "settled": settled, "last_end": ends[-1] if ends else 0.0}


# ---------------------------------------------------------------- embeddings (cached, parallel)
_EMB = {}
_PCM = {}


def _embed_job(args):
    audio, w, times, threads = args
    from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
    if audio not in _PCM:
        _PCM[audio] = read_wav(Path(audio)).astype(np.float32) / 32768.0
    key = threads
    if key not in _EMB:
        factory = None
        if threads != 1:
            import onnxruntime as ort

            def factory(path, sess_options, providers):
                sess_options.intra_op_num_threads = threads
                session = ort.InferenceSession(path, sess_options=sess_options, providers=providers)
                sess_options.intra_op_num_threads = 1
                return session
        _EMB[key] = _OnnxWeSpeakerEmbedder(ONNX, device="cpu", session_factory=factory,
                                           audio_loader=lambda p: (_PCM[str(p)], RATE))
    emb = _EMB[key]
    vectors, ms = [], []
    for t in times:
        t0 = time.perf_counter()
        vectors.append(emb.embed(audio, [(t - w, t)]))
        ms.append((time.perf_counter() - t0) * 1000)
    return np.asarray(vectors, dtype=np.float32), np.asarray(ms)


def embeddings(clip, w, times, pool):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{clip.tier}-{clip.clip_id.replace(':', '_')}-W{w}.npz"
    if path.exists():
        z = np.load(path)
        if len(z["t"]) == len(times) and np.allclose(z["t"], times):
            return z["v"], z["ms"]
    chunks = [times[i:i + 40] for i in range(0, len(times), 40)]
    parts = list(pool.map(_embed_job, [(str(clip.audio), w, list(c), 1) for c in chunks]))
    v = np.concatenate([p[0] for p in parts]) if parts else np.zeros((0, 256), np.float32)
    ms = np.concatenate([p[1] for p in parts]) if parts else np.zeros(0)
    np.savez(path, t=np.asarray(times), v=v, ms=ms)
    return v, ms


# ---------------------------------------------------------------- truth helpers
def voiced(pcm16, t):
    import webrtcvad
    vad = voiced.vad = getattr(voiced, "vad", None) or webrtcvad.Vad(1)
    seg = pcm16[max(0, round((t - .5) * RATE)):round(t * RATE)].tobytes()
    return any(vad.is_speech(seg[i:i + 320], RATE) for i in range(0, len(seg) - 319, 320))


def truth_at(refs, x):
    live = {r["speaker"] for r in refs if r["start"] <= x < r["end"]}
    if not live or len(live) > 1:
        return None
    s = next(iter(live))
    return None if s in ("<EXCLUDE>", "", None) or s.upper().startswith("<EXCL") else s


def turns(refs):
    rows = sorted((r for r in refs if r["speaker"] not in ("<EXCLUDE>", "") and r["end"] > r["start"]),
                  key=lambda r: r["start"])
    out = []
    for r in rows:
        if out and out[-1][2] == r["speaker"] and r["start"] - out[-1][1] <= 1.0:
            out[-1][1] = max(out[-1][1], r["end"])
        else:
            out.append([r["start"], r["end"], r["speaker"]])
    return out


def canon_at(arr, x):
    S_, E_, M_ = arr
    mask = (S_ - .15 <= x) & (x <= E_ + .15)
    if not mask.any():
        return None
    idx = np.nonzero(mask)[0]
    d = np.where((S_[idx] <= x) & (x <= E_[idx]), 0.0, np.minimum(abs(x - S_[idx]), abs(x - E_[idx])))
    return M_[idx[int(np.argmin(d))]]


# ---------------------------------------------------------------- per-clip step table
def prepare(clip, pool):
    pcm = read_wav(clip.audio)
    duration = len(pcm) / RATE
    can = canonical(clip, duration)
    if can is None:
        return None
    refs = clip.reference_segments()
    snaps, settled = can["snaps"], can["settled"]
    # meeting ID -> reference speaker by majority overlap of settled words
    votes = {}
    for s, e, m in settled:
        if m is None or not refs:
            continue
        tr = truth_at(refs, (s + e) / 2)
        if tr is not None:
            votes.setdefault(m, {}).setdefault(tr, 0.0)
            votes[m][tr] += max(e - s, .05)
    id2ref = {m: max(v, key=v.get) for m, v in votes.items()}
    tr_list = turns(refs) if refs else []
    change = []
    for i, (s, e, spk) in enumerate(tr_list):
        if i and tr_list[i - 1][2] != spk:
            change.append((s, e, spk))
    arr = (np.array([r[0] for r in settled]), np.array([r[1] for r in settled]),
           np.array([r[2] for r in settled], dtype=object))
    times = [round(t, 3) for t in np.arange(STEP, can["last_end"] + 1e-6, STEP)]
    steps = []
    for t in times:
        k = max((i for i, sn in enumerate(snaps) if sn[0] <= t), default=None)
        x = t - .1
        steps.append({
            "t": t, "snap": k, "voiced": voiced(pcm, t),
            "truth": truth_at(refs, x) if refs else None,
            "canon": canon_at(arr, x),
            "post_change": any(s <= x < min(s + 2, e) for s, e, _ in change),
            "frontier": snaps[k][1] if k is not None else 0.0,
        })
    return {"clip": clip, "pcm": pcm, "snaps": snaps, "settled": settled, "id2ref": id2ref,
            "steps": steps, "change": change, "has_truth": bool(refs)}


def guesses(prep, w, vectors, variant):
    """Per step: (best_id, best_cos, second_cos) against the causally known centroids."""
    out = []
    times = [s["t"] for s in prep["steps"] if s["t"] >= w]
    index = {t: i for i, t in enumerate(times)}
    for s in prep["steps"]:
        if s["t"] < w or s["snap"] is None or not s["voiced"]:
            out.append(None)
            continue
        cents = prep["snaps"][s["snap"]][2 if variant == "ema" else 3]
        if not cents:
            out.append(None)
            continue
        v = unit(vectors[index[s["t"]]])
        sims = sorted(((float(np.dot(v, c)), m) for m, c in cents.items()), reverse=True)
        out.append((sims[0][1], sims[0][0], sims[1][0] if len(sims) > 1 else -1.0))
    return out


def evaluate(prep, g, t_thr, m_thr, mode):
    """mode: fp | sticky | hybrid. Returns counters."""
    c = dict(elig=0, known=0, shown=0, shown_known=0, correct=0, canon_n=0, flick=0,
             pc_elig=0, pc_shown=0, pc_correct=0)
    first_correct = {}
    snaps, id2ref = prep["snaps"], prep["id2ref"]
    for s, gi in zip(prep["steps"], g):
        if not s["voiced"]:
            continue
        guess = None
        sticky = snaps[s["snap"]][4] if s["snap"] is not None else None
        if gi is not None and gi[1] >= t_thr and gi[1] - gi[2] >= m_thr:
            guess = gi[0]
        if mode == "sticky":
            guess = sticky
        elif mode == "hybrid" and guess is None:
            guess = sticky
        truth = s["truth"]
        if prep["has_truth"]:
            if truth is None:
                continue
            c["elig"] += 1
            known_refs = ({id2ref.get(m) for m in snaps[s["snap"]][2]} if s["snap"] is not None else set())
            is_known = truth in known_refs
            c["known"] += is_known
            if s["post_change"]:
                c["pc_elig"] += 1
        else:
            c["elig"] += 1
        if guess is None:
            continue
        c["shown"] += 1
        if prep["has_truth"]:
            c["shown_known"] += is_known
            ok = id2ref.get(guess) == truth
            c["correct"] += ok
            if s["post_change"]:
                c["pc_shown"] += 1
                c["pc_correct"] += ok
            if ok:
                for (ts, te, spk) in prep["change"]:
                    if ts <= s["t"] - .1 < te and spk == truth and (ts, te) not in first_correct:
                        first_correct[(ts, te)] = s["t"] - ts
        if s["canon"] is not None:
            c["canon_n"] += 1
            c["flick"] += guess != s["canon"]
    # time to first correct guess after each speaker change (turns >= 2 s, after first settle)
    first_settle = snaps[0][0] if snaps else 1e9
    eligible_turns = [(ts, te) for ts, te, _ in prep["change"] if te - ts >= 2 and ts >= first_settle]
    delays = [first_correct[k] for k in eligible_turns if k in first_correct]
    c["turns"] = len(eligible_turns)
    c["turn_delays"] = delays
    return c


def summarize(c):
    def r(a, b):
        return round(a / b, 4) if b else None
    d = c.get("turn_delays", [])
    return {"coverage": r(c["shown"], c["elig"]), "accuracy": r(c["correct"], c["shown"]),
            "flicker": r(c["flick"], c["canon_n"]), "known_share": r(c["known"], c["elig"]),
            "coverage_when_known": r(c["shown_known"], c["known"]),
            "post_change_accuracy": r(c["pc_correct"], c["pc_shown"]),
            "post_change_coverage": r(c["pc_shown"], c["pc_elig"]),
            "turn_first_correct_p50_s": round(float(np.median(d)), 2) if d else None,
            "turn_first_correct_p90_s": round(float(np.percentile(d, 90)), 2) if d else None,
            "turns_never_correct": (c["turns"] - len(d)) if c.get("turns") is not None else None,
            "turns": c.get("turns"), "eligible_steps": c["elig"], "shown_steps": c["shown"]}


def add(a, b):
    out = dict(a)
    for k, v in b.items():
        out[k] = out.get(k, [] if isinstance(v, list) else 0) + v
    return out


def cpu_bench():
    clip = next(c for c in clips() if c.tier == "accept6")
    res = {}
    for threads in (1, 4):
        for w in WS:
            _, ms = _embed_job((str(clip.audio), w, [10 + .5 * k for k in range(40)], threads))
            ms = np.sort(ms[5:])
            res[f"threads{threads}-W{w}"] = {"median_ms": round(float(np.median(ms)), 1),
                                            "p95_ms": round(float(np.percentile(ms, 95)), 1)}
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    workers = min(16, os.cpu_count() or 4)
    preps = []
    skipped = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for clip in selected():
            prep = prepare(clip, pool)
            if prep is None:
                skipped.append(clip.clip_id)
                print(f"SKIP {clip.clip_id}: no cached S{S}/L{L} observations/vectors", flush=True)
                continue
            prep["vectors"] = {}
            for w in WS:
                times = [s["t"] for s in prep["steps"] if s["t"] >= w]
                v, ms = embeddings(clip, w, times, pool)
                prep["vectors"][w] = v
            print(f"{clip.tier:8} {clip.clip_id:40} steps={len(prep['steps'])} "
                  f"voiced={sum(s['voiced'] for s in prep['steps'])} IDs={len(prep['id2ref'])} "
                  f"id2ref={prep['id2ref']} snaps={len(prep['snaps'])}", flush=True)
            preps.append(prep)
    cpu = cpu_bench()
    print("CPU ms per snippet embedding:", json.dumps(cpu), flush=True)

    results = []
    for variant in ("ema", "mean"):
        for w in WS:
            gs = {id(p): guesses(p, w, p["vectors"][w], variant) for p in preps}
            for mode in ("fp", "hybrid"):
                for t_thr in TS:
                    for m_thr in MS:
                        pooled, per = {}, {}
                        for p in preps:
                            c = evaluate(p, gs[id(p)], t_thr, m_thr, mode)
                            per[p["clip"].clip_id] = summarize(c)
                            if p["clip"].tier in LONGFORM:
                                pooled = add(pooled, c)
                        results.append({"variant": variant, "W": w, "mode": mode, "T": t_thr, "M": m_thr,
                                        "pooled": summarize(pooled), "per_clip": per})
            # sticky baseline once per W (independent of T/M/variant)
            if variant == "ema":
                pooled, per = {}, {}
                for p in preps:
                    c = evaluate(p, gs[id(p)], 9, 9, "sticky")
                    per[p["clip"].clip_id] = summarize(c)
                    if p["clip"].tier in LONGFORM:
                        pooled = add(pooled, c)
                results.append({"variant": "-", "W": w, "mode": "sticky", "T": None, "M": None,
                                "pooled": summarize(pooled), "per_clip": per})

    def ok(r, acc=.90, cov=.60):
        p = r["pooled"]
        return (p["accuracy"] or 0) >= acc and (p["coverage"] or 0) >= cov and (p["flicker"] or 1) <= .10

    print("\n=== pooled long-form + accept6 (fp = fingerprint only; hybrid = fp else sticky) ===")
    print(f"{'var':5} {'W':>4} {'mode':6} {'T':>5} {'M':>5} | {'cov':>6} {'acc':>6} {'flick':>6} "
          f"{'pcAcc':>6} {'pcCov':>6} {'cov|kn':>6} {'turn50':>6} {'turn90':>6} never/turns")
    for r in sorted(results, key=lambda r: (r["mode"], r["variant"], r["W"], r["T"] or 0, r["M"] or 0)):
        p = r["pooled"]
        print(f"{r['variant']:5} {r['W']:>4} {r['mode']:6} {str(r['T']):>5} {str(r['M']):>5} | "
              f"{str(p['coverage']):>6} {str(p['accuracy']):>6} {str(p['flicker']):>6} "
              f"{str(p['post_change_accuracy']):>6} {str(p['post_change_coverage']):>6} "
              f"{str(p['coverage_when_known']):>6} {str(p['turn_first_correct_p50_s']):>6} "
              f"{str(p['turn_first_correct_p90_s']):>6} {p['turns_never_correct']}/{p['turns']}"
              f"{'  <== meets rule' if ok(r) else ''}")
    passing = [r for r in results if r["mode"] == "fp" and ok(r)]
    at85 = [r for r in results if r["mode"] == "fp" and (r["pooled"]["coverage"] or 0) >= .50
            and (r["pooled"]["accuracy"] or 0) >= .85]
    verdict = ("SHOWABLE (accuracy/coverage/flicker)" if passing else
               "NOT SHOWABLE (<85% accuracy at every setting with >=50% coverage)" if not at85 else
               "BORDERLINE (85-90% accuracy band or flicker/coverage short)")
    print("\nVERDICT (quality part):", verdict, "| CPU bar p95<=150ms:",
          {k: v["p95_ms"] <= 150 for k, v in cpu.items()})
    (OUT / "sweep.json").write_text(json.dumps({"cpu": cpu, "skipped": skipped, "verdict": verdict,
                                                "results": results}, indent=1))
    print("receipt:", OUT / "sweep.json")


if __name__ == "__main__":
    main()
