#!/usr/bin/env python3
"""Behavior checks for the operator-authorized A4 completion decision."""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODULE = HERE / "complete_a4.py"


def load_module():
    spec = importlib.util.spec_from_file_location("complete_a4", MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("complete_a4_import_spec_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompleteA4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.optimized = json.loads(
            (HERE / "evidence/a4/optimized/a4-runtime-optimized.json").read_text()
        )

    def test_revised_six_gate_contract_passes(self) -> None:
        result = self.module.evaluate_revised_gates(self.optimized)
        self.assertEqual(6, len(result["gates"]))
        self.assertTrue(all(gate["pass"] for gate in result["gates"]))
        self.assertLessEqual(result["first_finalizer_allowance"]["overhead_seconds"], 5.0)

    def test_steady_state_rtf_and_wall_are_hard_gates(self) -> None:
        mutated = copy.deepcopy(self.optimized)
        run = mutated["measurements"][-1]["runs"][1]
        run["rtf"] = 0.1000001
        run["wall_seconds"] = 180.0001
        result = self.module.evaluate_revised_gates(mutated)
        self.assertFalse(result["gates"][0]["pass"])
        self.assertFalse(result["gates"][1]["pass"])

    def test_first_finalizer_allowance_is_hard_gate(self) -> None:
        mutated = copy.deepcopy(self.optimized)
        mutated["measurements"][-1]["runs"][0]["wall_seconds"] = (
            mutated["measurements"][-1]["runs"][1]["wall_seconds"] + 5.000001
        )
        result = self.module.evaluate_revised_gates(mutated)
        self.assertFalse(result["first_finalizer_allowance"]["pass"])
        self.assertFalse(result["gates"][0]["pass"])
        self.assertFalse(result["gates"][1]["pass"])

    def test_operator_decision_is_option_a_and_d_deferred(self) -> None:
        decision = self.module.OPERATOR_DECISION
        self.assertEqual("A", decision["adopted_option"])
        self.assertEqual("post-MVP", decision["option_d_server_gpu_embedding"])
        self.assertEqual("2026-08-03", decision["authorized_date"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
