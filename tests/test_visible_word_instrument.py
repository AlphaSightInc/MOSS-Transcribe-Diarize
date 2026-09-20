from __future__ import annotations

import json
import wave

import pytest

from tools.qualify.visible_word_headed import (
    _chromium_args,
    _dom_segments,
    _frame_payload,
    _observation_due,
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


def test_finally_wrong_word_nulls_an_earlier_correct_time():
    result = evaluate_visible_word_stream(
        _references("alpha"),
        (_observe(1.0, "alpha"), _observe(2.0, "wrong")),
        clock_name="api_arrival",
    )

    word = result["words"][0]
    assert word["final_status"] == "wrong"
    assert word["first_correct_sec"] is None
    assert word["stable_correct_sec"] is None
    assert "first_correct_latency_sec" not in word
    assert "stable_correct_latency_sec" not in word


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
    assert result["phrase_end_diagnostics"]["stable_complete_distribution"] == {
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
        visible_word_percentile(
            result,
            field="stable_correct_sec",
            quantile=0.95,
        )


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
        (
            row.id,
            row.source_interval_id,
            row.text,
            row.source_start_sec,
            row.source_end_sec,
        )
        for row in references
    ] == [
        ("phrase-a:0", "phrase-a", "alpha", 0.25, 1.25),
        ("phrase-a:1", "phrase-a", "one", 0.25, 1.25),
        ("phrase-b:0", "phrase-b", "beta", 1.25, 2.5),
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


def test_dom_row_cannot_credit_later_same_word_outside_its_owned_span():
    """Falsifies inventing a row end from the playback frontier."""

    references = reference_words_from_intervals(
        (
            {"id": "earlier", "text": "alpha", "start": 0.0, "end": 1.0},
            {"id": "later", "text": "alpha", "start": 10.0, "end": 11.0},
        )
    )
    segments, reason = _dom_segments(
        [{"start": 0.0, "end": 1.0, "text": "alpha"}],
    )
    assert reason is None
    result = evaluate_visible_word_stream(
        references,
        (TranscriptObservation(12.0, segments),),
        clock_name="rendered_dom",
    )

    earlier, later = result["words"]
    assert earlier["final_status"] == "correct"
    assert earlier["first_correct_sec"] == 12.0
    assert later["final_status"] == "missing"
    assert later["first_correct_sec"] is None
    assert result["phrase_end_diagnostics"]["phrases"][0][
        "first_complete_delay_sec"
    ] == 11.0
    assert all("latency" not in key for row in result["words"] for key in row)


def test_merged_dom_row_keeps_custody_with_each_constituent_segment():
    """Falsifies using a merged row's outer span as word custody."""

    references = reference_words_from_intervals(
        (
            {"id": "earlier", "text": "alpha", "start": 0.0, "end": 1.0},
            {"id": "later", "text": "alpha", "start": 10.0, "end": 11.0},
        )
    )
    segments, reason = _dom_segments(
        [
            {
                "start": 0.0,
                "end": 11.0,
                "text": "alpha ...",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "alpha"},
                    {"start": 10.0, "end": 11.0, "text": "..."},
                ],
            }
        ]
    )
    assert reason is None
    result = evaluate_visible_word_stream(
        references,
        (TranscriptObservation(12.0, segments),),
        clock_name="rendered_dom",
    )

    assert [
        (word["final_status"], word["first_correct_sec"])
        for word in result["words"]
    ] == [("correct", 12.0), ("missing", None)]


def test_dom_rows_without_published_spans_are_unmeasured_and_earn_no_credit():
    """Falsifies silently dropping spanless rows or inventing their custody."""

    references = _references("alpha")
    segments, reason = _dom_segments([{"text": "alpha"}])
    result = evaluate_visible_word_surfaces(
        references,
        api_observations=(_observe(1.0, "alpha"),),
        rendered_observations=(TranscriptObservation(1.0, segments),),
        rendered_unmeasured_reason=reason,
    )

    assert segments == ()
    assert result["rendered_dom"] == {
        "status": "UNMEASURED",
        "reason": "rendered row lacks its model-state source span",
        "full_denominator": 1,
    }
    assert "words" not in result["rendered_dom"]


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
    assert result["phrase_end_diagnostics"]["phrases"][0][
        "first_complete_delay_sec"
    ] == 1.0


def test_repeated_word_does_not_credit_an_omitted_later_phrase():
    """Falsifies reusing an earlier repeated token for an absent later phrase."""

    references = reference_words_from_intervals(
        (
            {"id": "early", "text": "alpha", "start": 0.0, "end": 1.0},
            {"id": "late", "text": "alpha beta", "start": 10.0, "end": 11.0},
        )
    )
    result = evaluate_visible_word_stream(
        references,
        (
            TranscriptObservation(
                12.0, (TranscriptSegment(0.0, 1.0, "alpha"),)
            ),
        ),
        clock_name="rendered_dom",
    )

    assert [row["final_status"] for row in result["words"]] == [
        "correct",
        "missing",
        "missing",
    ]


def test_one_displayed_row_can_carry_two_reference_phrases():
    """Falsifies requiring one rendered row per source phrase."""

    references = reference_words_from_intervals(
        (
            {"id": "first", "text": "alpha beta", "start": 0.0, "end": 1.0},
            {"id": "second", "text": "gamma", "start": 1.0, "end": 2.0},
        )
    )
    result = evaluate_visible_word_stream(
        references,
        (
            TranscriptObservation(
                3.0, (TranscriptSegment(0.0, 2.0, "alpha beta gamma"),)
            ),
        ),
        clock_name="rendered_dom",
    )

    diagnostics = result["phrase_end_diagnostics"]
    assert result["final_correct"] == 3
    assert diagnostics["full_denominator"] == 2
    assert [row["first_complete_delay_sec"] for row in diagnostics["phrases"]] == [
        2.0,
        1.0,
    ]


def test_revision_that_changes_earlier_text_nulls_its_phrase_clock():
    """Falsifies retaining credit after an earlier displayed phrase is revised."""

    references = reference_words_from_intervals(
        ({"id": "first", "text": "alpha", "start": 0.0, "end": 1.0},)
    )
    result = evaluate_visible_word_stream(
        references,
        (
            TranscriptObservation(
                2.0, (TranscriptSegment(0.0, 1.0, "alpha"),)
            ),
            TranscriptObservation(
                3.0, (TranscriptSegment(0.0, 1.0, "beta"),)
            ),
        ),
        clock_name="rendered_dom",
    )

    assert result["words"][0]["final_status"] == "wrong"
    assert result["words"][0]["first_correct_sec"] is None
    assert result["phrase_end_diagnostics"]["phrases"][0][
        "first_complete_delay_sec"
    ] is None


def test_unchanged_text_is_observed_when_a_phrase_end_is_crossed():
    """Falsifies recording only text revisions and missing a phrase-end crossing."""

    segments = (TranscriptSegment(0.0, 2.0, "alpha"),)
    assert _observation_due(
        segments,
        previous_segments=segments,
        previous_elapsed_sec=1.0,
        elapsed_sec=2.5,
        source_ends=(2.0,),
    )
    result = evaluate_visible_word_stream(
        reference_words_from_intervals(
            ({"id": "first", "text": "alpha", "start": 0.0, "end": 2.0},)
        ),
        (TranscriptObservation(1.0, segments), TranscriptObservation(2.5, segments)),
        clock_name="rendered_dom",
    )

    assert result["words"][0]["first_correct_sec"] == 2.5
    assert result["phrase_end_diagnostics"]["phrases"][0][
        "first_complete_delay_sec"
    ] == 0.5


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
