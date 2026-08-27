#!/usr/bin/env python3
"""Replay retained Jamie windows 0-4 through production rolling/session classes.

One command:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
    prototypes/streaming-diarization/live-policy-sweep-20260825/verify_jamie_rolling_recovery.py \
    --sweep evidence/live-policy-sweep-20260825 \
    --output evidence/live-g4-recovery-20260825/jamie-production-class-probe.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_adapters import InferenceTranscript  # noqa: E402
from moss_transcribe_diarize.app.live_session import (  # noqa: E402
    AudioFrame,
    CanonicalResult,
    LiveSession,
)
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.live_transcript_convergence import (  # noqa: E402
    DEFAULT_ROLLING_GEOMETRY,
    RollingTranscriptConverger,
)

WINDOW = DEFAULT_ROLLING_GEOMETRY.window_samples
JAMIE_HASH = "e68a87f5e05d3b001ed352bc775cc6ec4d3acd4f09603fc180459d69aef1b070"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    sweep = args.sweep.resolve()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit(f"refusing to overwrite {output}")

    cache = json.loads(
        (sweep / "moss" / "shadow-cache" / "pass-A.json").read_text(encoding="utf-8")
    )["entries"]
    retained: dict[int, dict[str, Any]] = {}
    for key, value in cache.items():
        parts = key.split(":")
        if len(parts) != 6 or parts[0] != JAMIE_HASH:
            continue
        start, end, token_cap = int(parts[1]), int(parts[2]), int(parts[4])
        if end - start == WINDOW and token_cap == 938 and start < 5 * WINDOW:
            retained[start // WINDOW] = value
    if sorted(retained) != list(range(5)):
        raise RuntimeError(f"retained Jamie windows 0-4 missing: {sorted(retained)}")

    session = LiveSession(max_retained_samples=6 * WINDOW)
    session.accept_frame(
        AudioFrame(sequence=0, pcm=b"\0" * (12 * WINDOW), sample_count=6 * WINDOW)
    )
    frozen = session.freeze_until(6 * WINDOW, reason="retained_jamie_production_probe")
    if not session.submit_canonical(
        CanonicalResult(
            span_id=frozen.id,
            epoch=frozen.epoch,
            start_sample=0,
            end_sample=6 * WINDOW,
            transcript="[0][S01]prototype base[60]",
        )
    ):
        raise RuntimeError("probe base did not commit")

    converger = RollingTranscriptConverger(epoch=0)
    records = []
    following = ()
    for window_index in range(5):
        accepted = converger.accounting().accepted_samples
        converger.accept_pcm(accepted, b"\0" * (2 * WINDOW))
        request = converger.observe_base(session.snapshot())[0]
        if window_index == 4:
            converger.accept_pcm(5 * WINDOW, b"\0" * (2 * WINDOW))
        cached = retained[window_index]
        raw_words = sum(
            len(row.text.split())
            for row in span_segments(cached["transcript"], sample_count=WINDOW)
        )
        proposal = converger.complete(
            request.id,
            InferenceTranscript(
                transcript=cached["transcript"],
                elapsed_sec=cached["elapsed_seconds"],
                token_cap=cached["token_cap"],
                capped=cached["capped"],
                generated_tokens=cached["generated_tokens"],
            ),
        )
        if proposal is None:
            raise RuntimeError(f"window {window_index} produced no proposal")
        outcome = session.apply_text_revision(proposal)
        records.append(
            {
                "window_index": window_index,
                "interval": [request.start_sample, request.end_sample],
                "raw_words": raw_words,
                "published_words": len(" ".join(row.text for row in proposal.segments).split()),
                "merged": proposal.normalization_merged_segments,
                "dropped": proposal.normalization_dropped_segments,
                "displaced_samples": proposal.normalization_displaced_samples,
                "applied": outcome.applied,
                "refusal": outcome.refusal,
                "canonical_through_sample": outcome.canonical_through_sample,
            }
        )
    following = converger.observe_base(session.snapshot())

    window_4 = records[4]
    gates = {
        "windows_0_4_applied": len(records) == 5 and all(row["applied"] for row in records),
        "window_4_displaced_2720": window_4["displaced_samples"] == 2720,
        "window_4_words_24_of_24": (
            window_4["raw_words"] == window_4["published_words"] == 24
        ),
        "window_4_zero_merge_drop": window_4["merged"] == window_4["dropped"] == 0,
        "window_5_queued": (
            len(following) == 1
            and following[0].window_index == 5
            and following[0].start_sample == 5 * WINDOW
            and following[0].end_sample == 6 * WINDOW
        ),
    }
    report = {
        "schema": "moss-g4-jamie-production-class-probe.v1",
        "source_cache": str(sweep / "moss" / "shadow-cache" / "pass-A.json"),
        "records": records,
        "next_window": (
            None
            if not following
            else {
                "window_index": following[0].window_index,
                "start_sample": following[0].start_sample,
                "end_sample": following[0].end_sample,
            }
        ),
        "accounting": {
            "status": converger.accounting().status.value,
            "windows_planned": converger.accounting().windows_planned,
            "windows_completed": converger.accounting().windows_completed,
            "windows_failed": converger.accounting().windows_failed,
            "proposal_refusals": converger.accounting().proposal_refusals,
            "retained_samples": converger.accounting().retained_samples,
        },
        "gates": gates,
        "verdict": "PASS" if all(gates.values()) else "FAIL",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
