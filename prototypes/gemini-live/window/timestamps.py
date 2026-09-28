"""PROTOTYPE — Gemini word-timestamp inventory and bounded R2 repair.

One command from the worktree root:
  PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/gemini-live/window/timestamps.py
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
import gemini_common as gc  # noqa: E402

OUT = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P53/timestamps-inventory.json")
QUALITY = OUT.with_name("timestamps-quality-r2.json")
CHUNK_CALLS = OUT.with_name("timestamps-chunk-calls.json")
CHUNKS = OUT.with_name("timestamps-chunks-r2.json")
REPAIR_INVENTORY = OUT.with_name("timestamps-repair-inventory-r2.json")
STATUS = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/status/PANE-5.3-STATUS.md")
BOUNDS = (30, 60, 120, 300, 600, 1200, 1800, 2586)


def bucket(seconds: float) -> str:
    lower = 0
    for upper in BOUNDS:
        if seconds <= upper + 1e-6:
            return f"({lower},{upper}]"
        lower = upper
    return ">2586"


def anomalies(words: list[gc.Word]) -> dict:
    backward = [i for i in range(1, len(words)) if words[i].start < words[i-1].start - .5]
    duration = [i for i, w in enumerate(words) if w.end - w.start > 5]
    isolated = [i for i in range(1, len(words)-1)
                if abs(words[i].start-words[i-1].start) > 5
                and abs(words[i].start-words[i+1].start) > 5
                and abs(words[i-1].start-words[i+1].start) <= 5]
    excursion = []
    for i in range(1, len(words)-1):
        first = words[i].start - words[i-1].start
        if abs(first) <= 5:
            continue
        for j in range(i+1, min(i+11, len(words))):
            second = words[j].start - words[j-1].start
            if first*second < 0 and abs(words[j].start-words[i-1].start) <= 5:
                excursion.append([i, j, round(first, 3), round(second, 3)])
                break
    return {"backward": backward, "duration_gt5": duration,
            "isolated_start": isolated, "short_excursion": excursion}


def repair(words: list[gc.Word], audio_s: float, *, jump_s: float = 10) -> tuple[list[gc.Word], dict]:
    """R2: fix implausible single words before local islands; preserve word order/content."""
    fixed = list(words)
    changed = set()
    isolated = duration = 0
    for i in range(1, len(words)-1):
        prev, w, following = words[i-1], words[i], words[i+1]
        bad_start = (abs(w.start-prev.start) > jump_s and abs(w.start-following.start) > jump_s
                     and abs(prev.start-following.start) <= jump_s
                     and prev.end-prev.start <= 5 and following.end-following.start <= 5)
        bad_duration = w.end-w.start > 5
        if not (bad_start or bad_duration):
            continue
        if bad_start:
            start = max(prev.start, min(following.start, (prev.end+following.start)/2))
            length = min(max(w.end-w.start, .1), 1.0)
            end = min(start+length, following.start) if following.start > start else start+length
            isolated += 1
        else:
            start = w.start
            end = min(start+1.0, following.start) if following.start > start else start+1.0
        if end <= start:
            end = start + .1
        start, end = max(0.0, min(start, audio_s)), max(0.0, min(end, audio_s))
        if end > start:
            fixed[i] = gc.Word(w.text, w.speaker, start, end)
            changed.add(i)
            if bad_duration:
                duration += 1
    islands = []
    i = 1
    while i < len(fixed)-1:
        first_jump = fixed[i].start - fixed[i-1].start
        if abs(first_jump) <= jump_s:
            i += 1
            continue
        end = next((j for j in range(i+1, min(i+31, len(fixed)))
                    if first_jump * (fixed[j].start - fixed[j-1].start) < 0
                    and abs(fixed[j].start - fixed[i-1].start) <= jump_s), None)
        if end is None or any(fixed[k].end-fixed[k].start > 5 for k in range(i, end)):
            i += 1
            continue
        shift = ((fixed[i-1].end + fixed[end].start) -
                 (fixed[i].start + fixed[end-1].end)) / 2
        if all(0 <= fixed[k].start+shift <= fixed[k].end+shift <= audio_s for k in range(i, end)):
            for k in range(i, end):
                w = fixed[k]
                fixed[k] = gc.Word(w.text, w.speaker, w.start+shift, w.end+shift)
                changed.add(k)
            islands.append({"first": i, "last": end-1, "shift_s": round(shift, 3)})
            i = end
        else:
            i += 1
    return fixed, {"changed_words": len(changed), "islands": islands,
                   "isolated_words": isolated, "duration_words": duration}


def quality() -> None:
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parent / "harness"))
    from corpus import clips
    from final_policy import VECTORS, cached_words, merge_map
    from h1_offline import score_case
    from probe import safe_diarization

    vectors = json.loads(VECTORS.read_text())
    chosen = [c for c in clips() if c.tier == "accept6" or c.clip_id == "benchmark_30m:lex_bill_ackman"
              or (c.tier == "synth" and c.clip_id.endswith("_s1"))]
    results = {}
    for c in chosen:
        audio = gc.read_wav(c.audio)
        original = cached_words(audio).words
        mapping, _ = merge_map(original, vectors[c.clip_id], .65, 2.0, constraint=True, order="single")
        repaired, edits = repair(original, len(audio)/gc.SAMPLE_RATE)
        scores = {}
        for name, ww in (("raw", original), ("sorted", sorted(original, key=lambda w:(w.start,w.end))),
                         ("repaired", repaired)):
            hyp = gc.words_to_segments(ww, speaker_map=mapping)
            if c.tier == "accept6":
                metrics = score_case(c.clip_id, immediate=[], settled=[], final=hyp)["metrics"]["final"]
                scores[name] = {"der": metrics["der"], "wer": metrics.get("wer"),
                                "reference_speech_der": metrics.get("reference_speech_der"),
                                "segments": len(hyp)}
            else:
                metrics = safe_diarization(c.reference_segments(), hyp)
                scores[name] = {"der": metrics["der"], "segments": len(hyp)}
        results[c.clip_id] = {"tier": c.tier, "duration_s": len(audio)/gc.SAMPLE_RATE,
                              "words": len(original), "labels": len(set(mapping.values())),
                              "raw_anomalies": anomalies(original),
                              "repair": edits, "repaired_anomalies": anomalies(repaired),
                              "score": scores}
        QUALITY.write_text(json.dumps(results, indent=2) + "\n")
        print("SCORE", c.clip_id, "DER", {k:v["der"] for k,v in scores.items()},
              "edits", edits["changed_words"], flush=True)
    accept = [v for v in results.values() if v["tier"] == "accept6"]
    print("ACCEPT6 FINAL DER MACRO", {k:round(sum(v["score"][k]["der"] for v in accept)/len(accept),6)
                                     for k in ("raw","sorted","repaired")})
    print("WROTE", QUALITY)


def repair_inventory() -> None:
    snapshot = json.loads(OUT.read_text())
    grouped = defaultdict(list)
    for prior in snapshot["calls"]:
        raw = json.loads((gc.CACHE_DIR / prior["cache_file"]).read_text())
        words = gc._parse(raw, cached=True).words
        fixed, edits = repair(words, prior["audio_s"])
        after = anomalies(fixed)
        row = {"cache_file": prior["cache_file"], "bucket": prior["bucket"],
               "words": len(words), "changed_words": edits["changed_words"],
               "islands": len(edits["islands"]),
               "large_backward_before": sum(words[i-1].start-words[i].start > 10
                                            for i in range(1, len(words))),
               "large_backward_after": sum(fixed[i-1].start-fixed[i].start > 10
                                           for i in range(1, len(fixed))),
               "residual_backward": len(after["backward"]),
               "residual_duration_gt5": len(after["duration_gt5"]),
               "residual_isolated_start": len(after["isolated_start"])}
        assert len(fixed) == len(words)
        assert all((a.text, a.speaker) == (b.text, b.speaker) for a, b in zip(words, fixed))
        grouped[row["bucket"]].append(row)
    summary = []
    for key in [bucket(upper) for upper in BOUNDS] + [">2586"]:
        rows = grouped[key]
        summary.append({"bucket": key, "calls": len(rows),
                        "changed_calls": sum(r["changed_words"] > 0 for r in rows),
                        "changed_words": sum(r["changed_words"] for r in rows),
                        "islands": sum(r["islands"] for r in rows),
                        "large_backward_before": sum(r["large_backward_before"] for r in rows),
                        "large_backward_after": sum(r["large_backward_after"] for r in rows),
                        "residual_backward_calls": sum(r["residual_backward"] > 0 for r in rows),
                        "residual_duration_gt5_calls": sum(r["residual_duration_gt5"] > 0 for r in rows),
                        "residual_isolated_start_calls": sum(r["residual_isolated_start"] > 0 for r in rows)})
    REPAIR_INVENTORY.write_text(json.dumps({"snapshot_calls": len(snapshot["calls"]),
                                            "summary": summary}, indent=2) + "\n")
    for row in summary:
        print("REPAIR BUCKET", row)
    print("WROTE", REPAIR_INVENTORY)


def note(message: str) -> None:
    line = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} TIMESTAMPS {message}"
    with STATUS.open("a") as out:
        out.write(line + "\n")
    print(line, flush=True)


def lex_id_count(reference: list[dict], words: list[dict], mapping: dict[str, str]) -> tuple[int, dict]:
    lex = [r for r in reference if r["speaker"] == "Lex Fridman"]
    spans = defaultdict(list)
    for word in words:
        if not word["core"]:
            continue
        for row in lex:
            start, end = max(word["start"], row["start"]), min(word["end"], row["end"])
            if end > start:
                spans[mapping[word["node"]]].append((start, end))
    support = {}
    for label, intervals in spans.items():
        merged = []
        for start, end in sorted(intervals):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        support[label] = round(sum(end-start for start, end in merged), 3)
    return sum(seconds >= 2 for seconds in support.values()), dict(sorted(support.items()))


def chunks() -> None:
    sys.path.insert(0, str(HERE))
    sys.path.insert(0, str(HERE.parent / "continuity"))
    from corpus import clips
    from final_policy import MODEL
    from probe import safe_diarization
    from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder
    import long_final as long
    import long_final_gated as gated

    chosen = [c for c in clips() if c.clip_id in {"benchmark_30m:lex_bill_ackman", "long60"}]
    calls = json.loads(CHUNK_CALLS.read_text()) if CHUNK_CALLS.exists() else {}
    results = json.loads(CHUNKS.read_text()) if CHUNKS.exists() else {}
    embedder = _OnnxWeSpeakerEmbedder(MODEL, device="cpu")
    for c in chosen:
        audio = gc.read_wav(c.audio)
        duration = len(audio)/gc.SAMPLE_RATE
        for cap in (600, 900, 1200, 1800):
            if cap == 1800 and duration <= 1800:
                continue
            key = f"{c.clip_id}|T{cap}|O30"
            if key in results:
                continue
            plan = long.schedule(duration, cap, 30)
            base_chunks = []
            for i, bounds in enumerate(plan):
                call_key = f"{key}|c{i}"
                part = audio[round(bounds["start"]*gc.SAMPLE_RATE):round(bounds["end"]*gc.SAMPLE_RATE)]
                if call_key not in calls and sum(row["cost_usd"] for row in calls.values()) + len(part)/gc.SAMPLE_RATE*.0002 >= 1:
                    raise RuntimeError("$1 timestamp brief guard before " + call_key)
                response = gc.diarize_window(part, use_cache=True, max_attempts=3, ledger_lane="P53-timestamps")
                if call_key not in calls:
                    calls[call_key] = {"start": bounds["start"], "end": bounds["end"],
                                       "audio_s": len(part)/gc.SAMPLE_RATE, "cached": response.cached,
                                       "words": len(response.words), "labels": len({w.speaker for w in response.words}),
                                       "timing_anomalies": response.timing_anomalies,
                                       "cost_usd": 0.0 if response.cached else response.cost_usd()}
                    CHUNK_CALLS.write_text(json.dumps(calls, indent=2) + "\n")
                    note(f"CHUNK CALL {call_key} {len(part)/gc.SAMPLE_RATE:.0f}s "
                         f"cached={response.cached} anomaly={response.timing_anomalies} "
                         f"cost=${calls[call_key]['cost_usd']:.6f}")
                base_chunks.append({"index": i, **bounds, "words": response.words})
            arms = {}
            for mode in ("raw", "repaired"):
                edits = []
                mode_chunks = []
                for row in base_chunks:
                    words, change = (repair(row["words"], row["end"]-row["start"])
                                     if mode == "repaired" else (row["words"], {"changed_words": 0}))
                    edits.append(change["changed_words"])
                    mode_chunks.append({**row, "words": words})
                nodes, all_words, excluded = long.observed(c, mode_chunks, embedder)
                edges, seams = long.overlap_edges(mode_chunks, all_words)
                mapping, edge_info = gated.partition(nodes, excluded, edges)
                core = [gc.Word(w["text"], mapping[w["node"]], w["start"], w["end"])
                        for w in all_words if w["core"]]
                hyp = gc.words_to_segments(core)
                reference = c.reference_segments()
                metric = safe_diarization(reference, hyp)
                lex_count, lex_support = lex_id_count(reference, all_words, mapping)
                arms[mode] = {"score": metric, "ids": len(set(mapping.values())),
                              "lex_ids_2s": lex_count, "lex_support_s": lex_support,
                              "false_merge_groups": long.identity_diagnostic(c, all_words, mapping)["false_merge_groups"],
                              "edits_by_call": edits, "core_words": len(core),
                              "seams": seams, "edge_info": edge_info, "mapping": mapping}
            results[key] = {"clip_id": c.clip_id, "cap_s": cap, "overlap_s": 30,
                            "duration_s": duration, "calls": len(plan), "truth_ids": len({r['speaker'] for r in c.reference_segments()}),
                            "arms": arms}
            CHUNKS.write_text(json.dumps(results, indent=2) + "\n")
            note(f"CHUNK RESULT {key} DER raw/repaired={arms['raw']['score']['der']:.6f}/"
                 f"{arms['repaired']['score']['der']:.6f} IDs={arms['raw']['ids']}/"
                 f"{arms['repaired']['ids']} Lex={arms['raw']['lex_ids_2s']}/"
                 f"{arms['repaired']['lex_ids_2s']} false={len(arms['raw']['false_merge_groups'])}/"
                 f"{len(arms['repaired']['false_merge_groups'])} "
                 f"new_spend=${sum(row['cost_usd'] for row in calls.values()):.6f}")
    print("WROTE", CHUNKS, "configs", len(results), "calls", len(calls),
          "new_spend", sum(row["cost_usd"] for row in calls.values()))


def main() -> None:
    rows = []
    grouped = defaultdict(list)
    for path in sorted(gc.CACHE_DIR.rglob("*.json")):
        raw = json.loads(path.read_text())
        if raw.get("model") != "gemini-3.5-transcribe" or "audio_seconds" not in raw:
            continue
        result = gc._parse(raw, cached=True)
        seconds = float(raw["audio_seconds"])
        finding = anomalies(result.words)
        row = {"cache_file": str(path.relative_to(gc.CACHE_DIR)), "audio_s": seconds,
               "bucket": bucket(seconds), "words": len(result.words),
               "timing_anomalies": result.timing_anomalies,
               "backward_count": len(finding["backward"]),
               "duration_gt5_count": len(finding["duration_gt5"]),
               "isolated_start_count": len(finding["isolated_start"]),
               "short_excursion_count": len(finding["short_excursion"]),
               "examples": {k: v[:3] for k, v in finding.items()}}
        rows.append(row)
        grouped[row["bucket"]].append(row)
    summary = []
    for key in [bucket(upper) for upper in BOUNDS] + [">2586"]:
        rr = grouped[key]
        summary.append({"bucket": key, "calls": len(rr), "words": sum(x["words"] for x in rr),
                        "backward_calls": sum(x["backward_count"] > 0 for x in rr),
                        "backward_words": sum(x["backward_count"] for x in rr),
                        "duration_gt5_calls": sum(x["duration_gt5_count"] > 0 for x in rr),
                        "duration_gt5_words": sum(x["duration_gt5_count"] for x in rr),
                        "isolated_start_calls": sum(x["isolated_start_count"] > 0 for x in rr),
                        "isolated_start_words": sum(x["isolated_start_count"] for x in rr),
                        "short_excursion_calls": sum(x["short_excursion_count"] > 0 for x in rr),
                        "clamped_calls": sum(x["timing_anomalies"]["clamped"] > 0 for x in rr),
                        "clamped_words": sum(x["timing_anomalies"]["clamped"] for x in rr),
                        "dropped_calls": sum(x["timing_anomalies"]["dropped"] > 0 for x in rr),
                        "dropped_words": sum(x["timing_anomalies"]["dropped"] for x in rr)})
    OUT.write_text(json.dumps({"definitions": {"backward_s": .5, "duration_outlier_s": 5,
                                              "isolated_start_s": 5, "excursion_max_words": 10},
                               "summary": summary, "calls": rows}, indent=2) + "\n")
    print("INVENTORY", len(rows), "cached calls", sum(x["words"] for x in rows), "parsed words")
    for row in summary:
        print("BUCKET", row)
    print("WROTE", OUT)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "quality":
        quality()
    elif len(sys.argv) > 1 and sys.argv[1] == "chunks":
        chunks()
    elif len(sys.argv) > 1 and sys.argv[1] == "repair_inventory":
        repair_inventory()
    else:
        main()
