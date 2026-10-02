"""H2: rule H on every (live sample, whole-recording draw) pair of the Chinese+names fixture ($0, throwaway).

    PY f3/s2_witness.py [--detail]

Live samples: the committed live words of the production engine at five leading silences (`runs/base-short-aec40`
= R5-D's recorded meeting, `runs/live-p*` = new). Whole-recording draws: every recorded answer for the same audio
(production request and the request variants), time-shifted to the live sample's leading silence.
Scored against the fixture's script (the text the voice was given), on comparable units, script-folded for
scoring only: units of the passage that are missing, and units that are extra (doubled or invented).
"""
from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import f3lib  # noqa: E402
import rule  # noqa: E402
from f3lib import EV, RAW, RD, RD_RAW, S  # noqa: E402
from rule import Word  # noqa: E402

ZH = json.loads((RD / "fixtures" / "fixtures.json").read_text())["text"]["zh"]
NAMES = ["media", "lab", "alan", "turing", "grace", "hopper", "microsoft", "google", "google", "computerphile"]
ZH_END = 20.6
_PAIRS = dict(zip("這個問題學院計算機經網絡訓練會議頻道專訪從頭講為什麼開願術們視頻對實現時間後來說話還沒與業務數據長個發進佈",
                  "这个问题学院计算机经网络训练会议频道专访从头讲为什么开愿术们视频对实现时间后来说话还没与业务数据长个发进布"))
LIVE = {0.0: "live-p0", 1.5: "live-p1.5", 3.0: "base-short-aec40", 5.0: "live-p5", 8.0: "live-p8"}
SWEEP_M = (0.1, 0.15, 0.2, 0.3, 0.5, 1.0)
OWNER = "--raw-witness" not in sys.argv
for _flag in sys.argv:
    if _flag.startswith("--edge="):
        rule.VARIANT["edge"] = _flag.split("=", 1)[1]


def fold(text: str) -> str:
    return "".join(_PAIRS.get(ch, ch) for ch in text)


def zh_units(words, prefix: float) -> list[str]:
    units = f3lib.units(fold(" ".join(w.text for w in words if w.start_sample < (prefix + ZH_END) * S)))
    out = []
    for unit in units:      # "Computer File" / "Computer phile" is the provider's replacement for "Computerphile"
        if out and out[-1] == "computer" and unit in ("file", "phile"):
            out[-1] = "computerphile"
        else:
            out.append(unit)
    return out


TRUTH = f3lib.units(fold(ZH))


def against_truth(units: list[str]) -> tuple[int, int]:
    """(truth units missing, extra units) by one in-order alignment."""
    same = sum(b.size for b in difflib.SequenceMatcher(None, TRUTH, units, autojunk=False).get_matching_blocks())
    return len(TRUTH) - same, len(units) - same


def stutters(units: list[str]) -> int:
    return sum(a == b for a, b in zip(units, units[1:]))


def draws() -> list[tuple[str, float, Path]]:
    out = []
    for variant in ("base", "lang", "lang2", "text"):
        path = EV / "runs" / f"request-sys-zhlatin-en-{variant}.json"
        for row in json.loads(path.read_text()) if path.is_file() else []:
            if "answer" not in row:
                continue
            prefix = float(row["draw"].rsplit("-p", 1)[1])
            source = next(f / row["answer"] for f in (RAW, RD_RAW) if (f / row["answer"]).is_file())
            out.append((row["draw"].replace("sys-zhlatin-en-", ""), prefix, source))
    return out


def shifted(path: Path, by: float):
    words, _ = f3lib.response_words(path)
    delta = int(round(by * S))
    return [Word(w.text, w.speaker, w.start_sample + delta, w.end_sample + delta) for w in words]


def main():
    detail = "--detail" in sys.argv
    table = []
    for live_prefix, run in LIVE.items():
        raw = json.loads((EV / "runs" / run / "witness.json").read_text())["system"]
        witness = [Word(*w[:4]) for w in raw]
        if OWNER:
            witness = rule.one_owner(witness, [w[4] for w in raw])
        live_units = zh_units(witness, live_prefix)
        live_names = f3lib.kept_of(NAMES, [u for u in live_units if u.isascii() and u.isalpha()])[0]
        for name, prefix, path in draws():
            words = shifted(path, live_prefix - prefix)
            today = zh_units(words, live_prefix)
            need = {t: min(NAMES.count(t), max(live_units.count(t), today.count(t))) for t in set(NAMES)}
            row = {"live": run, "cleanup": name, "live_names_of_10": live_names, "need": need,
                   "today_lost_names_live_had": sum(max(0, c - today.count(t)) for t, c in need.items()),
                   "live_missing_extra": against_truth(live_units),
                   "today": {"names": f3lib.kept_of(NAMES, [u for u in today if u.isascii() and u.isalpha()])[0],
                             "missing_extra": against_truth(today), "stutters": stutters(today),
                             "punctuation": f3lib.punctuation("".join(w.text for w in words
                                                                      if w.start_sample < (live_prefix + ZH_END) * S))},
                   "runs": [{"s": round(n / S, 2), "text": " ".join(w.text for w in r),
                             "at": round(r[0].start_sample / S, 1)} for r, n in rule.uncovered_runs(words, witness)]}
            for m in SWEEP_M:
                filled, restored = rule.fill_holes(words, witness, min_run_samples=int(m * S))
                it = iter(filled)                      # every whole-recording word is still there, in its order
                assert all(any(w is f for f in it) for w in words)
                after = zh_units(sorted(filled, key=lambda w: (w.start_sample, w.end_sample)), live_prefix)
                names = f3lib.kept_of(NAMES, [u for u in after if u.isascii() and u.isalpha()])[0]
                row[f"m{m}"] = {"lost_names_either_had": sum(max(0, c - after.count(t)) for t, c in need.items()),
                                "names": names, "missing_extra": against_truth(after), "stutters": stutters(after),
                                "restored_runs": len(restored), "restored_words": sum(len(r["text"]) for r in restored),
                                "punctuation": f3lib.punctuation("".join(
                                    w.text for w in filled if w.start_sample < (live_prefix + ZH_END) * S)),
                                "overlaps_kept_word": sum(
                                    1 for r in restored for w in words
                                    if w.end_sample > w.start_sample
                                    and min(w.end_sample, r["end_s"] * S) - max(w.start_sample, r["start_s"] * S) > 0.1 * S)}
            table.append(row)
    (EV / "runs" / "witness-pairs.json").write_text(json.dumps(table, ensure_ascii=False, indent=1) + "\n")
    n = len(table)
    print(f"pairs: {n} = {len(LIVE)} live samples x {n // len(LIVE)} whole-recording draws; passage = {len(TRUTH)} units")
    print("live samples (names of 10; units missing, extra vs the script):",
          {r["live"]: (r["live_names_of_10"], r["live_missing_extra"]) for r in table})

    def summary(key):
        cells = [r[key] for r in table]
        best = [min(r["live_names_of_10"], 10) for r in table]
        return {"names_kept_mean": round(sum(c["names"] for c in cells) / n, 2),
                "name_tokens_lost_that_live_or_cleanup_had": (
                    sum(r["today_lost_names_live_had"] for r in table) if key == "today"
                    else sum(c["lost_names_either_had"] for c in cells)),
                "pairs_losing_such_a_name": (sum(r["today_lost_names_live_had"] > 0 for r in table) if key == "today"
                                             else sum(c["lost_names_either_had"] > 0 for c in cells)),
                "units_missing_mean": round(sum(c["missing_extra"][0] for c in cells) / n, 2),
                "units_extra_mean": round(sum(c["missing_extra"][1] for c in cells) / n, 2),
                "pairs_with_more_extra_than_today": sum(c["missing_extra"][1] > r["today"]["missing_extra"][1]
                                                        for c, r in zip(cells, table)),
                "pairs_with_more_missing_than_today": sum(c["missing_extra"][0] > r["today"]["missing_extra"][0]
                                                          for c, r in zip(cells, table)),
                "stutters_total": sum(c["stutters"] for c in cells),
                "punctuation_mean": round(sum(c["punctuation"] for c in cells) / n, 2),
                **({"restored_words_total": sum(c["restored_words"] for c in cells),
                    "restored_overlapping_a_kept_word": sum(c["overlaps_kept_word"] for c in cells)} if key != "today" else {})}

    print("today      ", json.dumps(summary("today")))
    for m in SWEEP_M:
        print(f"rule m={m:<4}", json.dumps(summary(f"m{m}")))
    # every uncovered live run, by what it is
    kinds: dict[str, list[float]] = {}
    for r in table:
        for run in r["runs"]:
            kinds.setdefault(run["text"], []).append(run["s"])
    print("\nuncovered live runs over all pairs (text: count, uncovered seconds min-max):")
    for text, secs in sorted(kinds.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(secs):3d}  {min(secs):.2f}-{max(secs):.2f} s  {text}")
    key = "m0.15"
    print(f"\nrestored at {key} that leave more extra units than today (pair: runs restored):")
    for r in table:
        if r[key]["missing_extra"][1] > r["today"]["missing_extra"][1] or r[key]["stutters"] > r["today"]["stutters"]:
            print("  ", r["live"], r["cleanup"], [x for x in r["runs"] if x["s"] >= 0.15 and x["at"] < 26])
    print(f"\nname tokens still lost at {key} (pair: need, runs):")
    shown = 0
    for r in table:
        if r[key]["lost_names_either_had"] and shown < 12:
            shown += 1
            print("  ", r["live"], r["cleanup"], "lost", r[key]["lost_names_either_had"], [x for x in r["runs"] if x["at"] < 26])
    if detail:
        for r in table:
            print(json.dumps({k: v for k, v in r.items() if k in ("live", "cleanup", "today", "m0.2", "runs")},
                             ensure_ascii=False))


if __name__ == "__main__":
    main()
