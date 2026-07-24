from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Callable

import pytest

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.speaker_identity import IdentityResolution
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner


WINDOW_TRANSCRIPTS = {
    0: "[129][S01]left[135][136][S02]duplicate[142]",
    1: "[9][S01]left[15][16][S02]duplicate[22][130][S01]right[136]",
    2: "[10][S02]right[16][50][S01]tail[56]",
}
EXPECTED_STITCHED = (
    "[129][S01]left[135][136][S02]duplicate[142]"
    "[250][S01]right[256][290][S03]tail[296]"
)


class RecordingDelegate:
    model_path = "fake-vllm"

    def __init__(self, *, fail_once: set[int] | None = None):
        self.calls: list[int] = []
        self.kwargs: list[dict] = []
        self.fail_once = set(fail_once or set())

    def transcribe(self, audio_path, **kwargs):
        window_index = _window_index(audio_path)
        self.calls.append(window_index)
        self.kwargs.append(dict(kwargs))
        if window_index in self.fail_once:
            self.fail_once.remove(window_index)
            raise RuntimeError(f"interrupted window {window_index}")
        return _result(WINDOW_TRANSCRIPTS[window_index], window_index)


class RejectingDelegate:
    model_path = "fake-vllm"

    def __init__(self):
        self.calls = 0

    def transcribe(self, audio_path, **kwargs):
        self.calls += 1
        raise AssertionError("checkpoint rejection must happen before model invocation")


class RecordingExtractor:
    def __init__(self):
        self.calls: list[tuple[float, float]] = []

    def __call__(self, source, destination, *, start_seconds, duration_seconds):
        self.calls.append((start_seconds, duration_seconds))
        Path(destination).write_bytes(b"slice")


class StaticIdentityResolver:
    def __init__(self, *, tier_b_enabled: bool):
        self.tier_b_enabled = tier_b_enabled

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
                    "enabled": self.tier_b_enabled,
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
            "availability": {"available": self.tier_b_enabled, "reason": None},
        }

    def resolve(self, windows, local_results, *, window_audio_paths) -> IdentityResolution:
        del windows, window_audio_paths
        summary = {
            "schema_version": 2,
            "accepted_edges": 0,
            "tier_a_accepted": 0,
            "tier_b_status": "available" if self.tier_b_enabled else "disabled",
            "tier_b_accepted": 0,
            "false_accepted_edges": 0,
            "fragmented_recurring_speakers": 0,
        }
        diagnostics = {
            "schema_version": 2,
            "config": self.contract()["config"],
            "contract": self.contract(),
            "tier_b": {"status": summary["tier_b_status"], "proposals": []},
        }
        return IdentityResolution(
            relabeled_results=local_results,
            summary=summary,
            diagnostics=diagnostics,
        )


def _result(text: str, window_index: int) -> TranscriptionResult:
    return TranscriptionResult(
        text=text,
        prompt_len=10 + window_index,
        generated_tokens=5 + window_index,
        elapsed_sec=1.0 + window_index,
        model="fake-vllm",
        audio=f"window-{window_index:04d}.wav",
        decoding="greedy",
        temperature=None,
    )


def _runner(
    delegate,
    tmp_path: Path,
    *,
    duration: float = 300.0,
    identity_resolver=None,
) -> tuple[WindowedRunner, RecordingExtractor]:
    extractor = RecordingExtractor()
    scratch_dir = tmp_path / "scratch"
    scratch_dir.mkdir(exist_ok=True)
    return (
        WindowedRunner(
            delegate,
            duration_probe=lambda _: duration,
            window_extractor=extractor,
            scratch_dir=scratch_dir,
            identity_resolver=identity_resolver,
        ),
        extractor,
    )


def _source(tmp_path: Path, payload: bytes = b"source-audio") -> Path:
    source = tmp_path / "source.wav"
    source.write_bytes(payload)
    return source


def _transcribe(runner: WindowedRunner, source: Path, checkpoint_dir: Path):
    return runner.transcribe(
        source,
        prompt="speaker labels",
        max_length=4096,
        max_new_tokens=12000,
        decoding="greedy",
        checkpoint_dir=checkpoint_dir,
    )


def _window_index(audio_path) -> int:
    match = re.search(r"window-(\d+)", Path(audio_path).stem)
    if match is None:
        raise AssertionError(f"expected extracted window path, got {audio_path}")
    return int(match.group(1))


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _manifest_path(checkpoint_dir: Path) -> Path:
    return checkpoint_dir / "manifest.json"


def _window_record(checkpoint_dir: Path, index: int) -> Path:
    key_prefixes = {
        0: "w000000-0-150000000",
        1: "w000001-120000000-270000000",
        2: "w000002-240000000-300000000",
    }
    matches = [
        path
        for path in checkpoint_dir.rglob(f"{key_prefixes[index]}*")
        if path.is_file() and not path.name.endswith(".tmp")
    ]
    assert len(matches) == 1, f"expected one committed record for window {index}, found {matches}"
    return matches[0]


def _assert_checkpoint_shape(checkpoint_dir: Path) -> None:
    manifest = _read_json(_manifest_path(checkpoint_dir))
    assert manifest["schema_version"] == 1
    assert manifest["contract_fingerprint"]
    assert manifest["plan"] == [
        {"index": 0, "start_us": 0, "end_us": 150000000, "own_start_us": 0, "own_end_us": 135000000},
        {
            "index": 1,
            "start_us": 120000000,
            "end_us": 270000000,
            "own_start_us": 135000000,
            "own_end_us": 255000000,
        },
        {
            "index": 2,
            "start_us": 240000000,
            "end_us": 300000000,
            "own_start_us": 255000000,
            "own_end_us": 300000000,
        },
    ]
    assert manifest["source_sha256"]
    assert manifest["model"] == "fake-vllm"
    assert manifest["inference"]["prompt"] == "speaker labels"
    for index in range(3):
        record = _read_json(_window_record(checkpoint_dir, index))
        assert record["schema_version"] == 1
        assert record["key"].startswith(f"w{index:06d}-")
        assert record["contract_fingerprint"] == manifest["contract_fingerprint"]
        assert record["raw_result"]["text"] == WINDOW_TRANSCRIPTS[index]
        assert record["checksum"]


def test_checkpointed_uninterrupted_three_window_result_persists_contract(tmp_path):
    checkpoint_dir = tmp_path / "checkpoint"
    source = _source(tmp_path)
    delegate = RecordingDelegate()
    runner, extractor = _runner(delegate, tmp_path)

    result = _transcribe(runner, source, checkpoint_dir)

    assert result.text == EXPECTED_STITCHED
    assert result.window_count == 3
    assert result.completed_windows == 3
    assert result.identity_resolution is not None
    assert delegate.calls == [0, 1, 2]
    assert [(start, duration) for start, duration in extractor.calls] == [
        (0.0, 150.0),
        (120.0, 150.0),
        (240.0, 60.0),
    ]
    assert all("checkpoint_dir" not in kwargs for kwargs in delegate.kwargs)
    _assert_checkpoint_shape(checkpoint_dir)
    manifest = _read_json(_manifest_path(checkpoint_dir))
    assert manifest["contract"]["identity"] == runner.identity_resolver.contract()
    assert manifest["identity"] == runner.identity_resolver.contract()
    assert "tier_b" not in manifest["contract"]


def test_resume_retries_interrupted_suffix_without_replaying_committed_window(tmp_path):
    source = _source(tmp_path)
    uninterrupted_delegate = RecordingDelegate()
    uninterrupted_runner, _ = _runner(uninterrupted_delegate, tmp_path)
    uninterrupted = _transcribe(uninterrupted_runner, source, tmp_path / "uninterrupted-checkpoint")

    checkpoint_dir = tmp_path / "resume-checkpoint"
    first_delegate = RecordingDelegate(fail_once={1})
    first_runner, _ = _runner(first_delegate, tmp_path)
    with pytest.raises(RuntimeError, match="interrupted window 1"):
        _transcribe(first_runner, source, checkpoint_dir)
    assert first_delegate.calls == [0, 1]
    assert _window_record(checkpoint_dir, 0).exists()

    (checkpoint_dir / "windows" / "w999999-stray.tmp").parent.mkdir(parents=True, exist_ok=True)
    (checkpoint_dir / "windows" / "w999999-stray.tmp").write_text("not a committed record", encoding="utf-8")

    resume_delegate = RecordingDelegate()
    resume_runner, _ = _runner(resume_delegate, tmp_path)
    resumed = _transcribe(resume_runner, source, checkpoint_dir)

    assert first_delegate.calls + resume_delegate.calls == [0, 1, 1, 2]
    assert resumed.text == uninterrupted.text
    assert resumed.identity_resolution == uninterrupted.identity_resolution
    assert resumed.window_count == 3
    assert resumed.completed_windows == 3
    _assert_checkpoint_shape(checkpoint_dir)


def _prepare_complete_checkpoint(tmp_path: Path) -> tuple[Path, Path]:
    checkpoint_dir = tmp_path / "checkpoint"
    source = _source(tmp_path)
    runner, _ = _runner(RecordingDelegate(), tmp_path)
    _transcribe(runner, source, checkpoint_dir)
    _assert_checkpoint_shape(checkpoint_dir)
    return source, checkpoint_dir


@pytest.mark.parametrize(
    "name, mutate, duration, prompt",
    [
        (
            "corrupt_record",
            lambda checkpoint_dir, source: _window_record(checkpoint_dir, 0).write_text("{not json", encoding="utf-8"),
            300.0,
            "speaker labels",
        ),
        (
            "incompatible_schema",
            lambda checkpoint_dir, source: _rewrite_manifest(
                checkpoint_dir,
                lambda manifest: {**manifest, "schema_version": 999},
            ),
            300.0,
            "speaker labels",
        ),
        (
            "source_sha_mismatch",
            lambda checkpoint_dir, source: source.write_bytes(b"changed source"),
            300.0,
            "speaker labels",
        ),
        (
            "contract_fingerprint_mismatch",
            lambda checkpoint_dir, source: None,
            300.0,
            "different prompt",
        ),
        (
            "plan_mismatch",
            lambda checkpoint_dir, source: None,
            301.0,
            "speaker labels",
        ),
        (
            "nonconsecutive_prefix",
            lambda checkpoint_dir, source: _window_record(checkpoint_dir, 1).unlink(),
            300.0,
            "speaker labels",
        ),
    ],
)
def test_invalid_checkpoint_is_rejected_before_delegate_invocation(
    tmp_path,
    name: str,
    mutate: Callable[[Path, Path], object],
    duration: float,
    prompt: str,
):
    source, checkpoint_dir = _prepare_complete_checkpoint(tmp_path)
    mutate(checkpoint_dir, source)
    delegate = RejectingDelegate()
    runner, _ = _runner(delegate, tmp_path, duration=duration)

    with pytest.raises(Exception, match="checkpoint|manifest|fingerprint|schema|checksum|source|plan|gap|prefix"):
        runner.transcribe(
            source,
            prompt=prompt,
            max_length=4096,
            max_new_tokens=12000,
            decoding="greedy",
            checkpoint_dir=checkpoint_dir,
        )

    assert delegate.calls == 0, name


def test_identity_contract_drift_rejects_checkpoint_before_delegate_invocation(tmp_path):
    checkpoint_dir = tmp_path / "checkpoint"
    source = _source(tmp_path)
    initial_runner, _ = _runner(
        RecordingDelegate(),
        tmp_path,
        identity_resolver=StaticIdentityResolver(tier_b_enabled=False),
    )
    _transcribe(initial_runner, source, checkpoint_dir)

    delegate = RejectingDelegate()
    drifted_runner, _ = _runner(
        delegate,
        tmp_path,
        identity_resolver=StaticIdentityResolver(tier_b_enabled=True),
    )

    with pytest.raises(Exception, match="checkpoint contract fingerprint mismatch"):
        _transcribe(drifted_runner, source, checkpoint_dir)

    assert delegate.calls == 0


def _rewrite_manifest(checkpoint_dir: Path, mutator: Callable[[dict], dict]) -> None:
    path = _manifest_path(checkpoint_dir)
    payload = deepcopy(_read_json(path))
    _write_json(path, mutator(payload))
