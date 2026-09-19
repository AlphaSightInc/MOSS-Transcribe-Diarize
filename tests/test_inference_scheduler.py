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


def test_scheduler_rejects_invalid_capacity_and_kind():
    with pytest.raises(ValueError, match="max_calls"):
        InferenceDispatchScheduler(max_calls=0, max_background_calls=1)
    with pytest.raises(ValueError, match="max_background_calls"):
        InferenceDispatchScheduler(max_calls=2, max_background_calls=3)
    with pytest.raises(ValueError, match="kind"):
        ScheduledInferenceRunner(object(), InferenceDispatchScheduler(), kind="unknown")
