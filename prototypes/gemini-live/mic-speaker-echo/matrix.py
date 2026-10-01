"""One line per recorded cell: what the listener would see for each symptom (throwaway, $0).

    PYTHON prototypes/gemini-live/mic-speaker-echo/matrix.py [run ...]     # default: every rp-*-recorded run
Reads each run's files as written in real time (the *-recorded copies), so preview timing is the provider's own.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import ledger  # noqa: E402

RUNS = sys.argv[1:] or sorted(p.name for p in (ledger.EV / "runs").glob("rp-*-recorded")) + ["short-aec40"]
rows = []
for run in RUNS:
    out = subprocess.run([sys.executable, str(HERE / "e2e_analyze.py"), run], capture_output=True, text=True, check=True).stdout
    d = json.loads(out[out.index("{"):out.rindex("\n}") + 2])
    gates_path = ledger.EV / "runs" / run / "gates.jsonl"
    summaries = ([json.loads(line) for line in gates_path.read_text().splitlines()
                  if json.loads(line)["stage"] == "window_summary"] if gates_path.is_file() else [])
    diag = d["diagnostics"]
    rows.append({
        "run": run, "mic_fixture": d["fixtures"][1],
        "S1_seconds_grey_repeats_solid": d["S1_system_preview_vs_solid"]["seconds_with_repeat"],
        "S1_worst_repeated_units": d["S1_system_preview_vs_solid"]["worst"]["system"]["repeat_own_solid"],
        "mic_grey_snapshots": d["mic_preview"]["snapshots_with_mic_grey"],
        "mic_grey_max_units": d["mic_preview"]["max_mic_grey_units"],
        "mic_grey_texts": d["mic_preview"]["distinct_mic_grey_texts"][-6:],
        "mic_rows_live_max": d["mic_rows"]["max_live_mic_rows"],
        "mic_saved_at_stop": d["mic_rows"]["saved_at_stop"], "mic_after_cleanup": d["mic_rows"]["after_cleanup"],
        "gate_level": diag["mic_words_dropped_by_acoustic_gate"], "gate_voice": diag["mic_echo_dropped_by_voice"],
        "gate_text": diag["mic_words_dropped_by_text_guard"], "gate_unanchored": diag["mic_words_dropped_unanchored"],
        "gate_lane_withheld": diag["mic_words_withheld_unanchored_lane"],
        "cleanup_latin_lost": d["S3b_cleanup_vs_live_system"]["latin_runs_lost"],
        "cleanup_latin_gained": d["S3b_cleanup_vs_live_system"]["latin_runs_gained"],
        "provider_words_per_mic_window": [s["after_voice_activity_gate"] for s in summaries]})
(ledger.EV / "runs" / "matrix.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n")
for row in rows:
    print(json.dumps(row, ensure_ascii=False))
