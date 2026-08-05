#!/usr/bin/env python3
"""Contract checks for the calibrated L1.5 baseline wrapper."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from run_l1_baseline import BaselineError, load_a2_instrument, percentile_type7, select_cases


HERE = Path(__file__).resolve().parent


class BaselineContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.spec = json.loads((HERE / "l1-baseline-spec.json").read_text(encoding="utf-8"))
        cls.split = json.loads((HERE / "split-manifest.json").read_text(encoding="utf-8"))

    def test_a2_instrument_is_hash_pinned_and_production_bound(self) -> None:
        instrument = load_a2_instrument(self.spec)
        bindings = instrument.production_bindings()
        self.assertEqual(
            bindings["sweep"],
            "moss_transcribe_diarize.app.live_identity_sweep.sweep",
        )

    def test_holdout_is_refused_before_baseline_selection(self) -> None:
        with self.assertRaisesRegex(BaselineError, "l15_l1_holdout_sealed"):
            select_cases(self.split, ["5m-acquired-coca-cola"])

    def test_exact_dev_validation_scope_is_selected(self) -> None:
        selected = select_cases(self.split, self.spec["case_ids"])
        self.assertEqual(len(selected), 16)
        self.assertNotIn("blind_holdout", {case["split"] for case in selected})

    def test_type7_percentile_is_predeclared_and_deterministic(self) -> None:
        self.assertEqual(percentile_type7([1.0, 2.0, 3.0, 4.0], 75), 3.25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
