"""C4 observation helpers. Use c4_stop.py for the corrected short Stop drain.

The original runner below is retained only for its reusable observation helpers.
Its full-length final window and score receipts are superseded.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from measure import (EVIDENCE, cached_embeddings, evaluate, measured_score, note,
                     segmentize, windows)
from score_support import mask_words

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from common.corpus import clips  # noqa: E402
from common.gemini_common import diarize_window, read_wav, spend  # noqa: E402
from h1_offline import score_case  # noqa: E402

BASELINE_SPEND_USD = 1.5492
FOLLOWUP_CAP_USD = 8.0


def clip_pcm(clip, mix):
    pcm = read_wav(clip.audio)
    if mix:
        if clip.mic_audio is None:
            raise ValueError("microphone mix requested without fixture")
        mic = read_wav(clip.mic_audio)
        if len(mic) != len(pcm):
            raise ValueError("system/mic lengths differ")
        pcm = np.clip(pcm.astype(np.int32) + mic.astype(np.int32), -32768, 32767).astype(np.int16)
    return pcm


def observation_path(clip, step, length, mix):
    safe = clip.clip_id.replace(":", "_")
    return EVIDENCE / f"c4-observations-{clip.tier}-{safe}-S{step:g}-L{length:g}{'-mix' if mix else ''}.jsonl"


def observations(clip, pcm, step, length, mix):
    path = observation_path(clip, step, length, mix)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    retained = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    schedule = list(windows(pcm, step, length))
    if len(retained) > len(schedule):
        raise ValueError(f"extra observations in {path}")
    for index, (start, end, part) in enumerate(schedule):
        if index < len(retained):
            row = retained[index]
            if (row["start"], row["end"]) != (start, end):
                raise ValueError(f"schedule mismatch at {index}: {path}")
            yield row
            continue
        spent = spend("P61").get("P61", {}).get("cost_usd", BASELINE_SPEND_USD)
        if spent - BASELINE_SPEND_USD >= FOLLOWUP_CAP_USD - 0.15:
            raise RuntimeError(f"P61 follow-up spend cap near: ${spent - BASELINE_SPEND_USD:.4f}")
        result = diarize_window(part, ledger_lane="P61", max_attempts=3)
        anomaly = result.timing_anomalies or {"clamped": 0, "dropped": 0}
        row = {"start": start, "end": end, "words": [vars(word) for word in result.words],
               "cached": result.cached, "api_latency_s": result.latency_s,
               "cost_usd": result.cost_usd(), "timing_anomalies": anomaly,
               "timing_anomaly_rate": sum(anomaly.values()) /
               max(1, len(result.words) + anomaly["dropped"])}
        with path.open("a") as file:
            file.write(json.dumps(row) + "\n")
        print(json.dumps({"case": clip.clip_id, "mix": mix, "S": step, "L": length,
                          "window": index + 1, "windows": len(schedule),
                          "start": start, "end": end, "words": len(result.words),
                          "labels": len({word.speaker for word in result.words}),
                          "cached": result.cached, "cost_usd": result.cost_usd(),
                          "api_latency_s": result.latency_s,
                          "timing_anomalies": anomaly,
                          "timing_anomaly_rate": row["timing_anomaly_rate"]}), flush=True)
        yield row


def score_view(clip, reference, masks, variant, view, immediate=False):
    prefix = "first" if view == "first" else "last_revised"
    immediate_key = "first_immediate_segments" if view == "first" else "last_immediate_segments"
    words = variant[immediate_key] if immediate else variant[f"{prefix}_segments"]
    if clip.tier == "accept6":
        # H1 requires strictly positive durations; preserve raw words separately.
        rows = [word for word in words if word["end"] > word["start"]]
        if immediate:
            return rows
        instant = [word for word in variant[immediate_key]
                   if word["end"] > word["start"]]
        h1 = score_case(clip.clip_id, immediate=instant, settled=rows, final=[])
        return {"metrics": h1["metrics"]["settled"], "immediate_metrics": h1["metrics"]["immediate"],
                "h1": h1}
    if clip.tier == "e1":
        return None
    # Apply EXCLUDE at word resolution before grouping, as required for gold8.
    source_words = variant["first_words" if view == "first" else "last_revised_words"]
    filtered, removed, zero = mask_words(source_words, masks)
    metrics = measured_score(reference, segmentize(filtered))
    return {"metrics": metrics, "masked_words": removed, "zero_duration_words": zero}


def run_clip(clip, step, length, mix=False, holds=(0, 10)):
    pcm = clip_pcm(clip, mix)
    obs = list(observations(clip, pcm, step, length, mix))
    vectors, cached = cached_embeddings(clip, obs, step, length, mix, pcm)
    reference = [] if clip.tier == "e1" else clip.reference_segments()
    excluded = [row for row in reference if clip.tier != "synth" and
                (row["speaker"] == "<EXCLUDE>" or not row["text"].strip())]
    masks = [(row["start"], row["end"]) for row in excluded]
    reference = [row for row in reference if row not in excluded]
    variants = {}
    for hold in holds:
        for name, args in {
            "pure_C1": (None, None, 0),
            "pure_C1_birth2": (None, None, 2),
            "C1_C3_local": (.46, .6, 0),
            "C1_C3_local_birth2": (.46, .6, 2),
        }.items():
            eth, wth, birth = args
            state = evaluate([], obs, hold, .3, eth, wth, include_segments=True,
                             stop_drain=True, birth_min_s=birth)
            first = score_view(clip, reference, masks, state, "first")
            last = score_view(clip, reference, masks, state, "last")
            variants[f"{name}_H{hold:g}"] = {
                "first": first, "last_revised": last,
                "speaker_count": state["speaker_count"],
                "last_speaker_count": state["last_speaker_count"],
                "immediate_speaker_count": state["immediate_speaker_count"],
                "births": state["births"], "merges": state["merges"],
                "local_merges": state["local_merges"],
                "visible_relabel_events": state["visible_relabel_events"],
                "visible_relabels_per_minute": state["visible_relabels_per_minute"],
                "unattributed_s": state["unattributed_s"],
                "last_unattributed_s": state["last_unattributed_s"],
                "stop_drained_words": state["stop_drained_words"],
                "stop_api_latency_s": state["stop_api_latency_s"],
                "latency_p50_s": state["latency_p50_s"],
                "latency_p90_s": state["latency_p90_s"],
                "latency_with_api_p50_s": state["latency_with_api_p50_s"],
                "latency_with_api_p90_s": state["latency_with_api_p90_s"],
                "state": state["state"],
            }
    duration = len(pcm) / 16000
    batch_cost = sum(row["cost_usd"] for row in obs)
    output = {"case": clip.clip_id, "tier": clip.tier, "mix": mix,
              "S": step, "Lmax": length, "holds": list(holds),
              "duration_s": duration, "windows": len(obs),
              "cached_calls": sum(row["cached"] for row in obs),
              "vectors": vectors, "vectors_cached": cached,
              "audio_sent_s": sum(row["end"] - row["start"] for row in obs),
              "batch_cost_usd": batch_cost,
              "batch_plus_live_per_hour_usd": batch_cost * 3600 / duration + .30,
              "api_latency_p50_s": float(np.median([row["api_latency_s"] for row in obs])),
              "timing_anomalies": {key: sum(row["timing_anomalies"][key] for row in obs)
                                   for key in ("clamped", "dropped")},
              "timing_words": sum(len(row["words"]) for row in obs),
              "excluded_reference_rows": excluded,
              "variants": variants}
    safe = clip.clip_id.replace(":", "_")
    path = EVIDENCE / f"c4-score-{clip.tier}-{safe}-S{step:g}-L{length:g}{'-mix' if mix else ''}.json"
    path.write_text(json.dumps(output, indent=2))
    print(json.dumps({"case": clip.clip_id, "mix": mix, "S": step, "L": length,
                      "windows": len(obs), "cached": output["cached_calls"],
                      "audio_sent_s": output["audio_sent_s"],
                      "batch_plus_live_per_hour_usd": output["batch_plus_live_per_hour_usd"],
                      "variants": {name: {"ids": value["speaker_count"],
                                          "first_der": value["first"]["metrics"]["der"]
                                          if value["first"] else None,
                                          "unattributed_s": value["unattributed_s"],
                                          "label_lag_p50_s": value["latency_with_api_p50_s"]}
                                   for name, value in variants.items()},
                      "receipt": path.name}), flush=True)
    note(f"C4 {clip.clip_id} {'mix' if mix else 'system'} S{step:g}/L{length:g}: "
         f"{len(obs)} windows, {output['cached_calls']} cached, batch+Live "
         f"${output['batch_plus_live_per_hour_usd']:.3f}/h, P61 total {spend('P61').get('P61', {})}; "
         f"receipt {path.name}")
    return output


if __name__ == "__main__":
    raise SystemExit("Superseded Stop scoring; run continuity/c4_stop.py instead.")
