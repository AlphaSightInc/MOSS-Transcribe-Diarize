#!/usr/bin/env python3
"""Measure the two capture-health thresholds before implementing them.

Questions this probe answers
----------------------------
The charter (`docs/phase1-afk-charter.md` section 4) makes two demands the client cannot
meet without numbers:

  "Clipping. Meter and warn on sustained full-scale; the measured loopback lane hit
   +/-32767."
  "Silent mic lane -> the status line must name how to change Chrome's default input."

So:

  Q1. What per-frame statistic marks a frame as clipped, and at what fraction, such that
      real speech at ordinary and loud levels never trips it?
  Q2. How many consecutive frames make clipping "sustained" rather than a transient?
  Q3. How many consecutive silent frames mean "the microphone is not working" rather than
      "somebody stopped talking"? The answer must clear real speech pauses.

Method
------
Real 16 kHz mono audio already in the tree, framed at the descriptor geometry the
production client actually uses (`frame_samples` = 8000 = 500 ms):

  * `prototypes/streaming-diarization/l15/exploratory/f2-dual-lane/source/{local,remote}.wav`
    -- 59.6 s of real two-party meeting audio, one file per lane. This is the
    "must never warn" corpus, and its pause structure answers Q3.
  * `prototypes/streaming-diarization/dl2-capture/evidence/d3-leading-silence/fixtures/leading-060s.wav`
    -- 120 s with 60 s of real leading silence, i.e. a lane that genuinely is not
    delivering sound. This is the "must warn" corpus for silence.
  * The same speech, digitally gained until it clips, standing in for the measured
    loopback lane that "hit full-scale PCM (+/-32767)". Gain is the honest model: the
    observed failure was a too-hot source, not distortion of a different shape.

Every statistic is computed on the values the SERVER receives, i.e. after the client's
own `Math.round(clamp(x) * 32767)` encoding -- a sample counts as clipped only when it
encodes to exactly +/-32767.

One command:
    /opt/homebrew/bin/python3 evidence/phase1/x2-capture-client/probes/measure_capture_health_thresholds_probe.py

Exit 0 = the thresholds compiled into `frontend/src/capture/captureClient.ts` still
separate every corpus above. Exit 1 = they no longer do, or a corpus moved.
"""
from __future__ import annotations

import array
import math
import re
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
CLIENT = REPO / "frontend" / "src" / "capture" / "captureClient.ts"

FRAME_SAMPLES = 8000  # the production descriptor geometry: 500 ms at 16 kHz
SAMPLE_RATE = 16000
FULL_SCALE = 32767

SPEECH = [
    REPO / "prototypes/streaming-diarization/l15/exploratory/f2-dual-lane/source/local.wav",
    REPO / "prototypes/streaming-diarization/l15/exploratory/f2-dual-lane/source/remote.wav",
]
LEADING_SILENCE = (
    REPO
    / "prototypes/streaming-diarization/dl2-capture/evidence/d3-leading-silence/fixtures/leading-060s.wav"
)


def read_float_mono(path: Path) -> list[float]:
    with wave.open(str(path)) as handle:
        if handle.getsampwidth() != 2 or handle.getnchannels() != 1:
            raise SystemExit(f"{path} is not 16-bit mono")
        if handle.getframerate() != SAMPLE_RATE:
            raise SystemExit(f"{path} is {handle.getframerate()} Hz, expected {SAMPLE_RATE}")
        raw = array.array("h")
        raw.frombytes(handle.readframes(handle.getnframes()))
    return [value / 32768.0 for value in raw]


def frames(samples: list[float]) -> list[list[float]]:
    return [
        samples[start : start + FRAME_SAMPLES]
        for start in range(0, len(samples) - FRAME_SAMPLES + 1, FRAME_SAMPLES)
    ]


def encode(sample: float) -> int:
    """Exactly what `pcm16Base64` does, one sample at a time."""
    return round(max(-1.0, min(1.0, sample)) * FULL_SCALE)


def frame_stats(frame: list[float]) -> tuple[float, float]:
    """(rms, fraction of samples that encode to full scale)."""
    total = 0.0
    clipped = 0
    for sample in frame:
        total += sample * sample
        if abs(encode(sample)) >= FULL_SCALE:
            clipped += 1
    return math.sqrt(total / len(frame)), clipped / len(frame)


def runs_of(flags: list[bool]) -> list[int]:
    runs: list[int] = []
    current = 0
    for flag in flags:
        if flag:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def constant(name: str, source: str) -> float:
    match = re.search(rf"^const {name} = ([0-9.eE_+-]+);", source, re.MULTILINE)
    if not match:
        raise SystemExit(f"{CLIENT.name} no longer declares {name}")
    return float(match.group(1).replace("_", ""))


def main() -> int:
    source = CLIENT.read_text(encoding="utf-8")
    silence_rms = constant("SILENCE_RMS", source)
    clipped_fraction = constant("CLIPPED_FRAME_FRACTION", source)
    sustained_clipping = int(constant("SUSTAINED_CLIPPING_FRAMES", source))
    silent_frames = int(constant("SILENT_MICROPHONE_FRAMES", source))

    print("== thresholds currently compiled into the client ==")
    print(f"  SILENCE_RMS               {silence_rms:g}")
    print(f"  CLIPPED_FRAME_FRACTION    {clipped_fraction:g}")
    print(f"  SUSTAINED_CLIPPING_FRAMES {sustained_clipping}  "
          f"({sustained_clipping * FRAME_SAMPLES / SAMPLE_RATE:g} s)")
    print(f"  SILENT_MICROPHONE_FRAMES  {silent_frames}  "
          f"({silent_frames * FRAME_SAMPLES / SAMPLE_RATE:g} s)")

    failures: list[str] = []

    print("\n== Q1/Q2: real speech at rising gain, per 500 ms frame ==")
    print(f"  {'corpus':38} {'gain':>6} {'peak':>7} {'rms max':>8} "
          f"{'clip frac max':>13} {'longest clipped run':>20}")
    for path in SPEECH:
        samples = read_float_mono(path)
        for gain in (1.0, 2.0, 4.0, 8.0, 16.0, 32.0):
            stats = [frame_stats([sample * gain for sample in frame]) for frame in frames(samples)]
            peak = max(abs(encode(sample * gain)) for sample in samples)
            rms_max = max(rms for rms, _ in stats)
            clip_max = max(fraction for _, fraction in stats)
            flags = [fraction >= clipped_fraction for _, fraction in stats]
            longest = max(runs_of(flags), default=0)
            print(f"  {path.name:38} {gain:6g} {peak:7d} {rms_max:8.4f} "
                  f"{clip_max:13.6f} {longest:20d}")
            warns = longest >= sustained_clipping
            # Native gain is real captured audio, peaking at 5659 and 27821 respectively;
            # neither produces a single full-scale sample and neither may warn. Above
            # that the corpus is deliberately being driven into the encoder's ceiling,
            # and by gain 16 it is pinned there for tens of seconds.
            if gain <= 1.0 and warns:
                failures.append(
                    f"{path.name} at native gain (peak {peak}) would warn about clipping; "
                    "real captured speech must not"
                )
            if gain >= 16.0 and not warns:
                failures.append(
                    f"{path.name} at gain {gain:g} pins the encoder at full scale for "
                    f"{longest} consecutive frames but would not warn"
                )

    # Nothing above pins SUSTAINED_CLIPPING_FRAMES from below: at native gain the corpus
    # produces no clipped frame at all, so even a 1-frame window would stay quiet on it.
    # "Sustained" only means something against a real transient overload, so build one --
    # real speech with a short burst driven into the ceiling.
    print("\n== Q2 lower bound: transient overload on real speech must NOT warn ==")
    # The two bounds are product statements, deliberately NOT derived from the constant
    # under test: half a second of overload is a transient and must stay quiet; three
    # seconds of it is the condition the charter asks to be warned about.
    TRANSIENT_FRAMES = 1
    DEFINITELY_SUSTAINED_FRAMES = 6
    print(f"  {'burst frames':>13} {'burst seconds':>14} {'clipped run':>12} {'warns?':>8}")
    speech = read_float_mono(SPEECH[0])
    for burst in range(1, DEFINITELY_SUSTAINED_FRAMES + 1):
        loud = list(speech)
        start = FRAME_SAMPLES * 10
        for index in range(start, start + FRAME_SAMPLES * burst):
            loud[index] = max(-1.0, min(1.0, loud[index] * 64))
        stats = [frame_stats(frame) for frame in frames(loud)]
        flags = [fraction >= clipped_fraction for _, fraction in stats]
        longest = max(runs_of(flags), default=0)
        warns = longest >= sustained_clipping
        seconds = burst * FRAME_SAMPLES / SAMPLE_RATE
        print(f"  {burst:13d} {seconds:14g} {longest:12d} {str(warns):>8}")
        if burst <= TRANSIENT_FRAMES and warns:
            failures.append(
                f"a {seconds:g} s overload on real speech would be reported as sustained "
                "clipping; that is a transient, not a condition"
            )
        if burst >= DEFINITELY_SUSTAINED_FRAMES and not warns:
            failures.append(
                f"{seconds:g} s of continuous full-scale audio would never be warned about"
            )

    print("\n== Q3: silent-run structure of real speech vs a lane that is really silent ==")
    print(f"  {'corpus':38} {'frames':>7} {'silent':>7} {'longest silent run':>19}")
    for path in SPEECH + [LEADING_SILENCE]:
        samples = read_float_mono(path)
        stats = [frame_stats(frame) for frame in frames(samples)]
        flags = [rms < silence_rms for rms, _ in stats]
        longest = max(runs_of(flags), default=0)
        print(f"  {path.name:38} {len(stats):7d} {sum(flags):7d} {longest:19d}")
        if path in SPEECH and longest >= silent_frames:
            failures.append(
                f"{path.name} has a {longest}-frame natural pause and would be reported as a "
                "silent microphone"
            )
        if path == LEADING_SILENCE and longest < silent_frames:
            failures.append(
                f"{path.name} carries {longest} consecutive genuinely silent frames, which is "
                f"under the {silent_frames}-frame threshold: a dead lane would never be reported"
            )

    print("\n== synthetic controls ==")
    controls = {
        "digital silence": [0.0] * (FRAME_SAMPLES * 20),
        "5e-5 dither (the PRD's no-op-gate example)": [5e-5] * (FRAME_SAMPLES * 20),
        "full-scale square (the measured loopback lane)": [
            1.0 if (index // 8) % 2 == 0 else -1.0 for index in range(FRAME_SAMPLES * 20)
        ],
        "0.98 sine, hot but unclipped": [
            0.98 * math.sin(2 * math.pi * 997 * index / SAMPLE_RATE)
            for index in range(FRAME_SAMPLES * 20)
        ],
    }
    print(f"  {'signal':48} {'rms':>8} {'clip frac':>10} {'silent?':>8} {'clip warn?':>11}")
    for name, samples in controls.items():
        stats = [frame_stats(frame) for frame in frames(samples)]
        rms_value = stats[0][0]
        clip_value = stats[0][1]
        silent = all(rms < silence_rms for rms, _ in stats)
        clip_flags = [fraction >= clipped_fraction for _, fraction in stats]
        warns = max(runs_of(clip_flags), default=0) >= sustained_clipping
        print(f"  {name:48} {rms_value:8.5f} {clip_value:10.5f} {str(silent):>8} {str(warns):>11}")
        if name.startswith("digital silence") and not silent:
            failures.append("digital silence is not classified silent")
        if name.startswith("5e-5") and not silent:
            failures.append("5e-5 dither is not classified silent; the preflight gate is a no-op")
        if name.startswith("full-scale square") and not warns:
            failures.append("a full-scale square wave does not raise sustained clipping")
        if name.startswith("0.98") and warns:
            failures.append("a hot-but-unclipped 0.98 sine raises sustained clipping")

    print()
    if failures:
        print("PROBE FAIL")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(
        "PROBE OK  the compiled thresholds separate real captured speech from audio pinned at "
        "full scale, and real speech pauses from a genuinely silent lane"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
