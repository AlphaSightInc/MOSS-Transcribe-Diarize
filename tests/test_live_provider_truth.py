from __future__ import annotations

import json

import pytest

from moss_transcribe_diarize.app.live_service_runtime import hash_config
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.live_provider_truth import (
    DEVELOPMENT_60S_PHASE,
    HOLDOUT_300S_PHASE,
    LiveVadTruth,
    LiveVadTruthError,
    compare_live_provider_candidates,
    main,
)


def _sha(label: str) -> str:
    return hash_config({"test": label})


def _interval(start: int, end: int) -> dict:
    return {"start_sample": start, "end_sample": end}


def _truth(sample_count: int = 60 * LIVE_SAMPLE_RATE) -> dict:
    return {
        "schema_version": 1,
        "fixture_sha256": _sha("fixture"),
        "fixture_sample_rate": LIVE_SAMPLE_RATE,
        "fixture_sample_count": sample_count,
        "annotation_provenance": "annotator-a local reviewed manifest",
        "review_provenance": "reviewer-b independent local audit",
        "provider_blind": True,
        "speech_intervals": [_interval(100, 400)],
        "non_speech_intervals": [_interval(0, 100), _interval(500, sample_count)],
        "uncertain_intervals": [_interval(400, 500)],
        "safe_end_intervals": [_interval(500, 700)],
    }


def _candidate(
    *,
    config_hash: str | None = None,
    sample_count: int = 60 * LIVE_SAMPLE_RATE,
    wrong_uncertain: bool = True,
    endpoint_reason: str = "end_silence",
) -> dict:
    observations = [
        {"start_sample": 0, "end_sample": 100, "speech_present": False},
        {"start_sample": 100, "end_sample": 400, "speech_present": True},
        {"start_sample": 400, "end_sample": 500, "speech_present": wrong_uncertain},
        {"start_sample": 500, "end_sample": sample_count, "speech_present": False},
    ]
    return {
        "schema_version": 1,
        "name": "candidate-a",
        "config_hash": config_hash or _sha("config-a"),
        "fixture_sha256": _sha("fixture"),
        "observations": observations,
        "endpoint_spans": [{"start_sample": 0, "end_sample": 600, "reason": endpoint_reason}],
    }


def _thresholds() -> dict[str, float]:
    return {
        "min_speech_recall": 0.9,
        "max_false_positive_rate": 0.1,
        "min_safe_end_recall": 1.0,
    }


def test_truth_schema_validates_provider_blind_exact_partition():
    truth = LiveVadTruth.from_mapping(_truth())

    assert truth.fixture_sample_rate == 16000
    assert truth.provider_blind is True
    assert truth.uncertain_intervals[0].start_sample == 400


def test_truth_validation_rejects_overlap_gap_and_non_independent_review():
    payload = _truth()
    payload["speech_intervals"] = [_interval(100, 450)]

    with pytest.raises(LiveVadTruthError, match="partition"):
        LiveVadTruth.from_mapping(payload)

    payload = _truth()
    payload["review_provenance"] = payload["annotation_provenance"]

    with pytest.raises(LiveVadTruthError, match="independent"):
        LiveVadTruth.from_mapping(payload)

    payload = _truth()
    payload["provider_blind"] = False

    with pytest.raises(LiveVadTruthError, match="provider blind"):
        LiveVadTruth.from_mapping(payload)


def test_truth_validation_rejects_safe_end_outside_non_speech():
    payload = _truth()
    payload["safe_end_intervals"] = [_interval(200, 300)]

    with pytest.raises(LiveVadTruthError, match="inside non_speech"):
        LiveVadTruth.from_mapping(payload)


def test_compare_excludes_uncertain_intervals_from_threshold_scoring():
    result = compare_live_provider_candidates(
        _truth(),
        [_candidate(wrong_uncertain=True)],
        phase=DEVELOPMENT_60S_PHASE,
        thresholds=_thresholds(),
    )

    candidate = result["results"][0]
    assert candidate["accepted"] is True
    assert candidate["confusion"] == {"tp": 300, "fn": 0, "tn": 60 * LIVE_SAMPLE_RATE - 400, "fp": 0}
    assert candidate["uncertain_samples_excluded"] == 100
    assert result["locked_config_hash"] == candidate["config_hash"]


def test_safe_end_requires_end_silence_not_hard_cap_or_stop_flush():
    result = compare_live_provider_candidates(
        _truth(),
        [_candidate(endpoint_reason="hard_cap")],
        phase=DEVELOPMENT_60S_PHASE,
        thresholds=_thresholds(),
    )

    candidate = result["results"][0]
    assert candidate["accepted"] is False
    assert candidate["safe_end"]["wrong_reason"] == 1
    assert "safe_end_recall below threshold" in candidate["failures"]


def test_calibration_lock_only_for_registered_60_second_phase():
    with pytest.raises(LiveVadTruthError, match="60-second"):
        compare_live_provider_candidates(
            _truth(sample_count=LIVE_SAMPLE_RATE),
            [_candidate(sample_count=LIVE_SAMPLE_RATE)],
            phase=DEVELOPMENT_60S_PHASE,
            thresholds=_thresholds(),
        )

    with pytest.raises(LiveVadTruthError, match="produces"):
        compare_live_provider_candidates(
            _truth(),
            [_candidate()],
            phase=DEVELOPMENT_60S_PHASE,
            thresholds=_thresholds(),
            locked_config_hash=_sha("locked"),
        )


def test_holdout_accepts_exact_locked_hash_and_rejects_retuning():
    locked = _sha("locked")
    accepted = compare_live_provider_candidates(
        _truth(sample_count=300 * LIVE_SAMPLE_RATE),
        [_candidate(config_hash=locked, sample_count=300 * LIVE_SAMPLE_RATE)],
        phase=HOLDOUT_300S_PHASE,
        thresholds=_thresholds(),
        locked_config_hash=locked,
    )
    retuned = compare_live_provider_candidates(
        _truth(sample_count=300 * LIVE_SAMPLE_RATE),
        [_candidate(config_hash=_sha("retuned"), sample_count=300 * LIVE_SAMPLE_RATE)],
        phase=HOLDOUT_300S_PHASE,
        thresholds=_thresholds(),
        locked_config_hash=locked,
    )

    assert accepted["locked_config_hash"] == locked
    assert accepted["results"][0]["accepted"] is True
    assert retuned["results"][0]["accepted"] is False
    assert "holdout candidate config_hash does not match locked_config_hash" in retuned["results"][0]["failures"]


def test_thresholds_are_explicit_validated_and_reported():
    with pytest.raises(TypeError):
        compare_live_provider_candidates(
            _truth(),
            [_candidate()],
            phase=DEVELOPMENT_60S_PHASE,
        )
    with pytest.raises(LiveVadTruthError, match="explicitly provide"):
        compare_live_provider_candidates(
            _truth(),
            [_candidate()],
            phase=DEVELOPMENT_60S_PHASE,
            thresholds={"min_speech_recall": 0.9},
        )

    result = compare_live_provider_candidates(
        _truth(),
        [_candidate()],
        phase=DEVELOPMENT_60S_PHASE,
        thresholds=_thresholds(),
    )

    assert result["thresholds"] == _thresholds()


def test_truth_cli_compares_json_files(tmp_path, capsys):
    truth_path = tmp_path / "truth.json"
    candidate_path = tmp_path / "candidate.json"
    truth_path.write_text(json.dumps(_truth(), sort_keys=True), encoding="utf-8")
    candidate_path.write_text(json.dumps(_candidate(), sort_keys=True), encoding="utf-8")

    rc = main(
        [
            "--truth",
            str(truth_path),
            "--candidate",
            str(candidate_path),
            "--phase",
            DEVELOPMENT_60S_PHASE,
            "--min-speech-recall",
            "0.9",
            "--max-false-positive-rate",
            "0.1",
            "--min-safe-end-recall",
            "1.0",
            "--json",
        ]
    )

    out = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert out["results"][0]["accepted"] is True
    assert out["thresholds"] == _thresholds()
