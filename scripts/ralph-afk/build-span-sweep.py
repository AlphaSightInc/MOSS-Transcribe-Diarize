#!/usr/bin/env python3
"""Cut a sweep of frozen-span WAVs out of the pipeline probe's own two-lane audio.

Why this exists
---------------
Blocker 4 is a *boundary* defect: the decoder's closing timestamp lands at ~= the duration
of the audio it is handed, so a span whose speech runs to its end reports an end at or just
past its own duration and `BoundedCausalIdentityPreparer.prepare` rejects it with no
tolerance. Iteration 7 measured that once, on one span (2.50 s -> 2.51 s). One sample cannot
answer the question the fix has to answer -- *how far* past the end can a timestamp land? --
and the difference between "one quantisation tick" and "arbitrary" is the difference between
widening the bound and clamping to the span.

This tool builds the inputs for that measurement. It rebuilds the exact mixed timeline the
live pipeline probe drives the service with -- same schedule, same voices, same per-lane
offset, same mixer arithmetic -- and cuts it into arbitrary spans, so a cut is the same audio
the service would have mixed *by construction* rather than by description. Each cut is
written as one 16 kHz mono WAV that `live-identity-seam-probe.py` can take directly.

It is a Ralph evidence tool, not product source: nothing in the product imports it, it talks
to no service, and it writes only into the directory it is given.

Cuts
----
`--cut START:COUNT[:PAD]`, in samples on the mixed timeline. PAD appends that many samples of
silence *after* the cut, which is the control the boundary question needs: the same speech in
a longer span stops touching the span end. Repeat `--cut` for a sweep.
"""

from __future__ import annotations

import argparse
import array
import hashlib
import importlib.util
import json
import math
import sys
import tempfile
import wave
from pathlib import Path

SAMPLE_RATE = 16000
EDGE_WINDOW_SAMPLES = SAMPLE_RATE // 50  # 20 ms -- one glance at each end of a cut
SPEECH_DBFS_THRESHOLD = -45.0  # stated, not tuned: `say` output sits far above it


def load_pipeline_probe(path: Path):
    """Import the sibling probe by path -- its filename is not a Python identifier."""
    spec = importlib.util.spec_from_file_location("ralph_live_pipeline_probe", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves annotations through sys.modules[cls.__module__], so a module
    # executed before it is registered raises inside dataclasses rather than here.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def mix_lanes(
    lane_tracks: dict[str, array.array],
    lane_offset_samples: dict[str, int],
    total_samples: int,
) -> array.array:
    """The mixer's own per-sample arithmetic, with the mixer's own constants.

    `LiveCompatibilityMixer` needs a session, frames and timestamps; the arithmetic it
    applies to two aligned lanes is the four lines imported below, so they are imported
    rather than restated. A lane offset shifts that lane's whole timeline later, exactly as
    `--lane-offset-ms` shifts its `capture_timestamp_ns`.
    """
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from moss_transcribe_diarize.app.live_mixer import (
        _HEADROOM_GAIN,
        _LIMITER_RANGE,
        _LIMITER_THRESHOLD,
    )

    mixed = array.array("h", bytes(total_samples * 2))
    for index in range(total_samples):
        total = 0.0
        for lane, track in lane_tracks.items():
            source = index - lane_offset_samples.get(lane, 0)
            if 0 <= source < len(track):
                total += (track[source] / 32768.0) * _HEADROOM_GAIN
        if abs(total) > _LIMITER_THRESHOLD:
            total = math.copysign(
                _LIMITER_THRESHOLD
                + _LIMITER_RANGE * math.tanh((abs(total) - _LIMITER_THRESHOLD) / _LIMITER_RANGE),
                total,
            )
        mixed[index] = int(max(-1.0, min(1.0, total)) * 32767.0)
    return mixed


def dbfs(samples: array.array) -> float:
    """RMS of a window in dBFS; -inf for digital silence."""
    if not samples:
        return float("-inf")
    total = sum((value / 32768.0) ** 2 for value in samples)
    rms = math.sqrt(total / len(samples))
    return 20.0 * math.log10(rms) if rms > 0 else float("-inf")


def parse_cut(raw: str) -> tuple[int, int, int]:
    parts = raw.split(":")
    if len(parts) not in (2, 3):
        raise SystemExit(f"--cut wants START:COUNT[:PAD] in samples, got {raw!r}")
    try:
        start, count = int(parts[0]), int(parts[1])
        pad = int(parts[2]) if len(parts) == 3 else 0
    except ValueError:
        raise SystemExit(f"--cut fields must be integers, got {raw!r}") from None
    if start < 0 or count <= 0 or pad < 0:
        raise SystemExit(f"--cut needs start >= 0, count > 0, pad >= 0, got {raw!r}")
    return start, count, pad


def write_wav(path: Path, samples: array.array) -> str:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument(
        "--cut",
        action="append",
        default=[],
        required=True,
        help="START:COUNT[:PAD] in samples on the mixed timeline; repeatable",
    )
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--lead-seconds", type=float, default=1.0)
    parser.add_argument("--mic-voice", default="Samantha")
    parser.add_argument("--system-voice", default="Fred")
    parser.add_argument(
        "--lane-offset-ms",
        default="",
        help="comma-separated LANE=MS, the same form live-pipeline-probe.py takes",
    )
    parser.add_argument("--probe", default="", help="path to live-pipeline-probe.py")
    parser.add_argument("--report", default="", help="optional JSON index path")
    args = parser.parse_args()

    probe_path = Path(args.probe) if args.probe else Path(__file__).with_name("live-pipeline-probe.py")
    probe = load_pipeline_probe(probe_path)

    lane_offset_samples = {"microphone": 0, "system": 0}
    for item in (part.strip() for part in args.lane_offset_ms.split(",") if part.strip()):
        lane, _, milliseconds = item.partition("=")
        if lane not in lane_offset_samples:
            raise SystemExit(f"unknown lane in --lane-offset-ms: {lane}")
        lane_offset_samples[lane] = int(round(float(milliseconds) * SAMPLE_RATE / 1000.0))

    cuts = [parse_cut(raw) for raw in args.cut]
    total_samples = int(args.seconds * SAMPLE_RATE)
    for start, count, _pad in cuts:
        if start + count > total_samples:
            raise SystemExit(
                f"cut {start}:{count} runs past the {total_samples}-sample timeline; "
                f"raise --seconds"
            )

    with tempfile.TemporaryDirectory(prefix="moss-span-sweep-say-") as tmp:
        workdir = Path(tmp)
        mic_schedule, system_schedule = probe.build_schedule(args.seconds, args.lead_seconds)
        lane_tracks = {
            "microphone": probe.build_lane_track(args.mic_voice, mic_schedule, args.seconds, workdir),
            "system": probe.build_lane_track(args.system_voice, system_schedule, args.seconds, workdir),
        }
    mixed = mix_lanes(lane_tracks, lane_offset_samples, total_samples)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    index: dict = {
        "schema": "ralph-span-sweep.v1",
        "timeline": {
            "seconds": args.seconds,
            "lead_seconds": args.lead_seconds,
            "sample_rate": SAMPLE_RATE,
            "voices": {"microphone": args.mic_voice, "system": args.system_voice},
            "lane_offset_samples": lane_offset_samples,
            "mixed_sha256": hashlib.sha256(mixed.tobytes()).hexdigest(),
        },
        "speech_dbfs_threshold": SPEECH_DBFS_THRESHOLD,
        "cuts": [],
    }

    for start, count, pad in cuts:
        body = mixed[start : start + count]
        payload = body + array.array("h", bytes(pad * 2))
        name = f"span-s{start}-n{count}-p{pad}.wav"
        digest = write_wav(out_dir / name, payload)
        head = dbfs(body[:EDGE_WINDOW_SAMPLES])
        tail = dbfs(body[-EDGE_WINDOW_SAMPLES:])
        index["cuts"].append(
            {
                "name": name,
                "start_sample": start,
                "sample_count": len(payload),
                "speech_samples": count,
                "pad_samples": pad,
                "duration_sec": round(len(payload) / SAMPLE_RATE, 4),
                # The two facts the boundary question turns on: does the audio touch the
                # span end, and did it start mid-utterance?
                "head_dbfs": None if head == float("-inf") else round(head, 1),
                "tail_dbfs": None if tail == float("-inf") else round(tail, 1),
                "starts_in_speech": head > SPEECH_DBFS_THRESHOLD,
                "speech_reaches_cut_end": tail > SPEECH_DBFS_THRESHOLD,
                "ends_in_speech": pad == 0 and tail > SPEECH_DBFS_THRESHOLD,
                "sha256": digest,
            }
        )

    text = json.dumps(index, indent=2)
    print(text)
    if args.report:
        Path(args.report).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
