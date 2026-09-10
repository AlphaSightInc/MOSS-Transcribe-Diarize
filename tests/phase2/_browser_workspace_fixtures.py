"""Stable owner labels for meeting tests; real browser bootstrap is tested separately."""
from __future__ import annotations

from unittest.mock import patch

from moss_transcribe_diarize.app import phase2


async def seed_workspace(store: phase2.Phase2Store, workspace_id: str):
    # Repeated fixture references mean tabs in the same browser, with one cookie.
    cursor = await store._connection.execute(
        "SELECT session_id FROM sign_in_sessions WHERE account_id = ?", (workspace_id,)
    )
    row = await cursor.fetchone()
    await cursor.close()
    if row is not None:
        return await store.bootstrap_browser(row["session_id"])
    token = phase2.secrets.token_urlsafe
    with patch.object(phase2.secrets, "token_urlsafe", side_effect=lambda n: workspace_id if n == 24 else token(n)):
        return await store.bootstrap_browser(None)
