"""G5 ($0): the grey microphone row, today and with the same evidence as a row-level test (throwaway).

    PYTHON f2/g5_preview.py
Replays R5-D's recorded instant-word streams (9 cells). For every snapshot that shows a grey microphone row it asks
the candidate's own question, causally (audio up to that moment, last 30 s as context): does the microphone lane hold
a sustained stretch of unexplained voiced audio inside the row's time span? A row with none would be hidden.
Reports grey microphone snapshots before/after, and for real phrases the delay of their first grey display.
The candidate does NOT include this; it is measured as a possible follow-up.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[3]), str(HERE)]
import candidate  # noqa: E402
import cells  # noqa: E402
import evidence  # noqa: E402
import fixtures  # noqa: E402
import ledger  # noqa: E402
import matrix  # noqa: E402

S, PREFIX = 16000, 3.0


def lanes(mic_wav):
    tab = sf.read(str(fixtures.D_FIX / "sys-zhlatin-en.wav"), dtype="int16")[0]
    mic = sf.read(str(mic_wav), dtype="int16")[0]
    lead = int(PREFIX * S)
    floor = (np.random.default_rng(7).normal(0, 10 ** (-63 / 20), lead) * 32767).astype(np.int16)
    return np.concatenate([floor, mic]), np.concatenate([np.zeros(lead, dtype=np.int16), tab])


def main():
    p = candidate.PARAMS
    out = []
    for name, mic_wav, _answers, what in matrix.R5D:
        mic, tab = lanes(mic_wav)
        truth = cells.truth_of(str(mic_wav))
        snaps = [json.loads(line) for line in (ledger.EV / "runs" / f"base/{name}" / "snapshots.jsonl").read_text().splitlines()]
        before = after = 0
        first_before, first_after = {}, {}
        hidden_texts, kept_texts = set(), set()
        for snap in snaps:
            rows = [seg for seg in (snap["provisional"] or {}).get("segments", []) if seg["source_lane"] == "microphone"]
            if not rows or snap["status"] != "active":
                continue
            now = int((snap["e"] + PREFIX) * S)
            lo = max(0, now - p["context_s"] * S)
            facts = evidence.Facts(mic[lo:now], tab[lo:now], vad_mode=p["vad_mode"])
            flags = evidence.unexplained(facts, evidence.echo_return_db(facts, p["quantile"]), p["margin_db"])
            stretches = [(lo + a * evidence.FRAME, lo + b * evidence.FRAME)
                         for a, b in candidate.stretches_of(flags, p["gap_frames"], p["min_frames"])]
            shown = [row for row in rows if any(a < row["end_sample"] and b > row["start_sample"] for a, b in stretches)]
            before += 1
            after += bool(shown)
            hidden_texts.update(row["text"] for row in rows if row not in shown)
            kept_texts.update(row["text"] for row in shown)
            for index, phrase in enumerate(truth):
                want = cells.units(phrase["text"])
                for group, first in ((rows, first_before), (shown, first_after)):
                    heard = [u for row in group for u in cells.units(row["text"])]
                    if index not in first and cells.lcs(want, heard) >= max(2, len(want) // 2) \
                            and snap["e"] >= phrase["start"]:
                        first[index] = snap["e"]
        delays = [round(first_after[i] - first_before[i], 2) for i in first_before if i in first_after]
        row = {"cell": name, "what": what, "grey_microphone_snapshots_today": before, "with_evidence_test": after,
               "phrases_first_shown_grey_today": len(first_before), "with_evidence": len(first_after),
               "added_delay_s": delays, "hidden_examples": sorted(hidden_texts)[:4], "kept_examples": sorted(kept_texts)[:4]}
        out.append(row)
        print(json.dumps(row, ensure_ascii=False))
    (ledger.EV / "runs" / "g5-preview.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")


main()
