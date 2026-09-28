from __future__ import annotations

import copy
import json

from moss_transcribe_diarize import phase2_acceptance as acceptance
from moss_transcribe_diarize import phase2_acceptance_summary as summary
from tests.phase2.test_wave1_qualification import _capacity_raw


def _provider_body():
    return {
        "model": "g9-model-a",
        "stream": False,
        "response_format": {"type": "json_object"},
        "max_tokens": 2048,
        "messages": [
            {"role": "system", "content": "private prompt A"},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "segments": [
                            {
                                "source_lane": "system",
                                "start": "00:00:00",
                                "end": "00:00:04",
                                "speaker": "Speaker TBD",
                                "text": "synthetic owner A speech",
                            },
                            {
                                "source_lane": "microphone",
                                "start": "00:00:01",
                                "end": "00:00:03",
                                "speaker": "Alex",
                                "text": "synthetic owner A speech",
                            },
                        ]
                    }
                ),
            },
        ],
    }


def _source():
    return {
        "transcript": {
            "segments": [
                {
                    "start": 1.5,
                    "end": 3.5,
                    "speaker": "Alex",
                    "source_lane": "microphone",
                    "text": "synthetic owner A speech",
                },
                {
                    "start": 0.25,
                    "end": 4.75,
                    "speaker": "S00",
                    "source_lane": "system",
                    "text": "synthetic owner A speech",
                },
            ]
        }
    }


def test_g9_owner_payload_accepts_approved_browser_projection_and_rejects_bad_control():
    validate = getattr(summary, "_owner_payload_failure_checks")
    assert validate(
        _provider_body(),
        owner="a",
        prompt="private prompt A",
        sources=[_source()],
    ) == []

    bad = copy.deepcopy(_provider_body())
    user = json.loads(bad["messages"][1]["content"])
    user["segments"][0]["speaker"] = "Wrong speaker"
    bad["messages"][1]["content"] = json.dumps(user)
    failures = validate(bad, owner="a", prompt="private prompt A", sources=[_source()])
    assert failures
    assert any("speaker" in failure for failure in failures)
    assert all("Wrong speaker" not in failure for failure in failures)


def test_g9_owner_payload_rejects_wrong_owner_and_extra_key():
    validate = getattr(summary, "_owner_payload_failure_checks")
    bad = _provider_body()
    bad["model"] = "g9-model-b"
    bad["foreign_meeting_id"] = "synthetic-foreign-id"
    failures = validate(bad, owner="a", prompt="private prompt A", sources=[_source()])
    assert "request.model" in failures
    assert "request.extra_key:foreign_meeting_id" in failures


def test_capacity_diagnostics_pass_and_name_a_genuinely_bad_capacity():
    passing_failures = []
    assert acceptance._validate_capacity(
        {"raw": _capacity_raw()}, failure_checks=passing_failures
    )
    assert passing_failures == []

    revision = _capacity_raw()
    for session in revision["session_observations"]:
        session["events"].append(
            {"kind": "text_revision_applied", "runtime_monotonic_ns": None, "source": "rolling"}
        )
    assert acceptance._validate_capacity({"raw": revision})

    bad_event = _capacity_raw()
    bad_event["session_observations"][0]["events"][2]["runtime_monotonic_ns"] = None
    event_failures = []
    assert not acceptance._validate_capacity({"raw": bad_event}, failure_checks=event_failures)
    assert "capacity.event_runtime_monotonic_ns_missing:canonical_processed" in event_failures

    bad = _capacity_raw()
    bad["vllm_gpu_cache_use"] = 1.2
    bad["vllm_gpu_cache_samples"] = [1.2, 1.2]
    failing_checks = []
    assert not acceptance._validate_capacity({"raw": bad}, failure_checks=failing_checks)
    assert "capacity.check_failed:cache_peak_at_most_0_95" in failing_checks

    inconsistent = _capacity_raw()
    inconsistent["vllm_gpu_cache_use"] = 1.2
    consistency_failures = []
    assert not acceptance._validate_capacity({"raw": inconsistent}, failure_checks=consistency_failures)
    assert "capacity.check_failed:vllm_gpu_cache_use_matches_samples" in consistency_failures


def test_g9_summary_receipt_retains_only_named_diagnostics(tmp_path):
    class Campaign:
        def _artifact_json(self, relative, payload):
            (tmp_path / relative).write_text(json.dumps(payload))

    raw = {
        "checks": {"owner_payloads_only": False, "speech_capacity_unchanged": False},
        "diagnostics": {
            "owner_payloads_only": ["call[0].request.extra_key:response_format"],
            "speech_capacity_unchanged": ["prestop_inference_rtf_below_one"],
        },
        "capacity": _capacity_raw(),
        "retry_deliveries": [0, 60, 180, 420],
        "events": [[], []],
        "relay": {"checks": {"placeholder": True}, "upstream_requests": 1},
    }
    try:
        summary._record_summary_result(Campaign(), raw)
    except RuntimeError:
        pass
    retained = json.loads((tmp_path / "summary-checks.json").read_text())
    assert retained["diagnostics"] == raw["diagnostics"]
    assert "synthetic owner A speech" not in json.dumps(retained)


def test_overload_validator_tolerates_untimed_text_revisions_only():
    """H1 #2 overload events carry D46's untimed `text_revision_applied` rows (1 and 12)."""

    from tests.phase2.test_wave1_qualification import _overload_raw

    assert acceptance._validate_overload({"raw": _overload_raw()})

    revision = _overload_raw()
    for session in revision["session_observations"]:
        session["events"].append(
            {"kind": "text_revision_applied", "runtime_monotonic_ns": None, "source": "rolling"}
        )
    assert acceptance._validate_overload({"raw": revision})

    untimed_other = _overload_raw()
    event = next(
        row for row in untimed_other["session_observations"][0]["events"]
        if row.get("kind") == "canonical_processed"
    )
    event["runtime_monotonic_ns"] = None
    assert not acceptance._validate_overload({"raw": untimed_other})
