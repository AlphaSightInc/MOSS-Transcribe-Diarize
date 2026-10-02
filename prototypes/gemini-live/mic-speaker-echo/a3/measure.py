"""Absorbed $0 T4 falsification bench; recorded public text only, no provider client."""
from __future__ import annotations

import difflib
import json
import statistics
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE.parent / "f1")]
import score
import stream
from moss_transcribe_diarize.app import gemini_live_runtime as rt
from moss_transcribe_diarize.app.live_session import AudioFrame

S = 16000
EV = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P73/a3"
F1 = EV.parents[1] / "P72/f1/runs"
PRODUCT = rt._trim_committed_preview


def common_prefix(a, b):
    return next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), min(len(a), len(b)))


def mismatch(raw, solid):
    """Lexical audit only; substitutions cannot by themselves prove semantic loss."""
    a, b = score.units(solid), score.units(raw)
    blocks = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return [dict(kind=tag, solid=a[i:j], preview=b[k:l], preview_from=k,
                 context=b[max(0, k - 6):min(len(b), l + 6)])
            for tag, i, j, k, l in blocks.get_opcodes() if tag in ("replace", "insert")]


class Snapshot:
    """Throwaway T4 reducer with ORIGINAL turn identity; no guessed/clipped key."""
    def __init__(self):
        self.pending = {}
        self.snapshots = {}
        self.frontiers = {}

    def publication(self, lane, start, end, text):
        key = (lane, start)
        self.pending.setdefault(key, []).append((end, score.units(text, fold=False)))

    def frontier(self, lane, through):
        self.frontiers[lane] = through
        for key, publications in self.pending.items():
            if key[0] != lane:
                continue
            eligible = [p for p in publications if p[0] <= through]
            if eligible:
                self.snapshots[key] = max(eligible, key=lambda p: p[0])
            self.pending[key] = [p for p in publications if p[0] > through]

    def cut(self, lane, start, text):
        snapshot = self.snapshots.get((lane, start))
        return common_prefix(snapshot[1], score.units(text, fold=False)) if snapshot else 0

    def clear(self, lane):
        self.pending = {k: v for k, v in self.pending.items() if k[0] != lane}
        self.snapshots = {k: v for k, v in self.snapshots.items() if k[0] != lane}

    def state(self):
        return dict(frontiers=self.frontiers,
                    pending=[dict(lane=k[0], start=k[1], publications=v) for k, v in self.pending.items()],
                    snapshots=[dict(lane=k[0], start=k[1], end=v[0], units=v[1])
                               for k, v in self.snapshots.items()])


def audit_stream(name, loader):
    events, commits, total = loader()
    audits, rewrites = [], []
    previous = {}
    for index, (text, start, end, final) in enumerate(events):
        words = score.units(text, fold=False)
        if start in previous:
            old = previous[start]
            same = common_prefix(old, words)
            if same < len(old):
                rewrites.append(dict(event=index, start_s=start / S, end_s=end / S,
                                     old_units=len(old), new_units=len(words), common_prefix=same,
                                     back_from_old_end=len(old) - same, before=old, after=words))
        previous[start] = words
        ownership = next((i for i, (_, frontier, _) in enumerate(commits) if frontier >= end), None)
        if ownership is None:
            continue
        solid = " ".join(row.text for _, _, rows in commits[:ownership + 1] for row in rows)
        absent = mismatch(text, solid)
        # Full evidence per eligible publication; only print compact counts to the terminal.
        audits.append(dict(event=index, turn_start_s=start / S, publication_end_s=end / S,
                           frontier_s=commits[ownership][1] / S, final=final, raw_text=text,
                           solid_text=solid, lexical_uncovered_units=sum(len(x["preview"]) for x in absent),
                           lexical_gaps=absent))
    result = dict(seconds=total / S, events=len(events), frontiers=len(commits),
                  eligible_publications=len(audits),
                  publications_with_lexical_gaps=sum(bool(a["lexical_gaps"]) for a in audits),
                  lexical_uncovered_unit_publications=sum(a["lexical_uncovered_units"] for a in audits),
                  rewritten_publications=len(rewrites),
                  max_rewrite_back_units=max((r["back_from_old_end"] for r in rewrites), default=0),
                  audits=audits, rewrites=rewrites)
    (EV / f"{name}-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return {k: v for k, v in result.items() if k not in ("audits", "rewrites")}


def recorded_snapshot(name, loader, path):
    """Best-case T4 with oracle original starts; fails even before identity plumbing."""
    events, commits, total = loader()
    by_text_end = {(text.strip(), end): (text, start, end, final) for text, start, end, final in events}
    calls = [json.loads(line) for line in path.read_text().splitlines()]
    cuts, trace, times = [], [], []
    changed = extra = extra_lexical = fresh_proxy = unmapped = no_snapshot = 0
    refinement_beyond_snapshot = max_latency_residue = 0
    for index, call in enumerate(calls):
        segments = tuple(score.seg(row) for row in call["segments"])
        committed = tuple(score.eff(row) for row in call["committed"])
        started = time.perf_counter()
        baseline = PRODUCT(segments, committed, cuts)
        base_cuts = score.cuts(segments, baseline)
        output = []
        rows_trace = []
        frontier = call.get("frontier", max((r.end_sample for r in committed), default=0))
        for row, (_, raw, base_cut) in zip(segments, base_cuts):
            event = by_text_end.get((row.text, row.end_sample))
            snapshot = None
            if event is None:
                unmapped += 1
            else:
                eligible = [e for e in events if e[1] == event[1] and e[2] <= frontier]
                snapshot = max(eligible, key=lambda e: e[2]) if eligible else None
                no_snapshot += snapshot is None
            snapshot_cut = common_prefix(score.units(snapshot[0], fold=False), raw) if snapshot else 0
            refinement_beyond_snapshot += snapshot is not None and base_cut > snapshot_cut
            cut = max(base_cut, snapshot_cut)
            spans = rt._preview_units(row.text)
            text = row.text[spans[cut - 1][2]:].lstrip(" \t\r\n,.;:!?，。；：！？、") if cut else row.text
            if text:
                output.append(replace(row, text=text))
            extra += cut - base_cut
            solid = " ".join(r.text for r in committed if r.source_lane == row.source_lane)
            # Full lexical audit of additionally hidden units (not a semantic loss claim).
            absent = mismatch(" ".join(raw[base_cut:cut]), solid) if cut > base_cut else []
            extra_lexical += sum(len(g["preview"]) for g in absent)
            later = score.later_solid(stream.final_rows(commits), row.source_lane, frontier)
            truth = score.true_cut(raw, later, score.units(solid)[-len(raw) - 40:])
            if snapshot and truth is not None:
                max_latency_residue = max(max_latency_residue, truth - snapshot_cut)
            lost = max(0, cut - max(base_cut, truth)) if truth is not None else 0
            fresh_proxy += lost
            rows_trace.append(dict(lane=row.source_lane, raw=row.text, original_start=event[1] if event else None,
                                   snapshot=snapshot, baseline_cut=base_cut, snapshot_cut=snapshot_cut,
                                   chosen_cut=cut, additionally_hidden_lexical_gaps=absent,
                                   later_solid_boundary_proxy=truth, additional_fresh_proxy=lost, shown=text))
        times.append((time.perf_counter() - started) * 1000)
        changed += tuple(output) != baseline
        trace.append(dict(call=index, at=call["at"], frontier=frontier, rows=rows_trace))
    (EV / f"{name}-snapshot.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in trace))
    return dict(calls=len(calls), changed_calls=changed, additionally_hidden_unit_publications=extra,
                additionally_hidden_lexically_absent_unit_publications=extra_lexical,
                additional_fresh_later_solid_proxy=fresh_proxy, unmapped_rows=unmapped,
                rows_without_snapshot=no_snapshot,
                A2_refinement_beyond_snapshot_rows=refinement_beyond_snapshot,
                max_snapshot_only_latency_residue_later_solid_proxy=max_latency_residue,
                audit_including_scoring_mean_ms=statistics.fmean(times))


def captured_audit():
    """All frozen rows, both lanes; end <= later same-lane solid extent is conservative."""
    report, details = {}, []
    files = sorted(F1.glob("*-base*/trim.jsonl")) + sorted(F1.glob("*-trim-base.jsonl"))
    for path in files:
        calls = [json.loads(line) for line in path.read_text().splitlines()]
        label = path.parent.name if path.name == "trim.jsonl" else path.stem
        eligible = lexical_gap_rows = units_absent = raw_rows = 0
        lanes = {lane: dict(eligible=0, lexical_gap_rows=0) for lane in ("system", "microphone")}
        for index, call in enumerate(calls):
            for start, end, text, lane in call["segments"]:
                raw_rows += 1
                future = next((c for c in calls[index:] if max((r[1] for r in c["committed"] if r[3] == lane), default=0) >= end), None)
                if future is None:
                    continue
                eligible += 1
                lanes[lane]["eligible"] += 1
                solid = " ".join(r[2] for r in future["committed"] if r[3] == lane)
                gaps = mismatch(text, solid)
                lexical_gap_rows += bool(gaps)
                lanes[lane]["lexical_gap_rows"] += bool(gaps)
                units_absent += sum(len(g["preview"]) for g in gaps)
                details.append(dict(file=label, call=index, lane=lane, row_start=start, publication_row_end=end,
                                    later_call_at=future["at"], raw=text, solid=solid, lexical_gaps=gaps))
        report[label] = dict(calls=len(calls), raw_rows=raw_rows, eligible_rows=eligible,
                             rows_with_lexical_gaps=lexical_gap_rows, lexical_uncovered_unit_publications=units_absent, lanes=lanes)
    (EV / "captured-audit.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in details))
    (EV / "captured-summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return dict(files=len(files), calls=sum(r["calls"] for r in report.values()),
                raw_rows=sum(r["raw_rows"] for r in report.values()),
                eligible_rows=sum(r["eligible_rows"] for r in report.values()),
                rows_with_lexical_gaps=sum(r["rows_with_lexical_gaps"] for r in report.values()),
                lexical_uncovered_unit_publications=sum(r["lexical_uncovered_unit_publications"] for r in report.values()),
                limit="Clipped row starts are not original turn identity. Absence is lexical, not semantic proof.")


def boundary_controls():
    reducer = Snapshot()
    old = "one settled introduction about a previous meeting"
    grown = old + " fresh words now"
    reducer.publication("system", 0, 10, old)
    reducer.frontier("system", 15)
    result = []
    def save(name, actual, expected):
        result.append(dict(case=name, actual=actual, expected=expected, passes=actual == expected, state=reducer.state()))
    save("unchanged-prefix", reducer.cut("system", 0, grown), len(score.units(old)))
    save("other-lane-no-snapshot", reducer.cut("microphone", 0, grown), 0)
    save("new-turn-after-frontier-real-repeat", reducer.cut("system", 16, grown), 0)
    save("prefix-rewrite", reducer.cut("system", 0, "rewritten " + grown), 0)
    save("rewrite-after-unchanged-first-unit", reducer.cut("system", 0, "one changed " + grown), 1)
    save("split-turn-with-new-start", reducer.cut("system", 5, grown), 0)
    save("merged-turn-with-new-start", reducer.cut("system", -5, grown), 0)
    save("final-restated-by-next-interim-new-start", reducer.cut("system", 10, grown), 0)
    reducer.frontier("system", 30)
    save("frontier-with-no-publication-keeps-old-snapshot", reducer.cut("system", 0, grown), len(score.units(old)))
    reducer.clear("system")
    save("stop-or-lane-replacement-clears", reducer.cut("system", 0, grown), 0)
    save("cleared-pending-and-snapshot-state", len(reducer.pending) + len(reducer.snapshots), 0)
    assert all(r["passes"] for r in result)
    (EV / "boundary-controls.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return dict(passed=len(result), scope="Ideal original-key reducer only; no production lifecycle implementation after G3 failure.")


def injected_cases():
    """Known omissions/word timing; text from recordings, edits/timing explicitly injected."""
    english = max(stream.load_e1()[0], key=lambda e: len(score.units(e[0])))[0]
    zh = max(stream.load_zh()[0], key=lambda e: len(score.units(e[0])))[0]
    en_units = score.units(english, fold=False)
    zh_units = score.units(zh, fold=False)
    insertion = "these eleven injected unheard words belong exclusively to this omitted passage"
    assert len(score.units(insertion)) == 11
    han = "".join(u for u in zh_units if len(u) == 1)[:169]
    assert len(score.units(han)) == 169
    fresh_en = "Zebras gallop quietly while fresh speakers discuss entirely novel matters today"
    fresh_zh = "此刻新说的话必须继续完整显示出来"
    cases = [
        ("solid-22-word-omission", " ".join(en_units),
         " ".join(en_units[:40] + en_units[62:]), fresh_en, set(range(40, 62))),
        ("preview-11-word-insertion", " ".join(en_units[:40]) + " " + insertion + " " + " ".join(en_units[40:]),
         " ".join(en_units), fresh_en, set(range(40, 51))),
        ("preview-169-character-insertion", "".join(zh_units[:40]) + han + "".join(zh_units[40:]),
         "".join(zh_units), fresh_zh, set(range(40, 209))),
        ("word-straddles-frontier", " ".join(en_units) + " boundaryword",
         " ".join(en_units), fresh_en, {len(en_units)}),
    ]
    report = []
    for name, old, solid, fresh, omitted in cases:
        for lane in ("system", "microphone"):
            result = {}
            for mode in ("A2-product", "T4-prototype"):
                snapshot = Snapshot()
                history = []
                current_cut = 0
                # Oracle turn identity gives T4 its strongest possible interpretation.
                def trim(segments, committed, cuts=None, *, degraded=False):
                    nonlocal current_cut
                    baseline = PRODUCT(segments, committed, cuts, degraded=degraded)
                    shown = []
                    for row, (_, words, cut) in zip(segments, score.cuts(segments, baseline)):
                        if mode == "T4-prototype":
                            cut = max(cut, snapshot.cut(row.source_lane, 0, row.text))
                        current_cut = cut
                        spans = rt._preview_units(row.text)
                        text = row.text[spans[cut - 1][2]:].lstrip(" \t\r\n,.;:!?，。；：！？、") if cut else row.text
                        if text:
                            shown.append(replace(row, text=text))
                    history.append(dict(state=snapshot.state(), raw=[r.text for r in segments],
                                        baseline=[r.text for r in baseline], shown=[r.text for r in shown], cut=current_cut))
                    return tuple(shown)
                rt._trim_committed_preview = trim
                try:
                    with tempfile.TemporaryDirectory() as tmp:
                        runtime = rt.GeminiLiveRuntime(descriptor=stream.descriptor(25), tape_storage_root=tmp,
                            engine_factory=lambda _id, publish, _usage: rt.ScriptedGeminiEngine(publish, batches=(), terminal=()))
                        runtime.create(session_id="one")
                        for seq in range(40):
                            runtime.accept_frame("one", AudioFrame(seq, b"\0" * 16000, 8000))
                        snapshot.publication(lane, 0, 14 * S, old)
                        runtime.publish_update("one", rt.GeminiPreview(14 * S, (rt.GeminiSegment(0, 14 * S, old, source_lane=lane),)))
                        runtime.publish_update("one", rt.GeminiBase(15 * S, ()))
                        runtime.publish_update("one", rt.GeminiRolling(0, 15 * S,
                            (rt.GeminiSegment(0, 15 * S, solid, "speaker-0001", lane),), revision_lanes=(lane,)))
                        snapshot.frontier(lane, 15 * S)
                        snapshot.publication(lane, 0, 20 * S, old + " " + fresh)
                        runtime.publish_update("one", rt.GeminiPreview(20 * S,
                            (rt.GeminiSegment(15 * S, 20 * S, old + " " + fresh, source_lane=lane),)))
                        shown = " ".join(row["text"] for row in runtime.snapshot("one").session.provisional.segments)
                        old_units = len(score.units(old, fold=False))
                        result[mode] = dict(shown=shown, cut=current_cut, snapshot_units=old_units,
                            known_omitted_units_hidden=sum(i < current_cut for i in omitted),
                            known_fresh_suffix_units_hidden=max(0, current_cut - old_units),
                            repeated_old_units_left=max(0, old_units - current_cut - sum(i >= current_cut for i in omitted)),
                            latency_residue_units=0, state_history=history)
                finally:
                    rt._trim_committed_preview = PRODUCT
            report.append(dict(case=name, lane=lane, injection=True,
                               timing_stipulation=(dict(word_start_s=13.9, word_end_s=15.1,
                                                        preview_end_s=14, solid_frontier_s=15)
                                                   if name == "word-straddles-frontier" else None),
                               known_omitted_unit_count=len(omitted),
                               additional_lost_from_view=result["T4-prototype"]["known_omitted_units_hidden"] - result["A2-product"]["known_omitted_units_hidden"],
                               runs=result))
    (EV / "injections.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return [dict(case=r["case"], lane=r["lane"], additional_lost_from_view=r["additional_lost_from_view"],
                 A2_cut=r["runs"]["A2-product"]["cut"], T4_cut=r["runs"]["T4-prototype"]["cut"],
                 T4_repeated_residue=r["runs"]["T4-prototype"]["repeated_old_units_left"],
                 latency_residue_units=0) for r in report]


def main():
    EV.mkdir(parents=True, exist_ok=True)
    report = {name: audit_stream(name, loader) for name, loader in
              (("zh-188s", stream.load_zh), ("en-302s", stream.load_e1), ("r5d-cell", stream.load_cell))}
    report["snapshot_replay"] = {
        name: recorded_snapshot(name, loader, F1 / filename) for name, loader, filename in
        (("zh-188s", stream.load_zh, "zh-long-trim-base.jsonl"),
         ("en-302s", stream.load_e1, "e1-en-trim-base.jsonl"))}
    report["injections"] = injected_cases()
    report["captured_population"] = captured_audit()
    report["boundary_controls"] = boundary_controls()
    assert all(r["additional_lost_from_view"] == expected
               for r, expected in zip(report["injections"], (22, 22, 11, 11, 169, 169, 1, 1)))
    report["decision"] = "REJECT T4: premise/G3 fail; retain A2 product"
    (EV / "measurement.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
