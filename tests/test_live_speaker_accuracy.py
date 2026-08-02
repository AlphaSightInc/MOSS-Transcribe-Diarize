from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from moss_transcribe_diarize.evaluation import Segment
from moss_transcribe_diarize.live_speaker_accuracy import (
    evaluate_live_speaker_evidence,
    hypothesis_from_live_snapshot,
    load_reference_jsonl,
    score_live_speaker_accuracy,
)


REAL_CORPUS = (
    Path(
        os.environ.get(
            "MOSS_REAL_CORPUS_ROOT",
            Path(__file__).resolve().parents[1]
            / "prototypes"
            / "streaming-diarization"
            / "data"
            / "real",
        )
    )
    / "benchmark_5m"
    / "acquired_alphabet"
)


def test_f_cert_real_corpus_contract_is_exact() -> None:
    audio = REAL_CORPUS / "audio.wav"
    reference = REAL_CORPUS / "reference.jsonl"
    if not audio.is_file() or not reference.is_file():
        pytest.skip("real F-cert corpus is not provisioned in this clean worktree")

    assert hashlib.sha256(audio.read_bytes()).hexdigest() == (
        "333b1e50b05d5dc888a6bdb4dc82f1c429e0e9c5a0b1df0cf115c2215eb394fb"
    )
    assert len(load_reference_jsonl(reference)) == 45


def test_live_snapshot_scores_duration_weighted_optimal_mapping() -> None:
    reference = (
        Segment(0.0, 2.0, "Alice", "alpha"),
        Segment(2.0, 4.0, "Bob", "beta"),
    )
    snapshot = live_snapshot(
        [
            commit(32000, 64000, "[0][S02]alpha[2]"),
            commit(64000, 96000, "[0][S01]beta[2]"),
        ]
    )

    hypothesis = hypothesis_from_live_snapshot(
        snapshot,
        corpus_start_sample=32000,
        corpus_duration_sec=4.0,
    )
    result = score_live_speaker_accuracy(reference, hypothesis)

    assert [(item.start, item.end, item.speaker) for item in hypothesis] == [
        (0.0, 2.0, "S02"),
        (2.0, 4.0, "S01"),
    ]
    assert result["speaker_accuracy"] == 1.0
    assert result["reference_coverage"] == 1.0
    assert result["speaker_mapping"] == {"Alice": "S02", "Bob": "S01"}


def test_final_revised_transcript_is_scored_instead_of_stale_live_label() -> None:
    reference = (Segment(0.0, 2.0, "Alice", "alpha"),)
    snapshot = live_snapshot(
        [
            commit(
                0,
                32000,
                "[0][S01]alpha[2]",
                revised_transcript="[0][S03]alpha[2]",
            )
        ]
    )

    hypothesis = hypothesis_from_live_snapshot(
        snapshot,
        corpus_start_sample=0,
        corpus_duration_sec=2.0,
    )
    result = score_live_speaker_accuracy(reference, hypothesis)

    assert [item.speaker for item in hypothesis] == ["S03"]
    assert result["speaker_mapping"] == {"Alice": "S03"}
    assert result["speaker_accuracy"] == 1.0


def test_live_snapshot_parser_keeps_adjacent_segments_and_numeric_brackets_in_text() -> None:
    snapshot = live_snapshot(
        [
            commit(
                0,
                32000,
                "[0][S01]cost [42] dollars[1][1][S02]answer[2]",
            )
        ]
    )

    hypothesis = hypothesis_from_live_snapshot(
        snapshot,
        corpus_start_sample=0,
        corpus_duration_sec=2.0,
    )

    assert [(item.start, item.end, item.speaker, item.text) for item in hypothesis] == [
        (0.0, 1.0, "S01", "cost [42] dollars"),
        (1.0, 2.0, "S02", "answer"),
    ]


def test_unlabelled_reference_duration_counts_against_live_accuracy() -> None:
    reference = (
        Segment(0.0, 2.0, "Alice", "alpha"),
        Segment(2.0, 4.0, "Bob", "beta"),
    )
    hypothesis = (Segment(0.0, 2.0, "S01", "alpha"),)

    result = score_live_speaker_accuracy(reference, hypothesis)

    assert result["speaker_accuracy"] == 0.5
    assert result["reference_coverage"] == 0.5
    assert result["matched_speaker_seconds"] == 2.0
    assert result["reference_seconds"] == 4.0
    assert result["two_sided_mapping"] is False
    assert result["speaker_correctness"] == {"Alice": 1.0, "Bob": 0.0}


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"snapshot": {}},
        {"snapshot": {"session": {"committed": "not-a-list"}}},
        {
            "snapshot": {
                "session": {
                    "committed": [{"start_sample": 0, "end_sample": 32000, "transcript": 7}]
                }
            }
        },
    ],
)
def test_malformed_live_snapshot_is_refused(payload: dict) -> None:
    with pytest.raises(ValueError):
        hypothesis_from_live_snapshot(
            payload,
            corpus_start_sample=0,
            corpus_duration_sec=2.0,
        )


def test_reference_jsonl_rejects_missing_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "reference.jsonl"
    path.write_text(json.dumps({"start": 0, "end": 1, "speaker": "Alice"}) + "\n")

    with pytest.raises(ValueError, match="text"):
        load_reference_jsonl(path)


def test_formal_evidence_binds_audio_reference_and_final_snapshot(tmp_path: Path) -> None:
    reference = tmp_path / "speaker-reference.jsonl"
    reference.write_text(
        json.dumps({"start": 0.0, "end": 2.0, "speaker": "Alice", "text": "alpha"}) + "\n"
    )
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    (tmp_path / "speaker-final.json").write_text(
        json.dumps(live_snapshot([commit(16000, 48000, "[0][S01]alpha[2]")]))
    )
    (tmp_path / "corpus.env").write_text(
        "\n".join(
            [
                "CORPUS_AUDIO_SHA256=abc123",
                "CORPUS_EXPECTED_AUDIO_SHA256=abc123",
                "CORPUS_START_SAMPLE=16000",
                "CORPUS_DURATION_SEC=2",
                f"CORPUS_REFERENCE_SHA256={reference_hash}",
                "CORPUS_REFERENCE_SEGMENTS=1",
            ]
        )
        + "\n"
    )

    result = evaluate_live_speaker_evidence(tmp_path)

    assert result["speaker_accuracy"] == 1.0
    assert result["reference_segments"] == 1
    assert result["hypothesis_segments"] == 1
    assert result["corpus_start_sample"] == 16000


def test_formal_evidence_uses_label_blind_coverage_to_align_playback(tmp_path: Path) -> None:
    write_formal_evidence(
        tmp_path,
        reference_rows=two_speaker_reference(),
        committed=[
            commit(48000, 64000, "[0][S01]alpha[1]"),
            commit(96000, 112000, "[0][S02]beta[1]"),
        ],
        duration_sec=8,
    )

    result = evaluate_live_speaker_evidence(tmp_path)

    assert result["unaligned_speaker_accuracy"] == 0.0
    assert result["corpus_alignment_adjustment_sec"] == 1.0
    assert result["aligned_corpus_start_sample"] == 16000
    assert result["speaker_accuracy"] == 1.0
    assert result["two_sided_mapping"] is True
    assert result["speaker_correctness"] == {"Alice": 1.0, "Bob": 1.0}


def test_alignment_cannot_turn_one_live_label_into_two_sided_mapping(tmp_path: Path) -> None:
    write_formal_evidence(
        tmp_path,
        reference_rows=two_speaker_reference(),
        committed=[
            commit(48000, 64000, "[0][S01]alpha[1]"),
            commit(96000, 112000, "[0][S01]beta[1]"),
        ],
        duration_sec=8,
    )

    result = evaluate_live_speaker_evidence(tmp_path)

    assert result["corpus_alignment_adjustment_sec"] == 1.0
    assert result["speaker_accuracy"] == 0.5
    assert result["two_sided_mapping"] is False
    assert sorted(result["speaker_correctness"].values()) == [0.0, 1.0]


def test_formal_alignment_reports_a_negative_adjustment_without_clamping(tmp_path: Path) -> None:
    write_formal_evidence(
        tmp_path,
        reference_rows=two_speaker_reference(),
        committed=[
            commit(48000, 64000, "[0][S01]alpha[1]"),
            commit(96000, 112000, "[0][S02]beta[1]"),
        ],
        duration_sec=8,
        start_sample=32000,
    )

    result = evaluate_live_speaker_evidence(tmp_path)

    assert result["corpus_alignment_adjustment_sec"] == -1.0
    assert result["aligned_corpus_start_sample"] == 16000
    assert result["speaker_accuracy"] == 1.0


@pytest.mark.parametrize(
    ("line", "match"),
    [
        ("CORPUS_EXPECTED_AUDIO_SHA256=different", "audio sha256 mismatch"),
        ("CORPUS_REFERENCE_SEGMENTS=2", "segment count mismatch"),
    ],
)
def test_formal_evidence_refuses_provenance_mismatch(
    tmp_path: Path,
    line: str,
    match: str,
) -> None:
    reference = tmp_path / "speaker-reference.jsonl"
    reference.write_text(
        json.dumps({"start": 0.0, "end": 2.0, "speaker": "Alice", "text": "alpha"}) + "\n"
    )
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    (tmp_path / "speaker-final.json").write_text(
        json.dumps(live_snapshot([commit(0, 32000, "[0][S01]alpha[2]")]))
    )
    values = {
        "CORPUS_AUDIO_SHA256": "abc123",
        "CORPUS_EXPECTED_AUDIO_SHA256": "abc123",
        "CORPUS_START_SAMPLE": "0",
        "CORPUS_DURATION_SEC": "2",
        "CORPUS_REFERENCE_SHA256": reference_hash,
        "CORPUS_REFERENCE_SEGMENTS": "1",
    }
    key, value = line.split("=", 1)
    values[key] = value
    (tmp_path / "corpus.env").write_text(
        "".join(f"{key}={value}\n" for key, value in values.items())
    )

    with pytest.raises(ValueError, match=match):
        evaluate_live_speaker_evidence(tmp_path)


def test_clause_reducer_makes_real_speaker_accuracy_a_visible_red_gate(tmp_path: Path) -> None:
    reference = tmp_path / "speaker-reference.jsonl"
    reference.write_text(
        "\n".join(
            [
                json.dumps({"start": 0.0, "end": 2.0, "speaker": "Alice", "text": "alpha"}),
                json.dumps({"start": 2.0, "end": 4.0, "speaker": "Bob", "text": "beta"}),
            ]
        )
        + "\n"
    )
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    (tmp_path / "speaker-final.json").write_text(
        json.dumps(live_snapshot([commit(0, 32000, "[0][S01]alpha[2]")]))
    )
    (tmp_path / "corpus.env").write_text(
        "\n".join(
            [
                "CORPUS_AUDIO_SHA256=abc123",
                "CORPUS_EXPECTED_AUDIO_SHA256=abc123",
                "CORPUS_START_SAMPLE=0",
                "CORPUS_DURATION_SEC=4",
                f"CORPUS_REFERENCE_SHA256={reference_hash}",
                "CORPUS_REFERENCE_SEGMENTS=2",
            ]
        )
        + "\n"
    )
    reducer = Path(__file__).resolve().parents[1] / "scripts" / "ralph-afk" / "live-canary-clauses.py"

    completed = subprocess.run(
        [sys.executable, "-S", str(reducer), str(tmp_path)],
        cwd=reducer.parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 3
    assert "live speaker accuracy 50.00% >= 90.00%" in completed.stdout
    assert "RED" in completed.stdout


def test_clause_reducer_requires_two_sided_mapping_even_above_accuracy_gate(tmp_path: Path) -> None:
    write_formal_evidence(
        tmp_path,
        reference_rows=[
            {"start": 0.0, "end": 95.0, "speaker": "Alice", "text": "alpha"},
            {"start": 95.0, "end": 100.0, "speaker": "Bob", "text": "beta"},
        ],
        committed=[commit(0, 1600000, "[0][S01]one label[100]")],
        duration_sec=100,
    )
    reducer = Path(__file__).resolve().parents[1] / "scripts" / "ralph-afk" / "live-canary-clauses.py"

    completed = subprocess.run(
        [sys.executable, "-S", str(reducer), str(tmp_path)],
        cwd=reducer.parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 3
    assert "live speaker accuracy 95.00% >= 90.00%" in completed.stdout
    assert "two-sided mapping=False" in completed.stdout
    assert "speaker correctness=" in completed.stdout
    assert "RED" in completed.stdout


def live_snapshot(committed: list[dict]) -> dict:
    return {"snapshot": {"session": {"committed": committed}}}


def two_speaker_reference() -> list[dict]:
    return [
        {"start": 2.0, "end": 3.0, "speaker": "Alice", "text": "alpha"},
        {"start": 5.0, "end": 6.0, "speaker": "Bob", "text": "beta"},
    ]


def write_formal_evidence(
    directory: Path,
    *,
    reference_rows: list[dict],
    committed: list[dict],
    duration_sec: int,
    start_sample: int = 0,
) -> None:
    reference = directory / "speaker-reference.jsonl"
    reference.write_text("\n".join(json.dumps(row) for row in reference_rows) + "\n")
    reference_hash = hashlib.sha256(reference.read_bytes()).hexdigest()
    (directory / "speaker-final.json").write_text(json.dumps(live_snapshot(committed)))
    (directory / "corpus.env").write_text(
        "\n".join(
            [
                "CORPUS_AUDIO_SHA256=abc123",
                "CORPUS_EXPECTED_AUDIO_SHA256=abc123",
                f"CORPUS_START_SAMPLE={start_sample}",
                f"CORPUS_DURATION_SEC={duration_sec}",
                f"CORPUS_REFERENCE_SHA256={reference_hash}",
                f"CORPUS_REFERENCE_SEGMENTS={len(reference_rows)}",
            ]
        )
        + "\n"
    )


def commit(
    start_sample: int,
    end_sample: int,
    transcript: str,
    *,
    revised_transcript: str | None = None,
) -> dict:
    return {
        "start_sample": start_sample,
        "end_sample": end_sample,
        "transcript": transcript,
        "revised_transcript": revised_transcript,
    }
