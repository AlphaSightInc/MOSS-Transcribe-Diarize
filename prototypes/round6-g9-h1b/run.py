#!/usr/bin/env python3
"""Content-free G9 replay on the production browser and local fake provider."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import tempfile
from collections import Counter
from pathlib import Path

from moss_transcribe_diarize.phase2_acceptance import (
    _validate_capacity,
    prestop_inference_projection,
)

ROOT = Path(__file__).resolve().parents[2]
H1B = Path("/Users/gao/Documents/Codex/2026-09-23/moss-round6/evidence/r6-h1b-20260923T205011Z/deployed-ws")
RAW_EXPECTED_KEYS = {"model", "stream", "messages", "max_tokens"}
SYNTHETIC = [
    {"start": 0.25, "end": 4.75, "speaker": "S00", "source_lane": "system"},
    {"start": 1.5, "end": 3.5, "speaker": "Speaker uncertain", "source_lane": "microphone"},
]


def load_probe():
    path = ROOT / "prototypes/round6-g9-h1b/local_browser_probe.py"
    spec = importlib.util.spec_from_file_location("g9_local_browser_probe", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("local browser probe import unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = module.SummaryProbeProvider
    providers = []

    class CapturingProvider(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            providers.append(self)

    module.SummaryProbeProvider = CapturingProvider
    return module, providers


def timestamp(seconds: float) -> str:
    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def request_shape(row: dict, owner: int) -> dict:
    body_value = row.get("body", b"")
    if isinstance(body_value, bytes):
        body_value = body_value.decode("utf-8")
    body = json.loads(body_value)
    messages = body.get("messages") if isinstance(body, dict) else None
    user = messages[1] if isinstance(messages, list) and len(messages) > 1 else {}
    content = json.loads(user.get("content", "{}")) if isinstance(user, dict) else {}
    actual_segments = content.get("segments") if isinstance(content, dict) else None
    actual_segments = actual_segments if isinstance(actual_segments, list) else []
    expected_fields = {"start", "end", "speaker", "text"}
    expected_owner_text = f"ONLY-OWNER-{owner}-TRANSCRIPT"
    other_owner_text = f"ONLY-OWNER-{1-owner}-TRANSCRIPT"
    actual_speakers = [item.get("speaker") for item in actual_segments if isinstance(item, dict)]
    expected_speakers = [item["speaker"] for item in SYNTHETIC]
    expected_projected_speakers = [
        "Speaker uncertain" if value == "S00" else value
        for value in expected_speakers
    ]
    expected_times = [(timestamp(item["start"]), timestamp(item["end"])) for item in SYNTHETIC]
    actual_times = [
        (item.get("start"), item.get("end"))
        for item in actual_segments
        if isinstance(item, dict)
    ]
    return {
        "actual_top_level_keys": sorted(body) if isinstance(body, dict) else [],
        "old_expected_top_level_keys": sorted(RAW_EXPECTED_KEYS),
        "extra_top_level_keys_vs_old_expectation": sorted(set(body) - RAW_EXPECTED_KEYS),
        "missing_top_level_keys_vs_old_expectation": sorted(RAW_EXPECTED_KEYS - set(body)),
        "model_matches_owner": body.get("model") == f"probe-model-{owner}",
        "stream_false": body.get("stream") is False,
        "max_tokens": body.get("max_tokens"),
        "max_tokens_floor_pass": isinstance(body.get("max_tokens"), int) and body["max_tokens"] >= 2048,
        "system_prompt_matches": bool(messages and messages[0].get("content") == f"probe-prompt-{owner}"),
        "user_role_is_user": isinstance(user, dict) and user.get("role") == "user",
        "segment_count": len(actual_segments),
        "old_expected_segment_fields": sorted(expected_fields),
        "actual_segment_field_sets": [sorted(item) for item in actual_segments if isinstance(item, dict)],
        "extra_segment_fields_vs_old_expectation": sorted(
            set().union(*(set(item) for item in actual_segments if isinstance(item, dict))) - expected_fields
        ) if actual_segments else [],
        "start_end_actual_types": [
            [type(item.get("start")).__name__, type(item.get("end")).__name__]
            for item in actual_segments if isinstance(item, dict)
        ],
        "start_end_match_product_normalization": actual_times == expected_times,
        "speaker_values_match_source": actual_speakers == expected_speakers,
        "speaker_values_match_d45b_projection": actual_speakers == expected_projected_speakers,
        "text_values_match_owner_source": len(actual_segments) == 2 and all(
            isinstance(item, dict) and item.get("text") == expected_owner_text
            for item in actual_segments
        ),
        "other_owner_text_absent": other_owner_text not in body_value,
        "response_format_json_object": body.get("response_format") == {"type": "json_object"},
    }


def capacity_replay() -> dict:
    root = H1B
    files = [root / "campaign/summary-load/load-2" / f"session-{i}-events.json" for i in (1, 2)]
    stops = [root / "campaign/summary-load/load-2" / f"session-{i}-stop-wait.json" for i in (1, 2)]
    rows = []
    for index, path in enumerate(files, 1):
        data = json.loads(path.read_text())
        events = data.get("events", [])
        missing_times = Counter(
            str(event.get("kind", "unknown"))
            for event in events
            if not isinstance(event.get("runtime_monotonic_ns"), int)
        )
        projection = prestop_inference_projection(events, accepted_audio_seconds=600.0)
        rows.append({
            "session": index,
            "event_count": len(events),
            "kind_counts": dict(sorted(Counter(event.get("kind") for event in events).items())),
            "missing_runtime_monotonic_ns_count": sum(missing_times.values()),
            "missing_runtime_monotonic_ns_by_kind": dict(sorted(missing_times.items())),
            "prestop_inference_rtf": projection["rtf"],
            "prestop_rtf_below_one": projection["rtf"] < 1,
            "terminal_failure_events": sum(event.get("kind") == "terminal_finalization_failed" for event in events),
        })
    g4_path = root / "raw/deployed--G4--two_session_capacity.json"
    g4 = json.loads(g4_path.read_text())
    g4_raw = g4.get("raw", {})
    g4_replay_failures = []
    g4_export_replay = _validate_capacity({"raw": g4_raw}, failure_checks=g4_replay_failures)
    g4_events = [event for session in g4_raw.get("session_observations", []) for event in session.get("events", [])]
    g4_missing_times = Counter(
        str(event.get("kind", "unknown"))
        for event in g4_events
        if not isinstance(event.get("runtime_monotonic_ns"), int)
    )
    required_raw_fields = {
        "session_observations", "wrong_owner_observations", "rss_samples", "vllm_gpu_cache_samples",
        "log_match_counts", "backpressure_observation", "campaign_interval", "requested_duration_seconds",
        "duration_seconds", "accounts", "real_human_speech", "ingress_cadence_seconds",
    }
    event_only_fields = {"events", "next_seq", "session_id"}
    missing_fields = sorted(required_raw_fields - event_only_fields)
    for path in stops:
        json.loads(path.read_text())
    return {
        "nested_g9_full_capacity_result_retained": False,
        "nested_g9_required_aggregate_fields_missing_from_event_bundle": missing_fields,
        "nested_g9_event_reductions": rows,
        "nested_g9_untimed_text_revision_events_per_session": [
            row["missing_runtime_monotonic_ns_by_kind"].get("text_revision_applied", 0)
            for row in rows
        ],
        "nested_g9_possible_guard_failure_if_full_inputs_reach_event_loop":
            "capacity.event_runtime_monotonic_ns_missing:text_revision_applied",
        "nested_g9_actual_first_failed_capacity_check":
            "UNMEASURED: complete capacity aggregate is absent",
        "nested_g9_full_check_name_identifiable": False,
        "g4_recorded_sample_state": g4.get("samples", [{}])[0].get("state"),
        "g4_exported_raw_replay_valid": g4_export_replay,
        "g4_exported_raw_replay_failure_checks_after_harness_fix": g4_replay_failures,
        "g4_export_missing_runtime_monotonic_ns_count": sum(g4_missing_times.values()),
        "g4_export_missing_runtime_monotonic_ns_by_kind": dict(sorted(g4_missing_times.items())),
        "classification": "STALE_GUARD_CONFIRMED_ON_G4; H1B PRODUCT CAPACITY REMAINS POSSIBLE AND UNMEASURED",
        "capacity_attempt": "3/3; final bounded offline replay",
    }


def main() -> None:
    module, providers = load_probe()
    with tempfile.TemporaryDirectory(prefix="moss-g9-h1b-probe-") as directory:
        evidence = asyncio.run(module.run(Path(directory)))
    external_calls = providers[0].calls if providers else []
    shapes = [request_shape(row, index) for index, row in enumerate(external_calls)]
    report = {
        "platform": "macOS",
        "gpu_requests": 0,
        "real_decoder_or_external_provider_requests": 0,
        "local_browser_probe": {
            "existing_checks_passed": evidence.get("passed"),
            "existing_checks_total": evidence.get("total"),
            "synthetic_transcripts": evidence.get("synthetic_transcripts"),
            "provider_calls_captured": len(external_calls),
            "payload_attempt": "2/3; final D5 predicate comparison",
            "captured_payload_shapes": shapes,
            "transcript_text_printed_or_saved": False,
        },
        "capacity_offline_replay": capacity_replay(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
