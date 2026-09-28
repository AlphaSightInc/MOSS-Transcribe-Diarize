"""Throwaway P53 final identity and word-gate probe. No provider calls.

Run from the worktree with the sibling venv: python .../final_policy.py {vectors,tune,test,vad}.
The test stage requires a frozen selection JSON written after reading tune results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np
import webrtcvad

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "continuity"))
sys.path.insert(0, str(HERE.parent / "harness"))
from corpus import clips  # noqa: E402
from gemini_common import CACHE_DIR, SAMPLE_RATE, _parse, read_wav, wav_bytes, words_to_segments  # noqa: E402
from score import score  # noqa: E402
from measure import embedding_intervals  # noqa: E402
from registry import cosine  # noqa: E402
from h1_offline import score_case  # noqa: E402
from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder  # noqa: E402
from probe import safe_diarization  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53")
VECTORS = EVIDENCE / "final-policy-vectors.json"
TUNE = EVIDENCE / "final-policy-tune.json"
SELECTION = EVIDENCE / "final-policy-selection.json"
TEST = EVIDENCE / "final-policy-test.json"
VAD_RESULT = EVIDENCE / "final-policy-vad.json"
AUDIT = EVIDENCE / "final-policy-pair-audit.json"
MODEL = ROOT / "prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx"
TAUS = (.40, .46, .50, .55, .60, .65, .70, .75, .80)
GAPS = (2.0, 5.0, 10.0, 20.0, 30.0)
VAD_MODE = 1
VAD_FRAME_SAMPLES = 160  # deployed 10 ms at 16 kHz


def population():
    tune, test = [], []
    for c in clips():
        if c.tier == "gold9" and c.clip_id != "benchmark:acquired_jamie_dimon":
            tune.append(c)
        elif c.tier == "bench5m" and c.clip_id.startswith("benchmark_5m:lex_"):
            tune.append(c)
        elif c.tier == "synth":
            (tune if c.clip_id.endswith("_s0") else test).append(c)
        elif c.tier == "accept6" or c.tier == "rtfl" or (c.tier == "long30m" and c.clip_id == "benchmark_30m:lex_bill_ackman"):
            test.append(c)
    return tune, test


@lru_cache(maxsize=40)
def pcm(clip_id):
    c = next(c for c in clips() if c.clip_id == clip_id)
    return read_wav(c.audio)


def cached_words(samples):
    """Read exactly the production-helper cache entry; never fall through to API."""
    mode = {"type": "verbatim", "diarization_mode": "speaker", "timestamp_granularities": ["word"]}
    config = {"transcription_config": {"mode": mode}}
    key = hashlib.sha256(wav_bytes(samples) + json.dumps(["gemini-3.5-transcribe", config], sort_keys=True).encode()).hexdigest()
    path = CACHE_DIR / key[:2] / f"{key}.json"
    if not path.exists():
        raise FileNotFoundError(f"offline cache miss: {path}")
    return _parse(json.loads(path.read_text()), cached=True)


@lru_cache(maxsize=40)
def words(clip_id):
    return cached_words(pcm(clip_id)).words


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))
    print("WROTE", path, flush=True)


def unit(vectors):
    x = np.mean(np.asarray(vectors, dtype=float), axis=0)
    norm = np.linalg.norm(x)
    return (x / norm).tolist() if norm else x.tolist()


def vectors_stage():
    tune, test = population()
    saved = json.loads(VECTORS.read_text()) if VECTORS.exists() else {}
    embedder = _OnnxWeSpeakerEmbedder(MODEL, device="cpu")
    for c in tune + test:
        if c.clip_id in saved:
            print("VECTORS cached", c.clip_id, len(saved[c.clip_id]), flush=True)
            continue
        result = {}
        clip_words = words(c.clip_id)
        for label in sorted({w.speaker for w in clip_words}):
            intervals = embedding_intervals(0, [w.__dict__ for w in clip_words], label)
            if intervals:
                vectors = embedder.embed_intervals(c.audio, intervals)
                result[label] = {"intervals": intervals, "vectors": vectors,
                                 "centroid": unit(vectors)}
        saved[c.clip_id] = result
        write(VECTORS, saved)
        print("VECTORS measured", c.clip_id, "eligible", len(result),
              "labels", len({w.speaker for w in clip_words}), flush=True)


def turns_and_exclusions(clip_words, gap_s):
    turns = sorted(words_to_segments(clip_words), key=lambda x: (x["start"], x["end"]))
    evidence = defaultdict(int)
    for a, b, c in zip(turns, turns[1:], turns[2:]):
        if a["speaker"] != c["speaker"] or a["speaker"] == b["speaker"]:
            continue
        if b["start"] - a["end"] <= gap_s and c["start"] - b["end"] <= gap_s:
            evidence[tuple(sorted((a["speaker"], b["speaker"])))] += 1
    return turns, dict(evidence)


def merge_map(clip_words, label_vectors, tau, gap_s, *, constraint, order):
    labels = sorted({w.speaker for w in clip_words})
    _, motifs = turns_and_exclusions(clip_words, gap_s)
    excluded = set(motifs) if constraint else set()
    groups = {label: {label} for label in labels}
    member = {label: label for label in labels}

    def compatible(a, b):
        return not any(tuple(sorted((x, y))) in excluded for x in groups[a] for y in groups[b])

    def combine(a, b):
        groups[a] |= groups.pop(b)
        for label in groups[a]:
            member[label] = a

    if order == "single":
        pairs = [(a, b, cosine(label_vectors[a]["centroid"], label_vectors[b]["centroid"]))
                 for i, a in enumerate(sorted(label_vectors)) for b in sorted(label_vectors)[i+1:]]
        for a, b, similarity in sorted(pairs, key=lambda x: (-x[2], x[0], x[1])):
            ga, gb = member[a], member[b]
            if similarity >= tau and ga != gb and compatible(ga, gb):
                combine(ga, gb)
    else:
        while True:
            candidates = []
            roots = sorted(k for k in groups if any(x in label_vectors for x in groups[k]))
            centroids = {k: unit([v for label in groups[k] if label in label_vectors
                                  for v in label_vectors[label]["vectors"]]) for k in roots}
            for i, a in enumerate(roots):
                for b in roots[i+1:]:
                    if compatible(a, b):
                        candidates.append((cosine(centroids[a], centroids[b]), a, b))
            if not candidates:
                break
            similarity, a, b = max(candidates, key=lambda x: (x[0], x[1], x[2]))
            if similarity < tau:
                break
            combine(a, b)
    return member, motifs


def truth_support(c, clip_words):
    ref = c.reference_segments()
    support = defaultdict(lambda: defaultdict(float))
    for w in clip_words:
        for row in ref:
            overlap = max(0.0, min(w.end, row["end"]) - max(w.start, row["start"]))
            if overlap:
                support[w.speaker][row["speaker"]] += overlap
    dominant = {}
    for label, votes in support.items():
        speaker, amount = max(votes.items(), key=lambda x: x[1])
        if amount >= .5 and amount / sum(votes.values()) >= .70:
            dominant[label] = speaker
    return dominant, support


def identity_diagnostics(c, clip_words, mapping):
    dominant, support = truth_support(c, clip_words)
    groups = defaultdict(set)
    for label, final_label in mapping.items():
        groups[final_label].add(label)
    false_groups = []
    for final_label, members in groups.items():
        truths = {dominant[m] for m in members if m in dominant}
        if len(truths) > 1:
            false_groups.append({"label": final_label, "members": sorted(members), "truth": sorted(truths)})
    true_to_final = defaultdict(set)
    for label, truth in dominant.items():
        true_to_final[truth].add(mapping[label])
    residual_splits = sum(max(0, len(values)-1) for values in true_to_final.values())
    return {"false_merge_groups": false_groups, "residual_splits": residual_splits,
            "dominant_truth_labels": len(dominant), "unattributed_labels": len(set(mapping)-set(dominant)),
            "truth_to_output_counts": {k: len(v) for k, v in true_to_final.items()}}


def score_policy(c, mapping):
    hyp = words_to_segments(words(c.clip_id), speaker_map=mapping)
    if c.tier == "accept6":
        return score_case(c.clip_id, immediate=[], settled=[], final=hyp)["metrics"]["final"]
    return safe_diarization(c.reference_segments(), hyp)


def case_result(c, label_vectors, tau, gap_s, constraint, order):
    clip_words = words(c.clip_id)
    mapping, motifs = merge_map(clip_words, label_vectors, tau, gap_s,
                                constraint=constraint, order=order)
    scored = score_policy(c, mapping)
    diagnostic = identity_diagnostics(c, clip_words, mapping)
    return {"clip_id": c.clip_id, "tier": c.tier, "truth_speakers": len({x["speaker"] for x in c.reference_segments()}),
            "input_labels": len(mapping), "eligible_labels": len(label_vectors),
            "output_labels": len(set(mapping.values())), "der": scored["der"],
            "miss": scored.get("miss"), "false_alarm": scored.get("false_alarm"),
            "speaker_confusion": scored.get("speaker_confusion"),
            "motif_pairs": len(motifs), "motif_counts": {"|".join(k): v for k, v in motifs.items()},
            "mapping": mapping, **diagnostic}


def evaluate_cases(cases, vectors, tau, gap_s, constraint, order):
    rows = []
    for c in cases:
        row = case_result(c, vectors[c.clip_id], tau, gap_s, constraint, order)
        rows.append(row)
        print("CASE", c.clip_id, "DER", row["der"], "labels", row["input_labels"],
              "->", row["output_labels"], "false", len(row["false_merge_groups"]),
              "splits", row["residual_splits"], flush=True)
    return rows


def summary(rows):
    # rtfl90 is the same PCM as accept6 discussion_rtfl_90s: retain its row,
    # but do not count the recording twice in the real macro.
    real = [r for r in rows if r["tier"] not in ("synth", "rtfl")]
    synth = [r for r in rows if r["tier"] == "synth"]
    return {"real_n": len(real), "real_macro_der": float(np.mean([r["der"] for r in real])),
            "real_false_merge_groups": sum(len(r["false_merge_groups"]) for r in real),
            "real_residual_splits": sum(r["residual_splits"] for r in real),
            "synth_n": len(synth), "synth_macro_der": float(np.mean([r["der"] for r in synth])) if synth else None,
            "synth_false_merge_groups": sum(len(r["false_merge_groups"]) for r in synth),
            "synth_residual_splits": sum(r["residual_splits"] for r in synth)}


def tune_stage():
    tune, _ = population()
    vectors = json.loads(VECTORS.read_text())
    rows = []
    for tau in TAUS:
        for constraint in (False, True):
            for gap_s in (GAPS if constraint else (0.0,)):
                for order in ("single", "agglomerate"):
                    print("TUNE POLICY", tau, gap_s, constraint, order, flush=True)
                    cases = evaluate_cases(tune, vectors, tau, gap_s, constraint, order)
                    row = {"tau": tau, "gap_s": gap_s, "constraint": constraint,
                           "order": order, "summary": summary(cases), "cases": cases}
                    rows.append(row)
                    write(TUNE, {"population": [c.clip_id for c in tune], "policies": rows})


def test_stage():
    if not SELECTION.exists():
        raise RuntimeError(f"freeze tune selection first: {SELECTION}")
    selection = json.loads(SELECTION.read_text())
    _, test = population()
    vectors = json.loads(VECTORS.read_text())
    policies = [("pure", {"tau": 2.0, "gap_s": 0.0, "constraint": False, "order": "single"}),
                ("selected", selection)]
    output = {"selection": selection, "population": [c.clip_id for c in test], "arms": {}}
    for name, spec in policies:
        print("TEST", name, spec, flush=True)
        cases = evaluate_cases(test, vectors, **spec)
        output["arms"][name] = {"summary": summary(cases), "cases": cases}
        write(TEST, output)


def pair_audit(c, label_vectors, tau, gap_s):
    dominant, _ = truth_support(c, words(c.clip_id))
    _, motifs = turns_and_exclusions(words(c.clip_id), gap_s)
    pairs = []
    labels = sorted(label_vectors)
    for i, a in enumerate(labels):
        for b in labels[i+1:]:
            similarity = cosine(label_vectors[a]["centroid"], label_vectors[b]["centroid"])
            if similarity < tau:
                continue
            pair = tuple(sorted((a, b)))
            relation = ("same" if dominant[a] == dominant[b] else "different") if a in dominant and b in dominant else "unknown"
            pairs.append({"labels": pair, "cosine": similarity, "truth_relation": relation,
                          "true_speakers": [dominant.get(a), dominant.get(b)],
                          "converse_motifs": motifs.get(pair, 0)})
    return pairs


def audit_stage():
    if not SELECTION.exists():
        raise RuntimeError(f"freeze tune selection first: {SELECTION}")
    selected = json.loads(SELECTION.read_text())
    vectors = json.loads(VECTORS.read_text())
    tune, test = population()
    output = {"selection": selected, "tune": {}, "test": {}}
    for part, cases in (("tune", tune), ("test", test)):
        for c in cases:
            output[part][c.clip_id] = pair_audit(c, vectors[c.clip_id], selected["tau"], selected["gap_s"])
        high = [p for pairs in output[part].values() for p in pairs]
        print("AUDIT", part, "high_pairs", len(high),
              "same_converse", sum(p["truth_relation"] == "same" and p["converse_motifs"] for p in high),
              "different_no_converse", sum(p["truth_relation"] == "different" and not p["converse_motifs"] for p in high),
              flush=True)
    write(AUDIT, output)


def voiced_mask(samples):
    vad = webrtcvad.Vad(VAD_MODE)
    return np.array([vad.is_speech(samples[i:i+VAD_FRAME_SAMPLES].tobytes(), SAMPLE_RATE)
                     for i in range(0, len(samples)-VAD_FRAME_SAMPLES+1, VAD_FRAME_SAMPLES)], dtype=bool)


def silent_stretches(mask, min_frames=50):
    spans = []
    start = None
    for i, voiced in enumerate(mask):
        if not voiced and start is None:
            start = i
        elif voiced and start is not None:
            if i-start >= min_frames:
                spans.append((start/100, i/100))
            start = None
    if start is not None and len(mask)-start >= min_frames:
        spans.append((start/100, len(mask)/100))
    return spans


def gate_words(clip_words, mask, *, offset=0.0):
    kept, dropped = [], []
    for w in clip_words:
        lo = max(0, math.floor((offset + w.start - .2) * 100))
        hi = min(len(mask), math.ceil((offset + w.end + .2) * 100))
        (kept if np.any(mask[lo:hi]) else dropped).append(w)
    return kept, dropped


def generated_signals():
    n = 30*SAMPLE_RATE
    x = np.arange(n, dtype=np.float64)/SAMPLE_RATE
    chord = .18*np.sin(2*np.pi*220*x)+.12*np.sin(2*np.pi*277.18*x)+.10*np.sin(2*np.pi*329.63*x)
    gate = ((x % .5) < .35).astype(float)
    rng = np.random.default_rng(53)
    return {"silence": np.zeros(n, dtype=np.int16),
            "music_like": np.int16(np.clip(chord*gate, -1, 1)*32767),
            "white_noise": np.int16(rng.normal(0, .01, n)*32767)}


def vad_stage():
    tune, test = population()
    real = [c for c in tune+test if c.tier in ("accept6", "gold9", "bench5m")]
    output = {"configuration": {"vad_mode": VAD_MODE, "frame_ms": 10, "sample_rate": SAMPLE_RATE,
                                   "word_pad_s": .2}, "real_cases": [], "generated": [], "e1": {}}
    for c in real:
        clip_words = words(c.clip_id)
        mask = voiced_mask(pcm(c.clip_id))
        kept, dropped = gate_words(clip_words, mask)
        ref = c.reference_segments()
        within_ref = sum(any(max(w.start, r["start"]) < min(w.end, r["end"]) for r in ref)
                         for w in dropped)
        base_hyp = words_to_segments(clip_words)
        base = (score_case(c.clip_id, immediate=[], settled=[], final=base_hyp)["metrics"]["final"]
                if c.tier == "accept6" else score(ref, base_hyp))
        after_hyp = words_to_segments(kept)
        after = (score_case(c.clip_id, immediate=[], settled=[], final=after_hyp)["metrics"]["final"]
                 if c.tier == "accept6" else score(ref, after_hyp))
        row = {"clip_id": c.clip_id, "tier": c.tier, "words": len(clip_words),
               "dropped": len(dropped), "dropped_in_reference_speech": within_ref,
               "dropped_examples": [[w.text,w.start,w.end] for w in dropped[:20]],
               "der_before": base["der"], "der_after": after["der"],
               "wer_before": base.get("wer"), "wer_after": after.get("wer"),
               "voiced_frames": int(np.sum(mask)), "total_frames": len(mask)}
        output["real_cases"].append(row)
        write(VAD_RESULT, output)
        print("VAD REAL", c.clip_id, len(dropped), "/", len(clip_words), "ref", within_ref, flush=True)
    for name, samples in generated_signals().items():
        mask = voiced_mask(samples)
        clip_words = cached_words(samples).words
        kept, dropped = gate_words(clip_words, mask)
        output["generated"].append({"signal": name, "words_before": len(clip_words),
                                     "words_after": len(kept), "dropped": [[w.text,w.start,w.end] for w in dropped],
                                     "voiced_frames": int(np.sum(mask)), "total_frames": len(mask)})
        print("VAD GENERATED", name, len(clip_words), "->", len(kept), flush=True)
    e1 = clips("e1")[0]
    samples = pcm(e1.clip_id)
    mask = voiced_mask(samples)
    duration = len(samples)/SAMPLE_RATE
    starts = [max(0.0, t-30.0) for t in list(np.arange(10.0, duration, 10.0))+[duration]]
    ends = list(np.arange(10.0, duration, 10.0))+[duration]
    stretches = silent_stretches(mask)
    total_words = total_dropped = silent_words = silent_dropped = 0
    examples = []
    for start, end in zip(starts, ends):
        clip_words = cached_words(samples[round(start*SAMPLE_RATE):round(end*SAMPLE_RATE)]).words
        kept, dropped = gate_words(clip_words, mask, offset=start)
        total_words += len(clip_words)
        total_dropped += len(dropped)
        for w in clip_words:
            middle = start+(w.start+w.end)/2
            if any(lo <= middle < hi for lo, hi in stretches):
                silent_words += 1
                if w in dropped:
                    silent_dropped += 1
        examples.extend([[w.text,start+w.start,start+w.end] for w in dropped[:4]])
    output["e1"] = {"windows": len(starts), "window_word_observations": total_words,
                     "dropped": total_dropped, "midpoint_unvoiced_words": silent_words,
                     "midpoint_unvoiced_dropped": silent_dropped, "dropped_examples": examples[:30],
                     "silent_stretches_ge_0_5s": stretches,
                     "voiced_frames": int(np.sum(mask)), "total_frames": len(mask),
                     "truth": "E1 has speaker count only; no word-level reference"}
    write(VAD_RESULT, output)
    print("VAD E1", total_dropped, "/", total_words, "midpoint silent", silent_dropped,
          "/", silent_words, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("vectors", "tune", "test", "audit", "vad"))
    args = parser.parse_args()
    globals()[args.stage + "_stage"]()


if __name__ == "__main__":
    main()
