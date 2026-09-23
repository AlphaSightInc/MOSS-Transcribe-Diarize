"""Throwaway D46 evidence sufficiency probe; prints counts only."""
import json
from pathlib import Path

from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.app.live_transcript_convergence import (
    ROLLING_STRIDE_SECONDS,
    ROLLING_WINDOW_SECONDS,
)


ROOT = Path(
    "/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/"
    "r6-h1-20260923T051306Z/20260923T051605Z-f7fe4ad/raw"
)
WINDOW = int(LIVE_SAMPLE_RATE * ROLLING_WINDOW_SECONDS)
STRIDE = int(LIVE_SAMPLE_RATE * ROLLING_STRIDE_SECONDS)


def main() -> None:
    for layer in ("deployed", "pre_admission"):
        report = json.loads((ROOT / f"{layer}-observations.json").read_text())
        quality = next(row["raw"] for row in report["predicates"] if row["id"] == "quality_corpus")
        totals = {"planned": 0, "rolling": 0, "terminal_range_proved": 0}
        for case in quality["per_case"]:
            accepted = case["surface_observations"]["post_stop_final"]["accepted_samples"]
            planned = len(range(0, accepted - WINDOW + 1, STRIDE))
            path = ROOT / f"{layer}-collector/artifacts/quality/pass-{case['pass']}/{case['case_id']}/terminal-diagnostics.json"
            diag = json.loads(path.read_text())
            completed = [e for e in diag["events"] if e["kind"] == "rolling_decode_completed"]
            terminal_revision = [e for e in diag["events"] if e["kind"] == "text_revision_applied" and e.get("source") == "terminal"]
            terminal_complete = [e for e in diag["events"] if e["kind"] == "terminal_finalization_completed"]
            totals["planned"] += planned
            totals["rolling"] += len(completed)
            totals["terminal_range_proved"] += bool(terminal_revision and terminal_complete)
            print(json.dumps({"layer": layer, "case": case["case_id"], "pass": case["pass"], "accepted": accepted, "planned": planned, "rolling": len(completed), "terminal_revision_events": len(terminal_revision), "terminal_completion_events": len(terminal_complete)}, sort_keys=True))
        print(json.dumps({"layer": layer, **totals}, sort_keys=True))


if __name__ == "__main__":
    main()
