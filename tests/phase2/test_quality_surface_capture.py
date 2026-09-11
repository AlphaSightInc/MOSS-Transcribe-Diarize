from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest
from moss_transcribe_diarize.phase2_acceptance_external import _load_surface_harness
from moss_transcribe_diarize.live_service_replay import ServiceReplayFailure


def snapshot(finalization="not_started", pending=0):
    session = SimpleNamespace(status="active", finalization_status=finalization,
        accepted_samples=160000, accounted_samples=160000, effective_transcript=())
    return SimpleNamespace(session=session, pending_work_items=pending,
        to_dict=lambda: {"session": {"finalization_status": finalization}})


@pytest.fixture
def harness(monkeypatch):
    module = _load_surface_harness(Path(__file__).resolve().parents[2])
    clock = SimpleNamespace(now=0.0)
    def sleep(seconds):
        clock.now += seconds
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock.now,
        monotonic_ns=lambda: int(clock.now * 1e9), sleep=sleep))
    return module, clock


class Service:
    def __init__(self, clock, completes=True, terminal="final"):
        self.clock, self.completes, self.terminal = clock, completes, terminal
        self.stopped = False
    def snapshot(self, session_id, since_version=None):
        return snapshot(self.terminal if self.stopped else "not_started")
    def events(self, session_id, since_seq=0):
        rows = [SimpleNamespace(seq=0, kind="rolling_decode_queued", payload={"item_id": 4, "admitted": True})]
        if self.completes and self.clock.now >= 1:
            rows.append(SimpleNamespace(seq=1, kind="rolling_decode_completed", payload={"item_id": 4}))
        return tuple(row for row in rows if row.seq >= since_seq)
    async def stop(self, session_id, deadline):
        self.stopped = True
        return self.snapshot(session_id)


def test_settle_waits_for_rolling_even_when_canonical_queue_is_empty(harness):
    module, clock = harness
    service = Service(clock)
    capture = module.SurfaceCaptureService(service, settle_timeout=3, poll_seconds=.25)
    # Replay already consumed the queued event; subsequent reads must not lose it.
    capture.events("meeting")
    asyncio.run(capture.stop("meeting", 5))
    wait = capture.captures["pre_stop_settled"]["wait"]
    assert wait["polls"] == 4
    assert wait["drained"] is True
    assert clock.now == 1
    assert service.stopped


def test_settle_timeout_raises_without_capture_or_stop(harness):
    module, clock = harness
    service = Service(clock, completes=False)
    capture = module.SurfaceCaptureService(service, settle_timeout=.5, poll_seconds=.25)
    with pytest.raises(ServiceReplayFailure, match="settle.*timed out"):
        asyncio.run(capture.stop("meeting", 5))
    assert "pre_stop_settled" not in capture.captures
    assert not service.stopped


@pytest.mark.parametrize("state", ["failed", "unavailable", "not_started"])
def test_final_capture_refuses_unsuccessful_terminal_states(harness, state):
    module, _ = harness
    capture = module.SurfaceCaptureService(None, settle_timeout=3, poll_seconds=.25)
    with pytest.raises(ServiceReplayFailure, match="final.*" + state):
        capture._capture("post_stop_final", snapshot(state))
    assert "post_stop_final" not in capture.captures


def test_successful_final_capture_is_retained(harness):
    module, _ = harness
    capture = module.SurfaceCaptureService(None, settle_timeout=3, poll_seconds=.25)
    capture._capture("post_stop_final", snapshot("final"))
    assert capture.captures["post_stop_final"]["snapshot"]["session"]["finalization_status"] == "final"


def test_settled_snapshot_is_refreshed_after_observing_rolling_completion(harness):
    module, clock = harness
    class CompletingService(Service):
        applied = False
        def snapshot(self, session_id, since_version=None):
            value = super().snapshot(session_id, since_version)
            revision = int(self.applied)
            value.to_dict = lambda: {"session": {"text_revision_version": revision}}
            return value
        def events(self, session_id, since_seq=0):
            events = super().events(session_id, since_seq)
            if any(event.kind == "rolling_decode_completed" for event in events):
                self.applied = True
            return events
    capture = module.SurfaceCaptureService(CompletingService(clock), settle_timeout=3, poll_seconds=.25)
    asyncio.run(capture.stop("meeting", 5))
    assert capture.captures["pre_stop_settled"]["snapshot"]["session"]["text_revision_version"] == 1


@pytest.mark.parametrize("state", ["failed", "unavailable"])
def test_failed_finalization_returned_by_stop_is_rejected(harness, state):
    module, clock = harness
    capture = module.SurfaceCaptureService(Service(clock, terminal=state), settle_timeout=3, poll_seconds=.25)
    with pytest.raises(ServiceReplayFailure, match="final.*" + state):
        asyncio.run(capture.stop("meeting", 5))
    assert "post_stop_final" not in capture.captures


@pytest.mark.parametrize("failure", ["settle_timeout", "nonfinal_stop"])
def test_strict_capture_failure_aborts_through_real_replay(harness, tmp_path, failure):
    from moss_transcribe_diarize.live_service_replay import run_service_replay
    from tests.test_live_service_replay import (
        RecordingService, ScriptedClock, _descriptor, _runtime, _write_wav,
    )
    module, _ = harness
    descriptor = _descriptor(frame_samples=400)
    inner = RecordingService(_runtime(
        descriptor=descriptor, speech=(False,), session_ids=("strict-capture",),
    ))
    capture = module.SurfaceCaptureService(inner, settle_timeout=0, poll_seconds=.25)
    if failure == "settle_timeout":
        # An admitted rolling item still pending after canonical work drained.
        capture._pending_rolling.add(42)
    audio = tmp_path / 'input.wav'
    _write_wav(audio, samples=400)
    clock = ScriptedClock()
    with pytest.raises(ServiceReplayFailure, match="settle timed out|final capture requires"):
        run_service_replay(
            service=capture, audio_path=audio, out_dir=tmp_path/'out', pace=1.0,
            max_pacing_lag=.5, runs=1, expect_revision=descriptor.source_revision,
            expect_provider_hash=descriptor.provider_manifest_hash,
            expect_config_hash=descriptor.config_hashes.combined_config_hash,
            monotonic=clock.monotonic, sleep=clock.sleep,
        )
    assert len(inner.abort_reasons) == 1
    assert inner.snapshot("strict-capture").session.status in {"aborted", "closed"}
    assert "post_stop_final" not in capture.captures


@pytest.mark.parametrize('surface', ['pre_stop_immediate', 'pre_stop_settled', 'post_stop_final'])
def test_quality_capture_scores_identically_with_reader_only_draft(harness, surface):
    from dataclasses import replace
    from tests.test_live_service_replay import _rich_service_snapshot
    module, _ = harness
    with_draft = _rich_service_snapshot()
    if surface == 'post_stop_final':
        with_draft = replace(with_draft, session=replace(with_draft.session, finalization_status='final'))
    without_draft = replace(with_draft, draft=None, draft_stats=None)
    captures = []
    for value in (without_draft, with_draft):
        capture = module.SurfaceCaptureService(None, settle_timeout=3, poll_seconds=.25)
        capture._capture(surface, value)
        captures.append(module.transcript_rows(capture.captures[surface]['snapshot'], 2.5))
    assert captures[0]  # Non-empty canonical evidence, not a vacuous empty comparison.
    assert captures[0] == captures[1]
    assert all(row['text'] != 'draft' for row in captures[1])
