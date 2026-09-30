"""Re-score both fixtures through the *current* production MicrophoneWordGate (rule built in)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import chain  # noqa: E402

FIXTURES = {"fixture": ["en-hp", "en-sp"], "fixture2": ["A-hp", "A-sp", "B-hp", "B-sp"]}


def main():
    rows = []
    for fixture, names in FIXTURES.items():
        chain.FIX = HERE / "out" / fixture
        for name in names:
            v = chain.Variant(name)
            gate, sysw = v.gate()
            for path in ("rolling", "terminal"):
                s = v.score(v.rolling(gate) if path == "rolling" else v.terminal(gate, sysw))
                rows.append({"variant": name, "path": path, "nonbc": s["retained"] - s["backchannel_units_kept"],
                             "nonbc_ref": s["reference"] - s["backchannel_units"], "bc": s["backchannel_units_kept"],
                             "bc_ref": s["backchannel_units"], "stray": s["stray_words"],
                             "unanchored_dropped": v.drops.get("unanchored_window_dropped_words", 0)})
                print(json.dumps(rows[-1]), flush=True)
    (HERE / "out" / "verify-product.json").write_text(json.dumps(rows, indent=1))


if __name__ == "__main__":
    main()
