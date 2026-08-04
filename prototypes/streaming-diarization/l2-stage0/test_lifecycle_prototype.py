#!/usr/bin/env python3
"""A3 observable lifecycle behavior tests."""

from __future__ import annotations

import unittest

from lifecycle_prototype import (
    CurrentClosingClosedControl,
    EarlyTapeReleaseControl,
    LifecyclePrototype,
    LifecycleViolation,
    OneThreadPerSessionControl,
)


class LifecyclePrototypeTest(unittest.TestCase):
    def test_capture_authority_ends_at_stop_ack(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=2)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")
        lifecycle.capture("meeting-1", b"closing-frame")

        snapshot = lifecycle.acknowledge_stop("meeting-1")

        self.assertEqual(snapshot["state"], "finalizing")
        self.assertFalse(snapshot["capture_authority"])
        with self.assertRaisesRegex(LifecycleViolation, "capture_authority_closed"):
            lifecycle.capture("meeting-1", b"late-frame")

    def test_view_authority_survives_finalizing_through_terminal_revision(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=2)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")
        lifecycle.acknowledge_stop("meeting-1")

        finalizing = lifecycle.view("meeting-1")
        lifecycle.start_next_finalizer()
        lifecycle.finish_active_finalizer("success")
        terminal = lifecycle.view("meeting-1")
        events = lifecycle.view_events("meeting-1", after_sequence=0)

        self.assertTrue(finalizing["view_authority"])
        self.assertEqual(finalizing["state"], "finalizing")
        self.assertTrue(terminal["view_authority"])
        self.assertEqual(terminal["state"], "closed")
        self.assertEqual(
            [(event["sequence"], event["type"]) for event in events],
            [(1, "identity_revision_final")],
        )

    def test_tape_is_sealed_and_read_leased_while_finalizer_runs(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=2)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")

        queued = lifecycle.acknowledge_stop("meeting-1")
        running = lifecycle.start_next_finalizer()

        self.assertTrue(queued["tape_sealed"])
        self.assertEqual(queued["tape_lease_count"], 1)
        self.assertEqual(queued["tape_lease_acquires"], 1)
        self.assertEqual(queued["tape_lease_releases"], 0)
        self.assertTrue(running["tape_sealed"])
        self.assertEqual(running["tape_lease_count"], 1)

    def test_one_bounded_queue_owns_finalizers_and_one_cpu_runs(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=2)
        for meeting_id in ("meeting-1", "meeting-2"):
            lifecycle.start(meeting_id)
            lifecycle.begin_stop(meeting_id)
            lifecycle.acknowledge_stop(meeting_id)
        lifecycle.start_next_finalizer()
        lifecycle.start("meeting-3")
        lifecycle.begin_stop("meeting-3")
        lifecycle.acknowledge_stop("meeting-3")

        with self.assertRaisesRegex(LifecycleViolation, "cpu_finalizer_already_active"):
            lifecycle.start_next_finalizer()
        scheduler = lifecycle.scheduler_snapshot()

        self.assertEqual(scheduler["queue_capacity"], 2)
        self.assertEqual(scheduler["queue_depth"], 2)
        self.assertEqual(scheduler["queue_owner_count"], 1)
        self.assertEqual(scheduler["active_cpu_finalizers"], 1)
        self.assertEqual(scheduler["max_cpu_finalizers"], 1)

    def test_bounded_queue_refuses_overflow_without_partial_transition(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=1)
        lifecycle.start("queued")
        lifecycle.begin_stop("queued")
        lifecycle.acknowledge_stop("queued")
        lifecycle.start("rejected")
        lifecycle.begin_stop("rejected")

        with self.assertRaisesRegex(LifecycleViolation, "finalizer_queue_full"):
            lifecycle.acknowledge_stop("rejected")
        rejected = lifecycle.view("rejected")

        self.assertEqual(lifecycle.scheduler_snapshot()["queue_depth"], 1)
        self.assertEqual(rejected["state"], "closing")
        self.assertTrue(rejected["capture_authority"])
        self.assertFalse(rejected["tape_sealed"])
        self.assertEqual(rejected["tape_lease_count"], 0)

    def test_every_failed_finalizer_releases_once_and_falls_back_to_l1(self) -> None:
        for outcome in (
            "timeout",
            "cancelled",
            "shutdown",
            "degraded_tape",
            "exception",
        ):
            with self.subTest(outcome=outcome):
                lifecycle = LifecyclePrototype(queue_capacity=1)
                lifecycle.start("meeting-1")
                lifecycle.begin_stop("meeting-1")
                lifecycle.acknowledge_stop("meeting-1")
                lifecycle.start_next_finalizer()

                failed = lifecycle.finish_active_finalizer(outcome)

                self.assertEqual(failed["state"], "failed")
                self.assertEqual(failed["result_source"], "l1")
                self.assertEqual(failed["fallback_reason"], outcome)
                self.assertEqual(failed["tape_lease_count"], 0)
                self.assertEqual(failed["tape_lease_acquires"], 1)
                self.assertEqual(failed["tape_lease_releases"], 1)
                with self.assertRaisesRegex(LifecycleViolation, "no_active_finalizer"):
                    lifecycle.finish_active_finalizer(outcome)
                self.assertEqual(
                    lifecycle.view("meeting-1")["tape_lease_releases"], 1
                )

    def test_raised_finalizer_exception_releases_once_and_falls_back(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=1)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")
        lifecycle.acknowledge_stop("meeting-1")
        lifecycle.start_next_finalizer()

        def raise_finalizer_error() -> str:
            raise RuntimeError("synthetic-finalizer-fault")

        failed = lifecycle.execute_active_finalizer(raise_finalizer_error)

        self.assertEqual(failed["state"], "failed")
        self.assertEqual(failed["fallback_reason"], "exception")
        self.assertEqual(failed["result_source"], "l1")
        self.assertEqual(failed["tape_lease_count"], 0)
        self.assertEqual(failed["tape_lease_releases"], 1)

    def test_abort_never_starts_l2(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=1)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")

        aborted = lifecycle.abort("meeting-1")

        self.assertEqual(aborted["state"], "aborted")
        self.assertFalse(aborted["capture_authority"])
        self.assertFalse(aborted["l2_started"])
        self.assertEqual(aborted["result_source"], "l1")
        self.assertEqual(lifecycle.scheduler_snapshot()["queue_depth"], 0)
        with self.assertRaisesRegex(LifecycleViolation, "finalizer_queue_empty"):
            lifecycle.start_next_finalizer()

    def test_abort_of_queued_finalization_removes_job_without_l2(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=1)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")
        lifecycle.acknowledge_stop("meeting-1")

        aborted = lifecycle.abort("meeting-1")

        self.assertEqual(aborted["state"], "aborted")
        self.assertFalse(aborted["l2_started"])
        self.assertEqual(aborted["tape_lease_count"], 0)
        self.assertEqual(aborted["tape_lease_releases"], 1)
        self.assertEqual(lifecycle.scheduler_snapshot()["queue_depth"], 0)
        with self.assertRaisesRegex(LifecycleViolation, "finalizer_queue_empty"):
            lifecycle.start_next_finalizer()

    def test_ttl_zero_reaps_only_after_lease_release(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=1)
        lifecycle.start("meeting-1")
        lifecycle.begin_stop("meeting-1")
        lifecycle.acknowledge_stop("meeting-1")

        blocked = lifecycle.reap_ttl_zero()
        lifecycle.start_next_finalizer()
        lifecycle.finish_active_finalizer("success")
        reaped = lifecycle.reap_ttl_zero()

        self.assertEqual(blocked, [])
        self.assertEqual(reaped, ["meeting-1"])
        self.assertTrue(lifecycle.view("meeting-1")["tape_reaped"])
        self.assertEqual(lifecycle.view("meeting-1")["tape_lease_releases"], 1)

    def test_new_live_meeting_progresses_while_older_finalizer_runs(self) -> None:
        lifecycle = LifecyclePrototype(queue_capacity=2)
        lifecycle.start("older")
        lifecycle.begin_stop("older")
        lifecycle.acknowledge_stop("older")
        lifecycle.start_next_finalizer()

        lifecycle.start("new-live")
        live = lifecycle.capture("new-live", b"live-frame")
        responsiveness = lifecycle.responsiveness_snapshot()

        self.assertEqual(live["state"], "active")
        self.assertEqual(live["captured_frames"], 1)
        self.assertEqual(responsiveness["active_cpu_finalizers"], 1)
        self.assertEqual(responsiveness["live_captures_during_finalizer"], 1)


class LifecycleNegativeControlTest(unittest.TestCase):
    def test_active_closing_closed_reproduces_invisible_revision(self) -> None:
        result = CurrentClosingClosedControl().run()

        self.assertFalse(result["invariant_passed"])
        self.assertEqual(result["failed_invariant"], "terminal_revision_visible")
        self.assertEqual(result["state_path"], ["active", "closing", "closed"])
        self.assertTrue(result["revision_published"])
        self.assertFalse(result["view_authority_at_revision"])

    def test_one_thread_per_session_fails_bounded_concurrency(self) -> None:
        result = OneThreadPerSessionControl().run(session_count=3)

        self.assertFalse(result["invariant_passed"])
        self.assertEqual(result["failed_invariant"], "bounded_single_cpu_finalizer")
        self.assertEqual(result["queue_owner_count"], 0)
        self.assertEqual(result["max_cpu_finalizers"], 3)

    def test_early_tape_release_fails_read_lease_invariant(self) -> None:
        result = EarlyTapeReleaseControl().run()

        self.assertFalse(result["invariant_passed"])
        self.assertEqual(result["failed_invariant"], "tape_read_lease_held")
        self.assertEqual(result["lease_count_at_finalizer_start"], 0)
        self.assertTrue(result["ttl_zero_reaped_before_read"])


if __name__ == "__main__":
    unittest.main()
