"""R4-7 stopped-process SQLite plus Meeting-audio cold-copy drill."""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import Phase2Store, SESSION_COOKIE, create_phase2_app
from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive


def md5(path: Path) -> str:
    digest = hashlib.md5()  # Receipt compatibility, not an integrity/security primitive.
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def seed(database: Path, audio_root: Path, pcm_path: Path) -> dict[str, object]:
    store = await Phase2Store.open(database)
    try:
        account, session_id = await store.bootstrap_browser(None)
        handle = await store.workspace(account).create_meeting("file")
        audio = await handle.publish_audio(
            MeetingAudioArchive(audio_root), pcm_path, raw_pcm=True
        )
        if audio.state != "available":
            raise AssertionError(audio)
        document = {
            "segments": [
                {
                    "id": "seg_0001",
                    "start": 0.0,
                    "end": 1.0,
                    "speaker": "S01",
                    "text": "cold-copy-generation-a",
                }
            ]
        }
        await handle.finish_with_transcript(document, "completed")
        return {
            "session_id": session_id,
            "meeting_id": handle.meeting_id,
            "relative_path": audio.relative_path,
            "document": document,
        }
    finally:
        await store.close()


def copy_bundle(database: Path, audio_root: Path, target: Path) -> list[str]:
    target.mkdir(parents=True)
    copied: list[str] = []
    for source in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
        if source.exists():
            shutil.copy2(source, target / source.name)
            copied.append(source.name)
    shutil.copytree(audio_root, target / "meetings")
    copied.append("meetings/")
    return copied


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="moss-r4-runtime-backup-") as raw:
        root = Path(raw)
        source = root / "source"
        source.mkdir()
        database = source / "moss.sqlite3"
        audio_root = source / "meetings"
        pcm = source / "generation-a.pcm"
        pcm.write_bytes(b"\x01\x00" * 16_000)
        seeded = asyncio.run(seed(database, audio_root, pcm))

        # The owning store is closed before this ordinary filesystem copy.
        published = audio_root / str(seeded["relative_path"])
        source_audio_md5 = md5(published)
        backup = root / "backup"
        copied = copy_bundle(database, audio_root, backup)

        restore = root / "restore"
        restore.mkdir()
        restored_database = restore / "moss.sqlite3"
        for item in backup.iterdir():
            if item.name == "meetings":
                shutil.copytree(item, restore / "meetings")
            else:
                shutil.copy2(item, restore / item.name)

        app = create_phase2_app(
            database_path=restored_database,
            file_work_root=restore / "file-work",
            meeting_audio_root=restore / "meetings",
        )
        with TestClient(app, base_url="https://moss.test") as client:
            client.cookies.set(
                SESSION_COOKIE,
                str(seeded["session_id"]),
                domain="moss.test",
                path="/",
            )
            meeting = client.get(f"/api/meetings/{seeded['meeting_id']}")
            meeting.raise_for_status()
            payload = meeting.json()
            downloaded = client.get(
                f"/api/meetings/{seeded['meeting_id']}/audio/download"
            )
            downloaded.raise_for_status()

        restored_audio = restore / "meetings" / str(seeded["relative_path"])
        state = {
            "verdict": "SUPPORTED",
            "copy_started_after_store_close": True,
            "copied": copied,
            "source_database": str(database),
            "restored_database": str(restored_database),
            "source_audio_md5": source_audio_md5,
            "restored_audio_md5": md5(restored_audio),
            "downloaded_audio_md5": hashlib.md5(downloaded.content).hexdigest(),
            "status": payload["status"],
            "transcript": payload["transcript"],
            "expected_transcript": seeded["document"],
            "same_generation": (
                payload["status"] == "completed"
                and payload["transcript"] == seeded["document"]
                and md5(restored_audio) == source_audio_md5
                and hashlib.md5(downloaded.content).hexdigest() == source_audio_md5
            ),
        }
        if not state["same_generation"]:
            raise AssertionError(state)
        print(json.dumps(state, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
