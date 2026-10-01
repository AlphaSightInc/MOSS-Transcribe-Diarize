"""Condense one e2e_run.py recording into the facts each symptom needs (throwaway, $0).

    PYTHON prototypes/gemini-live/mic-speaker-echo/e2e_analyze.py <run> [--timeline]
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE)]
import ledger  # noqa: E402
from moss_transcribe_diarize.app.gemini_lane_engine import _preview_units  # noqa: E402

S = 16000
RUN = sys.argv[1]
OUT = ledger.EV / "runs" / RUN


def units(text: str) -> list[str]:
    return [unit for unit, _, _ in _preview_units(text)]


def repeated(shown: list[str], reference: list[str], run: int = 5) -> int:
    """Units of `shown` inside in-order runs of >= `run` units that `reference` also holds."""
    return sum(block.size for block in difflib.SequenceMatcher(None, reference, shown, autojunk=False)
               .get_matching_blocks() if block.size >= run)


def text_stats(text: str) -> dict:
    return {"units": len(units(text)), "latin_words": len(re.findall(r"[A-Za-z][A-Za-z']*", text)),
            "han": sum(1 for ch in text if "一" <= ch <= "鿿"),
            "punctuation": sum(1 for ch in text if unicodedata.category(ch).startswith("P"))}


def lane_text(rows, lane):
    return "".join(row["text"] for row in rows if row.get("source_lane") == lane)


def main():
    snaps = [json.loads(line) for line in (OUT / "snapshots.jsonl").read_text().splitlines()]
    rows_log = [json.loads(line) for line in (OUT / "rows.jsonl").read_text().splitlines()]
    receipt = json.loads((OUT / "receipt.json").read_text())
    prefix = receipt["prefix_s"]
    out: dict = {"run": RUN, "fixtures": [receipt["system_wav"], receipt["mic_wav"]]}

    # S1: the system lane's grey preview against the system lane's committed (solid) text, per server snapshot
    polls = []
    for snap in snaps:
        if snap["status"] != "active" or not snap["provisional"]:
            continue
        committed = {lane: units(lane_text(snap["effective"], lane)) for lane in ("system", "microphone")}
        row = {"e": snap["e"], "committed_s": snap["committed"] / S - prefix}
        for lane in ("system", "microphone"):
            shown = units("".join(seg["text"] for seg in snap["provisional"]["segments"] if seg["source_lane"] == lane))
            other = "microphone" if lane == "system" else "system"
            other_shown = units("".join(seg["text"] for seg in snap["provisional"]["segments"]
                                        if seg["source_lane"] == other))
            row[lane] = {"grey_units": len(shown), "repeat_own_solid": repeated(shown, committed[lane]),
                         "repeat_other_lane": repeated(shown, committed[other] + other_shown)}
        polls.append(row)
    worst = max(polls, key=lambda r: r["system"]["repeat_own_solid"], default=None)
    out["S1_system_preview_vs_solid"] = {
        "snapshots_with_preview": len(polls),
        "snapshots_where_system_grey_repeats_>=10_solid_units": sum(r["system"]["repeat_own_solid"] >= 10 for r in polls),
        "worst": worst,
        "seconds_with_repeat": round(sum(b["e"] - a["e"] for a, b in zip(polls, polls[1:])
                                         if a["system"]["repeat_own_solid"] >= 10), 1)}
    out["mic_preview"] = {
        "snapshots_with_mic_grey": sum(r["microphone"]["grey_units"] > 0 for r in polls),
        "max_mic_grey_units": max((r["microphone"]["grey_units"] for r in polls), default=0),
        "max_mic_grey_repeating_system": max((r["microphone"]["repeat_other_lane"] for r in polls), default=0),
        "distinct_mic_grey_texts": sorted({seg["text"] for snap in snaps if snap["provisional"]
                                           for seg in snap["provisional"]["segments"]
                                           if seg["source_lane"] == "microphone"})[:40]}

    # What the page showed: grey rows by lane, and whether a grey row hangs under a solid card of its lane
    grey = {}
    for entry in rows_log:
        for row in entry["rows"]:
            if row["guess"] or any(f["grey"] for f in row["fragments"]):
                key = (row["lane"], row["continuation"], row["source"])
                grey[key] = grey.get(key, 0) + 1
    out["page_grey_rows"] = [{"lane": k[0], "continuation_of_card_above": k[1], "source_label": k[2], "samples": v}
                             for k, v in sorted(grey.items(), key=lambda kv: str(kv[0]))]

    # S2/S3: microphone rows live, at Stop, and after clean-up
    def rows_of(path):
        doc = json.loads((OUT / path).read_text())
        return (doc.get("transcript") or {}).get("segments") or []
    live_rows, final_rows = rows_of("saved-meeting-live.json"), rows_of("saved-meeting.json")
    before_stop = next((s for s in reversed(snaps) if s["note"] == "before Stop"), None)
    out["mic_rows"] = {
        "max_live_mic_rows": max(sum(1 for r in s["effective"] if r.get("source_lane") == "microphone") for s in snaps),
        "saved_at_stop": [r["text"] for r in live_rows if r.get("source_lane") == "microphone"],
        "after_cleanup": [r["text"] for r in final_rows if r.get("source_lane") == "microphone"]}
    for name, rows in (("system_saved_at_stop", live_rows), ("system_after_cleanup", final_rows)):
        text = "".join(r["text"] for r in rows if r.get("source_lane") == "system")
        out[name] = {**text_stats(text), "rows": [(r["start"], r["end"], r["speaker"], r["text"])
                                                 for r in rows if r.get("source_lane") == "system"]}
    if before_stop:
        out["system_live_before_stop"] = text_stats(lane_text(before_stop["effective"], "system"))
    diag = json.loads((OUT / "engine.json").read_text())
    out["diagnostics"] = {k: diag.get(k) for k in (
        "calls_by_kind", "timing_anomalies", "repaired_words", "mic_words_dropped_by_acoustic_gate",
        "mic_words_dropped_by_text_guard", "mic_echo_dropped_by_voice", "mic_words_dropped_unanchored",
        "mic_words_withheld_unanchored_lane", "coverage_retries", "terminal_coverage_fallbacks",
        "degraded_path_activations", "errors_by_code", "audio_seconds_sent")}
    (OUT / "analysis.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if "--timeline" in sys.argv:
        for r in polls:
            print(f"e={r['e']:6.2f} committed={r['committed_s']:5.1f}  sys grey {r['system']['grey_units']:3d} "
                  f"repeat-solid {r['system']['repeat_own_solid']:3d} | mic grey {r['microphone']['grey_units']:3d} "
                  f"repeat-system {r['microphone']['repeat_other_lane']:3d}")


main()
