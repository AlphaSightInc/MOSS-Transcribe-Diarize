"""Paid once (ledger first): the cells R5-D did not record, through the unpatched product engine (throwaway).

    PYTHON f2/record_cells.py            # replays at $0 once the answers exist
Batch answers only; the tab lane's requests and instant words are R5-D's recorded ones (same tab audio); the
microphone lane has no instant-word stream in these cells.
"""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import cells, fixtures, ledger

NEW = [("dlong", -40.0, -37.0, None), ("short", -40.0, -37.0, None), ("zhshort", -40.0, -37.0, None),
       ("varied-en", -40.0, -27.0, None), ("varied-zh", -40.0, -27.0, None), ("mixed", -40.0, -27.0, None),
       ("short", -15.0, -27.0, None), ("listen", -15.0, -27.0, None), ("listen", -40.0, -27.0, 3)]


def main():
    for kind, echo, level, seed in NEW:
        mic = fixtures.d_cell(kind, echo, level, seed)
        name = mic.stem[4:]
        result = cells.run(f"base/{name}", mic, answers=f"f2-{name}", record=True, w3="none",
                           w3_system_from="rp-short-aec40", key=True)
        print(json.dumps(result), flush=True)
        print(cells.line(cells.score(f"base/{name}")), flush=True)
    print(json.dumps(ledger.summary()))


main()
