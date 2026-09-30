from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def no_operator_gemini_key(monkeypatch: pytest.MonkeyPatch):
    """The operator fallback key comes from the environment; tests opt in with setenv."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def permit_test_runner_sqlite(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """Phase-2 semantic tests use host SQLite; exact-runtime gates override this.

    Keep registration at the common tests ancestor: pytest 9.1.1 can create a
    second Directory collector when explicit file arguments leave phase2 and
    return, losing autouse fixtures registered on the first collector.
    """
    if request.node.path.is_relative_to(Path(__file__).parent / "phase2"):
        from moss_transcribe_diarize.app import phase2

        if os.environ.get("MOSS_TEST_REAL_SQLITE") == "1":
            assert sqlite3.sqlite_version == phase2.REQUIRED_SQLITE_RUNTIME
            return
        monkeypatch.setattr(phase2, "REQUIRED_SQLITE_RUNTIME", sqlite3.sqlite_version)
