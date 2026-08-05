#!/usr/bin/env python3

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from run_stage0_ledger_differential import (
    ENGINE_SHA256,
    FAMILY_SHA256,
    load_stage0_engine,
    ledger_unit_read_set,
    read_owning_blob,
    sha256_bytes,
)


HERE = Path(__file__).resolve().parent


class Stage0LedgerDifferentialTests(unittest.TestCase):
    def test_owning_commit_blobs_match_immutable_pins(self) -> None:
        engine = read_owning_blob("candidate_engine.py")
        family = read_owning_blob("a5-dev-candidate-family-v4.json")
        self.assertEqual(ENGINE_SHA256, sha256_bytes(engine))
        self.assertEqual(FAMILY_SHA256, sha256_bytes(family))

    def test_exact_engine_loads_without_source_edit(self) -> None:
        module, provenance = load_stage0_engine()
        self.assertTrue(callable(module.propose_ledger_only))
        self.assertEqual(ENGINE_SHA256, provenance["candidate_engine_sha256"])

    def test_ledger_helpers_do_not_read_interval_geometry(self) -> None:
        read_set = set(ledger_unit_read_set(read_owning_blob("candidate_engine.py")))
        self.assertFalse({"intervals", "span_start", "span_end"} & read_set)
        self.assertTrue({"duration_seconds", "vector", "current_speaker"} <= read_set)

    def test_decision_process_has_no_scorer_import(self) -> None:
        path = HERE / "run_stage0_ledger_differential.py"
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imports = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertFalse(any("live_speaker_accuracy" in name for name in imports))
        self.assertFalse(any("run_f1_family" in name for name in imports))


if __name__ == "__main__":
    unittest.main(verbosity=2)
