from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REFERENCE_SEGMENTS = [
    {
        "start": 0.0,
        "end": 10.0,
        "speaker": "Reference A",
        "text": "alpha words",
    },
    {
        "start": 10.0,
        "end": 20.0,
        "speaker": "Reference B",
        "text": "beta words",
    },
]


def test_evaluate_accepts_json_list_wrapped_list_and_jsonl(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path)
    records = build_hypothesis({"Reference A": "S02", "Reference B": "S01"})
    formats = [
        write_json(tmp_path / "list.json", records),
        write_json(tmp_path / "wrapped.json", {"segments": records}),
        write_jsonl(tmp_path / "records.jsonl", records),
    ]

    results = [evaluate_fixture(fixture, hypothesis) for hypothesis in formats]

    for result in results:
        assert result["schema_version"] == 1
        assert result["fixture_id"] == "speaker-fixture"
        assert result["gate_tier"] == "fine"
        assert result["reference_path"] == str((fixture.manifest.parent / "reference.jsonl").resolve())
        assert result["match_rate"] == 1.0
        assert result["reference_covered_seconds"] == 20.0
        assert_perfect_scores(
            result,
            {"Reference A": "S02", "Reference B": "S01"},
        )


def test_sibling_reference_is_authoritative_over_embedded_manifest_paths(tmp_path: Path) -> None:
    stale_reference = tmp_path / "stale" / "reference.jsonl"
    stale_reference.parent.mkdir()
    write_jsonl(
        stale_reference,
        [
            {
                "start": 0.0,
                "end": 20.0,
                "speaker": "Embedded Stale Speaker",
                "text": "stale text that must not be authoritative",
            }
        ],
    )
    fixture = write_fixture(
        tmp_path,
        manifest_updates={
            "reference_jsonl": str(stale_reference),
            "reference_txt": str(stale_reference.with_suffix(".txt")),
        },
    )
    hypothesis = write_json(
        tmp_path / "hypothesis.json",
        build_hypothesis({"Reference A": "S01", "Reference B": "S02"}),
    )

    result = evaluate_fixture(fixture, hypothesis)

    assert result["reference_path"] == str((fixture.manifest.parent / "reference.jsonl").resolve())
    assert_perfect_scores(
        result,
        {"Reference A": "S01", "Reference B": "S02"},
    )


@pytest.mark.parametrize(
    ("manifest_updates", "alignment_updates", "match"),
    [
        ({}, {"match_rate": 0.99}, "match_rate"),
        ({"reference_covered_seconds": 19.999}, {}, "coverage"),
        ({"duration_sec": 300.001, "reference_covered_seconds": 300.001}, {}, "duration"),
    ],
)
def test_fine_gate_rejects_weak_provenance_partial_coverage_and_long_duration(
    tmp_path: Path,
    manifest_updates: dict[str, float],
    alignment_updates: dict[str, float],
    match: str,
) -> None:
    fixture = write_fixture(
        tmp_path,
        manifest_updates=manifest_updates,
        alignment_updates=alignment_updates,
    )
    hypothesis = write_json(
        tmp_path / "hypothesis.json",
        build_hypothesis({"Reference A": "S01", "Reference B": "S02"}),
    )

    with pytest.raises(ValueError, match=match):
        evaluate_fixture(fixture, hypothesis)


def test_two_label_permutations_score_perfectly_without_direct_label_equality(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path)

    for mapping in [
        {"Reference A": "S01", "Reference B": "S02"},
        {"Reference A": "S02", "Reference B": "S01"},
    ]:
        hypothesis = write_json(
            tmp_path / f"hypothesis-{mapping['Reference A']}.json",
            build_hypothesis(mapping),
        )

        result = evaluate_fixture(fixture, hypothesis)

        assert_perfect_scores(result, mapping)


def test_collapsed_speakers_remain_visible_after_assignment(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path)
    hypothesis = write_json(
        tmp_path / "collapsed.json",
        build_hypothesis({"Reference A": "S01", "Reference B": "S01"}),
    )

    result = evaluate_fixture(fixture, hypothesis)

    assert result["tbsa"]["text_speaker_accuracy"] < 1.0
    assert result["tbsa"]["composite"] < 1.0
    assert result["diarization"]["der"] > 0.0


def test_rectangular_speaker_count_mismatch_keeps_exact_best_mapping(tmp_path: Path) -> None:
    reference = REFERENCE_SEGMENTS + [
        {
            "start": 20.0,
            "end": 30.0,
            "speaker": "Reference C",
            "text": "gamma words",
        }
    ]
    fixture = write_fixture(
        tmp_path,
        reference=reference,
        manifest_updates={
            "duration_sec": 30.0,
            "reference_covered_seconds": 30.0,
            "segment_count": 3,
            "speakers": ["Reference A", "Reference B", "Reference C"],
        },
    )
    hypothesis = write_json(
        tmp_path / "mismatch.json",
        build_hypothesis(
            {
                "Reference A": "S02",
                "Reference B": "S01",
                "Reference C": "S01",
            },
            reference=reference,
        ),
    )

    result = evaluate_fixture(fixture, hypothesis)

    assert result["tbsa"]["speaker_mapping"]["Reference A"] == "S02"
    assert result["tbsa"]["speaker_mapping"]["Reference B"] == "S01"
    assert any(
        value.startswith("<HYP_PAD_")
        for value in result["tbsa"]["speaker_mapping"].values()
    )
    assert result["tbsa"]["text_speaker_accuracy"] < 1.0
    assert result["diarization"]["der"] > 0.0


def test_cli_output_is_deterministic_and_orders_mappings(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path)
    hypothesis = write_json(
        tmp_path / "hypothesis.json",
        build_hypothesis({"Reference A": "S02", "Reference B": "S01"}),
    )

    first = run_cli(fixture, hypothesis)
    second = run_cli(fixture, hypothesis)

    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert first.stdout == second.stdout
    payload = json.loads(first.stdout)
    assert list(payload["tbsa"]["speaker_mapping"]) == ["Reference A", "Reference B"]
    assert list(payload["diarization"]["speaker_mapping"]) == ["Reference A", "Reference B"]


@pytest.mark.parametrize(
    ("manifest_updates", "alignment_updates", "match"),
    [
        ({"sample_id": None}, {}, "sample_id"),
        ({"duration_sec": None}, {}, "duration_sec"),
        ({}, {"match_rate": None}, "match_rate"),
    ],
)
def test_required_fixture_schema_fields_are_rejected(
    tmp_path: Path,
    manifest_updates: dict[str, object],
    alignment_updates: dict[str, object],
    match: str,
) -> None:
    fixture = write_fixture(
        tmp_path,
        manifest_updates=manifest_updates,
        alignment_updates=alignment_updates,
    )
    hypothesis = write_json(
        tmp_path / "hypothesis.json",
        build_hypothesis({"Reference A": "S01", "Reference B": "S02"}),
    )

    with pytest.raises(ValueError, match=match):
        evaluate_fixture(fixture, hypothesis)


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        ([{"start": 0.0, "end": 1.0, "speaker": "S01"}], "text"),
        ([{"start": 1.0, "end": 0.0, "speaker": "S01", "text": "bad"}], "end"),
        ({"records": []}, "segments"),
        ([], "hypothesis"),
    ],
)
def test_malformed_hypothesis_records_are_rejected(
    tmp_path: Path,
    payload: object,
    match: str,
) -> None:
    fixture = write_fixture(tmp_path)
    hypothesis = write_json(tmp_path / "bad.json", payload)

    with pytest.raises(ValueError, match=match):
        evaluate_fixture(fixture, hypothesis)


def test_malformed_jsonl_record_is_rejected(tmp_path: Path) -> None:
    fixture = write_fixture(tmp_path)
    hypothesis = tmp_path / "bad.jsonl"
    hypothesis.write_text('{"start": 0, "end": 1, "speaker": "S01", "text": "ok"}\nnot-json\n')

    with pytest.raises(ValueError, match="JSONL"):
        evaluate_fixture(fixture, hypothesis)


def evaluate_fixture(fixture: "FixturePaths", hypothesis: Path) -> dict:
    from moss_transcribe_diarize import evaluation

    return evaluation.evaluate_files(
        manifest_path=fixture.manifest,
        alignment_stats_path=fixture.alignment_stats,
        hypothesis_path=hypothesis,
    )


def run_cli(fixture: "FixturePaths", hypothesis: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "moss_transcribe_diarize.evaluation",
            "--manifest",
            str(fixture.manifest),
            "--alignment-stats",
            str(fixture.alignment_stats),
            "--hypothesis",
            str(hypothesis),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def assert_perfect_scores(result: dict, mapping: dict[str, str]) -> None:
    assert result["tbsa"]["composite"] == 1.0
    assert result["tbsa"]["text_speaker_accuracy"] == 1.0
    assert result["tbsa"]["text_coverage"] == 1.0
    assert result["tbsa"]["wer"] == 0.0
    assert result["tbsa"]["speaker_mapping"] == mapping
    assert result["diarization"]["der"] == 0.0
    assert result["diarization"]["miss"] == 0.0
    assert result["diarization"]["false_alarm"] == 0.0
    assert result["diarization"]["speaker_confusion"] == 0.0
    assert result["diarization"]["speaker_mapping"] == mapping


class FixturePaths:
    def __init__(self, manifest: Path, alignment_stats: Path):
        self.manifest = manifest
        self.alignment_stats = alignment_stats


def write_fixture(
    tmp_path: Path,
    *,
    reference: list[dict] | None = None,
    manifest_updates: dict[str, object] | None = None,
    alignment_updates: dict[str, object] | None = None,
) -> FixturePaths:
    sample_dir = tmp_path / "sample"
    sample_dir.mkdir(exist_ok=True)
    reference_records = REFERENCE_SEGMENTS if reference is None else reference
    write_jsonl(sample_dir / "reference.jsonl", reference_records)

    manifest = {
        "sample_id": "speaker-fixture",
        "duration_sec": 20.0,
        "reference_covered_seconds": 20.0,
        "segment_count": len(reference_records),
        "speakers": sorted({record["speaker"] for record in reference_records}),
        "audio_path": str(tmp_path / "stale" / "audio.wav"),
        "reference_jsonl": str(tmp_path / "stale" / "reference.jsonl"),
        "reference_txt": str(tmp_path / "stale" / "reference.txt"),
    }
    if manifest_updates:
        manifest.update(manifest_updates)
    manifest = {key: value for key, value in manifest.items() if value is not None}

    alignment_stats = {
        "method": "test_fixture",
        "total_lines": len(reference_records),
        "matched_lines": len(reference_records),
        "match_rate": 1.0,
    }
    if alignment_updates:
        alignment_stats.update(alignment_updates)
    alignment_stats = {
        key: value for key, value in alignment_stats.items() if value is not None
    }

    manifest_path = write_json(sample_dir / "sample_manifest.json", manifest)
    alignment_path = write_json(tmp_path / "alignment_stats.json", alignment_stats)
    return FixturePaths(manifest_path, alignment_path)


def build_hypothesis(
    speaker_mapping: dict[str, str],
    *,
    reference: list[dict] | None = None,
) -> list[dict]:
    reference_records = REFERENCE_SEGMENTS if reference is None else reference
    return [
        {
            "start": record["start"],
            "end": record["end"],
            "speaker": speaker_mapping[record["speaker"]],
            "text": record["text"],
        }
        for record in reference_records
    ]


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def write_jsonl(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "".join(json.dumps(record) + "\n" for record in records),
        encoding="utf-8",
    )
    return path
