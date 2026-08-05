#!/usr/bin/env python3
"""Public-interface checks for the L1.5 opening-once guard."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from holdout_gate import GateError, assert_case_access, open_holdout_session


HERE = Path(__file__).resolve().parent


class HoldoutGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.split = json.loads((HERE / "split-manifest.json").read_text(encoding="utf-8"))
        cls.procedure = json.loads((HERE / "holdout-procedure.json").read_text(encoding="utf-8"))

    def test_development_case_is_available_before_freeze(self) -> None:
        result = assert_case_access(
            "1m-acquired-nfl", self.split, self.procedure, repo=HERE.parents[2]
        )
        self.assertEqual(result, "development")

    def test_holdout_case_refuses_before_candidate_freeze(self) -> None:
        with self.assertRaisesRegex(GateError, "l15_holdout_before_candidate_freeze"):
            assert_case_access(
                "5m-acquired-coca-cola", self.split, self.procedure, repo=HERE.parents[2]
            )

    def test_opening_is_exactly_once_after_valid_freeze(self) -> None:
        with tempfile.TemporaryDirectory(prefix="l15-holdout-gate-") as temp:
            root = Path(temp)
            split_path = root / "split.json"
            procedure_path = root / "procedure.json"
            freeze_path = root / "candidate.json"
            marker_path = root / "opening.json"
            split_path.write_text(json.dumps(self.split, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            fixture_procedure = dict(self.procedure)
            fixture_procedure.update(
                {
                    "candidate_freeze_path": "candidate.json",
                    "opening_marker_path": "opening.json",
                    "split_manifest_path": "split.json",
                }
            )
            procedure_path.write_text(
                json.dumps(fixture_procedure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            freeze_path.write_text(
                json.dumps(
                    {
                        "candidate_frozen": True,
                        "corpus_manifest_sha256": fixture_procedure["corpus_manifest_sha256"],
                        "schema": "moss-l15-candidate-freeze.v1",
                        "split_manifest_sha256": fixture_procedure["split_manifest_sha256"],
                    },
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            opened = open_holdout_session(
                procedure_path, repo=root, authorization="SUPERVISOR_GO"
            )
            self.assertEqual(opened, marker_path)
            with self.assertRaisesRegex(GateError, "l15_holdout_already_opened"):
                open_holdout_session(
                    procedure_path, repo=root, authorization="SUPERVISOR_GO"
                )

    def test_split_hash_drift_refuses(self) -> None:
        bad = dict(self.procedure)
        bad["split_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(GateError, "l15_split_hash_mismatch"):
            assert_case_access("1m-acquired-nfl", self.split, bad, repo=HERE.parents[2])


if __name__ == "__main__":
    unittest.main(verbosity=2)
