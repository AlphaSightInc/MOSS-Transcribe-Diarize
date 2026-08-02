"""External real-corpus provenance plus clause 11 at the identity seam."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pytest

from live_identity_accuracy import Meeting, assert_fixture_matches_production, replay
from moss_transcribe_diarize.app.live_identity_album import (
    ALBUM_ADMISSION_SECONDS,
    ALBUM_BIRTH_MIN_SECONDS,
    ALBUM_MIN_MATCH_MARGIN,
    ALBUM_MIN_MATCH_SCORE,
)
from moss_transcribe_diarize.app.live_identity_sweep import SWEEP_INTERVAL_SECONDS


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "tests" / "fixtures" / "live_identity_real_corpus.json"
CORPUS = Path(
    os.environ.get(
        "MOSS_REAL_CORPUS_ROOT",
        REPO_ROOT / "prototypes" / "streaming-diarization" / "data" / "real",
    )
)
CLAUSE_11_FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "live_identity_real_corpus"
    / "acquired_alphabet_5m.npz"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_identity_acceptance_names_exactly_nine_hash_pinned_clips():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert len(cases) == 9
    assert len({case["name"] for case in cases}) == 9
    assert [case["tier"] for case in cases].count("1min") == 6
    assert [case["tier"] for case in cases].count("3min") == 3
    for case in cases:
        assert len(case["audio_sha256"]) == 64
        assert len(case["reference_sha256"]) == 64


def test_available_external_real_corpus_matches_the_adopted_hashes():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    first_audio = CORPUS / payload["cases"][0]["path"] / "audio.wav"
    if not first_audio.is_file():
        pytest.skip("operator-owned real identity corpus is not provisioned")

    for case in payload["cases"]:
        root = CORPUS / case["path"]
        assert _sha256(root / "audio.wav") == case["audio_sha256"]
        assert _sha256(root / "reference.jsonl") == case["reference_sha256"]


def _meeting() -> Meeting:
    with np.load(CLAUSE_11_FIXTURE) as payload:
        return Meeting(
            name="acquired_alphabet_5m",
            speaker_count=int(payload["k"]),
            truth=payload["truth"].astype(np.float64),
            rows=payload["rows"].astype(np.float64),
            vectors=payload["vecs"].astype(np.float32),
        )


def test_clause_11_real_corpus_identity_reaches_ninety_percent():
    """David's short turns must not collapse into Ben's canonical identity."""

    meeting = _meeting()
    assert_fixture_matches_production(meeting)
    result = replay(
        meeting,
        policy="album",
        min_match_score=ALBUM_MIN_MATCH_SCORE,
        min_match_margin=ALBUM_MIN_MATCH_MARGIN,
        admission_seconds=ALBUM_ADMISSION_SECONDS,
        birth_min_seconds=ALBUM_BIRTH_MIN_SECONDS,
        sweep_interval=SWEEP_INTERVAL_SECONDS,
    )

    assert result.accuracy >= 0.90, {
        "accuracy": result.accuracy,
        "David_recall": result.speaker_recalls[0],
        "Ben_recall": result.speaker_recalls[1],
        "canonicals": result.final_speaker_count,
        "corrections": result.corrections,
    }
