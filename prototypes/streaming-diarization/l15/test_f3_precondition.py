#!/usr/bin/env python3

from __future__ import annotations

import unittest

from f3_candidate import F3Schedule, audit_f3_chain, semantic_hash


class F3PreconditionTests(unittest.TestCase):
    def test_schedule_boundaries_are_end_exclusive(self) -> None:
        schedule = F3Schedule(
            "staged",
            ((300.0, 0.1), (900.0, 0.15), (None, 0.2)),
        )
        self.assertEqual(0.1, schedule.margin_at(299.999))
        self.assertEqual(0.15, schedule.margin_at(300.0))
        self.assertEqual(0.15, schedule.margin_at(899.999))
        self.assertEqual(0.2, schedule.margin_at(900.0))

    def test_short_meeting_remains_at_deployed_margin(self) -> None:
        schedule = F3Schedule("step", ((300.0, 0.1), (None, 0.2)))
        self.assertEqual({0.1}, {schedule.margin_at(value) for value in (0.0, 60.0, 299.999)})

    def test_semantic_hash_is_deterministic(self) -> None:
        payload = {"schedule": "step", "trace": [0.1, 0.2]}
        self.assertEqual(semantic_hash(payload), semantic_hash(payload))

    def test_full_chain_calls_production_preparer_without_policy_copy(self) -> None:
        audit = audit_f3_chain()
        self.assertTrue(audit["passed"], audit)
        self.assertEqual(
            "moss_transcribe_diarize.app.live_identity.BoundedCausalIdentityPreparer",
            audit["production_preparer_binding"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
