"""R5-F1 T3/T4 ($0 replay): multi-minute streams through the production publication path (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/stream.py

One lane's recorded instant-word (W3) events and the recorded batch words of the same audio are
published through `GeminiLiveRuntime.publish_update`: a rolling commit per window tick (the product's
ownership rule `old < word end <= frontier`, rows by `speaker_turns(ordered_segments())`), released
`LAG` s after the tick, and one preview per W3 event built the way `GeminiHybridEngine._on_live_text`
and `LaneGeminiEngine._preview_rows` build it (finals + interim past the frontier, clipped to it, a
later overlapping row replacing an earlier one). The bookkeeping copy is checked against the real
engine's captured trim inputs on a recorded cell first. Streams:
- zh-long: 188 s synthetic Mandarin, W3 + one 30 s window per 15 s tick (record_zh.py), 12 frontiers
- e1-en:   302 s English (P52 recorded W3 + 30 s windows every 10 s), 30 frontiers
- cell:    rp-short-aec40 system lane (validation of the bookkeeping copy)
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import score  # noqa: E402
import trim as arms  # noqa: E402
from trim import runtime  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import ordered_segments, speaker_turns  # noqa: E402
from moss_transcribe_diarize.app.live_service_runtime import (  # noqa: E402
    LiveServiceBounds, LiveServiceConfigHashes, LiveServiceDescriptor)
from moss_transcribe_diarize.app.live_session import AudioFrame  # noqa: E402

S, FRAME, LAG = 16000, 8000, 3.5
EVID = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence"
EV = EVID / "P72/f1"
D = EVID / "P72/mic-speaker-echo"
G = runtime.GeminiSegment


def descriptor(seconds: int):
    return LiveServiceDescriptor(
        source_revision="proto", provider_name="gemini", provider_revision="r5f1",
        provider_manifest_hash=hashlib.sha256(b"gemini").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(endpoint_config={}, identity_config={}, decoder_config={}),
        bounds=LiveServiceBounds(max_frame_samples=S, max_queue_depth=4, max_retained_samples=2 * S,
                                 max_identity_speakers=8, max_events=64, max_tape_bytes=(seconds + 5) * 2 * S),
        frame_samples=FRAME)


def commits_from_windows(windows: list[dict], lane: str) -> list[tuple[int, int, tuple]]:
    """(old, frontier, rows) per window: the product's ownership rule and row builder."""
    out, old, ids = [], 0, {}
    for window in sorted(windows, key=lambda w: w["end_s"]):
        frontier = round(window["end_s"] * S)
        rows = speaker_turns(ordered_segments(
            tuple(G(start, max(end, start + 1), text, ids.setdefault(speaker, f"speaker-{len(ids) + 1:04d}"), lane)
                  for text, speaker, start, end in window["words"] if old < end <= frontier),
            start_sample=old, end_sample=frontier, preserve_order=True))
        out.append((old, frontier, tuple(rows)))
        old = frontier
    return out


def replay(events: list, commits: list, total: int, arm, lane: str = "system", lag: float = LAG) -> tuple[list, list]:
    """Returns (trim calls with inputs, snapshots after every 0.5 s frame)."""
    calls: list = []
    position = frontier_now = 0

    def trim(segments, committed):
        kept = arm(segments, committed)
        calls.append({"at": position, "frontier": frontier_now,
                      "segments": [[r.start_sample, r.end_sample, r.text, r.source_lane] for r in segments],
                      "committed": [[r.start_sample, r.end_sample, r.text, r.source_lane] for r in committed],
                      "kept": [[r.start_sample, r.end_sample, r.text, r.source_lane] for r in kept]})
        return kept

    runtime._trim_committed_preview = trim
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rt = runtime.GeminiLiveRuntime(descriptor=descriptor(total // S + 1), tape_storage_root=tmp,
                                           engine_factory=lambda _id, publish, _usage: runtime.ScriptedGeminiEngine(
                                               publish, batches=(), terminal=()))
            rt.create(session_id="one")
            events = sorted(events, key=lambda e: e[2])
            pending = list(commits)
            committed, finals, interim, at, snaps = 0, [], None, 0, []
            for sequence, start in enumerate(range(0, total - FRAME + 1, FRAME)):
                rt.accept_frame("one", AudioFrame(sequence=sequence, pcm=b"\0" * 2 * FRAME, sample_count=FRAME))
                position = accepted = start + FRAME
                while pending and accepted >= pending[0][1] + round(lag * S):
                    old, frontier, rows = pending.pop(0)
                    rt.publish_update("one", runtime.GeminiBase(frontier, ()))
                    rt.publish_update("one", runtime.GeminiRolling(old, frontier, rows, revision_lanes=(lane,)))
                    committed = frontier_now = frontier
                    finals = [w for w in finals if w[2] > committed]
                while at < len(events) and events[at][2] <= accepted:
                    text, begin, end, final = events[at]
                    at += 1
                    if not text.strip() or end <= committed:      # GeminiHybridEngine._on_live_text
                        continue
                    row = (text.strip(), begin, end)
                    if final:
                        finals.append(row)
                        interim = None
                    else:
                        interim = row
                    finals = [w for w in finals if w[2] > committed]
                    fast = finals + ([interim] if interim else [])
                    through = min(accepted, max(committed, end))
                    if through <= committed:
                        continue
                    preview = ordered_segments(tuple(G(b, max(e, b + 1), t, source_lane=lane) for t, b, e in fast
                                                     if e > committed), start_sample=committed, end_sample=through)
                    shown: list = []                               # LaneGeminiEngine._preview_rows, one lane
                    for seg in preview:
                        if seg.end_sample <= committed or seg.start_sample >= through:
                            continue
                        current = G(max(seg.start_sample, committed), min(seg.end_sample, through), seg.text, None, lane)
                        shown = [prior for prior in shown if prior.end_sample <= current.start_sample
                                 or prior.start_sample >= current.end_sample]
                        shown.append(current)
                    rt.publish_update("one", runtime.GeminiPreview(through, tuple(sorted(shown, key=lambda r: r.start_sample))))
                session = rt.snapshot("one").to_dict()["session"]
                snaps.append({"e": accepted / S, "note": None, "status": session["status"],
                              "committed": session["committed_samples"],
                              "effective": session["effective_transcript"], "provisional": session["provisional"]})
    finally:
        runtime._trim_committed_preview = arms.BASE
    return calls, snaps


def load_zh():
    events = json.loads((EV / "provider-responses/zh-long-w3.json").read_text())["system"]
    windows = json.loads((EV / "runs/zh-long-windows.json").read_text())
    seconds = json.loads((EV / "fixtures/zh-long.json").read_text())["seconds"]
    return events, commits_from_windows(windows, "system"), int(seconds * S)


def load_e1():
    data = json.loads((EVID / "P52/robust-live-e1_system-en-US.json").read_text())
    events = [[u["text"], round(u["audio_start_s"] * S), round(u["audio_end_s"] * S), u["kind"] == "input_transcription"]
              for u in data["updates_full"]]
    windows = []
    for path in sorted((EVID / "P52").glob("lane-batch-system-*.json")):
        w = json.loads(path.read_text())
        windows.append({"end_s": w["end_s"], "words": [[x["text"], x.get("speaker", "s"), round(x["start"] * S),
                                                        round(x["end"] * S)] for x in w["words"]]})
    return events, commits_from_windows(windows, "system"), int(data["audio_s"] * S)


def load_cell(cell: str = "rp-short-aec40"):
    """The recorded cell's system lane: W3 events as recorded, commits as the engine published them."""
    # the lane engine opens the W3 socket at the first voiced frame (after the 3 s digital-silent lead-in)
    # and re-bases its positions by that origin (gemini_lane_engine.py:497-520)
    origin = 3 * S
    events = [[text, start + origin, end + origin, final] for text, start, end, final in
              json.loads((D / f"provider-responses/{cell}-w3.json").read_text())["system"]]
    snaps = [json.loads(line) for line in (EV / f"runs/{cell}-base-lag3.5/snapshots.jsonl").read_text().splitlines()]
    commits, old = [], 0
    for snap in snaps:
        if snap["status"] == "active" and snap["committed"] > old:
            rows = tuple(G(r["start_sample"], r["end_sample"], r["text"], r["canonical_speaker"], "system")
                         for r in snap["effective"] if r["source_lane"] == "system" and r["end_sample"] > old)
            commits.append((old, snap["committed"], rows))
            old = snap["committed"]
    return events, commits, snaps[-1]["accepted"]


def validate_copy() -> dict:
    """The bookkeeping copy against the real engine: the system-lane rows handed to the trim, in order."""
    events, commits, total = load_cell()
    calls, _ = replay(events, commits, total, arms.BASE)
    mine = []
    for call in calls:
        rows = tuple(r[2] for r in call["segments"] if r[3] == "system")
        if rows and (not mine or mine[-1] != rows):
            mine.append(rows)
    engine = []
    for line in (EV / "runs/rp-short-aec40-base-lag3.5/trim.jsonl").read_text().splitlines():
        rows = tuple(r[2] for r in json.loads(line)["segments"] if r[3] == "system")
        if rows and (not engine or engine[-1] != rows):
            engine.append(rows)
    same = sum(1 for row in mine if row in set(engine))
    return {"engine_distinct_system_inputs": len(engine), "copy_distinct_system_inputs": len(mine),
            "copy_inputs_also_in_engine": same, "engine_inputs_also_in_copy": sum(1 for row in engine if row in set(mine)),
            "identical_sequence": mine == engine}


def final_rows(commits) -> list[list]:
    return [[r.start_sample, r.end_sample, r.text, r.source_lane] for _, _, rows in commits for r in rows]


def by_frontier(calls, kept_of, commits) -> list[dict]:
    """Per commit interval (the accumulation check): what a publication shows that is already solid.

    block metric: units of the shown text in >= 5-unit runs found anywhere in the solid text (R5-D's metric;
    it also counts speech that genuinely repeats earlier words). truth: units of the first row that the
    later-committed text says were already solid when shown (`score.true_cut`)."""
    out = []
    final = final_rows(commits)
    edges = [0] + [frontier for _, frontier, _ in commits]
    variants = {frontier: sum(ch in arms.FOLD for row in rows for ch in row.text) for _, frontier, rows in commits}
    for index, low in enumerate(edges):
        rep, raw, left, n = 0, 0, 0, 0
        for call, kept in zip(calls, kept_of):
            if call["frontier"] != low:
                continue
            solid = score.units("".join(r[2] for r in call["committed"]))
            rep += score.repeated(score.units("".join(kept)), solid)
            first = score.units(call["segments"][0][2], fold=False)
            raw += len(score.units("".join(r[2] for r in call["segments"])))
            cut = len(first) - (len(score.units(kept[0], fold=False)) if kept and call["segments"][0][2].endswith(kept[0]) else 0)
            truth = score.true_cut(first, score.later_solid(final, "system", low), solid[-len(first) - 40:])
            left += max(0, truth - cut) if truth is not None else 0
            n += 1
        if n:
            out.append({"frontiers_passed": index, "publications": n, "mean_preview_units": round(raw / n, 1),
                        "mean_repeated_units_shown": round(rep / n, 2), "mean_solid_units_left_in_first_row": round(left / n, 2),
                        "traditional_characters_in_newest_window": variants.get(low, 0)})
    return out


def main():
    names = ["base", "A", "B", "C", "D-min3", "D-min4", "D-min6", "D-min7", "D-min8", "D-min9", "D-min10",
             "D-scaled", "D-tight", "D-share50", "D-share70", "D-share80", "A+fold"]
    report: dict = {"validation": validate_copy()}
    print("== bookkeeping copy vs the real engine (rp-short-aec40, system lane):", json.dumps(report["validation"]))
    for label, loader in (("zh-long", load_zh), ("e1-en", load_e1)):
        if label == "zh-long" and not (EV / "runs/zh-long-windows.json").is_file():
            print("zh-long: not recorded yet (record_zh.py)")
            continue
        events, commits, total = loader()
        base_calls, base_snaps = replay(events, commits, total, arms.BASE)
        a_calls, a_snaps = replay(events, commits, total, arms.ARMS["A"])
        c_calls, c_snaps = replay(events, commits, total, arms.ARMS["C"])
        for other in (a_calls, c_calls):
            assert [(c["segments"], c["committed"]) for c in base_calls] == [(c["segments"], c["committed"]) for c in other]
        off = score.offline(base_calls, names, final_rows(commits), time_reps=4)
        kept = {name: [[r.text for r in arms.ARMS[name](tuple(score.seg(s) for s in c["segments"]),
                                                       tuple(score.eff(s) for s in c["committed"]))] for c in base_calls]
                for name in ("base", "A", "C", "A+fold")}
        assert kept["A"] == [[r[2] for r in c["kept"]] for c in a_calls]
        assert kept["C"] == [[r[2] for r in c["kept"]] for c in c_calls]
        report[label] = {
            "seconds": total / S, "w3_events": len(events), "w3_finals": sum(1 for e in events if e[3]),
            "longest_w3_turn_s": round(max((e[2] - e[1]) for e in events) / S, 1),
            "frontiers": len(commits), "publications": len(base_calls),
            "snapshots": {"base": score.snapshot_score(base_snaps, prefix=0)["system"],
                          "A": score.snapshot_score(a_snaps, prefix=0)["system"],
                          "C": score.snapshot_score(c_snaps, prefix=0)["system"]},
            "offline": off, "by_frontier": {name: by_frontier(base_calls, kept[name], commits) for name in kept}}
        r = report[label]
        print(f"\n== {label}: {r['seconds']:.0f} s, {r['w3_events']} W3 events ({r['w3_finals']} finals, longest turn "
              f"{r['longest_w3_turn_s']} s), {r['frontiers']} frontiers, {r['publications']} preview publications")
        for name in ("base", "A", "C"):
            s = r["snapshots"][name]
            print(f"snapshots {name:5}: repeated unit-polls {s['repeated_unit_polls']:6} seconds>=10 repeated {s['seconds_ge10_repeated']:6} "
                  f"worst {s['worst_repeated']:4} grey unit-polls {s['grey_unit_polls']:6} fresh {s['fresh_unit_polls']:6}")
        keys = ["removed_unit_polls", "repeated_unit_polls", "truth_rows", "unverifiable_rows", "fresh_shown_units",
                "over_trim_units", "over_trim_rows", "under_trim_units", "under_trim_rows_ge5", "reshown_units", "reshow_events",
                "later_rows", "later_removed_restating_kept_rows", "later_removed_other", "later_shown_restating_kept_rows",
                "noncjk_rows", "noncjk_rows_differ_from_base", "noncjk_calls", "noncjk_calls_differ_from_base", "calls_differ_from_base", "us_mean", "us_p99", "us_max"]
        print("arm | " + " | ".join(keys))
        for name in names:
            print(f"{name:10} | " + " | ".join(str(off[name].get(k, 0)) for k in keys))
        report[label]["margins_A"] = score.margins(base_calls)
        print("margins of arm A's accepted cuts:", json.dumps(report[label]["margins_A"]))
        for name in ("base", "A", "C", "A+fold"):
            print(f"-- {name}: by frontiers passed -> block-metric repeated units / solid units left in the first row "
                  f"(traditional characters in the newest window): "
                  + " ".join(f"{b['frontiers_passed']}:{b['mean_repeated_units_shown']}/{b['mean_solid_units_left_in_first_row']}"
                             f"({b['traditional_characters_in_newest_window']})" for b in r["by_frontier"][name]))
        for name in ("base", "A", "C", "D-min9", "A+fold"):
            for kind in ("over_trims", "under_trims", "reshows"):
                seen, shown = set(), 0
                for item in off[name][kind]:
                    key = json.dumps({k: v for k, v in item.items() if k not in ("call", "at_s")}, ensure_ascii=False)
                    if key not in seen and shown < 14:
                        seen.add(key)
                        shown += 1
                        print(f"   {name} {kind}: {json.dumps(item, ensure_ascii=False)}")
        (EV / f"runs/{label}-trim-base.jsonl").write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in base_calls))
        (EV / f"runs/{label}-snapshots-base.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in base_snaps))
        (EV / f"runs/{label}-snapshots-A.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in a_snaps))
        (EV / f"runs/{label}-snapshots-C.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in c_snaps))
    (EV / "stream.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
