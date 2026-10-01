"""R5-F1 scoring helpers ($0, throwaway): snapshot metrics (R5-D's definitions) and offline arm scoring
on captured trim inputs. Imported by cells.py / stream.py; no command of its own.
"""
from __future__ import annotations

import difflib
import statistics
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import trim as arms  # noqa: E402
from trim import runtime  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units  # noqa: E402
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment  # noqa: E402

S = 16000
# For the METRIC only (R5-D's e2e_analyze.py method): the provider answers in simplified or traditional Han at
# random, and that variance must not be counted as new or lost speech. Arms never see this fold, except the
# prototype arm "A+fold", which uses the same table on purpose.
FOLD = arms.FOLD


def units(text: str, fold: bool = True) -> list[str]:
    if fold:
        text = "".join(FOLD.get(ch, ch) for ch in text)
    return [unit for unit, _, _ in _preview_units(text)]


def has_cjk(text: str) -> bool:
    return any(unicodedata.name(ch, "").startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL")) for ch in text)


def repeated(shown: list[str], reference: list[str], run: int = 5) -> int:
    """Units of `shown` inside in-order runs of >= `run` units that `reference` also holds (R5-D)."""
    return sum(block.size for block in difflib.SequenceMatcher(None, reference, shown, autojunk=False)
               .get_matching_blocks() if block.size >= run)


def snapshot_score(snaps: list[dict], prefix: float = 3.0) -> dict:
    """Per lane: repeated / fresh unit-polls of the grey text against the lane's solid text, seconds with
    >= 10 repeated units, worst poll (R5-D's e2e_analyze definitions)."""
    out = {}
    polls = [s for s in snaps if s["status"] == "active" and s["provisional"]]
    for lane in ("system", "microphone"):
        rows = []
        for snap in polls:
            solid = units("".join(r["text"] for r in snap["effective"] if r.get("source_lane") == lane))
            grey = units("".join(r["text"] for r in snap["provisional"]["segments"] if r["source_lane"] == lane))
            rows.append((snap["e"], len(grey), repeated(grey, solid)))
        out[lane] = {
            "polls": len(rows), "grey_unit_polls": sum(r[1] for r in rows),
            "repeated_unit_polls": sum(r[2] for r in rows), "fresh_unit_polls": sum(r[1] - r[2] for r in rows),
            "polls_ge10_repeated": sum(r[2] >= 10 for r in rows), "worst_repeated": max((r[2] for r in rows), default=0),
            "seconds_ge10_repeated": round(sum(b[0] - a[0] for a, b in zip(rows, rows[1:]) if a[2] >= 10), 1)}
    frontiers, last = [], None
    for snap in snaps:
        if snap["committed"] != last:
            frontiers.append((snap["e"], snap["committed"] / S - prefix))
            last = snap["committed"]
    out["frontier_published_at_e"] = frontiers
    return out


def seg(row):
    return runtime.GeminiSegment(row[0], row[1], row[2], None, row[3])


def eff(row):
    return EffectiveTranscriptSegment(row[0], row[1], row[2], None, "rolling", row[3])


def cuts(segments, kept) -> list[tuple]:
    """(lane, raw units, units removed from the head) per input row; a dropped row has cut == its units."""
    out, at = [], 0
    for row in segments:
        raw = units(row.text, fold=False)
        if at < len(kept) and (kept[at].start_sample, kept[at].end_sample, kept[at].source_lane) == (
                row.start_sample, row.end_sample, row.source_lane) and row.text.endswith(kept[at].text):
            out.append((row.source_lane, raw, len(raw) - len(units(kept[at].text, fold=False))))
            at += 1
        else:
            out.append((row.source_lane, raw, len(raw)))
    assert at == len(kept), "kept rows are not a head-trimmed subsequence of the input rows"
    return out


def later_solid(final_rows, lane, frontier):
    """Units of the lane's live transcript for audio at or after `frontier` (what was still fresh then)."""
    return units("".join(r[2] for r in final_rows if r[3] == lane and r[0] >= frontier))


def true_cut(raw: list[str], later: list[str], solid_tail: list[str]) -> int | None:
    """Where the not-yet-solid speech begins in a preview row, from the text committed LATER.

    The first in-order block of >= 4 units between the row and the first units of the later-committed
    text gives the row index where fresh speech starts. A row with no such block is all repeat if it
    aligns with the solid tail (>= 5 in order), else unverifiable (None): W3 text that was never
    committed, e.g. echo residue on the microphone lane.
    """
    folded = [FOLD.get(u, u) for u in raw]
    for block in difflib.SequenceMatcher(None, later[:len(raw) + 30], folded, autojunk=False).get_matching_blocks():
        if block.size >= 4 and block.a <= 12:
            return max(0, block.b - block.a)
    if repeated(folded, solid_tail) >= max(5, len(raw) // 2):
        return len(raw)
    return None


def offline(calls: list[dict], names: list[str], final_rows=None, time_reps: int = 0) -> dict:
    """Run every arm on the captured inputs. Per arm: unit-poll sums, truth-based over/under-trim,
    re-shown units, G2 identity against base on rows without CJK, per-call time."""
    result = {}
    base_out = []
    for call in calls:
        segments = tuple(seg(r) for r in call["segments"])
        committed = tuple(eff(r) for r in call["committed"])
        base_out.append([r.text for r in arms.BASE(segments, committed)])
    for name in names:
        arm = arms.ARMS[name]
        stat = {"calls": len(calls), "rows": 0, "raw_unit_polls": 0, "removed_unit_polls": 0, "shown_unit_polls": 0,
                "repeated_unit_polls": 0, "over_trim_units": 0, "over_trim_rows": 0, "under_trim_units": 0,
                "under_trim_rows_ge5": 0, "fresh_shown_units": 0, "truth_rows": 0, "unverifiable_rows": 0,
                "reshown_units": 0, "reshow_events": 0, "noncjk_calls": 0, "noncjk_calls_differ_from_base": 0,
                "calls_differ_from_base": 0, "differences": [], "over_trims": [], "under_trims": [], "reshows": []}
        previous: dict = {}
        times = []
        for index, call in enumerate(calls):
            segments = tuple(seg(r) for r in call["segments"])
            committed = tuple(eff(r) for r in call["committed"])
            started = time.perf_counter()
            kept = arm(segments, committed)
            elapsed = time.perf_counter() - started
            for _ in range(time_reps):
                started = time.perf_counter()
                arm(segments, committed)
                elapsed = min(elapsed, time.perf_counter() - started)
            times.append(elapsed * 1e6)
            texts = [r.text for r in kept]
            plain = not any(has_cjk(r[2]) for r in call["segments"])
            stat["noncjk_calls"] += plain
            if texts != base_out[index]:
                stat["calls_differ_from_base"] += 1
                if plain:
                    stat["noncjk_calls_differ_from_base"] += 1
            # row level: an input row without CJK must come out exactly as today, whatever else the call holds
            base_rows = {(r.start_sample, r.end_sample, r.source_lane): r.text
                         for r in arms.BASE(segments, committed)}
            arm_rows = {(r.start_sample, r.end_sample, r.source_lane): r.text for r in kept}
            for row in segments:
                if has_cjk(row.text):
                    continue
                key = (row.start_sample, row.end_sample, row.source_lane)
                stat["noncjk_rows"] = stat.get("noncjk_rows", 0) + 1
                if base_rows.get(key) != arm_rows.get(key):
                    stat["noncjk_rows_differ_from_base"] = stat.get("noncjk_rows_differ_from_base", 0) + 1
                    if len(stat["differences"]) < 40:
                        stat["differences"].append({"call": index, "row": row.text, "base": base_rows.get(key),
                                                    "arm": arm_rows.get(key)})
            frontier = max((r[1] for r in call["committed"]), default=0)
            solid = {lane: units("".join(r[2] for r in call["committed"] if r[3] == lane))
                     for lane in {r[3] for r in call["segments"]}}
            shown_by_lane: dict = {}
            for row in kept:
                shown_by_lane.setdefault(row.source_lane, []).extend(units(row.text))
            for lane, shown in shown_by_lane.items():
                stat["repeated_unit_polls"] += repeated(shown, solid[lane])
            now: dict = {}
            for lane, raw, cut in cuts(segments, kept):
                stat["rows"] += 1
                stat["raw_unit_polls"] += len(raw)
                stat["removed_unit_polls"] += cut
                stat["shown_unit_polls"] += len(raw) - cut
                first = lane not in now
                if final_rows is not None and first:
                    lane_frontier = max((r[1] for r in call["committed"] if r[3] == lane), default=0)
                    truth = true_cut(raw, later_solid(final_rows, lane, lane_frontier), solid[lane][-len(raw) - 40:])
                    if truth is None:
                        stat["unverifiable_rows"] += 1
                    else:
                        stat["truth_rows"] += 1
                        stat["fresh_shown_units"] += len(raw) - max(cut, truth)
                        if cut > truth:
                            stat["over_trim_units"] += cut - truth
                            stat["over_trim_rows"] += 1
                            if len(stat["over_trims"]) < 40:
                                stat["over_trims"].append({"call": index, "at_s": call["at"] / S, "lane": lane, "cut": cut,
                                                           "true_cut": truth, "removed_fresh": "".join(raw[truth:cut])})
                        elif cut < truth:
                            stat["under_trim_units"] += truth - cut
                            stat["under_trim_rows_ge5"] += truth - cut >= 5
                            if truth - cut >= 5 and len(stat["under_trims"]) < 40:
                                stat["under_trims"].append({"call": index, "at_s": call["at"] / S, "lane": lane, "cut": cut,
                                                            "true_cut": truth, "repeat_left": "".join(raw[cut:truth])})
                elif not first:
                    # a later row of the lane (an interim after finals): its head may restate the rows kept above it
                    above = [FOLD.get(u, u) for row_raw, row_cut, _ in now[lane] for u in row_raw[row_cut:]]
                    folded = [FOLD.get(u, u) for u in raw]
                    # what the reader already sees in the lane: the solid tail, then the rows kept above
                    restated = repeated(folded[:cut], solid[lane][-len(raw) - 60:] + above)
                    stat["later_rows"] = stat.get("later_rows", 0) + 1
                    stat["later_removed_restating_kept_rows"] = stat.get("later_removed_restating_kept_rows", 0) + restated
                    stat["later_removed_other"] = stat.get("later_removed_other", 0) + cut - restated
                    stat["later_shown_restating_kept_rows"] = (stat.get("later_shown_restating_kept_rows", 0)
                                                               + repeated(folded[cut:], solid[lane][-len(raw) - 60:] + above))
                # re-shown: same turn (its head is unchanged), frontier not moved back, cut went down
                for was_raw, was_cut, was_frontier in previous.get(lane, ()):
                    if was_cut and frontier >= was_frontier and raw[:was_cut] == was_raw[:was_cut] and cut < was_cut:
                        stat["reshown_units"] += was_cut - cut
                        stat["reshow_events"] += 1
                        if len(stat["reshows"]) < 40:
                            stat["reshows"].append({"call": index, "at_s": call["at"] / S, "lane": lane, "was_cut": was_cut,
                                                    "cut": cut, "reshown": "".join(raw[cut:was_cut])})
                        break
                now.setdefault(lane, []).append((raw, cut, frontier))
            for lane in now:
                previous[lane] = now[lane]
        stat["us_mean"] = round(statistics.fmean(times), 1) if times else 0
        stat["us_p99"] = round(sorted(times)[int(len(times) * 0.99) - 1], 1) if times else 0
        stat["us_max"] = round(max(times), 1) if times else 0
        result[name] = stat
    return result


def margins(calls: list[dict], units=None) -> dict:
    """How far each accepted cut sat from every threshold of the run rule (arm A on the captured inputs)."""
    probe: list = []
    arm = arms.make_trim(head=arms.head_rule(probe=probe), **({"units": units} if units else {}))
    for call in calls:
        arm(tuple(seg(r) for r in call["segments"]), tuple(eff(r) for r in call["committed"]))
    out = {}
    for label, rows in (("cjk", [r for r in probe if r["cjk"]]), ("other", [r for r in probe if not r["cjk"]])):
        if not rows:
            out[label] = {"cuts": 0}
            continue
        shares = sorted(r["share"] for r in rows)
        out[label] = {
            "cuts": len(rows), "matched_min": min(r["matched"] for r in rows),
            "share_min": round(shares[0], 3), "share_p05": round(shares[int(len(shares) * .05)], 3),
            "share_p50": round(shares[len(shares) // 2], 3),
            "start_max": max(r["start"] for r in rows),
            "reach_max_when_not_covering_chunk": max((r["reach"] for r in rows if not r["covers_chunk"]), default=0),
            "gap_both_sides_max": max(r["max_gap_both"] for r in rows),
            "skip_shown_side_max": max(r["max_skip_shown"] for r in rows),
            "cuts_of_5_to_8_units": sum(5 <= r["end"] <= 8 for r in rows)}
    return out
