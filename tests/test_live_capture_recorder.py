from __future__ import annotations

from dataclasses import dataclass, field

from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_tape import LiveCaptureTapeRecorder


def _frame() -> LiveV2Frame:
    return LiveV2Frame(
        lane=LiveLane.SYSTEM,
        sequence=0,
        capture_timestamp_ns=1,
        device_epoch=0,
        silent=False,
        discontinuity=False,
        sample_rate=16_000,
        sample_count=2,
        pcm=b"\x01\x00\x02\x00",
    )


@dataclass
class Stage:
    lane_frames: list[LiveV2Frame] = field(default_factory=list)
    mixed: list[tuple[bytes, int, int, int]] = field(default_factory=list)

    def append_lane_frame(self, frame: LiveV2Frame) -> None:
        self.lane_frames.append(frame)

    def append_mixed(
        self,
        *,
        pcm: bytes,
        start_timestamp_ns: int,
        sample_count: int,
        sample_rate: int,
    ) -> None:
        self.mixed.append((pcm, start_timestamp_ns, sample_count, sample_rate))


class Store:
    def __init__(self) -> None:
        self.stages: dict[str, Stage] = {}

    def create(self, session_id: str) -> Stage:
        stage = Stage()
        self.stages[session_id] = stage
        return stage

    def get(self, session_id: str) -> Stage | None:
        return self.stages.get(session_id)

    def release(self, session_id: str) -> Stage | None:
        return self.stages.pop(session_id, None)

    def reap(self, *, active_session_ids=()):
        active = set(active_session_ids)
        reaped = tuple(key for key in self.stages if key not in active)
        for key in reaped:
            self.stages.pop(key)
        return reaped


class HostileStore:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, action: str):
        self.calls.append(action)
        raise OSError("capture stage unavailable")

    def create(self, session_id):
        del session_id
        self._fail("create")

    def get(self, session_id):
        del session_id
        self._fail("get")

    def release(self, session_id):
        del session_id
        self._fail("release")

    def reap(self, *, active_session_ids=()):
        del active_session_ids
        self._fail("reap")


def test_account_capture_recorder_tees_accepted_lane_and_mixed_audio_then_releases():
    store = Store()
    recorder = LiveCaptureTapeRecorder(store)
    frame = _frame()

    recorder.create("meeting-a")
    recorder.append_lane_frame("meeting-a", frame)
    recorder.append_mixed(
        "meeting-a",
        pcm=b"\x03\x00\x04\x00",
        start_timestamp_ns=1,
        sample_count=2,
    )

    stage = store.stages["meeting-a"]
    assert stage.lane_frames == [frame]
    assert stage.mixed == [(b"\x03\x00\x04\x00", 1, 2, 16_000)]
    recorder.release("meeting-a")
    assert store.stages == {}


def test_disabled_or_missing_capture_stage_is_a_noop():
    disabled = LiveCaptureTapeRecorder(None)
    disabled.create("meeting-a")
    disabled.append_lane_frame("meeting-a", _frame())
    disabled.append_mixed(
        "meeting-a", pcm=b"\x00\x00", start_timestamp_ns=1, sample_count=1
    )
    disabled.release("meeting-a")
    assert disabled.reap() == ()

    store = Store()
    enabled = LiveCaptureTapeRecorder(store)
    enabled.append_lane_frame("missing", _frame())
    enabled.release("missing")
    assert store.stages == {}


def test_capture_stage_failure_never_escapes_the_live_path(caplog):
    store = HostileStore()
    recorder = LiveCaptureTapeRecorder(store)

    with caplog.at_level("WARNING", logger="moss_transcribe_diarize.live.tape"):
        recorder.create("meeting-a")
        recorder.append_lane_frame("meeting-a", _frame())
        recorder.append_mixed(
            "meeting-a", pcm=b"\x00\x00", start_timestamp_ns=1, sample_count=1
        )
        recorder.release("meeting-a")
        assert recorder.reap() == ()

    assert store.calls == ["create", "get", "get", "release", "reap"]
    assert len(caplog.records) == 5
