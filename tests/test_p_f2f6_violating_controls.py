"""Frozen-tree violating controls for F2 raw custody and F6 observer isolation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "prototypes/p-f2f6/run.py"


def _prototype_state() -> dict:
    completed = subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)},
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


@pytest.mark.xfail(
    strict=True,
    reason="F2 frozen capture is post-normalization and loses contained raw S02",
)
def test_f2_frozen_capture_retains_contained_raw_terminal_span():
    state = _prototype_state()
    assert "S02" in state["frozen_product"]["captured_labels"]


@pytest.mark.xfail(
    strict=True,
    reason="F6 frozen observer imports and reconstructs the identity preparer",
)
def test_f6_frozen_observer_has_no_preparer_decision_dependency():
    source = (
        ROOT / "moss_transcribe_diarize/app/terminal_label_capture.py"
    ).read_text(encoding="utf-8")
    assert "BoundedCausalIdentityPreparer" not in source
    assert "prepare_revision" not in source
    assert "_EvidenceObserver" not in source
