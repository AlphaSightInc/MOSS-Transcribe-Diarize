#!/usr/bin/env python3
"""PROTOTYPE: falsify mixed-PCM staging and terminal recovery policy."""

from __future__ import annotations

import asyncio
import json
import math
import os
import statistics
import struct
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from moss_transcribe_diarize.app.phase2 import GoogleIdentity, Phase2Store
from moss_transcribe_diarize.app.phase2_audio import (
    LiveMeetingAudioStages,
    MeetingAudioArchive,
)
from moss_transcribe_diarize.app.phase2_live import Phase2LiveMeetings


SAMPLE_RATE = 16_000
BYTES_PER_SAMPLE = 2


class _OneFailedStageCreateArchive(MeetingAudioArchive):
    """Reachable local-storage refusal before any raw Live bytes are accepted."""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self._fail_once = True

    def _ensure_private_directory(self, path: Path) -> None:
        if self._fail_once:
            self._fail_once = False
            raise OSError("prototype stage directory refusal")
        super()._ensure_private_directory(path)


class _FailingDiscardStages:
    def __init__(self, stages: LiveMeetingAudioStages, *, failures: int | None) -> None:
        self.stages = stages
        self.failures = failures
        self.attempts = 0

    def __getattr__(self, name: str):
        return getattr(self.stages, name)

    def discard(self, account_id: str, meeting_id: str) -> None:
        self.attempts += 1
        if self.failures is None or self.attempts <= self.failures:
            raise OSError("prototype stage discard refusal")
        self.stages.discard(account_id, meeting_id)


class _RejectCreateRuntime:
    def create(self, *, echo_mode: str | None, session_id: str) -> None:
        del echo_mode, session_id
        raise ValueError("prototype runtime creation refusal")


class _HeldCountingArchive(MeetingAudioArchive):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.publish_count = 0
        self.publish_started = threading.Event()
        self.release_publish = threading.Event()

    def publish_live_prefix(
        self,
        account_id: str,
        meeting_id: str,
        source_path: str | Path,
        *,
        partial: bool,
    ):
        self.publish_count += 1
        self.publish_started.set()
        if not self.release_publish.wait(timeout=5):
            raise TimeoutError("prototype did not release held MP3 publication")
        return super().publish_live_prefix(
            account_id,
            meeting_id,
            source_path,
            partial=partial,
        )


def pcm_tone(samples: int, frequency: float = 880.0) -> bytes:
    values = [
        round(12_000 * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE))
        for index in range(samples)
    ]
    return struct.pack(f"<{samples}h", *values)


def recoverable_prefix(path: Path) -> bytes:
    try:
        payload = path.read_bytes()
    except FileNotFoundError:
        return b""
    return payload[: len(payload) - (len(payload) % BYTES_PER_SAMPLE)]


def probe(path: Path) -> dict[str, object]:
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bit_rate:format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    stream = payload["streams"][0]
    container = payload["format"]
    return {
        "codec": stream["codec_name"],
        "sample_rate_hz": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "bit_rate_bps": int(stream["bit_rate"]),
        "duration_ms": round(float(container["duration"]) * 1000),
        "byte_count": int(container["size"]),
    }


def publish_prefix(
    work: Path,
    archive: MeetingAudioArchive,
    meeting_id: str,
    pcm: bytes,
) -> dict[str, object]:
    if not pcm:
        return {"state": "unavailable", "samples": 0, "stage_exists": False}
    stage = work / f"{meeting_id}.pcm"
    stage.write_bytes(pcm)
    publication = archive.publish_live_prefix(
        "account-a",
        meeting_id,
        stage,
        partial=True,
    )
    stage.unlink()
    return {
        "state": "partial",
        "samples": len(pcm) // BYTES_PER_SAMPLE,
        "stage_exists": False,
        "probe": probe(publication.path),
    }


async def _crash_boundary(
    work: Path,
    full_pcm: bytes,
    crash_after: str,
) -> dict[str, object]:
    """Restart from durable row/path truth after every terminal ordering boundary."""

    case = work / f"crash-{crash_after}"
    database = case / "moss.sqlite3"
    audio_root = case / "meetings"
    archive_before_crash = MeetingAudioArchive(audio_root)
    stages_before_crash = LiveMeetingAudioStages(
        archive_before_crash,
        max_bytes=len(full_pcm),
    )
    store = await Phase2Store.open(database)
    actions: list[str] = []
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, session_id = admitted
        handle = await store.workspace(account).create_meeting("live")
        stage_path = stages_before_crash.path(account.account_id, handle.meeting_id)
        if crash_after != "meeting_create":
            await handle.commit_transcript(
                {"segments": [{"id": "seg_0001", "text": "durable transcript"}]}
            )
            actions.append("transcript")
            stages_before_crash.reserve(account.account_id, handle.meeting_id)
            stage = stages_before_crash.create(handle.meeting_id)
            stage.append_mixed(
                pcm=full_pcm,
                start_timestamp_ns=0,
                sample_count=len(full_pcm) // 2,
                sample_rate=SAMPLE_RATE,
            )
            stages_before_crash.release(handle.meeting_id)
        if crash_after not in {"meeting_create", "transcript"}:
            archive_before_crash.publish_live_prefix(
                account.account_id,
                handle.meeting_id,
                stage_path,
                partial=False,
            )
            actions.append("mp3_publish")
        if crash_after not in {"meeting_create", "transcript", "mp3_publish"}:
            await handle.publish_audio(
                archive_before_crash,
                stage_path,
                partial=False,
                raw_pcm=True,
            )
            actions.append("metadata")
        if crash_after not in {
            "meeting_create",
            "transcript",
            "mp3_publish",
            "metadata",
        }:
            stages_before_crash.discard(account.account_id, handle.meeting_id)
            actions.append("stage_cleanup")
        if crash_after == "meeting_finish":
            await handle.finish("completed")
            actions.append("meeting_finish")
        meeting_id = handle.meeting_id
    finally:
        await store.close()

    complete_path = audio_root / "account-a" / meeting_id / "audio.mp3"
    partial_path = audio_root / "account-a" / meeting_id / "audio.partial.mp3"
    orphan_before_restart = crash_after == "mp3_publish" and complete_path.exists()
    del archive_before_crash, stages_before_crash, store, handle

    archive_after_restart = MeetingAudioArchive(audio_root)
    stages_after_restart = LiveMeetingAudioStages(
        archive_after_restart,
        max_bytes=len(full_pcm),
    )
    reopened = await Phase2Store.open(database)
    try:
        await reopened.recover_active_meetings(
            audio_archive=archive_after_restart,
            live_audio_stages=stages_after_restart,
        )
        reopened_account = await reopened.account_for_session(session_id)
        assert reopened_account is not None
        reopened_handle = await reopened.workspace(reopened_account).open_meeting(meeting_id)
        assert reopened_handle is not None
        snapshot = await reopened_handle.snapshot()
    finally:
        await reopened.close()
    return {
        "crash_after": crash_after,
        "actions_before_crash": actions,
        "transcript_truth_preserved": (
            snapshot.transcript is None
            if crash_after == "meeting_create"
            else snapshot.transcript["segments"][0]["text"] == "durable transcript"
        ),
        "audio_state_after_recovery": snapshot.audio.state,
        "complete_mp3_exists": complete_path.exists(),
        "partial_mp3_exists": partial_path.exists(),
        "orphan_reconciled": orphan_before_restart and not complete_path.exists(),
        "stage_clean": not stage_path.exists(),
        "meeting_status": snapshot.status,
    }


def crash_order_probe(work: Path, full_pcm: bytes) -> list[dict[str, object]]:
    return asyncio.run(
        _crash_boundaries(work, full_pcm)
    )


async def _crash_boundaries(work: Path, full_pcm: bytes) -> list[dict[str, object]]:
    return [
        await _crash_boundary(work, full_pcm, boundary)
        for boundary in (
            "meeting_create",
            "transcript",
            "mp3_publish",
            "metadata",
            "stage_cleanup",
            "meeting_finish",
        )
    ]


async def _cleanup_failure_probe(work: Path, pcm: bytes) -> dict[str, object]:
    database = work / "moss.sqlite3"
    archive = MeetingAudioArchive(work / "meetings")
    stages = LiveMeetingAudioStages(archive, max_bytes=len(pcm))
    store = await Phase2Store.open(database)
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, _ = admitted
        handle = await store.workspace(account).create_meeting("live")
        await handle.commit_transcript(
            {"segments": [{"id": "seg_0001", "text": "durable transcript"}]}
        )
        stages.reserve(account.account_id, handle.meeting_id)
        stage = stages.create(handle.meeting_id)
        stage.append_mixed(
            pcm=pcm,
            start_timestamp_ns=0,
            sample_count=len(pcm) // 2,
            sample_rate=SAMPLE_RATE,
        )
        stages.release(handle.meeting_id)
        prefix = stages.prefix(
            account.account_id,
            handle.meeting_id,
            expected_samples=len(pcm) // 2,
        )
        assert prefix is not None
        await handle.publish_audio(
            archive,
            prefix.path,
            partial=False,
            raw_pcm=True,
        )

        persistent = _FailingDiscardStages(stages, failures=None)
        live = Phase2LiveMeetings(
            object(),
            audio_archive=archive,
            audio_stages=persistent,
        )
        binding = SimpleNamespace(
            owner_key=(account.account_id, account.authority_generation),
            handle=handle,
            capture_fenced=False,
            terminal_persisted=False,
            persistence_failure=None,
            public_snapshot=None,
            public_events=(),
            public_event_high_water=-1,
            durable_document={"segments": [{"id": "seg_0001", "text": "durable transcript"}]},
            durable_version=1,
            authority_cleanup_task=None,
            terminal_settlement_lock=asyncio.Lock(),
            changed=asyncio.Condition(),
        )
        await live._terminal_recovery_failed(
            binding,
            "audio_terminal_recovery_failed",
            None,
            (),
        )
        persistent_snapshot = await handle.snapshot()
        persistent_state = {
            "cleanup_attempts": persistent.attempts,
            "meeting_status": persistent_snapshot.status,
            "audio_state": persistent_snapshot.audio.state,
            "stage_exists": stages.path(account.account_id, handle.meeting_id).exists(),
            "terminal_persisted": binding.terminal_persisted,
            "failure_explicit": binding.persistence_failure,
        }

        transient = _FailingDiscardStages(stages, failures=1)
        revoked_live = Phase2LiveMeetings(
            object(),
            audio_archive=archive,
            audio_stages=transient,
        )
        binding.authority_cleanup_task = None
        revoked_live.audio_stages = transient
        revoked_clean = await revoked_live._discard_stage_after_authority_loss(binding)
        transient_state = {
            "cleanup_attempts": transient.attempts,
            "cleanup_verified": revoked_clean,
            "stage_exists": stages.path(account.account_id, handle.meeting_id).exists(),
        }
        return {
            "persistent_authority_valid": persistent_state,
            "transient_authority_revoked": transient_state,
        }
    finally:
        try:
            stages.discard("account-a", handle.meeting_id)
        except Exception:
            pass
        await store.close()


async def _missing_interrupted_artifact_probe(work: Path, pcm: bytes) -> dict[str, object]:
    database = work / "moss.sqlite3"
    audio_root = work / "meetings"
    archive = MeetingAudioArchive(audio_root)
    stages = LiveMeetingAudioStages(archive, max_bytes=len(pcm))
    store = await Phase2Store.open(database)
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, session_id = admitted
        handle = await store.workspace(account).create_meeting("live")
        stages.reserve(account.account_id, handle.meeting_id)
        stage = stages.create(handle.meeting_id)
        stage.append_mixed(
            pcm=pcm,
            start_timestamp_ns=0,
            sample_count=len(pcm) // 2,
            sample_rate=SAMPLE_RATE,
        )
        stages.release(handle.meeting_id)
        prefix = stages.prefix(
            account.account_id,
            handle.meeting_id,
            expected_samples=len(pcm) // 2,
        )
        assert prefix is not None
        audio = await handle.publish_audio(
            archive,
            prefix.path,
            partial=False,
            raw_pcm=True,
        )
        await handle.finish("interrupted")
        assert audio.relative_path is not None
        (audio_root / audio.relative_path).unlink()
        meeting_id = handle.meeting_id
    finally:
        await store.close()

    reopened_archive = MeetingAudioArchive(audio_root)
    reopened_stages = LiveMeetingAudioStages(reopened_archive, max_bytes=len(pcm))
    reopened = await Phase2Store.open(database)
    try:
        await reopened.recover_active_meetings(
            audio_archive=reopened_archive,
            live_audio_stages=reopened_stages,
        )
        reopened_account = await reopened.account_for_session(session_id)
        assert reopened_account is not None
        reopened_handle = await reopened.workspace(reopened_account).open_meeting(meeting_id)
        assert reopened_handle is not None
        snapshot = await reopened_handle.snapshot()
    finally:
        await reopened.close()
    return {
        "meeting_status": snapshot.status,
        "audio_state": snapshot.audio.state,
        "stage_exists": reopened_stages.path("account-a", meeting_id).exists(),
        "artifact_exists": bool(tuple((audio_root / "account-a" / meeting_id).glob("*.mp3"))),
    }


async def _failed_create_cleanup_probe(work: Path, pcm: bytes) -> dict[str, object]:
    database = work / "moss.sqlite3"
    audio_root = work / "meetings"
    archive = MeetingAudioArchive(audio_root)
    stages = LiveMeetingAudioStages(archive, max_bytes=len(pcm))
    persistent = _FailingDiscardStages(stages, failures=None)
    store = await Phase2Store.open(database)
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, session_id = admitted
        workspace = store.workspace(account)
        live = Phase2LiveMeetings(
            _RejectCreateRuntime(),
            audio_archive=archive,
            audio_stages=persistent,
        )
        try:
            await live.create(
                account=account,
                workspace=workspace,
                origin_session=session_id,
                echo_mode=None,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("runtime creation refusal was not propagated")
        meetings = await workspace.list_meetings()
        assert len(meetings) == 1
        meeting_id = meetings[0].meeting_id
        before = {
            "cleanup_attempts": persistent.attempts,
            "meeting_status": meetings[0].status,
            "stage_exists": stages.path(account.account_id, meeting_id).exists(),
        }
    finally:
        await store.close()

    reopened_archive = MeetingAudioArchive(audio_root)
    reopened_stages = LiveMeetingAudioStages(reopened_archive, max_bytes=len(pcm))
    reopened = await Phase2Store.open(database)
    try:
        await reopened.recover_active_meetings(
            audio_archive=reopened_archive,
            live_audio_stages=reopened_stages,
        )
        reopened_account = await reopened.account_for_session(session_id)
        assert reopened_account is not None
        handle = await reopened.workspace(reopened_account).open_meeting(meeting_id)
        assert handle is not None
        after_snapshot = await handle.snapshot()
        after = {
            "meeting_status": after_snapshot.status,
            "audio_state": None if after_snapshot.audio is None else after_snapshot.audio.state,
            "stage_exists": reopened_stages.path("account-a", meeting_id).exists(),
        }
    finally:
        try:
            reopened_stages.discard("account-a", meeting_id)
        except Exception:
            pass
        await reopened.close()
    return {"before_restart": before, "after_restart": after}


async def _terminal_atomicity_probe(work: Path) -> dict[str, object]:
    store = await Phase2Store.open(work / "moss.sqlite3")
    old = {"segments": [{"id": "seg_0001", "text": "old"}]}
    final = {"segments": [{"id": "seg_0001", "text": "final"}]}
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        workspace = store.workspace(admitted[0])

        split = await workspace.create_meeting("live")
        await split.commit_transcript(old)
        await split.commit_transcript(final)
        split_boundary = await split.snapshot()

        atomic = await workspace.create_meeting("live")
        await atomic.commit_transcript(old)
        atomic_version = await atomic.finish_with_transcript(final, "completed")
        atomic_boundary = await atomic.snapshot()
        return {
            "split_boundary": {
                "status": split_boundary.status,
                "transcript": split_boundary.transcript["segments"][0]["text"],
                "version": split_boundary.transcript_version,
            },
            "atomic_boundary": {
                "status": atomic_boundary.status,
                "transcript": atomic_boundary.transcript["segments"][0]["text"],
                "version": atomic_boundary.transcript_version,
                "returned_version": atomic_version,
            },
        }
    finally:
        await store.close()


async def _serialized_terminal_probe(work: Path, pcm: bytes) -> dict[str, object]:
    database = work / "moss.sqlite3"
    archive = _HeldCountingArchive(work / "meetings")
    stages = LiveMeetingAudioStages(archive, max_bytes=len(pcm))
    store = await Phase2Store.open(database)
    settlement_lock = asyncio.Lock()
    outcomes: list[str] = []
    document = {"segments": [{"id": "seg_0001", "text": "final"}]}
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, _ = admitted
        handle = await store.workspace(account).create_meeting("live")
        stages.reserve(account.account_id, handle.meeting_id)
        stage = stages.create(handle.meeting_id)
        stage.append_mixed(
            pcm=pcm,
            start_timestamp_ns=0,
            sample_count=len(pcm) // 2,
            sample_rate=SAMPLE_RATE,
        )

        async def settle() -> None:
            async with settlement_lock:
                if (await handle.snapshot()).status != "active":
                    outcomes.append("existing-terminal")
                    return
                prefix = await asyncio.to_thread(
                    stages.prefix,
                    account.account_id,
                    handle.meeting_id,
                    expected_samples=len(pcm) // 2,
                )
                assert prefix is not None
                await handle.publish_audio(
                    archive,
                    prefix.path,
                    partial=False,
                    raw_pcm=True,
                )
                await asyncio.to_thread(stages.discard, account.account_id, handle.meeting_id)
                await handle.finish_with_transcript(document, "completed")
                outcomes.append("published")

        first = asyncio.create_task(settle())
        assert await asyncio.to_thread(archive.publish_started.wait, 2)
        second = asyncio.create_task(settle())
        archive.release_publish.set()
        await asyncio.gather(first, second)
        snapshot = await handle.snapshot()
        meeting_dir = archive.root / account.account_id / handle.meeting_id
        return {
            "outcomes": outcomes,
            "publish_count": archive.publish_count,
            "meeting_status": snapshot.status,
            "audio_state": None if snapshot.audio is None else snapshot.audio.state,
            "artifact_resolves": (
                snapshot.audio is not None
                and snapshot.audio.relative_path is not None
                and snapshot.audio.byte_count is not None
                and archive.resolve(
                    account.account_id,
                    handle.meeting_id,
                    snapshot.audio.relative_path,
                    snapshot.audio.byte_count,
                )
                is not None
            ),
            "mp3_files": sorted(
                path.name for path in meeting_dir.iterdir() if path.suffix == ".mp3"
            ),
            "stage_exists": stages.path(account.account_id, handle.meeting_id).exists(),
        }
    finally:
        archive.release_publish.set()
        await store.close()


async def _staged_crash_cleanup_probe(work: Path, pcm: bytes) -> dict[str, object]:
    database = work / "moss.sqlite3"
    audio_root = work / "meetings"
    archive = MeetingAudioArchive(audio_root)
    stages = LiveMeetingAudioStages(archive, max_bytes=len(pcm))
    store = await Phase2Store.open(database)
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, session_id = admitted
        handle = await store.workspace(account).create_meeting("live")
        stages.reserve(account.account_id, handle.meeting_id)
        stage = stages.create(handle.meeting_id)
        stage.append_mixed(
            pcm=pcm,
            start_timestamp_ns=0,
            sample_count=len(pcm) // 2,
            sample_rate=SAMPLE_RATE,
        )
        stages.release(handle.meeting_id)
        staged_path = audio_root / account.account_id / handle.meeting_id / ".audio.staged.mp3"
        staged_path.write_bytes(b"crash-staged-mp3")
        meeting_id = handle.meeting_id
    finally:
        await store.close()

    reopened_archive = MeetingAudioArchive(audio_root)
    reopened_stages = LiveMeetingAudioStages(reopened_archive, max_bytes=len(pcm))
    reopened = await Phase2Store.open(database)
    try:
        await reopened.recover_active_meetings(
            audio_archive=reopened_archive,
            live_audio_stages=reopened_stages,
        )
        account = await reopened.account_for_session(session_id)
        assert account is not None
        handle = await reopened.workspace(account).open_meeting(meeting_id)
        assert handle is not None
        snapshot = await handle.snapshot()
        meeting_dir = audio_root / account.account_id / meeting_id
        return {
            "meeting_status": snapshot.status,
            "audio_state": None if snapshot.audio is None else snapshot.audio.state,
            "mp3_files": sorted(
                path.name for path in meeting_dir.iterdir() if path.suffix == ".mp3"
            ),
            "staged_exists": staged_path.exists(),
            "raw_stage_exists": reopened_stages.path(account.account_id, meeting_id).exists(),
        }
    finally:
        await reopened.close()


async def _file_staged_crash_cleanup_probe(work: Path) -> dict[str, object]:
    database = work / "moss.sqlite3"
    audio_root = work / "meetings"
    archive = MeetingAudioArchive(audio_root)
    store = await Phase2Store.open(database)
    try:
        await store.allow_email("a@example.com")
        admitted = await store.admit(GoogleIdentity("account-a", "a@example.com", "A"))
        assert admitted is not None
        account, session_id = admitted
        handle = await store.workspace(account).create_meeting("file")
        await handle.commit_transcript(
            {"segments": [{"id": "seg_0001", "text": "durable file transcript"}]}
        )
        meeting_dir = audio_root / account.account_id / handle.meeting_id
        meeting_dir.mkdir(parents=True)
        staged_path = meeting_dir / ".audio.staged.mp3"
        staged_path.write_bytes(b"crash-staged-file-mp3")
        meeting_id = handle.meeting_id
    finally:
        await store.close()

    reopened = await Phase2Store.open(database)
    startup_error = None
    try:
        try:
            await reopened.recover_active_meetings(audio_archive=archive)
        except Exception as exc:
            startup_error = type(exc).__name__
        account = await reopened.account_for_session(session_id)
        assert account is not None
        handle = await reopened.workspace(account).open_meeting(meeting_id)
        assert handle is not None
        snapshot = await handle.snapshot()
        return {
            "startup_error": startup_error,
            "meeting_status": snapshot.status,
            "audio_state": None if snapshot.audio is None else snapshot.audio.state,
            "transcript": snapshot.transcript["segments"][0]["text"],
            "staged_exists": staged_path.exists(),
        }
    finally:
        await reopened.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="moss-live-audio-prototype-") as temporary:
        root = Path(temporary)
        frame_pcm = pcm_tone(SAMPLE_RATE // 2)
        accepted_mix = frame_pcm * 120
        stage_archive = MeetingAudioArchive(root / "meetings")
        normal_stages = LiveMeetingAudioStages(
            stage_archive,
            max_bytes=len(accepted_mix),
        )
        normal_stages.reserve("account-a", "normal")
        stage = normal_stages.create("normal")
        latencies = []
        for index in range(120):
            started = time.perf_counter()
            stage.append_mixed(
                pcm=frame_pcm,
                start_timestamp_ns=index * 500_000_000,
                sample_count=len(frame_pcm) // 2,
                sample_rate=SAMPLE_RATE,
            )
            latencies.append((time.perf_counter() - started) * 1000)
        normal_stages.release("normal")
        stage_path = normal_stages.path("account-a", "normal")
        recovered = recoverable_prefix(stage_path)

        cap_stages = LiveMeetingAudioStages(
            stage_archive,
            max_bytes=len(frame_pcm) * 2,
        )
        cap_stages.reserve("account-a", "cap")
        capped = cap_stages.create("cap")
        for index in range(3):
            capped.append_mixed(
                pcm=frame_pcm,
                start_timestamp_ns=index * 500_000_000,
                sample_count=len(frame_pcm) // 2,
                sample_rate=SAMPLE_RATE,
            )
        cap_stages.release("cap")
        cap_path = cap_stages.path("account-a", "cap")

        refused_archive = _OneFailedStageCreateArchive(root / "refused-meetings")
        refused_stages = LiveMeetingAudioStages(
            refused_archive,
            max_bytes=len(frame_pcm),
        )
        refused_stages.reserve("account-a", "refused")
        refused_stage = refused_stages.create("refused")
        refused_stage.append_mixed(
            pcm=frame_pcm,
            start_timestamp_ns=0,
            sample_count=len(frame_pcm) // 2,
            sample_rate=SAMPLE_RATE,
        )
        refused_prefix = refused_stages.prefix(
            "account-a",
            "refused",
            expected_samples=len(frame_pcm) // 2,
        )
        refused_stages.discard("account-a", "refused")

        torn_path = root / "meetings" / "account-a" / "torn" / ".live-mix.pcm"
        torn_path.parent.mkdir(parents=True)
        torn_path.write_bytes(frame_pcm + b"\xff")
        short = struct.pack("<h", 7)
        archive = MeetingAudioArchive(root / "archive")
        short_outcome = publish_prefix(root, archive, "short", short)
        zero_outcome = publish_prefix(root, archive, "zero", b"")
        torn_outcome = publish_prefix(
            root,
            archive,
            "torn",
            recoverable_prefix(torn_path),
        )
        state = {
            "structural_question": (
                "Can one bounded fsynced mixed-PCM stage preserve exactly the accepted Live "
                "transcription mix and recover truthful complete/partial/unavailable audio?"
            ),
            "minimum_primitives": [
                "one owner-derived mixed PCM stage path",
                "one existing max_tape_bytes bound",
                "one existing MeetingAudioArchive publication truth seam",
                "one owner-bound terminal recovery operation",
            ],
            "invariants": [
                "only the exact runtime-accepted mixed bytes enter staging",
                "each acknowledged staged append is fsynced",
                "recovery uses only a canonical Live Meeting record and its fixed owner path",
                "a torn suffix is excluded at the last complete PCM16 sample",
                "transcript durability is independent of audio outcome",
                "terminal success follows transcript, MP3 metadata, stage cleanup, then Meeting status",
            ],
            "assumptions_unknowns": [
                "single-process local filesystem; power-loss durability is delegated to fsync",
                "perceived quality and production-host fsync latency remain unmeasured",
                "one positive PCM16 sample is mechanically playable but not perceptually useful",
            ],
            "falsifier": (
                "Byte divergence, append p95 above the 500 ms ingress cadence, unplayable positive "
                "prefix, metadata/file disagreement, or surviving raw stage rejects the policy."
            ),
            "tool_decision": (
                "Use real fsync plus production MeetingAudioArchive/FFmpeg/ffprobe; simulate process "
                "loss at every terminal ordering edge and inject cleanup refusal because each "
                "result changes whether Meeting terminality is eligible."
            ),
            "normal_stage": {
                "frames": 120,
                "bytes_expected": len(accepted_mix),
                "bytes_recovered": len(recovered),
                "byte_exact": recovered == accepted_mix,
                "append_latency_ms": {
                    "min": min(latencies),
                    "median": statistics.median(latencies),
                    "p95": sorted(latencies)[math.ceil(0.95 * len(latencies)) - 1],
                    "max": max(latencies),
                },
            },
            "cap": {
                "attempts": 3,
                "bytes": cap_path.stat().st_size,
                "degraded": capped.degraded,
                "prefix_frames": cap_path.stat().st_size // len(frame_pcm),
            },
            "stage_create_refusal": {
                "capture_can_continue": True,
                "degraded": refused_stage.degraded,
                "prefix_state": "unavailable" if refused_prefix is None else "unexpected",
                "raw_path_exists": refused_stages.path("account-a", "refused").exists(),
            },
            "short_prefix": short_outcome,
            "zero_prefix": zero_outcome,
            "torn_prefix": {
                "raw_bytes": torn_path.stat().st_size,
                "recovered_bytes": len(recoverable_prefix(torn_path)),
                "outcome": torn_outcome,
            },
            "terminal_crash_boundaries": crash_order_probe(root / "ordering", frame_pcm),
            "cleanup_failure_ordering": asyncio.run(
                _cleanup_failure_probe(root / "cleanup-failure", frame_pcm)
            ),
            "missing_interrupted_artifact": asyncio.run(
                _missing_interrupted_artifact_probe(
                    root / "missing-interrupted-artifact",
                    frame_pcm,
                )
            ),
            "failed_create_cleanup": asyncio.run(
                _failed_create_cleanup_probe(root / "failed-create-cleanup", frame_pcm)
            ),
            "terminal_atomicity": asyncio.run(
                _terminal_atomicity_probe(root / "terminal-atomicity")
            ),
            "serialized_terminal_settlement": asyncio.run(
                _serialized_terminal_probe(root / "serialized-terminal", frame_pcm)
            ),
            "staged_crash_cleanup": asyncio.run(
                _staged_crash_cleanup_probe(root / "staged-crash", frame_pcm)
            ),
            "file_staged_crash_cleanup": asyncio.run(
                _file_staged_crash_cleanup_probe(root / "file-staged-crash")
            ),
        }
        state["verdict"] = "PASS" if (
            state["normal_stage"]["byte_exact"]
            and state["normal_stage"]["append_latency_ms"]["p95"] < 500
            and state["cap"]["prefix_frames"] == 2
            and state["stage_create_refusal"] == {
                "capture_can_continue": True,
                "degraded": True,
                "prefix_state": "unavailable",
                "raw_path_exists": False,
            }
            and state["short_prefix"]["state"] == "partial"
            and state["zero_prefix"]["state"] == "unavailable"
            and state["torn_prefix"]["recovered_bytes"] % 2 == 0
            and all(
                item["transcript_truth_preserved"]
                and item["stage_clean"]
                and item["meeting_status"] in {"completed", "interrupted"}
                for item in state["terminal_crash_boundaries"]
            )
            and state["cleanup_failure_ordering"] == {
                "persistent_authority_valid": {
                    "cleanup_attempts": 1,
                    "meeting_status": "active",
                    "audio_state": "available",
                    "stage_exists": True,
                    "terminal_persisted": False,
                    "failure_explicit": "audio_terminal_recovery_failed",
                },
                "transient_authority_revoked": {
                    "cleanup_attempts": 2,
                    "cleanup_verified": True,
                    "stage_exists": False,
                },
            }
            and state["missing_interrupted_artifact"] == {
                "meeting_status": "interrupted",
                "audio_state": "unavailable",
                "stage_exists": False,
                "artifact_exists": False,
            }
            and state["failed_create_cleanup"] == {
                "before_restart": {
                    "cleanup_attempts": 1,
                    "meeting_status": "active",
                    "stage_exists": True,
                },
                "after_restart": {
                    "meeting_status": "interrupted",
                    "audio_state": "unavailable",
                    "stage_exists": False,
                },
            }
            and state["terminal_atomicity"] == {
                "split_boundary": {
                    "status": "active",
                    "transcript": "final",
                    "version": 2,
                },
                "atomic_boundary": {
                    "status": "completed",
                    "transcript": "final",
                    "version": 2,
                    "returned_version": 2,
                },
            }
            and state["serialized_terminal_settlement"] == {
                "outcomes": ["published", "existing-terminal"],
                "publish_count": 1,
                "meeting_status": "completed",
                "audio_state": "available",
                "artifact_resolves": True,
                "mp3_files": ["audio.mp3"],
                "stage_exists": False,
            }
            and state["staged_crash_cleanup"] == {
                "meeting_status": "interrupted",
                "audio_state": "partial",
                "mp3_files": ["audio.partial.mp3"],
                "staged_exists": False,
                "raw_stage_exists": False,
            }
            and state["file_staged_crash_cleanup"] == {
                "startup_error": None,
                "meeting_status": "interrupted",
                "audio_state": "unavailable",
                "transcript": "durable file transcript",
                "staged_exists": False,
            }
        ) else "FAIL"
        print(json.dumps(state, indent=2, sort_keys=True))
        if state["verdict"] != "PASS":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
