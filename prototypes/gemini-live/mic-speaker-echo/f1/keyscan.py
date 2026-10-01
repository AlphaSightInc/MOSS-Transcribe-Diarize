"""Count-only key scan of this prototype's evidence and code (run through ../with_key.sh; prints counts only)."""
import json
import os
from pathlib import Path

key = os.environ["GEMINI_API_KEY"].encode()
roots = [Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P72/f1", Path(__file__).resolve().parent]
files = [p for root in roots for p in root.rglob("*") if p.is_file()]
hits = [p for p in files if key in p.read_bytes()]
out = {"distinct_values_checked": 1, "files_scanned": len(files), "key_occurrences": sum(p.read_bytes().count(key) for p in hits),
       "files_with_key": len(hits)}
(roots[0] / "keyscan.json").write_text(json.dumps(out) + "\n")
print(json.dumps(out))
