"""$0 replay: which mic preview words are in a script foreign to the meeting so far, and what does
hiding them cost genuine speech (incl. a real mid-meeting language switch)?

Recorded W3 mic updates run through the hybrid preview bookkeeping, the production echo strip
(`_without_echo`), a candidate script rule, and `_trim_committed_preview`. Committed text is the
reference text of turns that ended before the 15 s rolling frontier (published 4 s late).
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT)]
from moss_transcribe_diarize.app import gemini_lane_engine as lane_engine  # noqa: E402
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment, _trim_committed_preview  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import ordered_segments  # noqa: E402
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment  # noqa: E402

S = 16000
OUT = HERE / "out"
REFRESH, LAG = 15, 4
SUSTAINED = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--bar=")), 20))  # 3/CJK char, 5/word


def script(ch):
    if not ch.isalpha():
        return None
    head = unicodedata.name(ch, "").split(" ")[0]
    return {"HIRAGANA": "KANA", "KATAKANA": "KANA", "CJK": "HAN"}.get(head, head)  # sim names Han "HAN"


def runs(text):
    """[script, weight, start, end): maximal same-script letter spans; a run owns the text up to the next run.

    A word is a stretch of one script's letters and their combining marks (Devanagari vowel signs
    are marks, not letters); CJK-like scripts weigh 3 per character, other scripts 5 per word.
    """
    out = []
    i, n = 0, len(text)
    while i < n:
        s = script(text[i])
        if s is None:
            i += 1
            continue
        j = i + 1
        while j < n and (script(text[j]) == s or unicodedata.category(text[j]).startswith("M")):
            j += 1
        w = 3 * sum(1 for ch in text[i:j] if ch.isalpha()) if s in ("HAN", "KANA", "HANGUL") else 5
        if out and out[-1][0] == s:
            out[-1][1] += w
        else:
            out.append([s, w, i, None])
        i = j
    for k, r in enumerate(out):
        r[3] = out[k + 1][2] if k + 1 < len(out) else len(text)
    return out


def units(text):
    out = []
    for token in re.findall(r"[^\W_\d]+|\d+", text.casefold()):
        run = ""
        for ch in token:
            if script(ch) in ("HAN", "KANA", "HANGUL"):
                if run:
                    out.append(run)
                    run = ""
                out.append(ch)
            else:
                run += ch
        if run:
            out.append(run)
    return out


# ------------------------------------------------------------------ rule arms

def strip(row, bad):
    rs = runs(row.text)
    drop = [r for r in rs if bad(r, rs)]
    if not drop:
        return row
    text = row.text
    for r in reversed(drop):
        text = text[:r[2]] + text[r[3]:]
    text = text.strip()
    return GeminiSegment(row.start_sample, row.end_sample, text, row.speaker, row.source_lane) if runs(text) else None


def arm_none(row, established):
    return row


def arm_runs(row, established):          # every unestablished run
    return strip(row, lambda r, rs: r[0] not in established)


def arm_isolated(row, established):      # only rows made of unestablished scripts
    rs = runs(row.text)
    return None if rs and all(r[0] not in established for r in rs) else row


def sustained(text):
    totals = Counter()
    for sc, w, _, _ in runs(text):
        totals[sc] += w
    return {sc for sc, w in totals.items() if w >= SUSTAINED}


def arm_short_rows(row, established):    # unestablished runs in rows that hold no sustained script
    return strip(row, lambda r, rs: r[0] not in established) if not sustained(row.text) else row


ARMS = {"none": arm_none, "every_unestablished_run": arm_runs, "isolated_rows_only": arm_isolated,
        "rows_without_sustained_run": arm_short_rows}
if "--product" in sys.argv:
    ARMS = {"none": arm_none, "product": None}


# ------------------------------------------------------------------ replay

class LanePreview:
    def __init__(self, lane):
        self.lane, self.finals, self.interim, self.committed = lane, [], None, 0

    def update(self, text, start, end, final):
        if not text.strip() or end <= self.committed:
            return
        row = (text.strip(), start, end)
        if final:
            self.finals.append(row)
            self.interim = None
        else:
            self.interim = row

    def preview(self, accepted):
        self.finals = [w for w in self.finals if w[2] > self.committed]
        if self.interim and self.interim[2] <= self.committed:
            self.interim = None
        fast = list(self.finals) + ([self.interim] if self.interim else [])
        return ordered_segments(tuple(GeminiSegment(s, max(e, s + 1), t, source_lane=self.lane)
                                      for t, s, e in fast), start_sample=self.committed, end_sample=accepted)


def events(path):
    return [(e["end_s"], e["start_s"], e["text"], e["final"]) for e in json.loads(Path(path).read_text())["events"]]


def replay(case, arm_name):
    manifest = json.loads((OUT / "manifest.json").read_text())[case]
    true_scripts = {script(ch) for r in manifest["local"] + manifest["system"] for ch in r["text"]} - {None}
    local = [(r["start"], r["end"], units(r["text"])) for r in manifest["local"]]
    seg = lambda r, lane: GeminiSegment(round(r["start"] * S), round(r["end"] * S), r["text"], "x", lane)
    sys_rows = [seg(r, "system") for r in manifest["system"]]
    mic_rows = [seg(r, "microphone") for r in manifest["local"]]
    timeline = [(t, "microphone", s, x, f) for t, s, x, f in events(OUT / f"{case}-w3.json")]
    sysw3 = OUT / ("zh2-system-w3.json" if case.startswith("zh2") else "none")
    if sysw3.exists():
        timeline += [(t, "system", s, x, f) for t, s, x, f in events(sysw3) if t <= max(e[0] for e in timeline)]
    timeline.sort(key=lambda e: (e[0], e[1]))
    lanes = {"system": LanePreview("system"), "microphone": LanePreview("microphone")}
    res = Counter()
    first_seen, removed = {}, Counter()
    seen_scripts = set()
    engine = None
    for t, lane, s, text, final in timeline:
        acc = round(t * S)
        frontier = max(0, int((t - LAG) // REFRESH) * REFRESH) * S
        for ln in lanes.values():
            ln.committed = max(ln.committed, frontier)
        lanes[lane].update(text, round(s * S), acc, final)
        mic_prev = lanes["microphone"].preview(acc)
        if sysw3.exists():
            sys_prev = list(lanes["system"].preview(acc))
        else:  # far-end preview stand-in: reference text of the turns still beyond the frontier
            sys_prev = [GeminiSegment(max(r.start_sample, frontier), min(r.end_sample, acc), r.text, None, "system")
                        for r in sys_rows if r.end_sample > frontier and r.start_sample < acc]
        sys_done = [r for r in sys_rows if r.end_sample <= frontier]
        mic_done = [r for r in mic_rows if r.end_sample <= frontier]
        if arm_name == "product":
            if engine is None:  # one composer per meeting; committed rows arrive as GeminiRolling
                engine = lane_engine.LaneGeminiEngine.__new__(lane_engine.LaneGeminiEngine)
                engine._rows = {"system": [], "microphone": []}
                engine._committed_script_weight, engine._scripts = {}, set()
                engine._lane_frontiers = {"system": 0, "microphone": 0}
                engine._observations = {}
                engine._publish_ready = lambda: None
                import threading
                engine._lock = threading.RLock()
            from moss_transcribe_diarize.app.gemini_live_runtime import GeminiRolling
            for ln, done in (("system", sys_done), ("microphone", mic_done)):
                fresh = done[len(engine._rows[ln]):]
                if fresh:
                    engine._on_update(ln, GeminiRolling(0, frontier, tuple(fresh), ()))
            engine._previews = {"system": type("P", (), {"segments": tuple(sys_prev)})(),
                                "microphone": type("P", (), {"segments": tuple(mic_prev)})()}
            composed = [r for r in engine._preview_rows(frontier, acc)]
        else:
            established = set()
            weight = Counter()
            for r in sys_done + mic_done:
                for sc, w, _, _ in runs(r.text):
                    weight[sc] += w
            established |= {sc for sc, w in weight.items() if w >= SUSTAINED}
            composed = list(sys_prev)
            stripped = []
            for row in mic_prev:
                row = lane_engine._without_echo(row, sys_done + sys_prev, mic_done)
                if row is not None:
                    stripped.append(row)
            for r in list(sys_prev) + stripped:
                seen_scripts.update(sustained(r.text))
            established |= seen_scripts
            for row in stripped:
                kept = ARMS[arm_name](row, established)
                if kept is not row:
                    before, after = Counter(units(row.text)), Counter(units(kept.text) if kept else [])
                    for u, n in (before - after).items():
                        removed[u] += n
                if kept is not None:
                    composed.append(kept)
        committed = [EffectiveTranscriptSegment(r.start_sample, r.end_sample, r.text, None, "rolling", r.source_lane)
                     for r in sorted(sys_done + mic_done, key=lambda r: r.start_sample)]
        shown = [r for r in _trim_committed_preview(tuple(composed), committed) if r.source_lane == "microphone"]
        res["polls"] += 1
        foreign_now = 0
        for r in shown:
            u = units(r.text)
            foreign_now += sum(1 for sc, w, a, b in runs(r.text) if sc not in true_scripts
                               for _ in units(r.text[a:b]))
            for i, (a, b, p) in enumerate(local):
                if a - 1 > t:
                    continue
                got = sum(bl.size for bl in difflib.SequenceMatcher(None, p, u, autojunk=False).get_matching_blocks()
                          if bl.size >= min(2, len(p)))
                res["genuine_unit_polls"] += got
                if got >= max(1, min(len(p) // 2, 3)):
                    first_seen.setdefault(i, t)
        res["foreign_unit_polls"] += foreign_now
        res["foreign_max"] = max(res["foreign_max"], foreign_now)
    return res, first_seen, removed, local


def main():
    cases = [c for c in sys.argv[1:] if not c.startswith("--")] or ["zh2-sp", "en2zh", "zh2en"]
    out = {}
    for case in cases:
        base_seen = None
        for arm in ARMS:
            res, seen, removed, local = replay(case, arm)
            if base_seen is None:
                base_seen = seen
            commit = lambda i: -(-local[i][1] // REFRESH) * REFRESH + LAG
            delays = {i: round(seen[i] - base_seen[i], 1) for i in base_seen
                      if i in seen and .05 < seen[i] - base_seen[i] and seen[i] <= commit(i)}
            lost = [i for i in base_seen if i not in seen or seen[i] > commit(i)]
            out[f"{case}/{arm}"] = {**res, "delayed_items": {str(i): (d, round(local[i][0], 1), "".join(local[i][2][:6]))
                                                           for i, d in delays.items()},
                                    # held words appear with their rolling commit instead
                                    "never_shown_items": [(round(local[i][0], 1), "".join(local[i][2][:6]),
                                                           "wait_s", round(-(-local[i][1] // REFRESH) * REFRESH + LAG - base_seen[i], 1))
                                                          for i in lost],
                                    "removed_units_top": removed.most_common(12)}
            print(f"{case:7} {arm:28} foreign-script unit-polls {res['foreign_unit_polls']:4d} (max {res['foreign_max']})"
                  f" genuine unit-polls {res['genuine_unit_polls']:6d} delayed {out[f'{case}/{arm}']['delayed_items']}"
                  f" never {out[f'{case}/{arm}']['never_shown_items']}", flush=True)
            if removed:
                print("        removed:", removed.most_common(12))
    (OUT / ("sim-product.json" if "--product" in sys.argv else "sim.json")).write_text(
        json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
