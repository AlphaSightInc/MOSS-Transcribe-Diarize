"""$0: across every saved/committed transcript in the campaign evidence, find isolated tokens whose
script occurs nowhere else in that meeting (the "кве" shape) and list them for classification."""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOTS = [Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence",
         Path.home() / "Documents/Codex/2026-09-23/moss-round6/evidence"]
SKIP = ("a4-operator", "operator-mixed", "dx-replay/real-")  # never read operator material


def script(ch: str) -> str | None:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    head = name.split(" ")[0]
    return {"HIRAGANA": "KANA", "KATAKANA": "KANA", "CJK": "HAN"}.get(head, head)


def texts(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "text" and isinstance(v, str):
                yield v
            else:
                yield from texts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from texts(v)


def main():
    files = scanned = 0
    found = []
    for root in ROOTS:
        for path in root.rglob("*.json"):
            p = str(path)
            if any(s in p for s in SKIP) or path.stat().st_size > 30_000_000:
                continue
            try:
                data = json.loads(path.read_text())
            except Exception:
                continue
            body = list(texts(data))
            if not body:
                continue
            files += 1
            joined = " ".join(body)
            counts = Counter(s for ch in joined if (s := script(ch)))
            scanned += sum(counts.values())
            if len(counts) < 2:
                continue
            for token in set(re.findall(r"\S+", joined)):
                scripts = {script(ch) for ch in token} - {None}
                if len(scripts) != 1:
                    continue
                s = next(iter(scripts))
                letters = sum(1 for ch in token if script(ch) == s)
                occurrences = joined.count(token)
                if counts[s] == letters * occurrences:  # this token is the script's only appearance
                    i = joined.index(token)
                    found.append({"file": p.split("evidence/")[-1], "token": token, "script": s,
                                  "occurrences": occurrences, "dominant": counts.most_common(1)[0][0],
                                  "context": joined[max(0, i - 30):i + len(token) + 30]})
    print(json.dumps({"files_with_text": files, "letters": scanned, "unique_script_tokens": len(found)}))
    for f in found:
        print(json.dumps(f, ensure_ascii=False))


if __name__ == "__main__":
    main()
