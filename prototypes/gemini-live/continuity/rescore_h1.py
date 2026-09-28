"""Zero-send H1-exact rescore of P61 rolling settled surfaces.

Run from worktree: python prototypes/gemini-live/continuity/rescore_h1.py --tier accept6
Only previously cached Gemini calls and span2s vector receipts are consumed.
"""
from __future__ import annotations

import argparse
import json
import sys

from measure import EVIDENCE, HERE, cached_embeddings, evaluate, note, windows

sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "harness"))
from common.corpus import clips  # noqa: E402
from common.gemini_common import diarize_window, read_wav  # noqa: E402
from h1_offline import score_case, macro  # noqa: E402


def rescore(clip, step_s: float, length_s: float, hold_s: float,
            first_only: bool = False, settled_only: bool = False,
            last_only: bool = False):
    observations = []
    for start, end, part in windows(read_wav(clip.audio), step_s, length_s):
        result = diarize_window(part, max_attempts=0)
        observations.append({"start": start, "end": end,
                             "words": [vars(word) for word in result.words],
                             "api_latency_s": result.latency_s})
    count, cached = cached_embeddings(clip, observations, step_s, length_s, False, None)
    if not cached:
        raise RuntimeError(f"missing L1 span2s vectors: {clip.clip_id}")
    variants = {
        "pure_C1": evaluate([], observations, hold_s, .3, include_segments=True),
        "C1_C3_local": evaluate([], observations, hold_s, .3, .46, .6,
                                include_segments=True),
    }
    scored = {}
    for name, variant in variants.items():
        # The pane measures two settled-surface definitions and their Stop-time
        # committed+preview immediate views. The terminal pass is not retained;
        # its empty input is a placeholder and final WER must not be interpreted.
        ruled = {}
        views = (
            ("first_committed", "first_segments", "first_immediate_segments"),
            ("last_revised", "last_revised_segments", "last_immediate_segments"),
        )
        for view, key, immediate_key in (views[:1] if first_only else
                                          views[1:] if last_only else views):
            raw_rows = variant[key]
            raw_immediate = variant[immediate_key]
            # A word with start=end at the window edge has zero scored duration;
            # H1 rejects it. Preserve it in the receipt while excluding it from
            # the surface passed to the H1 scorer.
            excluded = [row for row in raw_rows if row["end"] <= row["start"]]
            excluded_immediate = [row for row in raw_immediate
                                  if row["end"] <= row["start"]]
            rows = [row for row in raw_rows if row["end"] > row["start"]]
            immediate_rows = [row for row in raw_immediate
                              if row["end"] > row["start"]]
            result = score_case(clip.clip_id, immediate=[] if settled_only else immediate_rows,
                                settled=rows, final=[])
            ruled[view] = {"metrics": result["metrics"]["settled"],
                            "h1": result,
                            "speaker_count": variant["speaker_count"],
                            "immediate_speaker_count": variant["immediate_speaker_count"],
                            "births": variant["births"],
                            "local_merges": variant["local_merges"],
                            "visible_relabel_events": variant["visible_relabel_events"],
                            "visible_relabels_per_minute": variant["visible_relabels_per_minute"],
                            "latency_p50_s": variant["latency_p50_s"],
                            "latency_p90_s": variant["latency_p90_s"],
                            "latency_with_api_p50_s": variant["latency_with_api_p50_s"],
                            "latency_with_api_p90_s": variant["latency_with_api_p90_s"],
                            "zero_duration_excluded_settled": excluded,
                            "zero_duration_excluded_immediate": excluded_immediate,
                            "immediate_segments": immediate_rows,
                            "segments": rows}
        scored[name] = ruled
    return {"case": clip.clip_id, "tier": clip.tier,
            "reference_set": "H1 manifest 80fc15bd" if clip.tier == "accept6" else "public tier reference",
            "hold_s": hold_s,
            "windows": len(observations), "eligible_vectors": count,
            "immediate": "unmeasured placeholder" if settled_only else "Stop-time committed+last-window preview",
            "final": "unmeasured placeholder excluded from verdict",
            "variants": scored}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=["accept6", "gold9", "bench5m", "long30m"],
                        required=True)
    parser.add_argument("--case", default="")
    parser.add_argument("--step", type=float, default=10)
    parser.add_argument("--length", type=float, default=30)
    parser.add_argument("--hold", type=float, default=5)
    parser.add_argument("--first-only", action="store_true")
    parser.add_argument("--last-only", action="store_true")
    parser.add_argument("--settled-only", action="store_true")
    args = parser.parse_args()
    if args.first_only and args.last_only:
        parser.error("--first-only and --last-only are exclusive")
    selected = [clip for clip in clips(args.tier)
                if (not args.case or args.case in clip.clip_id)]
    note(f"Start zero-send H1-exact rescore: {args.tier}, {len(selected)} cases, "
         f"S{args.step:g}/L{args.length:g}/H{args.hold:g}; "
         f"first_only={args.first_only}, last_only={args.last_only}, "
         f"settled_only={args.settled_only}, final unmeasured")
    results = []
    for clip in selected:
        try:
            result = rescore(clip, args.step, args.length, args.hold,
                             args.first_only, args.settled_only, args.last_only)
        except ValueError as exc:
            if clip.clip_id != "benchmark:acquired_nfl" or "field text must be non-empty" not in str(exc):
                raise
            note(f"H1-exact {clip.clip_id}: UNMEASURED, reference row 6 has empty text; "
                 "shared scorer rejects it")
            print(json.dumps({"case": clip.clip_id, "h1_exact": "UNMEASURED",
                              "reason": str(exc)}), flush=True)
            continue
        results.append(result)
        suffix = "-last-only" if args.last_only else "-first-only" if args.first_only else ""
        path = EVIDENCE / f"h1-exact-{clip.tier}-{clip.clip_id}-S{args.step:g}-L{args.length:g}-H{args.hold:g}{suffix}.json"
        path.write_text(json.dumps(result, indent=2))
        print(json.dumps({"case": clip.clip_id,
                          "settled": {method: {view: scored["metrics"]
                                               for view, scored in views.items()}
                                      for method, views in result["variants"].items()}}), flush=True)
        view_key = "last_revised" if args.last_only else "first_committed"
        note(f"H1-exact {clip.clip_id}: pure {view_key} ruled DER "
             f"{result['variants']['pure_C1'][view_key]['metrics']['der']:.6f}; "
             f"C3+local {view_key} ruled DER "
             f"{result['variants']['C1_C3_local'][view_key]['metrics']['der']:.6f}; "
             f"receipt {path.name}")
    for method in ("pure_C1", "C1_C3_local"):
        for view in (("first_committed",) if args.first_only else
                     ("last_revised",) if args.last_only else
                     ("first_committed", "last_revised")):
            scored = [r["variants"][method][view]["h1"] for r in results]
            bounds = macro(scored)
            rows = [r["metrics"]["settled"] for r in scored]
            print(json.dumps({"tier": args.tier, "hold_s": args.hold, "method": method, "view": view,
                              "cases": len(rows), "h1_macro_settled_der": bounds["diarization_error_rate"],
                              "ruled_der_macro": sum(x["der"] for x in rows) / len(rows),
                              "raw_der_macro": sum(x["der_raw"] for x in rows) / len(rows)}), flush=True)
