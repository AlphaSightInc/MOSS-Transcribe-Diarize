from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from moss_transcribe_diarize.speaker_reference import (
    AcousticReferenceValidation,
    normalize_reference_text,
    validate_speaker_reference,
)


EXISTENCE_FIXTURES = Path(__file__).parent / "fixtures" / "speaker_reference_existence"
REAL_CORPUS_FIXTURES = Path(__file__).parent / "fixtures" / "live_identity_real_corpus"
AUTHORITATIVE_90S_AUDIO_SHA256 = (
    "dd48a724629aa05846a7c266218ee161083c60933e3c6a313540442536c95cbe"
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _aligned_row(*, start: float, end: float, text: str, line_index: int) -> dict:
    normalized = normalize_reference_text(text)
    return {
        "schema": "moss-speaker-reference.v2",
        "speaker_activity": {"start": start, "end": end, "speaker": "David"},
        "transcript": {"text": text, "line_index": line_index},
        "alignment": {
            "normalized_text": normalized,
            "normalized_text_sha256": hashlib.sha256(normalized.encode()).hexdigest(),
            "word_count": len(normalized.split()),
        },
    }


def test_validator_rejects_impossible_v1_speech_rate(tmp_path: Path) -> None:
    reference = tmp_path / "reference-v1.jsonl"
    _write_jsonl(
        reference,
        [
            {
                "speaker": "Ben",
                "text": "one two three four five six seven eight nine",
                "line_index": 7,
                "start": 40.0,
                "end": 41.0,
            }
        ],
    )

    result = validate_speaker_reference(reference)

    assert result["verdict"] == "FAIL"
    assert [issue["code"] for issue in result["issues"]] == ["speech_rate"]


def test_validator_accepts_v2_and_checks_v1_text_lineage(tmp_path: Path) -> None:
    v1 = tmp_path / "reference-v1.jsonl"
    v2 = tmp_path / "reference-v2.jsonl"
    rows = [
        _aligned_row(start=0.5, end=2.0, text="Hello there", line_index=0),
        _aligned_row(start=3.0, end=4.5, text="General Kenobi", line_index=1),
    ]
    _write_jsonl(
        v1,
        [
            {
                "speaker": row["speaker_activity"]["speaker"],
                "text": row["transcript"]["text"],
                "line_index": row["transcript"]["line_index"],
                "start": row["speaker_activity"]["start"],
                "end": row["speaker_activity"]["end"],
            }
            for row in rows
        ],
    )
    _write_jsonl(v2, rows)

    result = validate_speaker_reference(v2, lineage_path=v1)

    assert result["verdict"] == "PASS"
    assert result["segment_count"] == 2
    assert result["max_speech_rate_words_per_sec"] < 8.0


def test_validator_rejects_non_monotonic_and_text_misaligned_v2(tmp_path: Path) -> None:
    v1 = tmp_path / "reference-v1.jsonl"
    v2 = tmp_path / "reference-v2.jsonl"
    _write_jsonl(
        v1,
        [
            {
                "speaker": "David",
                "text": "Expected words",
                "line_index": 0,
                "start": 0.0,
                "end": 1.0,
            }
        ],
    )
    _write_jsonl(v2, [_aligned_row(start=2.0, end=1.0, text="Wrong words", line_index=0)])

    result = validate_speaker_reference(v2, lineage_path=v1)

    codes = {issue["code"] for issue in result["issues"]}
    assert result["verdict"] == "FAIL"
    assert {"interval", "text_lineage"} <= codes


def test_acoustic_existence_accepts_genuinely_present_90s_line() -> None:
    result = validate_speaker_reference(
        EXISTENCE_FIXTURES / "youtube_rtfl_first_90s-present.jsonl",
        acoustic=AcousticReferenceValidation(
            evidence_path=(
                EXISTENCE_FIXTURES / "youtube_rtfl_first_90s-independent-asr.json"
            ),
            expected_audio_sha256=AUTHORITATIVE_90S_AUDIO_SHA256,
            required=True,
        ),
    )

    assert result["verdict"] == "PASS"
    assert result["acoustic_existence"]["accepted"] == 1


@pytest.mark.parametrize(
    "fixture_name",
    [
        "youtube_rtfl_first_90s-absent.jsonl",
        "youtube_rtfl_first_90s-absent-whats-up.jsonl",
    ],
)
def test_acoustic_existence_rejects_absent_line_despite_valid_claimed_metadata(
    fixture_name: str,
) -> None:
    absent = EXISTENCE_FIXTURES / fixture_name

    result = validate_speaker_reference(
        absent,
        lineage_path=absent,
        acoustic=AcousticReferenceValidation(
            evidence_path=(
                EXISTENCE_FIXTURES / "youtube_rtfl_first_90s-independent-asr.json"
            ),
            expected_audio_sha256=AUTHORITATIVE_90S_AUDIO_SHA256,
            required=True,
        ),
    )

    assert result["verdict"] == "FAIL"
    acoustic_issues = [issue for issue in result["issues"] if issue["code"] == "acoustic_existence"]
    assert len(acoustic_issues) == 1
    assert acoustic_issues[0]["record"] == 1
    assert acoustic_issues[0]["score"] < acoustic_issues[0]["threshold"]


def test_validator_accepts_audited_text_edit_and_separate_nonlexical_activity(
    tmp_path: Path,
) -> None:
    candidate = tmp_path / "candidate.jsonl"
    post_audit = tmp_path / "post-audit.jsonl"
    audit = tmp_path / "audit.json"
    candidate_row = _aligned_row(
        start=1.0,
        end=3.0,
        text="Woo hoo hoo. Oh, you're giving away the end.",
        line_index=23,
    )
    post_audit_row = _aligned_row(
        start=1.0,
        end=3.0,
        text="Oh, you're giving away the end.",
        line_index=23,
    )
    post_audit_row["transcript"].update({"start": 1.6, "end": 3.0})
    post_audit_row["nonlexical_activity"] = {
        "start": 1.0,
        "end": 1.6,
        "kind": "uncertain_prelexical_vocalization",
        "confirmed_lexical_text": None,
    }
    _write_jsonl(candidate, [candidate_row])
    _write_jsonl(post_audit, [post_audit_row])
    audit.write_text(
        json.dumps(
            {
                "schema": "moss-speaker-reference-human-audit.v1",
                "status": "accepted",
                "candidate_reference_sha256": hashlib.sha256(
                    candidate.read_bytes()
                ).hexdigest(),
                "decisions": [
                    {
                        "range_id": "R4",
                        "disposition": "EDIT",
                        "line_indices": [23],
                        "candidate_text": candidate_row["transcript"]["text"],
                        "post_audit_text": post_audit_row["transcript"]["text"],
                    }
                ],
            }
        )
        + "\n"
    )

    unaudited = validate_speaker_reference(post_audit, lineage_path=candidate)
    audited = validate_speaker_reference(
        post_audit,
        lineage_path=candidate,
        audit_path=audit,
    )

    assert unaudited["verdict"] == "FAIL"
    assert audited["verdict"] == "PASS"
    assert audited["audit"]["accepted_edits"] == 1


def test_frozen_post_audit_reference_preserves_r4_activity_and_removes_lexical_claim() -> None:
    reference = REAL_CORPUS_FIXTURES / "speaker-reference-v2-post-audit.jsonl"
    provenance = json.loads(
        (REAL_CORPUS_FIXTURES / "speaker-reference-v2-post-audit.provenance.json").read_text()
    )
    rows = [json.loads(line) for line in reference.read_text().splitlines()]
    r4 = next(row for row in rows if row["transcript"]["line_index"] == 23)

    assert hashlib.sha256(reference.read_bytes()).hexdigest() == (
        "28dc9a5b80098db58a261b4bfa73e2975acac31ef36e7e8f057c514d8bdc0759"
    )
    assert provenance["post_audit_reference_sha256"] == hashlib.sha256(
        reference.read_bytes()
    ).hexdigest()
    assert provenance["rejected_candidate_reference_sha256"] == (
        "7c3020b89326a933dd011cbbd8c8b398b6a5e0aea51a42458d716cd2867565f8"
    )
    assert provenance["human_audit_primary_basis"]["method"] == "direct human listen"
    assert r4["speaker_activity"] == {
        "start": 161.8,
        "end": 163.410711,
        "speaker": "David",
    }
    assert r4["transcript"] == {
        "start": 162.4,
        "end": 163.410711,
        "line_index": 23,
        "text": "Oh, you're giving away the end.",
    }
    assert r4["nonlexical_activity"]["confirmed_lexical_text"] is None
    assert "Woo hoo hoo" not in r4["transcript"]["text"]
