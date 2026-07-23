"""IDEA-002 contract tests for bounded vLLM window transcription."""

from __future__ import annotations

from pathlib import Path

import pytest

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.windowed_transcription import (
    WindowTranscriptionError,
    WindowedRunner,
)


class FakeRunner:
    model_path = "fake-vllm"

    def __init__(self, results):
        self.results = iter(results)
        self.paths: list[Path] = []

    def transcribe(self, audio_path, **kwargs):
        self.paths.append(Path(audio_path))
        return next(self.results)


class RecordingExtractor:
    def __init__(self):
        self.calls: list[tuple[Path, Path, float, float]] = []

    def __call__(self, source, destination, *, start_seconds, duration_seconds):
        self.calls.append((Path(source), Path(destination), start_seconds, duration_seconds))
        Path(destination).write_bytes(b"slice")


def result(text, prompt_tokens=10, generated_tokens=5, elapsed=1.0):
    return TranscriptionResult(
        text=text,
        prompt_len=prompt_tokens,
        generated_tokens=generated_tokens,
        elapsed_sec=elapsed,
        model="fake-vllm",
        audio="slice.wav",
        decoding="greedy",
        temperature=None,
    )


def make_runner(results, duration):
    extractor = RecordingExtractor()
    runner = WindowedRunner(
        FakeRunner(results),
        duration_probe=lambda _: duration,
        window_extractor=extractor,
    )
    return runner, extractor


def test_300_second_result_has_bounded_plan_absolute_times_and_one_overlap_owner(tmp_path):
    runner, extractor = make_runner(
        [
            result("[129][S01]left[135][136][S02]duplicate[142]"),
            result("[9][S01]left[15][16][S02]duplicate[22][130][S01]right[136]"),
            result("[10][S02]right[16][50][S01]tail[56]"),
        ],
        300.0,
    )
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")

    stitched = runner.transcribe(source, max_new_tokens=12000)

    assert [(call[2], call[3]) for call in extractor.calls] == [
        (0.0, 150.0),
        (120.0, 150.0),
        (240.0, 60.0),
    ]
    assert all(duration <= 150.0 for _, _, _, duration in extractor.calls)
    assert stitched.text == (
        "[129][S01]left[135][136][S02]duplicate[142]"
        "[250][S01]right[256][290][S03]tail[296]"
    )
    assert stitched.prompt_len == 30
    assert stitched.generated_tokens == 15
    assert stitched.elapsed_sec == 3.0
    assert stitched.window_count == 3
    assert stitched.completed_windows == 3
    assert stitched.possibly_truncated is False


def test_windowed_result_relabels_overlap_copies_before_stitching(tmp_path):
    runner, _ = make_runner(
        [
            result("[125][S01]alice overlap[134][136][S02]bob owned[146]"),
            result("[5][S02]alice copy[14][16][S01]bob overlap[26]"),
        ],
        200.0,
    )
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")

    stitched = runner.transcribe(source, max_new_tokens=12000)

    assert stitched.text == "[125][S01]alice overlap[134][136][S02]bob overlap[146]"
    assert stitched.identity_summary == {
        "schema_version": 2,
        "accepted_edges": 2,
        "tier_a_accepted": 2,
        "tier_b_status": "disabled",
        "tier_b_accepted": 0,
        "false_accepted_edges": 0,
        "fragmented_recurring_speakers": 0,
    }
    assert stitched.identity_resolution is not None
    assert stitched.identity_resolution["summary"] == stitched.identity_summary


def test_short_input_delegates_without_slicing(tmp_path):
    expected = result("[0][S01]short[60]")
    runner, extractor = make_runner([expected], 60.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")

    actual = runner.transcribe(source, max_new_tokens=12000)

    assert actual.text == expected.text
    assert runner.delegate.paths == [source]
    assert extractor.calls == []
    assert actual.window_count == 1
    assert actual.completed_windows == 1


@pytest.mark.parametrize(
    "bad_result",
    [
        result("", generated_tokens=0),
        result("not compact transcript", generated_tokens=3),
    ],
)
def test_empty_or_unparseable_window_fails_whole_job(tmp_path, bad_result):
    runner, _ = make_runner([result("[0][S01]ok[120]"), bad_result], 300.0)
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")

    with pytest.raises(WindowTranscriptionError, match=r"window 1.*120.*270"):
        runner.transcribe(source, max_new_tokens=12000)


def test_contract_constants_are_150_second_window_and_120_second_stride():
    assert WindowedRunner.window_seconds == 150
    assert WindowedRunner.stride_seconds == 120
