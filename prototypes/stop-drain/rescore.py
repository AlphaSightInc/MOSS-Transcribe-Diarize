"""PROTOTYPE: re-score a retained capacity-campaign run offline. No decoder calls.

One command:
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. <python> prototypes/stop-drain/rescore.py \
      evidence/mvpfix/wp35/real-4x300-after

Why this exists: WP35's real run was measured before the `prestop_inference_projection`
repair that the same change required (a window the Stop stopped awaiting has no inference to
project and every measurement null), so the run's own `result.json` carries
`inference_evidence:rolling completion has a non-healthy terminal outcome` and `clean: false`.
Re-running the campaign to re-score it would cost another ~550 real decoder requests. The
campaign's `clean` predicate is a pure function of what the run already retained, so this
recomputes it from the retained events instead, and prints both the projection and every term
of the predicate so nothing is taken on trust.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.concurrency_evidence import prestop_inference_projection


def main() -> None:
    directory = Path(sys.argv[1])
    result = json.loads((directory / "result.json").read_text())
    rows = result["session_results"]
    events = [event for row in rows for event in row["events"]]
    sessions, seconds = result["sessions"], result["seconds"]
    projection = prestop_inference_projection(
        events, accepted_audio_seconds=seconds * sessions
    )
    # Every term of run.py's `clean`, recomputed from the retained run.
    failures = [
        failure for failure in result["failures"] if not failure.startswith("inference_evidence:")
    ]
    terms = {
        "every_session_clean": all(row.get("clean") for row in rows),
        "session_rows": len(rows) == sessions,
        "no_other_failures": not failures,
        "no_foreign_load": not result["foreign_load_detected"],
        "fairness_passes": result["fairness"].get("passes") is True,
        "rss_growth_within_4gib": result["app_rss_growth_bytes"] <= 4 * 1024 ** 3,
        "prestop_rtf_below_1": projection["rtf"] < 1,
        "refinement_queue_depth_at_most_1": result["maximum_refinement_queue_depth"] <= 1,
        "gpu_cache_at_most_95pc": (
            result["maximum_gpu_cache_use"] is not None
            and result["maximum_gpu_cache_use"] <= .95
        ),
    }
    per_session = []
    for row in sorted(rows, key=lambda item: item["ordinal"]):
        stop_seq = next(
            event["seq"] for event in row["events"] if event["kind"] == "stop_requested"
        )
        after = [event for event in row["events"] if event["seq"] > stop_seq]
        per_session.append({
            "ordinal": row["ordinal"],
            "finalization_status": row["finalization_status"],
            "stop_to_final_seconds": row["stop_to_final_seconds"],
            "accepted_samples": row["accepted_samples"],
            "accounted_samples": row["accounted_samples"],
            "acknowledged_frames": row["acknowledged_frames"],
            "word_count": row["word_count"],
            "rolling_admitted_after_stop": sum(
                1 for event in after
                if event["kind"] == "rolling_decode_queued"
                and event["payload"].get("admitted") is True
            ),
            "rolling_completed_after_stop": [
                event["payload"].get("outcome") for event in after
                if event["kind"] == "rolling_decode_completed"
            ],
            "canonical_processed_after_stop": sum(
                1 for event in after if event["kind"] == "canonical_processed"
            ),
            "terminal_started": any(
                event["kind"] == "terminal_finalization_started" for event in after
            ),
        })
    print(json.dumps({
        "run": str(directory),
        "decoder_calls": result["decoder_calls"],
        "maximum_own_inflight": result["maximum_own_inflight"],
        "foreign_load_detected": result["foreign_load_detected"],
        "prestop_inference": projection,
        "clean_terms": terms,
        "clean_rescored": all(terms.values()),
        "clean_as_run": result["clean"],
        "excluded_failures": [
            failure for failure in result["failures"]
            if failure.startswith("inference_evidence:")
        ],
        "sessions": per_session,
    }, indent=2))


if __name__ == "__main__":
    main()
