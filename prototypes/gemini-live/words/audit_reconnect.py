"""Compare long Live text near each rotation with retained-audio batch words."""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "common"))
from corpus import clips  # noqa: E402
from gemini_common import diarize_window, read_wav  # noqa: E402

EVIDENCE = Path("/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P52")


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:'[a-z0-9]+)?", text.lower())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stream", default="w3-long-replay2.json")
    p.add_argument("--output", default="w3-long-boundary-audit.json")
    args = p.parse_args()
    stream = json.loads((EVIDENCE / args.stream).read_text())
    clip = next(c for c in clips() if c.clip_id == stream["clip"])
    pcm = read_wav(clip.audio)
    rows = []
    for reconnect in stream["reconnects"]:
        boundary = reconnect["at_audio_s"]
        start = round(boundary) - 15
        end = round(boundary) + 15
        result = diarize_window(pcm[start * 16000:end * 16000],
                                diarize=False, ledger_lane="P52", use_cache=True)
        batch = []
        for word in result.words:
            for token in tokens(word.text):
                batch.append({"text": token, "audio_s": start + (word.start + word.end) / 2,
                              "start_s": start + word.start, "end_s": start + word.end})
        nearby = [x for x in stream["hypothesis"]
                  if x["end"] >= boundary - 30 and x["start"] <= boundary + 30]
        live = tokens(" ".join(x["text"] for x in nearby))
        matcher = difflib.SequenceMatcher(a=[x["text"] for x in batch], b=live, autojunk=False)
        matched = {block.a + i for block in matcher.get_matching_blocks() for i in range(block.size)}
        focus = [i for i, w in enumerate(batch) if abs(w["audio_s"] - boundary) <= 5]
        missing = [batch[i] for i in focus if i not in matched]
        missing_indices = [i for i in focus if i not in matched]
        missing_runs = []
        for i in missing_indices:
            if missing_runs and missing_runs[-1]["last_index"] == i - 1:
                missing_runs[-1]["last_index"] = i
                missing_runs[-1]["end_s"] = batch[i]["end_s"]
                missing_runs[-1]["text"] += " " + batch[i]["text"]
            else:
                missing_runs.append({"first_index": i, "last_index": i,
                                     "start_s": batch[i]["start_s"],
                                     "end_s": batch[i]["end_s"], "text": batch[i]["text"]})
        for run in missing_runs:
            run["duration_s"] = round(run["end_s"] - run["start_s"], 3)
        repeated_final = []
        for left, right in zip(nearby, nearby[1:]):
            a, b = tokens(left["text"]), tokens(right["text"])
            overlap = max((n for n in range(1, min(len(a), len(b)) + 1)
                           if a[-n:] == b[:n]), default=0)
            if overlap and (left["end"] >= boundary - 10 or right["start"] <= boundary + 10):
                repeated_final.append({"words": overlap, "text": " ".join(b[:overlap])})
        rows.append({"reconnect_audio_s": boundary, "batch_window_s": [start, end],
                     "batch_words": len(batch), "focus_batch_words": len(focus),
                     "batch_text": result.text,
                     "batch_focus_text": " ".join(batch[i]["text"] for i in focus),
                     "live_nearby_final_text": " ".join(x["text"] for x in nearby),
                     "focus_matched_words": len(focus) - len(missing),
                     "focus_missing_batch_words": missing,
                     "focus_missing_runs": missing_runs,
                     "adjacent_final_repeated_phrases": repeated_final,
                     "batch_call_s": result.latency_s,
                     "batch_call_cached": result.cached,
                     "batch_cost_usd": result.cost_usd(),
                     "batch_timing_anomalies": result.timing_anomalies})
    out = EVIDENCE / args.output
    out.write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
