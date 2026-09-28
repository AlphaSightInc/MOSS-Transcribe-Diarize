"""Score offline three-surface segments with the H1 production quality path.

Add this directory to sys.path, then import score_case and macro. Each segment is
{start, end, speaker, text} in seconds. None and "S00" are unattributed.
"""

from __future__ import annotations

from functools import lru_cache
import json
import math
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any
import wave

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE
from moss_transcribe_diarize.phase2_acceptance import QUALITY_BOUNDS
from moss_transcribe_diarize.phase2_acceptance_external import (
    _load_surface_harness, _mean, _quality_speaker_intervals,
)

from run_quality import CORPUS, verified_corpus


@lru_cache(maxsize=1)
def _inputs():
    manifest = json.loads((CORPUS / "corpus-manifest.json").read_text(encoding="utf-8"))
    scratch = TemporaryDirectory(prefix="moss-h1-offline-")
    try:
        corpus, _ = verified_corpus(CORPUS, Path(scratch.name), manifest["cases"])
    except BaseException:
        scratch.cleanup()
        raise
    return corpus, {item["case_id"]: item for item in manifest["cases"]}, scratch


@lru_cache(maxsize=1)
def _surface():
    return _load_surface_harness(ROOT)


def _case_inputs(case_id: str):
    corpus, manifest, _scratch = _inputs()
    if case_id in manifest:
        item = manifest[case_id]
        return corpus / case_id, item["audio"]["duration_seconds"], item["category"]
    roots = {
        "benchmark": ("benchmark_diarization_1min/samples", "gold9"),
        "calibration": ("calibration_diarization_3min/samples", "gold9"),
        "benchmark_5m": ("benchmark_5m", "bench5m"),
        "benchmark_30m": ("benchmark_30m", "long30m"),
    }
    prefix, separator, name = case_id.partition(":")
    if case_id == "rtfl90":
        directory = ROOT / "prototypes/streaming-diarization/data/real/regression_fixtures/youtube_rtfl_first_90s"
        category = "rtfl"
    elif separator and prefix in roots and name and "/" not in name and name != "..":
        subdir, category = roots[prefix]
        if prefix == "benchmark_5m" and name not in {
            "lex_bill_ackman", "lex_javier_milei", "lex_keyu_jin"
        }:
            category = "bench5m sparse diagnostic"
        if prefix == "benchmark_30m" and name != "lex_bill_ackman":
            category = "long30m sparse diagnostic"
        directory = ROOT / "prototypes/streaming-diarization/data/real" / subdir / name
    else:
        raise ValueError(f"unknown timed reference case: {case_id}")
    if not (directory / "audio.wav").is_file() or not (directory / "reference.jsonl").is_file():
        raise ValueError(f"missing audio or timed reference: {case_id}")
    with wave.open(str(directory / "audio.wav")) as audio:
        duration = audio.getnframes() / audio.getframerate()
    return directory, duration, category


def _snapshot(segments: list[dict[str, Any]], speakers: list[str]) -> dict[str, Any]:
    album = {speaker: f"speaker-{index:04d}" for index, speaker in enumerate(speakers, 1)}
    effective = []
    for segment in segments:
        start, end = float(segment["start"]), float(segment["end"])
        if not (math.isfinite(start) and math.isfinite(end) and end > start):
            raise ValueError("segment must have finite start < end")
        speaker = segment["speaker"]
        if speaker is not None and not isinstance(speaker, str):
            raise TypeError("segment speaker must be a string or None")
        text = segment["text"]
        if not isinstance(text, str):
            raise TypeError("segment text must be a string")
        effective.append({
            "start_sample": round(start * LIVE_SAMPLE_RATE),
            "end_sample": round(end * LIVE_SAMPLE_RATE),
            "canonical_speaker": None if speaker is None or speaker == "S00" else album[speaker],
            "text": text,
        })
    return {"session": {
        "identity_snapshot": {"canonical_speakers": list(album.values())},
        "effective_transcript": effective,
    }}


def score_case(
    case_id: str, *, immediate: list[dict[str, Any]], settled: list[dict[str, Any]],
    final: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return H1 per-case fields; live-only fields are None (unmeasured)."""
    directory, duration, category = _case_inputs(case_id)
    surfaces = {"immediate": immediate, "settled": settled, "final": final}
    speakers = list(dict.fromkeys(
        segment["speaker"] for segments in surfaces.values() for segment in segments
        if segment["speaker"] is not None and segment["speaker"] != "S00"
    ))
    surface = _surface()
    case = surface.Case(case_id, directory, directory / "reference.jsonl")
    scored = {}
    settled_rows = settled_snapshot = None
    for name, segments in surfaces.items():
        snapshot = _snapshot(segments, speakers)
        rows = surface.transcript_rows(snapshot, duration)
        scored[name] = surface.score_surface(case, rows)
        if name == "settled":
            settled_rows, settled_snapshot = rows, snapshot
    intervals = _quality_speaker_intervals(
        settled_snapshot, settled_rows, case.reference,
        speech_regions=surface.speech_regions_from_wav(case.audio),
    )
    diagnostic = intervals["settled_der_s00_diagnostic"]
    if (diagnostic["as_is"] != scored["settled"]["der"] or
            diagnostic["reference_speech_as_is"] != scored["settled"]["reference_speech_der"]):
        raise RuntimeError("H1 settled interval and surface scores disagree")
    scored["settled"]["der_raw"] = scored["settled"]["der"]
    scored["settled"]["reference_speech_der_raw"] = scored["settled"]["reference_speech_der"]
    scored["settled"]["der"] = diagnostic["without_s00_confusion"]
    scored["settled"]["reference_speech_der"] = diagnostic["reference_speech_without_s00_confusion"]
    return {
        "case_id": case_id,
        "pass": None,
        "session_id": None,
        "category": category,
        "duration_seconds": duration,
        "windows": None,
        "window_coverage": None,
        "metrics": scored,
        **intervals,
        "surface_observations": None,
    }


def macro(results: list[dict[str, Any]]) -> dict[str, float]:
    """H1's eight QUALITY_BOUNDS macro means; each result counts once."""
    fields = {
        "immediate_wer": ("immediate", "wer"),
        "settled_wer": ("settled", "wer"),
        "recall": ("settled", "content_recall"),
        "time_speaker_attribution": ("settled", "tbsa"),
        "diarization_error_rate": ("settled", "der"),
        "matched_speaker_accuracy": ("settled", "matched_word_speaker_accuracy"),
        "reference_speech_der": ("settled", "reference_speech_der"),
        "final_wer": ("final", "wer"),
    }
    if fields.keys() != QUALITY_BOUNDS.keys():
        raise RuntimeError("H1 quality bound names changed")
    return {name: _mean(results, *surface_field) for name, surface_field in fields.items()}
