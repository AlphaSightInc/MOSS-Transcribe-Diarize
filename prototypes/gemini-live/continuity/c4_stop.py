"""C4 growing windows with an exact [live frontier, audio end] Stop drain.

Run from worktree root: PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
  prototypes/gemini-live/continuity/c4_stop.py --tier accept6 --length 60 --step 20
Per-call numeric receipts resume interrupted runs. Previous c4.py scores used a
full Lmax window at Stop and are superseded by this runner's c4-stop-score files.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from c4 import (BASELINE_SPEND_USD, FOLLOWUP_CAP_USD, clip_pcm, observation_path,
                score_view)
from measure import EVIDENCE, add_embeddings, cached_embeddings, evaluate, note, windows

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.corpus import clips  # noqa: E402
from common.gemini_common import diarize_window, spend  # noqa: E402


def budget_guard():
    spent = spend("P61").get("P61", {}).get("cost_usd", BASELINE_SPEND_USD)
    if spent - BASELINE_SPEND_USD >= FOLLOWUP_CAP_USD - .15:
        raise RuntimeError(f"P61 follow-up spend cap near: ${spent - BASELINE_SPEND_USD:.4f}")


def call(part, start, end, metadata):
    budget_guard()
    result = diarize_window(part, ledger_lane="P61", max_attempts=3)
    anomaly = result.timing_anomalies or {"clamped": 0, "dropped": 0}
    row = {"start": start, "end": end, "words": [vars(word) for word in result.words],
           "cached": result.cached, "api_latency_s": result.latency_s,
           "cost_usd": result.cost_usd(), "timing_anomalies": anomaly,
           "timing_anomaly_rate": sum(anomaly.values()) /
           max(1, len(result.words) + anomaly["dropped"])}
    print(json.dumps({**metadata, "start": start, "end": end,
                      "words": len(result.words), "labels": len({w.speaker for w in result.words}),
                      "cached": result.cached, "cost_usd": result.cost_usd(),
                      "api_latency_s": result.latency_s,
                      "timing_anomalies": anomaly,
                      "timing_anomaly_rate": row["timing_anomaly_rate"]}), flush=True)
    return row


def periodic_observations(clip, pcm, step, length, mix):
    schedule = list(windows(pcm, step, length))[:-1]
    path = observation_path(clip, step, length, mix)
    retained = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
    # The first C4 runner retained a full Lmax final window. Keep its evidence
    # but do not feed that observation into the corrected Stop surface.
    if len(retained) == len(schedule) + 1:
        final_start, final_end, _ = list(windows(pcm, step, length))[-1]
        if (retained[-1]["start"], retained[-1]["end"]) != (final_start, final_end):
            raise ValueError(f"unexpected trailing observation: {path}")
        retained = retained[:-1]
    if len(retained) > len(schedule):
        raise ValueError(f"extra observations: {path}")
    for index, (start, end, part) in enumerate(schedule):
        if index < len(retained):
            if (retained[index]["start"], retained[index]["end"]) != (start, end):
                raise ValueError(f"periodic schedule mismatch: {path}:{index}")
            continue
        row = call(part, start, end,
                   {"case": clip.clip_id, "mix": mix, "S": step, "L": length,
                    "periodic_window": index + 1, "periodic_windows": len(schedule)})
        with path.open("a") as file:
            file.write(json.dumps(row) + "\n")
        retained.append(row)
    return retained


def periodic_vectors(clip, observations, step, length, mix, pcm):
    path = EVIDENCE / (f"vectors-span2s-{clip.tier}-{clip.clip_id}-S{step:g}-L{length:g}"
                       f"{'-mix' if mix else ''}.json")
    if path.exists():
        rows = json.loads(path.read_text())
        if len(rows) in (len(observations), len(observations) + 1) and all(
            (a["start"], a["end"]) == (b["start"], b["end"])
            for a, b in zip(rows, observations)):
            for obs, row in zip(observations, rows):
                obs["embeddings"] = row["embeddings"]
            return sum(len(row["embeddings"]) for row in rows[:len(observations)]), True
        raise ValueError(f"periodic vector schedule mismatch: {path}")
    return cached_embeddings(clip, observations, step, length, mix, pcm)


def stop_observation(clip, pcm, step, length, hold, mix, frontier):
    duration = len(pcm) / 16000
    start = round(frontier, 4)
    end = round(duration, 4)
    safe = clip.clip_id.replace(":", "_")
    suffix = f"{clip.tier}-{safe}-S{step:g}-L{length:g}-H{hold:g}{'-mix' if mix else ''}"
    path = EVIDENCE / f"c4-stop-observation-{suffix}.json"
    if path.exists():
        row = json.loads(path.read_text())
        if (row["start"], row["end"]) != (start, end):
            raise ValueError(f"Stop frontier mismatch: {path}")
    else:
        part = pcm[round(start * 16000):round(end * 16000)]
        row = call(part, start, end,
                   {"case": clip.clip_id, "mix": mix, "S": step, "L": length,
                    "stop_hold": hold})
        path.write_text(json.dumps(row, indent=2))
    vector_path = EVIDENCE / f"c4-stop-vectors-{suffix}.json"
    if vector_path.exists():
        vectors = json.loads(vector_path.read_text())
        if (vectors["start"], vectors["end"]) != (start, end):
            raise ValueError(f"Stop vector frontier mismatch: {vector_path}")
        row["embeddings"] = vectors["embeddings"]
    else:
        add_embeddings(clip, [row], pcm if mix else None)
        vector_path.write_text(json.dumps({"start": start, "end": end,
                                           "embeddings": row["embeddings"]}))
    return row


def run_clip(clip, step, length, mix=False, holds=(0, 10)):
    pcm = clip_pcm(clip, mix)
    periodic = periodic_observations(clip, pcm, step, length, mix)
    periodic_vector_count, vectors_cached = periodic_vectors(clip, periodic, step, length, mix, pcm)
    reference = [] if clip.tier == "e1" else clip.reference_segments()
    excluded = [r for r in reference if clip.tier != "synth" and
                (r["speaker"] == "<EXCLUDE>" or not r["text"].strip())]
    masks = [(r["start"], r["end"]) for r in excluded]
    reference = [r for r in reference if r not in excluded]
    duration = len(pcm) / 16000
    output = {"case": clip.clip_id, "tier": clip.tier, "mix": mix,
              "S": step, "Lmax": length, "duration_s": duration,
              "periodic_windows": len(periodic), "holds": list(holds),
              "periodic_vectors": periodic_vector_count, "vectors_cached": vectors_cached,
              "excluded_reference_rows": excluded, "by_hold": {}}
    for hold in holds:
        frontier = max(0.0, periodic[-1]["end"] - hold) if periodic else 0.0
        stop = stop_observation(clip, pcm, step, length, hold, mix, frontier)
        obs = periodic + [stop]
        variants = {}
        for name, (eth, wth, birth) in {
            "pure_C1": (None, None, 0),
            "pure_C1_birth2": (None, None, 2),
            "C1_C3_local": (.46, .6, 0),
            "C1_C3_local_birth2": (.46, .6, 2),
        }.items():
            state = evaluate([], obs, hold, .3, eth, wth, include_segments=True,
                             stop_drain=True, birth_min_s=birth)
            variants[name] = {
                "first": score_view(clip, reference, masks, state, "first"),
                "last_revised": score_view(clip, reference, masks, state, "last"),
                "speaker_count": state["speaker_count"],
                "last_speaker_count": state["last_speaker_count"],
                "immediate_speaker_count": state["immediate_speaker_count"],
                "births": state["births"], "local_merges": state["local_merges"],
                "visible_relabel_events": state["visible_relabel_events"],
                "visible_relabels_per_minute": state["visible_relabels_per_minute"],
                "unattributed_s": state["unattributed_s"],
                "last_unattributed_s": state["last_unattributed_s"],
                "stop_drained_words": state["stop_drained_words"],
                "latency_p50_s": state["latency_p50_s"],
                "latency_p90_s": state["latency_p90_s"],
                "latency_with_api_p50_s": state["latency_with_api_p50_s"],
                "latency_with_api_p90_s": state["latency_with_api_p90_s"],
                "state": state["state"],
            }
        cost = sum(row["cost_usd"] for row in obs)
        output["by_hold"][f"H{hold:g}"] = {
            "stop_interval": [stop["start"], stop["end"]],
            "stop_api_latency_s": stop["api_latency_s"],
            "stop_cached": stop["cached"],
            "windows": len(obs),
            "cached_calls": sum(row["cached"] for row in obs),
            "audio_sent_s": sum(row["end"] - row["start"] for row in obs),
            "batch_cost_usd": cost,
            "batch_plus_live_per_hour_usd": cost * 3600 / duration + .30,
            "timing_anomalies": {key: sum(row["timing_anomalies"][key] for row in obs)
                                 for key in ("clamped", "dropped")},
            "timing_words": sum(len(row["words"]) for row in obs),
            "variants": variants,
        }
    safe = clip.clip_id.replace(":", "_")
    path = EVIDENCE / (f"c4-stop-score-{clip.tier}-{safe}-S{step:g}-L{length:g}"
                       f"{'-mix' if mix else ''}.json")
    path.write_text(json.dumps(output, indent=2))
    print(json.dumps({"case": clip.clip_id, "mix": mix, "S": step, "L": length,
                      "by_hold": {h: {"stop_interval": data["stop_interval"],
                                      "cost_per_hour": data["batch_plus_live_per_hour_usd"],
                                      "variants": {name: {"ids": v["speaker_count"],
                                                          "last_ids": v["last_speaker_count"],
                                                          "der": v["first"]["metrics"]["der"]
                                                          if v["first"] else None,
                                                          "S00_s": v["unattributed_s"],
                                                          "lag_p50_s": v["latency_with_api_p50_s"]}
                                                   for name, v in data["variants"].items()}}
                                  for h, data in output["by_hold"].items()},
                      "receipt": path.name}), flush=True)
    note(f"C4 exact Stop {clip.clip_id} {'mix' if mix else 'system'} S{step:g}/L{length:g}: "
         f"periodic {len(periodic)}, H{','.join(f'{h:g}' for h in holds)}, "
         f"P61 total {spend('P61').get('P61', {})}; receipt {path.name}")
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", required=True,
                        choices=("accept6", "e1", "gold9", "bench5m", "long30m", "long60", "synth"))
    parser.add_argument("--case", default="")
    parser.add_argument("--length", type=float, required=True)
    parser.add_argument("--step", type=float, required=True)
    parser.add_argument("--mix", action="store_true")
    parser.add_argument("--holds", type=float, nargs="+", default=[0, 10])
    args = parser.parse_args()
    selected = [c for c in clips(args.tier)
                if (not args.case or args.case in c.clip_id)
                and (args.tier != "gold9" or c.clip_id != "benchmark:acquired_jamie_dimon")
                and (args.tier not in ("bench5m", "long30m") or "lex_" in c.clip_id)]
    if args.mix and args.tier != "e1":
        parser.error("--mix is E1 only")
    for clip in selected:
        run_clip(clip, args.step, args.length, args.mix, args.holds)
