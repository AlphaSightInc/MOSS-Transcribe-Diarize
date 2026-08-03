#!/usr/bin/env python3
"""A1 red-first contract for hashes, acoustic truth, runtime, and holdout seal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from validate_inputs import (
    ValidationError,
    audit_runtime_surface,
    authorize_holdout_open,
    validate_acoustic_support,
    validate_declared_hash,
)


class InputBoundaryTest(unittest.TestCase):
    def assert_code(self, code: str, action) -> None:
        with self.assertRaises(ValidationError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def test_one_byte_audio_reference_and_model_mutations_fail(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-hash-red-") as temp:
            root = Path(temp)
            for kind in ("audio", "reference", "model"):
                with self.subTest(kind=kind):
                    fixture = root / f"{kind}.fixture"
                    fixture.write_bytes(b"immutable-input")
                    expected = hashlib.sha256(fixture.read_bytes()).hexdigest()
                    fixture.write_bytes(b"jmmutable-input")
                    self.assert_code(
                        f"{kind}_hash_mismatch",
                        lambda fixture=fixture, expected=expected, kind=kind: validate_declared_hash(
                            fixture, expected, kind
                        ),
                    )

    def test_transcript_only_line_fails_acoustic_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-acoustic-red-") as temp:
            root = Path(temp)
            reference = root / "reference.jsonl"
            reference.write_text(
                json.dumps(
                    {
                        "start": 1.0,
                        "end": 2.0,
                        "speaker": "speaker-a",
                        "text": "known transcript only words",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            evidence = root / "acoustic.json"
            evidence.write_text(
                json.dumps(
                    {
                        "blind_to_reference_transcript": True,
                        "segments": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            self.assert_code(
                "reference_line_not_acoustically_supported",
                lambda: validate_acoustic_support(reference, evidence),
            )

    def test_golden_path_in_runtime_config_fails(self) -> None:
        config = {"runtime": {"input_path": "golden/reference.jsonl"}}
        self.assert_code(
            "runtime_truth_path_reachable",
            lambda: audit_runtime_surface(config, "import json\n"),
        )

    def test_reference_import_in_runtime_source_fails(self) -> None:
        self.assert_code(
            "runtime_truth_import_reachable",
            lambda: audit_runtime_surface(
                {"holdout_manifest_sha256": "a" * 64},
                "import speaker_reference\n",
            ),
        )

    def test_pre_freeze_holdout_open_fails(self) -> None:
        config = {
            "candidate_frozen": False,
            "candidate_spec_sha256": "UNFROZEN",
            "holdout_manifest_sha256": "a" * 64,
        }
        self.assert_code(
            "holdout_open_before_candidate_freeze",
            lambda: authorize_holdout_open(config, Path("sealed-holdout.json")),
        )


if __name__ == "__main__":
    unittest.main()
