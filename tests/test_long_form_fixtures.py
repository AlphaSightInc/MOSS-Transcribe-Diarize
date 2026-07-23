from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest


THRESHOLDS = {
    "SECONDS_200_MINUTES": 12.0,
    "DECIMAL_200_MB": 20,
    "BINARY_200_MIB": 24,
}


def test_certifies_schema_threshold_roles_sensors_samples_and_zero_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    module = load_module(monkeypatch, fixture)

    payload = module.certify_files(
        manifest_path=fixture.manifest,
        corpus_root=fixture.corpus_root,
    )

    assert payload["schema_version"] == 1
    assert payload["pass"] is True
    assert payload["inference_calls"] == 0
    assert payload["manifest_sha256"] == sha256(fixture.manifest)
    assert payload["corpus_root"] == str(fixture.corpus_root.resolve())
    fixtures = {item["fixture_id"]: item for item in payload["fixtures"]}
    assert set(fixtures) == {
        "quality-fixture",
        "strict-size-smoke",
    }

    quality = fixtures["quality-fixture"]
    assert quality["validation_role"] == "duration_quality"
    assert quality["gate_tier"] == "coarse"
    assert quality["quality_eligible"] is True
    assert quality["actual"]["audio_bytes"] == 21
    assert quality["actual"]["audio_sha256"] == sha256(fixture.quality_audio)
    assert quality["actual"]["duration_seconds"] == 13.0
    assert quality["actual"]["reference_segment_count"] == 5
    assert quality["actual"]["timed_reference_segment_count"] == 5
    assert quality["actual"]["reference_speakers"] == ["Speaker A", "Speaker B"]
    assert quality["actual"]["reference_start_seconds"] == 0.0
    assert quality["actual"]["reference_end_seconds"] == 13.0
    assert quality["actual"]["match_rate"] == 1.0
    assert quality["threshold_claims"] == {
        "over_200_minutes": True,
        "over_200_mb_decimal": True,
        "over_200_mib_binary": False,
    }
    assert quality["sensor_contract"]["speaker_count"] == {
        "expected_humans": 2,
        "allowed_min": 2,
        "allowed_max": 3,
        "plus_one_reason": "non_speech_speaker_inflation",
    }
    assert quality["sensor_contract"]["continuity_zero_fields"] == [
        "false_accepted_edges",
        "fragmented_recurring_speakers",
    ]
    assert [item["index"] for item in quality["sampled_reference"]] == [0, 2, 4]
    assert {"wer", "der"}.issubset(
        quality["sensor_contract"]["forbidden_pass_fail_metrics"]
    )

    strict_size = fixtures["strict-size-smoke"]
    assert strict_size["validation_role"] == "strict_size_smoke"
    assert strict_size["gate_tier"] == "smoke"
    assert strict_size["quality_eligible"] is False
    assert strict_size["actual"]["audio_bytes"] == 25
    assert strict_size["actual"]["match_rate"] == 0.3512
    assert all(strict_size["threshold_claims"].values())
    assert {
        "speaker_count_proximity",
        "sampled_message_alignment",
        "wer",
        "der",
    }.issubset(strict_size["sensor_contract"]["forbidden_pass_fail_metrics"])
    assert strict_size["sampled_reference"] == []


@pytest.mark.parametrize(
    "path_value",
    [
        "/tmp/outside.wav",
        "../outside.wav",
        "fixtures/../../outside.wav",
    ],
)
def test_rejects_absolute_or_traversal_fixture_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    path_value: str,
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    update_manifest(
        fixture.manifest,
        lambda manifest: manifest["fixtures"][0]["paths"].update({"audio": path_value}),
    )
    module = load_module(monkeypatch, fixture)

    with pytest.raises(ValueError, match="relative|traversal|path"):
        module.certify_files(fixture.manifest, fixture.corpus_root)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda manifest: manifest["fixtures"].append(dict(manifest["fixtures"][0])),
            "duplicate|fixture_id",
        ),
        (
            lambda manifest: manifest["fixtures"][0].update(
                {"validation_role": "merged_quality"}
            ),
            "validation_role|role",
        ),
        (
            lambda manifest: manifest["fixtures"][0].update({"gate_tier": "fine"}),
            "gate_tier|tier",
        ),
        (
            lambda manifest: manifest["fixtures"][0]["sensor_contract"][
                "pass_fail"
            ].append("mystery_sensor"),
            "sensor|unknown",
        ),
        (
            lambda manifest: manifest["fixtures"][0]["sensor_contract"][
                "pass_fail"
            ].append("wer"),
            "forbidden|wer",
        ),
        (
            lambda manifest: manifest["fixtures"][1]["sensor_contract"][
                "pass_fail"
            ].append("speaker_count_proximity"),
            "forbidden|speaker_count",
        ),
    ],
)
def test_rejects_duplicates_unknown_values_and_forbidden_sensor_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Any,
    match: str,
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    update_manifest(fixture.manifest, mutate)
    module = load_module(monkeypatch, fixture)

    with pytest.raises(ValueError, match=match):
        module.certify_files(fixture.manifest, fixture.corpus_root)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (
            lambda fixture: fixture.manifest.write_text("{not json", encoding="utf-8"),
            "JSON|manifest",
        ),
        (
            lambda fixture: fixture.quality_reference.write_text(
                '{"start":0,"end":1,"speaker":"Speaker A","text":"ok"}\nnot-json\n',
                encoding="utf-8",
            ),
            "JSONL|reference",
        ),
        (
            lambda fixture: fixture.quality_alignment.write_text(
                "{not json",
                encoding="utf-8",
            ),
            "JSON|alignment",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"duration_seconds": float("inf")}
                ),
            ),
            "finite|duration",
        ),
        (
            lambda fixture: fixture.quality_alignment.write_text(
                json.dumps({"match_rate": float("nan")}),
                encoding="utf-8",
            ),
            "finite|match_rate",
        ),
    ],
)
def test_rejects_malformed_json_jsonl_and_non_finite_numbers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Any,
    match: str,
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    mutate(fixture)
    module = load_module(monkeypatch, fixture)

    with pytest.raises(ValueError, match=match):
        module.certify_files(fixture.manifest, fixture.corpus_root)


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda fixture: fixture.quality_audio.unlink(), "missing|audio"),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"audio_sha256": "0" * 64}
                ),
            ),
            "audio_sha256|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"audio_bytes": 22}
                ),
            ),
            "audio_bytes|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"duration_seconds": 99.0}
                ),
            ),
            "duration|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"reference_sha256": "0" * 64}
                ),
            ),
            "reference_sha256|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"alignment_stats_sha256": "0" * 64}
                ),
            ),
            "alignment_stats_sha256|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"reference_segment_count": 4}
                ),
            ),
            "reference_segment_count|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"timed_reference_segment_count": 4}
                ),
            ),
            "timed_reference_segment_count|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"reference_speakers": ["Speaker A"]}
                ),
            ),
            "reference_speakers|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"reference_start_seconds": 0.5}
                ),
            ),
            "reference_start_seconds|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"reference_end_seconds": 12.0}
                ),
            ),
            "reference_end_seconds|drift",
        ),
        (
            lambda fixture: update_manifest(
                fixture.manifest,
                lambda manifest: manifest["fixtures"][0]["expected"].update(
                    {"match_rate": 0.99}
                ),
            ),
            "match_rate|drift",
        ),
    ],
)
def test_missing_files_and_exact_manifest_drift_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate: Any,
    match: str,
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    mutate(fixture)
    module = load_module(monkeypatch, fixture)

    with pytest.raises(ValueError, match=match):
        module.certify_files(fixture.manifest, fixture.corpus_root)


def test_threshold_boundaries_are_strict_and_do_not_equate_mb_with_mib(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_fixture_corpus(
        tmp_path,
        quality_audio_bytes=20,
        quality_duration_seconds=12.0,
    )
    update_manifest(
        fixture.manifest,
        lambda manifest: manifest["fixtures"][0].update(
            {
                "threshold_claims": {
                    "over_200_minutes": True,
                    "over_200_mb_decimal": True,
                    "over_200_mib_binary": False,
                }
            }
        ),
    )
    module = load_module(monkeypatch, fixture)

    with pytest.raises(ValueError, match="threshold|over_200"):
        module.certify_files(fixture.manifest, fixture.corpus_root)


def test_cli_json_is_deterministic_and_mismatch_emits_no_false_certificate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    module = load_module(monkeypatch, fixture)

    first_code = module.main(
        ["--manifest", str(fixture.manifest), "--corpus-root", str(fixture.corpus_root)]
    )
    first = capsys.readouterr()
    second_code = module.main(
        ["--manifest", str(fixture.manifest), "--corpus-root", str(fixture.corpus_root)]
    )
    second = capsys.readouterr()

    assert first_code == 0
    assert second_code == 0
    assert first.err == ""
    assert second.err == ""
    assert first.out == second.out
    assert json.loads(first.out)["pass"] is True

    update_manifest(
        fixture.manifest,
        lambda manifest: manifest["fixtures"][0]["expected"].update(
            {"audio_sha256": "0" * 64}
        ),
    )
    failed_code = module.main(
        ["--manifest", str(fixture.manifest), "--corpus-root", str(fixture.corpus_root)]
    )
    failed = capsys.readouterr()

    assert failed_code != 0
    assert '"pass":true' not in failed.out.replace(" ", "")


def test_certification_does_not_import_inference_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = write_fixture_corpus(tmp_path)
    module = load_module(monkeypatch, fixture)
    original_import = builtins.__import__
    blocked_prefixes = (
        "torch",
        "transformers",
        "moss_transcribe_diarize.inference_utils",
        "moss_transcribe_diarize.modeling_moss_transcribe_diarize",
        "moss_transcribe_diarize.app.model_runner",
        "moss_transcribe_diarize.app.vllm_runner",
    )

    def guarded_import(name: str, *args: object, **kwargs: object) -> Any:
        if name.startswith(blocked_prefixes):
            raise AssertionError(f"inference runtime imported: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    payload = module.certify_files(fixture.manifest, fixture.corpus_root)

    assert payload["inference_calls"] == 0


def load_module(monkeypatch: pytest.MonkeyPatch, fixture: "FixtureCorpus") -> Any:
    from moss_transcribe_diarize import long_form_fixtures

    for name, value in THRESHOLDS.items():
        monkeypatch.setattr(long_form_fixtures, name, value)
    monkeypatch.setattr(
        long_form_fixtures,
        "_probe_duration_seconds",
        lambda path: fixture.duration_seconds[Path(path).name],
    )
    return long_form_fixtures


class FixtureCorpus:
    def __init__(
        self,
        *,
        corpus_root: Path,
        manifest: Path,
        quality_audio: Path,
        quality_reference: Path,
        quality_alignment: Path,
        strict_audio: Path,
        strict_reference: Path,
        strict_alignment: Path,
        duration_seconds: dict[str, float],
    ) -> None:
        self.corpus_root = corpus_root
        self.manifest = manifest
        self.quality_audio = quality_audio
        self.quality_reference = quality_reference
        self.quality_alignment = quality_alignment
        self.strict_audio = strict_audio
        self.strict_reference = strict_reference
        self.strict_alignment = strict_alignment
        self.duration_seconds = duration_seconds


def write_fixture_corpus(
    tmp_path: Path,
    *,
    quality_audio_bytes: int = 21,
    quality_duration_seconds: float = 13.0,
) -> FixtureCorpus:
    corpus_root = tmp_path / "corpus"
    quality_dir = corpus_root / "quality"
    strict_dir = corpus_root / "strict"
    quality_dir.mkdir(parents=True)
    strict_dir.mkdir(parents=True)

    quality_audio = quality_dir / "audio.wav"
    quality_audio.write_bytes(b"q" * quality_audio_bytes)
    strict_audio = strict_dir / "audio.wav"
    strict_audio.write_bytes(b"s" * 25)

    quality_reference = quality_dir / "reference.jsonl"
    write_jsonl(
        quality_reference,
        [
            segment(0.0, 1.0, "Speaker A", "alpha"),
            segment(1.0, 3.0, "Speaker B", "bravo"),
            segment(3.0, 8.0, "Speaker A", "charlie"),
            segment(8.0, 11.0, "Speaker B", "delta"),
            segment(11.0, 13.0, "Speaker A", "echo"),
        ],
    )
    strict_reference = strict_dir / "reference.jsonl"
    write_jsonl(
        strict_reference,
        [
            segment(0.5, 2.0, "Smoke A", "one"),
            {"speaker": "Smoke B", "text": "untimed"},
            segment(2.0, 15.0, "Smoke B", "two"),
        ],
    )

    quality_alignment = write_json(quality_dir / "alignment_stats.json", {"match_rate": 1.0})
    strict_alignment = write_json(strict_dir / "alignment_stats.json", {"match_rate": 0.3512})

    duration_seconds = {
        quality_audio.name: quality_duration_seconds,
        strict_audio.name: 15.0,
    }
    manifest = write_json(
        tmp_path / "manifest.json",
        {
            "schema_version": 1,
            "fixtures": [
                fixture_manifest(
                    fixture_id="quality-fixture",
                    case_id="quality-case",
                    validation_role="duration_quality",
                    gate_tier="coarse",
                    quality_eligible=True,
                    audio=quality_audio.relative_to(corpus_root),
                    reference=quality_reference.relative_to(corpus_root),
                    alignment_stats=quality_alignment.relative_to(corpus_root),
                    expected={
                        "audio_sha256": sha256(quality_audio),
                        "audio_bytes": quality_audio_bytes,
                        "duration_seconds": quality_duration_seconds,
                        "duration_tolerance_seconds": 0.01,
                        "reference_sha256": sha256(quality_reference),
                        "alignment_stats_sha256": sha256(quality_alignment),
                        "reference_segment_count": 5,
                        "timed_reference_segment_count": 5,
                        "reference_speakers": ["Speaker A", "Speaker B"],
                        "reference_start_seconds": 0.0,
                        "reference_end_seconds": 13.0,
                        "match_rate": 1.0,
                    },
                    threshold_claims={
                        "over_200_minutes": quality_duration_seconds
                        > THRESHOLDS["SECONDS_200_MINUTES"],
                        "over_200_mb_decimal": quality_audio_bytes
                        > THRESHOLDS["DECIMAL_200_MB"],
                        "over_200_mib_binary": quality_audio_bytes
                        > THRESHOLDS["BINARY_200_MIB"],
                    },
                    sensor_contract={
                        "pass_fail": [
                            "job_completion",
                            "speaker_count_proximity",
                            "label_continuity",
                        ],
                        "observation_only": ["sampled_message_alignment"],
                        "speaker_count": {
                            "expected_humans": 2,
                            "allowed_min": 2,
                            "allowed_max": 3,
                            "plus_one_reason": "non_speech_speaker_inflation",
                        },
                        "continuity_zero_fields": [
                            "false_accepted_edges",
                            "fragmented_recurring_speakers",
                        ],
                        "sample_reference_indices": [0, 2, 4],
                        "forbidden_pass_fail_metrics": ["wer", "der"],
                    },
                ),
                fixture_manifest(
                    fixture_id="strict-size-smoke",
                    case_id="strict-case",
                    validation_role="strict_size_smoke",
                    gate_tier="smoke",
                    quality_eligible=False,
                    audio=strict_audio.relative_to(corpus_root),
                    reference=strict_reference.relative_to(corpus_root),
                    alignment_stats=strict_alignment.relative_to(corpus_root),
                    expected={
                        "audio_sha256": sha256(strict_audio),
                        "audio_bytes": 25,
                        "duration_seconds": 15.0,
                        "duration_tolerance_seconds": 0.01,
                        "reference_sha256": sha256(strict_reference),
                        "alignment_stats_sha256": sha256(strict_alignment),
                        "reference_segment_count": 3,
                        "timed_reference_segment_count": 2,
                        "reference_speakers": ["Smoke A", "Smoke B"],
                        "reference_start_seconds": 0.5,
                        "reference_end_seconds": 15.0,
                        "match_rate": 0.3512,
                    },
                    threshold_claims={
                        "over_200_minutes": True,
                        "over_200_mb_decimal": True,
                        "over_200_mib_binary": True,
                    },
                    sensor_contract={
                        "pass_fail": [
                            "source_integrity",
                            "upload_admission",
                            "job_completion",
                        ],
                        "observation_only": ["resource_usage", "label_continuity"],
                        "forbidden_pass_fail_metrics": [
                            "speaker_count_proximity",
                            "sampled_message_alignment",
                            "wer",
                            "der",
                        ],
                    },
                ),
            ],
        },
    )

    return FixtureCorpus(
        corpus_root=corpus_root,
        manifest=manifest,
        quality_audio=quality_audio,
        quality_reference=quality_reference,
        quality_alignment=quality_alignment,
        strict_audio=strict_audio,
        strict_reference=strict_reference,
        strict_alignment=strict_alignment,
        duration_seconds=duration_seconds,
    )


def fixture_manifest(
    *,
    fixture_id: str,
    case_id: str,
    validation_role: str,
    gate_tier: str,
    quality_eligible: bool,
    audio: Path,
    reference: Path,
    alignment_stats: Path,
    expected: dict[str, object],
    threshold_claims: dict[str, bool],
    sensor_contract: dict[str, object],
) -> dict[str, object]:
    return {
        "fixture_id": fixture_id,
        "case_id": case_id,
        "validation_role": validation_role,
        "gate_tier": gate_tier,
        "quality_eligible": quality_eligible,
        "paths": {
            "audio": str(audio),
            "reference": str(reference),
            "alignment_stats": str(alignment_stats),
        },
        "expected": expected,
        "threshold_claims": threshold_claims,
        "sensor_contract": sensor_contract,
    }


def segment(start: float, end: float, speaker: str, text: str) -> dict[str, object]:
    return {"start": start, "end": end, "speaker": speaker, "text": text}


def update_manifest(path: Path, mutate: Any) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return path


def write_jsonl(path: Path, records: list[dict[str, object]]) -> Path:
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
