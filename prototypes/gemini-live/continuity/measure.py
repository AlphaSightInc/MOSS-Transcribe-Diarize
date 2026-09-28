"""One-command P61 rolling-window continuity measurement (public corpus only).

Run from worktree: PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/gemini-live/continuity/measure.py --tier accept6
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from common.corpus import clips  # noqa: E402
from common.gemini_common import Word, diarize_window, read_wav, spend, words_to_segments  # noqa: E402
from common.score import score  # noqa: E402
from registry import SpeakerRegistry, assignment  # noqa: E402
from moss_transcribe_diarize import evaluation  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P61")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-6.1-STATUS.md")


def note(message):
    with STATUS.open("a") as f:
        f.write(f"{datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} | {message}\n")


def windows(pcm, step_s, length_s):
    duration = len(pcm) / 16000
    times = list(np.arange(step_s, duration, step_s)) + [duration]
    for t in times:
        start = max(0.0, t - length_s)
        part = pcm[round(start * 16000):round(t * 16000)]
        yield round(start, 4), round(t, 4), part


def percentile(values, p):
    return round(float(np.percentile(values, p)), 3) if values else None


def segmentize(rows):
    """Use the shared Gemini word grouping before production DER scoring."""
    ordered = sorted(rows, key=lambda w: (w["start"], w["end"]))
    return words_to_segments([Word(w["text"], w["speaker"], w["start"], w["end"])
                              for w in ordered])


def polynomial_assignment(row_labels, column_labels, weights):
    """Exact maximum-weight objective for the production scorer at large label counts."""
    columns = list(column_labels)
    if len(columns) < len(row_labels):
        columns.extend(f"<HYP_PAD_{index:03d}>"
                       for index in range(1, len(row_labels) - len(columns) + 1))
    matrix = [[weights.get((row, col), 0.0) for col in columns] for row in row_labels]
    selected = assignment(matrix)
    mapping = {row: columns[col] if col is not None else None
               for row, col in zip(row_labels, selected)}
    matched = sum(matrix[i][col] for i, col in enumerate(selected) if col is not None)
    return mapping, matched


def measured_score(reference, hypothesis):
    if len({w["speaker"] for w in hypothesis}) <= 12:
        return score(reference, hypothesis)
    # The production scorer calls this module-global assignment function. Replace
    # only its exponential optimizer in this offline measurement process.
    with patch.object(evaluation, "_maximum_weight_assignment", polynomial_assignment):
        return score(reference, hypothesis)


def evaluate(reference, observations, hold_s, threshold, embedding_threshold=None,
             within_window_threshold=None, reuse_overlap=False, include_segments=False):
    registry = SpeakerRegistry(min_overlap_s=threshold, embedding_threshold=embedding_threshold,
                               within_window_threshold=within_window_threshold,
                               reuse_overlap=reuse_overlap)
    first, revised, latency, latency_with_api = [], [], [], []
    visible_relabels = 0
    frontier = 0.0
    state = []
    preview = []
    for n, obs in enumerate(observations):
        start, t, words = obs["start"], obs["end"], obs["words"]
        mapping, relabels = registry.observe_window(start, words, obs.get("embeddings"))
        new_frontier = max(0.0, t - hold_s)
        absolute = [{"start": start + w["start"], "end": start + w["end"],
                     "speaker": mapping[w["speaker"]], "text": w["text"]} for w in words]
        preview = [w for w in absolute if w["end"] > new_frontier]
        fresh = [w for w in absolute if frontier < w["end"] <= new_frontier]
        first.extend(fresh)
        latency.extend(t - w["end"] for w in fresh)
        latency_with_api.extend(t + obs["api_latency_s"] - w["end"] for w in fresh)
        # Latest observation replaces already shown words only inside this audio window.
        changed_pairs = set()
        for old in revised:
            if old["end"] <= start or old["end"] > new_frontier:
                continue
            best = max(absolute, key=lambda new: min(old["end"], new["end"]) -
                       max(old["start"], new["start"]), default=None)
            if best and min(old["end"], best["end"]) > max(old["start"], best["start"]):
                if old["speaker"] != best["speaker"]:
                    changed_pairs.add((old["speaker"], best["speaker"]))
        visible_relabels += len(changed_pairs)
        revised = [w for w in revised if w["end"] <= start or w["end"] > new_frontier]
        revised.extend(w for w in absolute if w["end"] <= new_frontier)
        revised.sort(key=lambda w: (w["start"], w["end"]))
        frontier = new_frontier
        state.append({"window": n + 1, "start": start, "end": t,
                      "labels": mapping, "births_total": registry.births,
                      "committed": len(fresh), "frontier": round(frontier, 3),
                      "relabels": relabels, "visible_relabel_pairs": len(changed_pairs)})
    first.sort(key=lambda w: (w["start"], w["end"]))
    first_immediate = sorted(first + preview, key=lambda w: (w["start"], w["end"]))
    last_immediate = sorted(revised + preview, key=lambda w: (w["start"], w["end"]))
    first_score = measured_score(reference, segmentize(first)) if reference else None
    revised_score = measured_score(reference, segmentize(revised)) if reference else None
    result = {"first": first_score, "last_revised": revised_score,
            "first_word_count": len(first), "last_word_count": len(revised),
            "speaker_count": len({w["speaker"] for w in first}), "births": registry.births,
            "immediate_speaker_count": len({w["speaker"] for w in first_immediate}),
            "merges": registry.merges, "local_merges": registry.local_merges,
            "overlap_reuses": registry.overlap_reuses,
            "visible_relabel_events": visible_relabels,
            "visible_relabels_per_minute": round(visible_relabels * 60 / observations[-1]["end"], 3),
            "latency_p50_s": percentile(latency, 50),
            "latency_p90_s": percentile(latency, 90),
            "latency_with_api_p50_s": percentile(latency_with_api, 50),
            "latency_with_api_p90_s": percentile(latency_with_api, 90), "state": state}
    if include_segments:
        result["first_words"] = first
        result["last_revised_words"] = revised
        result["first_segments"] = segmentize(first)
        result["last_revised_segments"] = segmentize(revised)
        result["first_immediate_segments"] = segmentize(first_immediate)
        result["last_immediate_segments"] = segmentize(last_immediate)
    return result


def embedding_intervals(start, words, label):
    """Continuous Gemini-attributed speech spans of at least 2 seconds (L1)."""
    spans = sorted((start + w["start"], start + w["end"])
                   for w in words if w["speaker"] == label and w["end"] > w["start"])
    merged = []
    for s, e in spans:
        if merged and s - merged[-1][1] <= 0.6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return [(s, min(e, s + 10.0)) for s, e in merged if e - s >= 2.0][:3]


def add_embeddings(clip, observations, mixed_pcm=None):
    from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
    onnx = HERE.parents[1] / "streaming-diarization" / "data" / "voxceleb_resnet152_LM.onnx"
    loader = (lambda _: (mixed_pcm.astype(np.float32) / 32768.0, 16000)) if mixed_pcm is not None else None
    embedder = _OnnxWeSpeakerEmbedder(onnx, device="cpu", audio_loader=loader)
    count = 0
    for obs in observations:
        obs["embeddings"] = {}
        for label in {w["speaker"] for w in obs["words"]}:
            intervals = embedding_intervals(obs["start"], obs["words"], label)
            if intervals:
                obs["embeddings"][label] = embedder.embed(clip.audio, intervals)
                count += 1
    return count


def cached_embeddings(clip, observations, step_s, length_s, mix_mic, mixed_pcm):
    """Keep numeric vectors so registry policy sweeps do not rerun ONNX."""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    path = EVIDENCE / f"vectors-span2s-{clip.tier}-{clip.clip_id}-S{step_s:g}-L{length_s:g}{'-mix' if mix_mic else ''}.json"
    if path.exists():
        rows = json.loads(path.read_text())
        if [(r["start"], r["end"]) for r in rows] != [(r["start"], r["end"]) for r in observations]:
            raise ValueError(f"vector receipt window schedule mismatch: {path}")
        for obs, row in zip(observations, rows):
            obs["embeddings"] = row["embeddings"]
        return sum(len(r["embeddings"]) for r in rows), True
    count = add_embeddings(clip, observations, mixed_pcm if mix_mic else None)
    path.write_text(json.dumps([{"start": r["start"], "end": r["end"],
                                 "embeddings": r["embeddings"]} for r in observations]))
    return count, False


def run_case(clip, step_s, length_s, holds, thresholds, embedding_thresholds,
             within_thresholds, mix_mic=False, skip_score=False, reuse_overlap=False):
    pcm = read_wav(clip.audio)
    if mix_mic:
        if clip.mic_audio is None:
            raise ValueError("--mix-mic requires E1 microphone fixture")
        mic = read_wav(clip.mic_audio)
        if len(mic) != len(pcm):
            raise ValueError("E1 system/mic lengths differ")
        pcm = np.clip(pcm.astype(np.int32) + mic.astype(np.int32), -32768, 32767).astype(np.int16)
    observations = []
    actual_cost = 0.0
    theoretical_cost = 0.0
    cache_hits = 0
    for n, (start, t, part) in enumerate(windows(pcm, step_s, length_s), 1):
        result = diarize_window(part, ledger_lane="P61", max_attempts=3)
        theoretical_cost += result.cost_usd()
        if result.cached:
            cache_hits += 1
        else:
            actual_cost += result.cost_usd()
        obs = {"start": start, "end": t,
               "words": [vars(w) for w in result.words], "cached": result.cached,
               "api_latency_s": result.latency_s, "cost_usd": result.cost_usd(),
               "timing_anomalies": result.timing_anomalies or {"clamped": 0, "dropped": 0}}
        observations.append(obs)
        print(json.dumps({"case": clip.clip_id, "window": n, "start": start,
                          "end": t, "words": len(result.words), "labels":
                          sorted({w.speaker for w in result.words}), "cached": result.cached,
                          "api_latency_s": round(result.latency_s, 3),
                          "timing_anomalies": obs["timing_anomalies"],
                          "timing_anomaly_rate": round(sum(obs["timing_anomalies"].values()) /
                                                       max(1, len(result.words) + obs["timing_anomalies"]["dropped"]), 6),
                          "theoretical_cost_usd": round(theoretical_cost, 5)}), flush=True)
    reference = [] if skip_score else clip.reference_segments()
    embedding_count, embeddings_cached = (cached_embeddings(clip, observations, step_s, length_s, mix_mic, pcm)
                                          if embedding_thresholds else (0, False))
    variants = {}
    for hold in holds:
        for threshold in thresholds:
            name = f"C1_S{step_s:g}_L{length_s:g}_H{hold:g}_T{threshold:g}"
            variants[name] = evaluate(reference, observations, hold, threshold)
            if reuse_overlap:
                variants[name + "+reuse"] = evaluate(reference, observations, hold, threshold,
                                                      reuse_overlap=True)
            for eth in embedding_thresholds:
                name = f"C1+C3_S{step_s:g}_L{length_s:g}_H{hold:g}_T{threshold:g}_E{eth:g}"
                variants[name] = evaluate(reference, observations, hold, threshold, eth)
                for wth in within_thresholds:
                    name = f"C1+C3+local_S{step_s:g}_L{length_s:g}_H{hold:g}_T{threshold:g}_E{eth:g}_W{wth:g}"
                    variants[name] = evaluate(reference, observations, hold, threshold, eth, wth)
                    if reuse_overlap:
                        variants[name + "+reuse"] = evaluate(reference, observations, hold,
                                                              threshold, eth, wth, True)
    duration = len(pcm) / 16000
    result = {"case": clip.clip_id, "tier": clip.tier, "duration_s": duration,
              "reference_speakers": len({w["speaker"] for w in reference}) if reference else
              (4 if mix_mic else 3) if clip.tier == "e1" else clip.true_speakers,
              "mic_mixed": mix_mic,
              "score_skipped": skip_score,
              "windows": len(observations), "cache_hits": cache_hits,
              "timing_anomalies": {key: sum(x["timing_anomalies"][key] for x in observations)
                                   for key in ("clamped", "dropped")},
              "timing_anomaly_windows": sum(any(x["timing_anomalies"].values()) for x in observations),
              "timing_words": sum(len(x["words"]) for x in observations),
              "embedding_observations": embedding_count,
              "embeddings_cached": embeddings_cached,
              "audio_sent_s": sum(x["end"] - x["start"] for x in observations),
              "actual_cost_usd": actual_cost, "theoretical_cost_usd": theoretical_cost,
              "cost_per_meeting_hour_usd": theoretical_cost * 3600 / duration,
              "api_latency_p50_s": percentile([x["api_latency_s"] for x in observations], 50),
              "variants": variants}
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    output = EVIDENCE / f"{clip.tier}-{clip.clip_id}-S{step_s:g}-L{length_s:g}{'-mix' if mix_mic else ''}{'-C3-span2s' if embedding_thresholds else ''}{'-no-score' if skip_score else ''}.json"
    output.write_text(json.dumps(result, indent=2))
    note(f"{clip.clip_id}: {len(observations)} windows ({cache_hits} cached), "
         f"{result['audio_sent_s']:.1f} audio-s, actual ${actual_cost:.4f}, "
         f"modeled ${theoretical_cost:.4f}, P61 cumulative {spend('P61').get('P61', {})}; "
         f"receipt {output.name}")
    print(json.dumps({k: v for k, v in result.items() if k != "variants"}), flush=True)
    for name, value in variants.items():
        print(json.dumps({"case": clip.clip_id, "variant": name,
                          "first": value["first"], "last_revised": value["last_revised"],
                          "births": value["births"], "speaker_count": value["speaker_count"],
                          "latency_p50_s": value["latency_p50_s"]}), flush=True)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default="accept6", choices=["accept6", "gold9", "bench5m", "long30m", "rtfl", "synth", "e1"])
    ap.add_argument("--case", default="")
    ap.add_argument("--step", type=float, default=10)
    ap.add_argument("--length", type=float, default=30)
    ap.add_argument("--holds", type=float, nargs="+", default=[5, 10])
    ap.add_argument("--thresholds", type=float, nargs="+", default=[0.3, 0.6, 1.2])
    ap.add_argument("--embedding-thresholds", type=float, nargs="*", default=[])
    ap.add_argument("--within-thresholds", type=float, nargs="*", default=[])
    ap.add_argument("--mix-mic", action="store_true")
    ap.add_argument("--skip-score", action="store_true")
    ap.add_argument("--overlap-reuse", action="store_true")
    args = ap.parse_args()
    selected = [c for c in clips(args.tier) if not args.case or args.case in c.clip_id]
    note(f"Start {args.tier}, {len(selected)} cases, S={args.step:g} L={args.length:g}, "
         f"H={args.holds}, thresholds={args.thresholds}, embedding_thresholds={args.embedding_thresholds}, "
         f"within_thresholds={args.within_thresholds}, "
         f"mix_mic={args.mix_mic}, skip_score={args.skip_score}, "
         f"overlap_reuse={args.overlap_reuse}; "
         f"P61 starting {spend('P61').get('P61', {})}")
    for clip in selected:
        run_case(clip, args.step, args.length, args.holds, args.thresholds,
                 args.embedding_thresholds, args.within_thresholds, args.mix_mic,
                 args.skip_score, args.overlap_reuse)
