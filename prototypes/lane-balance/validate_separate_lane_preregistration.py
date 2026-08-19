#!/usr/bin/env python3
"""Validate and print the sealed separate-lane decode/merge contract."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).parent
REPO = ROOT.parents[1]
CONTRACT = ROOT / "preregistration-separate-lane-v1.json"
sys.path.insert(0, str(ROOT))
from proto_lane_balance_v3 import sha256  # noqa: E402
from proto_separate_lane_decode import merge_lane_transcripts  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402


def main() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema"] == "moss-separate-lane-decode-preregistration.v1"
    v3_path = REPO / contract["trigger"]["lane_balance_v3_result"]
    assert sha256(v3_path) == contract["trigger"]["sha256"]
    v3 = json.loads(v3_path.read_text(encoding="utf-8"))
    assert v3["selection"]["verdict"] == contract["trigger"]["verdict"]
    assert contract["decode_policy"]["concurrency"] == "serial"
    assert contract["decode_policy"]["request_order"] == ["shared", "microphone"]
    assert "do not invent" in contract["decision_rule"]["latency_load_rule"]

    shared = "[0][S02]shared first[1.5][2][S01]shared second[3]"
    microphone = "[1][S01]mic overlap[2.5][3.5][S02]mic tail[4]"
    merged, state = merge_lane_transcripts(shared, microphone)
    assert state["all_segments_preserved"]
    assert state["parse_roundtrip_equal"]
    assert state["namespace_collision_free"]
    assert state["speaker_capacity_passes"]
    assert state["cross_lane_overlap_pair_count"] == 2
    assert state["cross_lane_overlap_seconds_sum"] == 1.0
    assert [segment.speaker for segment in parse_transcript(merged)] == [
        "S02", "S03", "S01", "S04"
    ]
    print(json.dumps({
        "contract_path": str(CONTRACT.relative_to(REPO)),
        "contract_sha256": sha256(CONTRACT),
        "bound_v3_result": {
            "path": str(v3_path.relative_to(REPO)),
            "sha256": sha256(v3_path),
            "verdict": v3["selection"]["verdict"],
        },
        "merge_self_check": {"merged": merged, **state},
        "contract": contract,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
