import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "prototypes/streaming-diarization/concurrency/run_cpu_hf_local_measurement.py"
HISTORICAL_RUN_STATE = ROOT / "evidence/phase1/w2-local-concurrency/run-20260818T213600/run-state.json"
HISTORICAL_SOURCE_SHA256 = "a28f57e5b5266c429bb1df106417ee6448fed58fb94180c207788e5b4d8986dd"
HISTORICAL_SOURCE_SIZE_BYTES = 59_992_997
HISTORICAL_PREDICATE_PROJECTION_SHA256 = "3c8eaa6a557f3d40292c2a8456fe1289726929aa6921765b53a29b0a69b8e9d2"
SPEC = importlib.util.spec_from_file_location("w2_measurement_evidence", RUNNER_PATH)
assert SPEC is not None and SPEC.loader is not None
RUNNER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RUNNER
SPEC.loader.exec_module(RUNNER)


def _attempt(*, lane: str, sequence: int, status: int, pcm: bytes) -> dict:
    payload = {
        "lane": lane,
        "sequence": sequence,
        "capture_timestamp_ns": 123_000 + sequence,
        "device_epoch": 7,
        "silent": False,
        "discontinuity": False,
        "sample_rate": 16_000,
        "sample_count": len(pcm) // 2,
        "pcm_base64": base64.b64encode(pcm).decode("ascii"),
    }
    response = {"status": status, "json": None}
    if status != 200:
        response["json"] = {
            "detail": "live canonical queue is full.",
            "failure": {
                "code": "canonical_queue_full",
                "detail": {"queue_depth": 16, "required_work_items": 2},
                "retryable": True,
            },
        }
    return {"payload": payload, "response": response, "record": {"status": status}}


def test_unexpected_frame_evidence_aggregates_counts_and_never_serializes_pcm():
    results = RUNNER._new_unexpected_frame_results()
    for sequence in range(1, 5):
        failure = {
            "session_id": "session-a",
            "sequence": sequence,
            "attempted": [
                _attempt(lane="microphone", sequence=sequence, status=200, pcm=bytes([sequence]) * 16),
                _attempt(lane="system", sequence=sequence, status=429, pcm=bytes([sequence]) * 16),
            ],
        }
        RUNNER._record_unexpected_frame_result(results, failure)

    assert results["total_count"] == 4
    assert len(results["buckets"]) == 1
    bucket = results["buckets"][0]
    assert (bucket["http_status"], bucket["error_code"], bucket["lane"], bucket["count"]) == (
        429,
        "canonical_queue_full",
        "system",
        4,
    )
    assert [item["sequence"] for item in bucket["first_exemplars"]] == [1, 2, 3]
    assert [item["sequence"] for item in bucket["last_exemplars"]] == [2, 3, 4]
    frame = bucket["first_exemplars"][0]["attempted"][0]["frame"]
    assert frame["pcm_len"] == 16
    assert len(frame["pcm_sha256_prefix"]) == 16
    assert "pcm_base64" not in json.dumps(results, sort_keys=True)


def test_historical_run_state_compaction_preserves_predicates_without_pcm():
    raw = HISTORICAL_RUN_STATE.read_bytes()
    assert len(raw) < 1_000_000
    assert b'"pcm_base64"' not in raw

    state = json.loads(raw)
    assert state.pop("evidence_compaction") == {
        "kind": "unexpected_frame_results_compaction",
        "legacy_session_id_source": "attempted[-1].response.json.snapshot.session_id",
        "predicate_projection_sha256": HISTORICAL_PREDICATE_PROJECTION_SHA256,
        "source_sha256": HISTORICAL_SOURCE_SHA256,
        "source_size_bytes": HISTORICAL_SOURCE_SIZE_BYTES,
    }

    expected_bucket_counts = {
        "screen-1": {},
        "screen-2": {
            (429, "canonical_queue_full", "microphone"): 80,
            (429, "canonical_queue_full", "system"): 33,
        },
        "screen-4": {
            (429, "canonical_queue_full", "microphone"): 430,
            (429, "canonical_queue_full", "system"): 43,
        },
        "screen-8": {
            (429, "canonical_queue_full", "microphone"): 954,
            (429, "canonical_queue_full", "system"): 44,
        },
    }
    for phase in state["phases"]:
        if phase.get("kind") != "normal":
            continue
        results = phase.pop("unexpected_frame_results")
        actual_bucket_counts = {
            (bucket["http_status"], bucket["error_code"], bucket["lane"]): bucket["count"]
            for bucket in results["buckets"]
        }
        assert actual_bucket_counts == expected_bucket_counts[phase["name"]]
        assert results["total_count"] == sum(actual_bucket_counts.values())
        for bucket in results["buckets"]:
            assert len(bucket["first_exemplars"]) == min(3, bucket["count"])
            assert len(bucket["last_exemplars"]) == min(3, bucket["count"])
            for exemplar in bucket["first_exemplars"] + bucket["last_exemplars"]:
                assert isinstance(exemplar["session_id"], str) and exemplar["session_id"]

    projection = json.dumps(state, sort_keys=True, separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(projection).hexdigest() == HISTORICAL_PREDICATE_PROJECTION_SHA256
