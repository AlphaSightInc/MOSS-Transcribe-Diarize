#!/usr/bin/env python3
"""PROTOTYPE: falsify terminal MP3 publication and cleanup policy."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def probe(path: Path) -> dict[str, object]:
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
    packet_bitrates = sorted(
        {
            round(int(packet["size"]) * 8 / float(packet["duration_time"]))
            for packet in packets
            if float(packet.get("duration_time") or 0) > 0
        }
    )
    stream = media["streams"][0]
    container = media["format"]
    return {
        "format": container["format_name"],
        "codec": stream["codec_name"],
        "sample_rate_hz": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "stream_bit_rate_bps": int(stream["bit_rate"]),
        "packet_bitrates_bps": packet_bitrates,
        "duration_ms": round(float(container["duration"]) * 1000),
        "byte_count": int(container["size"]),
    }


def ensure_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish(
    source: Path,
    root: Path,
    account_id: str,
    meeting_id: str,
    *,
    fail_after_replace: bool = False,
) -> tuple[Path, dict[str, object]]:
    account_dir = root / account_id
    meeting_dir = account_dir / meeting_id
    for directory in (root, account_dir, meeting_dir):
        ensure_private_directory(directory)
    staged = meeting_dir / ".audio.staging.mp3"
    final = meeting_dir / "audio.mp3"
    replaced = False
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-v",
                "error",
                "-y",
                "-i",
                str(source),
                "-map",
                "0:a:0",
                "-vn",
                "-map_metadata",
                "-1",
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "48k",
                "-f",
                "mp3",
                str(staged),
            ],
            check=True,
            capture_output=True,
        )
        metadata = probe(staged)
        if metadata["format"] != "mp3" or metadata["codec"] != "mp3":
            raise RuntimeError("not MP3")
        if (
            metadata["sample_rate_hz"] != 16000
            or metadata["channels"] != 1
            or metadata["stream_bit_rate_bps"] != 48000
            or metadata["packet_bitrates_bps"] != [48000]
        ):
            raise RuntimeError("MP3 encoding contract mismatch")
        staged.chmod(0o600)
        with staged.open("rb") as output:
            os.fsync(output.fileno())
        os.replace(staged, final)
        replaced = True
        if fail_after_replace:
            raise OSError("forced post-replace storage failure")
        fsync_directory(meeting_dir)
        metadata["relative_path"] = final.relative_to(root).as_posix()
        metadata["state"] = "available"
        return final, metadata
    except BaseException:
        staged.unlink(missing_ok=True)
        if replaced:
            final.unlink(missing_ok=True)
        raise


def main() -> None:
    state: dict[str, object] = {
        "question": (
            "Can terminal publication yield only a private 16 kHz mono 48-kbit/s CBR MP3, "
            "while filesystem/encoder failure preserves transcript truth as unavailable?"
        ),
        "hypothesis": (
            "FFmpeg libmp3lame -b:a 48k plus atomic same-directory replacement supplies the "
            "smallest sufficient publication seam."
        ),
        "falsifier": (
            "Any codec/rate/channel/packet-bitrate mismatch, non-private mode, surviving source/"
            "staging file, or transcript change on publication failure rejects the design."
        ),
        "ffmpeg": run("ffmpeg", "-version").splitlines()[0],
    }
    with tempfile.TemporaryDirectory(prefix="moss-file-mp3-prototype-") as temp_name:
        temp = Path(temp_name)
        work_dir = temp / "file-work" / "source"
        work_dir.mkdir(parents=True)
        source = work_dir / "input.wav"
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
        transcript = {"segments": [{"text": "transcript truth"}]}
        root = temp / "meetings"
        final, metadata = publish(source, root, "account-a", "meeting-a")
        shutil.rmtree(work_dir)
        state["success"] = {
            "metadata": metadata,
            "metadata_byte_count_matches": metadata["byte_count"] == final.stat().st_size,
            "root_mode": oct(stat.S_IMODE(root.stat().st_mode)),
            "account_mode": oct(stat.S_IMODE(final.parent.parent.stat().st_mode)),
            "meeting_mode": oct(stat.S_IMODE(final.parent.stat().st_mode)),
            "file_mode": oct(stat.S_IMODE(final.stat().st_mode)),
            "surviving_files": sorted(
                path.relative_to(temp).as_posix() for path in temp.rglob("*") if path.is_file()
            ),
            "source_exists_after_cleanup": source.exists(),
            "transcript": transcript,
        }

        post_replace_reason = None
        try:
            publish(
                final,
                root,
                "account-a",
                "meeting-c",
                fail_after_replace=True,
            )
        except Exception as exc:
            post_replace_reason = type(exc).__name__
        state["post_replace_failure"] = {
            "exception_type": post_replace_reason,
            "remaining_files": sorted(
                path.name for path in (root / "account-a" / "meeting-c").iterdir()
            ),
            "transcript_unchanged": transcript == {"segments": [{"text": "transcript truth"}]},
        }

        failed_source_dir = temp / "file-work" / "failed-source"
        failed_source_dir.mkdir(parents=True)
        failed_source = failed_source_dir / "input.wav"
        failed_source.write_bytes(b"not decodable")
        failed_transcript = json.loads(json.dumps(transcript))
        failure_reason = None
        try:
            publish(failed_source, root, "account-a", "meeting-b")
        except Exception as exc:
            failure_reason = type(exc).__name__
        unavailable = {
            "state": "unavailable",
            "relative_path": None,
            "byte_count": None,
            "duration_ms": None,
        }
        shutil.rmtree(failed_source_dir)
        state["failure"] = {
            "exception_type": failure_reason,
            "metadata": unavailable,
            "transcript_unchanged": failed_transcript == transcript,
            "remaining_meeting_b_files": sorted(
                path.name for path in (root / "account-a" / "meeting-b").iterdir()
            ),
            "source_exists_after_cleanup": failed_source.exists(),
        }
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
