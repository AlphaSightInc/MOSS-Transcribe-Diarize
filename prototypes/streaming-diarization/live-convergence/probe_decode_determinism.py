"""Is the deployed vLLM decoder bit-reproducible for an identical greedy request?

M0(d) asks whether two fresh live runs produce hash-identical transcripts. On the
first pairing the *endpointer* was fully deterministic (24/24 span_frozen events
byte-identical) and exactly one span decoded differently (span 19 of
lex_bill_ackman, samples 760000-800000: 20 vs 37 generated tokens). That points at
the decoder, not at live-mode logic. This probe settles it without any live
session: extract that span's PCM, send the SAME multipart request N times through
the SAME `VllmRunner` the service uses, and compare text + token counts.

  python probe_decode_determinism.py [--repeats 12] [--output out.json]
                                     [--case lex_bill_ackman]
                                     [--start-sample 760000 --end-sample 800000]

Exit 0 always -- this is a measurement, not a gate. The verdict is in the output.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import sys
import tempfile
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402

SAMPLE_RATE = 16000


def extract_wav(source: Path, start_sample: int, end_sample: int, dest: Path) -> None:
    with wave.open(str(source), "rb") as src:
        if src.getframerate() != SAMPLE_RATE or src.getsampwidth() != 2 or src.getnchannels() != 1:
            raise SystemExit(f"{source} is not mono pcm16 @ {SAMPLE_RATE}")
        src.setpos(start_sample)
        pcm = src.readframes(end_sample - start_sample)
    with wave.open(str(dest), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="lex_bill_ackman")
    parser.add_argument("--corpus", default="prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples")
    parser.add_argument("--start-sample", type=int, default=760000)
    parser.add_argument("--end-sample", type=int, default=800000)
    parser.add_argument("--token-cap", type=int, default=286, help="live token cap for a 2.5 s span")
    parser.add_argument("--repeats", type=int, default=12)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    parser.add_argument("--model", default="OpenMOSS-Team/MOSS-Transcribe-Diarize")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    audio = REPO / args.corpus / args.case / "audio.wav"
    runner = VllmRunner(base_url=args.base_url, model=args.model, timeout=600.0)

    with tempfile.TemporaryDirectory(prefix="mtd-determinism-") as scratch:
        span_wav = Path(scratch) / "span.wav"
        extract_wav(audio, args.start_sample, args.end_sample, span_wav)
        pcm_sha = hashlib.sha256(span_wav.read_bytes()).hexdigest()
        attempts = []
        for index in range(args.repeats):
            result = runner.transcribe(span_wav, max_new_tokens=args.token_cap, decoding="greedy")
            attempts.append(
                {
                    "index": index,
                    "generated_tokens": result.generated_tokens,
                    "prompt_len": result.prompt_len,
                    "text_sha256": hashlib.sha256(result.text.encode("utf-8")).hexdigest(),
                    "text_length": len(result.text),
                }
            )
            print(
                f"[{index:2d}] tokens={result.generated_tokens:4d} "
                f"chars={len(result.text):4d} sha={attempts[-1]['text_sha256'][:12]}",
                flush=True,
            )

    counts = collections.Counter(a["text_sha256"] for a in attempts)
    payload = {
        "audio": str(audio),
        "span": {"start_sample": args.start_sample, "end_sample": args.end_sample},
        "request_wav_sha256": pcm_sha,
        "repeats": args.repeats,
        "distinct_outputs": len(counts),
        "output_histogram": counts.most_common(),
        "token_counts": sorted(collections.Counter(a["generated_tokens"] for a in attempts).items()),
        "deterministic": len(counts) == 1,
        "attempts": attempts,
    }
    if args.output:
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(
        f"\ndistinct outputs over {args.repeats} identical greedy requests: {len(counts)} "
        f"-> {'DETERMINISTIC' if len(counts) == 1 else 'NOT DETERMINISTIC'}"
    )
    print(f"token counts: {payload['token_counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
