"""Six-call source-backed contained-interruption decoder matrix.

Requires the identity lease recorded in GPU.md. One command, peak one, no retries:

    PYTHONPATH=. .venv/bin/python .../source_backed_probe.py \
      --endpoint http://127.0.0.1:19135/v1 --output-dir .../source-backed
"""
from __future__ import annotations

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np

from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError
from moss_transcribe_diarize.transcript_parser import parse_transcript


ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "evidence/live-policy-sweep-20260825/corpus"
OUTER_SOURCE = CORPUS / "mono_javier_intro_50s/audio.wav"
INTERRUPT_SOURCE = CORPUS / "discussion_rtfl_90s/audio.wav"
REQUEST_LOG = Path("/Users/gao/Documents/Codex/2026-09-19/moss-round2/decoder-requests.jsonl")
RATE = 16_000
INTERRUPT_START = 0.63
INTERRUPT_END = 2.07
MIX_START = 20.0
LEASE_LIMIT = 259


def sent_count() -> int:
    sent = 0
    for line in REQUEST_LOG.read_text().splitlines():
        row = json.loads(line)
        if row.get("kind") == "start":
            sent = max(sent, int(row["sent"]))
    return sent


def read_pcm(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as source:
        assert (source.getframerate(), source.getnchannels(), source.getsampwidth()) == (RATE, 1, 2)
        return np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float64) / 32768.0


def write_pcm(path: Path, samples: np.ndarray) -> None:
    encoded = np.clip(np.rint(samples * 32768.0), -32768, 32767).astype("<i2")
    with wave.open(str(path), "wb") as destination:
        destination.setnchannels(1)
        destination.setsampwidth(2)
        destination.setframerate(RATE)
        destination.writeframes(encoded.tobytes())


def rms(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples))))


def build_cases(output_dir: Path) -> tuple[list[tuple[str, Path]], dict[str, object]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    outer = read_pcm(OUTER_SOURCE)
    interrupt_all = read_pcm(INTERRUPT_SOURCE)
    interrupt = interrupt_all[round(INTERRUPT_START * RATE) : round(INTERRUPT_END * RATE)]
    mix_start = round(MIX_START * RATE)
    outer_region = outer[mix_start : mix_start + len(interrupt)]
    outer_rms = rms(outer_region)
    interrupt_rms = rms(interrupt)

    rows: list[tuple[str, Path]] = []
    measurements: dict[str, object] = {
        "sample_rate": RATE,
        "outer_source": str(OUTER_SOURCE),
        "interrupt_source": str(INTERRUPT_SOURCE),
        "interrupt_source_interval_sec": [INTERRUPT_START, INTERRUPT_END],
        "mix_start_sec": MIX_START,
        "outer_region_rms": outer_rms,
        "interrupt_source_rms": interrupt_rms,
        "cases": {},
    }

    def retain(name: str, samples: np.ndarray, detail: dict[str, object]) -> None:
        path = output_dir / f"{name}.wav"
        write_pcm(path, samples)
        rows.append((name, path))
        measurements["cases"][name] = {"duration_sec": len(samples) / RATE, **detail}

    retain("outer_only", outer, {"construction": "unaltered outer source"})
    retain("interruption_only", interrupt, {"construction": "unaltered source interval"})
    sequential = np.concatenate((outer[:mix_start], interrupt, outer[mix_start:]))
    retain(
        "sequential_control",
        sequential,
        {"construction": "interrupt inserted before outer continuation; no acoustic overlap"},
    )

    for sir_db in (-3.0, 0.0, 3.0):
        # SIR is outer RMS / interruption RMS over the inserted interval.
        desired_interrupt_rms = outer_rms / (10.0 ** (sir_db / 20.0))
        scaled_interrupt = interrupt * (desired_interrupt_rms / interrupt_rms)
        mixed = outer.copy()
        mixed[mix_start : mix_start + len(interrupt)] += scaled_interrupt
        peak_before = float(np.max(np.abs(mixed)))
        global_gain = min(1.0, 0.95 / peak_before)
        mixed *= global_gain
        observed_outer_rms = outer_rms * global_gain
        observed_interrupt_rms = rms(scaled_interrupt) * global_gain
        observed_sir = 20.0 * math.log10(observed_outer_rms / observed_interrupt_rms)
        retain(
            f"overlap_sir_{sir_db:+.0f}db".replace("+", "plus").replace("-", "minus"),
            mixed,
            {
                "construction": "source-backed additive overlap",
                "target_sir_db": sir_db,
                "observed_sir_db": observed_sir,
                "global_gain": global_gain,
                "peak_before_gain": peak_before,
            },
        )
    return rows, measurements


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--seed", type=Path)
    args = parser.parse_args()

    before = sent_count()
    cases, construction = build_cases(args.output_dir)
    cases = cases[args.start_index :]
    if before + len(cases) > LEASE_LIMIT:
        raise RuntimeError(
            f"identity decoder lease insufficient: sent={before}, needed={len(cases)}, limit={LEASE_LIMIT}"
        )
    runner = VllmRunner(
        base_url=args.endpoint,
        model="OpenMOSS-Team/MOSS-Transcribe-Diarize",
        timeout=600.0,
    )
    decoded = json.loads(args.seed.read_text())["decoded"] if args.seed else []
    for name, path in cases:
        try:
            result = runner.transcribe(path, max_new_tokens=6000, decoding="greedy")
            segments = parse_transcript(result.text)
            row = {
                "case": name,
                "audio": str(path),
                "raw_text": result.text,
                "generated_tokens": result.generated_tokens,
                "elapsed_sec": round(result.elapsed_sec, 6),
                "segments": [
                    {"start": item.start, "end": item.end, "speaker": item.speaker, "text": item.text}
                    for item in segments
                ],
            }
        except EmptyTranscriptionError as error:
            row = {
                "case": name,
                "audio": str(path),
                "raw_text": error.text,
                "generated_tokens": error.generated_tokens,
                "segments": [],
                "error": type(error).__name__,
                "empty_cause": error.cause.value,
            }
        decoded.append(row)
        after = sent_count()
        record = {
            "sent_before": before,
            "sent_after": after,
            "requests_this_invocation": after - before,
            "construction": construction,
            "decoded": decoded,
        }
        (args.output_dir / "results.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n"
        )
    after = sent_count()
    print(
        json.dumps(
            {
                "sent_before": before,
                "sent_after": after,
                "requests_this_invocation": after - before,
                "speakers": {
                    row["case"]: (
                        None
                        if row.get("segments") is None
                        else sorted({segment["speaker"] for segment in row["segments"]})
                    )
                    for row in decoded
                },
                "segments": {
                    row["case"]: None if row.get("segments") is None else len(row["segments"])
                    for row in decoded
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
