import sys
from pathlib import Path
path = Path(sys.argv[1]) / "trio-A/lex_keyu_jin/live-hypothesis.jsonl"
rows = [line for line in path.read_text().splitlines() if line.strip()]
path.write_text("\n".join(rows[: len(rows) // 2]) + "\n")
