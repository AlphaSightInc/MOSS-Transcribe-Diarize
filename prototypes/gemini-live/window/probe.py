"""THROWAWAY P53 Gemini window measurement. Run from worktree: python .../probe.py all.

Each finished item is a JSONL receipt. Re-running skips finished items; latency
uses uncached calls and records exactly one result for each planned call.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "common"))
sys.path.insert(0, str(HERE.parent / "continuity"))
sys.path.insert(0, str(HERE.parent / "harness"))
from corpus import clips  # noqa: E402
from gemini_common import (  # noqa: E402
    SAMPLE_RATE, Word, client, diarize_window, read_wav, spend,
    wav_bytes, words_to_segments, ledger,
)
from score import score  # noqa: E402
from moss_transcribe_diarize.evaluation import _tokenize, _wer  # noqa: E402
from moss_transcribe_diarize.evaluation import _round_metric  # noqa: E402
from measure import embedding_intervals  # noqa: E402
from registry import cosine  # noqa: E402
from h1_offline import score_case as h1_score_case  # noqa: E402

RECEIPT = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53/measurements.jsonl")
BASELINE = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1c-20260924T013646Z/20260924T013946Z-8d8fb68/raw/deployed-collector/artifacts/quality/content-free-metrics.json")
LANE = "P53"


@lru_cache(maxsize=40)
def audio(clip_id):
    c = next(c for c in clips() if c.clip_id == clip_id)
    return read_wav(c.audio)


def piece(clip_id, start, end):
    a = audio(clip_id)
    return a[round(start * SAMPLE_RATE):min(len(a), round(end * SAMPLE_RATE))]


def reference(clip, start, end, *, relative=True):
    out = []
    for r in clip.reference_segments():
        s, e = max(start, r["start"]), min(end, r["end"])
        if e > s:
            out.append({"start": s - start if relative else s,
                        "end": e - start if relative else e,
                        "speaker": r["speaker"], "text": r["text"]})
    return out


def receipts():
    if not RECEIPT.exists():
        return {}
    return {r["key"]: r for line in RECEIPT.read_text().splitlines()
            if (r := json.loads(line)).get("key")}


def save(row):
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    with RECEIPT.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    print(json.dumps(row, default=str), flush=True)


def call(pcm, *, use_cache=True):
    if spend(LANE).get(LANE, {}).get("cost_usd", 0) > 24.5:
        raise RuntimeError("P53 spend cap guard")
    return diarize_window(pcm, ledger_lane=LANE, use_cache=use_cache, max_attempts=3)


def valid_words(words, duration):
    return [w for w in words if w.start >= -.5 and w.end <= duration + .5
            and w.end >= w.start]


def fast_diarization(reference_rows, hypothesis_rows):
    """Exact production DER assignment, with polynomial optimization for many labels."""
    from scipy.optimize import linear_sum_assignment

    ref = [r for r in reference_rows if r["end"] > r["start"]]
    hyp = [h for h in hypothesis_rows if h["end"] > h["start"]]
    rlabels = sorted({r["speaker"] for r in ref})
    hlabels = sorted({h["speaker"] for h in hyp})
    weight = np.zeros((len(rlabels), max(len(rlabels), len(hlabels))), dtype=float)
    rix = {label: i for i, label in enumerate(rlabels)}
    hix = {label: i for i, label in enumerate(hlabels)}
    overlap_by_pair = []
    for r in ref:
        for h in hyp:
            overlap = max(0.0, min(r["end"], h["end"]) - max(r["start"], h["start"]))
            if overlap:
                weight[rix[r["speaker"]], hix[h["speaker"]]] += overlap
                overlap_by_pair.append((r["speaker"], h["speaker"], overlap))
    if rlabels:
        rr, cc = linear_sum_assignment(-weight)
        mapping = {rlabels[i]: hlabels[j] if j < len(hlabels) else None
                   for i, j in zip(rr, cc)}
    else:
        mapping = {}
    reference_duration = sum(r["end"]-r["start"] for r in ref)
    hypothesis_duration = sum(h["end"]-h["start"] for h in hyp)
    overlapped = sum(x[2] for x in overlap_by_pair)
    confusion = sum(duration for rs, hs, duration in overlap_by_pair
                    if mapping.get(rs) != hs)
    miss = max(reference_duration - overlapped, 0.0)
    false_alarm = max(hypothesis_duration - overlapped, 0.0)
    confusion = min(confusion, reference_duration)
    def ratio(x):
        return _round_metric(x/reference_duration) if reference_duration else 0.0
    return {"ref_speakers": len(rlabels), "hyp_speakers": len(hlabels),
            "der": ratio(miss+false_alarm+confusion), "miss": ratio(miss),
            "false_alarm": ratio(false_alarm), "speaker_confusion": ratio(confusion)}


def safe_diarization(reference_rows, hypothesis_rows):
    labels = len({h["speaker"] for h in hypothesis_rows})
    if labels > 20:
        return fast_diarization(reference_rows, hypothesis_rows)
    return score(reference_rows, hypothesis_rows, with_text=False)


def quantile(values, q):
    if not values:
        return None
    return float(np.quantile(values, q))


def latency_plan():
    bench = clips("bench5m")
    synth = clips("synth")
    long = clips("long30m")
    for length in (10, 20, 30, 60, 90, 120, 180, 300, 600, 1200, 1800):
        if length <= 300:
            sources = [(c.clip_id, 0, length, None) for c in bench[:5]]
        elif length == 600:
            sources = [(c.clip_id, 0, length, None) for c in synth[:5]]
        elif length == 1200:
            sources = [(long[i % 2].clip_id, (i // 2) * 300, (i // 2) * 300 + length, None)
                       for i in range(5)]
        else:
            sources = [(c.clip_id, 0, length, None) for c in long]
            # Three distinct permutations of K2+K2+K3 public synthetic clips:
            # at most seven source speakers, inside the documented eight-speaker
            # diarization limit. Latency only; no quality claim.
            for order in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
                sources.append(("synthetic-concat", 0, length,
                                [synth[j].clip_id for j in order]))
        for concurrency in (1, 2, 4):
            for index, (clip_id, start, end, parts) in enumerate(sources):
                yield {"length": length, "concurrency": concurrency, "index": index,
                       "clip_id": clip_id, "start": start, "end": end, "parts": parts}


def latency():
    existing = receipts()
    by_group = defaultdict(list)
    for task in latency_plan():
        by_group[(task["length"], task["concurrency"])].append(task)
    for (length, concurrency), tasks in by_group.items():
        todo = []
        for t in tasks:
            key = f"latency:{length}:{concurrency}:{t['index']}"
            if key not in existing:
                todo.append((key, t))
        def execute(item):
            key, t = item
            if t["parts"]:
                pcm = np.concatenate([audio(cid) for cid in t["parts"]])[:length * SAMPLE_RATE]
            else:
                pcm = piece(t["clip_id"], t["start"], t["end"])
            r = call(pcm, use_cache=False)
            return {"key": key, "kind": "latency", **t, "audio_s": len(pcm) / SAMPLE_RATE,
                    "latency_s": r.latency_s, "words": len(r.words), "cost_usd": r.cost_usd()}
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = [pool.submit(execute, item) for item in todo]
            for future in as_completed(futures):
                try:
                    save(future.result())
                except Exception as exc:
                    save({"kind": "failure", "stage": "latency", "length": length,
                          "concurrency": concurrency, "error": str(exc)[:300]})
        rows = [r for r in receipts().values() if r.get("kind") == "latency"
                and r["length"] == length and r["concurrency"] == concurrency]
        save({"kind": "latency_summary", "length": length, "concurrency": concurrency,
              "n": len(rows), "p50_s": quantile([r["latency_s"] for r in rows], .5),
              "p90_s": quantile([r["latency_s"] for r in rows], .9)})


def quality_lengths(clip):
    return (10, 20, 30, 60, 90, 120) if clip.tier != "synth" else (30, 60, 120, 300)


def quality():
    population = [c for c in clips() if c.tier in ("accept6", "gold9", "rtfl")
                  or c.tier == "synth" and c.true_speakers in (4, 6)]
    existing = receipts()
    tasks = []
    for c in population:
        duration = len(audio(c.clip_id)) / SAMPLE_RATE
        for length in quality_lengths(c):
            for index in range(math.ceil(duration / length)):
                start, end = index * length, min((index + 1) * length, duration)
                if end - start < 5:
                    continue
                key = f"quality:{c.clip_id}:{length}:{index}"
                if key in existing:
                    continue
                tasks.append((key, c, length, index, start, end))
    def execute(task):
        key, c, length, index, start, end = task
        r = call(piece(c.clip_id, start, end))
        ref = reference(c, start, end)
        hyp = words_to_segments(r.words)
        result = safe_diarization(ref, hyp)
        clean = valid_words(r.words, end-start)
        result_valid = safe_diarization(ref, words_to_segments(clean))
        invalid = sum(w.start < -0.001 or w.end > end - start + .001
                      or w.end < w.start for w in r.words)
        overlaps = sum(r.words[i].start < r.words[i-1].end - .001
                       for i in range(1, len(r.words)))
        edge = {}
        for side, lo, hi in (("first", 0, min(2, end-start)),
                             ("middle", min(2, end-start), max(2, end-start-2)),
                             ("last", max(0, end-start-2), end-start)):
            er = [{"start": max(x["start"], lo)-lo, "end": min(x["end"], hi)-lo,
                   "speaker": x["speaker"], "text": ""}
                  for x in ref if min(x["end"], hi) > max(x["start"], lo)]
            eh = [{"start": max(x["start"], lo)-lo, "end": min(x["end"], hi)-lo,
                   "speaker": x["speaker"], "text": ""}
                  for x in hyp if min(x["end"], hi) > max(x["start"], lo)]
            edge[side] = safe_diarization(er, eh)
        return {"key": key, "kind": "quality", "tier": c.tier, "clip_id": c.clip_id,
                "length": length, "start": start, "end": end,
                "reference_speech_s": sum(x["end"]-x["start"] for x in ref),
                "result": result, "result_valid": result_valid,
                "edge": edge, "words": len(r.words),
                "out_of_window_words": invalid, "overlapping_word_pairs": overlaps,
                "latency_s": r.latency_s, "cached": r.cached,
                "cost_usd": 0 if r.cached else r.cost_usd()}
    client()  # create once before worker threads; avoids SDK client teardown race
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(execute, t): t for t in tasks}
        for future in as_completed(futures):
            try:
                save(future.result())
            except Exception as exc:
                key, c, length, index, start, end = futures[future]
                save({"kind": "failure", "stage": "quality", "clip_id": c.clip_id,
                      "length": length, "index": index, "error": str(exc)[:300]})


def final():
    population = [c for c in clips() if c.tier in
                  ("accept6", "gold9", "bench5m", "rtfl", "synth", "long30m")]
    existing = receipts()
    baseline = json.loads(BASELINE.read_text())
    baseline_by_id = {r["case_id"]: r["metrics"]["final"] for r in baseline["per_case"]
                      if r.get("pass") == 1}
    for c in population:
        key = f"final:{c.clip_id}"
        if key in existing:
            continue
        try:
            r = call(audio(c.clip_id))
            ref = c.reference_segments()
            hyp = words_to_segments(r.words)
            result = score(ref, hyp)
            save({"key": key, "kind": "final", "tier": c.tier, "clip_id": c.clip_id,
                  "audio_s": len(audio(c.clip_id)) / SAMPLE_RATE,
                  "result": result, "moss_h1_final": baseline_by_id.get(c.clip_id),
                  "words": len(r.words), "latency_s": r.latency_s,
                  "cached": r.cached, "cost_usd": 0 if r.cached else r.cost_usd()})
        except Exception as exc:
            save({"kind": "failure", "stage": "final", "clip_id": c.clip_id,
                  "error": str(exc)[:300]})


def determinism():
    c = clips("accept6")[1]
    pcm = piece(c.clip_id, 0, 60)
    existing = receipts()
    for i in range(2):
        if f"repeat:{i}" in existing:
            continue
        r = call(pcm, use_cache=False)
        save({"key": f"repeat:{i}", "kind": "repeat", "clip_id": c.clip_id,
              "words": [w.__dict__ for w in r.words], "latency_s": r.latency_s,
              "timing_anomalies": r.timing_anomalies,
              "cost_usd": r.cost_usd()})


def _speaker_at(ref, midpoint):
    for x in ref:
        if x["start"] <= midpoint < x["end"]:
            return x["speaker"]
    return None


def anchor_plan():
    # Earlier continuous 5 s reference speech is the smallest observed exemplar.
    # Select 30 distinct trials, round-robin across public tiers.
    groups = defaultdict(list)
    candidates = [c for c in clips() if c.tier in ("accept6", "gold9")
                  or c.tier == "synth" and c.true_speakers in (4, 6)]
    for c in candidates:
        ref = c.reference_segments()
        duration = len(audio(c.clip_id)) / SAMPLE_RATE
        for start in range(20, int(duration - 30), 15):
            main = reference(c, start, start + 30, relative=False)
            present = {r["speaker"] for r in main}
            prior = {}
            for speaker in present:
                eligible = [r for r in ref if r["speaker"] == speaker
                            and r["end"] <= start - 1 and r["end"] - r["start"] >= 5]
                if eligible:
                    prior[speaker] = max(eligible, key=lambda r: r["end"])
            if not prior:
                continue
            groups[c.tier].append((c, start, prior))
    chosen = []
    for tier in ("accept6", "gold9", "synth"):
        by_clip = defaultdict(list)
        for trial in groups[tier]:
            by_clip[trial[0].clip_id].append(trial)
        for trials in by_clip.values():
            trials.sort(key=lambda trial: (-len(trial[2]), trial[1]))
        while len([x for x in chosen if x[0].tier == tier]) < 10:
            progress = False
            for clip_id in sorted(by_clip):
                if by_clip[clip_id]:
                    chosen.append(by_clip[clip_id].pop(0))
                    progress = True
                    if len([x for x in chosen if x[0].tier == tier]) == 10:
                        break
            if not progress:
                break
    return chosen


def anchors():
    existing = receipts()
    for index, (c, start, prior) in enumerate(anchor_plan()):
        key = f"anchor:{index}:{c.clip_id}:{start}"
        if key in existing:
            continue
        main_pcm = piece(c.clip_id, start, start + 30)
        exemplar_pcm = []
        locations = []
        cursor = 0.0
        for speaker, r in sorted(prior.items()):
            segment = piece(c.clip_id, r["start"], r["start"] + 5)
            exemplar_pcm.append(segment)
            locations.append((speaker, cursor, cursor + 5))
            cursor += 5
            exemplar_pcm.append(np.zeros(round(.5 * SAMPLE_RATE), dtype=np.int16))
            cursor += .5
        anchored_pcm = np.concatenate([*exemplar_pcm, main_pcm])
        try:
            base = call(main_pcm)
            anchored = call(anchored_pcm)
            main_words = [type(w)(w.text, w.speaker, w.start-cursor, w.end-cursor)
                          for w in anchored.words if w.start >= cursor]
            ref_main = reference(c, start, start + 30)
            baseline_score = score(ref_main, words_to_segments(base.words), with_text=False)
            anchored_score = score(ref_main, words_to_segments(main_words), with_text=False)
            exemplar_labels = {}
            for speaker, lo, hi in locations:
                votes = defaultdict(float)
                for w in anchored.words:
                    overlap = max(0, min(w.end, hi)-max(w.start, lo))
                    votes[w.speaker] += overlap
                exemplar_labels[speaker] = max(votes, key=votes.get) if votes else None
            agreements = {}
            for speaker in exemplar_labels:
                votes = defaultdict(float)
                for w in main_words:
                    if _speaker_at(ref_main, (w.start+w.end)/2) == speaker:
                        votes[w.speaker] += max(0, w.end-w.start)
                main_label = max(votes, key=votes.get) if votes else None
                agreements[speaker] = {"exemplar_label": exemplar_labels[speaker],
                                       "main_label": main_label,
                                       "same": main_label is not None
                                               and main_label == exemplar_labels[speaker]}
            save({"key": key, "kind": "anchor", "tier": c.tier, "clip_id": c.clip_id,
                  "start": start, "k": len(prior), "base_der": baseline_score["der"],
                  "anchor_der": anchored_score["der"], "agreements": agreements,
                  "preamble_s": cursor, "base_words": len(base.words),
                  "anchor_main_words": len(main_words),
                  "base_timing_anomalies": base.timing_anomalies,
                  "anchor_timing_anomalies": anchored.timing_anomalies,
                  "cost_usd": (0 if base.cached else base.cost_usd())
                              + (0 if anchored.cached else anchored.cost_usd())})
        except Exception as exc:
            save({"kind": "failure", "stage": "anchors", "index": index,
                  "clip_id": c.clip_id, "error": str(exc)[:300]})


def failure_surface():
    existing = receipts()
    # Authorized by lead: generated signals contain no private content.
    n = 30 * SAMPLE_RATE
    x = np.arange(n, dtype=np.float64) / SAMPLE_RATE
    chord = (.18*np.sin(2*np.pi*220*x) + .12*np.sin(2*np.pi*277.18*x)
             + .10*np.sin(2*np.pi*329.63*x))
    gate = ((x % .5) < .35).astype(float)
    rng = np.random.default_rng(53)
    signals = {"silence": np.zeros(n, dtype=np.int16),
               "music_like": np.int16(np.clip(chord*gate, -1, 1)*32767),
               "white_noise": np.int16(rng.normal(0, 0.01, n)*32767)}
    for name, pcm in signals.items():
        for repeat in range(2):
            key = f"failure:{name}:{repeat}"
            if key in existing:
                continue
            try:
                r = call(pcm, use_cache=False)
                save({"key": key, "kind": "failure_surface", "signal": name,
                      "repeat": repeat, "words": len(r.words),
                      "text": r.text[:500], "speakers": sorted({w.speaker for w in r.words}),
                      "timing_anomalies": r.timing_anomalies,
                      "latency_s": r.latency_s, "cost_usd": r.cost_usd()})
            except Exception as exc:
                save({"kind": "failure", "stage": "failure_surface", "signal": name,
                      "repeat": repeat, "error": str(exc)[:300]})


def alternative():
    from google.genai import types

    existing = receipts()
    selected = [
        ("interview_bill_ackman_60s", 0, 30),
        ("interview_keyu_jin_60s", 0, 60),
        ("discussion_jamie_dimon_180s", 30, 90),
        ("discussion_rtfl_90s", 0, 90),
        ("interview_adam_frank_180s", 30, 150),
        ("mono_javier_intro_50s", 0, 30),
        ("benchmark:acquired_nfl", 0, 60),
        ("calibration:lex_shapiro_destiny", 30, 150),
        ("synth:meet_k4_s0", 60, 120),
        ("synth:meet_k4_s1", 120, 240),
        ("synth:meet_k6_s0", 60, 120),
        ("synth:meet_k6_s1", 120, 240),
        ("benchmark_5m:lex_bill_ackman", 0, 120),
        ("benchmark_5m:lex_keyu_jin", 0, 120),
        ("benchmark_5m:lex_javier_milei", 0, 120),
    ]
    prompt = (
        "Transcribe this audio verbatim and diarize every spoken word. Return only JSON "
        "with shape {\"segments\":[{\"start\":0.0,\"end\":0.3,\"speaker\":\"speaker_1\","
        "\"text\":\"word\"}]}. Times are seconds relative to the beginning of this audio. "
        "Use one stable speaker label per voice throughout this audio. Include no non-speech "
        "segments. Do not guess words in silence."
    )
    prior_low_failures = defaultdict(int)
    if RECEIPT.exists():
        for line in RECEIPT.read_text().splitlines():
            row = json.loads(line)
            if (row.get("kind") == "failure" and row.get("stage") == "alternative"
                    and "MINIMAL" not in row.get("error", "")):
                prior_low_failures[(row["clip_id"], row["start"], row["end"])] += 1
    for clip_id, start, end in selected:
        key = f"alternative:{clip_id}:{start}:{end}"
        if key in existing or prior_low_failures[(clip_id, start, end)] >= 3:
            continue
        c = next(c for c in clips() if c.clip_id == clip_id)
        pcm = piece(clip_id, start, end)
        ref = reference(c, start, end)
        response_text = None
        try:
            baseline = call(pcm)
            if spend(LANE).get(LANE, {}).get("cost_usd", 0) > 24.5:
                raise RuntimeError("P53 spend cap guard")
            t0 = time.monotonic()
            response = client().models.generate_content(
                model="gemini-3.8-flash",
                contents=[types.Part.from_bytes(data=wav_bytes(pcm), mime_type="audio/wav"), prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    # Gemini 3.8 Flash rejects MINIMAL (HTTP 400); LOW is the
                    # next level to test for this paired arm.
                    thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                    temperature=0,
                ),
            )
            latency_s = time.monotonic() - t0
            usage = response.usage_metadata.model_dump(exclude_none=True, mode="json") if response.usage_metadata else {}
            audio_tokens = sum(int(x.get("token_count", 0)) for x in usage.get("prompt_tokens_details", [])
                               if str(x.get("modality", "")).upper() == "AUDIO")
            text_tokens = int(usage.get("prompt_token_count", 0)) - audio_tokens
            out_tokens = int(usage.get("candidates_token_count", 0)) + int(usage.get("thoughts_token_count", 0))
            cost = (audio_tokens*.75 + text_tokens*.75 + out_tokens*4.50)/1e6
            ledger(LANE, {"kind": "alternative", "model": "gemini-3.8-flash",
                          "audio_s": len(pcm)/SAMPLE_RATE, "latency_s": latency_s,
                          "usage": usage, "cost_usd": cost})
            response_text = response.text
            # Some responses contain an object whose quote characters are
            # escaped even though the object itself is not JSON-quoted.
            parse_text = response_text
            escaped_layers = 0
            while parse_text.startswith('{\\') and escaped_layers < 2:
                parse_text = parse_text.replace('\\"', '"')
                escaped_layers += 1
            raw = json.loads(parse_text)
            segments = raw["segments"] if isinstance(raw, dict) else raw
            hyp = [{"start": float(x["start"]), "end": float(x["end"]),
                    "speaker": str(x["speaker"]), "text": str(x["text"])}
                   for x in segments if float(x["end"]) > float(x["start"])]
            flash_words = [Word(x["text"], x["speaker"], x["start"], x["end"])
                           for x in hyp]
            original_turns = [{**turn, "start": turn["start"]-start,
                               "end": turn["end"]-start}
                              for turn in c.reference_segments()]
            save({"key": key, "kind": "alternative", "clip_id": clip_id,
                  "tier": c.tier, "start": start, "end": end,
                  "reference_coverage": sum(x["end"]-x["start"] for x in ref)/(end-start),
                  "transcribe": safe_diarization(ref, words_to_segments(baseline.words)),
                  "flash": safe_diarization(ref, hyp),
                  "transcribe_supported": safe_diarization(
                      ref, _supported_hypothesis(ref, words_to_segments(baseline.words))),
                  "flash_supported": safe_diarization(ref, _supported_hypothesis(ref, hyp)),
                  "transcribe_text": _text_zone(original_turns, baseline.words, 0, end-start),
                  "flash_text": _text_zone(original_turns, flash_words, 0, end-start),
                  "flash_segments": len(hyp),
                  "escaped_json_layers_repaired": escaped_layers,
                  "flash_latency_s": latency_s, "transcribe_latency_s": baseline.latency_s,
                  "flash_cost_usd": cost,
                  "transcribe_cost_usd": baseline.cost_usd(),
                  "transcribe_timing_anomalies": baseline.timing_anomalies,
                  "flash_usage": usage})
        except Exception as exc:
            prior_low_failures[(clip_id, start, end)] += 1
            save({"kind": "failure", "stage": "alternative", "clip_id": clip_id,
                  "start": start, "end": end, "thinking": "LOW",
                  "error": str(exc)[:300],
                  "response_raw": response_text})


def _supported_hypothesis(ref, hyp):
    spans = []
    for r in sorted(ref, key=lambda r: r["start"]):
        if spans and r["start"] <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], r["end"])
        else:
            spans.append([r["start"], r["end"]])
    out = []
    for h in hyp:
        for start, end in spans:
            a, b = max(start, h["start"]), min(end, h["end"])
            if b > a:
                out.append({**h, "start": a, "end": b})
    return out


def _text_zone(ref, words, lo, hi):
    # Reference text exists only per turn. Fully contained turns are the
    # defensible subset for a text comparison; cut turns have unknown words.
    selected = sorted((r for r in ref if r["text"] and r["start"] >= lo
                       and r["end"] <= hi), key=lambda r: (r["start"], r["end"]))
    rt = _tokenize(" ".join(r["text"] for r in selected))
    ht = _tokenize(" ".join(w.text for w in words
                            if any(r["start"] <= (w.start+w.end)/2 < r["end"]
                                   for r in selected)))
    tokens = len(rt)
    errors = _wer(rt, ht) * tokens if tokens else 0
    turns = len(selected)
    return {"reference_words": tokens, "reference_turns": turns,
            "word_errors": errors, "wer": errors/tokens if tokens else None}


def rescore():
    existing = receipts()
    source = [r for r in existing.values() if r["kind"] in ("quality", "final")]
    for row in source:
        key = "rescore:" + row["key"]
        c = next(c for c in clips() if c.clip_id == row["clip_id"])
        needed_version = 5 if c.tier == "accept6" else 4
        if key in existing and existing[key].get("text_zone_version") == needed_version:
            continue
        start = row.get("start", 0)
        end = row.get("end", len(audio(c.clip_id))/SAMPLE_RATE)
        r = call(piece(c.clip_id, start, end))
        if not r.cached:
            raise RuntimeError(f"rescore unexpectedly paid: {row['key']}")
        ref = reference(c, start, end)
        clean = valid_words(r.words, end-start)
        hyp = words_to_segments(clean)
        supported = safe_diarization(ref, _supported_hypothesis(ref, hyp))
        valid_result = safe_diarization(ref, hyp)
        edge = {}
        duration = end-start
        if c.tier == "accept6" and row["kind"] == "quality":
            for side, lo, hi in (("first", 0, min(2, duration)),
                                 ("middle", min(2, duration), max(2, duration-2)),
                                 ("last", max(0, duration-2), duration)):
                er = [{"start": max(x["start"], lo)-lo,
                       "end": min(x["end"], hi)-lo, "speaker": x["speaker"], "text": ""}
                      for x in ref if min(x["end"], hi) > max(x["start"], lo)]
                eh = [{"start": max(x["start"], lo)-lo,
                       "end": min(x["end"], hi)-lo, "speaker": x["speaker"], "text": ""}
                      for x in hyp if min(x["end"], hi) > max(x["start"], lo)]
                edge[side] = safe_diarization(er, eh)
        original_turns = [{**turn, "start": turn["start"]-start,
                           "end": turn["end"]-start}
                          for turn in c.reference_segments()]
        zones = {"first": _text_zone(original_turns, r.words, 0, min(2, duration)),
                 "middle": _text_zone(original_turns, r.words,
                                       min(2, duration), max(2, duration-2)),
                 "last": _text_zone(original_turns, r.words,
                                     max(0, duration-2), duration)}
        window_text = _text_zone(original_turns, r.words, 0, duration)
        boundary = []
        for rr in ref:
            within = [w for w in r.words if rr["start"] <= (w.start+w.end)/2 < rr["end"]]
            if within:
                boundary.append([within[0].start-rr["start"], within[-1].end-rr["end"]])
        save({"key": key, "kind": "rescore", "source_key": row["key"],
              "tier": c.tier, "clip_id": c.clip_id, "length": row.get("length"),
              "reference_set": "H1 #3 manifest 80fc15bd" if c.tier == "accept6" else "corpus current",
              "reference_speech_s": sum(x["end"]-x["start"] for x in ref),
              "reference_coverage": sum(x["end"]-x["start"] for x in ref)/duration,
              "supported": supported, "valid_result": valid_result,
              "full_result": score(ref, hyp) if c.tier == "accept6" and row["kind"] == "final" else None,
              "edge": edge,
              "invalid_word_count": len(r.words)-len(clean),
              "timing_anomalies": r.timing_anomalies,
              "text_zone_version": needed_version,
              "text_zones": zones, "window_text": window_text,
              "boundary_offsets_s": boundary})


def stitch():
    existing = receipts()
    for c in clips("long30m"):
        key = f"stitch_v2:{c.clip_id}"
        if key in existing:
            continue
        tasks = ((0, 610, 0, 600), (590, 1210, 600, 1200),
                 (1190, 1800, 1200, 1800))
        collected = []
        previous = []
        seams = []
        chunk_anomalies = []
        try:
            for chunk, (start, end, core_start, core_end) in enumerate(tasks):
                r = call(piece(c.clip_id, start, end))
                chunk_anomalies.append(r.timing_anomalies)
                absolute = [(w, w.start+start, w.end+start)
                            for w in valid_words(r.words, end-start)]
                local_labels = sorted({w.speaker for w in r.words})
                mapping = {}
                if chunk == 0:
                    mapping = {sp: f"c0:{sp}" for sp in local_labels}
                else:
                    overlap_start = start
                    overlap_end = tasks[chunk-1][1]
                    weights = defaultdict(float)
                    prior = [(p_sp, p_s, p_e) for p_sp, p_s, p_e in previous
                             if p_e > overlap_start and p_s < overlap_end]
                    current = [(w.speaker, s, e) for w, s, e in absolute
                               if e > overlap_start and s < overlap_end]
                    for p_sp, p_s, p_e in prior:
                        for q_sp, q_s, q_e in current:
                            weights[(p_sp, q_sp)] += max(0, min(p_e,q_e)-max(p_s,q_s))
                    used_prior = set()
                    used_local = set()
                    for (p_sp, q_sp), weight in sorted(weights.items(),
                                                       key=lambda item: item[1], reverse=True):
                        if weight <= 0 or p_sp in used_prior or q_sp in used_local:
                            continue
                        mapping[q_sp] = p_sp
                        used_prior.add(p_sp)
                        used_local.add(q_sp)
                    for sp in local_labels:
                        mapping.setdefault(sp, f"c{chunk}:{sp}")
                    seams.append({"chunk": chunk, "overlap_s": overlap_end-overlap_start,
                                  "previous_labels": sorted({x[0] for x in prior}),
                                  "current_labels": sorted({x[0] for x in current}),
                                  "mapping": mapping,
                                  "matched_overlap_s": sum(weights.get((mapped, local), 0)
                                                           for local, mapped in mapping.items())})
                for w, s, e in absolute:
                    if core_start <= (s+e)/2 < core_end:
                        collected.append((w, start, mapping))
                previous = [(mapping[w.speaker], s, e) for w, s, e in absolute]
            hyp_words = []
            for w, offset, mapping in collected:
                hyp_words.append(Word(w.text, mapping[w.speaker],
                                      w.start+offset, w.end+offset))
            # Use the same grouped speech-span representation as the one-pass
            # comparator; raw word gaps otherwise inflate DER miss.
            hyp = words_to_segments(hyp_words)
            ref = c.reference_segments()
            result = score(ref, hyp)
            supported = score(ref, _supported_hypothesis(ref, hyp), with_text=False)
            save({"key": key, "kind": "stitch_v2", "clip_id": c.clip_id,
                  "chunks": len(tasks), "core_words": len(hyp_words), "seams": seams,
                  "chunk_timing_anomalies": chunk_anomalies,
                  "result": result, "supported": supported})
        except Exception as exc:
            save({"kind": "failure", "stage": "stitch", "clip_id": c.clip_id,
                  "error": str(exc)[:300]})


def merge_arm():
    from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder

    targets = [c for c in clips() if c.tier == "accept6" or
               c.clip_id in ("synth:meet_k2_s0", "synth:meet_k2_s1",
                             "synth:meet_k4_s0", "synth:meet_k6_s0")]
    model_path = ROOT / "prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx"
    embedder = _OnnxWeSpeakerEmbedder(model_path, device="cpu")
    vector_path = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53/merge-embeddings-L1.json")
    vector_cache = json.loads(vector_path.read_text()) if vector_path.exists() else {}
    thresholds = (.30, .40, .46, .50, .60, .70, .80)
    existing = receipts()
    for c in targets:
        r = call(audio(c.clip_id))
        if not r.cached:
            raise RuntimeError(f"merge arm unexpectedly paid for {c.clip_id}")
        words = r.words
        labels = sorted({w.speaker for w in words})
        vectors = vector_cache.get(c.clip_id, {})
        intervals_by_label = {}
        embedded_s = 0.0
        for label in labels:
            intervals = embedding_intervals(0, [w.__dict__ for w in words], label)
            intervals_by_label[label] = intervals
            if intervals and label not in vectors:
                t0 = time.monotonic()
                vectors[label] = embedder.embed(c.audio, intervals)
                embedded_s += time.monotonic() - t0
                vector_cache[c.clip_id] = vectors
                vector_path.write_text(json.dumps(vector_cache))
        pairs = [(a, b, cosine(vectors[a], vectors[b]))
                 for i, a in enumerate(sorted(vectors)) for b in sorted(vectors)[i+1:]]
        ref = c.reference_segments()
        base = safe_diarization(ref, words_to_segments(words))
        base_supported = safe_diarization(ref, _supported_hypothesis(ref, words_to_segments(words)))
        for threshold in thresholds:
            key = f"merge_l1:{c.clip_id}:{threshold:.2f}"
            if key in existing:
                continue
            parent = {label: label for label in labels}
            def root(label):
                while parent[label] != label:
                    label = parent[label]
                return label
            for a, b, value in sorted(pairs, key=lambda x: x[2], reverse=True):
                if value >= threshold:
                    parent[root(b)] = root(a)
            mapping = {label: root(label) for label in labels}
            hyp = words_to_segments(words, speaker_map=mapping)
            result = safe_diarization(ref, hyp)
            supported = safe_diarization(ref, _supported_hypothesis(ref, hyp))
            save({"key": key, "kind": "merge_l1", "clip_id": c.clip_id, "tier": c.tier,
                  "reference_set": "H1 #3 manifest 80fc15bd" if c.tier == "accept6" else "corpus current",
                  "threshold": threshold, "labels_before": len(labels),
                  "eligible_labels": len(vectors),
                  "labels_after": len(set(mapping.values())),
                  "base": base, "base_supported": base_supported,
                  "result": result, "supported": supported,
                  "embedding_seconds_new": embedded_s,
                  "pair_cosines": pairs if threshold == .46 else None,
                  "mapping": mapping if threshold == .46 else None})


def h1_final():
    """Compare final-only Gemini surfaces with MOSS through H1's exact scorer."""
    existing = receipts()
    for c in clips("accept6"):
        r = call(audio(c.clip_id))
        if not r.cached:
            raise RuntimeError(f"H1 final scorer unexpectedly paid for {c.clip_id}")
        for method in ("pure", "L1-merge-0.46"):
            key = f"h1_final:{method}:{c.clip_id}"
            if key in existing:
                continue
            if method == "pure":
                mapping = None
            else:
                merge = existing.get(f"merge_l1:{c.clip_id}:0.46")
                if not merge:
                    raise RuntimeError(f"L1 merge receipt missing for {c.clip_id}")
                mapping = merge["mapping"]
            hyp = words_to_segments(r.words, speaker_map=mapping)
            result = h1_score_case(c.clip_id, immediate=[], settled=[], final=hyp)
            save({"key": key, "kind": "h1_final", "method": method,
                  "clip_id": c.clip_id, "reference_set": "H1 #3 manifest 80fc15bd",
                  "metrics": result["metrics"]["final"],
                  "timing_anomalies": r.timing_anomalies})


def summary():
    rows = list(receipts().values())
    print("P53 ledger", json.dumps(spend(LANE), sort_keys=True))
    for length in (10, 20, 30, 60, 90, 120):
        subset = [r for r in rows if r["kind"] == "rescore" and r["tier"] == "accept6"
                  and r["length"] == length and r["text_zone_version"] == 5]
        groups = defaultdict(list)
        for r in subset:
            groups[r["clip_id"]].append(r)
        if groups:
            macro_der = statistics.mean(
                sum(r["valid_result"]["der"]*r["reference_speech_s"] for r in rs)
                / sum(r["reference_speech_s"] for r in rs)
                for rs in groups.values())
            print("H1 truth accept6 window", length, "n", len(subset), "macro DER", macro_der)
    for method in ("pure", "L1-merge-0.46"):
        subset = [r for r in rows if r["kind"] == "h1_final" and r["method"] == method]
        if subset:
            print("H1 exact final", method, "n", len(subset),
                  "macro DER", statistics.mean(r["metrics"]["der"] for r in subset),
                  "macro WER", statistics.mean(r["metrics"]["wer"] for r in subset))
    reps = [r for r in rows if r["kind"] == "repeat"]
    if len(reps) >= 2:
        a, b = reps[:2]
        print("repeat", "word_count", len(a["words"]), len(b["words"]),
              "exact_equal", a["words"] == b["words"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("all", "latency", "quality", "final",
                                          "determinism", "anchors", "alternative",
                                          "failure_surface", "rescore", "stitch",
                                          "merge_arm", "h1_final", "summary"))
    args = parser.parse_args()
    stages = ("final", "quality", "latency", "determinism", "anchors",
              "alternative", "failure_surface", "rescore", "stitch",
              "merge_arm", "h1_final") if args.stage == "all" else (args.stage,)
    for stage in stages:
        print("STAGE", stage, "start", time.time(), flush=True)
        globals()[stage]()
        print("STAGE", stage, "end", time.time(), "spend", spend(LANE), flush=True)
    if args.stage != "summary":
        summary()


if __name__ == "__main__":
    main()
