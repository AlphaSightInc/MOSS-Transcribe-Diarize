"""THROWAWAY: verify revoked test data without restoring browser authority.

Question: can read-only SQLite/WAL plus silent decode prove preserved results after
the browser loses all access? Primitives: test-owned IDs, one consistent snapshot,
exact acknowledged transcript, referenced audio. Invariants: no DB writes, no new
product route, no authority restoration, no content in the emitted report.
Unknown: WAL visibility and actual audio verification. Falsifiers: foreign owner,
changed prefix, missing/corrupt audio, or a successful write through the read handle.
Run: PYTHONPATH=. .venv/bin/python prototypes/phase2-account-lifecycle/revocation_snapshot_probe.py
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import subprocess
import tempfile
import wave
from pathlib import Path

from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive


from moss_transcribe_diarize.phase2_acceptance_external import (
    _read_revocation_snapshot as snapshot, ExternalMeasurementError,
)


async def probe(root):
    phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version
    database = root / "disposable.sqlite3"
    audio_root = root / "meetings"
    source = root / "silent.wav"
    with wave.open(str(source), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        output.writeframes(b"\0\0" * 16000)
    store = await phase2.Phase2Store.open(database)
    try:
        owner, cookie = await store.bootstrap_browser(None)
        peer, _ = await store.bootstrap_browser(None)
        handle = await store.workspace(owner).create_meeting("live")
        prefix = {"segments": [{"text": "acknowledged prefix"}]}
        await handle.commit_transcript(prefix)
        audio = await handle.publish_audio(MeetingAudioArchive(audio_root), source, partial=True)
        await handle.finish("interrupted")
        assert await store.revoke_account(owner.account_id)
        assert await store.account_for_session(cookie) is None
        # Store stays open so the reader must correctly include committed WAL state.
        found = snapshot(database, audio_root, owner.account_id, (handle.meeting_id,))[handle.meeting_id]
        assert found["status"] == "interrupted" and found["version"] == 1
        assert json.loads(found["document_json"]) == prefix
        assert found["audio_state"] == "partial" and found["audio_decodes"]
        assert len(found["audio_bytes"]) == found["byte_count"]
        try:
            snapshot(database, audio_root, peer.account_id, (handle.meeting_id,))
        except ExternalMeasurementError:
            foreign_refused = True
        else:
            foreign_refused = False
        assert foreign_refused
        with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as read_only:
            try:
                read_only.execute("UPDATE meetings SET status='completed'")
            except sqlite3.OperationalError:
                write_refused = True
            else:
                write_refused = False
        assert write_refused
        artifact = audio_root / audio.relative_path
        original = artifact.read_bytes()
        artifact.write_bytes(b"corrupt test audio")
        corrupted = snapshot(database, audio_root, owner.account_id, (handle.meeting_id,))[handle.meeting_id]
        assert not corrupted["audio_decodes"]
        artifact.write_bytes(original)
        assert snapshot(database, audio_root, owner.account_id, (handle.meeting_id,))[handle.meeting_id] == found
        print(json.dumps({"sqlite": sqlite3.sqlite_version, "wal_visible": True,
            "prefix_preserved": True, "partial_audio_silently_decoded": True,
            "foreign_refused": foreign_refused, "write_refused": write_refused,
            "corrupt_audio_rejected": True, "authority_not_restored": True}), flush=True)
    finally:
        await store.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="moss-revocation-probe-") as scratch:
        asyncio.run(probe(Path(scratch)))
