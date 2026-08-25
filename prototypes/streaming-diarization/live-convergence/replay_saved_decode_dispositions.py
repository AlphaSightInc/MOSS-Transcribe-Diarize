#!/usr/bin/env python3
"""What the seven saved real decodes report, before and after the M0b disposition fix.

Question: for the spans the deployed service actually lost -- non-empty MOSS answers that
parsed to zero segments -- does the trace now say what the decoder did?

One command, full state printed:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
      prototypes/streaming-diarization/live-convergence/replay_saved_decode_dispositions.py \
      --output evidence/live-convergence-0824/M0b-decode-disposition/dispositions.json

The corpus is `prototypes/live-file-gap-emptyspan/out/d3.json` -- raw decodes captured from
the 2026-08-24 paired baseline runs, with their real generated-token counts. Each one is
pushed through the production seam with only the socket replaced: `VllmRunner.transcribe`
(so the real `_validate_transcription_response` decides), `RunnerBoundedWavInference` (the
live adapter that used to flatten every ending into `transcript=""`), and the coordinator's
own naming of what it received.

The "before" column is not a memory of an old run: it is what the coordinator answers when
it is given exactly what the adapter used to hand it -- an empty transcript and nothing else.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from moss_transcribe_diarize.app.live_adapters import (  # noqa: E402
    InferenceTranscript,
    RunnerBoundedWavInference,
)
from moss_transcribe_diarize.app.live_coordinator import _decode_empty_reason  # noqa: E402
from moss_transcribe_diarize.app.live_session import FrozenSpan  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402

SAVED_DECODES = REPO_ROOT / "prototypes/live-file-gap-emptyspan/out/d3.json"
LIVE_SAMPLE_RATE = 16000
DEPLOYED_HARD_CAP_SAMPLES = 40000


class SavedAnswerRunner(VllmRunner):
    """The product runner answering with one decode the deployed service really returned."""

    def __init__(self, response: dict):
        super().__init__(base_url="http://vllm.saved.test:8000", model="moss-saved")
        self._response = response

    def _post_multipart(self, url, **kwargs):
        del url, kwargs
        return self._response


def _span(sample_count: int) -> FrozenSpan:
    return FrozenSpan(id=1, epoch=0, start_sample=0, end_sample=sample_count, reason="hard_cap")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()

    saved = json.loads(SAVED_DECODES.read_text())["raw"]
    rows = []
    for entry in saved:
        window = entry["window"]
        sample_count = min(
            DEPLOYED_HARD_CAP_SAMPLES,
            max(1, round((window[1] - window[0]) * LIVE_SAMPLE_RATE)),
        )
        response = {
            "text": entry["raw_text"],
            "usage": {
                "prompt_tokens": entry["prompt_tokens"],
                "completion_tokens": entry["generated_tokens"],
            },
        }
        decoder = RunnerBoundedWavInference(
            SavedAnswerRunner(response), max_samples=DEPLOYED_HARD_CAP_SAMPLES
        )
        inferred = decoder.transcribe_pcm(
            span=_span(sample_count), pcm=b"\x00\x00" * sample_count
        )
        # What the adapter used to hand the coordinator for every one of these: nothing.
        flattened = InferenceTranscript(transcript="", generated_tokens=0)
        rows.append(
            {
                "case": entry["case"],
                "span_id": entry["span_id"],
                "window": window,
                "raw_text": entry["raw_text"],
                "parsed_segments": entry["parsed_segments"],
                "generated_tokens_saved": entry["generated_tokens"],
                "before_reason": _decode_empty_reason(flattened),
                "before_generated_tokens": flattened.generated_tokens,
                "after_cause": None if inferred.empty_cause is None else inferred.empty_cause.value,
                "after_reason": _decode_empty_reason(inferred),
                "after_generated_tokens": inferred.generated_tokens,
                "published_transcript": inferred.transcript,
            }
        )

    summary = {
        "corpus": str(SAVED_DECODES.relative_to(REPO_ROOT)),
        "decodes": len(rows),
        "before_reasons": _tally(rows, "before_reason"),
        "after_reasons": _tally(rows, "after_reason"),
        "after_causes": _tally(rows, "after_cause"),
        "generated_tokens_preserved": all(
            row["after_generated_tokens"] == row["generated_tokens_saved"] for row in rows
        ),
        "published_text_unchanged": all(row["published_transcript"] == "" for row in rows),
        "rows": rows,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return 0


def _tally(rows: list[dict], key: str) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[str(row[key])] = counts.get(str(row[key]), 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    raise SystemExit(main())
