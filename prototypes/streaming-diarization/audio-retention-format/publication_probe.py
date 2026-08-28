#!/usr/bin/env python3
"""PROTOTYPE: falsify production Meeting-audio truth and durability policy."""

from __future__ import annotations

import asyncio
import json
import stat
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from moss_transcribe_diarize.app.phase2 import MeetingHandle
from moss_transcribe_diarize.app.phase2_audio import (
    MeetingAudioArtifactSurvives,
    MeetingAudioArchive,
)


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def probe_mp3(path: Path) -> dict[str, object]:
    media = json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bit_rate:format=format_name,duration,size",
            "-of",
            "json",
            str(path),
        )
    )
    packets = json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_packets",
            "-show_entries",
            "packet=size,duration_time",
            "-of",
            "json",
            str(path),
        )
    )["packets"]
    stream = media["streams"][0]
    container = media["format"]
    return {
        "format": container["format_name"],
        "codec": stream["codec_name"],
        "sample_rate_hz": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "stream_bit_rate_bps": int(stream["bit_rate"]),
        "packet_bitrates_bps": sorted(
            {
                round(int(packet["size"]) * 8 / float(packet["duration_time"]))
                for packet in packets
                if float(packet.get("duration_time") or 0) > 0
            }
        ),
        "duration_ms": round(float(container["duration"]) * 1000),
        "byte_count": int(container["size"]),
    }


def dominant_frequency(path: Path, *, stream: str | None = None) -> int:
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-ss",
        "1",
        "-t",
        "1",
        "-i",
        str(path),
    ]
    if stream is not None:
        command.extend(["-map", stream])
    command.extend(["-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    pcm = subprocess.run(command, check=True, capture_output=True).stdout
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float64)
    spectrum = np.abs(np.fft.rfft(samples * np.hanning(len(samples))))
    frequencies = np.fft.rfftfreq(len(samples), 1 / 16_000)
    return round(float(frequencies[int(np.argmax(spectrum))]))


def extract_production_window(source: Path, destination: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            "0.000000",
            "-t",
            "150.000000",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "wav",
            str(destination),
        ],
        check=True,
        capture_output=True,
    )


class TracingArchive(MeetingAudioArchive):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.fsynced_directories: list[Path] = []

    def _fsync_directory(self, path: Path) -> None:
        self.fsynced_directories.append(path)
        super()._fsync_directory(path)


class CommitProbeStore:
    def __init__(self, *, retry_available_succeeds: bool) -> None:
        self.retry_available_succeeds = retry_available_succeeds
        self.commit_attempts: list[str] = []

    async def _commit_meeting_audio(self, *args: object) -> None:
        audio = args[-1]
        self.commit_attempts.append(audio.state)
        if audio.state == "available" and (
            len(self.commit_attempts) == 1 or not self.retry_available_succeeds
        ):
            raise RuntimeError("forced available metadata failure")


class SurvivingDiscardArchive(MeetingAudioArchive):
    def discard(self, publication) -> None:
        if not publication.path.exists():
            raise AssertionError("publication unexpectedly absent")
        raise MeetingAudioArtifactSurvives("forced surviving production MP3")


async def metadata_reconciliation(
    root: Path,
    source: Path,
    *,
    retry_available_succeeds: bool,
) -> dict[str, object]:
    root.parent.mkdir(parents=True, exist_ok=True)
    archive = SurvivingDiscardArchive(root)
    store = CommitProbeStore(retry_available_succeeds=retry_available_succeeds)
    handle = MeetingHandle(store, "account-a", 1, "meeting-metadata")
    outcome = "propagated"
    returned_state = None
    try:
        returned = await handle.publish_audio(archive, source)
    except RuntimeError:
        pass
    else:
        returned_state = returned.state
        outcome = returned.state
    publication_path = root / "account-a" / "meeting-metadata" / "audio.mp3"
    return {
        "outcome": outcome,
        "returned_state": returned_state,
        "commit_attempts": store.commit_attempts,
        "artifact_survives": publication_path.exists(),
        "unavailable_committed": "unavailable" in store.commit_attempts,
    }


def make_two_stream_source(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=151:sample_rate=16000",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=151:sample_rate=16000",
            "-map",
            "0:a:0",
            "-map",
            "1:a:0",
            "-c:a",
            "pcm_s16le",
            "-disposition:a:0",
            "0",
            "-disposition:a:1",
            "default",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def fail_unlink_for(target: Path):
    original = Path.unlink

    def fail_selected(path: Path, *args: object, **kwargs: object) -> None:
        if path == target:
            raise OSError("forced canonical MP3 unlink failure")
        original(path, *args, **kwargs)

    return fail_selected


def main() -> None:
    state: dict[str, object] = {
        "structural_question": (
            "Can one production archive keep inference, MP3 bytes, filesystem durability, and "
            "available/unavailable metadata truthful across every cleanup path?"
        ),
        "minimum_primitives": [
            "one transient 16 kHz mono PCM transcription mix",
            "one canonical owner-partitioned MP3 path",
            "one production discard operation: unlink, verify absence, fsync parent",
            "owner-bound available/unavailable metadata commit",
        ],
        "invariants": [
            "direct and windowed inference and retained MP3 consume one canonical mix",
            "available follows durable valid MP3 and exact metadata",
            "unavailable is committed only after discard proves canonical MP3 absent",
            "a surviving MP3 is never paired with durable unavailable",
            "new root, Account, Meeting, and final-file entries are parent-fsynced in order",
            "audio failure never changes transcript truth",
        ],
        "assumptions_unknowns": [
            "cooperating single-process operator; no hostile filesystem mutation",
            "perceived MP3 quality remains unmeasured and is not a gate",
            "production-host encoding time remains descriptive, not a fixed threshold",
        ],
        "falsifier": (
            "Any mix-frequency divergence, missing hierarchy fsync, format/privacy mismatch, "
            "unavailable metadata beside surviving MP3, or changed transcript rejects the design."
        ),
        "tool_decision": (
            "Call production MeetingAudioArchive and MeetingHandle directly; use real FFmpeg/"
            "ffprobe and forced filesystem/commit failures because each result selects a truth state."
        ),
        "ffmpeg": run("ffmpeg", "-version").splitlines()[0],
    }
    with tempfile.TemporaryDirectory(prefix="moss-file-mp3-prototype-") as temp_name:
        temp = Path(temp_name)
        transcript = {"segments": [{"text": "transcript truth"}]}
        source = temp / "source.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:duration=1",
                "-ar",
                "48000",
                "-ac",
                "2",
                "-c:a",
                "pcm_s16le",
                str(source),
            ],
            check=True,
            capture_output=True,
        )

        root = temp / "archive" / "meetings"
        root.parent.mkdir()
        archive = TracingArchive(root)
        mix = temp / "transcription-mix.wav"
        archive.prepare_mix(source, mix)
        publication = archive.publish("account-a", "meeting-success", mix)
        measured = probe_mp3(publication.path)
        state["success"] = {
            "metadata": measured,
            "metadata_bytes_match": measured["byte_count"] == publication.byte_count,
            "relative_path": publication.relative_path,
            "root_mode": oct(stat.S_IMODE(root.stat().st_mode)),
            "account_mode": oct(stat.S_IMODE(publication.path.parent.parent.stat().st_mode)),
            "meeting_mode": oct(stat.S_IMODE(publication.path.parent.stat().st_mode)),
            "file_mode": oct(stat.S_IMODE(publication.path.stat().st_mode)),
            "fsynced_directories": [
                path.relative_to(temp).as_posix() for path in archive.fsynced_directories
            ],
            "transcript_unchanged": transcript == {"segments": [{"text": "transcript truth"}]},
        }

        multi_stream = temp / "multi-stream.mka"
        make_two_stream_source(multi_stream)
        multi_mix = temp / "multi-mix.wav"
        inference_window = temp / "inference-window.wav"
        archive.prepare_mix(multi_stream, multi_mix)
        extract_production_window(multi_mix, inference_window)
        retained = archive.publish("account-a", "meeting-multi", multi_mix)
        canonical_hz = dominant_frequency(multi_mix)
        window_hz = dominant_frequency(inference_window)
        retained_hz = dominant_frequency(retained.path)
        state["multi_stream_shared_mix"] = {
            "source_first_stream_hz": dominant_frequency(multi_stream, stream="0:a:0"),
            "source_default_stream_hz": dominant_frequency(multi_stream),
            "canonical_mix_hz": canonical_hz,
            "windowed_inference_input_hz": window_hz,
            "retained_mp3_hz": retained_hz,
            "all_consumers_match": canonical_hz == window_hz == retained_hz,
        }

        postreplace_dir = root / "account-a" / "meeting-postreplace"
        postreplace_path = postreplace_dir / "audio.mp3"
        real_fsync = archive._fsync_directory

        def fail_postreplace_fsync(path: Path) -> None:
            if path == postreplace_dir:
                raise OSError("forced post-replace fsync failure")
            real_fsync(path)

        archive._fsync_directory = fail_postreplace_fsync
        postreplace_exception = None
        with patch.object(Path, "unlink", fail_unlink_for(postreplace_path)):
            try:
                archive.publish("account-a", "meeting-postreplace", mix)
            except Exception as exc:
                postreplace_exception = type(exc).__name__
        archive._fsync_directory = real_fsync
        state["postreplace_cleanup_failure"] = {
            "exception_type": postreplace_exception,
            "artifact_survives": postreplace_path.exists(),
            "unavailable_eligible": False,
        }

        mismatch = archive.publish("account-a", "meeting-mismatch", mix)
        mismatch.path.write_bytes(mismatch.path.read_bytes() + b"size mismatch")
        resolved_before_discard = archive.resolve(
            "account-a",
            "meeting-mismatch",
            mismatch.relative_path,
            mismatch.byte_count,
        )
        archive.discard_stored("account-a", "meeting-mismatch", mismatch.relative_path)
        state["size_mismatch_discarded"] = {
            "resolved_before_discard": resolved_before_discard is not None,
            "artifact_survives": mismatch.path.exists(),
            "unavailable_eligible": not mismatch.path.exists(),
        }

        mismatch_survives = archive.publish("account-a", "meeting-mismatch-survives", mix)
        mismatch_survives.path.write_bytes(mismatch_survives.path.read_bytes() + b"size mismatch")
        mismatch_exception = None
        with patch.object(Path, "unlink", fail_unlink_for(mismatch_survives.path)):
            try:
                archive.discard_stored(
                    "account-a",
                    "meeting-mismatch-survives",
                    mismatch_survives.relative_path,
                )
            except Exception as exc:
                mismatch_exception = type(exc).__name__
        state["size_mismatch_survives"] = {
            "exception_type": mismatch_exception,
            "artifact_survives": mismatch_survives.path.exists(),
            "unavailable_eligible": False,
        }

        mismatch_unknown = archive.publish("account-a", "meeting-mismatch-unknown", mix)
        mismatch_unknown.path.write_bytes(mismatch_unknown.path.read_bytes() + b"size mismatch")
        original_stat = Path.stat

        def fail_selected_stat(path: Path, *args: object, **kwargs: object):
            if path == mismatch_unknown.path:
                raise OSError("forced existence uncertainty")
            return original_stat(path, *args, **kwargs)

        unknown_exception = None
        with (
            patch.object(Path, "unlink", fail_unlink_for(mismatch_unknown.path)),
            patch.object(Path, "stat", fail_selected_stat),
        ):
            try:
                archive.discard_stored(
                    "account-a",
                    "meeting-mismatch-unknown",
                    mismatch_unknown.relative_path,
                )
            except Exception as exc:
                unknown_exception = type(exc).__name__
        state["size_mismatch_unobservable"] = {
            "exception_type": unknown_exception,
            "artifact_survives_after_probe": mismatch_unknown.path.exists(),
            "unavailable_eligible": False,
        }

        state["metadata_cleanup_reconciliation"] = {
            "retry_succeeds": asyncio.run(
                metadata_reconciliation(
                    temp / "metadata-success" / "meetings",
                    mix,
                    retry_available_succeeds=True,
                )
            ),
            "retry_fails": asyncio.run(
                metadata_reconciliation(
                    temp / "metadata-failure" / "meetings",
                    mix,
                    retry_available_succeeds=False,
                )
            ),
        }
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
