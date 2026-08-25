#!/usr/bin/env python3
"""PROTOTYPE -- throwaway. Does restoring decode context close the live-vs-file gap?

Extends `prototypes/live-latency/proto_cap_silence_sweep.py`: same production seams (the
recorded live span grid, `canonical_decode_token_cap`, `span_segments`, the real
`VllmRunner`, a decode cache keyed on audio+range+prompt), but the sweep dimension is
*decode context* rather than endpoint knobs.

Arms (see preregistration-context-arms-v1.json):

    a0      production replica -- the baseline's own span grid, each span decoded alone
    a1_5s   seam re-ASR, 5 s window centred on every internal seam
    a1_10s  seam re-ASR, 10 s window
    a2      rolling 10 s window on a 5 s stride
    a3      one whole-file decode (the upper bound; equals file mode on a 60 s clip)
    a4      prefix audio -- span decoded as [t0-1.8s, t1], prefix output trimmed
    a5      a4 plus a decaying committed-transcript tail in the prompt

One command:

    .venv/bin/python prototypes/live-file-gap-context/proto_context_arms.py \
      --baseline <frozen baseline dir> \
      --output prototypes/live-file-gap-context/results.json

Every wall-clock and RTF number is CONTENDED (three sibling agents share the GPU).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import tempfile
import time
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO))

from moss_transcribe_diarize.app.live_adapters import canonical_decode_token_cap  # noqa: E402
from moss_transcribe_diarize.app.live_span_bounds import span_segments  # noqa: E402
from moss_transcribe_diarize.app.transcription_outcome import EmptyTranscriptionError  # noqa: E402
from moss_transcribe_diarize.app.vllm_runner import VllmRunner  # noqa: E402
from moss_transcribe_diarize.evaluation import (  # noqa: E402
    Segment,
    _segment_order,
    _tokenize,
    calculate_diarization,
    calculate_tbsa,
)
from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT  # noqa: E402
from moss_transcribe_diarize.transcript_parser import parse_transcript  # noqa: E402
from moss_transcribe_diarize.app import vllm_runner as _vllm_runner  # noqa: E402


# The bench decodes through the production validator, so a span whose closing timestamp is
# malformed is discarded here exactly as the live lane discards it. The validator does not
# hand the raw text back, and the raw text is the only place the malformed-syntax signal
# lives, so it is captured on the way past. Behaviour is unchanged -- the original validator
# still decides.
_LAST_RAW: dict[str, Any] = {}
_ORIGINAL_VALIDATE = _vllm_runner._validate_transcription_response


def _capturing_validate(*, text: str, generated_tokens: int, audio_path: Any) -> None:
    _LAST_RAW["text"] = text
    _ORIGINAL_VALIDATE(text=text, generated_tokens=generated_tokens, audio_path=audio_path)


_vllm_runner._validate_transcription_response = _capturing_validate

REFUSAL_MARKERS = ("i'm sorry", "i am sorry", "can't assist", "cannot assist")


def transcript_health(raw_text: str) -> dict[str, Any]:
    """Cheap secondary signal: did the decoder close the span's syntax?"""
    stripped = (raw_text or "").strip()
    parsed = len(parse_transcript(stripped)) if stripped else 0
    closed = False
    if stripped.endswith("]"):
        tail = stripped[stripped.rfind("[") + 1:-1]
        closed = bool(tail) and all(character.isdigit() or character == "." for character in tail)
    lowered = stripped.lower()
    return {
        "raw_chars": len(stripped),
        "parsed_segments": parsed,
        "closing_timestamp": closed,
        "zero_parsed_with_output": parsed == 0 and bool(stripped),
        "malformed": bool(stripped) and (parsed == 0 or not closed),
        "refusal": any(marker in lowered for marker in REFUSAL_MARKERS),
    }

SAMPLE_RATE = 16_000
CASES = ("lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin")
CORPUS = REPO / "prototypes/streaming-diarization/data/real/benchmark_diarization_1min/samples"
PREREG = ROOT / "preregistration-context-arms-v1.json"
DEFAULT_CACHE = Path("/tmp/moss-context-arms-decode-cache-v2-20260824.json")
ARM_ORDER = ("a0", "a4", "a5", "a4_ts", "a1_5s", "a2", "a1_10s", "a3")
METRICS = ("tbsa", "wer", "content_recall", "coverage", "der", "mean_segment_seconds")

PREFIX_SECONDS = 1.8
CONTEXT_TOKEN_BUDGET = 180
CONTEXT_DECAY_SECONDS = 30.0
FILE_MODE_MAX_NEW_TOKENS = 12_000


# ---------------------------------------------------------------- io


def read_pcm(path: Path) -> bytes:
    with wave.open(str(path), "rb") as source:
        state = (
            source.getnchannels(),
            source.getsampwidth(),
            source.getframerate(),
            source.getcomptype(),
        )
        if state != (1, 2, SAMPLE_RATE, "NONE"):
            raise RuntimeError(f"audio_contract:{path}:{state}")
        return source.readframes(source.getnframes())


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)


def load_reference(case: str) -> list[Segment]:
    out = []
    for line in (CORPUS / case / "reference.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            out.append(Segment(float(item["start"]), float(item["end"]), item["speaker"], item["text"]))
    return out


def load_jsonl_segments(path: Path) -> list[Segment]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            out.append(Segment(float(item["start"]), float(item["end"]), item["speaker"], item["text"]))
    return out


def load_baseline_spans(trace_path: Path) -> list[dict[str, Any]]:
    terminal = None
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row.get("kind") == "terminal":
            terminal = row
    if terminal is None:
        raise RuntimeError(f"no terminal event in {trace_path}")
    return [
        {
            "span_id": int(item["span_id"]),
            "start_sample": int(item["start_sample"]),
            "end_sample": int(item["end_sample"]),
            "transcript": item.get("revised_transcript") or item.get("transcript") or "",
        }
        for item in terminal["snapshot"]["session"]["committed"]
    ]


# ---------------------------------------------------------------- decode


class Decoder:
    """One vLLM request per (audio range, prompt), cached on disk, concurrency 1."""

    def __init__(self, *, runner: VllmRunner, model: str, cache_path: Path):
        self.runner = runner
        self.model = model
        self.cache_path = cache_path
        if cache_path.exists():
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if payload.get("schema") != "moss-context-arms-decode-cache.v2":
                raise RuntimeError("decode_cache_schema")
            self.cache = payload
        else:
            self.cache = {"schema": "moss-context-arms-decode-cache.v2", "entries": {}}
        self.calls: list[dict[str, Any]] = []

    def _save(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(self.cache, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def decode(
        self,
        *,
        pcm: bytes,
        audio_sha: str,
        start_sample: int,
        end_sample: int,
        token_cap: int,
        prompt: str = DEFAULT_PROMPT,
        scratch: Path,
    ) -> dict[str, Any]:
        prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]
        key = f"{audio_sha}:{start_sample}:{end_sample}:{self.model}:{token_cap}:{prompt_sha}"
        cached = self.cache["entries"].get(key)
        if isinstance(cached, dict):
            self.calls.append({
                "samples": end_sample - start_sample,
                "elapsed_seconds": float(cached["elapsed_seconds"]),
                "cached": True,
            })
            return cached
        wav_path = scratch / f"{start_sample}-{end_sample}-{prompt_sha}.wav"
        write_wav(wav_path, pcm[start_sample * 2:end_sample * 2])
        started = time.monotonic()
        classification = "valid"
        error = None
        _LAST_RAW.clear()
        try:
            response = self.runner.transcribe(
                wav_path, prompt=prompt, max_new_tokens=token_cap
            )
            transcript = str(response.text)
            generated_tokens = int(response.generated_tokens)
            prompt_tokens = int(response.prompt_len)
        except EmptyTranscriptionError as exc:
            transcript = ""
            generated_tokens = 0
            prompt_tokens = 0
            error = str(exc)
            classification = "unparseable" if "zero parsed segments" in error else "empty"
        elapsed = time.monotonic() - started
        raw_text = str(_LAST_RAW.get("text") or "")
        health = transcript_health(raw_text)
        if health["refusal"]:
            # A span of near-silence can come back as the model's refusal boilerplate. Those
            # are not words anybody said; scoring them would add false insertions.
            transcript = ""
            classification = "refusal"
        result = {
            "classification": classification,
            "error": error,
            "transcript": transcript,
            "raw_text": raw_text,
            "health": health,
            "elapsed_seconds": elapsed,
            "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "token_cap": token_cap,
            "capped": generated_tokens >= token_cap,
        }
        self.cache["entries"][key] = result
        self._save()
        self.calls.append({
            "samples": end_sample - start_sample,
            "elapsed_seconds": elapsed,
            "cached": False,
        })
        return result

    def take_accounting(self) -> dict[str, Any]:
        calls, self.calls = self.calls, []
        fresh = [call for call in calls if not call["cached"]]
        return {
            "requests": len(calls),
            "fresh_requests": len(fresh),
            "decode_audio_seconds": sum(call["samples"] for call in calls) / SAMPLE_RATE,
            "wall_seconds_contended": sum(call["elapsed_seconds"] for call in calls),
            "p50_request_seconds_contended": (
                statistics.median([call["elapsed_seconds"] for call in calls]) if calls else None
            ),
            "max_request_seconds_contended": (
                max(call["elapsed_seconds"] for call in calls) if calls else None
            ),
        }


# ---------------------------------------------------------------- segments


def absolute_segments(
    transcript: str, *, start_sample: int, end_sample: int, offset_seconds: float = 0.0
) -> list[Segment]:
    """Parse a span/window transcript onto the session clock.

    `offset_seconds` shifts the decoder's local clock -- prefix-audio arms feed audio that
    begins before the span they are committing, so the span's true start sits at
    `offset_seconds` in the decoder's frame.
    """
    base = start_sample / SAMPLE_RATE
    out = []
    for parsed in span_segments(transcript, sample_count=end_sample - start_sample):
        start = base + parsed.start - offset_seconds
        end = base + parsed.end - offset_seconds
        if end > start and parsed.text.strip():
            out.append(Segment(start, end, parsed.speaker, parsed.text))
    return out


def normalise(segments: list[Segment], duration: float) -> list[Segment]:
    """Non-overlapping, in order, inside the clip. TBSA's coverage term double-counts
    overlapping hypothesis segments, so every arm is handed the same shape the live lane
    already produces: a partition."""
    out: list[Segment] = []
    for segment in sorted(segments, key=lambda item: (item.start, item.end)):
        start = max(0.0, segment.start)
        end = min(duration, segment.end)
        if out and start < out[-1].end:
            start = out[-1].end
        if end > start and segment.text.strip():
            out.append(Segment(start, end, segment.speaker, segment.text))
    return out


class SpeakerTimeline:
    """The identity stage, frozen at the baseline's decisions and shared by every arm."""

    def __init__(self, segments: list[Segment]):
        self.intervals = [(seg.start, seg.end, seg.speaker) for seg in segments]
        self.fallback = segments[0].speaker if segments else "S01"

    def label(self, start: float, end: float) -> str:
        overlap: dict[str, float] = {}
        for lo, hi, speaker in self.intervals:
            value = min(end, hi) - max(start, lo)
            if value > 0:
                overlap[speaker] = overlap.get(speaker, 0.0) + value
        if overlap:
            return max(sorted(overlap), key=lambda speaker: overlap[speaker])
        if not self.intervals:
            return self.fallback
        middle = (start + end) / 2
        return min(
            self.intervals,
            key=lambda item: min(abs(middle - item[0]), abs(middle - item[1])),
        )[2]

    def relabel(self, segments: list[Segment]) -> list[Segment]:
        return [
            Segment(seg.start, seg.end, self.label(seg.start, seg.end), seg.text)
            for seg in segments
        ]


def word_rows(segments: list[Segment], source: Any) -> list[dict[str, Any]]:
    """Every word with its own time slice inside its segment.

    Reconciliation has to happen at word granularity.  A 10 s window emits multi-second
    segments; assigning a whole segment to the 2.5 s region its midpoint lands in either
    duplicates every other word in it (the neighbouring region's window emits the same words
    again) or drops them (a narrow region swallows nothing).  Splitting each segment into
    words with char-proportional times means a region takes exactly the words spoken in it,
    from exactly one decode, so a tiling of regions reconstructs the transcript once.
    """
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(sorted(segments, key=lambda item: (item.start, item.end))):
        tokens = segment.text.split()
        if not tokens:
            continue
        total = sum(len(token) for token in tokens)
        duration = max(segment.end - segment.start, 1e-6)
        cursor = 0
        for token in tokens:
            start = segment.start + duration * cursor / total
            cursor += len(token)
            end = segment.start + duration * cursor / total
            rows.append({
                "word": token,
                "start": start,
                "end": end,
                "mid": (start + end) / 2,
                "speaker": segment.speaker,
                "src": (source, index),
            })
    return rows


def rows_to_segments(rows: list[dict[str, Any]], duration: float) -> list[Segment]:
    """Regroup words that came from the same decoded segment and still touch."""
    groups: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: (item["mid"], item["start"])):
        if groups and groups[-1]["src"] == row["src"] and row["start"] - groups[-1]["end"] <= 1e-6:
            groups[-1]["words"].append(row["word"])
            groups[-1]["end"] = max(groups[-1]["end"], row["end"])
        else:
            groups.append({
                "src": row["src"],
                "start": row["start"],
                "end": row["end"],
                "speaker": row["speaker"],
                "words": [row["word"]],
            })
    return normalise(
        [
            Segment(group["start"], group["end"], group["speaker"], " ".join(group["words"]))
            for group in groups
        ],
        duration,
    )


def _norm(row: dict[str, Any]) -> str:
    return "".join(character for character in row["word"].lower() if character.isalnum())


def trim_prefix_by_text(
    committed: list[dict[str, Any]], fresh: list[dict[str, Any]], *, prefix_start: float
) -> tuple[list[dict[str, Any]], str]:
    """Cut the re-uttered prefix off a prefix-audio decode by matching text, not clocks.

    MOSS timestamps a *segment*, not a word, so a 1.8 s cutoff can only be applied to words
    whose times were interpolated inside their segment -- and a segment that straddles the
    cutoff then loses real words or keeps duplicated ones.  Instead, align the words already
    committed for the prefix window against the head of the fresh decode and cut where that
    alignment ends: a semi-global alignment whose last DP row gives, for every j, the cost of
    explaining the whole committed tail with `fresh[:j]`.  The cheapest j is where the prefix
    stops and new speech starts.
    """
    tail = [row for row in committed if row["end"] > prefix_start]
    if not tail or not fresh:
        return fresh, "no_anchor"
    reference = [_norm(row) for row in tail]
    hypothesis = [_norm(row) for row in fresh]
    previous = list(range(len(hypothesis) + 1))
    for ref_token in reference:
        current = [previous[0] + 1]
        for index, hyp_token in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[index] + 1,
                previous[index - 1] + int(ref_token != hyp_token),
            ))
        previous = current
    cut = min(range(len(previous)), key=lambda index: (previous[index], index))
    if previous[cut] > 0.5 * len(reference):
        return fresh, "anchor_rejected"
    return fresh[cut:], f"text_anchor_cut={cut}"


def drop_join_repeat(committed: list[dict[str, Any]], fresh: list[dict[str, Any]], limit: int = 3):
    """Prefix audio makes the decoder re-utter the word the previous span already cut.

    The timestamp cutoff removes whole prefix words; a word straddling the cutoff survives
    both decodes.  Drop the longest run of up to `limit` leading fresh words that repeats the
    committed tail verbatim.
    """
    def key(row: dict[str, Any]) -> str:
        return "".join(character for character in row["word"].lower() if character.isalnum())

    for size in range(min(limit, len(committed), len(fresh)), 0, -1):
        if [key(row) for row in committed[-size:]] == [key(row) for row in fresh[:size]]:
            return fresh[size:]
    return fresh


# ---------------------------------------------------------------- arms


def seam_cells(seams: list[float], duration: float) -> list[tuple[float, tuple[float, float]]]:
    """Each seam owns the stretch of timeline closest to it; the cells tile without gaps."""
    cells = []
    for index, seam in enumerate(seams):
        left = 0.0 if index == 0 else (seams[index - 1] + seam) / 2
        right = duration if index == len(seams) - 1 else (seam + seams[index + 1]) / 2
        cells.append((seam, (left, right)))
    return cells


def context_tail(committed: list[Segment], now: float) -> str:
    """The last <= 180 tokens of already-committed text, decayed after 30 s."""
    words: list[str] = []
    for segment in sorted(committed, key=lambda item: item.start, reverse=True):
        if now - segment.end > CONTEXT_DECAY_SECONDS:
            break
        tokens = segment.text.split()
        words = tokens + words
        if len(words) >= CONTEXT_TOKEN_BUDGET:
            words = words[-CONTEXT_TOKEN_BUDGET:]
            break
    return " ".join(words).strip()


def run_arm(
    *,
    arm: str,
    pcm: bytes,
    audio_sha: str,
    spans: list[dict[str, Any]],
    duration: float,
    decoder: Decoder,
    scratch: Path,
    trim_mode: str = "text",
) -> dict[str, Any]:
    total_samples = len(pcm) // 2
    notes: list[str] = []

    def decode_range(start: int, end: int, *, prompt: str = DEFAULT_PROMPT, cap: int | None = None):
        token_cap = cap if cap is not None else canonical_decode_token_cap(sample_count=end - start)
        return decoder.decode(
            pcm=pcm,
            audio_sha=audio_sha,
            start_sample=start,
            end_sample=end,
            token_cap=token_cap,
            prompt=prompt,
            scratch=scratch,
        )

    # --- a0: the production replica, and the base every revision arm revises
    base_rows: list[dict[str, Any]] = []
    per_span: list[dict[str, Any]] = []
    if arm != "a3":
        for span in spans:
            start, end = span["start_sample"], span["end_sample"]
            if arm in {"a4", "a5"}:
                prefix_samples = min(int(PREFIX_SECONDS * SAMPLE_RATE), start)
                fed_start = start - prefix_samples
                prompt = DEFAULT_PROMPT
                if arm == "a5":
                    tail = context_tail(
                        rows_to_segments(base_rows, duration), start / SAMPLE_RATE
                    )
                    if tail:
                        prompt = f"{DEFAULT_PROMPT}\n前文：{tail}"
                decoded = decode_range(fed_start, end, prompt=prompt)
                segments = absolute_segments(
                    decoded["transcript"], start_sample=fed_start, end_sample=end
                )
                cutoff = start / SAMPLE_RATE
                produced = word_rows(segments, span["span_id"])
                if trim_mode == "timestamp":
                    rows = [row for row in produced if row["mid"] >= cutoff]
                    trim_note = f"timestamp_cut={len(produced) - len(rows)}"
                else:
                    rows, trim_note = trim_prefix_by_text(
                        base_rows, produced, prefix_start=fed_start / SAMPLE_RATE
                    )
                for row in rows[:1]:
                    row["start"] = max(row["start"], cutoff)
                rows = [row for row in rows if row["end"] > row["start"]]
                rows = drop_join_repeat(base_rows, rows)
            else:
                decoded = decode_range(start, end)
                segments = absolute_segments(
                    decoded["transcript"], start_sample=start, end_sample=end
                )
                rows = word_rows(segments, span["span_id"])
            base_rows.extend(rows)
            per_span.append({
                "span_id": span["span_id"],
                "range": [start / SAMPLE_RATE, end / SAMPLE_RATE],
                "transcript": decoded["transcript"],
                "committed_words": len(rows),
                "produced_words": len(produced) if arm in {"a4", "a5"} else len(rows),
                "trim": trim_note if arm in {"a4", "a5"} else None,
                "classification": decoded["classification"],
                "health": decoded["health"],
                "capped": decoded["capped"],
                "generated_tokens": decoded["generated_tokens"],
                "prompt_tokens": decoded["prompt_tokens"],
            })

    if arm in {"a0", "a4", "a5"}:
        if arm == "a5":
            unparseable = sum(1 for row in per_span if row["classification"] == "unparseable")
            notes.append(f"prompt_injection_unparseable_spans={unparseable}/{len(per_span)}")
        return {
            "segments": rows_to_segments(base_rows, duration),
            "spans": per_span,
            "notes": notes,
        }

    if arm == "a3":
        decoded = decode_range(0, total_samples, cap=FILE_MODE_MAX_NEW_TOKENS)
        segments = normalise(
            absolute_segments(decoded["transcript"], start_sample=0, end_sample=total_samples),
            duration,
        )
        return {
            "segments": segments,
            "spans": [{
                "span_id": 0,
                "range": [0.0, duration],
                "transcript": decoded["transcript"],
                "classification": decoded["classification"],
                "health": decoded["health"],
                "capped": decoded["capped"],
                "generated_tokens": decoded["generated_tokens"],
                "prompt_tokens": decoded["prompt_tokens"],
            }],
            "notes": ["single whole-file decode; this is what file mode does on a 60 s clip"],
        }

    windows: list[tuple[tuple[int, int], tuple[float, float]]] = []
    if arm in {"a1_5s", "a1_10s"}:
        length = 5.0 if arm == "a1_5s" else 10.0
        seams = sorted({
            span["start_sample"] / SAMPLE_RATE for span in spans if span["start_sample"] > 0
        })
        for seam, cell in seam_cells(seams, duration):
            lo = max(0.0, seam - length / 2)
            hi = min(duration, lo + length)
            lo = max(0.0, hi - length)
            windows.append((
                (int(round(lo * SAMPLE_RATE)), int(round(hi * SAMPLE_RATE))), cell
            ))
    else:  # a2 rolling
        length, stride = 10.0, 5.0
        starts = [value * stride for value in range(math.ceil(max(duration - length, 0) / stride) + 1)]
        for index, lo in enumerate(starts):
            hi = min(duration, lo + length)
            lo = max(0.0, hi - length)
            trust_lo = lo if index == 0 else lo + (length - stride) / 2
            trust_hi = hi if index == len(starts) - 1 else lo + (length + stride) / 2
            windows.append((
                (int(round(lo * SAMPLE_RATE)), int(round(hi * SAMPLE_RATE))), (trust_lo, trust_hi)
            ))

    regions = [region for _range, region in windows]
    merged = [
        row for row in base_rows
        if not any(lo <= row["mid"] < hi for lo, hi in regions)
    ]
    window_rows = []
    for index, ((start, end), region) in enumerate(windows):
        decoded = decode_range(start, end)
        replacement = word_rows(
            absolute_segments(decoded["transcript"], start_sample=start, end_sample=end),
            f"w{index}",
        )
        lo, hi = region
        taken = [row for row in replacement if lo <= row["mid"] < hi]
        merged.extend(taken)
        window_rows.append({
            "range": [start / SAMPLE_RATE, end / SAMPLE_RATE],
            "region": list(region),
            "transcript": decoded["transcript"],
            "classification": decoded["classification"],
            "health": decoded["health"],
            "capped": decoded["capped"],
            "words_taken": len(taken),
            "words_available": len(replacement),
        })
    return {
        "segments": rows_to_segments(merged, duration),
        "spans": per_span,
        "windows": window_rows,
        "notes": notes,
    }


# ---------------------------------------------------------------- scoring


def _lcs(reference: list[str], hypothesis: list[str]) -> int:
    previous = [0] * (len(hypothesis) + 1)
    for ref_token in reference:
        current = [0]
        for index, hyp_token in enumerate(hypothesis, 1):
            current.append(
                previous[index - 1] + 1
                if ref_token == hyp_token
                else max(previous[index], current[-1])
            )
        previous = current
    return previous[-1]


def score(reference: list[Segment], hypothesis: list[Segment]) -> dict[str, Any]:
    """TBSA and DER for comparability, plus the two text-only numbers the verdict ranks on.

    TBSA's speaker and coverage terms are pure time-extent overlap against gapless turn
    references -- a single [0, 60] segment of nonsense scores coverage 1.0 -- so an arm that
    merely emits wider segments inflates them without transcribing anything better.  `wer`
    and `content_recall` compare words to words and cannot be gamed that way, and
    `hypothesis_seconds` / `mean_segment_seconds` are reported so extent inflation is visible
    whenever TBSA moves.
    """
    tbsa = calculate_tbsa(reference, hypothesis)
    diarization = calculate_diarization(reference, hypothesis)
    ref_tokens = _tokenize(" ".join(seg.text for seg in sorted(reference, key=_segment_order)))
    hyp_tokens = _tokenize(" ".join(seg.text for seg in sorted(hypothesis, key=_segment_order)))
    hypothesis_seconds = sum(seg.end - seg.start for seg in hypothesis)
    return {
        "tbsa": tbsa["composite"],
        "text_speaker_accuracy": tbsa["text_speaker_accuracy"],
        "coverage": tbsa["text_coverage"],
        "wer": tbsa["wer"],
        "content_recall": _lcs(ref_tokens, hyp_tokens) / max(1, len(ref_tokens)),
        "recovered_words": _lcs(ref_tokens, hyp_tokens),
        "reference_words": len(ref_tokens),
        "hypothesis_words": len(hyp_tokens),
        "der": diarization["der"],
        "der_miss": diarization["miss"],
        "der_false_alarm": diarization["false_alarm"],
        "der_confusion": diarization["speaker_confusion"],
        "segments": len(hypothesis),
        "hypothesis_seconds": hypothesis_seconds,
        "mean_segment_seconds": hypothesis_seconds / max(1, len(hypothesis)),
    }


def decode_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """H3's malformed-span signal, per arm.

    The 5 empty spans in the live baseline were not silence: the decoder emitted words but
    closed the span's syntax wrongly, and the production validator -- which this bench decodes
    through unchanged -- discarded the whole span. If a mid-word hard cut is what breaks the
    closing timestamp, an arm that hands the decoder more context should break it less often.
    """
    health = [row["health"] for row in rows if isinstance(row.get("health"), dict)]
    total = max(1, len(health))
    return {
        "decodes": len(health),
        "malformed": sum(1 for item in health if item["malformed"]),
        "malformed_rate": sum(1 for item in health if item["malformed"]) / total,
        "zero_parsed_with_output": sum(1 for item in health if item["zero_parsed_with_output"]),
        "missing_closing_timestamp": sum(1 for item in health if not item["closing_timestamp"]),
        "refusals": sum(1 for item in health if item["refusal"]),
        "discarded_to_empty": sum(1 for row in rows if row.get("classification") != "valid"),
    }


def discover_model(base_url: str, timeout: float) -> str:
    with urlopen(base_url.rstrip("/") + "/models", timeout=timeout) as response:
        payload = json.load(response)
    models = [item.get("id") for item in payload.get("data", []) if isinstance(item, dict)]
    models = [item for item in models if isinstance(item, str) and item]
    if len(models) != 1:
        raise RuntimeError(f"expected_one_model:{models}")
    return models[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000/v1")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--arms", default=",".join(ARM_ORDER))
    cli = parser.parse_args()

    arms = [item for item in cli.arms.split(",") if item]
    unknown = [item for item in arms if item not in ARM_ORDER]
    if unknown:
        raise SystemExit(f"unknown arms: {unknown}")

    model = discover_model(cli.base_url, cli.timeout_seconds)
    runner = VllmRunner(
        base_url=cli.base_url, model=model, api_key=None, timeout=cli.timeout_seconds
    )
    decoder = Decoder(runner=runner, model=model, cache_path=cli.cache)

    document: dict[str, Any] = {
        "schema": "moss-live-file-gap-context-arms.v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "preregistration": {
            "path": str(PREREG.relative_to(REPO)),
            "sha256": hashlib.sha256(PREREG.read_bytes()).hexdigest(),
        },
        "vllm": {"base_url": cli.base_url, "model": model},
        "contention_warning": "three sibling agents share this GPU; every wall/RTF number here is contended",
        "cases": {},
    }

    for case in CASES:
        audio_path = CORPUS / case / "audio.wav"
        pcm = read_pcm(audio_path)
        audio_sha = hashlib.sha256(audio_path.read_bytes()).hexdigest()
        duration = (len(pcm) // 2) / SAMPLE_RATE
        reference = load_reference(case)
        spans = load_baseline_spans(cli.baseline / case / "live" / "run-001" / "trace.jsonl")
        baseline_live = load_jsonl_segments(cli.baseline / case / "live-hypothesis.jsonl")
        baseline_file = load_jsonl_segments(cli.baseline / case / "file-hypothesis.jsonl")
        timeline = SpeakerTimeline(baseline_live)

        entry: dict[str, Any] = {
            "duration_seconds": duration,
            "span_count": len(spans),
            "baseline": {
                "live": score(reference, baseline_live),
                "file": score(reference, baseline_file),
            },
            "arms": {},
        }
        with tempfile.TemporaryDirectory(prefix="moss-context-arms-") as temporary:
            scratch = Path(temporary)
            for arm in arms:
                print(f"MEASURE {case} {arm}", flush=True)
                decoder.take_accounting()
                produced = run_arm(
                    arm="a4" if arm == "a4_ts" else arm,
                    trim_mode="timestamp" if arm == "a4_ts" else "text",
                    pcm=pcm,
                    audio_sha=audio_sha,
                    spans=spans,
                    duration=duration,
                    decoder=decoder,
                    scratch=scratch,
                )
                accounting = decoder.take_accounting()
                shared = timeline.relabel(produced["segments"])
                row = {
                    "scores": score(reference, shared),
                    "scores_raw_decoder_labels": score(reference, produced["segments"]),
                    "cost": accounting,
                    "notes": produced.get("notes", []),
                    "decode_health": decode_health(
                        produced.get("spans", []) + produced.get("windows", [])
                    ),
                    "capped_decodes": sum(
                        1 for item in produced.get("spans", []) if item["capped"]
                    ),
                    "hypothesis": [
                        {"start": s.start, "end": s.end, "speaker": s.speaker, "text": s.text}
                        for s in shared
                    ],
                    "spans": produced.get("spans", []),
                    "windows": produced.get("windows", []),
                }
                entry["arms"][arm] = row
                document["cases"][case] = entry
                cli.output.parent.mkdir(parents=True, exist_ok=True)
                cli.output.write_text(
                    json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                print(
                    f"  wer={row['scores']['wer']:.4f} recall={row['scores']['content_recall']:.4f} "
                    f"tbsa={row['scores']['tbsa']:.4f} cov={row['scores']['coverage']:.4f} "
                    f"der={row['scores']['der']:.4f} segs={row['scores']['segments']} "
                    f"meanseg={row['scores']['mean_segment_seconds']:.2f}s "
                    f"audio_s={accounting['decode_audio_seconds']:.0f} "
                    f"fresh={accounting['fresh_requests']}",
                    flush=True,
                )
        document["cases"][case] = entry

    document["summary"] = summarise(document, arms)
    cli.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(document["summary"], indent=2, sort_keys=True))
    return 0


def summarise(document: dict[str, Any], arms: list[str]) -> dict[str, Any]:
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    gates = prereg["gates"]["primary_trio_means"]
    cases = [case for case in CASES if case in document["cases"]]
    audio_seconds = sum(document["cases"][case]["duration_seconds"] for case in cases)

    def mean(arm: str, metric: str) -> float:
        return statistics.fmean(
            document["cases"][case]["arms"][arm]["scores"][metric] for case in cases
        )

    out: dict[str, Any] = {
        "cases": cases,
        "metric_validity_note": (
            "WER and content_recall are the primary, text-only numbers. TBSA's speaker and "
            "coverage terms and DER are time-extent quantities against gapless turn references, "
            "so an arm that emits wider segments raises them without transcribing better; "
            "mean_segment_seconds is reported alongside so that is visible."
        ),
        "baseline_means": {
            role: {
                metric: statistics.fmean(
                    document["cases"][case]["baseline"][role][metric] for case in cases
                )
                for metric in METRICS
            }
            for role in ("live", "file")
        },
        "arms": {},
    }
    a0_audio = None
    for arm in arms:
        if not all(arm in document["cases"][case]["arms"] for case in cases):
            continue
        arm_audio = sum(
            document["cases"][case]["arms"][arm]["cost"]["decode_audio_seconds"] for case in cases
        )
        if arm == "a0":
            a0_audio = arm_audio
        means = {metric: mean(arm, metric) for metric in METRICS}
        regressions = {
            case: document["cases"][case]["baseline"]["live"]["tbsa"]
            - document["cases"][case]["arms"][arm]["scores"]["tbsa"]
            for case in cases
        }
        checks = {
            "wer_primary": means["wer"] <= gates["wer_max"],
            "tbsa": means["tbsa"] >= gates["tbsa_min"],
            "coverage": means["coverage"] >= gates["coverage_min"],
            "der": means["der"] <= gates["der_max"],
            "no_case_regression": max(regressions.values()) <= prereg["gates"]["per_case"][
                "max_tbsa_regression_vs_live_baseline"
            ],
        }
        out["arms"][arm] = {
            "means": means,
            "per_case": {
                case: document["cases"][case]["arms"][arm]["scores"] for case in cases
            },
            "tbsa_regression_vs_live_baseline": regressions,
            "gate_checks": checks,
            "passes": all(checks.values()),
            "decode_audio_seconds": arm_audio,
            "added_decode_audio_seconds_per_audio_second": (
                None if a0_audio is None else (arm_audio - a0_audio) / audio_seconds
            ),
            "wall_seconds_contended": sum(
                document["cases"][case]["arms"][arm]["cost"]["wall_seconds_contended"]
                for case in cases
            ),
            "requests": sum(
                document["cases"][case]["arms"][arm]["cost"]["requests"] for case in cases
            ),
            "decode_health": {
                field: sum(
                    document["cases"][case]["arms"][arm]["decode_health"][field]
                    for case in cases
                )
                for field in (
                    "decodes",
                    "malformed",
                    "zero_parsed_with_output",
                    "missing_closing_timestamp",
                    "refusals",
                    "discarded_to_empty",
                )
            },
        }
    if "a0" in out["arms"]:
        delta = abs(out["arms"]["a0"]["means"]["tbsa"] - out["baseline_means"]["live"]["tbsa"])
        wer_delta = abs(out["arms"]["a0"]["means"]["wer"] - out["baseline_means"]["live"]["wer"])
        out["bench_validation"] = {
            "a0_tbsa_delta_vs_baseline_live": delta,
            "a0_wer_delta_vs_baseline_live": wer_delta,
            "valid": delta <= 0.01 and wer_delta <= 0.01,
        }
    out["ranking_by_text_only_metrics"] = sorted(
        out["arms"],
        key=lambda arm: (
            out["arms"][arm]["means"]["wer"],
            -out["arms"][arm]["means"]["content_recall"],
        ),
    )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
