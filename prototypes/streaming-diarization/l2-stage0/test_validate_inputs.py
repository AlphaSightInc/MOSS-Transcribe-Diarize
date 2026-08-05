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
    select_case_scope,
    validate_acoustic_support,
    validate_declared_findings,
    validate_declared_hash,
    validate_human_audit_metadata,
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

    def test_non_holdout_validation_scope_skips_sealed_case_paths(self) -> None:
        cases = [
            {"case_id": "dev", "split": "development"},
            {
                "case_id": "sealed",
                "split": "blind_holdout",
                "reference_path": "must-not-open.jsonl",
            },
        ]
        selected, skipped = select_case_scope(cases, "non-holdout")
        self.assertEqual([case["case_id"] for case in selected], ["dev"])
        self.assertEqual(skipped, ["sealed"])

    def test_adjudicated_findings_preserve_scanner_history(self) -> None:
        actual = [{"index": 9, "kind": "overlap", "previous_end": 47.792, "start": 47.0}]
        declared = [{**actual[0], "adjudicated": True}]
        validate_declared_findings("audited", actual, declared)

    def test_human_audit_requires_every_finding_adjudicated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-human-audit-red-") as temp:
            attestation = Path(temp) / "attestation.md"
            attestation.write_text("operator attestation\n", encoding="utf-8")
            case = {
                "case_id": "audited",
                "human_audit": {
                    "attestation_path": str(attestation),
                    "basis": "operator direct listening",
                    "date": "2026-08-04",
                },
                "split": "acceptance_pool",
                "validation_state": "human_audited",
            }
            self.assert_code(
                "human_audit_finding_unadjudicated",
                lambda: validate_human_audit_metadata(
                    case,
                    reference_path=Path(temp) / "reference.jsonl",
                    findings=[{"index": 1, "kind": "high_word_rate"}],
                ),
            )

    def test_human_audit_cannot_preassign_campaign_split(self) -> None:
        with tempfile.TemporaryDirectory(prefix="moss-l2-human-audit-split-red-") as temp:
            attestation = Path(temp) / "attestation.md"
            attestation.write_text("operator attestation\n", encoding="utf-8")
            case = {
                "case_id": "audited",
                "human_audit": {
                    "attestation_path": str(attestation),
                    "basis": "operator direct listening",
                    "date": "2026-08-04",
                },
                "split": "development",
                "validation_state": "human_audited",
            }
            self.assert_code(
                "human_audit_split_not_acceptance_pool",
                lambda: validate_human_audit_metadata(
                    case,
                    reference_path=Path(temp) / "reference.jsonl",
                    findings=[],
                ),
            )


if __name__ == "__main__":
    unittest.main()
