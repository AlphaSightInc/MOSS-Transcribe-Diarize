"""Resumable Stop must settle before capacity samples its admitted/completed ledger."""
import asyncio
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize import phase2_acceptance_replay as replay
from moss_transcribe_diarize.concurrency_evidence import prestop_inference_projection


def snapshot(status, finalization):
    return SimpleNamespace(session=SimpleNamespace(status=status, finalization_status=finalization))


@pytest.mark.parametrize("terminal_status", ["closed", "failed", "aborted"])
def test_accepted_stop_waits_for_publication_before_forgetting_session(monkeypatch, terminal_status):
    adapter = object.__new__(replay.AccountCookieLiveReplayService)
    adapter._timeout_seconds = 300
    adapter.stop_observations = {}
    clock = [0.0]
    monkeypatch.setattr(replay.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(replay, "_snapshot_from_dict", lambda value: value)
    async def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr(replay.asyncio, "sleep", sleep)
    polls = iter([snapshot("closing", "not_started"), snapshot("closed", "running"), snapshot(terminal_status, "final")])
    forgotten = []
    requests = []
    def request(method, path, payload=None, **kwargs):
        requests.append((method, payload, kwargs))
        assert not forgotten
        if method == "POST":
            return {"code": "stop_in_progress", "snapshot": snapshot("closing", "not_started")}
        return {"snapshot": next(polls)}
    adapter._json = request
    adapter._forget = forgotten.append
    result = asyncio.run(adapter.stop("session", 5.0))
    assert result.session.status == terminal_status
    assert requests[0] == ("POST", {"deadline": 5.0}, {})
    assert len(requests) == 4
    assert forgotten == ["session"]
    assert adapter.stop_observations["session"]["polls"] == 3
    assert adapter.stop_observations["session"]["settled"] is True
    assert adapter.stop_observations["session"]["wait_seconds"] == .5


def test_pending_stop_times_out_without_claiming_completion(monkeypatch):
    adapter = object.__new__(replay.AccountCookieLiveReplayService)
    adapter._timeout_seconds = .5
    adapter.stop_observations = {}
    clock = [0.0]
    monkeypatch.setattr(replay.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(replay, "_snapshot_from_dict", lambda value: value)
    async def sleep(seconds):
        clock[0] += seconds
    monkeypatch.setattr(replay.asyncio, "sleep", sleep)
    adapter._json = lambda *args, **kwargs: {"code": "stop_in_progress", "snapshot": snapshot("closing", "not_started")}
    adapter._forget = lambda _: pytest.fail("unfinished session was forgotten")
    with pytest.raises(replay.AccountReplayTransportFailure, match="observation deadline") as error:
        asyncio.run(adapter.stop("session", 5.0))
    assert error.value.http_status == 202
    assert adapter.stop_observations["session"]["settled"] is False
    assert adapter.stop_observations["session"]["wait_seconds"] == .5


def test_four_resumable_stops_close_the_rolling_ledger_before_measurement(monkeypatch):
    monkeypatch.setattr(replay, "_snapshot_from_dict", lambda value: value)
    events = []
    def event(session_id, kind, **payload):
        return {"session_id": session_id, "kind": kind, "payload": payload}
    async def exercise():
        for ordinal in range(4):
            sid = str(ordinal)
            events.extend([
                event(sid, "canonical_processed", item_id=1, canonical_decode_elapsed_sec=.1),
                event(sid, "rolling_decode_queued", item_id=2, admitted=True),
            ])
            adapter = object.__new__(replay.AccountCookieLiveReplayService)
            adapter._timeout_seconds = 300
            adapter.stop_observations = {}
            adapter._forget = lambda _: None
            def request(method, path, payload=None, **kwargs):
                if method == "POST":
                    with pytest.raises(ValueError, match="accounting is incomplete"):
                        prestop_inference_projection(events, accepted_audio_seconds=600 * (ordinal + 1))
                    return {"code": "stop_in_progress", "snapshot": snapshot("closing", "not_started")}
                events.append(event(sid, "rolling_decode_completed", item_id=2, outcome="applied",
                    decode_failure=None, windows_failed=0, stale_completions=0, rolling_decode_elapsed_sec=.2))
                return {"snapshot": snapshot("closed", "final")}
            adapter._json = request
            await adapter.stop(sid, 5.0)
    asyncio.run(exercise())
    result = prestop_inference_projection(events, accepted_audio_seconds=2400)
    assert result["rolling_completed_items"] == 4
    assert result["canonical_processed_items"] == 4


def test_a_window_the_session_stopped_awaiting_closes_its_admission_without_compute():
    """WP35: Stop ends rolling, so a queued window is dispatched and refused, not decoded.

    It still has to close the admission the §7.4 accounting opened -- otherwise every meeting
    with a terminal pass would read as an incomplete ledger -- and it must contribute nothing
    to the pre-Stop projection, because nothing was decoded and every measurement is null.
    """

    def event(session_id, kind, **payload):
        return {"session_id": session_id, "kind": kind, "payload": payload}

    events = [
        event("s", "canonical_processed", item_id=1, canonical_decode_elapsed_sec=.1),
        event("s", "rolling_decode_queued", item_id=2, admitted=True),
        event("s", "rolling_decode_completed", item_id=2, outcome="applied", decode_failure=None,
              windows_failed=0, stale_completions=0, rolling_decode_elapsed_sec=.2),
        event("s", "rolling_decode_queued", item_id=3, admitted=True),
        event("s", "rolling_decode_completed", item_id=3, outcome="not_awaited",
              decode_failure=None, windows_failed=None, stale_completions=None,
              rolling_decode_elapsed_sec=None),
    ]
    result = prestop_inference_projection(events, accepted_audio_seconds=600)
    assert result["rolling_completed_items"] == 2
    assert result["rolling_decode_seconds"] == pytest.approx(.2)
    assert result["decode_seconds"] == pytest.approx(.3)


def test_load_event_capture_rejects_ring_overrun_instead_of_scoring_partial_history():
    from moss_transcribe_diarize.phase2_acceptance_external import _LoadEventCapture, ExternalMeasurementError
    capture = _LoadEventCapture()
    adapter = SimpleNamespace(events=lambda session_id, since_seq: [SimpleNamespace(seq=7)])
    with pytest.raises(ExternalMeasurementError, match="expected seq=0, observed=7"):
        capture.read(adapter, "session")
    assert capture.events == []
