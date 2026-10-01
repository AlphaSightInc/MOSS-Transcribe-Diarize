"""One candidate variant across every recorded cell and every round-4 negative sample ($0).   PYTHON f2/variant.py <tag> '<params-json>'"""
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import ledger
tag, params = sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "{}"
a = subprocess.Popen([sys.executable, str(HERE / "matrix.py"), tag, params], stdout=subprocess.PIPE, text=True)
b = subprocess.Popen([sys.executable, str(HERE / "r4_all.py"), params, f"r4-{tag}"], stdout=subprocess.PIPE, text=True)
out_a, out_b = a.communicate()[0], b.communicate()[0]
if a.returncode or b.returncode:
    raise SystemExit(out_a[-3000:] + out_b[-3000:])
m = json.loads((ledger.EV / "runs" / f"matrix-{tag}.json").read_text())
r4 = json.loads((ledger.EV / "runs" / f"r4-{tag}" / "summary.json").read_text())
neg = pos = wrong = 0
print(f"== {tag} {params}")
for row in m["rows"]:
    c, t = row["candidate"], row["today"]
    if row["cell"].startswith("listen"):
        neg += c["live_solid"]["extra_units"] + c["saved_at_stop"]["extra_units"] + c["saved"]["extra_units"]
    bad = sum(c[k]["outside_units"] + c[k]["echo_inside_units"] for k in ("live_solid", "saved_at_stop", "saved"))
    wrong += bad
    worse = [k for k in ("live_solid", "saved_at_stop", "saved")
             if int(c[k]["recall"].split("/")[0]) < int(t[k]["recall"].split("/")[0])]
    print(f"  {row['cell']:20s} today live {t['live_solid']['recall']:>6s} stop {t['saved_at_stop']['recall']:>6s} saved {t['saved']['recall']:>6s}"
          f" | cand live {c['live_solid']['recall']:>6s} stop {c['saved_at_stop']['recall']:>6s} saved {c['saved']['recall']:>6s} "
          f"outside+echo {c['live_solid']['outside_units'] + c['live_solid']['echo_inside_units']}/{c['saved_at_stop']['outside_units'] + c['saved_at_stop']['echo_inside_units']}/{c['saved']['outside_units'] + c['saved']['echo_inside_units']} "
          f"(today {t['live_solid']['outside_units'] + t['live_solid']['echo_inside_units']}/{t['saved_at_stop']['outside_units'] + t['saved_at_stop']['echo_inside_units']}/{t['saved']['outside_units'] + t['saved']['echo_inside_units']}) "
          f"{c['saved']['phrases']} {'WORSE ' + str(worse) if worse else ''}")
print(f"  listen cells: words committed or saved = {neg}; all cells: invented or echoed units (rows outside any phrase + tab words inside a local row) = {wrong}")
tot = lambda who, key: sum(int(row[who][key]["recall"].split("/")[0]) for row in m["rows"])
print(f"  recall totals of {sum(int(row['today']['saved']['recall'].split('/')[1]) for row in m['rows'])} units: today live {tot('today', 'live_solid')} stop {tot('today', 'saved_at_stop')} saved {tot('today', 'saved')} | cand live {tot('candidate', 'live_solid')} stop {tot('candidate', 'saved_at_stop')} saved {tot('candidate', 'saved')}")
print(f"  round-4 samples: {r4['samples']} samples, {r4['provider_words_after_voice_gate']} provider words, today {r4['today']}, candidate {r4['candidate']} "
      f"{[w[1] for w in r4['candidate_words']]}; max weight on sustained {r4['max_weight_on_sustained']}, "
      f"max weight on unexplained (runs touching a sustained stretch) {r4['max_weight_on_unexplained_of_runs_touching_a_sustained_stretch']}")
