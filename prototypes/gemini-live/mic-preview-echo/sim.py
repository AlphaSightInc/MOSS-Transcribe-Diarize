"""$0 replay of the live preview composer on recorded W3 streams (throwaway).

Feeds recorded W3 updates (both lanes where recorded) and timed committed rows through the
hybrid engine's preview bookkeeping, the lane composer's mic echo test (pluggable), and the
runtime's `_trim_committed_preview`, then counts what the grey mic preview shows.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT)]
from moss_transcribe_diarize.app.gemini_live_runtime import (GeminiSegment, _trim_committed_preview,  # noqa: E402
                                                              _PREVIEW_NUMBERS)
from moss_transcribe_diarize.app.gemini_provider import ordered_segments, speaker_turns  # noqa: E402
from moss_transcribe_diarize.app.live_session import EffectiveTranscriptSegment  # noqa: E402

S = 16000
EVID = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence")
V1 = ROOT / "prototypes/gemini-live/mic-hallucination/out/fixture"
REFRESH, LAG = 15, 4  # rolling refresh and observed publication lag (s)


def units(text: str) -> list[str]:
    out = []
    for token in re.findall(r"[^\W_\d]+|\d+", text.casefold()):
        run = ""
        for ch in token:
            if unicodedata.name(ch, "").startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL")):
                if run:
                    out.append(run)
                    run = ""
                out.append(ch)
            else:
                run += ch
        if run:
            out.append(run)
    return [_PREVIEW_NUMBERS.get(u, u) for u in out]


def lcs(a, b):
    return sum(block.size for block in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks())


# ----------------------------------------------------------------------------- rules

REF_MODE = {"mode": "time"}


def reference_units(row, system_preview, system_committed, n):
    """System words (committed then preview) a repeated passage of n units could come from.

    time: committed rows ending within n/1.5 s + 5 s before the row's end (speech runs faster
    than 1.5 units/s), plus the current system preview. count: last max(60, 5n/4+8) units.
    """
    limit = row.end_sample + 2 * S
    if REF_MODE["mode"] == "time":
        since = row.end_sample - round((n / 1.5 + 5) * S)
        rows = [r for r in system_committed if r.end_sample >= since and r.start_sample < limit] + \
               [r for r in system_preview if r.start_sample < limit]
        return [u for r in rows for u in units(r.text)]
    rows = [r for r in system_committed if r.start_sample < limit] + \
           [r for r in system_preview if r.start_sample < limit]
    seq = [u for r in rows for u in units(r.text)]
    return seq[-max(60, n * 5 // 4 + 8):]


def _echoed_preview(row, system):
    """Pre-change product rule (gemini_lane_engine at 1219db04): >= 60% of the mic row's words
    occur in the union of system preview rows overlapping it within 2 s."""
    words = re.findall(r"[^\W_\d]+|\d+", row.text.casefold())
    if not words:
        return False
    other = {w for seg in system if seg.start_sample <= row.end_sample + 2 * S
             and seg.end_sample + 2 * S >= row.start_sample
             for w in re.findall(r"[^\W_\d]+|\d+", seg.text.casefold())}
    return 5 * sum(w in other for w in words) >= 3 * len(words)


def rule_base(row, system_preview, system_committed):
    return _echoed_preview(row, system_preview)


def rule_bag(row, system_preview, system_committed):
    words = units(row.text)
    if not words:
        return False
    other = set(reference_units(row, system_preview, system_committed, len(words)))
    return 5 * sum(w in other for w in words) >= 3 * len(words)


def make_seq(k, share=.6):
    def rule(row, system_preview, system_committed):
        words = units(row.text)
        if len(words) < k:
            return False
        ref = reference_units(row, system_preview, system_committed, len(words))
        matched = sum(b.size for b in difflib.SequenceMatcher(None, ref, words, autojunk=False)
                      .get_matching_blocks() if b.size >= k)
        return matched >= share * len(words)
    return rule


def unit_spans(text: str):
    """(unit, start, end) over the original text: CJK per character, other runs whole."""
    out = []
    for m in re.finditer(r"[^\W_\d]+|\d+", text):
        token = m.group()
        i = 0
        while i < len(token):
            ch = token[i]
            if unicodedata.name(ch, "").startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL")):
                out.append((ch.casefold(), m.start() + i, m.start() + i + 1))
                i += 1
                continue
            j = i
            while j < len(token) and not unicodedata.name(token[j], "").startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL")):
                j += 1
            u = token[i:j].casefold()
            out.append((_PREVIEW_NUMBERS.get(u, u), m.start() + i, m.start() + j))
            i = j
    return out


def _cjk(u):
    return len(u) == 1 and unicodedata.name(u, "").startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL"))


def _blocks(ref, words, k, cjk_k):
    hit = set()
    for b in difflib.SequenceMatcher(None, ref, words, autojunk=False).get_matching_blocks():
        if b.size and sum(k / cjk_k if (cjk_k and _cjk(u)) else 1 for u in words[b.b:b.b + b.size]) >= k:
            hit.update(range(b.b, b.b + b.size))
    return hit


def make_strip(k, keep_min=1, run_min=1, cjk_k=None, own=False):
    """Remove the mic row's units inside >= k-unit blocks that repeat recent system text."""
    def rule(row, system_preview, system_committed):
        spans = unit_spans(row.text)
        words = [u for u, _, _ in spans]
        if len(words) < k:
            return row
        ref = reference_units(row, system_preview, system_committed, len(words))
        echo = set()
        for b in difflib.SequenceMatcher(None, ref, words, autojunk=False).get_matching_blocks():
            if not b.size:
                continue
            block = words[b.b:b.b + b.size]
            weight = sum(k / cjk_k if (cjk_k and _cjk(u)) else 1 for u in block)
            if weight >= k:
                echo.update(range(b.b, b.b + b.size))
        if not echo:
            return row
        kept = [i for i in range(len(spans)) if i not in echo]
        runs, cur = [], []
        for i in kept:
            if cur and i != cur[-1] + 1:
                runs.append(cur)
                cur = []
            cur.append(i)
        if cur:
            runs.append(cur)
        runs = [r for r in runs if len(r) >= run_min]
        if own and runs:
            # A row that carried echo: its leftover pieces that repeat the lane's own committed
            # words are already on screen above it.
            mine = [r for r in rule.mic_committed if r.end_sample >= row.end_sample - round((len(words) / 1.5 + 5) * S)]
            mref = [u for r in mine for u in units(r.text)]
            runs = [r for r in runs if len(_blocks(mref, [words[i] for i in r], k, cjk_k)) * 2 < len(r)]
        kept = [i for r in runs for i in r]
        if len(kept) < keep_min:
            return None
        pieces, run = [], []
        for i in kept:
            if run and i != run[-1] + 1:
                pieces.append(row.text[spans[run[0]][1]:spans[run[-1]][2]])
                run = []
            run.append(i)
        if run:
            pieces.append(row.text[spans[run[0]][1]:spans[run[-1]][2]])
        return GeminiSegment(row.start_sample, row.end_sample, " … ".join(pieces), row.speaker, row.source_lane)
    return rule


RULES = {"baseline": rule_base, "bag_committed+preview": rule_bag, "seq3_60": make_seq(3),
         "strip3_run4_cjk5": make_strip(3, run_min=4, cjk_k=5)}
_own = make_strip(3, run_min=4, cjk_k=5, own=True)
_own.mic_committed = []
RULES["strip3_run4_cjk5_own"] = _own


def _product(row, system_preview, system_committed):
    """The production composer function (gemini_lane_engine._without_echo)."""
    from moss_transcribe_diarize.app.gemini_lane_engine import _without_echo
    return _without_echo(row, list(system_committed) + list(system_preview), _product.mic_committed)


_product.mic_committed = []
RULES["product"] = _product
if "--product" in sys.argv:
    RULES = {"baseline": rule_base, "product": _product}


# ----------------------------------------------------------------------------- inputs

def w3_events(path, kind):
    d = json.loads(Path(path).read_text())
    if kind == "p52":
        return [(u["audio_end_s"], u["audio_start_s"], u["text"], u["kind"] == "input_transcription")
                for u in d["updates_full"]]
    return [(e["end_s"], e["start_s"], e["text"], e["final"]) for e in d["events"]]


def rows_from_words(words):
    segs = tuple(GeminiSegment(round(w["start"] * S), max(round(w["end"] * S), round(w["start"] * S) + 1),
                               w["text"], w.get("speaker", "s"), "system") for w in words)
    return list(speaker_turns(ordered_segments(segs, start_sample=0, end_sample=10 ** 9, preserve_order=True)))


def case_inputs(name):
    if name in ("E1", "M2"):
        snap = json.loads((EVID / "P68/r4-smoke/runs/e1/run/stop_snapshot.json").read_text())
        rows = snap["session"]["effective_transcript"]
        # Committed system text at word granularity: P52 cached 30 s/10 s rolling windows of the
        # same E1 system lane, each owning the words that end in (previous end, end].
        words, prior = [], 0.0
        for path in sorted((EVID / "P52").glob("lane-batch-system-*.json")):
            w = json.loads(path.read_text())
            words += [x for x in w["words"] if prior < x["end"] <= w["end_s"]]  # absolute times
            prior = w["end_s"]
        sys_rows = [GeminiSegment(round(x["start"] * S), max(round(x["end"] * S), round(x["start"] * S) + 1),
                                  x["text"], "s", "system") for x in words]
        mic_rows = [GeminiSegment(r["start_sample"], r["end_sample"], r["text"], "local", "microphone")
                    for r in rows if r["source_lane"] == "microphone"]
        local = [(r.start_sample / S, r.end_sample / S, units(r.text)) for r in mic_rows]
        mic = w3_events(EVID / f"P52/lane-live-{name}-mic.json", "p52")
        system = w3_events(EVID / "P52/robust-live-e1_system-en-US.json", "p52")
        return {"system_w3": system, "mic_w3": mic, "sys_rows": sys_rows,
                "mic_rows": mic_rows, "local": local}
    if name == "zh2-echo":
        # Corrected Mandarin echo lane (two genuinely different voices: Tingting far end, Meijia
        # local), built and recorded by prototypes/gemini-live/preview-script.
        ps = HERE.parent / "preview-script" / "out"
        man = json.loads((ps / "manifest.json").read_text())["zh2-echo"]
        return {"system_ref": [u for r in man["system"] for u in units(r["text"])],
                "system_w3": w3_events(ps / "zh2-system-w3.json", "v1"),
                "mic_w3": w3_events(ps / "zh2-echo-w3.json", "v1"),
                "sys_rows": [GeminiSegment(round(r["start"] * S), round(r["end"] * S), r["text"], "s", "system")
                             for r in man["system"]],
                "mic_rows": [], "local": [(r["start"], r["end"], units(r["text"])) for r in man["local"]]}
    if name == "qmic-sp10":
        sys.path.insert(0, str(ROOT / "prototypes/gemini-live/common"))
        import hashlib
        import gemini_common as g
        q = ROOT / "prototypes/gemini-live/micfixture/out"
        pcm = g.read_wav(q / "system.wav")
        mode = {"type": "verbatim", "diarization_mode": "speaker", "timestamp_granularities": ["word"]}
        key = hashlib.sha256(g.wav_bytes(pcm) + json.dumps(["gemini-3.5-transcribe", {"transcription_config": {"mode": mode}}],
                                                          sort_keys=True).encode()).hexdigest()
        assert (g.CACHE_DIR / key[:2] / f"{key}.json").exists(), "Q-MIC system words must be cached ($0)"
        words = g.diarize_window(pcm).words
        ref = json.loads((q / "reference.json").read_text())
        return {"system_ref": [u for r in ref["system_turns"] for u in units(r["text"])],
                "system_w3": w3_events(HERE / "out/qmic-system-w3.json", "v1"),
                "mic_w3": w3_events(HERE / "out/qmic-sp10-mic-w3.json", "v1"),
                "sys_rows": [GeminiSegment(round(w.start * S), max(round(w.end * S), round(w.start * S) + 1), w.text, "s", "system")
                             for w in words],
                "mic_rows": [], "local": [(r["start"], r["end"], units(r["text"])) for r in ref["local_turns"]]}
    ref = json.loads((V1 / "reference.json").read_text())
    lang = name.split("-")[0]
    g = json.loads((V1 / f"{'zh-hp' if name == 'zh-echo' else name}-gemini.json").read_text())  # same zh system lane
    sys_rows = [GeminiSegment(round(w["start"] * S), max(round(w["end"] * S), round(w["start"] * S) + 1),
                              w["text"], "s", "system") for w in g["whole_system"]]
    local = [(r["start"], r["end"], units(r["text"])) for r in ref[lang]["local_turns"] + ref[lang]["backchannels"]]
    memo = HERE.parent / "mic-hallucination/out/prefix-memo" / f"{name}-gated.json"
    mic_rows = []
    if memo.exists():  # committed mic words: production-gated rolling windows, each owning (prev end, end]
        windows = sorted(((int(k.split(":")[0]), int(k.split(":")[1]), v) for k, v in json.loads(memo.read_text()).items()
                          if k != "terminal"), key=lambda w: w[1])
        prior = 0
        for _start, end, rows in windows:
            mic_rows += [GeminiSegment(r[2], max(r[3], r[2] + 1), r[0], "local", "microphone")
                         for r in rows if prior < r[3] <= end]
            prior = end
    if name == "zh-echo":
        return {"system_ref": [u for r in ref[lang]["system_turns"] for u in units(r["text"])],
                "system_w3": w3_events(HERE / "out/zh-system-w3.json", "v1"),
                "mic_w3": w3_events(HERE / "out/zh-echo-mic-w3.json", "v1"), "sys_rows": sys_rows,
                "mic_rows": [], "local": local}
    return {"system_w3": None, "mic_w3": w3_events(V1 / f"{name}-w3.json", "v1"), "sys_rows": sys_rows,
            "mic_rows": mic_rows, "local": local}


# ----------------------------------------------------------------------------- replay

class LanePreview:
    """GeminiHybridEngine._on_live_text bookkeeping for one lane."""

    def __init__(self, lane):
        self.lane, self.finals, self.interim, self.committed = lane, [], None, 0

    def update(self, text, start, end, final, accepted):
        if not text.strip() or end <= self.committed:
            return None
        row = (text.strip(), start, end)
        if final:
            self.finals.append(row)
            self.interim = None
        else:
            self.interim = row
        self.finals = [w for w in self.finals if w[2] > self.committed]
        return self.preview(accepted, end)

    def preview(self, accepted, end=None):
        fast = list(self.finals) + ([self.interim] if self.interim else [])
        end = min(accepted, max(self.committed, end if end is not None else accepted))
        return ordered_segments(tuple(GeminiSegment(s, max(e, s + 1), t, source_lane=self.lane)
                                      for t, s, e in fast if e > self.committed),
                                start_sample=self.committed, end_sample=end)


def compose(previews, start, end, rule, sys_committed):
    """LaneGeminiEngine._preview_rows with a pluggable mic echo test."""
    segments = []
    for lane in ("system", "microphone"):
        for row in previews.get(lane, ()):
            if row.end_sample <= start or row.start_sample >= end:
                continue
            cur = GeminiSegment(max(row.start_sample, start), min(row.end_sample, end), row.text, None, lane)
            segments = [p for p in segments if p.source_lane != lane or p.end_sample <= cur.start_sample
                        or p.start_sample >= cur.end_sample]
            segments.append(cur)
    system = [r for r in segments if r.source_lane == "system"]
    out = []
    for r in segments:
        if r.source_lane == "system":
            out.append(r)
            continue
        verdict = rule(r, system, sys_committed)
        if verdict is True or verdict is None:
            continue
        out.append(r if verdict is False else verdict)
    return out


def replay(name, rule):
    data = case_inputs(name)
    events = [(t, "microphone", s, x, f) for t, s, x, f in data["mic_w3"]]
    if data["system_w3"]:
        events += [(t, "system", s, x, f) for t, s, x, f in data["system_w3"]]
    events.sort(key=lambda e: (e[0], e[1]))
    lanes = {"system": LanePreview("system"), "microphone": LanePreview("microphone")}
    shown_local = shown_other = polls = max_other = 0
    first_seen = {}
    elapsed = worst = 0.0
    reshown = 0
    for t, lane, s, text, final in events:
        acc = round(t * S)
        frontier = max(0, int((t - LAG) // REFRESH) * REFRESH) * S
        for ln in lanes.values():
            ln.committed = max(ln.committed, frontier)
        prev = {ln: lanes[ln].preview(acc) for ln in lanes}
        up = lanes[lane].update(text, round(s * S), acc, final, acc)
        if up is not None:
            prev[lane] = up
        if data["system_w3"] is None:  # system preview stand-in: batch words beyond the frontier
            prev["system"] = tuple(GeminiSegment(max(r.start_sample, frontier), min(r.end_sample, acc), r.text,
                                                 None, "system") for r in data["sys_rows"]
                                   if r.end_sample > frontier and r.start_sample < acc)
        sys_committed = [r for r in data["sys_rows"] if r.end_sample <= frontier]
        ref_committed = sys_committed
        if hasattr(rule, "mic_committed"):
            rule.mic_committed = [r for r in data["mic_rows"] if r.end_sample <= frontier]
        t0 = time.perf_counter()
        composed = compose(prev, frontier, acc, rule, ref_committed)
        took = time.perf_counter() - t0
        elapsed += took
        worst = max(worst, took)
        committed = [EffectiveTranscriptSegment(r.start_sample, r.end_sample, r.text, None, "rolling", r.source_lane)
                     for r in sorted(sys_committed + [r for r in data["mic_rows"] if r.end_sample <= frontier],
                                     key=lambda r: r.start_sample)]
        shown = [r for r in _trim_committed_preview(composed, committed) if r.source_lane == "microphone"]
        done = [units(r.text) for r in data["mic_rows"] if r.end_sample <= frontier]
        if any(b.size >= 3 for r in shown for d in done
               for b in difflib.SequenceMatcher(None, d, units(r.text), autojunk=False).get_matching_blocks()):
            reshown += 1
        polls += 1
        other_now = 0
        for r in shown:
            u = units(r.text)
            local_idx = set()
            per_item = {}
            for i, (a, b, p) in enumerate(data["local"]):
                if a - 1 > t:
                    continue
                blocks = [bl for bl in difflib.SequenceMatcher(None, p, u, autojunk=False).get_matching_blocks()
                          if bl.size >= min(2, len(p))]
                item = set()
                for bl in blocks:
                    item.update(range(bl.b, bl.b + bl.size))
                per_item[i] = item
                local_idx |= item
            echo_idx = set()
            if data.get("system_ref"):
                for bl in difflib.SequenceMatcher(None, data["system_ref"], u, autojunk=False).get_matching_blocks():
                    if bl.size >= 2:
                        echo_idx.update(range(bl.b, bl.b + bl.size))
                both = local_idx & echo_idx
                local_idx -= both
                echo_idx -= both
            for i, item in per_item.items():
                p = data["local"][i][2]
                if len(item & local_idx) >= max(1, min(len(p) // 2, 3)):
                    first_seen.setdefault(i, t)
            loc = len(local_idx)
            shown_local += loc
            # echo cases with a reference far-end text: count distinctive echo units; else non-local
            other_now += len(echo_idx) if data.get("system_ref") else len(u) - loc
        shown_other += other_now
        max_other = max(max_other, other_now)
    return {"polls": polls, "local_word_polls": shown_local, "other_word_polls": shown_other,
            "max_other_words_one_poll": max_other, "local_items_seen": len(first_seen),
            "local_items": len(data["local"]), "first_seen": first_seen,
            "rule_ms_per_poll": round(1000 * elapsed / max(1, polls), 3), "rule_ms_max": round(1000 * worst, 2),
            "reshown_committed_mic_polls": reshown}


def main():
    cases = [c for c in sys.argv[1:] if not c.startswith("--")] or ["E1", "M2", "en-hp", "en-sp", "zh-hp", "zh-sp", "zh-echo", "qmic-sp10"]
    out = {}
    for rule_name, rule in RULES.items():
        for case in cases:
            r = replay(case, rule)
            out.setdefault(rule_name, {})[case] = r
            print(f"{rule_name:22} {case:6} other(max/poll) {r['max_other_words_one_poll']:4d} other-sum {r['other_word_polls']:6d}"
                  f" local-sum {r['local_word_polls']:6d} local items {r['local_items_seen']}/{r['local_items']}"
                  f" {r['rule_ms_per_poll']} ms (max {r['rule_ms_max']}) reshown {r['reshown_committed_mic_polls']}", flush=True)
    for rule_name in RULES:
        if rule_name == "baseline":
            continue
        for case in cases:
            b, r = out["baseline"][case]["first_seen"], out[rule_name][case]["first_seen"]
            data = case_inputs(case)
            big = {i for i, (_, _, p) in enumerate(data["local"]) if len(p) >= 4}
            delays = [round(r[i] - b[i], 2) for i in b if i in r and i in big]
            lost = [i for i in b if i not in r and i in big]
            out[rule_name][case]["delay_s"] = delays
            out[rule_name][case]["lost_items"] = lost
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / "sim.json").write_text(json.dumps(out, indent=1, default=str))
    for rule_name in RULES:
        if rule_name != "baseline":
            print(rule_name, {c: (max(out[rule_name][c]["delay_s"], default=0), out[rule_name][c]["lost_items"]) for c in cases})


if __name__ == "__main__":
    main()
