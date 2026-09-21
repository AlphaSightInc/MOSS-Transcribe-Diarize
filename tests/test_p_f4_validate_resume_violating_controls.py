"""Strict violating controls for the frozen runner-ownership defect."""

from __future__ import annotations

import inspect

import pytest

from moss_transcribe_diarize.app.phase2_file import FileMeetingTasks
from moss_transcribe_diarize.app.windowed_transcription import WindowedRunner


def test_windowed_runner_owns_resume_validation() -> None:
    assert callable(getattr(WindowedRunner, "validate_resume", None))


def test_file_checkpoint_validation_is_a_plain_runner_caller() -> None:
    source = inspect.getsource(FileMeetingTasks._checkpoint_is_valid)
    assert "validate_resume" in source
    assert "from .windowed_transcription import" not in source
    assert "_CheckpointStore" not in source
