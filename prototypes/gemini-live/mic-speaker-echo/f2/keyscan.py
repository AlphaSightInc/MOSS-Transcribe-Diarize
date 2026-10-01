"""Count-only key scan of the R5-F2 evidence folder and prototype folder.

    prototypes/gemini-live/mic-speaker-echo/with_key.sh PYTHON f2/keyscan.py
The key is read from the process environment only and is never printed, copied or written; the output is counts.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import ledger

key = os.environ.get("GEMINI_API_KEY", "").encode()
if len(key) < 8:
    raise SystemExit("no key in the environment")
files = hits = with_key = 0
for root in (ledger.EV, HERE):
    for path in root.rglob("*"):
        if path.is_file() and path.name != "keyscan.json":
            files += 1
            count = path.read_bytes().count(key)
            hits += count
            with_key += bool(count)
out = {"distinct_values_checked": 1, "files_scanned": files, "key_occurrences": hits, "files_with_key": with_key}
(ledger.EV / "keyscan.json").write_text(json.dumps(out) + "\n")
print(json.dumps(out))
