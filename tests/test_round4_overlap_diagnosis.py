import json
from pathlib import Path

import pytest

from moss_transcribe_diarize.lane_word_oracle import words


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "round4" / "overlap"


@pytest.mark.xfail(
    strict=True,
    reason="R4-6: the 29 s system reference must match its audited audio population",
)
def test_r4_6_demo_reference_matches_corrected_audio_population() -> None:
    current = json.loads((EVIDENCE / "bill-reference-source.jsonl").read_text())
    proposal = json.loads((EVIDENCE / "reference-correction-proposal.json").read_text())
    corrected = proposal["proposals"]["demo_overlap_29s"]
    assert (current["start"], current["end"], words(current["text"])) == (
        corrected["start"],
        corrected["end"],
        words(corrected["text"]),
    )


@pytest.mark.xfail(
    strict=True,
    reason="R4-6: the ladder reference must not extend beyond its 24 s captured audio",
)
def test_r4_6_ladder_reference_is_bounded_by_captured_audio() -> None:
    current = json.loads((EVIDENCE / "bill-reference-source.jsonl").read_text())
    duration = json.loads((EVIDENCE / "ladder-duration-evidence.json").read_text())
    assert all(current["end"] <= row["meeting_audio_duration_ms"] / 1000 for row in duration["cases"])
