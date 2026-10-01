"""A 28 s local turn that fills the meeting while the tab talks, 20 dB under it ($0 replay; throwaway).

    PYTHON f2/vlong.py
The reference text of this cut is not known word for word, so it is scored as provider words kept / returned
inside the turn, per gate call, and as microphone words on the page before Stop, at Stop and after clean-up.
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import cells, fixtures, ledger

mic = fixtures.d_cell("vlong", -40.0, -37.0)
kw = dict(answers="f2-vlong-e40-L37", w3="none", w3_system_from="rp-short-aec40")
cells.run("base/vlong-e40-L37", mic, **kw)
cells.run("final/vlong-e40-L37", mic, candidate={}, **kw)
out = {}
for tag in ("base", "final"):
    folder = ledger.EV / "runs" / f"{tag}/vlong-e40-L37"
    calls = []
    for line in (folder / "gates.jsonl").read_text().splitlines():
        g = json.loads(line)
        if g["stage"] in ("mic_window", "mic_cleanup"):
            inside = lambda words: [w for w in words if 5.5 <= w[2] <= 34.5]
            calls.append({"call": g["stage"], "seconds": g["seconds"], "provider_words_in_turn": len(inside(g["given"])),
                          "kept": len(inside(g["kept"])), "kept_outside_turn": len(g["kept"]) - len(inside(g["kept"]))})
    snaps = [json.loads(l) for l in (folder / "snapshots.jsonl").read_text().splitlines()]
    page = {note: sum(len(r["text"].split()) for r in next(s for s in snaps if s["note"] == note)["effective"]
                      if r.get("source_lane") == "microphone")
            for note in ("before Stop", "completed (live transcript saved)", "settled")}
    out["today" if tag == "base" else "candidate"] = {"gate_calls": calls, "microphone_words_on_page": page}
    print("today" if tag == "base" else "candidate", json.dumps(out["today" if tag == "base" else "candidate"]))
(ledger.EV / "runs" / "vlong.json").write_text(json.dumps(out, indent=1) + "\n")
