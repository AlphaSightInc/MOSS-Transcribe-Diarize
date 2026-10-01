"""$0: the UI-observed mic preview rows of the P69 Mandarin run through the product script rule."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT)]
from moss_transcribe_diarize.app.gemini_lane_engine import (_script_runs, _sustained_scripts,  # noqa: E402
                                                            _without_foreign_script)
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiSegment  # noqa: E402

RUN = Path.home() / "Documents/Codex/2026-09-28/moss-gemini/evidence/P69/r4-ui-e2e/runs"


def main():
    for run in "abc":
        states = [json.loads(line) for line in (RUN / run / "states.jsonl").open()]
        saved = json.loads((RUN / run / "saved-meeting.json").read_text())
        segments = (saved.get("transcript") or {}).get("segments") or []
        meeting = {s for seg in segments if seg.get("source_lane") == "system" for s in _sustained_scripts(seg["text"])}
        established = set()
        before, after, changed = Counter(), Counter(), Counter()
        for state in states:
            rows = state.get("micRows")
            if not isinstance(rows, list):
                continue
            # the far end's preview is not in the UI capture: its saved scripts stand in for it
            established |= meeting
            for row in rows:
                established |= _sustained_scripts(row["text"])
            for row in rows:
                kept = _without_foreign_script(GeminiSegment(0, 1, row["text"], None, "microphone"), established)
                for script, _, a, b in _script_runs(row["text"]):
                    before[script] += 1
                for script, _, a, b in _script_runs(kept.text if kept else ""):
                    after[script] += 1
                if kept is None or kept.text != row["text"]:
                    changed[(row["text"], kept.text if kept else None)] += 1
        print(run, "script runs shown before", dict(before), "after", dict(after))
        for (a, b), n in changed.most_common(12):
            print(f"   x{n} {a!r} -> {b!r}")


if __name__ == "__main__":
    main()
