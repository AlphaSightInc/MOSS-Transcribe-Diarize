"""Violating controls for R4-5; expected to fail on unpatched 89f833ac."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


def _prototype():
    path = Path(__file__).parents[2] / "prototypes" / "batch-startup" / "prototype.py"
    spec = importlib.util.spec_from_file_location("batch_startup_prototype", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


async def _settled_base_lifespan_control(module, ingress: str):
    """Observe eventual completion after the new background startup coordinator."""

    snapshot = module._snapshot

    async def settled_snapshot(app, seed):
        coordinator = app.state.phase2_file_tasks._retained_resume_task
        if coordinator is not None:
            await coordinator
        entry = app.state.phase2_file_tasks._tasks.get(seed.meeting_id)
        if entry is not None:
            await entry.task
        return await snapshot(app, seed)

    module._snapshot = settled_snapshot
    return await module.base_lifespan_control(ingress)


@pytest.mark.parametrize("ingress", ["file", "url"])
def test_r4_5_base_lifespan_resumes_valid_retained_prefix(ingress: str) -> None:
    module = _prototype()
    state = asyncio.run(_settled_base_lifespan_control(module, ingress))
    assert state == {
        "status": "completed",
        "transcript_version": 1,
        "delegate_calls": list(range(40, 101)),
    }
