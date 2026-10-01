"""The gate tables of NOTES.md from the files the other scripts wrote ($0).   PYTHON f2/report.py"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE)]
import candidate, cells, ledger
RUNS = ledger.EV / "runs"
m = json.loads((RUNS / "matrix-final.json").read_text())
TAB = [(0.1, 19.2), (21.5, 35.3)]            # when R5-D's tab is talking (content seconds)


def talking(start, seconds):
    return any(min(b, start + seconds) - max(a, start) > .5 for a, b in TAB)     # more than 0.5 s under the tab


class W:                                       # weight of a phrase as the gate weighs text
    def __init__(self, text): self.text = text


def split(cell, who, key, pick):
    got = said = 0
    for (start, seconds, text), score in zip(cell["today"]["truth"], cell[who][key]["phrases"]):
        if pick(start, seconds, text):
            a, b = score.split("/")
            got, said = got + int(a), said + int(b)
    return f"{got}/{said}" if said else "-"


long_enough = lambda s, d, t: candidate.weight([W(t)]) >= 15
short_reply = lambda s, d, t: candidate.weight([W(t)]) < 15
print("G1/G3 per cell - units kept / spoken (unit = word or CJK character). 'in scope' = phrases of at least three words / five characters")
print(f"{'cell':20s} | today: live  Stop  saved | candidate: live  Stop  saved | in scope, tab talking (saved) | in scope, tab silent (saved) | 1-2 word replies (saved)")
for cell in m["rows"]:
    if cell["cell"].startswith("listen"):
        continue
    t, c = cell["today"], cell["candidate"]
    print(f"{cell['cell']:20s} | {t['live_solid']['recall']:>11s} {t['saved_at_stop']['recall']:>5s} {t['saved']['recall']:>6s} |"
          f" {c['live_solid']['recall']:>15s} {c['saved_at_stop']['recall']:>5s} {c['saved']['recall']:>6s} |"
          f" {split(cell, 'candidate', 'saved', lambda s, d, x: long_enough(s, d, x) and talking(s, d)):>12s} (today {split(cell, 'today', 'saved', lambda s, d, x: long_enough(s, d, x) and talking(s, d))})"
          f" | {split(cell, 'candidate', 'saved', lambda s, d, x: long_enough(s, d, x) and not talking(s, d)):>8s} (today {split(cell, 'today', 'saved', lambda s, d, x: long_enough(s, d, x) and not talking(s, d))})"
          f" | {split(cell, 'candidate', 'saved', short_reply):>6s} (today {split(cell, 'today', 'saved', short_reply)})")
print("\nG2/G4 - cells with no local speech: microphone units committed live / at Stop / saved, and what each rule counted")
for cell in m["rows"]:
    if cell["cell"].startswith("listen"):
        t, c = cell["today"], cell["candidate"]
        print(f"{cell['cell']:20s} {cell['what']:48s} provider words per call {c['provider_words_per_mic_call']} | today "
              f"{t['live_solid']['extra_units']}/{t['saved_at_stop']['extra_units']}/{t['saved']['extra_units']} | candidate "
              f"{c['live_solid']['extra_units']}/{c['saved_at_stop']['extra_units']}/{c['saved']['extra_units']} | {c['counters']}")
r4 = json.loads((RUNS / "r4-final" / "summary.json").read_text())
print(f"round-4 lanes: {r4['samples']} provider answers, {r4['provider_words_after_voice_gate']} words after the voice-activity gate, "
      f"today {r4['today']} kept, candidate {r4['candidate']} kept; heaviest run on a sustained stretch weighs "
      f"{r4['max_weight_on_unexplained_of_runs_touching_a_sustained_stretch']} (bar 15)")
for path in sorted((RUNS / "r4-final").glob("*-saved.json")):
    d = json.loads(path.read_text())
    print(f"  {path.stem}: {d['provider_words_after_voice_gate']} words, {d['survive_echo_guards']} survive the echo guards "
          f"(longest run {d['longest_surviving_run_s']} s), today saved {d['today_saved']}, candidate saved {d['candidate_saved']}")
live = [json.loads(p.read_text()) for p in sorted((RUNS / "r4-final").glob("*-live-*.json"))]
print(f"  {len(live)} live windows: {sum(d['provider_words_after_voice_gate'] for d in live)} words, "
      f"{sum(d['survive_level_gate'] for d in live)} survive the level gate, anchored today {sum(d['anchored_today'] for d in live)}, "
      f"today published {sum(d['today_published'] for d in live)}, candidate published {sum(d['candidate_published'] for d in live)}")
print("\ncounters, all 18 cells (today -> candidate):")
for key in ("level", "voice", "text", "unanchored", "lane_withheld"):
    print(f"  {key}: {sum(c['today']['counters'][key] for c in m['rows'])} -> {sum(c['candidate']['counters'][key] for c in m['rows'])}")
print("  kept by local voice at the level gate:", sum(c["candidate"]["counters"]["kept_by_local_voice_level"] for c in m["rows"]),
      "| kept unanchored by local voice:", sum(c["candidate"]["counters"]["kept_by_local_voice_unanchored"] for c in m["rows"]))
