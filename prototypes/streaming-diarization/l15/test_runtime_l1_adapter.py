#!/usr/bin/env python3

from __future__ import annotations

import unittest

from runtime_l1 import load_runtime_case, run_runtime_l1


DECISION_KEYS = (
    "final_unit_labels",
    "live_unit_labels",
    "counts",
    "revision_trace",
    "span_trace",
    "changed_duration_fraction",
    "changed_speaker_seconds",
    "production_bindings",
    "production_config",
    "production_planner",
)


class RuntimeL1AdapterTests(unittest.TestCase):
    def test_terminal_synthetic_scorer_is_decision_independent(self) -> None:
        runtime = load_runtime_case("1m-acquired-nfl")
        unsuppressed = run_runtime_l1(runtime, suppress_terminal_synthetic_metrics=False)
        suppressed = run_runtime_l1(runtime, suppress_terminal_synthetic_metrics=True)
        self.assertFalse(unsuppressed["terminal_synthetic_metrics_suppressed"])
        self.assertTrue(suppressed["terminal_synthetic_metrics_suppressed"])
        self.assertEqual(
            {key: unsuppressed[key] for key in DECISION_KEYS},
            {key: suppressed[key] for key in DECISION_KEYS},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
