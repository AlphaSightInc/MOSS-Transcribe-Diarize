"""IDEA-002 contract tests for bounded vLLM window transcription."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.speaker_identity import IdentityResolution
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


class RecordingIdentityResolver:
    requires_window_audio = True

    def __init__(self):
        self.calls: list[dict[str, int]] = []

    def contract(self) -> dict:
        return {
            "schema_version": 2,
            "config": {
                "tier_a": {
                    "min_overlap_support_seconds": 2.0,
                    "min_overlap_dice": 0.75,
                    "mutual_margin_seconds": 1.0,
                },
                "tier_b": {
                    "enabled": True,
                    "min_segment_seconds": 2.0,
                    "max_segments_per_node": 3,
                    "similarity": 0.70,
                    "margin": 0.20,
                },
            },
            "provider": {
                "provider": "fake",
                "revision": "test",
                "state_sha256": "0" * 64,
                "embedding_dimension": 256,
                "device": "cpu",
            },
            "availability": {"available": True, "reason": None},
        }

    def resolve(self, windows, local_results, *, window_audio_paths) -> IdentityResolution:
        self.calls.append(
            {
                "windows": len(windows),
                "local_results": len(local_results),
                "window_audio_paths": len(window_audio_paths),
            }
        )
        summary = {
            "schema_version": 2,
            "accepted_edges": 0,
            "tier_a_accepted": 0,
            "tier_b_status": "available",
            "tier_b_accepted": 2,
            "false_accepted_edges": 0,
            "fragmented_recurring_speakers": 0,
        }
        diagnostics = {
            "schema_version": 2,
            "config": self.contract()["config"],
            "contract": self.contract(),
            "tier_b": {"status": "available", "proposals": []},
        }
        return IdentityResolution(
            relabeled_results=local_results,
            summary=summary,
            diagnostics=diagnostics,
        )


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


def test_windowed_runner_uses_injected_identity_resolver_and_runtime_contract(tmp_path):
    resolver = RecordingIdentityResolver()
    extractor = RecordingExtractor()
    runner = WindowedRunner(
        FakeRunner(
            [
                result("[10][S01]first[20]"),
                result("[10][S02]second[20]"),
                result("[10][S03]third[20]"),
            ]
        ),
        duration_probe=lambda _: 300.0,
        window_extractor=extractor,
        identity_resolver=resolver,
    )
    source = tmp_path / "source.wav"
    source.write_bytes(b"source")

    stitched = runner.transcribe(source, max_new_tokens=12000)

    assert resolver.calls == [{"windows": 3, "local_results": 3, "window_audio_paths": 3}]
    assert runner.runtime_info()["speaker_identity"] == resolver.contract()
    assert stitched.identity_summary["tier_b_status"] == "available"
    assert stitched.identity_summary["tier_b_accepted"] == 2


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


@pytest.mark.parametrize("condition", [
    "extraction_exception", "decoder_exception", "no_generated_tokens", "empty_text", "unparseable_text",
])
def test_window_failure_identifies_condition_and_extent_without_content(tmp_path, condition):
    class Decoder:
        model_path = "test"
        def transcribe(self, path, **kwargs):
            if Path(path).name == "window-0000.wav":
                return result("[0][S01]hello[1]")
            if condition == "decoder_exception":
                raise RuntimeError("SECRET response")
            return result("" if condition == "empty_text" else "PRIVATE unparseable text",
                          generated_tokens=0 if condition == "no_generated_tokens" else 5)
    def extract(source, destination, **kwargs):
        if condition == "extraction_exception" and kwargs["start_seconds"] == 120:
            raise OSError("SECRET path")
        Path(destination).write_bytes(b"wav")
    runner = WindowedRunner(Decoder(), duration_probe=lambda p: 600, window_extractor=extract)
    with pytest.raises(WindowTranscriptionError) as caught:
        runner.transcribe(tmp_path / "input.wav")
    expected = {"condition": condition, "window_index": 1,
                "start_seconds": 120.0, "end_seconds": 270.0}
    if condition in ("decoder_exception", "extraction_exception"):
        expected.update(exception_type="RuntimeError" if condition == "decoder_exception" else "OSError",
                        exception_message="[redacted: unstructured exception message]")
    assert caught.value.to_dict() == expected
    assert "SECRET" not in str(caught.value) and "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("seconds", [50, 600])
@pytest.mark.parametrize("condition", ["no_generated_tokens", "empty_text", "unparseable_text"])
def test_typed_decoder_empty_outcome_keeps_cause_on_short_and_long_tapes(tmp_path, seconds, condition):
    from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError, EmptyTranscriptCause
    class Decoder:
        model_path = "test"
        def transcribe(self, *args, **kwargs):
            raise EmptyTranscriptionError("SECRET", cause=EmptyTranscriptCause(condition), text="PRIVATE")
    runner = WindowedRunner(Decoder(), duration_probe=lambda p: seconds, window_extractor=RecordingExtractor())
    with pytest.raises(WindowTranscriptionError) as caught:
        runner.transcribe(tmp_path / "input.wav")
    assert caught.value.to_dict() == {"condition": condition, "window_index": 0,
                                     "start_seconds": 0.0, "end_seconds": min(seconds, 150),
                                     "exception_type": "EmptyTranscriptionError", "exception_message": condition}
    assert "SECRET" not in str(caught.value)


def test_structural_decoder_error_survives_window_and_event_projection(tmp_path):
    import wave
    from moss_transcribe_diarize.app.runner_composition import build_terminal_finalizer
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    from moss_transcribe_diarize.phase2_acceptance_external import _diagnostic_event

    class NoNetworkRunner(VllmRunner):
        def _build_fields(self, **kwargs):
            # Preserve the diagnostics regression after fixing the real missing prompt.
            absent = None
            return absent.strip()

        def _post_multipart(self, *args, **kwargs):
            pytest.fail('missing prompt must fail before HTTP')

    source = tmp_path / 'input.wav'
    with wave.open(str(source), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0\0' * 40000)
    runner = WindowedRunner(NoNetworkRunner(base_url='http://unused/v1', model='test'),
                            duration_probe=lambda p: 2.5)
    finalizer = build_terminal_finalizer(runner=runner, prompt=None, max_length=16384,
        max_new_tokens=12000, decoding='greedy', temperature=1., max_length_cap=16384)
    with pytest.raises(WindowTranscriptionError) as caught:
        runner.transcribe(source, **finalizer.transcribe_kwargs)
    details = caught.value.to_dict()
    assert details['exception_type'] == 'AttributeError'
    assert details['exception_message'] == "'NoneType' object has no attribute 'strip'"
    projected = _diagnostic_event({'kind': 'terminal_finalization_failed',
                                  'payload': {'window_failure': details}})
    assert projected['window_failure'] == details


@pytest.mark.parametrize('error', [RuntimeError('PRIVATE transcript Bearer SECRET'),
                                  OSError('PRIVATE path'),
                                  AttributeError('PRIVATE transcript')])
def test_wrapped_exception_diagnostics_do_not_copy_arbitrary_content(tmp_path, error):
    class Decoder:
        model_path = 'test'
        def transcribe(self, *args, **kwargs):
            raise error
    runner = WindowedRunner(Decoder(), duration_probe=lambda p: 2.5)
    with pytest.raises(WindowTranscriptionError) as caught:
        runner.transcribe(tmp_path / 'input.wav')
    details = caught.value.to_dict()
    assert details['exception_type'] == type(error).__name__
    assert details['exception_message'] == '[redacted: unstructured exception message]'
    assert 'PRIVATE' not in str(details) and 'SECRET' not in str(details)


def test_merged_tail_keeps_last_words_once_and_checkpoint_resume(tmp_path):
    runner, extractor = make_runner([
        result('[10][S01]first[11]'),
        result('[120][S01]last word[120.5]'),
    ], 240.5)
    source = tmp_path / 'source.wav'
    source.write_bytes(b'source')
    checkpoint = tmp_path / 'checkpoint'
    first = runner.transcribe(source, checkpoint_dir=checkpoint)
    assert first.text.count('last word') == 1
    from moss_transcribe_diarize.transcript_parser import parse_transcript
    last = parse_transcript(first.text)[-1]
    assert (last.start, last.end, last.text) == (240, 240.5, 'last word')
    assert first.completed_windows == 2
    assert [(start, duration) for _, _, start, duration in extractor.calls] == [(0, 150), (120, 120.5)]
    resumed = runner.transcribe(source, checkpoint_dir=checkpoint)
    assert resumed.text == first.text
    assert len(extractor.calls) == 2
    assert resumed.window_diagnostics == first.window_diagnostics
    assert resumed.window_diagnostics[-1]['condition'] == 'short_tail_window_merged'


def test_checkpoint_resume_rehydrates_completed_window_audio_for_identical_identity(tmp_path):
    class FailOnceRunner:
        model_path = "fake-vllm"

        def __init__(self, fail_at=None):
            self.fail_at = fail_at
            self.calls = []

        def transcribe(self, audio_path, **kwargs):
            del kwargs
            index = int(Path(audio_path).stem.rsplit("-", 1)[1])
            self.calls.append(index)
            if self.fail_at == index:
                self.fail_at = None
                raise RuntimeError("interrupted")
            return result(f"[60][S01]window {index}[61]")

    class AudioPathIdentity:
        requires_window_audio = True

        def contract(self):
            return {"schema_version": 1, "resolver": "audio-path-control"}

        def resolve(self, windows, local_results, *, window_audio_paths):
            missing = []
            relabeled = []
            for window, segments, audio_path in zip(
                windows, local_results, window_audio_paths, strict=True
            ):
                available = audio_path is not None and Path(audio_path).is_file()
                if not available:
                    missing.append(window.index)
                relabeled.append(
                    [replace(segment, speaker="S01" if available else "S00") for segment in segments]
                )
            return IdentityResolution(
                relabeled_results=relabeled,
                summary={"missing_audio_windows": missing},
                diagnostics={"schema_version": 1, "missing_audio_windows": missing},
            )

    source = tmp_path / "source.wav"
    source.write_bytes(b"source")
    clean_decoder = FailOnceRunner()
    clean = WindowedRunner(
        clean_decoder,
        duration_probe=lambda _: 360,
        window_extractor=RecordingExtractor(),
        identity_resolver=AudioPathIdentity(),
    ).transcribe(source, max_new_tokens=12000)

    resumed_decoder = FailOnceRunner(fail_at=2)
    extractor = RecordingExtractor()
    runner = WindowedRunner(
        resumed_decoder,
        duration_probe=lambda _: 360,
        window_extractor=extractor,
        identity_resolver=AudioPathIdentity(),
    )
    checkpoint = tmp_path / "checkpoint"
    with pytest.raises(WindowTranscriptionError):
        runner.transcribe(source, max_new_tokens=12000, checkpoint_dir=checkpoint)
    resumed = runner.transcribe(source, max_new_tokens=12000, checkpoint_dir=checkpoint)

    assert resumed.text == clean.text
    assert resumed.identity_summary == clean.identity_summary == {"missing_audio_windows": []}
    assert resumed_decoder.calls == [0, 1, 2, 2]
    assert [call[2] for call in extractor.calls] == [0, 120, 240, 0, 120, 240]
