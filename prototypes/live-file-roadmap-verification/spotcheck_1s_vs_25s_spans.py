"""PROTOTYPE (throwaway) — independent spot check of the codex-only claim that
1.0 s isolated live spans catastrophically degrade WER vs 2.5 s spans.

Question: on the same 30 s of continuous real speech (lex_bill_ackman 0-30 s),
decoded as isolated spans through the exact live request shape (same model,
prompt, greedy, canonical token cap), is the 1.0 s tiling dramatically worse
than the 2.5 s tiling, in the direction and rough magnitude codex measured
(trio WER .200 -> .377)?

One command:
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
    prototypes/live-file-roadmap-verification/spotcheck_1s_vs_25s_spans.py

Independent implementation: does NOT import codex's lane_* modules.
"""
from __future__ import annotations

import json
import sys
import tempfile
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.evaluation import _tokenize, _wer  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402

AUDIO = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples/lex_bill_ackman/audio.wav"
REFERENCE = AUDIO.parent / "reference.jsonl"
SLICE_SECONDS = 30.0
RATE = 16000

runner = VllmRunner(base_url="http://127.0.0.1:18000/v1", model="OpenMOSS-Team/MOSS-Transcribe-Diarize", api_key="EMPTY", timeout=600)

with wave.open(str(AUDIO), "rb") as wav:
    assert wav.getframerate() == RATE and wav.getnchannels() == 1
    pcm = wav.readframes(int(SLICE_SECONDS * RATE))


def decode_span(start_sample: int, end_sample: int) -> tuple[str, int]:
    span = pcm[start_sample * 2 : end_sample * 2]
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        with wave.open(handle, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(RATE)
            out.writeframes(span)
        path = handle.name
    cap = canonical_decode_token_cap(sample_count=end_sample - start_sample)
    try:
        result = runner.transcribe(path, max_new_tokens=cap, decoding="greedy", temperature=None)
        text = str(result.text or "")
    except Exception as exc:  # empty/unparseable collapses mirror the live path
        text = ""
        print(f"    decode exception ({type(exc).__name__}): treated as empty")
    finally:
        Path(path).unlink(missing_ok=True)
    parsed = list(parse_transcript(text))
    words = " ".join(item.text for item in parsed)
    return words, len(parsed)


def run_arm(span_seconds: float) -> dict:
    span_samples = int(span_seconds * RATE)
    total = int(SLICE_SECONDS * RATE)
    words: list[str] = []
    empty = 0
    spans = 0
    for start in range(0, total, span_samples):
        end = min(start + span_samples, total)
        text, segments = decode_span(start, end)
        spans += 1
        if not text.strip():
            empty += 1
        else:
            words.append(text)
    return {"span_seconds": span_seconds, "spans": spans, "empty_or_unparseable": empty, "hyp_text": " ".join(words)}


reference_tokens: list[str] = []
for line in REFERENCE.read_text().splitlines():
    record = json.loads(line)
    if float(record["start"]) < SLICE_SECONDS - 1.0 and float(record["end"]) <= SLICE_SECONDS + 3.5:
        reference_tokens += _tokenize(record["text"])
print(f"reference: {len(reference_tokens)} tokens from rows within ~[0,{SLICE_SECONDS}] s")

results = {}
for arm_seconds in (2.5, 1.0):
    print(f"== arm {arm_seconds} s ==")
    arm = run_arm(arm_seconds)
    arm["wer"] = round(_wer(reference_tokens, _tokenize(arm["hyp_text"])), 4)
    results[str(arm_seconds)] = arm
    print(json.dumps({k: v for k, v in arm.items() if k != "hyp_text"}, indent=1))
    print(f"  hyp: {arm['hyp_text'][:220]}...")

ratio = results["1.0"]["wer"] / max(results["2.5"]["wer"], 1e-9)
print("\nVERDICT-INPUT:", json.dumps({
    "wer_2.5s": results["2.5"]["wer"],
    "wer_1.0s": results["1.0"]["wer"],
    "degradation_ratio": round(ratio, 2),
    "empty_2.5s": results["2.5"]["empty_or_unparseable"],
    "empty_1.0s": results["1.0"]["empty_or_unparseable"],
    "codex_trio_claim": {"2.5s": 0.1999, "1.0s": 0.3767},
}))
