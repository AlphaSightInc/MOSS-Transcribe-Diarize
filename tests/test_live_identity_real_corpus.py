"""The external 9-clip corpus adopted by Phase N's formal identity acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "tests" / "fixtures" / "live_identity_real_corpus.json"
CORPUS = REPO_ROOT / "prototypes" / "streaming-diarization" / "data" / "real"


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
