from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.inference_scheduler import (
    InferenceDispatchCancelled,
    InferenceDispatchScheduler,
    ScheduledInferenceRunner,
)
from tools.qualify.scheduler_timing import (
    detects_whole_batch_hold,
    project_dispatch_timings,
)


def _thread(target):
    errors: list[BaseException] = []

    def run() -> None:
        try:
            target()
        except BaseException as exc:  # asserted by each caller
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    return worker, errors


def test_two_slots_reserve_background_to_one_and_dispatch_waiting_live_first():
    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    release_background = threading.Event()
    release_live_one = threading.Event()
    release_live_two = threading.Event()
    release_background_two = threading.Event()
    background_one_started = threading.Event()
    background_two_started = threading.Event()
    live_one_started = threading.Event()
    live_two_started = threading.Event()
    starts: list[str] = []

    def held(label: str, started: threading.Event, release: threading.Event):
        def call() -> str:
            starts.append(label)
            started.set()
            assert release.wait(timeout=2)
            return label

        return call

    background_one, background_one_errors = _thread(
        lambda: scheduler.run_background(
            "file-one", held("background-one", background_one_started, release_background)
        )
    )
    assert background_one_started.wait(timeout=1)
    background_two, background_two_errors = _thread(
        lambda: scheduler.run_background(
            "file-two", held("background-two", background_two_started, release_background_two)
        )
    )
    live_one, live_one_errors = _thread(
        lambda: scheduler.run_live(
            "live-one", held("live-one", live_one_started, release_live_one)
        )
    )
    assert live_one_started.wait(timeout=1)
    live_two, live_two_errors = _thread(
        lambda: scheduler.run_live(
            "live-two", held("live-two", live_two_started, release_live_two)
        )
    )

    assert scheduler.snapshot().running_calls == 2
    assert scheduler.snapshot().running_background_calls == 1
    assert not background_two_started.is_set()
    assert not live_two_started.is_set()

    release_live_one.set()
    assert live_two_started.wait(timeout=1)
    assert not background_two_started.is_set()
    release_live_two.set()
    release_background.set()
    assert background_two_started.wait(timeout=1)
    release_background_two.set()
    for worker in (background_one, background_two, live_one, live_two):
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert not background_one_errors
    assert not live_one_errors
    assert not live_two_errors
    assert not background_two_errors
    assert starts[:3] == ["background-one", "live-one", "live-two"]
    assert starts[3:] == ["background-two"]
    assert scheduler.snapshot().running_calls == 0


def test_cancelling_queued_background_never_calls_delegate():
    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    release = threading.Event()
    started = threading.Event()
    queued_called = threading.Event()

    running, running_errors = _thread(
        lambda: scheduler.run_background(
            "running",
            lambda: (started.set(), release.wait(timeout=2)),
        )
    )
    assert started.wait(timeout=1)
    queued, queued_errors = _thread(
        lambda: scheduler.run_background("cancelled", lambda: queued_called.set())
    )
    deadline = time.monotonic() + 1
    while scheduler.snapshot().waiting_background_calls != 1:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    assert scheduler.cancel_background("cancelled") is True
    queued.join(timeout=1)
    release.set()
    running.join(timeout=1)

    assert not queued_called.is_set()
    assert not running_errors
    assert len(queued_errors) == 1
    assert isinstance(queued_errors[0], InferenceDispatchCancelled)
    cancelled = next(
        timing for timing in scheduler.dispatch_timings()
        if timing.owner_key == "cancelled"
    )
    assert cancelled.started_monotonic_ns is None
    assert cancelled.ended_monotonic_ns is None


def test_stopped_meeting_settlement_cannot_freeze_other_active_capture():
    """One stopped meeting may settle; a second settlement cannot take Live's slot."""

    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    release_first_settlement = threading.Event()
    release_second_settlement = threading.Event()
    first_settlement_started = threading.Event()
    second_settlement_started = threading.Event()
    active_capture_started = threading.Event()

    first, first_errors = _thread(
        lambda: scheduler.run_background(
            "stopped-one",
            lambda: (
                first_settlement_started.set(),
                release_first_settlement.wait(timeout=2),
            ),
        )
    )
    assert first_settlement_started.wait(timeout=1)
    second, second_errors = _thread(
        lambda: scheduler.run_background(
            "stopped-two",
            lambda: (
                second_settlement_started.set(),
                release_second_settlement.wait(timeout=2),
            ),
        )
    )
    active, active_errors = _thread(
        lambda: scheduler.run_live(
            "still-recording",
            lambda: active_capture_started.set(),
        )
    )

    assert active_capture_started.wait(timeout=1)
    active.join(timeout=1)
    assert not active.is_alive()
    assert not second_settlement_started.is_set()
    assert scheduler.snapshot().running_background_calls == 1

    release_first_settlement.set()
    assert second_settlement_started.wait(timeout=1)
    release_second_settlement.set()
    for worker in (first, second):
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert not first_errors
    assert not second_errors
    assert not active_errors


def test_scheduled_runner_keeps_scheduler_controls_out_of_decoder_options():
    calls: list[tuple[object, dict[str, object]]] = []
    waiting: list[str] = []
    started: list[str] = []

    class Delegate:
        model_path = "model"

        def transcribe(self, audio_path, **kwargs):
            calls.append((audio_path, kwargs))
            return SimpleNamespace(text="ok")

    runner = ScheduledInferenceRunner(
        Delegate(),
        InferenceDispatchScheduler(max_calls=2, max_background_calls=1),
        kind="background",
    )
    result = runner.transcribe(
        "audio.wav",
        prompt="keep",
        _dispatch_key="meeting-one",
        _dispatch_on_wait=lambda: waiting.append("waiting"),
        _dispatch_on_start=lambda: started.append("started"),
    )

    assert result.text == "ok"
    assert calls == [("audio.wav", {"prompt": "keep"})]
    assert waiting == ["waiting"]
    assert started == ["started"]
    assert runner.scheduler.stage_clock_summary()["owners"][0]["owner_class"] == "file"


def test_scheduler_retains_content_free_dispatch_stage_clocks():
    ticks = iter((10, 20, 30, 40))
    scheduler = InferenceDispatchScheduler(
        max_calls=2,
        max_background_calls=1,
        monotonic_ns=lambda: next(ticks),
    )

    assert scheduler.run_background("meeting-one", lambda: "done") == "done"

    timing = scheduler.dispatch_timings()
    assert len(timing) == 1
    assert (
        timing[0].owner_kind,
        timing[0].owner_key,
        timing[0].window_index,
        timing[0].accepted_monotonic_ns,
        timing[0].wait_started_monotonic_ns,
        timing[0].started_monotonic_ns,
        timing[0].ended_monotonic_ns,
    ) == ("background", "meeting-one", 0, 10, 20, 30, 40)


def test_stage_clock_summary_reports_per_owner_wait_service_and_terminal_contention():
    ticks = iter(value * 1_000_000_000 for value in range(8))
    scheduler = InferenceDispatchScheduler(
        max_calls=1,
        max_background_calls=1,
        monotonic_ns=lambda: next(ticks),
    )
    first_started = threading.Event()
    release_first = threading.Event()

    first, first_errors = _thread(
        lambda: scheduler.run_background(
            "terminal-a",
            lambda: (first_started.set(), release_first.wait(timeout=2)),
        )
    )
    assert first_started.wait(timeout=1)
    second, second_errors = _thread(
        lambda: scheduler.run_background("terminal-b", lambda: "done")
    )
    deadline = time.monotonic() + 1
    while scheduler.snapshot().waiting_background_calls != 1:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    release_first.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert not first_errors and not second_errors

    assert scheduler.stage_clock_summary() == {
        "clock": "server_monotonic",
        "owners": [
            {
                "owner_kind": "background",
                "owner_key": "terminal-a",
                "owner_class": "terminal",
                "window_count": 1,
                "started_count": 1,
                "completed_count": 1,
                "acceptance_to_first_dispatch_ms": 2_000.0,
                "queue_wait_ms": 1_000.0,
                "service_ms": 3_000.0,
                "terminal_contention_ms": 0.0,
            },
            {
                "owner_kind": "background",
                "owner_key": "terminal-b",
                "owner_class": "terminal",
                "window_count": 1,
                "started_count": 1,
                "completed_count": 1,
                "acceptance_to_first_dispatch_ms": 3_000.0,
                "queue_wait_ms": 2_000.0,
                "service_ms": 1_000.0,
                "terminal_contention_ms": 1_000.0,
            },
        ],
        "terminal_vs_terminal_contention_ms": 1_000.0,
        "completed_windows": 2,
        "full_denominator": 2,
    }


def test_dispatch_instrument_sees_window_yield_and_terminal_contention():
    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    first_started = threading.Event()
    release_first = threading.Event()
    trace: list[str] = []

    def windows(owner: str, count: int, *, hold_first: bool = False) -> None:
        for index in range(count):
            def call(index=index):
                trace.append(f"{owner}:{index}")
                if hold_first and index == 0:
                    first_started.set()
                    assert release_first.wait(timeout=2)
            scheduler.run_background(owner, call)

    terminal_a, errors_a = _thread(
        lambda: windows("terminal-a", 3, hold_first=True)
    )
    assert first_started.wait(timeout=1)
    terminal_b, errors_b = _thread(lambda: windows("terminal-b", 3))
    file_job, file_errors = _thread(lambda: windows("file", 1))
    deadline = time.monotonic() + 1
    while scheduler.snapshot().waiting_background_calls != 2:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    release_first.set()
    for worker in (terminal_a, terminal_b, file_job):
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert not errors_a and not errors_b and not file_errors

    file_position = trace.index("file:0")
    assert any(item.startswith("terminal-") for item in trace[:file_position])
    assert any(item.startswith("terminal-") for item in trace[file_position + 1:])
    projection = project_dispatch_timings(
        scheduler.dispatch_timings(),
        file_keys={"file"},
        terminal_keys={"terminal-a", "terminal-b"},
    )
    assert projection["file_acceptance_to_first_dispatch_sec"]["file"] >= 0
    assert projection["terminal_vs_terminal_wait_sec"] > 0
    assert projection["completed_windows"] == projection["full_denominator"] == 7
    assert not detects_whole_batch_hold(
        scheduler.dispatch_timings(), terminal_key="terminal-a", file_key="file"
    )


def test_dispatch_instrument_detects_scheduler_above_window_loop():
    scheduler = InferenceDispatchScheduler(max_calls=1, max_background_calls=1)
    first_started = threading.Event()
    release_first = threading.Event()
    trace: list[str] = []

    def terminal_batch() -> None:
        for index in range(3):
            trace.append(f"terminal-wrong:{index}")
            if index == 0:
                first_started.set()
                assert release_first.wait(timeout=2)

    terminal, terminal_errors = _thread(
        lambda: scheduler.run_background("terminal-wrong", terminal_batch)
    )
    assert first_started.wait(timeout=1)
    file_job, file_errors = _thread(
        lambda: scheduler.run_background(
            "file-wrong", lambda: trace.append("file-wrong:0")
        )
    )
    deadline = time.monotonic() + 1
    while scheduler.snapshot().waiting_background_calls != 1:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    release_first.set()
    terminal.join(timeout=2)
    file_job.join(timeout=2)
    assert not terminal_errors and not file_errors
    assert trace == [
        "terminal-wrong:0",
        "terminal-wrong:1",
        "terminal-wrong:2",
        "file-wrong:0",
    ]
    assert detects_whole_batch_hold(
        scheduler.dispatch_timings(),
        terminal_key="terminal-wrong",
        file_key="file-wrong",
    )


def test_scheduler_rejects_invalid_capacity_and_kind():
    with pytest.raises(ValueError, match="max_calls"):
        InferenceDispatchScheduler(max_calls=0, max_background_calls=1)
    with pytest.raises(ValueError, match="max_background_calls"):
        InferenceDispatchScheduler(max_calls=2, max_background_calls=3)
    with pytest.raises(ValueError, match="kind"):
        ScheduledInferenceRunner(object(), InferenceDispatchScheduler(), kind="unknown")
    with pytest.raises(ValueError, match="owner class"):
        InferenceDispatchScheduler().run_background(
            "owner", lambda: None, owner_class="unknown"
        )
