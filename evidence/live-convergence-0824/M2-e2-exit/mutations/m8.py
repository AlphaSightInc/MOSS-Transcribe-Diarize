import sys
from pathlib import Path
path = Path(sys.argv[1]) / "trio-B/lex_keyu_jin/file-hypothesis.jsonl"
text = path.read_text()
path.write_text(text.replace("\n", "\n", 1) + '{"start": 59.0, "end": 59.5, "speaker": "S01", "text": "extra"}\n')
