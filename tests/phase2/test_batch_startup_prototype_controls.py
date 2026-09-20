"""Violating controls for R4-5; expected to fail on unpatched 89f833ac."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


def _prototype():
    path = Path(__file__).parents[2] / "prototypes" / "batch-startup" / "prototype.py"
    spec = importlib.util.spec_from_file_location("batch_startup_prototype", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("ingress", ["file", "url"])
@pytest.mark.xfail(
    strict=True,
    reason=(
        "R4-5 violating control: base lifespan interrupts a valid retained File/URL "
        "prefix instead of resuming it"
    ),
)
def test_r4_5_base_lifespan_resumes_valid_retained_prefix(ingress: str) -> None:
    state = asyncio.run(_prototype().base_lifespan_control(ingress))
    assert state == {
        "status": "completed",
        "transcript_version": 1,
        "delegate_calls": list(range(40, 101)),
    }
