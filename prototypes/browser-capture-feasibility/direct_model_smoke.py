#!/usr/bin/env python3
"""PROTOTYPE: smoke a local MOSS snapshot on known multi-speaker audio.

Question: can this host load the exact local snapshot through the production
ModelRunner and emit a non-empty diarized transcript with enough speaker ids?

Run: PYTORCH_ENABLE_MPS_FALLBACK=1 python3 direct_model_smoke.py \
  --model <snapshot-directory> --audio <multi-speaker-wav>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import time
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.app.model_runner import ModelRunner


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", default="bf16")
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    parser.add_argument("--min-speakers", type=int, default=2)
    args = parser.parse_args()

    model = args.model.expanduser().resolve(strict=True)
    audio = args.audio.expanduser().resolve(strict=True)
    started = time.monotonic()
    runner = ModelRunner(model, device=args.device, dtype=args.dtype)
    result = runner.transcribe(
        audio,
        max_new_tokens=args.max_new_tokens,
        decoding="greedy",
    )
    speaker_ids = sorted(set(re.findall(r"\[(S\d+)\]", result.text)))
    verdict = bool(result.text.strip()) and len(speaker_ids) >= args.min_speakers
    runtime = runner.runtime_info()
    runtime.update(
        resolved_device=str(runner._device),
        resolved_dtype=str(runner._dtype),
    )
    payload = {
        "verdict": "pass" if verdict else "fail",
        "question": (
            "Can this host load the exact local snapshot through production ModelRunner "
            "and emit a non-empty diarized transcript with enough speaker ids?"
        ),
        "minimum_speaker_ids": args.min_speakers,
        "model": {
            "snapshot_revision": model.name,
            "file_count": len(list(model.iterdir())),
            "snapshot_bytes": sum(path.stat().st_size for path in model.iterdir() if path.is_file()),
            "weight_sha256": {
                path.name: _sha256(path) for path in sorted(model.glob("*.safetensors"))
            },
        },
        "audio": {
            "sha256": _sha256(audio),
            "bytes": audio.stat().st_size,
        },
        "host": {
            "platform": platform.platform(),
            "torch_version": torch.__version__,
            "mps_available": torch.backends.mps.is_available(),
        },
        "runtime": runtime,
        "wall_elapsed_seconds": round(time.monotonic() - started, 6),
        "distinct_speaker_ids": speaker_ids,
        "inference": result.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
