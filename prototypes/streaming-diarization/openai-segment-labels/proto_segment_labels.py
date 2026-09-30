"""J1 per-segment labels through the production identity paths (live + File).

Question: with a non-diarizing OpenAI-compatible model, each returned segment gets its own
provisional label and local WeSpeaker linking must join voices. Does the production
composition recover speakers, or do short segments become spurious speakers?
Also: does spreading timeless text over voiced frames (vs uniform) keep words through the
production WebRTC word gate?

Provider stand-in: golden reference lines -> segments (lines > 8 s split into ~6 s pieces,
like whisper segments). Everything after the provider is production code:
parse_transcription, GeminiHybridEngine + ContinuityRegistry + WeSpeakerWindowEmbeddings +
WebRtcWordGate (live, 90 s context / 15 s refresh), GeminiFileRunner (FinalWordPolicy).

Run: <venv python> proto_segment_labels.py [--live] [--cases N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
import wave
from pathlib import Path

from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app.gemini_continuity_registry import ContinuityRegistry  # noqa: E402
from moss_transcribe_diarize.app.gemini_file_runner import GeminiFileRunner  # noqa: E402
from moss_transcribe_diarize.app.gemini_final_policy import WebRtcWordGate  # noqa: E402
from moss_transcribe_diarize.app.gemini_hybrid_engine import (  # noqa: E402
    GeminiHybridEngine, GrowingContextWindowScheduler, WeSpeakerWindowEmbeddings)
from moss_transcribe_diarize.app.gemini_live_runtime import GeminiRelabel, GeminiRolling  # noqa: E402
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords  # noqa: E402
from moss_transcribe_diarize.app.openai_compatible_provider import (  # noqa: E402
    NoPreviewWords, parse_transcription)
from moss_transcribe_diarize.app.speaker_identity import WeSpeakerResNet152LmAdapter  # noqa: E402
from moss_transcribe_diarize.subtitle import subtitle_segments_from_transcript  # noqa: E402

S = 16000
DATA = Path(os.environ.get("BENCH_DATA", "/Users/gao/Desktop/AI_Projects/Github_Projects/"
                           "MOSS-Transcribe-Diarize/prototypes/streaming-diarization/data"))


def cases():
    real = DATA / "real"
    tiers = ("benchmark_diarization_1min/samples", "calibration_diarization_3min/samples")
    return [*(case for tier in tiers for case in sorted((real / tier).iterdir()) if case.is_dir()),
            real / "regression_fixtures/youtube_rtfl_first_90s"]


def load(case: Path):
    with wave.open(str(case / "audio.wav")) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, S)
        pcm = wav.readframes(wav.getnframes())
    lines = []
    for raw in (case / "reference.jsonl").read_text().splitlines():
        row = json.loads(raw)
        start, end = row.get("start"), row.get("end")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)) and end > start:
            tokens = row["text"].split()
            pieces = max(1, math.ceil((end - start) / 8)) if end - start > 8 else 1
            for i in range(pieces):  # whisper-like segment sizes
                lo, hi = start + (end - start) * i / pieces, start + (end - start) * (i + 1) / pieces
                part = tokens[len(tokens) * i // pieces:len(tokens) * (i + 1) // pieces]
                if part:
                    lines.append((lo, hi, row["speaker"], part))
    return pcm, sorted(lines)


def response(lines, a: float, b: float, variant: str) -> dict:
    segments = []
    for lo, hi, speaker, tokens in lines:
        if hi <= a or lo >= b:
            continue
        first = math.floor(len(tokens) * max(0.0, a - lo) / (hi - lo))
        last = math.ceil(len(tokens) * min(1.0, (b - lo) / (hi - lo)))
        if tokens[first:last]:
            row = {"start": max(lo, a) - a, "end": min(hi, b) - a, "text": " ".join(tokens[first:last])}
            if variant == "oracle":
                row["speaker"] = speaker
            segments.append(row)
    if variant.startswith("json"):
        return {"text": " ".join(row["text"] for row in segments)}
    return {"segments": segments}


class Silent:
    def is_speech(self, _frame, _rate):
        return False


def attach_short(words: GeminiWords) -> GeminiWords:
    """Candidate: a <2 s segment label takes its previous (else next) segment's label."""
    order = list(dict.fromkeys(w.speaker for w in words.words))
    speech = {label: sum(w.end_sample - w.start_sample for w in words.words if w.speaker == label)
              for label in order}
    long = [label for label in order if speech[label] >= 2 * S]
    if not long:
        return words
    mapping = {}
    for i, label in enumerate(order):
        if speech[label] >= 2 * S:
            mapping[label] = label
        else:
            before = [x for x in order[:i] if x in long]
            mapping[label] = before[-1] if before else next(x for x in order[i:] if x in long)
    return GeminiWords(tuple(GeminiWord(w.text, mapping[w.speaker], w.start_sample, w.end_sample)
                             for w in words.words), words.clamped, words.dropped)


class Provider:
    def __init__(self, lines, variant):
        self.lines, self.variant, self.window = lines, variant, (0.0, 0.0)
        self.parsed = 0

    def diarize(self, pcm16, *, deadline, kind, diarize=True):
        del deadline, kind, diarize
        a, b = self.window if self.window != (0.0, 0.0) else (0.0, len(pcm16) / (2 * S))
        assert abs((b - a) - len(pcm16) / (2 * S)) < 1e-6
        words = parse_transcription(response(self.lines, a, b, self.variant), pcm16=pcm16,
                                    vad=Silent() if self.variant == "json_uniform" else None)
        if self.variant == "attach":
            words = attach_short(words)
        self.parsed += len(words.words)
        return words


def score(rows, lines):
    """Time overlap of output rows vs truth, one-to-one label mapping (spurious = error)."""
    tokens_out = sum(len(row[3].split()) for row in rows)
    tokens_true = sum(len(line[3]) for line in lines)
    rows = [row[:3] for row in rows]
    labels = sorted({row[2] for row in rows}, key=str)
    speakers = sorted({line[2] for line in lines})
    matrix = [[0.0] * len(speakers) for _ in labels]
    truth_total = sum(hi - lo for lo, hi, _s, _t in lines)
    for lo, hi, label in rows:
        for tlo, thi, speaker, _tokens in lines:
            matrix[labels.index(label)][speakers.index(speaker)] += max(0.0, min(hi, thi) - max(lo, tlo))
    covered = sum(map(sum, matrix))
    r, c = linear_sum_assignment([[-v for v in row] for row in matrix]) if labels else ([], [])
    matched = sum(matrix[i][j] for i, j in zip(r, c) if labels[i] is not None)
    unlabelled = sum(matrix[labels.index(None)]) if None in labels else 0.0
    return {"acc": round(matched / covered, 3) if covered else None,
            "k_true": len(speakers), "k_out": len([x for x in labels if x is not None]),
            "unlabelled": round(unlabelled / covered, 3) if covered else None,
            "coverage": round(covered / truth_total, 3),
            "tokens_ratio": round(tokens_out / tokens_true, 3)}


def file_path(pcm, lines, variant, encoder, work: Path):
    audio = work / "audio.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1), wav.setsampwidth(2), wav.setframerate(S)
        wav.writeframes(pcm)
    provider = Provider(lines, variant)
    runner = GeminiFileRunner(provider, encoder)
    result = runner.transcribe(audio)
    rows = [(row.start, row.end, row.speaker, row.text) for row in
            subtitle_segments_from_transcript(result.text, postprocess=False)]
    return {**score(rows, lines), "gate_kept": round(len(runner._terminal.last_words)
                                                     / max(1, provider.parsed), 3)}


def live_path(pcm, lines, variant, encoder):
    rows: dict[tuple, tuple] = {}
    provider = Provider(lines, variant)

    def publish(update):
        if isinstance(update, GeminiRolling):
            for seg in update.segments:
                rows[(seg.start_sample, seg.end_sample, seg.text)] = seg
        elif isinstance(update, GeminiRelabel):
            for key in [k for k in rows if update.start_sample <= k[0] and k[1] <= update.end_sample]:
                del rows[key]
            for seg in update.segments:
                rows[(seg.start_sample, seg.end_sample, seg.text)] = seg

    engine = GeminiHybridEngine(
        publish, word_source=NoPreviewWords(),
        window_scheduler=GrowingContextWindowScheduler(max_seconds=90, stride_seconds=15),
        registry=ContinuityRegistry(embedding_threshold=.46, within_window_threshold=.60,
                                    birth_min_seconds=2),
        diarizer=provider, terminal=None, embedding_source=WeSpeakerWindowEmbeddings(encoder),
        word_gate=WebRtcWordGate(), source_lane="system")
    engine._idle_seconds = 10 ** 6
    step = 15 * S
    total = len(pcm) // 2
    for start in range(0, total, step):
        end = min(total, start + step)
        if end - start == step:
            provider.window = (max(0, end - 90 * S) / S, end / S)
        engine.push_audio(start, pcm[start * 2:end * 2])
        if engine._future is not None:
            engine._future.result(timeout=600)
    if engine._rolling_frontier < total:
        provider.window = (engine._rolling_frontier / S, total / S)
        asyncio.run(engine.drain_tail(600))
    engine.close()
    out = [(seg.start_sample / S, seg.end_sample / S, seg.speaker, seg.text)
           for seg in rows.values()]
    return score(out, lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cases", type=int, default=99)
    parser.add_argument("--variants", default="oracle,seg,attach,json_voiced,json_uniform")
    args = parser.parse_args()
    encoder = WeSpeakerResNet152LmAdapter(DATA / "voxceleb_resnet152_LM.onnx", device="cpu")
    work = Path(os.environ.get("TMPDIR", "/tmp")) / "proto_segment_labels"
    work.mkdir(parents=True, exist_ok=True)
    for case in cases()[:args.cases]:
        pcm, lines = load(case)
        for variant in args.variants.split(","):
            started = time.monotonic()
            row = (live_path(pcm, lines, variant, encoder) if args.live
                   else file_path(pcm, lines, variant, encoder, work))
            print(json.dumps({"path": "live" if args.live else "file", "case": case.name,
                              "variant": variant, **row,
                              "wall_s": round(time.monotonic() - started, 1)}), flush=True)


if __name__ == "__main__":
    main()
