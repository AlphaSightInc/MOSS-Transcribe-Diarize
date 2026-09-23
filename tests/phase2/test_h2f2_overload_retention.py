"""A rejected production inference projection must leave content-free overload evidence."""

import json
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize import phase2_acceptance_external as external


@pytest.mark.parametrize("counter", ["windows_failed", "stale_completions"])
def test_overload_retains_the_reducer_check_and_counter_without_changing_failure(
    tmp_path, monkeypatch, counter
):
    repo = tmp_path / "repo"
    fixture = repo / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(json.dumps({"audio": {"path": "unused.wav"}, "clips": [
        {"start_seconds": 0, "end_seconds": 1, "expected_marker": "first"},
        {"start_seconds": 1, "end_seconds": 2, "expected_marker": "second"},
    ]}))
    for name in ("a.cookie", "b.cookie", "a.sentinel", "b.sentinel"):
        (tmp_path / name).write_text(name)
    campaign = external.FixedAccountCampaign(candidate_sha="a" * 40, config={
        "campaign_work_dir": str(tmp_path / "campaign"), "repo_root": str(repo),
        "https_origin": "https://fixture.test", "account_a_cookie_file": str(tmp_path / "a.cookie"),
        "account_b_cookie_file": str(tmp_path / "b.cookie"),
        "account_a_sentinel_file": str(tmp_path / "a.sentinel"),
        "account_b_sentinel_file": str(tmp_path / "b.sentinel"),
        "vllm_metrics_url": "https://metrics.invalid",
    })

    class Event:
        def __init__(self, seq, row):
            self.seq = seq
            self.row = row
        def to_dict(self):
            return self.row

    class Adapter:
        serial = 0
        def __init__(self, **kwargs): pass
        def descriptor(self): return SimpleNamespace(frame_samples=8000)
        def create(self):
            Adapter.serial += 1
            self.session_id = f"opaque-session-{Adapter.serial}"
            return SimpleNamespace(session_id=self.session_id, snapshot=SimpleNamespace(pending_work_items=0))
        def accept_frame(self, *args): return SimpleNamespace(snapshot=SimpleNamespace(pending_work_items=0))
        async def stop(self, *args):
            return SimpleNamespace(session=SimpleNamespace(accepted_samples=8000, accounted_samples=8000,
                effective_transcript=(SimpleNamespace(text="first second"),), finalization_status="final"))
        def events(self, session_id, *, since_seq):
            bad = session_id.endswith("1")
            checks = {"windows_failed": 0, "stale_completions": 0}
            if bad:
                checks[counter] = 1
            rows = [
                {"kind": "canonical_processed", "session_id": session_id,
                 "payload": {"item_id": 1, "canonical_decode_elapsed_sec": 0.1,
                             "runtime_monotonic_ns": 0, "committed_samples": 8000}},
                {"kind": "rolling_decode_queued", "session_id": session_id,
                 "payload": {"item_id": 2, "admitted": True, "end_sample": 8000}},
                {"kind": "rolling_decode_completed", "session_id": session_id,
                 "payload": {"item_id": 2, "outcome": "applied", "decode_failure": None,
                             "rolling_decode_elapsed_sec": 0.1, "end_sample": 8000, **checks}},
            ]
            return [Event(seq, row) for seq, row in enumerate(rows) if seq >= since_seq]
        async def abort(self, *args): pass

    class Response:
        status_code = 404
        content = b""
        def json(self): return {"detail": {}}

    class Client:
        def __init__(self, *args, **kwargs): pass
        def request(self, *args, **kwargs): return Response()
        def json(self, *args, **kwargs): return {"snapshot": {"session": {"status": "active"}}}, None
        def close(self): pass

    class Journal:
        def __init__(self, *args): pass
        def read(self): return b""

    class Backpressure:
        def __init__(self, *args): pass
        def accept(self, index, adapter, session_id, frame):
            return adapter.accept_frame(session_id, frame).snapshot
        def observation(self): return {"observed_429": True, "peer_progress": True, "same_sequence_retry": True}

    monkeypatch.setattr(campaign, "_replay_service", lambda **kwargs: Adapter())
    monkeypatch.setattr(campaign, "_journal_window", Journal)
    monkeypatch.setattr(external, "AccountHttpClient", Client)
    monkeypatch.setattr(external, "_CampaignBackpressure", Backpressure)
    monkeypatch.setattr(external, "_wav_pcm_clip", lambda *args: b"\0" * 16000)
    monkeypatch.setattr(external, "_unit_pid", lambda *args: 1)
    monkeypatch.setattr(external, "_process_tree_rss", lambda *args: 0)
    monkeypatch.setattr(external, "_vllm_cache_use", lambda *args: 0.0)
    campaign._clients["a"] = Client()
    campaign._clients["b"] = Client()

    with pytest.raises(ValueError, match=f"rolling completion has invalid {counter}"):
        campaign._run_live_load(sessions=2, duration_seconds=0.5, embedded_backpressure=True)
    path = tmp_path / "campaign/overload/prestop-inference-failure.json"
    record = json.loads(path.read_text())
    assert path.relative_to(tmp_path / "campaign") in campaign.safe_artifacts
    assert record["failure_check"] == f"rolling completion has invalid {counter}"
    assert record["accepted_audio_seconds"] == 1.0
    assert {row["session_id"] for row in record["sessions"]} == {
        "opaque-session-1", "opaque-session-2"}
    assert all(row["canonical_processed"] == row["rolling_admitted"] ==
               row["rolling_completed"] == 1 for row in record["sessions"])
    assert all(row["accepted_samples"] == row["prestop_frontier_samples"] == 8000
               for row in record["sessions"])
    bad = next(row for row in record["sessions"] if row["session_id"] == "opaque-session-1")
    assert bad["rolling_counter_checks"][0][counter]["value"] == 1
    assert "first second" not in path.read_text()
