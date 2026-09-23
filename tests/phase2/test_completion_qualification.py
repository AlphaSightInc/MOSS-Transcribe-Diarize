from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize import phase2_acceptance as acceptance
from moss_transcribe_diarize.phase2_acceptance_collect import collect_layer
from moss_transcribe_diarize.phase2_acceptance_measure import measure_layer
from moss_transcribe_diarize.phase2_acceptance_completion import (
    SUMMARY_CHECKS, VOICEPRINT_CHECKS, RELAY_SUMMARY_CHECKS, measure_voiceprint_workspace, validate_completion_observation,
)
from moss_transcribe_diarize.phase2_acceptance_summary import _record_summary_result
from tests.phase2.test_wave1_qualification import _capacity_raw, _overload_raw
from tests.phase2.test_owner_bound_live_meeting import EligibleIdentity, make_app, provision, session, feed_two_lane_span, wait_snapshot


def rule_report():
    results = {}
    for name, total, correct in (("causal", 470, 441), ("terminal_truth_aligned", 14, 14)):
        rows = [{"id": str(i), "truth": "p", "known": "p" if i < correct else None, "unknown": None, "seconds": 1.0} for i in range(total)]
        results[name] = {"observations": rows, "counts": {"total": total, "known_correct": correct, "known_abstain": total-correct,
            "known_wrong": 0, "unknown_abstain": total, "unknown_false": 0}}
    return {"fresh_embeddings": True, "production_rule": True, "model_sha256": "5b734353b4b410e222bbd124dd095537642237ad895727d18a3b9fee330262a8",
            "profiles": 5, "enrollment_samples": 14, "results": results}


def _two_meeting_overload_raw():
    raw = _overload_raw()
    raw["sessions"] = 2
    raw["session_observations"] = raw["session_observations"][:2]
    raw["wrong_owner_observations"] = [
        item
        for item in raw["wrong_owner_observations"]
        if item["session_ordinal"] <= 2
    ]
    raw["backpressure_observation"]["campaign_session_ordinals"] = [1, 2]
    events = sorted(
        (
            {
                "session_id": str(session["session_ordinal"]),
                "kind": event["kind"],
                "payload": {
                    key: value for key, value in event.items() if key != "kind"
                },
            }
            for session in raw["session_observations"]
            for event in session["events"]
            if event["kind"].startswith("canonical_")
        ),
        key=lambda event: event["payload"]["runtime_monotonic_ns"],
    )
    fairness = acceptance.canonical_lifecycle_fairness(
        events, {"1", "2"}, maximum_skew=1
    )
    raw["fairness_observation"] = fairness
    raw["dispatch_skew"] = fairness["maximum_contended_pair_dispatch_skew"]
    raw["admission_observation"] = {
        "accepted_sessions": 2,
        "excess_attempts": 1,
        "excess_status": 409,
        "refusal_code": "live_capacity_full",
        "accepted_active_after_refusal": True,
    }
    return raw


def test_overload_retains_two_accepted_meetings_and_refuses_excess_admission():
    raw = _two_meeting_overload_raw()
    assert acceptance._validate_overload({"raw": raw})
    for key, value in (
        ("accepted_sessions", 1),
        ("excess_attempts", 0),
        ("excess_status", 201),
        ("refusal_code", "wrong"),
        ("accepted_active_after_refusal", False),
    ):
        invalid = copy.deepcopy(raw)
        invalid["admission_observation"][key] = value
        assert not acceptance._validate_overload({"raw": invalid}), key


@pytest.mark.parametrize("mutation", ["missing_unknown", "missing_known", "cached", "wrong_name", "unknown_false", "wrong_count", "duplicate", "missing_surface"])
def test_g8_rule_requires_explicit_measured_observations(mutation):
    raw = rule_report()
    assert validate_completion_observation("voiceprint_production_rule", raw)
    rows = raw["results"]["causal"]["observations"]
    if mutation == "missing_unknown":
        for row in rows: del row["unknown"]
    elif mutation == "missing_known": del rows[-1]["known"]
    elif mutation == "cached": raw["fresh_embeddings"] = False
    elif mutation == "wrong_name": rows[0]["known"] = "foreign"
    elif mutation == "unknown_false": rows[0]["unknown"] = "foreign"
    elif mutation == "wrong_count": raw["results"]["causal"]["counts"]["total"] = 469
    elif mutation == "duplicate": rows[-1]["id"] = rows[0]["id"]
    else: del raw["results"]["terminal_truth_aligned"]
    assert not validate_completion_observation("voiceprint_production_rule", raw)


def summary_report():
    return {"relay": {"checks": {key: True for key in RELAY_SUMMARY_CHECKS}, "upstream_requests": 1}, "checks": {key: True for key in SUMMARY_CHECKS}, "capacity": _capacity_raw(), "retry_deliveries": [0, 60, 180, 420],
        "events": [[{"type": "llm_status", "state": value} for value in ("queued", "generating", "retry_wait", "failed", "cancelled", "current")],
                   [{"type": "llm_summary_update", "state": "current"}]]}


def test_g9_failure_retains_content_free_check_identity(tmp_path: Path):
    class Campaign:
        def _artifact_json(self, relative, payload):
            target = tmp_path / relative
            target.write_text(json.dumps(payload))

    raw = summary_report()
    raw["checks"]["lifecycle_events"] = False
    with pytest.raises(RuntimeError, match="Browser summary privacy/lifecycle/load qualification failed"):
        _record_summary_result(Campaign(), raw)
    retained = json.loads((tmp_path / "summary-checks.json").read_text())
    assert retained == {"checks": raw["checks"], "validator_pass": False, "diagnostics": {}}

    raw["checks"]["lifecycle_events"] = True
    assert _record_summary_result(Campaign(), raw) is raw
    retained = json.loads((tmp_path / "summary-checks.json").read_text())
    assert retained == {"checks": raw["checks"], "validator_pass": True, "diagnostics": {}}


def test_completion_boolean_claims_cannot_replace_missing_rows_timings_or_capacity():
    raw = summary_report()
    assert validate_completion_observation("browser_final_summary", raw)
    for key in SUMMARY_CHECKS:
        invalid = copy.deepcopy(raw); invalid["checks"][key] = False
        assert not validate_completion_observation("browser_final_summary", invalid), key
        del invalid["checks"][key]
        assert not validate_completion_observation("browser_final_summary", invalid), key
    for key in ("capacity", "events", "retry_deliveries", "relay"):
        invalid = copy.deepcopy(raw); del invalid[key]
        assert not validate_completion_observation("browser_final_summary", invalid)
    invalid = copy.deepcopy(raw); invalid["retry_deliveries"] = [0, 0, 0, 0]
    assert not validate_completion_observation("browser_final_summary", invalid)
    for value in (float("nan"), float("inf"), -float("inf"), True):
        invalid = copy.deepcopy(raw); invalid["retry_deliveries"] = [value] * 4
        assert not validate_completion_observation("browser_final_summary", invalid)
    invalid = copy.deepcopy(raw); invalid["capacity"]["session_observations"] = []
    assert not validate_completion_observation("browser_final_summary", invalid)
    invalid = copy.deepcopy(raw); invalid["events"] = [[], []]
    assert not validate_completion_observation("browser_final_summary", invalid)
    for key in VOICEPRINT_CHECKS:
        invalid = {"checks": {name: True for name in VOICEPRINT_CHECKS if name != key}}
        assert not validate_completion_observation("voiceprint_workspace_behavior", invalid)


def test_wave_catalog_collects_missing_completion_evidence_as_unmeasured(tmp_path: Path):
    assert "G8" not in acceptance.external_requirements("deployed", 1)
    assert "G9" not in acceptance.external_requirements("deployed", 2)
    raw = tmp_path / "new" / "raw"
    result = measure_layer(layer="deployed", candidate_sha="a"*40, config={}, raw_dir=raw, wave=3)
    assert result["qualified"] is False
    collected = collect_layer(layer="deployed", candidate_sha="a"*40, raw_dir=raw, wave=3)
    completion = [row for row in collected["predicates"] if row["gate"] in {"G8", "G9"}]
    assert {row["id"] for row in completion} == {"voiceprint_production_rule", "voiceprint_workspace_behavior", "browser_final_summary"}
    assert all(row["counts"]["unmeasured"] == 1 for row in completion)
    all_gates = {gate: True for gate in acceptance.required_gates(3)}
    assert acceptance._final_gate_table(identity_errors=[], deterministic=all_gates, deployed=all_gates, pre_admission=all_gates, wave=3)["passed"]
    for layer in ("deterministic", "deployed", "pre_admission"):
        values = {name: dict(all_gates) for name in ("deterministic", "deployed", "pre_admission")}
        del values[layer]["G9"]
        assert not acceptance._final_gate_table(identity_errors=[], wave=3, **values)["passed"]


def test_g8_http_collector_handles_empty_name_map_and_same_name_neighbor(tmp_path: Path):
    counter = 0
    class DistinctIdentity(EligibleIdentity):
        def __init__(self, vector): self.vector = vector
        def journal_observations(self):
            row = super().journal_observations()[0]; row.centroid = self.vector; return (row,)
        def match_observations(self, *, base_snapshot):
            return self.journal_observations() if base_snapshot.canonical_speakers else ()
    def factory():
        nonlocal counter
        counter += 1
        return DistinctIdentity((-.8, .6) if counter == 3 else (.6, .8))
    db = tmp_path / "db"
    credentials = asyncio.run(provision(db))
    app = make_app(db, identity_factory=factory)
    with TestClient(app, base_url="https://moss.test") as client:
        app.state.phase2_live.runtime._voiceprint_embedder_identity = ("wespeaker:test-revision", 2)
        class OwnerClient:
            def __init__(self, owner): self.owner = owner
            def request(self, method, path, **kwargs):
                session(client, credentials[self.owner]); return client.request(method, path, **kwargs)
            def json(self, method, path, expected, **kwargs):
                response = self.request(method, path, **kwargs)
                assert response.status_code == expected, response.text
                return response.json(), response
        registered = set()
        def new_live(owner):
            value, _ = OwnerClient(owner).json("POST", "/api/live/sessions", 201, json={"echo_mode": "speakers"})
            registered.add(value["id"])
            return value["id"]
        def seed(owner, meeting, index):
            assert meeting in registered, "seed requires campaign-owned helper registration"
            assert index == (1 if counter == 3 else 0)
            session(client, credentials[owner]); feed_two_lane_span(client, meeting)
            wait_snapshot(client, meeting, lambda body: body["meeting_transcript_version"] >= 1)
        campaign = SimpleNamespace(a=OwnerClient("a"), b=OwnerClient("b"), a_peer=OwnerClient("a"), _seed_live_transcript=seed, _new_live_id=new_live)
        raw = measure_voiceprint_workspace(campaign)
        assert validate_completion_observation("voiceprint_workspace_behavior", raw)
        assert raw["live_meetings"] == 3
        assert campaign.a.json("GET", "/api/voiceprints", 200)[0] == {"voiceprints": []}


def test_summary_relay_evidence_is_required_and_falsifiable():
    for key in RELAY_SUMMARY_CHECKS:
        raw = summary_report()
        raw["relay"]["checks"][key] = False
        assert not validate_completion_observation("browser_final_summary", raw)
    raw = summary_report()
    raw["relay"]["upstream_requests"] = 0
    assert not validate_completion_observation("browser_final_summary", raw)
