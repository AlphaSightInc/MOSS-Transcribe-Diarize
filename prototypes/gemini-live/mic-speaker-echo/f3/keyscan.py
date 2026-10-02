"""Count-only scan for the provider key in the F3 evidence folder and prototype folder (never prints the key).

    with_key.sh PY f3/keyscan.py
"""
import json
import os
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parent)]
from f3lib import EV  # noqa: E402

key = os.environ.get("GEMINI_API_KEY") or ""
assert len(key) > 20, "key not in the environment"
needle = key.encode()
files = hits = with_key = 0
for root in (EV, Path(__file__).resolve().parent):
    for path in root.rglob("*"):
        if path.is_file():
            files += 1
            count = path.read_bytes().count(needle)
            hits += count
            with_key += bool(count)
out = {"distinct_values_checked": 1, "files_scanned": files, "key_occurrences": hits, "files_with_key": with_key}
(EV / "keyscan.json").write_text(json.dumps(out) + "\n")
print(json.dumps(out))
