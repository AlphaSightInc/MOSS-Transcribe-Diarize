#!/usr/bin/env python3

from __future__ import annotations

import unittest

from f1_candidate import F1Config, audit_f1_chain, decide_f1, semantic_hash
from runtime_l1 import load_runtime_case, run_runtime_l1


class F1PreconditionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runtime = load_runtime_case("1m-acquired-nfl")
        cls.l1 = run_runtime_l1(cls.runtime)

    def test_full_chain_has_no_golden_access(self) -> None:
        audit = audit_f1_chain()
        self.assertTrue(audit["passed"], audit)

    def test_label_perturbation_cannot_change_runtime_shape_or_decision(self) -> None:
        config = F1Config(0.35, 0.10, 0.05)
        truth_ab = [(0.0, 1.0, "A"), (1.0, 2.0, "B")]
        truth_aa = [(0.0, 1.0, "A"), (1.0, 2.0, "A")]
        first = decide_f1(self.runtime, self.l1, config)
        second = decide_f1(self.runtime, self.l1, config)
        self.assertNotEqual(truth_ab, truth_aa)
        self.assertEqual(
            self.runtime["runtime_shape_sha256"], self.runtime["runtime_shape_sha256"]
        )
        self.assertEqual(semantic_hash(first), semantic_hash(second))

    def test_runtime_l1_calls_calibrated_production_bindings(self) -> None:
        self.assertEqual(
            "moss_transcribe_diarize.app.live_identity_sweep.sweep",
            self.l1["production_bindings"]["sweep"],
        )
        self.assertEqual(len(self.runtime["units"]), len(self.l1["final_unit_labels"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
