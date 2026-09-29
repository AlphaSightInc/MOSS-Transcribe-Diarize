"""Zero-provider shared WeSpeaker encoder concurrency falsifier.

Run from this worktree:
PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-gemini-live.venv/bin/python \
    prototypes/streaming-diarization/shared-encoder-concurrency/probe.py
"""
from __future__ import annotations

import json
import tempfile
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

from moss_transcribe_diarize.app.speaker_identity import _OnnxWeSpeakerEmbedder

ROOT = Path.cwd()
AUDIO = ROOT / "prototypes/gemini-live/.cache/long60/audio.wav"
REFERENCE = ROOT / "prototypes/gemini-live/window/long60/reference.jsonl"
MODEL = ROOT / "prototypes/streaming-diarization/data/voxceleb_resnet152_LM.onnx"
REPEATS = 4


def compare(a: np.ndarray, b: np.ndarray) -> tuple[float, float]:
    cosine = float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
    return float(np.max(np.abs(a - b))), cosine


def main() -> None:
    assert AUDIO.is_file() and REFERENCE.is_file() and MODEL.is_file()
    rows = [json.loads(line) for line in REFERENCE.read_text().splitlines()]
    chosen = {}
    for row in rows:
        if row["speaker"] not in chosen and row["end"] - row["start"] >= 7:
            chosen[row["speaker"]] = float(row["start"]) + 2.0
    assert len(chosen) == 5, chosen
    pcm, rate = sf.read(AUDIO, dtype="float32")
    assert rate == 16000 and pcm.ndim == 1
    encoder = _OnnxWeSpeakerEmbedder(MODEL, device="cpu", interval_workers=1)
    encoder.load()  # Product has already loaded the encoder before both workers overlap.
    with tempfile.TemporaryDirectory(prefix="moss-shared-encoder-") as scratch:
        paths = {}
        for speaker, start in chosen.items():
            for kind, duration in (("tentative", 1.0), ("registry", 2.5)):
                path = Path(scratch) / f"{len(paths)}.wav"
                a, b = round(start * rate), round((start + duration) * rate)
                sf.write(path, pcm[a:b], rate, subtype="PCM_16")
                paths[(speaker, kind)] = (path, duration)
        def embed(case):
            path, duration = paths[case]
            return np.asarray(encoder.embed(path, [(0.0, duration)]), dtype=np.float64)
        baseline = {case: embed(case) for case in paths}
        serial = defaultdict(list)
        for _ in range(2):
            for case in paths:
                serial[case].append(compare(baseline[case], embed(case)))
        barrier = threading.Barrier(2)
        active = 0
        overlapped_calls = 0
        lock = threading.Lock()
        def worker(kind):
            nonlocal active, overlapped_calls
            output = []
            for _ in range(REPEATS):
                for speaker in chosen:
                    case = (speaker, kind)
                    barrier.wait(timeout=30)
                    with lock:
                        active += 1
                        if active == 2:
                            overlapped_calls += 1
                    try:
                        vector = embed(case)
                    finally:
                        with lock:
                            active -= 1
                    output.append((case, compare(baseline[case], vector)))
            return output
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(worker, "tentative")
            b = pool.submit(worker, "registry")
            concurrent = a.result() + b.result()
        grouped = defaultdict(list)
        for case, result in concurrent:
            grouped[case].append(result)
        cases = []
        for case in paths:
            serial_values, parallel_values = serial[case], grouped[case]
            cases.append({"speaker": case[0], "kind": case[1],
                          "duration_seconds": paths[case][1],
                          "serial_max_abs_delta": max(x[0] for x in serial_values),
                          "serial_min_cosine": min(x[1] for x in serial_values),
                          "concurrent_max_abs_delta": max(x[0] for x in parallel_values),
                          "concurrent_min_cosine": min(x[1] for x in parallel_values)})
        result = {"schema": "shared-wespeaker-concurrency.v1", "source": str(AUDIO),
                  "model": str(MODEL), "encoder_class": type(encoder).__name__,
                  "same_encoder_instance": True, "workers": 2, "repeats_per_case": REPEATS,
                  "concurrent_call_pairs_observed": overlapped_calls,
                  "cases": cases,
                  "serial_max_abs_delta": max(x["serial_max_abs_delta"] for x in cases),
                  "serial_min_cosine": min(x["serial_min_cosine"] for x in cases),
                  "concurrent_max_abs_delta": max(x["concurrent_max_abs_delta"] for x in cases),
                  "concurrent_min_cosine": min(x["concurrent_min_cosine"] for x in cases)}
        print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
