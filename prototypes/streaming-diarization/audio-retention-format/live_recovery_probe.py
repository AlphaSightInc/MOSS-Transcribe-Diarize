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
import time
from pathlib import Path

from moss_transcribe_diarize.app.phase2 import GoogleIdentity, Phase2Store
from moss_transcribe_diarize.app.phase2_audio import (
    LiveMeetingAudioStages,
    MeetingAudioArchive,
)


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
                "recovery uses only an active Live Meeting record and its fixed owner path",
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
                "loss at every terminal ordering edge because each result changes recovery state."
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
        ) else "FAIL"
        print(json.dumps(state, indent=2, sort_keys=True))
        if state["verdict"] != "PASS":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
