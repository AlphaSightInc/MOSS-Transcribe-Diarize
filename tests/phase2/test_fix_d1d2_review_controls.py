"""Review controls for per-owner retained filesystem failure isolation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from _browser_workspace_fixtures import seed_workspace
from test_retained_file_claim import _RestartDecoder, _app, _snapshot

from moss_transcribe_diarize.app.phase2 import Phase2Store
from moss_transcribe_diarize.app.phase2_file import RETAINED_FILE_WORK_CONTRACT_VERSION


async def _seed_owner(root: Path, *, manifest: object | None = None, status: str = "active"):
    store = await Phase2Store.open(root / "state.sqlite3")
    try:
        account, session = await seed_workspace(store, "account-a")
        handle = await store.workspace(account).create_meeting("file")
        if status != "active":
            await handle.finish(status)
    finally:
        await store.close()
    owner = root / "file-retained" / account.account_id / handle.meeting_id
    owner.mkdir(parents=True)
    (owner / "input.wav").write_bytes(b"retained source")
    (owner / "checkpoint").mkdir()
    (owner / "owner.json").write_text(
        json.dumps(
            {
                "account_id": account.account_id,
                "meeting_id": handle.meeting_id,
                "ingress": "file",
                "source": "input.wav",
                "checkpoint": "checkpoint",
                "contract_version": RETAINED_FILE_WORK_CONTRACT_VERSION,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    if manifest is not None:
        (owner / "checkpoint" / "manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
    return account, session, handle, owner


@pytest.mark.parametrize("status", ["interrupted", "active"])
def test_d1_unreadable_owner_directory_never_aborts_startup(tmp_path, status):
    async def exercise():
        _account, _session, handle, owner = await _seed_owner(tmp_path, status=status)
        (owner / "owner.json").unlink()
        owner.chmod(0)
        try:
            app = _app(tmp_path, _RestartDecoder())
            try:
                async with app.router.lifespan_context(app):
                    outcome = "ready"
            except Exception as exc:  # noqa: BLE001 - the abort is the finding
                outcome = f"ABORT {type(exc).__name__}: {exc}"
        finally:
            owner.chmod(0o700)
        return outcome

    outcome = asyncio.run(exercise())
    print(f"\nD1 [{status}] startup -> {outcome}")
    assert outcome == "ready", outcome


@pytest.mark.parametrize("status", ["active", "interrupted"])
def test_d2_unreadable_account_directory_never_aborts_startup(tmp_path, status):
    """3.4 F4 (ruled MAJOR): an unreadable retained account directory must not abort startup."""

    async def exercise():
        _account, _session, handle, owner = await _seed_owner(tmp_path, status=status)
        account_dir = owner.parent
        account_dir.chmod(0)
        try:
            app = _app(tmp_path, _RestartDecoder())
            try:
                async with app.router.lifespan_context(app):
                    outcome = "ready"
                    snapshot = (await _snapshot(app, handle)).status
                    outcome += f" (meeting {snapshot})"
            except Exception as exc:  # noqa: BLE001
                outcome = f"ABORT {type(exc).__name__}: {exc}"
        finally:
            account_dir.chmod(0o700)
        return outcome

    outcome = asyncio.run(exercise())
    print(f"\nD2 [{status}] startup -> {outcome}")
    assert outcome.startswith("ready"), outcome
