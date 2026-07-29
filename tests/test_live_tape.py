"""ADR-0002 step 2: the tape recorder, bounded by ADR-0003.

Two contracts meet here and both are load-bearing.

* **ADR-0002 gate C -- assembly correctness.** Replay out-of-order, dropped, duplicated and
  burst-lost 0.5 s frames into the appender: byte-exact reconstruction, stable offsets
  under gaps, checkpoint/resume mid-session. The prototype passed 7/7 against a throwaway
  appender; these nodes are that gate against the tracked one.
* **ADR-0003 D2-D6 -- the retention bound.** Opt-in, one admissible root, a bounded tape
  whose pressure degrades the tape rather than the meeting, and a reaper that runs at
  startup.

The defect these nodes exist to keep dead is a tape that *looks* right: silence written
where a frame was dropped, with no gap manifest, makes a meeting's wall-clock offsets drift
by exactly the audio that never arrived -- and every retrospective sweep seeded from it
would relabel the wrong seconds.
"""

import json
import os
import struct
from pathlib import Path

import pytest

from moss_transcribe_diarize.app.live_lane_contract import LiveLane, LiveV2Frame
from moss_transcribe_diarize.app.live_session import LIVE_SAMPLE_RATE, PCM16_BYTES_PER_SAMPLE
from moss_transcribe_diarize.app.live_tape import (
    MIXED_TRACK,
    TAPE_CAPACITY_EXHAUSTED,
    TAPE_DIRECTORY_MODE,
    TAPE_FILE_MODE,
    TAPE_FRAME_NOT_ADMISSIBLE,
    TAPE_INDEX_FILENAME,
    TAPE_WRITE_FAILED,
    LiveSessionTape,
    LiveSessionTapeRecorder,
    LiveSessionTapeStore,
    LiveTapeRootError,
)


FRAME_SAMPLES = 8000  # the domain-contract live frame size, 0.5 s at 16 kHz
FRAME_NS = FRAME_SAMPLES * 1_000_000_000 // LIVE_SAMPLE_RATE
ORIGIN_NS = 1_700_000_000_000_000_000
CAP_BYTES = 8 * 1024 * 1024


def _pcm(seed: int, sample_count: int = FRAME_SAMPLES) -> bytes:
    """Distinguishable, non-zero PCM so silence can never be mistaken for content."""

    values = [((seed * 977 + index * 13) % 20000) - 10000 or 1 for index in range(sample_count)]
    return struct.pack("<" + "h" * sample_count, *values)


def _frame(sequence: int, *, lane: LiveLane = LiveLane.SYSTEM, silent: bool = False) -> LiveV2Frame:
    return LiveV2Frame(
        lane=lane,
        sequence=sequence,
        capture_timestamp_ns=ORIGIN_NS + sequence * FRAME_NS,
        device_epoch=1,
        silent=silent,
        discontinuity=False,
        sample_rate=LIVE_SAMPLE_RATE,
        sample_count=FRAME_SAMPLES,
        pcm=b"\x00" * (FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE) if silent else _pcm(sequence),
    )


def _store(tmp_path: Path, **kwargs) -> LiveSessionTapeStore:
    return LiveSessionTapeStore.declared(
        root=tmp_path / "tape-root",
        max_bytes_per_session=kwargs.pop("max_bytes_per_session", CAP_BYTES),
        **kwargs,
    )


def _expected(sequences) -> bytes:
    """The tape a perfect delivery of `sequences` would produce, gaps as silence."""

    highest = max(sequences)
    blocks = []
    for index in range(highest + 1):
        blocks.append(
            _pcm(index) if index in sequences else b"\x00" * (FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE)
        )
    return b"".join(blocks)


# --------------------------------------------------------------------------------------
# ADR-0003 D2 -- opt-in
# --------------------------------------------------------------------------------------


def test_retention_is_opt_in_because_there_is_no_default_root():
    """D2. A store cannot be built without a declared root, so no root means no tape."""

    with pytest.raises(TypeError):
        LiveSessionTapeStore.declared(max_bytes_per_session=CAP_BYTES)  # type: ignore[call-arg]


def test_a_cap_is_required_but_a_positive_ttl_is_not_defaulted(tmp_path):
    """D3/D5. The tool may only choose the zero TTL; the cap has no safe default at all."""

    with pytest.raises(TypeError):
        LiveSessionTapeStore.declared(root=tmp_path / "tape-root")  # type: ignore[call-arg]
    store = _store(tmp_path)
    assert store.retention_ttl_seconds == 0.0

    for bad in (0, -1, True, 1.5):
        with pytest.raises(LiveTapeRootError):
            LiveSessionTapeStore.declared(root=tmp_path / "r2", max_bytes_per_session=bad)
    with pytest.raises(LiveTapeRootError):
        LiveSessionTapeStore.declared(
            root=tmp_path / "r3", max_bytes_per_session=CAP_BYTES, retention_ttl_seconds=-1
        )


# --------------------------------------------------------------------------------------
# ADR-0003 D4 -- one declared root, where modes are real
# --------------------------------------------------------------------------------------


def test_a_root_inside_the_repository_checkout_is_refused():
    """D4(2). A rollback is `git checkout <sha>`; `git clean` must never be a reaper."""

    checkout = Path(__file__).resolve().parents[1]

    with pytest.raises(LiveTapeRootError, match="outside the repository checkout"):
        LiveSessionTapeStore.declared(
            root=checkout / "live-tape-scratch", max_bytes_per_session=CAP_BYTES
        )


def test_a_relative_root_is_refused(tmp_path):
    with pytest.raises(LiveTapeRootError, match="absolute path"):
        LiveSessionTapeStore.declared(root="tape-root", max_bytes_per_session=CAP_BYTES)


def test_a_root_sharing_a_filesystem_with_a_runs_tree_is_refused(tmp_path):
    """D4(3). A runaway tape answers 507 to the batch service without touching it."""

    runs = tmp_path / "runs"
    runs.mkdir()

    with pytest.raises(LiveTapeRootError, match="share a filesystem"):
        LiveSessionTapeStore.declared(
            root=tmp_path / "tape-root",
            max_bytes_per_session=CAP_BYTES,
            runs_directories=[runs],
        )


def test_a_root_inside_a_runs_tree_is_refused_by_name(tmp_path, monkeypatch):
    """Containment is checked separately: on one filesystem the device test cannot see it."""

    runs = tmp_path / "runs"
    runs.mkdir()
    monkeypatch.setattr(
        "moss_transcribe_diarize.app.live_tape.Path.stat",
        lambda self, *a, **k: os.stat_result(
            (0o40700, 0, hash(str(self)) & 0xFFFF, 1, 0, 0, 0, 0, 0, 0)
        ),
        raising=False,
    )
    with pytest.raises(LiveTapeRootError, match="inside a runs directory"):
        LiveSessionTapeStore.declared(
            root=runs / "tape-root",
            max_bytes_per_session=CAP_BYTES,
            runs_directories=[runs],
        )


def test_a_filesystem_that_does_not_enforce_modes_is_refused(tmp_path, monkeypatch):
    """D4(4). `/mnt/d` is a 9p drvfs mount where chmod is a silent no-op; say so early."""

    root = tmp_path / "tape-root"
    root.mkdir()
    os.chmod(root, 0o755)
    monkeypatch.setattr("moss_transcribe_diarize.app.live_tape.os.chmod", lambda *a, **k: None)

    with pytest.raises(LiveTapeRootError, match="does not enforce modes"):
        _store(tmp_path)


def test_the_root_the_tape_and_its_files_carry_the_declared_modes(tmp_path):
    """D4(1). The posture live.key and live-auth.json already have."""

    store = _store(tmp_path)
    tape = store.create("session-a")
    tape.append_lane_frame(_frame(0))
    tape.end()

    assert store.root.stat().st_mode & 0o777 == TAPE_DIRECTORY_MODE
    assert tape.directory.stat().st_mode & 0o777 == TAPE_DIRECTORY_MODE
    assert tape.track_path(LiveLane.SYSTEM.value).stat().st_mode & 0o777 == TAPE_FILE_MODE
    assert tape.index_path.stat().st_mode & 0o777 == TAPE_FILE_MODE


def test_a_session_id_that_is_not_a_path_component_is_refused(tmp_path):
    store = _store(tmp_path)

    for bad in ("../escape", "a/b", "", ".", ".."):
        with pytest.raises(ValueError):
            store.create(bad)


# --------------------------------------------------------------------------------------
# ADR-0002 gate C -- assembly correctness
# --------------------------------------------------------------------------------------


def test_gate_c_in_order_delivery_is_byte_exact(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a")

    for sequence in range(6):
        assert tape.append_lane_frame(_frame(sequence)).written is True

    assert tape.read_track(LiveLane.SYSTEM.value) == _expected(set(range(6)))
    assert tape.gaps(LiveLane.SYSTEM.value) == ()


def test_gate_c_duplicates_are_ignored_and_counted(tmp_path):
    """Outbox retry semantics: the same frame arrives twice and must not shift the tape."""

    store = _store(tmp_path)
    tape = store.create("session-a")

    for sequence in (0, 1, 1, 2, 0, 2):
        tape.append_lane_frame(_frame(sequence))

    assert tape.read_track(LiveLane.SYSTEM.value) == _expected({0, 1, 2})
    track = tape.manifest()["tracks"][LiveLane.SYSTEM.value]
    assert (track["frames_written"], track["duplicate_frames"]) == (3, 3)


def test_gate_c_reordered_delivery_reconstructs_the_same_bytes(tmp_path):
    """Placement is by capture timestamp, never by arrival order -- including backwards."""

    store = _store(tmp_path)
    tape = store.create("session-a")

    for sequence in (3, 1, 4, 0, 2):
        assert tape.append_lane_frame(_frame(sequence)).written is True

    assert tape.read_track(LiveLane.SYSTEM.value) == _expected({0, 1, 2, 3, 4})
    assert tape.gaps(LiveLane.SYSTEM.value) == ()
    # Sequence 3 arrived first, so the track was rebased when 1 and then 0 turned up.
    assert tape.manifest()["tracks"][LiveLane.SYSTEM.value]["rebases"] == 2
    assert tape.manifest()["tracks"][LiveLane.SYSTEM.value]["origin_timestamp_ns"] == ORIGIN_NS


def test_gate_c_a_dropped_frame_becomes_silence_and_a_named_gap(tmp_path):
    """The clause that makes offsets true: a hole is silence *and* an entry in the manifest."""

    store = _store(tmp_path)
    tape = store.create("session-a")

    delivered = {0, 1, 3, 4}
    for sequence in sorted(delivered):
        tape.append_lane_frame(_frame(sequence))

    assert tape.read_track(LiveLane.SYSTEM.value) == _expected(delivered)
    gaps = tape.gaps(LiveLane.SYSTEM.value)
    assert [(gap.start_sample, gap.end_sample) for gap in gaps] == [
        (2 * FRAME_SAMPLES, 3 * FRAME_SAMPLES)
    ]
    assert gaps[0].sample_count == FRAME_SAMPLES
    # Frame 3 sits at its true wall-clock offset, not packed against frame 1.
    body = tape.read_track(LiveLane.SYSTEM.value)
    start = 3 * FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE
    assert body[start : start + FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE] == _pcm(3)


def test_gate_c_burst_loss_is_one_gap_accounting_for_every_lost_frame(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a")

    delivered = {0, 1, 8, 9}
    for sequence in sorted(delivered):
        tape.append_lane_frame(_frame(sequence))

    gaps = tape.gaps(LiveLane.SYSTEM.value)
    assert [(gap.start_sample, gap.end_sample) for gap in gaps] == [
        (2 * FRAME_SAMPLES, 8 * FRAME_SAMPLES)
    ]
    assert sum(gap.sample_count for gap in gaps) == 6 * FRAME_SAMPLES
    assert tape.read_track(LiveLane.SYSTEM.value) == _expected(delivered)


def test_gate_c_a_late_frame_fills_its_gap_instead_of_correcting_it(tmp_path):
    """The gap manifest is the complement of coverage, so it can only ever shrink."""

    store = _store(tmp_path)
    tape = store.create("session-a")

    for sequence in (0, 1, 3):
        tape.append_lane_frame(_frame(sequence))
    assert len(tape.gaps(LiveLane.SYSTEM.value)) == 1

    assert tape.append_lane_frame(_frame(2)).written is True
    assert tape.gaps(LiveLane.SYSTEM.value) == ()
    assert tape.read_track(LiveLane.SYSTEM.value) == _expected({0, 1, 2, 3})


def test_gate_c_checkpoint_and_resume_reproduce_the_uninterrupted_tape(tmp_path):
    """ADR-0002 lists the tape as the crash/resume checkpoint; resume from the index alone."""

    sequences = list(range(10))
    uninterrupted = _store(tmp_path / "a")
    reference = uninterrupted.create("session-a")
    for sequence in sequences:
        reference.append_lane_frame(_frame(sequence))
    reference.end()

    interrupted = _store(tmp_path / "b")
    tape = interrupted.create("session-a")
    for sequence in sequences[:4]:  # 40 %
        tape.append_lane_frame(_frame(sequence))
    directory = tape.directory
    del tape  # the process dies here; nothing was flushed on the way out

    resumed = LiveSessionTape.resume(directory)
    for sequence in sequences[4:7]:  # 70 %
        resumed.append_lane_frame(_frame(sequence))
    del resumed

    finished = LiveSessionTape.resume(directory)
    for sequence in sequences[7:]:
        finished.append_lane_frame(_frame(sequence))
    finished.end()

    assert finished.read_track(LiveLane.SYSTEM.value) == reference.read_track(LiveLane.SYSTEM.value)
    assert finished.gaps(LiveLane.SYSTEM.value) == ()
    assert finished.session_id == "session-a"


def test_resume_carries_the_gap_manifest_across_the_crash(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a")
    for sequence in (0, 2):
        tape.append_lane_frame(_frame(sequence))
    directory = tape.directory
    del tape

    resumed = LiveSessionTape.resume(directory)

    assert [(gap.start_sample, gap.end_sample) for gap in resumed.gaps(LiveLane.SYSTEM.value)] == [
        (FRAME_SAMPLES, 2 * FRAME_SAMPLES)
    ]
    assert resumed.append_lane_frame(_frame(1)).written is True
    assert resumed.gaps(LiveLane.SYSTEM.value) == ()
    assert resumed.read_track(LiveLane.SYSTEM.value) == _expected({0, 1, 2})


def test_captured_silence_and_a_dropped_frame_are_not_the_same_fact(tmp_path):
    """Both are zeros on disk; only the manifest can tell a quiet room from a lost frame."""

    store = _store(tmp_path)
    tape = store.create("session-a")

    tape.append_lane_frame(_frame(0))
    tape.append_lane_frame(_frame(1, silent=True))
    tape.append_lane_frame(_frame(3))

    body = tape.read_track(LiveLane.SYSTEM.value)
    silent_start = FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE
    dropped_start = 2 * FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE
    span = FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE
    assert body[silent_start : silent_start + span] == b"\x00" * span
    assert body[dropped_start : dropped_start + span] == b"\x00" * span
    assert [(gap.start_sample, gap.end_sample) for gap in tape.gaps(LiveLane.SYSTEM.value)] == [
        (2 * FRAME_SAMPLES, 3 * FRAME_SAMPLES)
    ]


def test_the_two_lanes_and_the_mixed_track_are_independent(tmp_path):
    """Three tracks, ~0.3 GB/hr; the mixed track is teed from the mixer's sealed intervals."""

    store = _store(tmp_path)
    tape = store.create("session-a")

    tape.append_lane_frame(_frame(0, lane=LiveLane.SYSTEM))
    tape.append_lane_frame(_frame(0, lane=LiveLane.MICROPHONE))
    tape.append_lane_frame(_frame(1, lane=LiveLane.MICROPHONE))
    tape.append_mixed(
        pcm=_pcm(99),
        start_timestamp_ns=ORIGIN_NS,
        sample_count=FRAME_SAMPLES,
    )

    assert tape.read_track(LiveLane.SYSTEM.value) == _expected({0})
    assert tape.read_track(LiveLane.MICROPHONE.value) == _expected({0, 1})
    assert tape.read_track(MIXED_TRACK) == _pcm(99)
    assert set(tape.manifest()["tracks"]) == {
        LiveLane.SYSTEM.value,
        LiveLane.MICROPHONE.value,
        MIXED_TRACK,
    }


def test_a_skipped_mixer_interval_leaves_a_gap_rather_than_a_splice(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a")

    tape.append_mixed(pcm=_pcm(0), start_timestamp_ns=ORIGIN_NS, sample_count=FRAME_SAMPLES)
    tape.append_mixed(
        pcm=_pcm(2),
        start_timestamp_ns=ORIGIN_NS + 2 * FRAME_NS,
        sample_count=FRAME_SAMPLES,
    )

    assert [(gap.start_sample, gap.end_sample) for gap in tape.gaps(MIXED_TRACK)] == [
        (FRAME_SAMPLES, 2 * FRAME_SAMPLES)
    ]


# --------------------------------------------------------------------------------------
# ADR-0003 D5 -- storage pressure degrades the tape, never the meeting
# --------------------------------------------------------------------------------------


def test_reaching_the_cap_degrades_the_tape_and_never_raises(tmp_path):
    """D5. The third amendment's governing rule applied to a disk."""

    frame_bytes = FRAME_SAMPLES * PCM16_BYTES_PER_SAMPLE
    store = _store(tmp_path, max_bytes_per_session=frame_bytes * 2 + 1)
    tape = store.create("session-a")

    assert tape.append_lane_frame(_frame(0)).written is True
    assert tape.append_lane_frame(_frame(1)).written is True
    result = tape.append_lane_frame(_frame(2))

    assert result.taping is False and result.written is False
    assert result.degradation is not None
    assert result.degradation.reason == TAPE_CAPACITY_EXHAUSTED
    assert result.degradation.detail["max_bytes"] == frame_bytes * 2 + 1
    assert result.degradation.detail["total_bytes"] == frame_bytes * 2
    # The meeting continues: later frames are refused quietly, with the same reason.
    assert tape.append_lane_frame(_frame(3)).degradation.reason == TAPE_CAPACITY_EXHAUSTED
    assert tape.read_track(LiveLane.SYSTEM.value) == _expected({0, 1})
    assert json.loads(tape.index_path.read_text())["degradation"]["reason"] == TAPE_CAPACITY_EXHAUSTED


def test_a_failing_write_degrades_the_tape_and_never_raises(tmp_path, monkeypatch):
    store = _store(tmp_path)
    tape = store.create("session-a")
    tape.append_lane_frame(_frame(0))

    def _boom(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr("moss_transcribe_diarize.app.live_tape.os.pwrite", _boom)
    result = tape.append_lane_frame(_frame(1))

    assert result.taping is False
    assert result.degradation.reason == TAPE_WRITE_FAILED
    assert "No space left on device" in result.degradation.detail["error"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"sample_rate": 48000},
        {"sample_count": 0},
        {"pcm": b"\x00" * 7},
    ],
)
def test_a_frame_the_tape_cannot_place_degrades_rather_than_raising(tmp_path, kwargs):
    store = _store(tmp_path)
    tape = store.create("session-a")
    payload = {
        "pcm": _pcm(0),
        "start_timestamp_ns": ORIGIN_NS,
        "sample_count": FRAME_SAMPLES,
        "sample_rate": LIVE_SAMPLE_RATE,
    }
    payload.update(kwargs)

    result = tape.append_mixed(**payload)

    assert result.taping is False
    assert result.degradation.reason == TAPE_FRAME_NOT_ADMISSIBLE


def test_an_ended_tape_refuses_further_audio(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a")
    tape.append_lane_frame(_frame(0))
    tape.end()

    result = tape.append_lane_frame(_frame(1))

    assert result.taping is False
    assert result.degradation.reason == TAPE_FRAME_NOT_ADMISSIBLE
    assert tape.read_track(LiveLane.SYSTEM.value) == _expected({0})


# --------------------------------------------------------------------------------------
# ADR-0003 D3/D6 -- the reaper
# --------------------------------------------------------------------------------------


def test_the_zero_ttl_default_deletes_the_tape_when_the_meeting_ends(tmp_path):
    """D3. At the default configuration the PRD's audio clause still holds literally."""

    store = _store(tmp_path)
    tape = store.create("session-a", now=100.0)
    tape.append_lane_frame(_frame(0))
    directory = tape.directory

    store.release("session-a", now=200.0)
    assert directory.exists()

    assert store.reap(now=200.0) == ("session-a",)
    assert not directory.exists()
    assert list(store.root.iterdir()) == []


def test_a_positive_ttl_keeps_the_tape_until_it_elapses(tmp_path):
    store = _store(tmp_path, retention_ttl_seconds=3600.0)
    tape = store.create("session-a", now=100.0)
    tape.append_lane_frame(_frame(0))
    store.release("session-a", now=200.0)

    assert store.reap(now=200.0 + 3599.0) == ()
    assert tape.directory.exists()
    assert store.reap(now=200.0 + 3600.0) == ("session-a",)
    assert not tape.directory.exists()


def test_an_active_session_is_never_reaped(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a", now=100.0)
    tape.append_lane_frame(_frame(0))

    assert store.reap(now=1_000_000.0) == ()
    assert tape.directory.exists()
    # ... and a caller's own liveness list is honoured on top of the store's.
    store.release("session-a", now=200.0)
    assert store.reap(active_session_ids=["session-a"], now=1_000_000.0) == ()
    assert tape.directory.exists()


def test_a_crashed_meetings_tape_is_reaped_at_startup(tmp_path):
    """D6. A TTL that only fires while the process lives is not a retention policy."""

    store = _store(tmp_path)
    tape = store.create("session-a", now=100.0)
    tape.append_lane_frame(_frame(0))
    directory = tape.directory
    del tape, store  # the process dies mid-meeting; `ended_at` is never written

    assert json.loads((directory / TAPE_INDEX_FILENAME).read_text())["ended_at"] is None

    restarted = _store(tmp_path, retention_ttl_seconds=60.0)
    assert restarted.reap(now=os.path.getmtime(directory)) == ()
    assert restarted.reap(now=1_000_000_000_000.0) == ("session-a",)
    assert not directory.exists()


def test_the_reaper_never_deletes_what_it_cannot_read_as_a_tape(tmp_path):
    """A reaper that removes what it does not understand is the worse failure."""

    store = _store(tmp_path)
    stranger = store.root / "not-a-tape"
    stranger.mkdir()
    (stranger / "important.txt").write_text("keep me")
    torn = store.root / "torn"
    torn.mkdir()
    (torn / TAPE_INDEX_FILENAME).write_text("")

    assert store.reap(now=1_000_000_000_000.0) == ()
    assert (stranger / "important.txt").read_text() == "keep me"
    assert torn.exists()


def test_release_ends_the_tape_but_does_not_delete_it(tmp_path):
    store = _store(tmp_path)
    tape = store.create("session-a", now=100.0)
    tape.append_lane_frame(_frame(0))

    released = store.release("session-a", now=250.0)

    assert released is tape
    assert tape.ended_at == 250.0
    assert tape.directory.exists()
    assert json.loads(tape.index_path.read_text())["ended_at"] == 250.0
    assert store.get("session-a") is None
    assert store.release("session-a") is None


# --------------------------------------------------------------------------------------
# The recorder -- the wired side, where D2 and D5 have to hold for the live path
# --------------------------------------------------------------------------------------


class _HostileStore:
    """Every store call fails, the way a full or unmounted disk fails: mid-meeting."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def _fail(self, action: str):
        self.calls.append(action)
        raise OSError(28, "No space left on device")

    def create(self, session_id):  # noqa: ANN001 - stub
        self._fail("create")

    def get(self, session_id):  # noqa: ANN001 - stub
        self._fail("get")

    def release(self, session_id):  # noqa: ANN001 - stub
        self._fail("release")

    def reap(self, *, active_session_ids=()):
        self._fail("reap")


def test_an_undeclared_recorder_is_a_no_op_at_every_call_site(tmp_path):
    """D2. No declared root means the service behaves exactly as it did before the tape.

    Every gate this loop has recorded was measured against a no-tape service, so this is
    what keeps those results meaningful -- and it is the default all the way to create_app.
    """

    recorder = LiveSessionTapeRecorder(None)

    assert recorder.enabled is False
    recorder.create("session-a")
    recorder.append_lane_frame("session-a", _frame(0))
    recorder.append_mixed(
        "session-a", pcm=_pcm(0), start_timestamp_ns=ORIGIN_NS, sample_count=FRAME_SAMPLES
    )
    recorder.release("session-a")

    assert recorder.reap() == ()
    assert list(tmp_path.iterdir()) == []


def test_the_recorder_records_both_lanes_and_the_mixed_track_and_ends_the_tape(tmp_path):
    store = _store(tmp_path)
    recorder = LiveSessionTapeRecorder(store)

    recorder.create("session-a")
    recorder.append_lane_frame("session-a", _frame(0, lane=LiveLane.SYSTEM))
    recorder.append_lane_frame("session-a", _frame(0, lane=LiveLane.MICROPHONE))
    recorder.append_mixed(
        "session-a",
        pcm=_pcm(7),
        start_timestamp_ns=ORIGIN_NS,
        sample_count=FRAME_SAMPLES,
    )
    tape = store.get("session-a")
    assert tape is not None
    assert tape.read_track(LiveLane.SYSTEM.value) == _pcm(0)
    assert tape.read_track(LiveLane.MICROPHONE.value) == _pcm(0)
    assert tape.read_track(MIXED_TRACK) == _pcm(7)
    assert tape.gaps(MIXED_TRACK) == ()

    recorder.release("session-a")

    assert store.get("session-a") is None
    assert json.loads(tape.index_path.read_text())["ended_at"] is not None


def test_no_store_failure_reaches_the_live_path(tmp_path, caplog):
    """D5, at the seam. A disk error that escapes a route ends the meeting with a 500.

    `LiveSessionTape` already promises no *frame* raises; the store's own create/release/
    reap touch a filesystem and can, so the recorder is where the rule is enforced -- and
    it is enforced loudly, because a substrate that vanishes silently is indistinguishable
    from one that was never enabled.
    """

    store = _HostileStore()
    recorder = LiveSessionTapeRecorder(store)

    with caplog.at_level("WARNING", logger="moss_transcribe_diarize.live.tape"):
        recorder.create("session-a")
        recorder.append_lane_frame("session-a", _frame(0))
        recorder.append_mixed(
            "session-a", pcm=_pcm(0), start_timestamp_ns=ORIGIN_NS, sample_count=FRAME_SAMPLES
        )
        recorder.release("session-a")
        assert recorder.reap() == ()

    assert store.calls == ["create", "get", "get", "release", "reap"]
    actions = [record.getMessage() for record in caplog.records]
    assert len(actions) == 5
    assert all("No space left on device" in message for message in actions)


def test_a_frame_for_a_session_with_no_tape_is_ignored(tmp_path):
    """A frame that arrives after release -- or before create ever succeeded -- is not an
    error; it is a session the tape does not have. Only the failure that caused it was."""

    recorder = LiveSessionTapeRecorder(_store(tmp_path))

    recorder.append_lane_frame("session-a", _frame(0))

    assert not (tmp_path / "tape-root" / "session-a").exists()


def test_the_recorder_reaps_a_crashed_meetings_tape(tmp_path):
    """D6 through the wired path: what the service calls at startup is this."""

    store = _store(tmp_path, retention_ttl_seconds=0.0)
    tape = store.create("session-a", now=100.0)
    tape.append_lane_frame(_frame(0))
    directory = tape.directory
    del tape, store

    restarted = LiveSessionTapeRecorder(_store(tmp_path, retention_ttl_seconds=0.0))

    assert restarted.reap() == ("session-a",)
    assert not directory.exists()
