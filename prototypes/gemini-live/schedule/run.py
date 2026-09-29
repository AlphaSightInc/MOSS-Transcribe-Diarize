"""P65 PROTOTYPE (throwaway): cheaper Gemini speaker-window schedules vs S15/L180 (A0).

Run from worktree root:
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/gemini-live/schedule/run.py --arms A1 A2 A3 A4 --tiers accept6 e1
  ... run.py --summary          # table + decision rule from receipts (no provider calls)
Public corpus only. Ledger lane P65-schedule; hard cap $15 new spend incl. estimated output.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "continuity"))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "harness"))

import measure  # noqa: E402
import c4  # noqa: E402
import c4_stop  # noqa: E402
from registry import SpeakerRegistry, field  # noqa: E402
from common.corpus import clips  # noqa: E402
from common.gemini_common import LEDGER_DIR, diarize_window  # noqa: E402

EVID = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P65/schedule")
import os  # noqa: E402
if os.environ.get("P65_DRAW"):  # independent repeat draw: fresh responses in a separate cache + receipts
    import common.gemini_common as _gc  # noqa: E402
    _gc.CACHE_DIR = _gc.CACHE_DIR.parent / f".cache-draw{os.environ['P65_DRAW']}"
    EVID = EVID / f"draw{os.environ['P65_DRAW']}"
P61 = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P61")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/P65-schedule-STATUS.md")
LANE = "P65-schedule"
CAP_USD = 15.0
OUTPUT_USD_PER_AUDIO_S = 0.002 / 60  # Google's published $0.002/min text output estimate
LIVE_IN_H, LIVE_OUT_H = 0.30, 0.24
ARMS = {"A0": (15, 180), "A1": (30, 180), "A2": (15, 90), "A3": (30, 90), "A5": (15, 120), "A6": (15, 60)}
TRUE_IDS = {"e1": 3, "long30m": 2, "long60": 5}
CONCURRENCY = 1

EVID.mkdir(parents=True, exist_ok=True)
measure.EVIDENCE = c4.EVIDENCE = c4_stop.EVIDENCE = EVID
measure.STATUS = STATUS


def spent_usd():
    path = LEDGER_DIR / f"{LANE}.jsonl"
    total = 0.0
    if path.exists():
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("kind") == "error":
                continue
            total += float(row.get("cost_usd") or 0) + float(row.get("audio_s") or 0) * OUTPUT_USD_PER_AUDIO_S
    return total


def call(part, start, end, metadata):
    seconds = len(part) / 16000
    estimate = seconds * (0.00005 + OUTPUT_USD_PER_AUDIO_S)
    if spent_usd() + estimate > CAP_USD - 0.1:
        raise RuntimeError(f"P65 cap: spent ${spent_usd():.3f} + ${estimate:.3f} > ${CAP_USD}")
    result = diarize_window(part, ledger_lane=LANE, max_attempts=3)
    anomaly = result.timing_anomalies or {"clamped": 0, "dropped": 0}
    row = {"start": start, "end": end, "audio_s": seconds,
           "words": [vars(word) for word in result.words],
           "cached": result.cached, "api_latency_s": result.latency_s,
           "concurrency": None if result.cached else CONCURRENCY,
           "cost_usd": result.cost_usd(), "timing_anomalies": anomaly,
           "timing_anomaly_rate": sum(anomaly.values()) / max(1, len(result.words) + anomaly["dropped"])}
    print(json.dumps({**metadata, "start": start, "end": end, "audio_s": round(seconds, 2),
                      "words": len(result.words), "labels": len({w.speaker for w in result.words}),
                      "cached": result.cached, "api_latency_s": round(result.latency_s, 3),
                      "spent_usd": round(spent_usd(), 4)}), flush=True)
    return row


c4_stop.call = call  # every periodic/Stop call of the bench runner goes through the P65 guard


def safe(clip):
    return clip.clip_id.replace(":", "_")


def prefill_vectors(clip, step, length, source_step):
    """Reuse numeric vectors of identical windows from a superset schedule (same audio span)."""
    src = [P61, EVID]
    target = EVID / f"vectors-span2s-{clip.tier}-{clip.clip_id}-S{step:g}-L{length:g}.json"
    if target.exists():
        return
    rows = None
    for directory in src:
        path = directory / f"vectors-span2s-{clip.tier}-{clip.clip_id}-S{source_step:g}-L{length:g}.json"
        if path.exists():
            rows = {(r["start"], r["end"]): r for r in json.loads(path.read_text())}
            break
    if rows is None:
        return
    pcm = c4.clip_pcm(clip, False)
    schedule = list(measure.windows(pcm, step, length))[:-1]
    picked = [rows.get((start, end)) for start, end, _ in schedule]
    if all(picked):
        target.write_text(json.dumps([{"start": r["start"], "end": r["end"],
                                       "embeddings": r["embeddings"]} for r in picked]))


def growing_arm(arm, clip):
    step, length = ARMS[arm]
    if arm in ("A1", "A3"):
        prefill_vectors(clip, step, length, 15)
    out = c4_stop.run_clip(clip, step, length, mix=False, holds=(0,))
    return summarize_growing(arm, clip, out)


def summarize_growing(arm, clip, out):
    data = out["by_hold"]["H0"]
    v = data["variants"]["C1_C3_local_birth2"]
    first = v["first"]["metrics"] if v["first"] else None
    obs_path = c4.observation_path(clip, out["S"], out["Lmax"], False)
    rows = [json.loads(line) for line in obs_path.read_text().splitlines()] if obs_path.exists() else []
    return {"arm": arm, "case": clip.clip_id, "tier": clip.tier, "duration_s": out["duration_s"],
            "der": first["der"] if first else None, "der_raw": first.get("der_raw") if first else None,
            "ids": v["speaker_count"], "last_ids": v["last_speaker_count"],
            "S00_s": v["unattributed_s"],
            "lag_p50_s": v["latency_with_api_p50_s"], "lag_p90_s": v["latency_with_api_p90_s"],
            "audio_sent_s": data["audio_sent_s"], "batch_cost_usd": data["batch_cost_usd"],
            "calls": data["windows"], "cached_calls": data["cached_calls"],
            "new_call_concurrency": sorted({r.get("concurrency") for r in rows if not r.get("cached")} - {None}),
            "timing_anomalies": data["timing_anomalies"]}


# ---------------------------------------------------------------- A4 exemplar-anchored


class AnchoredRegistry(SpeakerRegistry):
    """Prototype registry + additive exemplar support. Zero anchors == SpeakerRegistry exactly."""

    def observe_anchored(self, window_start_s, words, embeddings, anchor):
        from registry import assignment, cosine
        labels = sorted({str(field(w, "speaker")) for w in words})
        groups = self._groups(words, labels, embeddings)
        group_by_label = {label: min(group) for group in groups for label in group}
        representatives = sorted({min(group) for group in groups})
        group_embeddings = {}
        if embeddings:
            for group in groups:
                vectors = [embeddings[label] for label in group if label in embeddings]
                if vectors:
                    group_embeddings[min(group)] = [sum(v[i] for v in vectors) / len(vectors)
                                                    for i in range(len(vectors[0]))]
        anchor_ids = {mid for per in anchor.values() for mid in per}
        previous_ids = sorted({row[2] for row in self.previous if row[2] != "S00"})
        available_ids = sorted(set(previous_ids) | set(self.centroids) | anchor_ids)
        support = {(label, mid): 0.0 for label in representatives for mid in available_ids}
        for w in words:
            label = group_by_label[str(field(w, "speaker"))]
            start = window_start_s + float(field(w, "start"))
            end = window_start_s + float(field(w, "end"))
            candidates = [(min(end, pe) - max(start, ps), mid) for ps, pe, mid in self.previous]
            if candidates:
                duration, mid = max(candidates)
                if duration > 0 and mid != "S00":
                    support[(label, mid)] += duration
        for label, per in anchor.items():
            if label in group_by_label:
                for mid, seconds in per.items():
                    support[(group_by_label[label], mid)] += seconds
        weights = []
        for label in representatives:
            row = []
            for mid in available_ids:
                overlap = support[(label, mid)]
                acoustic = -1.0
                if label in group_embeddings and mid in self.centroids:
                    acoustic = cosine(group_embeddings[label], self.centroids[mid])
                if overlap >= self.min_overlap_s:
                    row.append(overlap)
                elif self.embedding_threshold is not None and acoustic >= self.embedding_threshold:
                    row.append(acoustic)
                else:
                    row.append(0.0)
            weights.append(row)
        chosen = assignment(weights)
        mapped_groups = {}
        for label, col in zip(representatives, chosen):
            if col is None:
                speech_s = sum(max(0.0, float(field(w, "end")) - float(field(w, "start")))
                               for w in words if group_by_label[str(field(w, "speaker"))] == label)
                if speech_s < self.birth_min_s:
                    closest = max(((support[(label, mid)], mid) for mid in available_ids), default=(0.0, None))
                    mapped_groups[label] = closest[1] if closest[0] > 0 else "S00"
                else:
                    mapped_groups[label] = f"M{self.next_id}"
                    self.next_id += 1
                    self.births += 1
            else:
                mapped_groups[label] = available_ids[col]
        mapped = {label: mapped_groups[group_by_label[label]] for label in labels}
        self.previous = [(window_start_s + float(field(w, "start")), window_start_s + float(field(w, "end")),
                          mapped[str(field(w, "speaker"))])
                         for w in words if mapped[str(field(w, "speaker"))] != "S00"]
        for label, vector in group_embeddings.items():
            mid = mapped_groups[label]
            if mid == "S00":
                continue
            old = self.centroids.get(mid)
            self.centroids[mid] = list(vector) if old is None else [0.8 * a + 0.2 * b for a, b in zip(old, vector)]
        self.local_merges += 0
        return mapped


A4_RECENT_S, A4_STEP_S, A4_EXEMPLAR_MAX_S, A4_EXEMPLAR_MIN_S, A4_GAP_S, A4_MAX_SPEAKERS = 30.0, 15.0, 6.0, 1.5, 0.8, 5


def clean_spans(committed, before):
    """Continuous same-ID committed word runs (gap ≤ .6 s) ending by `before`, untouched by other IDs."""
    words = sorted((w for w in committed if w["speaker"] != "S00" and w["end"] <= before
                    and w["end"] > w["start"]), key=lambda w: (w["start"], w["end"]))
    runs = []
    for w in words:
        if runs and runs[-1]["mid"] == w["speaker"] and w["start"] - runs[-1]["end"] <= 0.6:
            runs[-1]["end"] = max(runs[-1]["end"], w["end"])
        else:
            runs.append({"mid": w["speaker"], "start": w["start"], "end": w["end"]})
    from bisect import bisect_left, bisect_right
    starts = [w["start"] for w in words]
    spans = {}
    for run in runs:
        s, e = run["start"], run["end"]
        nearby = words[bisect_left(starts, s - 10.0):bisect_right(starts, e + .3)]
        if any(o["speaker"] != run["mid"] and o["speaker"] != "S00" and o["end"] > s - .3 and o["start"] < e + .3
               for o in nearby):
            continue
        e = min(e, s + A4_EXEMPLAR_MAX_S)
        if e - s >= A4_EXEMPLAR_MIN_S:
            spans.setdefault(run["mid"], []).append((round(s, 3), round(e, 3)))
    return spans


def choose_exemplars(committed, before, current, last_active):
    for mid, spans in clean_spans(committed, before).items():
        best = max(spans, key=lambda span: (span[1] - span[0], -span[0]))
        old = current.get(mid)
        if old is None or (best[1] - best[0]) > (old[1] - old[0]) + 1e-6:
            current[mid] = best
    order = sorted(current, key=lambda mid: -last_active.get(mid, 0.0))[:A4_MAX_SPEAKERS]
    return [(mid, current[mid]) for mid in sorted(order)]


def compose(pcm, exemplars, recent_start, recent_end):
    parts, layout, cursor = [], [], 0.0
    gap = np.zeros(round(A4_GAP_S * 16000), dtype=np.int16)
    for mid, (s, e) in exemplars:
        clip = pcm[round(s * 16000):round(e * 16000)]
        layout.append({"mid": mid, "source": [s, e], "at": [round(cursor, 4), round(cursor + len(clip) / 16000, 4)]})
        parts += [clip, gap]
        cursor += (len(clip) + len(gap)) / 16000
    recent = pcm[round(recent_start * 16000):round(recent_end * 16000)]
    return np.concatenate(parts + [recent]) if parts else recent, layout, cursor


def anchors_from_prefix(words, layout, prefix_len):
    prefix = [w for w in words if (w["start"] + w["end"]) / 2 < prefix_len - A4_GAP_S / 2]
    recent = [w for w in words if (w["start"] + w["end"]) / 2 >= prefix_len - A4_GAP_S / 2]
    anchor, per_exemplar = {}, []
    for ex in layout:
        a, b = ex["at"]
        durations = {}
        for w in prefix:
            mid_t = (w["start"] + w["end"]) / 2
            if a - .2 <= mid_t <= b + .2:
                d = max(0.05, min(w["end"], b) - max(w["start"], a))
                durations[w["speaker"]] = durations.get(w["speaker"], 0.0) + d
        total = sum(durations.values())
        dominant = max(durations, key=durations.get) if durations else None
        split = bool(total) and sum(1 for v in durations.values() if v >= .2 * total) > 1
        per_exemplar.append({"mid": ex["mid"], "labels": durations, "dominant": dominant,
                             "split": split, "missing": not durations})
        for label, seconds in durations.items():
            anchor.setdefault(label, {})
            anchor[label][ex["mid"]] = anchor[label].get(ex["mid"], 0.0) + seconds
    dominants = [e["dominant"] for e in per_exemplar if e["dominant"] is not None]
    merged = len(dominants) - len(set(dominants))
    return prefix, recent, anchor, per_exemplar, merged


_EMBEDDER = None


def embedder():
    global _EMBEDDER
    if _EMBEDDER is None:
        from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
        _EMBEDDER = _OnnxWeSpeakerEmbedder(ROOT.parent / "streaming-diarization" / "data" /
                                           "voxceleb_resnet152_LM.onnx", device="cpu")
    return _EMBEDDER


def a4_arm(clip):
    pcm = c4.clip_pcm(clip, False)
    duration = len(pcm) / 16000
    receipt = EVID / f"a4-calls-{clip.tier}-{safe(clip)}.jsonl"
    retained = [json.loads(line) for line in receipt.read_text().splitlines()] if receipt.exists() else []
    registry = AnchoredRegistry(min_overlap_s=.3, embedding_threshold=.46, within_window_threshold=.6,
                                birth_min_s=2)
    committed, exemplars, last_active = [], {}, {}
    frontier, lags, rows = 0.0, [], []
    ticks = [float(t) for t in np.arange(A4_STEP_S, duration, A4_STEP_S)] + [duration]
    stats = {"calls": 0, "exemplar_observations": 0, "split": 0, "missing": 0, "merged_pairs": 0,
             "calls_with_inconsistency": 0, "anchor_vs_final_disagreements": 0}
    for index, t in enumerate(ticks):
        is_stop = index == len(ticks) - 1
        recent_start = max(0.0, t - A4_RECENT_S)
        chosen = choose_exemplars(committed, recent_start, exemplars, last_active)
        audio, layout, prefix_len = compose(pcm, chosen, recent_start, t)
        if index < len(retained) and retained[index]["layout"] == layout and \
                (retained[index]["recent"] == [round(recent_start, 4), round(t, 4)]):
            row = retained[index]
        else:
            if index < len(retained):
                raise ValueError(f"A4 replay diverged at call {index}: {receipt}")
            row = call(audio, round(recent_start, 4), round(t, 4),
                       {"arm": "A4", "case": clip.clip_id, "call": index + 1, "calls": len(ticks),
                        "exemplars": len(layout)})
            row.update({"layout": layout, "recent": [round(recent_start, 4), round(t, 4)],
                        "prefix_s": round(prefix_len, 4)})
            prefix, recent, anchor, per_ex, merged = anchors_from_prefix(row["words"], layout, prefix_len)
            rel = [{**w, "start": max(0.0, w["start"] - prefix_len), "end": max(0.0, w["end"] - prefix_len)}
                   for w in recent]
            row["recent_words"] = rel
            vectors = {}
            for label in {w["speaker"] for w in rel}:
                intervals = measure.embedding_intervals(recent_start, rel, label)
                if intervals:
                    vectors[label] = [float(x) for x in embedder().embed(clip.audio, intervals)]
            row.update({"anchor": anchor, "per_exemplar": per_ex, "merged": merged, "embeddings": vectors})
            with receipt.open("a") as file:
                file.write(json.dumps(row) + "\n")
        mapping = registry.observe_anchored(recent_start, row["recent_words"], row["embeddings"], row["anchor"])
        stats["calls"] += 1
        stats["exemplar_observations"] += len(row["per_exemplar"])
        stats["split"] += sum(e["split"] for e in row["per_exemplar"])
        stats["missing"] += sum(e["missing"] for e in row["per_exemplar"])
        stats["merged_pairs"] += row["merged"]
        stats["calls_with_inconsistency"] += bool(row["merged"] or any(e["split"] or e["missing"]
                                                                          for e in row["per_exemplar"]))
        for label, per in row["anchor"].items():
            if label in mapping and per:
                strongest = max(per, key=per.get)
                if per[strongest] >= .3 and mapping[label] != strongest:
                    stats["anchor_vs_final_disagreements"] += 1
        absolute = [{"start": recent_start + w["start"], "end": recent_start + w["end"],
                     "speaker": mapping[w["speaker"]], "text": w["text"]} for w in row["recent_words"]]
        fresh = [w for w in absolute if frontier < w["end"] <= t]
        committed.extend(fresh)
        for w in fresh:
            if w["speaker"] != "S00":
                last_active[w["speaker"]] = max(last_active.get(w["speaker"], 0.0), w["end"])
        if not is_stop:
            lags.extend(t + row["api_latency_s"] - w["end"] for w in fresh)
        rows.append(row)
        frontier = t
    committed.sort(key=lambda w: (w["start"], w["end"]))
    state = {"first_words": committed, "first_segments": measure.segmentize(committed),
             "first_immediate_segments": measure.segmentize(committed)}
    reference = [] if clip.tier == "e1" else clip.reference_segments()
    excluded = [r for r in reference if clip.tier != "synth" and (r["speaker"] == "<EXCLUDE>" or not r["text"].strip())]
    masks = [(r["start"], r["end"]) for r in excluded]
    reference = [r for r in reference if r not in excluded]
    scored = c4.score_view(clip, reference, masks, state, "first")
    metrics = scored["metrics"] if scored else None
    out = {"arm": "A4", "case": clip.clip_id, "tier": clip.tier, "duration_s": duration,
           "der": metrics["der"] if metrics else None, "der_raw": metrics.get("der_raw") if metrics else None,
           "ids": len({w["speaker"] for w in committed if w["speaker"] != "S00"}),
           "last_ids": len({w["speaker"] for w in committed if w["speaker"] != "S00"}),
           "S00_s": measure.span_seconds([w for w in committed if w["speaker"] == "S00"]),
           "lag_p50_s": measure.percentile(lags, 50), "lag_p90_s": measure.percentile(lags, 90),
           "audio_sent_s": sum(r["audio_s"] for r in rows),
           "batch_cost_usd": sum(r["cost_usd"] for r in rows),
           "calls": len(rows), "cached_calls": sum(bool(r["cached"]) for r in rows),
           "new_call_concurrency": sorted({r.get("concurrency") for r in rows if not r.get("cached")} - {None}),
           "timing_anomalies": {k: sum(r["timing_anomalies"][k] for r in rows) for k in ("clamped", "dropped")},
           "births": registry.births, "exemplar_stats": stats}
    (EVID / f"a4-score-{clip.tier}-{safe(clip)}.json").write_text(json.dumps(
        {**out, "metrics": metrics}, indent=2))
    return out


# ---------------------------------------------------------------- summary


def baseline_row(clip):
    path = P61 / f"c4-stop-score-{clip.tier}-{safe(clip)}-S15-L180.json"
    return summarize_growing("A0", clip, json.loads(path.read_text()))


def per_hour(row):
    duration = row["duration_s"]
    metered = row["batch_cost_usd"] * 3600 / duration + LIVE_IN_H
    output = row["audio_sent_s"] * OUTPUT_USD_PER_AUDIO_S * 3600 / duration + LIVE_OUT_H
    return metered, metered + output


def gather(arm, tier_clips):
    rows = []
    for clip in tier_clips:
        if arm == "A0":
            rows.append(baseline_row(clip))
            continue
        path = (EVID / f"a4-score-{clip.tier}-{safe(clip)}.json" if arm == "A4" else
                EVID / f"c4-stop-score-{clip.tier}-{safe(clip)}-S{ARMS[arm][0]:g}-L{ARMS[arm][1]:g}.json")
        if not path.exists():
            rows.append(None)
            continue
        data = json.loads(path.read_text())
        rows.append(data if arm == "A4" else summarize_growing(arm, clip, data))
    return rows


def summary():
    selected = {"accept6": clips("accept6"), "e1": clips("e1"),
                "long30m": [c for c in clips("long30m") if "lex_bill_ackman" in c.clip_id],
                "long60": clips("long60")}
    table = {}
    for arm in ("A0", "A1", "A2", "A3", "A4"):
        entry = {}
        for tier, tier_clips in selected.items():
            rows = gather(arm, tier_clips)
            if any(r is None for r in rows):
                entry[tier] = None
                continue
            if tier == "accept6":
                entry[tier] = {"der_macro": float(np.mean([r["der"] for r in rows])),
                               "der_raw_macro": float(np.mean([r["der_raw"] for r in rows])),
                               "lag_p50_case_median": float(np.median([r["lag_p50_s"] for r in rows])),
                               "lag_p90_case_median": float(np.median([r["lag_p90_s"] for r in rows])),
                               "anomalies": {k: sum(r["timing_anomalies"][k] for r in rows) for k in ("clamped", "dropped")}}
            else:
                r = rows[0]
                metered, with_output = per_hour(r)
                entry[tier] = {"ids": r["ids"], "last_ids": r["last_ids"], "der": r["der"],
                               "S00_s": r["S00_s"], "lag_p50": r["lag_p50_s"], "lag_p90": r["lag_p90_s"],
                               "audio_sent_x": r["audio_sent_s"] / r["duration_s"],
                               "cost_h_metered": metered, "cost_h_with_output": with_output,
                               "calls": r["calls"], "cached": r["cached_calls"],
                               "anomalies": r["timing_anomalies"],
                               "exemplar_stats": r.get("exemplar_stats")}
        table[arm] = entry
    base = table["A0"]
    for arm, entry in table.items():
        checks = {}
        if entry.get("accept6"):
            checks["accept6_der<=.110"] = entry["accept6"]["der_macro"] <= .110
        if entry.get("e1"):
            checks["e1_ids<=4"] = entry["e1"]["ids"] <= 4
        for tier in ("long30m", "long60"):
            if entry.get(tier):
                checks[f"{tier}_ids<=true+1"] = entry[tier]["ids"] <= TRUE_IDS[tier] + 1
                checks[f"{tier}_der<=A0+.03"] = entry[tier]["der"] <= base[tier]["der"] + .03
        complete = all(entry.get(t) for t in ("accept6", "e1", "long30m", "long60"))
        entry["gate"] = {"checks": checks, "complete": complete,
                         "final_off_eligible": complete and all(checks.values())}
    ledger = LEDGER_DIR / f"{LANE}.jsonl"
    new = {"calls": 0, "metered_usd": 0.0, "audio_s": 0.0}
    if ledger.exists():
        for line in ledger.read_text().splitlines():
            row = json.loads(line)
            if row.get("kind") == "error":
                continue
            new["calls"] += 1
            new["metered_usd"] += float(row.get("cost_usd") or 0)
            new["audio_s"] += float(row.get("audio_s") or 0)
    new["with_output_usd"] = new["metered_usd"] + new["audio_s"] * OUTPUT_USD_PER_AUDIO_S
    out = {"generated": datetime.now().astimezone().isoformat(), "table": table, "new_spend": new}
    (EVID / "summary.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", nargs="*", default=[])
    parser.add_argument("--tiers", nargs="*", default=[])
    parser.add_argument("--case", default="")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    CONCURRENCY = args.concurrency
    for arm in args.arms:
        for tier in args.tiers:
            for clip in clips(tier):
                if tier == "long30m" and "lex_bill_ackman" not in clip.clip_id:
                    continue
                if args.case and args.case not in clip.clip_id:
                    continue
                result = a4_arm(clip) if arm == "A4" else growing_arm(arm, clip)
                print(json.dumps({"RESULT": {k: v for k, v in result.items() if k != "exemplar_stats"},
                                  "exemplar_stats": result.get("exemplar_stats")}), flush=True)
    if args.summary:
        summary()
