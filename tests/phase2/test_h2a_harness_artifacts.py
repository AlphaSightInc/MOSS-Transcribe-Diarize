"""Two production live-load predicates share one append-only campaign directory."""
import json
from types import SimpleNamespace

from moss_transcribe_diarize import phase2_acceptance_external as external


def test_capacity_then_overload_keeps_each_artifact_in_one_campaign(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    fixture = repo / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json"
    fixture.parent.mkdir(parents=True)
    fixture.write_text(json.dumps({"audio": {"path": "unused.wav"}, "clips": [
        {"start_seconds": 0, "end_seconds": 1, "expected_marker": "first"},
        {"start_seconds": 1, "end_seconds": 2, "expected_marker": "second"},
    ]}))
    for name in ("a.cookie", "b.cookie", "a.sentinel", "b.sentinel", "web.log", "vllm.log"):
        (tmp_path / name).write_text(name)
    campaign = external.FixedAccountCampaign(candidate_sha="a" * 40, config={
        "campaign_work_dir": str(tmp_path / "campaign"), "repo_root": str(repo),
        "https_origin": "https://fixture.test", "account_a_cookie_file": str(tmp_path / "a.cookie"),
        "account_b_cookie_file": str(tmp_path / "b.cookie"),
        "account_a_sentinel_file": str(tmp_path / "a.sentinel"),
        "account_b_sentinel_file": str(tmp_path / "b.sentinel"),
        "vllm_metrics_url": "https://metrics.invalid",
    })

    class Adapter:
        serial = 0
        def __init__(self, **kwargs): pass
        def descriptor(self): return SimpleNamespace(frame_samples=8000)
        def create(self):
            Adapter.serial += 1
            return SimpleNamespace(session_id=f"session-{Adapter.serial}", snapshot=SimpleNamespace(pending_work_items=0))
        def accept_frame(self, *args): return SimpleNamespace(snapshot=SimpleNamespace(pending_work_items=0))
        async def stop(self, *args):
            return SimpleNamespace(session=SimpleNamespace(accepted_samples=8000, accounted_samples=8000,
                effective_transcript=(SimpleNamespace(text="first second"),), finalization_status="final"))
        def events(self, *args, **kwargs): return []
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
        def observation(self): return {"read_succeeded": True}
    class Backpressure:
        def __init__(self, *args): pass
        def accept(self, index, adapter, session_id, frame): return adapter.accept_frame(session_id, frame).snapshot
        def observation(self): return {"observed_429": True, "peer_progress": True, "same_sequence_retry": True}
    monkeypatch.setattr(campaign, "_replay_service", lambda **kwargs: Adapter())
    monkeypatch.setattr(campaign, "_journal_window", Journal)
    monkeypatch.setattr(external, "AccountHttpClient", Client)
    monkeypatch.setattr(external, "_CampaignBackpressure", Backpressure)
    monkeypatch.setattr(external, "_wav_pcm_clip", lambda *args: b"\0" * 16000)
    monkeypatch.setattr(external, "_unit_pid", lambda *args: 1)
    monkeypatch.setattr(external, "_process_tree_rss", lambda *args: 0)
    monkeypatch.setattr(external, "_vllm_cache_use", lambda *args: 0.0)
    monkeypatch.setattr(external, "prestop_inference_projection", lambda *args, **kwargs: {"rtf": 0.0})
    monkeypatch.setattr(external, "canonical_lifecycle_fairness", lambda *args, **kwargs: {
        "passes": True, "applicability": "measured", "maximum_contended_pair_dispatch_skew": 0})
    campaign._clients["a"] = Client()
    campaign._clients["b"] = Client()

    capacity = campaign._run_live_load(sessions=2, duration_seconds=0.5)
    overload = campaign._run_live_load(sessions=2, duration_seconds=0.5, embedded_backpressure=True)
    assert capacity["sessions"] == overload["sessions"] == 2
    relative = {path.as_posix() for path in campaign.safe_artifacts}
    assert {"load-2/session-1-events.json", "load-2/session-2-events.json",
            "capacity-2/observations.json", "overload/load-2/session-1-events.json",
            "overload/load-2/session-2-events.json", "overload/load-2/backpressure-observation.json",
            "overload/capacity-2/observations.json"} <= relative
