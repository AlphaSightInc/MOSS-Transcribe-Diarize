"""Does the provider give the same answer for the same request bytes? (one paid 15 s call; throwaway)

    with_key.sh PY f3/s4_determinism.py [--pay]
Decides whether the existing coverage retry (send the same chunk again) can ever return something new.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import f3lib  # noqa: E402
from f3lib import EV, RD_FIX, RD_RAW, S, tup  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import WindowDiarizer  # noqa: E402

pcm = f3lib.read_pcm(RD_FIX / "sys-zhlatin-en.wav", 1.5)[:15 * S * 2]
client = f3lib.Client("same-bytes", pay="--pay" in sys.argv)
diarizer = WindowDiarizer(client, lambda **_row: None)
first = diarizer.diarize(pcm, deadline=time.monotonic() + 120, kind="rolling", diarize=True).words
second = diarizer.diarize(pcm, deadline=time.monotonic() + 120, kind="rolling", diarize=True).words
pairs = [("15 s window, leading silence 1.5 s (new)", [tup(w) for w in first] == [tup(w) for w in second])]
for a, b in (("rp-short-aec40-6679896967d9d87e-0.json", "zhlatin-en-terminal-p3-r0-6679896967d9d87e-0.json"),
             ("zhlatin-en-terminal-8aa5ab7d6eb3a1ae-0.json", "zhlatin-en-terminal-p0-r0-8aa5ab7d6eb3a1ae-0.json")):
    wa, wb = f3lib.response_words(RD_RAW / a)[0], f3lib.response_words(RD_RAW / b)[0]
    ids = [json.loads((RD_RAW / f).read_text())["response"]["id"] for f in (a, b)]
    pairs.append((f"R5-D {a[:24]} vs {b[:28]} (two calls: ids differ {ids[0] != ids[1]})",
                  [tup(w) for w in wa] == [tup(w) for w in wb]))
out = {"pairs_of_calls_with_identical_request_bytes": len(pairs),
       "pairs_with_identical_words_times_and_labels": sum(same for _, same in pairs),
       "detail": pairs, "calls": client.calls}
(EV / "runs" / "same-bytes.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
