import base64
import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "prototypes/streaming-diarization/concurrency/run_cpu_hf_local_measurement.py"
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
