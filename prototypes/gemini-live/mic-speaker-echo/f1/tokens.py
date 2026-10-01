"""R5-F1 G2 ($0): are the lane composer's units exactly today's trim tokens on text without CJK?  (throwaway)

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/tokens.py

Every distinct recorded instant-word update string under P52 (the round-2/3 W3 recordings, 92 files) and
R5-D's nine W3 recordings: today's tokens (`_PREVIEW_WORD` over the casefolded string, number words as
digits, with their spans) against `_preview_units` (units and spans). If they are identical for a
string, the unit-based rule computes the same cut at the same character for that string.
"""
import json
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import trim as arms  # noqa: E402
from trim import runtime, _preview_units  # noqa: E402

EVID = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence"


def texts_of(value, out):
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "text" and isinstance(item, str):
                out.add(item)
            else:
                texts_of(item, out)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, list) and item and isinstance(item[0], str) and len(item) == 4:
                out.add(item[0])
            else:
                texts_of(item, out)


strings: set = set()
files = 0
for path in sorted((EVID / "P52").glob("*.json")) + sorted((EVID / "P72/mic-speaker-echo/provider-responses").glob("*-w3.json")):
    try:
        data = json.loads(path.read_text())
    except Exception:
        continue
    before = len(strings)
    texts_of(data, strings)
    files += len(strings) > before
cjk = lambda text: any(unicodedata.name(ch, "").startswith(arms._CJK) for ch in text)  # noqa: E731
plain = [s for s in strings if not cjk(s)]
words = differ = 0
examples = []
for text in plain:
    today = [(runtime._PREVIEW_NUMBERS.get(m.group(), m.group()), m.start(), m.end())
             for m in runtime._PREVIEW_WORD.finditer(text.casefold())]
    units = _preview_units(text)
    words += len(units)
    if today != units:
        differ += 1
        if len(examples) < 8:
            at = next((i for i, (a, b) in enumerate(zip(today, units)) if a != b), min(len(today), len(units)))
            examples.append({"text": text[:80], "today": today[at:at + 2], "units": units[at:at + 2],
                             "casefold_changes_length": len(text.casefold()) != len(text)})
out = {"files_with_strings": files, "distinct_strings": len(strings), "strings_without_cjk": len(plain),
       "strings_with_cjk": len(strings) - len(plain), "units_in_strings_without_cjk": words,
       "strings_where_units_differ_from_todays_tokens": differ, "examples": examples}
print(json.dumps(out, ensure_ascii=False, indent=1))
(EVID / "P72/f1/tokens.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
