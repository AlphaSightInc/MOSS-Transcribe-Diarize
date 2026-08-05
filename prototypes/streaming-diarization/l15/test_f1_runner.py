#!/usr/bin/env python3

from __future__ import annotations

import unittest

from run_f1_family import config_grid, select_config


class F1RunnerTests(unittest.TestCase):
    def test_grid_is_exactly_preregistered_27(self) -> None:
        configs = config_grid()
        self.assertEqual(27, len(configs))
        self.assertEqual(27, len({item["config_id"] for item in configs}))

    def test_tie_break_prefers_budget_then_score_then_margin(self) -> None:
        candidates = [
            {
                "config_id": "loose",
                "aggregate_speaker_accuracy": 0.9,
                "non_gain_gates_passed": True,
                "config": {
                    "max_changed_duration_fraction": 0.05,
                    "canonical_min_score": 0.3,
                    "canonical_min_margin": 0.05,
                },
            },
            {
                "config_id": "strict",
                "aggregate_speaker_accuracy": 0.9,
                "non_gain_gates_passed": True,
                "config": {
                    "max_changed_duration_fraction": 0.02,
                    "canonical_min_score": 0.4,
                    "canonical_min_margin": 0.15,
                },
            },
        ]
        self.assertEqual("strict", select_config(candidates)["config_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
