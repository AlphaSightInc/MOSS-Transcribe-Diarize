"""All round-4 negative samples through today's gate and the candidate, $0 (recorded answers).

    PYTHON f2/r4_all.py [params-json] [out-folder-name]
"""
import json, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import ledger
JOBS = [["terminal", "r4:A-listen-sp", "r4:B-listen-sp"],
        ["windows", "r4:B-listen-sp", "30,60,90,120,150,180,210,240,270,300"],
        ["windows", "r4:B-sp", "105,135,165,225,305,365,395,425"],
        ["windows", "r4:A-sp", "105,135,165,225,305,365,395,425"]]
OUT = sys.argv[2] if len(sys.argv) > 2 else "r4"
extra = (["--params", sys.argv[1]] if len(sys.argv) > 1 else []) + ["--out", OUT]
procs = [subprocess.Popen([sys.executable, str(HERE / "r4_chain.py"), *job, *extra], stdout=subprocess.PIPE, text=True) for job in JOBS]
rows = []
for proc in procs:
    out, _ = proc.communicate()
    if proc.returncode:
        raise SystemExit(out[-2000:])
folder = ledger.EV / "runs" / OUT
total = {"samples": 0, "provider_words_after_voice_gate": 0, "today": 0, "candidate": 0, "candidate_words": []}
runs = []
for path in sorted(folder.glob("*.json")):
    if path.name == "summary.json":
        continue
    row = json.loads(path.read_text())
    total["samples"] += 1
    total["provider_words_after_voice_gate"] += row["provider_words_after_voice_gate"]
    total["today"] += row.get("today_saved", row.get("today_published", 0))
    kept = row.get("candidate_saved_words", row.get("candidate_published_words", []))
    total["candidate"] += len(kept)
    total["candidate_words"] += [[path.stem] + w for w in kept]
    runs += [dict(run, sample=path.stem) for run in row["runs_on_unexplained_audio"]]
total["runs_touching_unexplained_audio"] = len(runs)
total["max_weight_on_sustained"] = max((r["weight_on_sustained"] for r in runs), default=0)
total["max_weight_on_unexplained_of_runs_touching_a_sustained_stretch"] = max(
    (r["weight_on_unexplained"] for r in runs if r["weight_on_sustained"] > 0), default=0)
total["top_runs"] = sorted(runs, key=lambda r: (-r["weight_on_sustained"], -r["weight_on_unexplained"]))[:8]
(folder / "summary.json").write_text(json.dumps(total, ensure_ascii=False, indent=1) + "\n")
print(json.dumps(total, ensure_ascii=False, indent=1))
