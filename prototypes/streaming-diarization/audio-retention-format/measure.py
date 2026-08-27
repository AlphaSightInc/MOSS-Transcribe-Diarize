#!/usr/bin/env python3
"""PROTOTYPE: measure retained-audio format sizes on real MOSS speech."""

from __future__ import annotations

import json
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "prototypes/streaming-diarization/data/real/benchmark_5m"
VARIANTS = {
    "wav_pcm16": (".wav", ["-c:a", "pcm_s16le"]),
    "mp3_cbr_32k": (".mp3", ["-c:a", "libmp3lame", "-b:a", "32k"]),
    "mp3_cbr_48k": (".mp3", ["-c:a", "libmp3lame", "-b:a", "48k"]),
    "mp3_cbr_64k": (".mp3", ["-c:a", "libmp3lame", "-b:a", "64k"]),
}


def run(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout


def probe(path: Path) -> dict[str, object]:
    payload = json.loads(
        run(
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,bits_per_sample,bit_rate:format=duration,size,bit_rate",
            "-of",
            "json",
            str(path),
        )
    )
    stream = payload["streams"][0]
    container = payload["format"]
    duration_seconds = float(container["duration"])
    size_bytes = int(container["size"])
    return {
        "codec": stream["codec_name"],
        "sample_rate_hz": int(stream["sample_rate"]),
        "channels": int(stream["channels"]),
        "bits_per_sample": int(stream.get("bits_per_sample") or 0),
        "duration_seconds": duration_seconds,
        "size_bytes": size_bytes,
        "measured_bytes_per_hour": round(size_bytes * 3600 / duration_seconds),
        "container_bit_rate": int(container["bit_rate"]),
    }


def main() -> None:
    inputs = sorted(CORPUS.glob("*/audio.wav"))
    if not inputs:
        raise SystemExit(f"no inputs found under {CORPUS}")

    state: dict[str, object] = {
        "question": (
            "What size and local conversion time do WAV PCM16 and 32/48/64 kbit/s CBR "
            "MP3 produce for retained 16 kHz mono mixed meeting audio?"
        ),
        "ffmpeg": run("ffmpeg", "-version").splitlines()[0],
        "corpus": str(CORPUS.relative_to(ROOT)),
        "input_count": len(inputs),
        "inputs": [],
        "outputs": [],
    }

    with tempfile.TemporaryDirectory(prefix="moss-audio-format-prototype-") as temp_dir:
        temp = Path(temp_dir)
        for input_path in inputs:
            input_state = probe(input_path)
            input_state["path"] = str(input_path.relative_to(ROOT))
            state["inputs"].append(input_state)

            for variant, (suffix, codec_args) in VARIANTS.items():
                output_path = temp / f"{input_path.parent.name}-{variant}{suffix}"
                started = time.perf_counter()
                subprocess.run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-v",
                        "error",
                        "-y",
                        "-i",
                        str(input_path),
                        "-map_metadata",
                        "-1",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        *codec_args,
                        str(output_path),
                    ],
                    check=True,
                )
                encode_seconds = time.perf_counter() - started
                output_state = probe(output_path)
                output_state.update(
                    {
                        "encode_seconds": round(encode_seconds, 6),
                        "encode_realtime_multiple": round(
                            float(output_state["duration_seconds"]) / encode_seconds,
                            3,
                        ),
                        "projected_encode_seconds_per_audio_hour": round(
                            encode_seconds * 3600 / float(output_state["duration_seconds"]),
                            3,
                        ),
                        "source": str(input_path.relative_to(ROOT)),
                        "variant": variant,
                    }
                )
                state["outputs"].append(output_state)

    summary: dict[str, dict[str, int]] = {}
    for variant in VARIANTS:
        hourly = [
            int(item["measured_bytes_per_hour"])
            for item in state["outputs"]
            if item["variant"] == variant
        ]
        projected_times = [
            float(item["projected_encode_seconds_per_audio_hour"])
            for item in state["outputs"]
            if item["variant"] == variant
        ]
        realtime_multiples = [
            float(item["encode_realtime_multiple"])
            for item in state["outputs"]
            if item["variant"] == variant
        ]
        summary[variant] = {
            "minimum_bytes_per_hour": min(hourly),
            "median_bytes_per_hour": round(statistics.median(hourly)),
            "maximum_bytes_per_hour": max(hourly),
            "minimum_projected_encode_seconds_per_hour": round(min(projected_times), 3),
            "median_projected_encode_seconds_per_hour": round(
                statistics.median(projected_times), 3
            ),
            "maximum_projected_encode_seconds_per_hour": round(max(projected_times), 3),
            "median_encode_realtime_multiple": round(
                statistics.median(realtime_multiples), 3
            ),
        }
    state["summary"] = summary
    print(json.dumps(state, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
