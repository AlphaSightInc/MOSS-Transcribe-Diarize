from __future__ import annotations

import json
import wave

import pytest

from tools.qualify.visible_word_headed import (
    _chromium_args,
    _frame_payload,
    _read_pcm16,
    _read_reference,
)
from tools.qualify.visible_words import (
    ReferenceWord,
    TranscriptObservation,
    TranscriptSegment,
    evaluate_visible_word_stream,
    evaluate_visible_word_surfaces,
    reference_words_from_intervals,
    require_visible_word_evidence,
    visible_word_percentile,
)


def _references(*words: str) -> tuple[ReferenceWord, ...]:
    return tuple(
        ReferenceWord(
            id=f"word-{index}",
            text=word,
            source_start_sec=float(index),
            source_end_sec=float(index + 1),
        )
        for index, word in enumerate(words)
    )


def _observe(at: float, text: str) -> TranscriptObservation:
    return TranscriptObservation(
        elapsed_sec=at,
        segments=(TranscriptSegment(0.0, 100.0, text),),
    )


def test_perfect_immediate_fixture_is_finite_and_stable():
    result = evaluate_visible_word_stream(
        _references("alpha", "beta"),
        (_observe(2.0, "alpha beta"),),
        clock_name="api_arrival",
    )

    assert result["full_denominator"] == 2
    assert result["final_correct"] == 2
    assert all(row["first_correct_sec"] is not None for row in result["words"])
    assert all(
        row["first_correct_sec"] == row["stable_correct_sec"]
        for row in result["words"]
    )


def test_delayed_correction_separates_first_and_stable():
    result = evaluate_visible_word_stream(
        _references("alpha", "beta"),
        (_observe(2.0, "alpha wrong"), _observe(4.0, "alpha beta")),
        clock_name="api_arrival",
    )

    beta = result["words"][1]
    assert beta["first_correct_sec"] == 4.0
    assert beta["stable_correct_sec"] == 4.0
    assert result["words"][0]["first_correct_sec"] == 2.0


def test_correct_wrong_correct_moves_stable_to_final_correction():
    result = evaluate_visible_word_stream(
        _references("alpha"),
        (
            _observe(1.0, "alpha"),
            _observe(2.0, "wrong"),
            _observe(3.0, "alpha"),
        ),
        clock_name="rendered_dom",
    )

    word = result["words"][0]
    assert word["first_correct_sec"] == 1.0
    assert word["stable_correct_sec"] == 3.0


def test_wrong_and_omitted_words_stay_null_and_in_full_denominator():
    result = evaluate_visible_word_stream(
        _references("alpha", "beta", "gamma"),
        (_observe(5.0, "wrong beta"),),
        clock_name="api_arrival",
    )

    assert result["full_denominator"] == 3
    assert result["final_correct"] == 1
    assert result["final_wrong"] == 1
    assert result["final_missing"] == 1
    assert result["stable_correct_distribution"] == {
        "full_denominator": 3,
        "finite_count": 1,
        "null_count": 2,
        "population_p50_sec": None,
        "population_p95_sec": None,
        "finite_only": {
            "minimum_sec": 3.0,
            "p50_sec": 3.0,
            "p95_sec": 3.0,
            "maximum_sec": 3.0,
        },
    }
    by_id = {row["reference_word_id"]: row for row in result["words"]}
    for key in ("word-0", "word-2"):
        assert by_id[key]["first_correct_sec"] is None
        assert by_id[key]["stable_correct_sec"] is None
    with pytest.raises(ValueError, match="full denominator"):
        visible_word_percentile(result, field="stable_correct_latency_sec", quantile=0.95)


def test_bucket_coverage_only_result_is_refused_as_visible_word_evidence():
    with pytest.raises(ValueError, match="ordered reference-word"):
        require_visible_word_evidence(
            {"bucket_coverage": 0.99, "covered_buckets": 99, "buckets": 100}
        )


def test_reference_intervals_supply_ordered_ids_and_source_end_times():
    references = reference_words_from_intervals(
        (
            {"id": "phrase-a", "text": "Alpha one", "start": 0.25, "end": 1.25},
            {"id": "phrase-b", "text": "Beta", "start": 1.25, "end": 2.5},
        )
    )

    assert [
        (row.id, row.text, row.source_start_sec, row.source_end_sec)
        for row in references
    ] == [
        ("phrase-a:0", "alpha", 0.25, 1.25),
        ("phrase-a:1", "one", 0.25, 1.25),
        ("phrase-b:0", "beta", 1.25, 2.5),
    ]


def test_headed_reference_reader_preserves_intervals_for_word_expansion(tmp_path):
    source = tmp_path / "reference.jsonl"
    source.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"id": "kept", "text": "Alpha one", "start": 0.25, "end": 1.25},
                {"id": "later", "text": "Beta", "start": 2.0, "end": 3.0},
            )
        )
        + "\n"
    )

    references = reference_words_from_intervals(_read_reference(source, 2.5))

    assert [
        (row.id, row.text, row.source_start_sec, row.source_end_sec)
        for row in references
    ] == [
        ("kept:0", "alpha", 0.25, 1.25),
        ("kept:1", "one", 0.25, 1.25),
    ]


def test_headed_chromium_stays_muted_without_physical_capture():
    args = _chromium_args()

    assert args == ["--mute-audio"]


def test_headed_live_frame_preserves_lane_sequence_pcm_and_silence():
    payload = _frame_payload(
        "microphone",
        3,
        b"\0\0\0\0",
        frame_samples=2,
        sample_rate=4,
        device_epoch=7,
    )

    assert set(payload) == {
        "lane",
        "sequence",
        "capture_timestamp_ns",
        "device_epoch",
        "pcm_base64",
        "sample_count",
        "sample_rate",
        "silent",
        "discontinuity",
    }
    assert payload["lane"] == "microphone"
    assert payload["sequence"] == 3
    assert payload["capture_timestamp_ns"] == 1_500_000_007
    assert payload["pcm_base64"] == "AAAAAA=="
    assert payload["silent"] is True


def test_headed_lane_reader_accepts_only_the_exact_pcm_contract(tmp_path):
    source = tmp_path / "lane.wav"
    with wave.open(str(source), "wb") as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(4)
        target.writeframes(b"\1\0" * 4)

    assert _read_pcm16(source, 4, 1.0) == b"\1\0" * 4
    with pytest.raises(ValueError, match="exactly 2 seconds"):
        _read_pcm16(source, 4, 2.0)


def test_repeated_word_cannot_credit_the_wrong_source_interval():
    references = (
        ReferenceWord("early-alpha", "alpha", 1.0, 0.0),
        ReferenceWord("late-alpha", "alpha", 11.0, 10.0),
    )
    result = evaluate_visible_word_stream(
        references,
        (
            TranscriptObservation(
                2.0, (TranscriptSegment(0.0, 1.0, "alpha"),)
            ),
        ),
        clock_name="api_arrival",
    )

    assert result["words"][0]["final_status"] == "correct"
    assert result["words"][1]["final_status"] == "missing"
    assert result["words"][1]["first_correct_sec"] is None


def test_word_is_not_credited_before_its_source_interval_finishes():
    reference = (ReferenceWord("interval-alpha", "alpha", 10.0, 0.0),)
    result = evaluate_visible_word_stream(
        reference,
        (
            TranscriptObservation(
                3.0, (TranscriptSegment(0.0, 5.0, "alpha"),)
            ),
            TranscriptObservation(
                11.0, (TranscriptSegment(0.0, 5.0, "alpha"),)
            ),
        ),
        clock_name="api_arrival",
    )

    assert result["words"][0]["first_correct_sec"] == 11.0
    assert result["words"][0]["first_correct_latency_sec"] == 1.0


def test_api_and_dom_clocks_remain_separate():
    result = evaluate_visible_word_surfaces(
        _references("alpha"),
        api_observations=(_observe(1.0, "alpha"),),
        rendered_observations=(_observe(1.4, "alpha"),),
    )

    assert result["api"]["clock"] == "api_arrival"
    assert result["rendered_dom"]["clock"] == "rendered_dom"
    assert result["api"]["words"][0]["first_correct_sec"] == 1.0
    assert result["rendered_dom"]["words"][0]["first_correct_sec"] == 1.4
    assert "api_to_dom_sec" not in result
