"""Make one bounded production-runner request for the R4-6 system window."""
from __future__ import annotations

import argparse
import json
import tempfile
import time
import wave
from pathlib import Path

from moss_transcribe_diarize.app.vllm_runner import VllmRunner
from moss_transcribe_diarize.transcript_parser import parse_transcript


def _crop(source: Path, destination: Path, seconds: float) -> int:
    with wave.open(str(source), "rb") as reader:
        if (reader.getframerate(), reader.getnchannels(), reader.getsampwidth()) != (16000, 1, 2):
            raise RuntimeError("expected 16 kHz mono PCM16")
        frames = reader.readframes(round(seconds * reader.getframerate()))
    with wave.open(str(destination), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(16000)
        writer.writeframes(frames)
    return len(frames) // 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--seconds", type=float, default=29.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.receipt.exists():
        raise RuntimeError("refuse to overwrite retained evidence")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="moss-r4-6-") as temporary:
        crop = Path(temporary) / "system-0-29.wav"
        samples = _crop(args.source, crop, args.seconds)
        request = {
            "request": 1,
            "case": "R4-6-system-0-29",
            "samples": samples,
            "sample_rate": 16000,
            "model": args.model,
            "base_url": args.base_url,
            "decoding": "greedy",
            "temperature": None,
            "retry": 0,
            "in_flight": 1,
            "started_epoch": time.time(),
        }
        try:
            result = VllmRunner(
                base_url=args.base_url,
                model=args.model,
                timeout=600.0,
            ).transcribe(crop)
        except Exception as exc:
            request.update(status="failed", error_type=type(exc).__name__, ended_epoch=time.time())
            args.receipt.write_text(json.dumps(request) + "\n")
            raise
        request.update(
            status="completed",
            ended_epoch=time.time(),
            elapsed_seconds=result.elapsed_sec,
            generated_tokens=result.generated_tokens,
            peak_in_flight=1,
        )
        args.receipt.write_text(json.dumps(request) + "\n")
        parsed = parse_transcript(result.text)
        payload = {
            "schema": "moss-r4-6-raw-window.v1",
            "request": request,
            "raw_text": result.text,
            "parsed_segments": [
                {
                    "speaker": segment.speaker,
                    "start": segment.start,
                    "end": segment.end,
                    "text": segment.text,
                }
                for segment in parsed
            ],
        }
        args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"requests": 1, "peak_in_flight": 1, "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
