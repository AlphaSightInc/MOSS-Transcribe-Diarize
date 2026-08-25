#!/usr/bin/env python3
"""Reproduce whether the HTTP replay adapter preserves retrospective revisions."""

from __future__ import annotations

import json

from moss_transcribe_diarize.live_service_replay import _live_snapshot_from_dict


def main() -> None:
    payload = {
        "status": "closed",
        "epoch": 0,
        "version": 9,
        "accepted_samples": 40000,
        "accounted_samples": 40000,
        "retained_samples": 0,
        "committed_samples": 40000,
        "committed_prefix_hash": "prefix",
        "identity_snapshot": {
            "version": 2,
            "canonical_speakers": ["speaker-0001", "speaker-0002"],
            "diagnostics": [],
        },
        "committed": [
            {
                "span_id": 0,
                "start_sample": 0,
                "end_sample": 40000,
                "transcript": "[0][S00]hello[2.5]",
                "revised_transcript": "[0][S01]hello[2.5]",
                "prefix_hash": "commit",
                "identity_snapshot_version": 2,
            }
        ],
        "provisional": None,
        "next_frame_sequence": 1,
        "frozen_until_sample": 40000,
        "pending_span_ids": [],
        "failure_reason": None,
        "label_revision_version": 7,
    }

    decoded = _live_snapshot_from_dict(payload)
    result = {
        "question": "Does the shipped HTTP replay adapter preserve retrospective identity revisions?",
        "input": {
            "label_revision_version": payload["label_revision_version"],
            "revised_transcript": payload["committed"][0]["revised_transcript"],
        },
        "decoded": {
            "label_revision_version": decoded.label_revision_version,
            "revised_transcript": decoded.committed[0].revised_transcript,
        },
    }
    result["revision_preserved"] = result["input"] == result["decoded"]
    print(json.dumps(result, indent=2, sort_keys=True))
    raise SystemExit(0 if result["revision_preserved"] else 1)


if __name__ == "__main__":
    main()
