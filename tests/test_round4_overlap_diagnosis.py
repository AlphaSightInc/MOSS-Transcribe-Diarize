import json
from pathlib import Path

from moss_transcribe_diarize.lane_word_oracle import distance, words
from tests.e2e.verify_demo_lanes import SYSTEM_LADDER_REFERENCE, reference_inputs


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "round4" / "overlap"


def test_r4_6_demo_reference_matches_corrected_audio_population() -> None:
    current = json.loads(
        (ROOT / "evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/reference.jsonl")
        .read_text()
        .splitlines()[0]
    )
    proposal = json.loads((EVIDENCE / "reference-correction-proposal.json").read_text())
    corrected = proposal["proposals"]["full_corpus_first_record"]
    assert (current["start"], current["end"], words(current["text"])) == (
        corrected["start"],
        corrected["end"],
        words(corrected["text"]),
    )


def test_r4_6_corrected_full_reference_rows_do_not_overlap() -> None:
    rows = [
        json.loads(line)
        for line in (
            ROOT / "evidence/live-policy-sweep-20260825/corpus/interview_bill_ackman_60s/reference.jsonl"
        )
        .read_text()
        .splitlines()
    ]
    assert all(previous["end"] <= current["start"] for previous, current in zip(rows, rows[1:]))


def test_r4_6_ladder_reference_is_bounded_by_captured_audio() -> None:
    current = reference_inputs(1, system_reference=SYSTEM_LADDER_REFERENCE)["system"]
    proposal = json.loads((EVIDENCE / "reference-correction-proposal.json").read_text())
    corrected = proposal["proposals"]["ladder_24s"]
    duration = json.loads((EVIDENCE / "ladder-duration-evidence.json").read_text())
    assert (len(current["pcm"]) / (16000 * 2), words(current["reference"])) == (
        corrected["end"],
        words(corrected["text"]),
    )
    assert all(corrected["end"] <= row["meeting_audio_duration_ms"] / 1000 for row in duration["cases"])


def test_r4_6_corrected_29s_reference_keeps_exact_decoder_additions() -> None:
    raw = json.loads((EVIDENCE / "raw-system-0-29.json").read_text())
    proposal = json.loads((EVIDENCE / "reference-correction-proposal.json").read_text())
    observed = " ".join(segment["text"] for segment in raw["parsed_segments"])
    assert distance(words(proposal["proposals"]["demo_overlap_29s"]["text"]), words(observed)) == {
        "reference_words": 102,
        "observed_words": 105,
        "substitutions": 0,
        "omissions": 0,
        "additions": 3,
        "wer": 3 / 102,
    }
