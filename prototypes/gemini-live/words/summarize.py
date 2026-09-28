"""Read P52 raw receipts; recompute comparable per-clip and macro metrics."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402
from score import score  # noqa: E402
from proto_words import dropped_passages, reference_speech_seconds  # noqa: E402
from analyze_words import timing  # noqa: E402
from run_suite import EXTENDED  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")
IDS = ["discussion_jamie_dimon_180s", "discussion_rtfl_90s",
       "interview_adam_frank_180s", "interview_bill_ackman_60s",
       "interview_keyu_jin_60s", "mono_javier_intro_50s",
       "benchmark_5m:acquired_alphabet"]
SPARSE_REFERENCE = {"benchmark_5m:acquired_alphabet", "benchmark:acquired_jamie_dimon"}


def receipt(arm: str, clip_id: str, suite: str):
    tag = clip_id.replace(":", "_")
    paths = sorted(EVIDENCE.glob(f"suite-{arm}-{'extended-' if suite == 'extended' else ''}*-{tag}.json"))
    if len(paths) != 1:
        return None, paths
    return json.loads(paths[0].read_text()), paths


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--set", choices=["base", "extended"], default="base")
    args = p.parse_args()
    ids = IDS if args.set == "base" else EXTENDED
    result = {}
    for arm in ("w1", "w3", "w4"):
        rows = []
        for cid in ids:
            d, paths = receipt(arm, cid, args.set)
            if d is None:
                rows.append({"clip": cid, "status": "MISSING", "matches": [str(p) for p in paths]})
                continue
            clip = next(c for c in clips() if c.clip_id == cid)
            ref = clip.reference_segments()
            rescored = score([{**x, "speaker": "one"} for x in ref], d["hypothesis"])
            reference_timed_s = sum(x["end"] - x["start"] for x in ref)
            drop = dropped_passages(ref, d["hypothesis"])
            event_rows = d.get("events_full") or []
            oracle_path = EVIDENCE / f"oracle-{cid.replace(':', '_')}.json"
            oracle = json.loads(oracle_path.read_text())["words"] if oracle_path.exists() else None
            latency = timing(clip, event_rows, oracle) if event_rows else None
            usage_events = [e for e in event_rows if "usage" in e]
            last_usage = usage_events[-1]["audio_sent_s"] if usage_events else None
            cost_complete = bool(last_usage is not None and last_usage >= d.get("sent_s", 0) - 2) if arm != "w4" else True
            rows.append({"clip": cid, "status": "OK", "audio_s": d["audio_s"],
                         "reference_path": str(clip.reference),
                         "receipt_wer": d["score"]["wer"],
                         "reference_timed_s": round(reference_timed_s, 3),
                         "reference_timing_fraction": round(reference_timed_s / (d.get("source_audio_s") or d["audio_s"]), 3),
                         "complete_timing_proxy": reference_timed_s >= 0.95 * (d.get("source_audio_s") or d["audio_s"]),
                         "quality_qualified": cid not in SPARSE_REFERENCE,
                         "sent_s": d.get("sent_s", d["audio_s"]), "wer": rescored["wer"],
                         "dropped_reference_seconds": sum(x["end"] - x["start"] for x in drop),
                         "reference_speech_seconds": reference_speech_seconds(ref),
                         "dropped_passages": drop, "latency": latency,
                         "batch_word_latency_p50_s": d["latency_p50_s"] if arm == "w4" else None,
                         "batch_word_latency_p90_s": d["latency_p90_s"] if arm == "w4" else None,
                         "cost_usd_observed": d["cost_usd"], "cost_complete": cost_complete,
                         "model_audio_bytes": sum(e.get("model_audio_bytes", 0) for e in event_rows),
                         "usage_observations": len(usage_events),
                         "timing_anomaly_calls": d.get("timing_anomaly_calls"),
                         "timing_clamped_words": d.get("timing_clamped_words"),
                         "timing_dropped_words": d.get("timing_dropped_words"),
                         "windows": d.get("windows"), "window_errors": d.get("window_errors"),
                         "receipt": str(paths[0])})
        good = [r for r in rows if r["status"] == "OK"]
        result[arm] = {"clips": rows, "measured_clips": len(good),
                       "macro_wer": statistics.mean(r["wer"] for r in good) if good else None,
                       "quality_qualified_clips": sum(r["quality_qualified"] for r in good),
                       "quality_qualified_macro_wer": statistics.mean(r["wer"] for r in good if r["quality_qualified"])
                       if any(r["quality_qualified"] for r in good) else None,
                       "complete_timing_clips": sum(r["complete_timing_proxy"] for r in good),
                       "complete_timing_macro_wer": statistics.mean(r["wer"] for r in good if r["complete_timing_proxy"])
                       if any(r["complete_timing_proxy"] for r in good) else None,
                       "dropped_reference_seconds": sum(r["dropped_reference_seconds"] for r in good),
                       "reference_speech_seconds": sum(r["reference_speech_seconds"] for r in good),
                       "observed_cost_usd": sum(r["cost_usd_observed"] for r in good),
                       "cost_complete_clips": sum(r["cost_complete"] for r in good),
                       "anomaly_calls": sum(r["timing_anomaly_calls"] or 0 for r in good),
                       "window_calls": sum(r["windows"] or 0 for r in good),
                       "window_errors": sum(r["window_errors"] or 0 for r in good)}
    out = EVIDENCE / ("suite-comparison.json" if args.set == "base" else "suite-comparison-extended.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({arm: {k: v for k, v in d.items() if k != "clips"} for arm, d in result.items()}, indent=2))
    print(out)


if __name__ == "__main__":
    main()
