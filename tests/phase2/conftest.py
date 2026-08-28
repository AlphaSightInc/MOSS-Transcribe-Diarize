from __future__ import annotations

import sqlite3

import pytest

from moss_transcribe_diarize.app import phase2


@pytest.fixture(autouse=True)
def permit_test_runner_sqlite(monkeypatch: pytest.MonkeyPatch):
    """Semantic tests use host SQLite; the packaged exact runtime has its own gate tests."""

    monkeypatch.setattr(phase2, "REQUIRED_SQLITE_RUNTIME", sqlite3.sqlite_version)
