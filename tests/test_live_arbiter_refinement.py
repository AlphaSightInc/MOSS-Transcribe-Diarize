"""T1 tests for the plan §6 M5 `live_refinement` queue.

One question per test, and every one of them is a rule from plan §6 M5 or §10.6 rather than
an implementation detail: where a rolling witness sits in the priority order, how many of
them may exist per session, what happens to the older one, and what a running one is
protected from. The pre-existing batch/canonical/provisional priority tests live in
`tests/test_live_vad.py`; these cover only what the fourth queue added.
"""

from __future__ import annotations

from moss_transcribe_diarize.app.live_arbiter import InferenceArbiter


def _arbiter() -> InferenceArbiter:
    return InferenceArbiter()


def test_refinement_runs_after_canonical_and_before_provisional():
    arbiter = _arbiter()

    arbiter.submit_live_provisional(coalesce_key="session-a", payload="provisional")
    arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="refinement")
    arbiter.submit_live_canonical(key="session-a:span-1", payload="canonical")
    arbiter.submit_batch(key="job-a", payload="batch")

    order = [
        arbiter.next_work().payload,
        arbiter.next_work().payload,
        arbiter.next_work().payload,
        arbiter.next_work().payload,
    ]

    assert order == ["batch", "canonical", "refinement", "provisional"]
    assert arbiter.next_work() is None


def test_refinement_never_delays_canonical_work_queued_after_it():
    # Plan §10.6: rolling must not delay unresolved short canonical work. The witness is
    # already queued when a 2.5 s span arrives; the span still goes first.
    arbiter = _arbiter()

    arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="refinement")
    arbiter.submit_live_canonical(key="session-a:span-1", payload="canonical-1")
    arbiter.submit_live_canonical(key="session-a:span-2", payload="canonical-2")

    assert [arbiter.next_work().payload for _ in range(3)] == [
        "canonical-1",
        "canonical-2",
        "refinement",
    ]


def test_newer_queued_witness_replaces_the_older_one_for_the_same_session():
    arbiter = _arbiter()

    first = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-3")
    second = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-4")

    assert first.accepted and second.accepted
    assert second.replaced_item_id == first.item_id
    assert arbiter.snapshot().live_refinement == 1
    assert arbiter.next_work().payload == "window-4"
    assert arbiter.next_work() is None


def test_a_running_witness_is_not_cancelled_by_a_newer_one():
    arbiter = _arbiter()

    admitted = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-3")
    running = arbiter.next_work()
    refused = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-4")

    assert running.id == admitted.item_id
    assert running.kind == InferenceArbiter.LIVE_REFINEMENT
    assert not refused.accepted
    assert refused.item_id is None
    assert refused.reason == "live refinement already running"
    assert arbiter.snapshot().live_refinement == 0
    assert arbiter.snapshot().live_refinement_running == 1
    assert arbiter.next_work() is None


def test_releasing_the_running_witness_admits_the_next_one():
    arbiter = _arbiter()

    admitted = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-3")
    arbiter.next_work()

    assert arbiter.release_live_refinement(item_id=admitted.item_id) is True
    assert arbiter.snapshot().live_refinement_running == 0

    readmitted = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-4")

    assert readmitted.accepted
    assert readmitted.replaced_item_id is None
    assert arbiter.next_work().payload == "window-4"


def test_releasing_an_unknown_item_id_changes_nothing():
    arbiter = _arbiter()

    admitted = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-3")
    arbiter.next_work()

    assert arbiter.release_live_refinement(item_id=admitted.item_id + 99) is False
    assert arbiter.snapshot().live_refinement_running == 1
    assert not arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-4").accepted


def test_releasing_twice_is_reported_the_second_time_and_frees_nothing_extra():
    arbiter = _arbiter()

    first = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-3")
    arbiter.next_work()
    arbiter.release_live_refinement(item_id=first.item_id)
    second = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-4")
    arbiter.next_work()

    assert arbiter.release_live_refinement(item_id=first.item_id) is False
    assert arbiter.snapshot().live_refinement_running == 1
    assert arbiter.release_live_refinement(item_id=second.item_id) is True
    assert arbiter.snapshot().live_refinement_running == 0


def test_one_session_running_does_not_block_another_session():
    # The rule is per session, and the coalesce key is what carries the session. Two
    # sessions sharing one arbiter each get a witness; neither suppresses the other.
    arbiter = _arbiter()

    a = arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="a-window-1")
    b = arbiter.submit_live_refinement(coalesce_key="rolling:1", payload="b-window-1")

    assert a.accepted and b.accepted
    assert arbiter.snapshot().live_refinement == 2

    dispatched_a = arbiter.next_work()

    assert dispatched_a.payload == "a-window-1"
    assert not arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="a-window-2").accepted
    assert arbiter.submit_live_refinement(coalesce_key="rolling:1", payload="b-window-2").accepted

    dispatched_b = arbiter.next_work()

    assert dispatched_b.payload == "b-window-2"
    assert arbiter.snapshot().live_refinement_running == 2


def test_replacing_a_queued_witness_yields_the_place_in_line_to_a_waiting_session():
    # Across sessions the queue is FIFO, and a replacement re-joins at the back -- the same
    # rule `submit_live_provisional` already has. It is the rule that cannot starve anyone:
    # a session loses its place only by choosing to replace its own witness, whereas
    # first-arrival order would let one session hold the front while swapping in a newer
    # window every time, and the other session would never decode.
    arbiter = _arbiter()

    arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="a-window-1")
    arbiter.submit_live_refinement(coalesce_key="rolling:1", payload="b-window-1")
    arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="a-window-2")

    assert [arbiter.next_work().payload, arbiter.next_work().payload] == [
        "b-window-1",
        "a-window-2",
    ]


def test_an_empty_coalesce_key_is_refused_without_touching_the_queue():
    arbiter = _arbiter()

    arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="window-3")
    try:
        arbiter.submit_live_refinement(coalesce_key="", payload="nameless")
    except ValueError as exc:
        assert "non-empty" in str(exc)
    else:  # pragma: no cover - the guard is the point of the test
        raise AssertionError("an empty coalesce key must be refused.")

    assert arbiter.snapshot().live_refinement == 1
    assert arbiter.next_work().payload == "window-3"


def test_snapshot_reports_refinement_depth_separately_from_provisional():
    arbiter = _arbiter()

    arbiter.submit_live_provisional(coalesce_key="session-a", payload="provisional")
    arbiter.submit_live_refinement(coalesce_key="rolling:0", payload="refinement")

    snapshot = arbiter.snapshot()

    assert (snapshot.batch, snapshot.live_canonical) == (0, 0)
    assert snapshot.live_provisional == 1
    assert snapshot.live_refinement == 1
    assert snapshot.live_refinement_running == 0


def test_discard_live_queued_removes_all_live_kinds_but_not_batch_or_running_work():
    arbiter = _arbiter()
    arbiter.submit_batch(key="file-job", payload="batch")
    arbiter.submit_live_canonical(key="session-a:span", payload="canonical", weight=2)
    running = arbiter.submit_live_refinement(coalesce_key="session-a:running", payload="running")
    assert arbiter.next_work().payload == "batch"
    assert arbiter.next_work().payload == "canonical"
    assert arbiter.next_work().payload == "running"
    arbiter.submit_batch(key="file-job-queued", payload="queued-batch")
    arbiter.submit_live_canonical(key="session-a:queued", payload="queued-canonical")
    arbiter.submit_live_refinement(coalesce_key="session-a:queued", payload="queued-refinement")
    arbiter.submit_live_provisional(coalesce_key="session-a", payload="queued-provisional")

    discarded = arbiter.discard_live_queued()

    assert [item.payload for item in discarded] == [
        "queued-canonical",
        "queued-refinement",
        "queued-provisional",
    ]
    snapshot = arbiter.snapshot()
    assert snapshot.live_canonical == 0
    assert snapshot.live_refinement == 0
    assert snapshot.live_provisional == 0
    assert snapshot.live_refinement_running == 1
    assert arbiter.next_work().payload == "queued-batch"
    assert arbiter.release_live_refinement(item_id=running.item_id) is True
