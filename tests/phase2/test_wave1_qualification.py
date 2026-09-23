from __future__ import annotations

import json
import math
import copy
import base64
import csv
import hashlib
import io
import zipfile
import os
import stat
import subprocess
import threading
from types import SimpleNamespace
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from moss_transcribe_diarize import phase2_acceptance as acceptance
from moss_transcribe_diarize.phase2_acceptance_collect import (
    RAW_SCHEMA,
    collect_layer,
    write_collected_report,
)
from moss_transcribe_diarize.phase2_acceptance_replay import AccountCookieLiveReplayService
from moss_transcribe_diarize import phase2_acceptance_measure as measurement
from moss_transcribe_diarize import phase2_acceptance_external as external
from moss_transcribe_diarize import phase2_acceptance_browser as browser_measurement
from moss_transcribe_diarize import phase2_cutover_rehearsal as cutover
from moss_transcribe_diarize.phase2_acceptance_measure import measure_layer
from moss_transcribe_diarize.installed_candidate import (
    installer_owned_empty_record,
    record_projection_sha256,
)


FIXTURES = {
    "quality_corpus_manifest": "80fc15bd730f7aa44d8a69aa6e7e00aaf43ed54e2af8a03abc2c8934d7438d7c",
    "concurrency_fixture": "d893248526fc29845817c06affb9d665d0cde6600e7a16c35945a695e8bb9aee",
    "concurrency_preregistration": "b6fbe1f5dc60c0f0a20128026eefa8bc369a456927fe267cf94aa2a8b2865d52",
}
ROOT = Path(__file__).resolve().parents[2]


def _commit_candidate_checkout(checkout: Path) -> str:
    subprocess.run(("git", "init", "--quiet", str(checkout)), check=True)
    subprocess.run(
        ("git", "-C", str(checkout), "config", "user.email", "test@example.invalid"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(checkout), "config", "user.name", "test"), check=True
    )
    subprocess.run(("git", "-C", str(checkout), "add", "."), check=True)
    subprocess.run(
        ("git", "-C", str(checkout), "commit", "--quiet", "-m", "candidate"),
        check=True,
    )
    return subprocess.check_output(
        ("git", "-C", str(checkout), "rev-parse", "HEAD"), text=True
    ).strip()


class _Response:
    def __init__(
        self,
        status_code: int,
        payload: object | None = None,
        *,
        content: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = {} if payload is None else payload
        self.content = (
            json.dumps(self._payload, sort_keys=True).encode()
            if content is None
            else content
        )
        self.headers = headers or {}

    def json(self):
        return self._payload


def _campaign(tmp_path: Path, **config: str) -> external.FixedAccountCampaign:
    journal = tmp_path / "operator.jsonl"
    journal.write_text("", encoding="utf-8")
    values = {
        "campaign_work_dir": str(tmp_path / "campaign"),
        "operator_journal": str(journal),
        **config,
    }
    campaign = external.FixedAccountCampaign(candidate_sha="a" * 40, config=values)
    class JournalStub:
        def __init__(self, unit):
            self.unit = unit
            self.path = Path(values.get("server_log" if unit == "moss-web.service" else "vllm_log", str(journal)))
            self.offset = self.path.stat().st_size if self.path.exists() else 0
            self.content = b""
        def read(self):
            self.content = self.path.read_bytes()[self.offset:] if self.path.exists() else b""
            return self.content
        def observation(self):
            return {"source": "systemd-user-journal", "unit": self.unit,
                    "baseline_cursor_observed": True, "read_succeeded": True,
                    "entries": len(self.content.splitlines()), "bytes": len(self.content)}
    campaign._journal_window = JournalStub
    return campaign


def _case() -> dict[str, object]:
    return {
        "cases": [{"id": "case-1", "executed": True, "passed": True}],
        "counts": {
            "collected": 1,
            "executed": 1,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "unmeasured": 0,
        },
    }


def _capacity_raw() -> dict[str, object]:
    sessions = []
    for ordinal in range(1, 3):
        sessions.append(
            {
                "session_ordinal": ordinal,
                "account_ordinal": 1 if ordinal % 2 else 2,
                "frames": 1200,
                "lags": [1.0, 2.0],
                "accepted_samples": 9_600_000,
                "accounted_samples": 9_600_000,
                "maximum_pending_work_items": 1,
                "own_marker_present": True,
                "foreign_markers_absent": True,
                "events": [
                    {
                        "kind": "canonical_queued",
                        "runtime_monotonic_ns": ordinal,
                        "item_id": ordinal,
                    },
                    {
                        "kind": "canonical_started",
                        "runtime_monotonic_ns": 10 + ordinal,
                        "item_id": ordinal,
                    },
                    {
                        "kind": "canonical_processed",
                        "runtime_monotonic_ns": 20 + ordinal,
                        "item_id": ordinal,
                        "canonical_decode_elapsed_sec": 540.0,
                        "frozen_span_duration_sec": 1.0,
                    },
                    {
                        "kind": "rolling_decode_queued",
                        "runtime_monotonic_ns": 30 + ordinal,
                        "admitted": True,
                        "item_id": 1,
                    },
                    {
                        "kind": "rolling_decode_completed",
                        "runtime_monotonic_ns": 40 + ordinal,
                        "item_id": 1,
                        "outcome": "applied",
                        "rolling_decode_elapsed_sec": 0.0,
                        "decode_failure": None,
                        "windows_failed": 0,
                        "stale_completions": 0,
                    },
                ],
            }
        )
    lifecycle = [
        {
            "session_id": str(session["session_ordinal"]),
            "kind": event["kind"],
            "payload": {key: value for key, value in event.items() if key != "kind"},
        }
        for session, event in sorted(
            (
                (session, event)
                for session in sessions
                for event in session["events"]
                if str(event["kind"]).startswith("canonical_")
            ),
            key=lambda pair: pair[1]["runtime_monotonic_ns"],
        )
    ]
    fairness = acceptance.canonical_lifecycle_fairness(
        lifecycle, {"1", "2"}, maximum_skew=1
    )
    return {
        "sessions": 2,
        "accounts": 2,
        "requested_duration_seconds": 600,
        "duration_seconds": 600,
        "campaign_interval": {
            "started_monotonic_ns": 1_000_000_000,
            "finished_monotonic_ns": 601_000_000_000,
        },
        "real_human_speech": True,
        "ingress_cadence_seconds": 0.5,
        "continuous_wrong_owner_probes": True,
        "transcript_lag_seconds": {f"s{index}": [1.0, 2.0] for index in range(2)},
        "dispatch_skew": 1,
        "fairness_measured": True,
        "fairness_observation": fairness,
        "prestop_inference_rtf": 0.9,
        "refinement_queue_depth": 1,
        "vllm_gpu_cache_use": 0.9,
        "rss_growth_bytes": 4 * 1024**3,
        "rss_samples": [0, 4 * 1024**3],
        "vllm_gpu_cache_samples": [0.8, 0.9],
        "session_observations": sessions,
        "wrong_owner_observations": [
            {
                "session_ordinal": ordinal,
                "sequence": sequence,
                "status": 404,
                "foreign_matches": 0,
            }
            for sequence in range(1200)
            for ordinal in range(1, 3)
        ],
        "log_match_counts": {"oom": 0, "accelerator": 0},
        "backpressure_observation": {
            "observed_429": True,
            "peer_progress": True,
            "same_sequence_retry": True,
        },
    }


def _overload_raw(duration_seconds: float = 120.5, capacity_samples: int = 960_000) -> dict[str, object]:
    frames = int(duration_seconds * 16_000 / 8_000)
    samples = frames * 8_000
    value = _capacity_raw()
    template = value["session_observations"]
    sessions = []
    for ordinal in range(1, 3):
        item = copy.deepcopy(template[(ordinal - 1) % 2])
        item.update(
            {
                "session_ordinal": ordinal,
                "account_ordinal": 1 if ordinal % 2 else 2,
                "frames": frames,
                "finalization_status": "final",
                "accepted_samples": samples,
                "accounted_samples": samples,
            }
        )
        for event in item["events"]:
            offsets = {
                "canonical_queued": 0,
                "canonical_started": 100,
                "canonical_processed": 200,
                "rolling_decode_queued": 300,
                "rolling_decode_completed": 400,
            }
            event["runtime_monotonic_ns"] = offsets[event["kind"]] + ordinal
        sessions.append(item)
    lifecycle = [
        {
            "session_id": str(session["session_ordinal"]),
            "kind": event["kind"],
            "payload": {key: item for key, item in event.items() if key != "kind"},
        }
        for session, event in sorted(
            (
                (session, event)
                for session in sessions
                for event in session["events"]
                if str(event["kind"]).startswith("canonical_")
            ),
            key=lambda pair: pair[1]["runtime_monotonic_ns"],
        )
    ]
    fairness = acceptance.canonical_lifecycle_fairness(
        lifecycle, {str(ordinal) for ordinal in range(1, 3)}, maximum_skew=1
    )
    value.update(
        {
            "sessions": 2,
            "terminal_failures": 0,
            "accounts": 2,
            "requested_duration_seconds": duration_seconds,
            "duration_seconds": duration_seconds,
            "campaign_interval": {
                "started_monotonic_ns": 1_000_000_000,
                "finished_monotonic_ns": int((1 + duration_seconds) * 1_000_000_000),
            },
            "session_observations": sessions,
            "wrong_owner_observations": [
                {
                    "session_ordinal": ordinal,
                    "sequence": sequence,
                    "status": 404,
                    "foreign_matches": 0,
                }
                for sequence in range(frames)
                for ordinal in range(1, 3)
            ],
            "isolation_failures": 0,
            "fairness_failures": 0,
            "fairness_measured": True,
            "fairness_observation": fairness,
            "dispatch_skew": fairness["maximum_contended_pair_dispatch_skew"],
            "sequence_gaps": 0,
            "cross_account_sentinel_deliveries": 0,
            "backpressure_workload": {"lane_capacity_samples": capacity_samples, "frame_samples": 8000,
                                      "frames_per_session": frames, "audio_seconds_per_session": duration_seconds},
            "backpressure_observation": {
                "observed_429": True,
                "peer_progress": True,
                "same_sequence_retry": True,
                "campaign_session_ordinals": [1, 2],
                "target_session_ordinal": 1,
                "peer_session_ordinal": 2,
                "refused_monotonic_ns": 10_000_000_000,
                "peer_progress_monotonic_ns": 11_000_000_000,
                "retry_monotonic_ns": 12_000_000_000,
            },
            "admission_observation": {
                "accepted_sessions": 2,
                "excess_attempts": 1,
                "excess_status": 409,
                "refusal_code": "live_capacity_full",
                "accepted_active_after_refusal": True,
            },
        }
    )
    return value


def test_capacity_rtf_excludes_stop_tail_and_overload_backpressure_is_campaign_bound():
    capacity = _capacity_raw()
    for session in capacity["session_observations"]:
        ordinal = int(session["session_ordinal"])
        session["events"].extend(
            (
                {
                    "kind": "canonical_queued",
                    "runtime_monotonic_ns": 50 + ordinal,
                    "item_id": 100 + ordinal,
                    "reason": "stop",
                },
                {
                    "kind": "canonical_started",
                    "runtime_monotonic_ns": 60 + ordinal,
                    "item_id": 100 + ordinal,
                },
                {
                    "kind": "canonical_processed",
                    "runtime_monotonic_ns": 70 + ordinal,
                    "item_id": 100 + ordinal,
                    "canonical_decode_elapsed_sec": 100.0,
                    "frozen_span_duration_sec": 1.0,
                },
            )
        )
    lifecycle = sorted(
        (
            {
                "session_id": str(session["session_ordinal"]),
                "kind": event["kind"],
                "payload": {key: value for key, value in event.items() if key != "kind"},
            }
            for session in capacity["session_observations"]
            for event in session["events"]
            if str(event["kind"]).startswith("canonical_")
        ),
        key=lambda event: int(event["payload"]["runtime_monotonic_ns"]),
    )
    fairness = acceptance.canonical_lifecycle_fairness(
        lifecycle, {"1", "2", "3", "4"}, maximum_skew=1
    )
    capacity["fairness_observation"] = fairness
    capacity["dispatch_skew"] = fairness["maximum_contended_pair_dispatch_skew"]
    assert acceptance._validate_capacity({"raw": capacity}) is True

    diluted = copy.deepcopy(capacity)
    for session in diluted["session_observations"]:
        for event in session["events"]:
            if event["kind"] == "canonical_processed" and event["item_id"] < 100:
                event["canonical_decode_elapsed_sec"] = 660.0
            elif event["kind"] == "canonical_processed":
                event["canonical_decode_elapsed_sec"] = 0.0
    diluted["prestop_inference_rtf"] = 0.55
    assert acceptance._validate_capacity({"raw": diluted}) is False

    rolling_omitted = copy.deepcopy(capacity)
    for session in rolling_omitted["session_observations"]:
        for event in session["events"]:
            if event["kind"] == "rolling_decode_completed":
                event["rolling_decode_elapsed_sec"] = 120.0
    rolling_omitted["prestop_inference_rtf"] = 0.9
    assert acceptance._validate_capacity({"raw": rolling_omitted}) is False

    missing_completions = copy.deepcopy(capacity)
    for session in missing_completions["session_observations"]:
        session["events"] = [
            event
            for event in session["events"]
            if event["kind"] != "rolling_decode_completed"
        ]
    assert acceptance._validate_capacity({"raw": missing_completions}) is False

    missing_elapsed = copy.deepcopy(capacity)
    for session in missing_elapsed["session_observations"]:
        for event in session["events"]:
            if event["kind"] == "rolling_decode_completed":
                event["rolling_decode_elapsed_sec"] = None
    assert acceptance._validate_capacity({"raw": missing_elapsed}) is False

    failed_rolling = copy.deepcopy(capacity)
    for session in failed_rolling["session_observations"]:
        for event in session["events"]:
            if event["kind"] == "rolling_decode_completed":
                event["decode_failure"] = "provider_failed"
                event["windows_failed"] = 1
                event["stale_completions"] = 1
    assert acceptance._validate_capacity({"raw": failed_rolling}) is False

    duplicate_admission = copy.deepcopy(capacity)
    duplicate_admission["session_observations"][0]["events"].append(
        copy.deepcopy(
            next(
                event
                for event in duplicate_admission["session_observations"][0]["events"]
                if event["kind"] == "rolling_decode_queued"
            )
        )
    )
    assert acceptance._validate_capacity({"raw": duplicate_admission}) is False

    collided = copy.deepcopy(capacity)
    for session in collided["session_observations"]:
        ordinal = int(session["session_ordinal"])
        for event in session["events"]:
            if event["kind"] == "canonical_processed" and event["item_id"] < 100:
                event["canonical_decode_elapsed_sec"] = 1020.0 if ordinal == 2 else 540.0
            if ordinal == 1 and event.get("item_id") == 101:
                event["item_id"] = 2
    collided["prestop_inference_rtf"] = 0.9
    assert acceptance._validate_capacity({"raw": collided}) is False

    overload = _overload_raw()
    assert acceptance._validate_overload({"raw": overload}) is True
    del overload["backpressure_observation"]["target_session_ordinal"]
    assert acceptance._validate_overload({"raw": overload}) is False

    overload = _overload_raw()
    overload["backpressure_observation"]["retry_monotonic_ns"] = overload["campaign_interval"]["finished_monotonic_ns"] + 1
    assert acceptance._validate_overload({"raw": overload}) is False


def test_prestop_rtf_includes_rolling_and_scopes_stop_items_to_meeting():
    events = [
        {
            "session_id": "meeting-a",
            "kind": "canonical_processed",
            "payload": {"item_id": 1, "canonical_decode_elapsed_sec": 0.9},
        },
        {
            "session_id": "meeting-a",
            "kind": "rolling_decode_queued",
            "payload": {"item_id": 2, "admitted": True},
        },
        {
            "session_id": "meeting-a",
            "kind": "rolling_decode_completed",
            "payload": {
                "item_id": 2,
                "outcome": "no_proposal",
                "rolling_decode_elapsed_sec": 0.2,
                "decode_failure": None,
                "windows_failed": 0,
                "stale_completions": 0,
            },
        },
        {
            "session_id": "meeting-a",
            "kind": "canonical_queued",
            "payload": {"item_id": 0, "reason": "stop"},
        },
        {
            "session_id": "meeting-a",
            "kind": "canonical_processed",
            "payload": {"item_id": 0, "canonical_decode_elapsed_sec": 100.0},
        },
        {
            "session_id": "meeting-b",
            "kind": "canonical_processed",
            "payload": {"item_id": 0, "canonical_decode_elapsed_sec": 1.1},
        },
    ]

    projection = acceptance.prestop_inference_projection(
        events,
        accepted_audio_seconds=2.0,
    )

    assert projection == {
        "canonical_processed_items": 2,
        "rolling_completed_items": 1,
        "stop_items": 1,
        "canonical_decode_seconds": 2.0,
        "rolling_decode_seconds": 0.2,
        "decode_seconds": 2.2,
        "accepted_audio_seconds": 2.0,
        "rtf": 1.1,
    }


@pytest.mark.parametrize("finalization_status", ["final", "failed"])
def test_live_load_success_reaches_authoritative_result_projection(tmp_path, monkeypatch, finalization_status):
    fixture_root = tmp_path / "repo"
    fixture_path = fixture_root / "prototypes/streaming-diarization/concurrency"
    fixture_path.mkdir(parents=True)
    (fixture_path / "cpu_hf_local_fixture.json").write_text(
        json.dumps(
            {
                "audio": {"path": "unused.wav"},
                "clips": [
                    {
                        "start_seconds": 0,
                        "end_seconds": 1,
                        "expected_marker": "marker",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    empty = tmp_path / "empty.log"
    empty.write_bytes(b"")
    sentinel_a = tmp_path / "a.sentinel"
    sentinel_b = tmp_path / "b.sentinel"
    sentinel_a.write_bytes(b"account-a")
    sentinel_b.write_bytes(b"account-b")

    class Event:
        def __init__(self, kind: str, payload: dict[str, object]) -> None:
            self.kind = kind
            self.payload = payload

        def to_dict(self):
            return {"session_id": "session-1", "kind": self.kind, "payload": self.payload}

    events = [
        Event("canonical_queued", {"item_id": 0, "runtime_monotonic_ns": 1}),
        Event("canonical_started", {"item_id": 0, "runtime_monotonic_ns": 2}),
        Event(
            "canonical_processed",
            {
                "item_id": 0,
                "runtime_monotonic_ns": 3,
                "canonical_decode_elapsed_sec": 0.1,
                "committed_samples": 8_000,
                "submitted": True,
            },
        ),
        Event(
            "rolling_decode_queued",
            {"item_id": 1, "admitted": True, "runtime_monotonic_ns": 4},
        ),
        Event(
            "rolling_decode_completed",
            {
                "item_id": 1,
                "outcome": "applied",
                "rolling_decode_elapsed_sec": 0.1,
                "decode_failure": None,
                "windows_failed": 0,
                "stale_completions": 0,
                "runtime_monotonic_ns": 5,
            },
        ),
    ]

    for seq, event in enumerate(events):
        event.seq = seq

    class Adapter:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def descriptor(self):
            return SimpleNamespace(frame_samples=8_000)

        def create(self):
            return SimpleNamespace(
                session_id="session-1",
                snapshot=SimpleNamespace(pending_work_items=0),
            )

        def accept_frame(self, session_id: str, frame: object):
            del session_id, frame
            return SimpleNamespace(snapshot=SimpleNamespace(pending_work_items=0))

        async def stop(self, session_id: str, deadline: float):
            del session_id, deadline
            session = SimpleNamespace(
                accepted_samples=8_000,
                accounted_samples=8_000,
                effective_transcript=(SimpleNamespace(text="marker"),),
                finalization_status=finalization_status,
            )
            return SimpleNamespace(session=session)

        def events(self, session_id: str, since_seq=0):
            del session_id
            return [event for event in events if event.seq >= since_seq]

        async def abort(self, session_id: str, reason: str):
            del session_id, reason

    class Probe:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def request(self, method: str, path: str):
            del method, path
            return _Response(404, content=b"")

        def close(self) -> None:
            pass

    monkeypatch.setattr(external, "AccountCookieLiveReplayService", Adapter)
    monkeypatch.setattr(external, "AccountHttpClient", Probe)
    monkeypatch.setattr(external, "_wav_pcm_clip", lambda *args: (b"\0" * 16_000, "marker"))
    monkeypatch.setattr(external, "_unit_pid", lambda unit: 1)
    monkeypatch.setattr(external, "_process_tree_rss", lambda pid: 0)
    monkeypatch.setattr(external, "_vllm_cache_use", lambda url: 0.0)
    campaign = _campaign(
        tmp_path,
        repo_root=str(fixture_root),
        account_a_cookie_file=str(empty),
        account_b_cookie_file=str(empty),
        account_a_sentinel_file=str(sentinel_a),
        account_b_sentinel_file=str(sentinel_b),
        server_log=str(empty),
        vllm_log=str(empty),
        vllm_metrics_url="https://metrics.invalid",
        https_origin="https://moss.test",
    )

    result = campaign._run_live_load(sessions=1, duration_seconds=0.5)

    assert result["session_observations"][0]["finalization_status"] == finalization_status
    assert result["prestop_inference_rtf"] == 0.4
    assert result["terminal_failures"] == 0
    assert "stale_failed_windows" not in result


def test_campaign_backpressure_retries_exact_target_frame_after_same_campaign_peer():
    probe = external._CampaignBackpressure(2)
    target_calls: list[dict[str, object]] = []

    class Target:
        def accept_lane(self, session_id: str, payload: dict[str, object]):
            assert session_id == "target"
            target_calls.append(payload)
            if len(target_calls) == 1:
                raise external.AccountReplayTransportFailure("full", http_status=429)
            return {"accepted": True}

        def heartbeat(self, session_id: str) -> None:
            assert session_id == "target"

        def snapshot(self, session_id: str):
            assert session_id == "target"
            return SimpleNamespace(pending_work_items=1)

    class Peer:
        def accept_frame(self, session_id: str, frame: object):
            assert session_id == "peer"
            return SimpleNamespace(snapshot=SimpleNamespace(pending_work_items=0))

    frame = external.AudioFrame(3, b"\0\0" * 8_000, 8_000, 16_000)
    target_result: list[object] = []
    target = threading.Thread(
        target=lambda: target_result.append(probe.accept(0, Target(), "target", frame))
    )
    target.start()
    assert probe._refusal_seen.wait(timeout=1)
    probe.accept(1, Peer(), "peer", frame)
    target.join(timeout=2)
    assert not target.is_alive()
    assert target_result
    assert target_calls[0] is target_calls[1]
    observation = probe.observation()
    assert observation["campaign_session_ordinals"] == [1, 2]
    assert observation["target_session_ordinal"] == 1
    assert observation["peer_session_ordinal"] == 2
    assert observation["observed_429"] is True
    assert observation["peer_progress"] is True
    assert observation["same_sequence_retry"] is True
    assert (
        observation["refused_monotonic_ns"]
        <= observation["peer_progress_monotonic_ns"]
        <= observation["retry_monotonic_ns"]
    )


def _raw(predicate_id: str, sha: str, wheel: str) -> dict[str, object]:
    values: dict[str, dict[str, object]] = {
        "installed_candidate_identity": {
            "candidate_sha": sha,
            "candidate_tree": "c" * 40,
            "uv_lock_sha256": "d" * 64,
            "fixtures": FIXTURES,
            "candidate_header_sha": sha,
            "wheel_record_verified": True,
            "wheel_record_entries_verified": 80,
            "wheel_record_projection_sha256": "f" * 64,
            "dependency_projection_sha256": "e" * 64,
            "sqlite_runtime": "3.53.4",
            "aiosqlite": "0.22.1",
            "manifest": {
                "schema": "moss-account-candidate.v1",
                "activation_state": "staged_inert",
                "release": "/srv/release",
                "release_launcher": "/srv/release/bin/mtd-account-web",
                "release_launcher_sha256": "9" * 64,
                "release_admin_launcher": "/srv/release/bin/mtd-admin",
                "release_admin_launcher_sha256": "8" * 64,
                "release_cutover_launcher": "/srv/release/bin/mtd-phase2-cutover",
                "release_cutover_launcher_sha256": "4" * 64,
                "release_vllm_launcher": "/srv/release/bin/mtd-vllm",
                "release_vllm_launcher_sha256": "7" * 64,
                "web_unit_sha256": "6" * 64,
                "vllm_unit_sha256": "5" * 64,
                "installed_units_match_manifest": True,
                "active_pointer_resolves_to_release": True,
            },
            "process": {"pid": 7, "cwd": "/srv/moss", "exe": "/usr/bin/python3.12", "interpreter": {"invoked": "/srv/release/bin/python", "release_path": "/srv/release/bin/python", "executable": "/usr/bin/python3.12"}, "argv": ["/srv/release/bin/python", "-I", "-m", "moss_transcribe_diarize.app.phase2_web_cli"]},
            "toolchain": {name: "version" for name in ("chrome", "node", "npm", "ffmpeg", "ffprobe")},
            "accelerator": {"vllm": "1", "torch": "1", "cuda": "1"},
            "tls": {"trusted": True, "subject": "CN=moss", "subject_alt_names": ["moss.example"], "not_after": "Jan 1 00:00:00 2028 GMT"},
            "input_fixtures": {"file": {"sha256": "1" * 64, "bytes": 100, "channels": 1, "sample_width_bytes": 2, "sample_rate_hz": 16000, "frames": 10}, "url": acceptance.QUALIFICATION_URL_FIXTURE},
            "descriptor": {
                "source_revision": sha,
                "provider_name": "vllm",
                "provider_revision": "1",
                "provider_manifest_hash": "1" * 64,
                "schema_version": 1,
                "live_protocol_version": "moss-live-service.v2",
                "sample_rate": 16000,
                "frame_samples": 8000,
                "bounds": {"max": 1},
                "config_hashes": {
                    "endpoint_config_hash": "2" * 64,
                    "identity_config_hash": "3" * 64,
                    "decoder_config_hash": "4" * 64,
                    "combined_config_hash": "5" * 64,
                },
                "combined_config_hash": "5" * 64,
            },
        },
        "zero_work_end": {"active_live": 0, "active_file": 0, "queue_depths": {"batch": 0, "live": 0}},
        "cross_owner_matrix": {
            "cases": [
                {
                    "id": case_id,
                    "method": method,
                    "route": route,
                    "observed_status": status,
                    "owner_state_unchanged": True,
                    "owner_content_matches": 0,
                }
                for case_id, (method, route, status) in acceptance.G1_CROSS_OWNER_MATRIX.items()
            ]
        },
        "sentinel_absence": {
            "audio_sentinel_checks": [
                {
                    "owner_status": 200,
                    "owner_identity_match": True,
                    "foreign_status": 404,
                    "foreign_artifact_bytes": 0,
                }
                for _ in range(2)
            ],
            "surfaces": [
                {"id": surface, "searches": 2, "foreign_matches": 0}
                for surface in sorted(acceptance.G1_SENTINEL_SURFACES)
            ]
        },
        "same_account_convergence": {"clients": 2, "observations": 4, "mismatches": 0},
        "browser_workspace_identity": {"first_tabs": 2, "first_tab_lock_contention_observed": True, "created_workspaces": 2, "same_profile_owner": True, "profiles_isolated": True, "foreign_meeting_status": 404, "mutation_without_cookie_status": 401, "invalid_cookie_bootstrap_status": 401, "cross_origin_status": 403, "nonempty_saved_history": True, "tls_trusted_without_interstitial": True, "tls_identity": {"trusted": True, "subject": "CN=moss", "subject_alt_names": ["moss.example"], "not_after": "Jan 1 00:00:00 2028 GMT"}, "browser_restart_session_survived": True, "history_survived_restart": True, "workspace_url": acceptance.G7_PRODUCTION_ORIGIN + "/", "cookie_contract": {"cookie_secure": True, "cookie_http_only": True, "cookie_same_site": "Lax", "javascript_cannot_read_cookie": True}},
        "revocation_lifecycle": {"cases": 4, "failures": 0, "late_commits": 0, "stale_authority_revived": 0, "durable_prefix_preserved": True, "partial_audio_playable": True},
        "meeting_modes_history_restart": {"modes": ["live", "file", "multi_file", "url", "serial_batch"], "same_account_clients": 2, "history_mismatches": 0, "restart_failures": 0, "one_item_failure_isolated": True, "submissions": {"single_file": 1, "multi_file": 2, "url": 2, "serial_batch": 6, "browser_closed_after_accept": 1, "accepted_failure": 1, "input_boundary_rejection": 1}},
        "crash_recovery": {"cases": 2, "nonempty_durable_prefix": True, "lost_commits": 0, "durable_document_mismatches": 0, "audio_prefix_failures": 0, "process_replaced": True, "resumed_capture": 0, "non_interrupted_active_rows": 0},
        "two_session_capacity": _capacity_raw(),
        "excess_admission_overload": _overload_raw(),
        "quality_corpus": {
            "cases": 6,
            "passes": 2,
            "sessions": 12,
            "windows": 122,
            "duration_seconds": 1239.987,
            "corpus_manifest_sha256": FIXTURES["quality_corpus_manifest"],
            "input_identities": [
                {
                    "case_id": case_id,
                    "checks": {
                        "wav_sha256": True,
                        "wav_bytes": True,
                        "pcm_sha256": True,
                        "samples": True,
                        "reference_sha256": True,
                    },
                    "source_present": False,
                    "source_audio_match": None,
                    "source_reference_match": None,
                }
                for case_id in sorted(acceptance.QUALITY_CASE_IDS)
            ],
            "per_case": [
                {
                    "case_id": sorted(acceptance.QUALITY_CASE_IDS)[index % 6],
                    "pass": index // 6 + 1,
                    "session_id": f"session-{index}",
                    "category": "speech",
                    "duration_seconds": 1239.987 / 12,
                    "windows": 11 if index < 2 else 10,
                    "window_coverage": {
                        "planned_full_windows": 11 if index < 2 else 10,
                        "rolling_decoded": 11 if index < 2 else 10,
                        "terminal_only": 0,
                        "uncovered": 0,
                    },
                    "metrics": {
                        surface: {
                            "wer": {"immediate": 0.16, "settled": 0.14, "final": 0.09}[surface],
                            "tbsa": 0.88,
                            "der": 0.16,
                            "content_recall": 0.93,
                            "matched_word_speaker_accuracy": 0.92,
                            "reference_speech_der": 0.13,
                            **({"der_raw": 0.16, "reference_speech_der_raw": 0.13}
                               if surface == "settled" else {}),
                        }
                        for surface in ("immediate", "settled", "final")
                    },
                    "settled_der_s00_diagnostic": {
                        "as_is": 0.16,
                        "without_s00_confusion": 0.16,
                        "s00_confusion_difference": 0.0,
                        "unattributed_der": 0.16,
                        "reference_speech_as_is": 0.13,
                        "reference_speech_without_s00_confusion": 0.13,
                        "reference_speech_s00_confusion_difference": 0.0,
                        "reference_speech_unattributed_der": 0.13,
                    },
                }
                for index in range(12)
            ],
            "per_category": {"speech": {"wer": 0.14, "tbsa": 0.88, "der": 0.16, "content_recall": 0.93, "matched_word_speaker_accuracy": 0.92, "reference_speech_der": 0.13, "der_raw": 0.16, "reference_speech_der_raw": 0.13}},
            "duration_weighted": {"wer": 0.14, "tbsa": 0.88, "der": 0.16, "content_recall": 0.93, "matched_word_speaker_accuracy": 0.92, "reference_speech_der": 0.13, "der_raw": 0.16, "reference_speech_der_raw": 0.13},
            "macro": {
                "immediate_wer": 0.16,
                "settled_wer": 0.14,
                "recall": 0.93,
                "time_speaker_attribution": 0.88,
                "diarization_error_rate": 0.16,
                "diarization_error_rate_raw": 0.16,
                "matched_speaker_accuracy": 0.92,
                "reference_speech_der": 0.13,
                "reference_speech_der_raw": 0.13,
                "final_wer": 0.09,
            },
        },
        "audio_durability_download": {"live_cases": 1, "file_cases": 1, "format_mismatches": 0, "durability_failures": 0, "cleanup_failures": 0, "owner_download_failures": 0, "foreign_leaks": 0, "unauthenticated_failures": 0, "revoked_failures": 0, "partial_download_failures": 0, "partial_or_unavailable_crash_cases": 1, "path_failures": 0, "permission_failures": 0, "out_of_band_reconciled": True, "ffprobe": [{"codec": "mp3"}, {"codec": "mp3"}, {"codec": "mp3"}]},
        "operator_control": {"socket_mode": "0600", "tcp_admin_surfaces": 0, "forbidden_content_matches": 0, "count_mismatches": 0, "status_surfaces": {"json_exact_projection": True, "human_exact_projection": True, "json_stderr_bytes": 0, "human_stderr_bytes": 0, "forbidden_matches": 0}, "interrupt_probe": {"admitted_work_observed": True, "admitted_started": True, "command_interrupted": True, "durable_interrupted": True, "transcript_unchanged": True, "target_active_after": 0, "queue_depth_after": 0, "queued_item_started_events": 0, "admitted_item_processed_events": 0, "queued_item_discarded_events": 1, "audio_partial_playable": True, "late_frame_status": 409}},
        "account_product_regression": {"suites": [{"collected": 1, "executed": 1, "passed": 1, "failed": 0, "skipped": 0, "unmeasured": 0} for _ in range(4)]},
        "transcript_pane_fidelity": {"viewports": [{"width": 1440, "height": 900, "total_difference": 0.02, "largest_connected_difference": 0.01}, {"width": 1280, "height": 800, "total_difference": 0.02, "largest_connected_difference": 0.01}], "reference_identity": {"head": "6a8d0c1fafe8a1a8d6ea449036dd1ca330309d70", "clean": True}},
    }
    raw = values[predicate_id]
    if predicate_id in {"sentinel_absence", "operator_control", "two_session_capacity", "excess_admission_overload"}:
        units = ["moss-web.service"] if predicate_id == "operator_control" else ["moss-web.service", "moss-vllm.service"]
        raw["journal_sources"] = [
            {"source": "systemd-user-journal", "unit": unit, "baseline_cursor_observed": True,
             "read_succeeded": True, "entries": 0, "bytes": 0}
            for unit in units
        ]
    return raw


def _report(layer: str, sha: str, wheel: str) -> dict[str, object]:
    predicates = []
    for gate, predicate_ids in acceptance.EXTERNAL_REQUIREMENTS[layer].items():
        for predicate_id in predicate_ids:
            predicates.append({"gate": gate, "id": predicate_id, **_case(), "raw": _raw(predicate_id, sha, wheel)})
    return {"schema": acceptance.OBSERVATION_SCHEMA, "layer": layer, "candidate_sha": sha, "predicates": predicates}


@pytest.mark.parametrize("field,value", [
    ("first_tabs", 1), ("created_workspaces", 3), ("same_profile_owner", False),
    ("first_tab_lock_contention_observed", False),
    ("profiles_isolated", False), ("foreign_meeting_status", 200),
    ("mutation_without_cookie_status", 200), ("invalid_cookie_bootstrap_status", 200),
    ("cross_origin_status", 200), ("nonempty_saved_history", False),
    ("tls_trusted_without_interstitial", False),
    ("browser_restart_session_survived", False), ("history_survived_restart", False),
    ("workspace_url", "https://other.example/"),
    ("cookie_contract.cookie_secure", False), ("cookie_contract.cookie_http_only", False),
    ("cookie_contract.cookie_same_site", "None"),
    ("cookie_contract.javascript_cannot_read_cookie", False),
    ("tls_identity.trusted", False), ("tls_identity.subject", ""),
    ("tls_identity.subject_alt_names", []), ("tls_identity.not_after", ""),
])
def test_browser_workspace_gate_rejects_each_missing_invariant(field, value):
    raw = _raw("browser_workspace_identity", "a" * 40, "unused")
    def valid():
        return acceptance._validate_raw_predicate(
            "browser_workspace_identity", {"raw": raw},
            candidate_sha="a" * 40, candidate_tree="b" * 40,
            uv_lock_sha256="c" * 64, fixtures=FIXTURES,
            wheel_record_projection_sha256="d" * 64,
            dependency_projection_sha256="e" * 64,
        )
    assert valid()
    target = raw
    parts = field.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value
    assert not valid()
    del target[parts[-1]]
    assert not valid()


@pytest.mark.parametrize("mutation", ["schema", "sha", "missing_paths", "missing_audio", "relative_path"])
def test_revocation_snapshot_refuses_unbound_candidate_state(monkeypatch, tmp_path, mutation):
    from moss_transcribe_diarize import phase2_acceptance_external as external
    from moss_transcribe_diarize.phase2_cutover import RESTORE_PLAN_SCHEMA
    plan = {
        "schema": RESTORE_PLAN_SCHEMA, "candidate_sha": "a" * 40,
        "candidate_state_paths": {
            "database": str(tmp_path / "database.sqlite3"),
            "meeting_audio": str(tmp_path / "audio"),
        },
    }
    path = tmp_path / "restore-plan.json"
    path.write_text(json.dumps(plan))
    campaign = external.FixedAccountCampaign(
        candidate_sha="a" * 40, config={"cutover_restore_plan": str(path)},
    )
    calls = []
    monkeypatch.setattr(external, "_read_revocation_snapshot", lambda *args: calls.append(args) or {})
    assert campaign._revocation_snapshot("owner", ("meeting",)) == {}
    assert len(calls) == 1
    if mutation == "schema":
        plan["schema"] = "other"
    elif mutation == "sha":
        plan["candidate_sha"] = "b" * 40
    elif mutation == "missing_paths":
        del plan["candidate_state_paths"]
    elif mutation == "missing_audio":
        del plan["candidate_state_paths"]["meeting_audio"]
    else:
        plan["candidate_state_paths"]["database"] = "relative.sqlite3"
    path.write_text(json.dumps(plan))
    with pytest.raises(external.ExternalMeasurementError):
        campaign._revocation_snapshot("owner", ("meeting",))
    assert len(calls) == 1


@pytest.mark.parametrize("predicate_id", ["sentinel_absence", "operator_control", "two_session_capacity", "excess_admission_overload"])
@pytest.mark.parametrize("field,value", [
    ("unit", "unrelated.service"), ("source", "caller-log-file"),
    ("baseline_cursor_observed", False), ("read_succeeded", False),
    ("entries", -1), ("bytes", -1),
])
def test_log_dependent_gates_reject_unproven_service_journal(predicate_id, field, value):
    raw = _raw(predicate_id, "a" * 40, "unused")
    def valid():
        return acceptance._validate_raw_predicate(
            predicate_id, {"raw": raw}, candidate_sha="a" * 40, candidate_tree="b" * 40,
            uv_lock_sha256="c" * 64, fixtures=FIXTURES,
            wheel_record_projection_sha256="d" * 64, dependency_projection_sha256="e" * 64,
        )
    assert valid()
    raw["journal_sources"][0][field] = value
    assert not valid()
    del raw["journal_sources"]
    assert not valid()


def test_external_predicates_recompute_exact_raw_bounds_and_reject_summary_only():
    sha = "a" * 40
    wheel = "b" * 64
    report = _report("deployed", sha, wheel)
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert all(outcomes.values())
    assert errors == []

    capacity = next(item for item in report["predicates"] if item["id"] == "two_session_capacity")
    capacity["raw"]["session_observations"][0]["lags"] = [10.000001]
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is False
    assert "deployed:G4:two_session_capacity:failed" in errors

    report = _report("deployed", sha, wheel)
    capacity = next(
        item for item in report["predicates"] if item["id"] == "two_session_capacity"
    )
    for session in capacity["raw"]["session_observations"]:
        session["events"] = [
            event
            for event in session["events"]
            if event["kind"] not in {"canonical_queued", "canonical_started"}
        ]
    capacity["raw"].update(
        {
            "fairness_measured": False,
            "dispatch_skew": 0,
            "fairness_observation": {
                "applicability": "not_applicable",
                "passes": None,
                "contended_pair_dispatch_observations": 0,
                "maximum_contended_pair_dispatch_skew": 0,
            },
        }
    )
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is False
    assert "deployed:G4:two_session_capacity:failed" in errors

    report = _report("deployed", sha, wheel)
    capacity = next(item for item in report["predicates"] if item["id"] == "two_session_capacity")
    capacity["raw"]["session_observations"].pop()
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    quality["raw"]["macro"]["final_wer"] = math.nan
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is False
    assert "deployed:G4:two_session_capacity:failed" in errors
    assert "deployed:G4:quality_corpus:failed" in errors

    report = _report("deployed", sha, wheel)
    identity = next(item for item in report["predicates"] if item["id"] == "installed_candidate_identity")
    identity["raw"]["candidate_tree"] = "e" * 40
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G0"] is False
    assert "deployed:G0:installed_candidate_identity:failed" in errors

    report = _report("deployed", sha, wheel)
    identity = next(
        item for item in report["predicates"] if item["id"] == "installed_candidate_identity"
    )
    del identity["raw"]["manifest"]["release_admin_launcher_sha256"]
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G0"] is False
    assert "deployed:G0:installed_candidate_identity:failed" in errors

    # The launcher runs `<release>/bin/python -I -m ...`; a different interpreter must not
    # satisfy the installed-candidate identity even when every hash matches.
    report = _report("deployed", sha, wheel)
    identity = next(
        item for item in report["predicates"] if item["id"] == "installed_candidate_identity"
    )
    identity["raw"]["process"]["argv"][0] = "/usr/bin/python3.12"
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G0"] is False
    assert "deployed:G0:installed_candidate_identity:failed" in errors

    report = _report("deployed", sha, wheel)
    identity = next(
        item for item in report["predicates"] if item["id"] == "installed_candidate_identity"
    )
    identity["raw"]["process"]["argv"][3] = "moss_transcribe_diarize.app.web_cli"
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G0"] is False
    assert "deployed:G0:installed_candidate_identity:failed" in errors

    report = _report("deployed", sha, wheel)
    matrix = next(item for item in report["predicates"] if item["id"] == "cross_owner_matrix")
    matrix["raw"]["cases"][0]["owner_state_unchanged"] = False
    sentinel = next(item for item in report["predicates"] if item["id"] == "sentinel_absence")
    sentinel["raw"]["surfaces"].pop()
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G1"] is False
    assert "deployed:G1:cross_owner_matrix:failed" in errors
    assert "deployed:G1:sentinel_absence:failed" in errors

    report = _report("deployed", sha, wheel)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    quality["raw"]["per_case"][0]["metrics"]["final"]["wer"] = 1.0
    overload = next(
        item for item in report["predicates"] if item["id"] == "excess_admission_overload"
    )
    overload["raw"]["wrong_owner_observations"].pop()
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is False
    assert "deployed:G4:quality_corpus:failed" in errors
    assert "deployed:G4:excess_admission_overload:failed" in errors

    report = _report("deployed", sha, wheel)
    oauth = next(item for item in report["predicates"] if item["id"] == "browser_workspace_identity")
    oauth["raw"]["workspace_url"] = "https://other.example/"
    operator = next(item for item in report["predicates"] if item["id"] == "operator_control")
    operator["raw"]["interrupt_probe"]["admitted_item_processed_events"] = 1
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G2"] is False
    assert outcomes["G6"] is False
    assert "deployed:G2:browser_workspace_identity:failed" in errors
    assert "deployed:G6:operator_control:failed" in errors

    report = _report("deployed", sha, wheel)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    quality["raw"]["input_identities"][0]["checks"]["wav_sha256"] = False
    crash = next(item for item in report["predicates"] if item["id"] == "crash_recovery")
    crash["raw"]["audio_prefix_failures"] = 1
    operator = next(item for item in report["predicates"] if item["id"] == "operator_control")
    operator["raw"]["interrupt_probe"]["queued_item_discarded_events"] = 0
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha=sha,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G3"] is False
    assert outcomes["G4"] is False
    assert outcomes["G6"] is False


def test_external_denominators_expose_exact_campaign_units_and_fail_units_together():
    report = _report("deployed", "a" * 40, "b" * 64)
    projection = acceptance.external_denominator_projection(report)
    assert {
        name: values["collected"] for name, values in projection.items()
    } == {
        "cross_owner_actions": 15,
        "two_session_capacity": 2,
        "excess_admission_overload": 2,
        "quality_sessions": 12,
        "quality_windows": 122,
    }
    assert all(values["passed"] == values["collected"] for values in projection.values())

    capacity = next(
        item for item in report["predicates"] if item["id"] == "two_session_capacity"
    )
    capacity["raw"]["fairness_measured"] = False
    failed = acceptance.external_denominator_projection(report)
    assert failed["two_session_capacity"] == {
        "collected": 2,
        "executed": 2,
        "passed": 0,
        "failed": 2,
        "skipped": 0,
        "unmeasured": 0,
    }


def test_cross_layer_identity_binds_manifested_release_and_process():
    first = _report("deployed", "a" * 40, "b" * 64)
    second = _report("pre_admission", "a" * 40, "b" * 64)
    assert acceptance._cross_layer_identity_errors(first, second) == []
    identity = next(
        item
        for item in second["predicates"]
        if item["id"] == "installed_candidate_identity"
    )
    identity["raw"]["manifest"]["release"] = "/srv/other-release"
    assert acceptance._cross_layer_identity_errors(first, second) == [
        "cross_layer_identity_mismatch:manifest"
    ]


def test_exact_output_identity_reaches_exclusive_attempt_claim(monkeypatch, tmp_path: Path):
    class ReachedAttemptClaim(RuntimeError):
        pass

    sha = "abcdef0" + "1" * 33
    monkeypatch.setattr(
        acceptance,
        "discover_candidate",
        lambda repo: {"git_sha": sha},
    )
    monkeypatch.setattr(
        acceptance,
        "AttemptBundle",
        lambda path: (_ for _ in ()).throw(ReachedAttemptClaim(str(path))),
    )
    output = (
        tmp_path
        / "evidence/phase2/wave-1/20260828T120000Z-abcdef0"
    )
    with pytest.raises(ReachedAttemptClaim, match="20260828T120000Z-abcdef0"):
        acceptance.run_acceptance(wave=1, output=output, repo=tmp_path)


def test_owner_state_digest_detects_same_shape_content_mutation():
    before = {
        "id": "meeting",
        "mode": "live",
        "status": "active",
        "title": "alpha",
        "title_source": "owner",
        "created_at_ms": 1,
        "updated_at_ms": 1,
        "transcript": {"version": 1, "segments": [{"speaker": "Speaker_1", "text": "alpha"}]},
        "audio": {"state": "partial", "byte_count": 100},
    }
    after = copy.deepcopy(before)
    after["title"] = "bravo"
    after["transcript"]["segments"][0]["text"] = "bravo"
    assert external._owner_state_digest(before) != external._owner_state_digest(after)


def test_candidate_owned_collector_derives_fresh_report_and_binds_raw_artifacts(tmp_path: Path):
    sha = "a" * 40
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir(mode=0o700)
    for gate, predicate_ids in acceptance.EXTERNAL_REQUIREMENTS["deployed"].items():
        for predicate_id in predicate_ids:
            payload = {
                "schema": RAW_SCHEMA,
                "layer": "deployed",
                "candidate_sha": sha,
                "gate": gate,
                "id": predicate_id,
                "samples": [{"id": f"{predicate_id}-1", "executed": True, "passed": True}],
                "raw": _raw(predicate_id, sha, "unused"),
            }
            (raw_dir / f"deployed--{gate}--{predicate_id}.json").write_text(
                json.dumps(payload), encoding="utf-8"
            )
    (raw_dir / "measurement-state.json").write_text(
        json.dumps(
            {
                "schema": "moss-phase2-fixed-measurement.v1",
                "layer": "deployed",
                "candidate_sha": sha,
                "campaign_artifacts": [],
            }
        ),
        encoding="utf-8",
    )

    report = collect_layer(layer="deployed", candidate_sha=sha, raw_dir=raw_dir)
    output = tmp_path / "report.json"
    write_collected_report(report, output)
    with pytest.raises(FileExistsError):
        write_collected_report(report, output)
    bundle = acceptance.AttemptBundle(tmp_path / "attempt")
    assert acceptance._capture_collector_artifacts(
        report,
        layer="deployed",
        raw_dir=raw_dir,
        bundle=bundle,
        forbidden=(),
    ) == []
    bundle.close()
    assert len(
        tuple(
            (tmp_path / "attempt" / "raw" / "deployed-collector").glob(
                "deployed--*.json"
            )
        )
    ) == sum(len(value) for value in acceptance.EXTERNAL_REQUIREMENTS["deployed"].values())
    first = next(raw_dir.glob("deployed--*.json"))
    duplicated = json.loads(first.read_text(encoding="utf-8"))
    duplicated["samples"].append(dict(duplicated["samples"][0]))
    first.write_text(json.dumps(duplicated), encoding="utf-8")
    with pytest.raises(ValueError, match="raw sample is incomplete"):
        collect_layer(layer="deployed", candidate_sha=sha, raw_dir=raw_dir)


@pytest.mark.parametrize("parent_exists", [False, True])
def test_fixed_measurement_creates_raw_itself_and_missing_prerequisites_are_unmeasured(
    tmp_path: Path, parent_exists,
):
    raw_dir = tmp_path / "fresh-workspace" / "raw"
    if parent_exists:
        raw_dir.parent.mkdir(mode=0o755)
    state = measure_layer(
        layer="deployed",
        candidate_sha="a" * 40,
        config={},
        raw_dir=raw_dir,
    )
    assert raw_dir.parent.stat().st_mode & 0o777 == 0o700
    assert raw_dir.stat().st_mode & 0o777 == 0o700
    assert state["qualified"] is False
    assert state["counts"] == {
        "required": 16,
        "executed": 0,
        "passed": 0,
        "failed": 0,
        "unmeasured": 16,
    }
    report = collect_layer(
        layer="deployed", candidate_sha="a" * 40, raw_dir=raw_dir
    )
    assert all(
        predicate["counts"]["unmeasured"] == 1
        and predicate["counts"]["executed"] == 0
        for predicate in report["predicates"]
    )
    outcomes, errors = acceptance.evaluate_external_report(
        report,
        layer="deployed",
        candidate_sha="a" * 40,
        candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64,
        dependency_projection_sha256="e" * 64,
    )
    assert not any(outcomes.values())
    assert errors
    with pytest.raises(FileExistsError):
        measure_layer(
            layer="deployed",
            candidate_sha="a" * 40,
            config={},
            raw_dir=raw_dir,
        )


def test_fixed_measurement_runs_every_candidate_owned_producer_then_cleanup_and_zero(
    monkeypatch, tmp_path: Path,
):
    calls: list[str] = []

    class FakeCampaign:
        def __init__(self, *, candidate_sha: str, config: object) -> None:
            assert candidate_sha == "a" * 40
            self.root = tmp_path / "campaign"
            self.root.mkdir()
            artifact = self.root / "safe" / "counts.json"
            artifact.parent.mkdir()
            artifact.write_text('{"count": 1}\n', encoding="utf-8")

        @property
        def artifact_root(self) -> Path:
            return self.root

        @property
        def safe_artifacts(self) -> tuple[Path, ...]:
            return (Path("safe/counts.json"),)

        def cleanup(self) -> None:
            calls.append("cleanup")

        def close(self) -> None:
            calls.append("close")

        def __getattr__(self, name: str):
            if name not in measurement.PREDICATE_FAMILY:
                raise AttributeError(name)

            def run() -> dict[str, object]:
                calls.append(name)
                return {"producer": name}

            return run

    monkeypatch.setattr(measurement, "FixedAccountCampaign", FakeCampaign)
    config = {
        prerequisite.key: "supplied"
        for requirements in measurement.PREDICATE_PREREQUISITES.values()
        for prerequisite in requirements
    }
    raw_dir = tmp_path / "attempt" / "raw"
    state = measure_layer(
        layer="deployed",
        candidate_sha="a" * 40,
        config=config,
        raw_dir=raw_dir,
    )
    required = [
        predicate_id
        for gate, predicate_ids in acceptance.EXTERNAL_REQUIREMENTS["deployed"].items()
        for predicate_id in predicate_ids
        if predicate_id not in {"zero_work_end", "revocation_lifecycle"}
    ]
    required.extend(("revocation_lifecycle", "cleanup", "zero_work_end", "close"))
    assert calls == required
    assert state["qualified"] is True
    assert state["counts"] == {
        "required": 16,
        "executed": 16,
        "passed": 16,
        "failed": 0,
        "unmeasured": 0,
    }
    assert state["campaign_artifacts"] == ["safe/counts.json"]
    copied = raw_dir / "artifacts" / "safe" / "counts.json"
    assert copied.read_text(encoding="utf-8") == '{"count": 1}\n'
    assert stat.S_IMODE(copied.stat().st_mode) == 0o600


@pytest.mark.parametrize("failure", [RuntimeError("injected producer failure"), FileNotFoundError(2, "No such file or directory", "/tmp/missing-browser")])
def test_fixed_measurement_failure_still_runs_cleanup_zero_and_closes(
    monkeypatch, tmp_path: Path, failure,
):
    calls: list[str] = []

    class FailingCampaign:
        safe_artifacts: tuple[Path, ...] = ()

        def __init__(self, **_: object) -> None:
            self.artifact_root = tmp_path / "campaign"

        def cleanup(self) -> None:
            calls.append("cleanup")

        def close(self) -> None:
            calls.append("close")

        def __getattr__(self, name: str):
            if name not in measurement.PREDICATE_FAMILY:
                raise AttributeError(name)

            def run() -> dict[str, object]:
                calls.append(name)
                if name == "operator_control":
                    raise failure
                return {"producer": name}

            return run

    monkeypatch.setattr(measurement, "FixedAccountCampaign", FailingCampaign)
    config = {
        prerequisite.key: "supplied"
        for requirements in measurement.PREDICATE_PREREQUISITES.values()
        for prerequisite in requirements
    }
    state = measure_layer(
        layer="deployed",
        candidate_sha="a" * 40,
        config=config,
        raw_dir=tmp_path / "attempt" / "raw",
    )
    assert state["qualified"] is False
    assert state["counts"]["failed"] == 1
    assert calls[-3:] == ["cleanup", "zero_work_end", "close"]
    record = json.loads(next((tmp_path / "attempt/raw").glob("*operator_control*.json")).read_text())["raw"]
    assert record["failure_type"] == type(failure).__name__
    assert record["failure_operation"].endswith(":run")


def test_real_g0_identity_and_zero_producers_use_fixed_product_observations(
    monkeypatch, tmp_path: Path,
):
    release = tmp_path / "release"
    release_bin = release / "bin"
    release_bin.mkdir(parents=True)
    launcher = release_bin / "mtd-account-web"
    admin_launcher = release_bin / "mtd-admin"
    cutover_launcher = release_bin / "mtd-phase2-cutover"
    vllm_launcher = release_bin / "mtd-vllm"
    launcher.write_bytes(b"reviewed launcher\n")
    admin_launcher.write_bytes(b"reviewed admin\n")
    cutover_launcher.write_bytes(b"reviewed cutover\n")
    vllm_launcher.write_bytes(b"reviewed vllm\n")
    shared_python = tmp_path / "python3.12"
    shared_python.write_bytes(b"runtime\n")
    (release_bin / "python").symlink_to(shared_python)
    checkout = tmp_path / "checkout"
    unit_sources = checkout / "ops/systemd"
    unit_sources.mkdir(parents=True)
    web_unit = unit_sources / "moss-web.service"
    vllm_unit = unit_sources / "moss-vllm.service"
    web_unit.write_bytes(b"web unit\n")
    vllm_unit.write_bytes(b"vllm unit\n")
    fake_home = tmp_path / "home"
    pointer = fake_home / ".local/share/moss-transcribe-diarize/account-current"
    pointer.parent.mkdir(parents=True)
    pointer.symlink_to(release)
    installed_units = fake_home / ".config/systemd/user"
    installed_units.mkdir(parents=True)
    (installed_units / "moss-web.service").write_bytes(web_unit.read_bytes())
    (installed_units / "moss-vllm.service").write_bytes(vllm_unit.read_bytes())
    manifest = tmp_path / "candidate.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "moss-account-candidate.v1",
                "activation_state": "staged_inert",
                "git_sha": "a" * 40,
                "git_tree": "b" * 40,
                "uv_lock_sha256": "c" * 64,
                "fixtures": FIXTURES,
                "installed_record": {
                    "record_verified": True,
                    "record_entries_verified": 12,
                },
                "wheel_record_projection_sha256": "d" * 64,
                "dependency_projection": {
                    "sha256": "e" * 64,
                    "packages": [
                        {"name": "aiosqlite", "version": "0.22.1"},
                    ],
                },
                "sqlite_runtime": "3.53.4",
                "release": str(release),
                "release_launcher": str(launcher),
                "release_launcher_sha256": hashlib.sha256(
                    launcher.read_bytes()
                ).hexdigest(),
                "release_admin_launcher": str(admin_launcher),
                "release_admin_launcher_sha256": hashlib.sha256(
                    admin_launcher.read_bytes()
                ).hexdigest(),
                "release_cutover_launcher": str(cutover_launcher),
                "release_cutover_launcher_sha256": hashlib.sha256(
                    cutover_launcher.read_bytes()
                ).hexdigest(),
                "release_vllm_launcher": str(vllm_launcher),
                "release_vllm_launcher_sha256": hashlib.sha256(
                    vllm_launcher.read_bytes()
                ).hexdigest(),
                "qualification_checkout": str(checkout),
                "web_unit_path": str(web_unit),
                "web_unit_sha256": hashlib.sha256(web_unit.read_bytes()).hexdigest(),
                "vllm_unit_path": str(vllm_unit),
                "vllm_unit_sha256": hashlib.sha256(vllm_unit.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    fixture = tmp_path / "fixture.wav"
    fixture.write_bytes(b"fixture")
    descriptor = {
        "source_revision": "a" * 40,
        "provider_name": "provider",
        "provider_revision": "revision",
        "provider_manifest_hash": "f" * 64,
        "schema_version": "schema",
        "live_protocol_version": "protocol",
        "sample_rate": 16_000,
        "frame_samples": 8_000,
        "bounds": {"limit": 4},
        "config_hashes": {"combined_config_hash": "1" * 64},
    }

    class IdentityClient:
        def json(self, *_: object, **__: object):
            return {"descriptor": descriptor}, _Response(
                200, headers={"X-MOSS-Candidate-SHA": "a" * 40}
            )

        def close(self) -> None:
            pass

    campaign = _campaign(
        tmp_path,
        candidate_manifest=str(manifest),
        url_fixture=acceptance.QUALIFICATION_URL_FIXTURE,
        file_fixture=str(fixture),
        chrome_binary=str(fixture),
        https_origin="https://moss.example",
        operator_socket=str(tmp_path / "operator.sock"),
    )
    campaign._clients["a"] = IdentityClient()
    monkeypatch.setattr(Path, "home", lambda: fake_home)
    def run_identity_command(argv, **kwargs):
        if tuple(argv[:4]) == ("git", "-C", str(checkout), "rev-parse"):
            return SimpleNamespace(returncode=0, stdout="a" * 40 + "\n")
        if tuple(argv[:4]) == ("git", "-C", str(checkout), "status"):
            return SimpleNamespace(returncode=0, stdout="")
        return SimpleNamespace(returncode=0, stdout="123\n")

    monkeypatch.setattr(external.subprocess, "run", run_identity_command)
    original_readlink = os.readlink
    monkeypatch.setattr(
        external.os,
        "readlink",
        lambda path: (
            str(shared_python)
            if str(path) in {"/proc/123/cwd", "/proc/123/exe"}
            else original_readlink(path)
        ),
    )
    original_read_bytes = Path.read_bytes

    def read_bytes(path: Path) -> bytes:
        if str(path) == "/proc/123/cmdline":
            return (
                str(pointer / "bin/python").encode()
                + b"\0-I\0-m\0moss_transcribe_diarize.app.phase2_web_cli\0"
            )
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(external, "_file_fixture_identity", lambda path: {"sha256": "2" * 64})
    monkeypatch.setattr(external, "_toolchain_identity", lambda path: {"chrome": "fixed"})
    monkeypatch.setattr(external, "_accelerator_identity", lambda pid: {"vllm": "fixed"})
    monkeypatch.setattr(external, "_tls_identity", lambda origin: {"trusted": True})
    monkeypatch.setattr(external, "_unit_pid", lambda unit: 456)
    identity = campaign.installed_candidate_identity()
    assert identity["candidate_sha"] == "a" * 40
    assert identity["process"] == {
        "pid": 123,
        "cwd": str(shared_python),
        "exe": str(shared_python),
        "interpreter": {"invoked": str(pointer / "bin/python"), "release_path": str(release_bin / "python"), "executable": str(shared_python)},
        "argv": [
            str(pointer / "bin/python"),
            "-I",
            "-m",
            "moss_transcribe_diarize.app.phase2_web_cli",
        ],
    }
    assert identity["manifest"]["installed_units_match_manifest"] is True
    raw = _raw("installed_candidate_identity", "a" * 40, "wheel")
    raw["process"] = identity["process"]
    raw["manifest"]["release"] = str(release)
    for name in ("release_launcher", "release_admin_launcher", "release_cutover_launcher", "release_vllm_launcher"):
        raw["manifest"][name] = raw["manifest"][name].replace("/srv/release", str(release))
    assert acceptance._validate_raw_predicate(
        "installed_candidate_identity", {"raw": raw}, candidate_sha="a" * 40,
        candidate_tree="c" * 40, uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    )
    foreign_bin = tmp_path / "foreign-release/bin"
    foreign_bin.mkdir(parents=True)
    (foreign_bin / "python").symlink_to(shared_python)
    approved_argv = identity["process"]["argv"]
    for refused_argv in (
        [approved_argv[0], "-m", approved_argv[3]],
        [str(tmp_path / "foreign-python"), *approved_argv[1:]],
        [str(foreign_bin / "python"), *approved_argv[1:]],
        [*approved_argv[:3], "moss_transcribe_diarize.app.phase1_web_cli"],
    ):
        def refused_cmdline(path: Path) -> bytes:
            if str(path) == "/proc/123/cmdline":
                return b"\0".join(item.encode() for item in refused_argv) + b"\0"
            return original_read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", refused_cmdline)
        with pytest.raises(external.ExternalMeasurementError, match="outside the manifested release"):
            campaign.installed_candidate_identity()
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    (installed_units / "moss-web.service").write_bytes(b"mixed future restart unit\n")
    with pytest.raises(
        external.ExternalMeasurementError,
        match="installed service unit differs",
    ):
        campaign.installed_candidate_identity()
    (installed_units / "moss-web.service").write_bytes(web_unit.read_bytes())
    pointer.unlink()
    other_release = tmp_path / "other-release"
    other_release.mkdir()
    pointer.symlink_to(other_release)
    with pytest.raises(
        external.ExternalMeasurementError,
        match="running Account release does not match",
    ):
        campaign.installed_candidate_identity()
    monkeypatch.setattr(
        external,
        "_control",
        lambda *args, **kwargs: {
            "capacity": {
                "live": {"active": 0},
                "file": {"active": 0},
                "queues": {"live": 0, "batch": 0},
            }
        },
    )
    assert campaign.zero_work_end() == {
        "active_live": 0,
        "active_file": 0,
        "queue_depths": {"live": 0, "batch": 0},
    }


def test_real_g1_and_g2_producers_cross_fixed_client_and_browser_seams(
    monkeypatch, tmp_path: Path,
):
    sentinel = tmp_path / "a-sentinel"
    sentinel.write_text("account-a-sentinel", encoding="utf-8")
    owner_state = {
        "id": "meeting-a",
        "mode": "live",
        "status": "active",
        "title": "account-a-sentinel",
        "title_source": "owner",
        "created_at_ms": 1,
        "updated_at_ms": 1,
        "transcript": {"version": 0, "segments": []},
        "audio": {"state": "unavailable"},
    }

    class Client:
        def __init__(self, status: int) -> None:
            self.status = status

        def json(self, method: str, path: str, expected: int, **kwargs: object):
            del method, expected, kwargs
            if path.startswith("/api/meetings/meeting-a"):
                return dict(owner_state), _Response(200, owner_state)
            if path == "/api/auth/session":
                return {"workspace_id": "disposable-probe"}, _Response(200)
            return {"meetings": []}, _Response(200, {"meetings": []})

        def request(self, method: str, path: str, **kwargs: object):
            del kwargs
            if method == "PUT" and path.endswith("/title"):
                return _Response(200)
            if self.status == 200:
                payload = owner_state if "meeting-a" in path else {"meetings": []}
                return _Response(200, payload)
            return _Response(self.status)

        def close(self) -> None:
            pass

    campaign = _campaign(
        tmp_path,
        https_origin="https://moss.example",
        account_a_sentinel_file=str(sentinel),
        operator_socket=str(tmp_path / "operator.sock"),
    )
    campaign._live["a"] = "meeting-a"
    campaign._clients.update(
        {
            "a": Client(200),
            "a_peer": Client(200),
            "b": Client(404),
            "revoked_probe": Client(401),
        }
    )
    monkeypatch.setattr(external.httpx, "Client", lambda **kwargs: Client(401))
    revoked_owners = []
    monkeypatch.setattr(external, "_control", lambda socket, command, owner: revoked_owners.append((command, owner)) or {"revoked": True})
    matrix = campaign.cross_owner_matrix()
    assert revoked_owners == [("accounts.revoke", "disposable-probe")]
    assert [item["id"] for item in matrix["cases"]] == list(
        acceptance.G1_CROSS_OWNER_MATRIX
    )
    assert all(item["owner_state_unchanged"] for item in matrix["cases"])
    assert campaign.same_account_convergence() == {
        "clients": 2,
        "observations": 4,
        "mismatches": 0,
    }

    oauth = _raw("browser_workspace_identity", "a" * 40, "unused")

    class Browser:
        def browser_workspace_identity(self, control):
            assert control("status") == {"ok": True}
            return oauth

    campaign._browser = Browser()
    monkeypatch.setattr(external, "_control", lambda *args, **kwargs: {"ok": True})
    assert campaign.browser_workspace_identity() == oauth
    assert Path("browser/workspace-identity.json") in campaign.safe_artifacts


@pytest.mark.parametrize("regression", [None, "failed", "interrupted", "empty_transcript", "global_revoke", "changed_peer"])
def test_real_sentinel_and_revocation_producers_measure_both_accounts_and_durable_prefix(
    monkeypatch, tmp_path: Path, regression,
):
    a_sentinel = tmp_path / "a-sentinel"
    b_sentinel = tmp_path / "b-sentinel"
    a_sentinel.write_text("alpha-sentinel", encoding="utf-8")
    b_sentinel.write_text("bravo-sentinel", encoding="utf-8")
    empty = tmp_path / "empty.log"
    empty.write_text("", encoding="utf-8")
    fixture = tmp_path / "fixture.wav"
    fixture.write_bytes(b"fixture")
    audio_bodies = {"audio-a": b"mp3-alpha", "audio-b": b"mp3-bravo"}
    peer_saved = {"id": "peer-file", "status": "completed", "transcript": {"segments": [{"text": "saved peer"}]}}

    class Client:
        def __init__(self, owner: str) -> None:
            self.owner = owner
            self.logged_out = False

        def json(self, method: str, path: str, expected: int, **kwargs: object):
            del method, expected, kwargs
            if self.logged_out and path != "/api/workspace/bootstrap":
                raise external.ExternalMeasurementError("Workspace HTTP returned 401")
            if path.endswith("peer-file"):
                result = copy.deepcopy(peer_saved)
                if regression == "changed_peer":
                    result["transcript"]["segments"][0]["text"] = "wrong"
                return result, _Response(200)
            if path == "/api/auth/session":
                return {"workspace_id": "owner-b"}, _Response(200)
            if path == "/api/workspace/bootstrap":
                response = _Response(200)
                response.cookies = {external.SESSION_COOKIE: "new-browser-credential"}
                return {"workspace_id": "new-owner"}, response
            if path.endswith("b-file"):
                return {"status": "active"}, _Response(200)
            if path.endswith("live-b"):
                return {
                    "id": "live-b",
                    "status": "active",
                    "transcript_version": 1,
                    "transcript": {"segments": [{"text": "durable"}]},
                }, _Response(200)
            return {}, _Response(200)

        def request(self, method: str, path: str, **kwargs: object):
            cookie = kwargs.get("headers", {}).get("Cookie")
            if cookie == "":
                return _Response(401)
            if cookie == external.SESSION_COOKIE + "=new-browser-credential":
                return _Response(404)
            if self.logged_out:
                return _Response(401)
            if "/audio/download" in path:
                meeting_id = path.split("/")[3]
                own = meeting_id == f"audio-{self.owner}"
                return _Response(200, content=audio_bodies[meeting_id]) if own else _Response(404)
            own = (
                a_sentinel.read_bytes() + b" transcript-alpha"
                if self.owner == "a"
                else b_sentinel.read_bytes() + b" transcript-bravo"
            )
            return _Response(200, content=own)

        def close(self) -> None:
            pass

    campaign = _campaign(
        tmp_path,
        account_a_sentinel_file=str(a_sentinel),
        account_b_sentinel_file=str(b_sentinel),
        account_a_cookie_file=str(empty),
        account_b_cookie_file=str(empty),
        operator_socket=str(tmp_path / "operator.sock"),
        operator_journal=str(empty),
        server_log=str(empty),
        llm_prompt_log=str(empty),
        file_fixture=str(fixture),
    )
    clients = {name: Client(name[0]) for name in ("a", "a_peer", "b", "b_peer")}
    campaign._clients.update(clients)
    campaign._live.update({"a": "live-a", "b": "live-b"})
    monkeypatch.setattr(
        campaign,
        "_seed_live_transcript",
        lambda owner, meeting_id, clip: f"transcript-{owner}".encode(),
    )
    monkeypatch.setattr(
        campaign,
        "_seed_audio_sentinel",
        lambda owner, clip: (
            f"audio-{owner}",
            hashlib.sha256(audio_bodies[f"audio-{owner}"]).digest(),
        ),
    )
    monkeypatch.setattr(
        campaign,
        "_rendered_body",
        lambda cookie, meeting_id: (
            a_sentinel.read_bytes() + b" transcript-a"
            if meeting_id == "live-a"
            else b_sentinel.read_bytes() + b" transcript-b"
        ),
    )
    monkeypatch.setattr(external, "_control", lambda *args, **kwargs: {"content": "none"})
    sentinel = campaign.sentinel_absence()
    assert len(sentinel["audio_sentinel_checks"]) == 2
    assert all(item["foreign_matches"] == 0 for item in sentinel["surfaces"])

    monkeypatch.setattr(
        campaign,
        "_submit_file_for",
        lambda client, path: "peer-file" if client is clients["a_peer"] else "b-file",
    )
    monkeypatch.setattr(campaign, "_new_live_id", lambda owner: "live-b")
    monkeypatch.setattr(campaign, "_seed_live_transcript", lambda *args: b"durable")
    monkeypatch.setattr(
        campaign,
        "_await_meeting_terminal",
        lambda meeting_id, timeout=1800: (
            {**peer_saved, "status": regression} if regression in {"failed", "interrupted"}
            else {**peer_saved, "transcript": {"segments": []}} if regression == "empty_transcript"
            else copy.deepcopy(peer_saved)
        ),
    )

    def control(_socket: Path, command: str, email=None, **kwargs: object):
        del email, kwargs
        if command == "accounts.revoke":
            clients["b"].logged_out = clients["b_peer"].logged_out = True
            if regression == "global_revoke":
                clients["a"].logged_out = clients["a_peer"].logged_out = True
            return {"revoked": True}
        return {}

    monkeypatch.setattr(campaign, "_revocation_snapshot", lambda owner, ids: {
        "live-b": {
            "status": "interrupted", "version": 1,
            "document_json": json.dumps({"segments": [{"text": "durable"}]}),
            "audio_state": "partial", "audio_decodes": True,
            "audio_bytes": b"measured-audio", "byte_count": len(b"measured-audio"),
        },
        "b-file": {"status": "interrupted"},
    })
    monkeypatch.setattr(external, "_control", control)
    if regression is not None:
        with pytest.raises(external.ExternalMeasurementError):
            campaign.revocation_lifecycle()
        return
    closed_helpers = []
    from types import SimpleNamespace
    campaign._live_helpers.update({
        "live-b": ("b", SimpleNamespace(close=lambda: closed_helpers.append("live-b"))),
        "older-live-b": ("b", SimpleNamespace(close=lambda: closed_helpers.append("older-live-b"))),
        "live-a": ("a", SimpleNamespace(close=lambda: closed_helpers.append("live-a"))),
    })
    revoked = campaign.revocation_lifecycle()
    assert closed_helpers == ["live-b", "older-live-b"]
    assert set(campaign._live_helpers) == {"live-a"}
    assert revoked["failures"] == 0
    assert revoked["late_commits"] == 0
    assert revoked["durable_prefix_preserved"] is True


@pytest.mark.parametrize(
    "stop_status,failed_item_status,peer_status,rejection_count",
    [(200, "failed", "completed", 1), (409, "failed", "completed", 1),
     (200, "completed", "completed", 1), (200, "failed", "failed", 1),
     (200, "failed", "interrupted", 1), (200, "failed", "completed", 0),
     (200, "failed", "completed", 2)],
)
def test_real_g3_g4_and_g10_producers_use_fixed_browser_load_and_history_seams(
    monkeypatch, tmp_path: Path, stop_status: int, failed_item_status: str,
    peer_status: str, rejection_count: int,
):
    fixture = tmp_path / "fixture.wav"
    fixture.write_bytes(b"fixture")
    ordered = [
        {"path": "/api/meetings/file", "status": 201, "meeting_id": "file-1"},
        {"path": "/api/meetings/file", "status": 201, "meeting_id": "file-2"},
        {"path": "/api/meetings/url", "status": 201, "meeting_id": "url-1"},
        {
            "path": "/api/meetings/url",
            "status": 201,
            "meeting_id": "url-failed",
            "input_kind": "accepted_failure",
        },
        {"path": "/api/meetings/url", "status": 400},
        {"path": "/api/meetings/url", "status": 201, "meeting_id": "url-2"},
    ]
    meetings = [
        {
            "id": meeting_id,
            "status": "failed" if meeting_id == "url-failed" else "completed",
            "title": "fixture",
            "transcript": {"version": 1, "segments": [{"text": "words"}]},
            "audio": {"state": "available", "byte_count": 1},
        }
        for meeting_id in (
            "file-1",
            "file-2",
            "url-1",
            "url-failed",
            "url-2",
            "detached-file",
            "live-a",
        )
    ]

    # Pre-admission's separate audio-bearing abort is visible in owner history,
    # but must never enter the batch-isolation denominator.
    meetings.append({"id": "unrelated-partial", "status": "interrupted"})
    next(item for item in meetings if item["id"] == "url-failed")["status"] = failed_item_status
    next(item for item in meetings if item["id"] == "url-2")["status"] = peer_status
    ordered = [item for item in ordered if item["status"] != 400]
    ordered.extend({"path": "/api/meetings/url", "status": 400} for _ in range(rejection_count))

    class Client:
        def json(self, method: str, path: str, expected: int, **kwargs: object):
            del expected, kwargs
            if path == "/api/live/descriptor":
                return {"descriptor": {"frame_samples": 8000,
                        "bounds": {"max_retained_samples": 960000}}}, _Response(200)
            if method == "PUT":
                renamed = {**meetings[0], "title": "Wave 1 durable owner title"}
                meetings[0] = renamed
                return renamed, _Response(200, renamed)
            if path == "/api/meetings":
                return {"meetings": copy.deepcopy(meetings)}, _Response(200)
            return {}, _Response(200)

        def request(self, method: str, path: str, **kwargs: object):
            del kwargs
            if method == "POST" and path.endswith("/stop"):
                return _Response(stop_status)
            return _Response(200)

        def close(self) -> None:
            pass

    class Browser:
        def submit_file_url_batch(self, got_fixture: Path, url: str):
            assert got_fixture == fixture
            assert url == acceptance.QUALIFICATION_URL_FIXTURE
            return {
                "ordered": copy.deepcopy(ordered),
                "detached": {"meeting_id": "detached-file"},
            }

        def product_regression(self, active_id: str, completed_id: str):
            return {"active": active_id, "completed": completed_id, "suites": []}

        def transcript_fidelity(self, meeting: object):
            return {"meeting_present": bool(meeting), "viewports": []}

    campaign = _campaign(
        tmp_path,
        file_fixture=str(fixture),
        url_fixture=acceptance.QUALIFICATION_URL_FIXTURE,
    )
    campaign._live["a"] = "live-a"
    campaign._clients.update({"a": Client(), "a_peer": Client()})
    campaign._browser = Browser()
    terminal = {item["id"]: item for item in meetings}
    monkeypatch.setattr(
        campaign,
        "_await_meeting_terminal",
        lambda meeting_id, timeout=1800: copy.deepcopy(terminal[meeting_id]),
    )
    monkeypatch.setattr(campaign, "_await_service", lambda timeout=60: None)
    monkeypatch.setattr(
        external.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0),
    )
    if stop_status != 200:
        with pytest.raises(external.ExternalMeasurementError, match=r"Live Meeting did not Stop: HTTP 409 b?['\"]"):
            campaign.meeting_modes_history_restart()
        return
    result = campaign.meeting_modes_history_restart()
    assert result["one_item_failure_isolated"] is (
        failed_item_status == "failed" and peer_status == "completed" and rejection_count == 1
    )
    assert result["accepted_failure_meeting_id"] == "url-failed"
    assert result["terminal_states"] == {
        key: value["status"] for key, value in terminal.items()
        if key not in {"live-a", "unrelated-partial"}
    }
    assert result["submissions"]["input_boundary_rejection"] == rejection_count
    assert result["submissions"]["accepted_failure"] == 1
    assert "words" not in json.dumps(result)
    assert "fixture" not in json.dumps(result)
    if (failed_item_status, peer_status, rejection_count) != ("failed", "completed", 1):
        return
    assert result["submissions"] == {
        "single_file": 1,
        "multi_file": 2,
        "url": 2,
        "serial_batch": 6,
        "browser_closed_after_accept": 1,
        "accepted_failure": 1,
        "input_boundary_rejection": 1,
    }
    base_load = _capacity_raw()
    monkeypatch.setattr(
        campaign,
        "_run_live_load",
        lambda *, sessions, duration_seconds, embedded_backpressure=False: {
            **copy.deepcopy(base_load if sessions == 4 else _overload_raw()),
            "wrong_owner_probes": 1,
            "marker_isolation_failures": 0,
            "fairness_measured": True,
            **(
                {
                    "embedded_backpressure_observation": copy.deepcopy(
                        _overload_raw()["backpressure_observation"]
                    )
                }
                if embedded_backpressure
                else {}
            ),
        },
    )
    monkeypatch.setattr(
        campaign,
        "_backpressure_probe",
        lambda: {"observed_429": True, "peer_progress": True, "same_sequence_retry": True},
    )
    assert campaign.two_session_capacity()["continuous_wrong_owner_probes"] is True
    assert campaign.excess_admission_overload()["sessions"] == 2
    monkeypatch.setattr(campaign, "_new_live_id", lambda owner: "active-live")
    monkeypatch.setattr(
        campaign,
        "_durable_transcript_meeting",
        lambda: {"id": "completed", "transcript": {"segments": [{"text": "words"}]}},
    )
    assert campaign.account_product_regression()["active"] == "active-live"
    assert campaign.transcript_pane_fidelity()["meeting_present"] is True
    assert {
        Path("browser/product-suite-counts.json"),
        Path("browser/transcript-fidelity-metrics.json"),
    }.issubset(set(campaign.safe_artifacts))


def test_browser_batch_selector_executes_fixed_six_item_and_detached_contract(
    monkeypatch, tmp_path: Path,
):
    fixture = tmp_path / "fixture.wav"
    fixture.write_bytes(b"fixture")
    cookie = tmp_path / "cookie"
    cookie.write_text("cookie", encoding="utf-8")
    cookie.chmod(0o600)
    chrome = tmp_path / "chrome"
    chrome.write_text("binary", encoding="utf-8")
    origin = "https://moss.example"

    class Request:
        def __init__(self, path: str, payload: dict[str, object]) -> None:
            self.url = origin + path
            self.method = "POST"
            self.post_data_json = payload

    class Response:
        def __init__(self, path: str, status: int, meeting_id: str | None, payload: dict[str, object]):
            self.request = Request(path, payload)
            self.status = status
            self._body = {} if meeting_id is None else {"id": meeting_id}

        def json(self):
            return self._body

    first = (
        Response("/api/meetings/file", 201, "file-1", {}),
        Response("/api/meetings/file", 201, "file-2", {}),
        Response("/api/meetings/url", 201, "url-1", {"url": acceptance.QUALIFICATION_URL_FIXTURE}),
        Response("/api/meetings/url", 201, "url-failed", {"url": browser_measurement.ACCEPTED_FAILURE_URL}),
        Response("/api/meetings/url", 400, None, {"url": "not-a-supported-url"}),
        Response("/api/meetings/url", 201, "url-2", {"url": acceptance.QUALIFICATION_URL_FIXTURE}),
    )
    detached = (Response("/api/meetings/file", 201, "detached", {}),)

    class Locator:
        def __init__(self, page: "Page", emit: bool = False) -> None:
            self.page = page
            self.emit = emit

        def set_input_files(self, value: object) -> None:
            del value

        def fill(self, value: str) -> None:
            assert browser_measurement.ACCEPTED_FAILURE_URL in value

        def click(self) -> None:
            if self.emit:
                for response in self.page.responses:
                    self.page.callback(response)

    class Page:
        def __init__(self, responses: tuple[Response, ...]) -> None:
            self.responses = responses
            self.callback = lambda response: None

        def on(self, event: str, callback) -> None:
            assert event == "response"
            self.callback = callback

        def locator(self, selector: str) -> Locator:
            return Locator(self)

        def get_by_role(self, role: str, *, name: str) -> Locator:
            assert role == "button" and name == "Transcribe files and URLs"
            return Locator(self, emit=True)

        def wait_for_timeout(self, milliseconds: int) -> None:
            del milliseconds

    class Context:
        def __init__(self, responses: tuple[Response, ...]) -> None:
            self.page = Page(responses)

        def new_page(self) -> Page:
            return self.page

        def close(self) -> None:
            pass

    class Browser:
        def __init__(self) -> None:
            self.calls = 0

        def new_context(self, **kwargs: object) -> Context:
            del kwargs
            self.calls += 1
            return Context(first if self.calls == 1 else detached)

        def close(self) -> None:
            pass

    browser = Browser()

    class Playwright:
        chromium = SimpleNamespace(launch=lambda **kwargs: browser)

    class Manager:
        def __enter__(self):
            return Playwright()

        def __exit__(self, *args: object) -> None:
            pass

    monkeypatch.setattr(browser_measurement, "sync_playwright", lambda: Manager())
    monkeypatch.setattr(browser_measurement, "_add_cookie", lambda *args, **kwargs: None)
    monkeypatch.setattr(browser_measurement, "_wait_workspace", lambda *args, **kwargs: None)
    campaign = browser_measurement.BrowserCampaign(
        {
            "https_origin": origin,
            "chrome_binary": str(chrome),
            "account_a_cookie_file": str(cookie),
        },
        repo=ROOT,
        work=tmp_path / "work",
    )
    result = campaign.submit_file_url_batch(
        fixture, acceptance.QUALIFICATION_URL_FIXTURE
    )
    assert [item["input_kind"] for item in result["ordered"]] == [
        "file",
        "file",
        "url",
        "accepted_failure",
        "invalid",
        "url",
    ]
    assert result["detached"] == {"status": 201, "meeting_id": "detached"}


@pytest.mark.parametrize("corrupt_audio", [False, True])
@pytest.mark.parametrize("late_status", [409, 404, 200])
@pytest.mark.parametrize("kill_returncode", [0, 1])
@pytest.mark.parametrize("prefix_fault", [None, "zero_version", "empty_segments", "nested_version_only"])
def test_real_crash_producer_compares_recovered_bytes_to_production_archive_oracle(
    monkeypatch, tmp_path: Path, prefix_fault, kill_returncode, late_status, corrupt_audio,
):
    corpus = tmp_path / "corpus"
    case = corpus / "case"
    case.mkdir(parents=True)
    (corpus / "corpus-manifest.json").write_text(
        json.dumps({"cases": [{"case_id": "case"}]}), encoding="utf-8"
    )
    (case / "audio.wav").write_bytes(b"wav")
    cookie = tmp_path / "cookie"
    cookie.write_text("cookie", encoding="utf-8")
    cookie.chmod(0o600)
    restarted = False

    class Archive:
        def __init__(self, root: Path) -> None:
            self.root = root

        def publish_live_prefix(self, account: str, meeting: str, source: Path, *, partial: bool):
            del account, meeting
            assert partial is True and len(source.read_bytes()) == 16_000
            # System sample 1 mixed with silent microphone rounds to zero.
            assert source.read_bytes() == b"\0\0" * 8_000
            path = self.root / "audio.partial.mp3"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"expected-mp3")
            return SimpleNamespace(
                path=path,
                byte_count=len(b"expected-mp3"),
                duration_ms=500,
                format="mp3",
                sample_rate_hz=16_000,
                channels=1,
                bit_rate_bps=48_000,
            )

    class Adapter:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def create(self):
            return SimpleNamespace(
                session_id="crash",
                descriptor=SimpleNamespace(frame_samples=8_000),
            )

        def accept_frame(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def snapshot(self, meeting_id: str):
            del meeting_id
            return SimpleNamespace(session=SimpleNamespace(accepted_samples=8_000))

        @staticmethod
        def _lane_payload(*args: object, **kwargs: object):
            del args, kwargs
            return {}

    from moss_transcribe_diarize.app.phase2 import Meeting, _settled_transcript
    before = Meeting(
        meeting_id="crash", mode="live", title=None, status="active", created_at_ms=1,
        transcript={"segments": [{"id": "committed", "speaker": "S00", "text": "durable"}]}, transcript_version=1,
    ).to_dict()
    if prefix_fault == "zero_version":
        before["transcript_version"] = 0
    elif prefix_fault == "empty_segments":
        before["transcript"]["segments"] = []
    elif prefix_fault == "nested_version_only":
        before.pop("transcript_version")
        before["transcript"]["version"] = 1
    after = {
        **before,
        "status": "interrupted",
        "transcript": _settled_transcript(copy.deepcopy(before["transcript"])),
        "audio": {
            "state": "partial",
            "relative_path": "account/crash/audio.partial.mp3",
            "byte_count": len(b"expected-mp3"),
            "duration_ms": 500,
            "format": "mp3",
            "sample_rate_hz": 16_000,
            "channels": 1,
            "bit_rate_bps": 48_000,
        },
    }

    class Owner:
        def json(self, method: str, path: str, expected: int, **kwargs: object):
            del method, path, expected, kwargs
            return copy.deepcopy(after if restarted else before), _Response(200)

        def request(self, method: str, path: str, **kwargs: object):
            del method, kwargs
            if path.endswith("/audio/download"):
                return _Response(200, content=b"corrupt-mp3" if corrupt_audio else b"expected-mp3")
            if path.endswith("/frames"):
                return _Response(late_status)
            return _Response(200)

        def close(self) -> None:
            pass

    campaign = _campaign(
        tmp_path,
        quality_corpus=str(corpus),
        account_a_cookie_file=str(cookie),
        https_origin="https://moss.example",
    )
    campaign._clients["a"] = Owner()
    monkeypatch.setattr(external, "AccountCookieLiveReplayService", Adapter)
    monkeypatch.setattr(external, "MeetingAudioArchive", Archive)
    monkeypatch.setattr(external, "_wav_pcm", lambda path: b"\1\0" * 16_000)
    pids = iter((111, 222))
    monkeypatch.setattr(external, "_unit_pid", lambda unit, **kwargs: next(pids))

    def run(command: object, **kwargs: object):
        nonlocal restarted
        del kwargs
        if "kill" in command:
            restarted = True
        return SimpleNamespace(returncode=kill_returncode)

    monkeypatch.setattr(external.subprocess, "run", run)
    monkeypatch.setattr(external.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(campaign, "_await_service", lambda timeout=60: None)
    if prefix_fault:
        with pytest.raises(external.ExternalMeasurementError, match="did not establish a durable prefix"):
            campaign.crash_recovery()
        assert restarted is False
        return
    result = campaign.crash_recovery()
    assert result["resumed_capture"] == int(late_status == 200)
    assert result["audio_comparison"]["late_frame_status"] == late_status
    assert result["audio_prefix_failures"] == int(corrupt_audio)
    assert result["durable_document_mismatches"] == 0
    assert result["accepted_prefix_samples"] == 8_000
    assert result["process_replaced"] is True
    assert result["recovery"]["kill_returncode"] == kill_returncode
    assert result["recovery"]["ready"] is True
    assert json.loads((campaign.artifact_root / "crash-recovery-wait.json").read_text()) == result["recovery"]


def test_terminal_transcript_comparison_preserves_content_and_version():
    from moss_transcribe_diarize.app.phase2 import _settled_transcript

    before = {"transcript_version": 1, "transcript": {"segments": [
        {"id": "committed", "speaker": "S00", "text": "durable"},
    ]}}
    after = {"transcript_version": 1, "transcript": _settled_transcript(copy.deepcopy(before["transcript"]))}
    assert external._terminal_transcript_matches(before, after)
    after["transcript"]["segments"][0]["text"] = "changed"
    assert not external._terminal_transcript_matches(before, after)
    after["transcript"]["segments"][0]["text"] = "durable"
    after["transcript_version"] = 2
    assert not external._terminal_transcript_matches(before, after)


@pytest.mark.parametrize("stop_failure", [False, True])
@pytest.mark.parametrize("nondecoded_rolling", [False, True])
@pytest.mark.parametrize("terminal_final", [False, True])
def test_real_quality_producer_runs_exact_six_cases_twice_through_fixed_replay_seam(
    monkeypatch, tmp_path: Path, stop_failure: bool,
    nondecoded_rolling: bool, terminal_final: bool,
):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    cases = []
    for case_id in sorted(acceptance.QUALITY_CASE_IDS):
        directory = corpus / case_id
        directory.mkdir()
        (directory / "audio.wav").write_bytes(b"wav")
        (directory / "reference.jsonl").write_text(
            json.dumps({"start": 0, "end": 1, "speaker": "S1", "text": "REFERENCE PRIVATE"}) + "\n",
            encoding="utf-8",
        )
        cases.append({"case_id": case_id, "category": "speech"})
    (corpus / "corpus-manifest.json").write_text(
        json.dumps({"cases": cases}), encoding="utf-8"
    )
    cookies = []
    for name in ("a", "b"):
        path = tmp_path / f"{name}.cookie"
        path.write_text(name, encoding="utf-8")
        path.chmod(0o600)
        cookies.append(path)

    class Descriptor:
        source_revision = "a" * 40
        provider_manifest_hash = "b" * 64
        config_hashes = SimpleNamespace(combined_config_hash="c" * 64)

    class Adapter:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def descriptor(self):
            return Descriptor()

        def events(self, session_id):
            from moss_transcribe_diarize.app.live_service_runtime import LiveServiceEvent
            return [LiveServiceEvent(
                seq=9, session_id=session_id, kind="terminal_finalization_failed",
                snapshot_version=12, payload={
                    "runtime_monotonic_ns": 1234, "outcome": "decode_failed",
                    "reason": "WindowTranscriptionError", "refusal": "decode_failed",
                    "text": "PRIVATE TRANSCRIPT", "credential": "SECRET COOKIE",
                },
            )]

    class Capture:
        def __init__(self, adapter: object, **kwargs: object) -> None:
            del adapter, kwargs
            snapshot = {"session": {
                "accepted_samples": 320000 if terminal_final else 160000,
                "finalization_status": "final" if terminal_final else "failed",
                "identity_snapshot": {"canonical_speakers": ["speaker-0001"]},
                "effective_transcript": [
                    {"start_sample": 0, "end_sample": 4_000,
                     "canonical_speaker": None, "text": "PRIVATE TRANSCRIPT"},
                    {"start_sample": 4_000, "end_sample": 16_000,
                     "canonical_speaker": "speaker-0001", "text": "PRIVATE TRANSCRIPT"},
                ],
            }}
            self.captures = {
                "pre_stop_immediate": {"snapshot": snapshot},
                "pre_stop_settled": {"snapshot": snapshot},
                "post_stop_final": {"snapshot": snapshot},
            }
            self.stop_requested_monotonic_ns = 1

    class Surface:
        SurfaceCaptureService = Capture
        Case = lambda self, case_id, directory, reference: SimpleNamespace(id=case_id)
        speech_regions_from_wav = staticmethod(lambda audio: ((0.0, 1.0),))

        @staticmethod
        def transcript_rows(snapshot: object, duration: float):
            from moss_transcribe_diarize.live_speaker_accuracy import hypothesis_from_live_snapshot
            return [{"start": row.start, "end": row.end, "speaker": row.speaker,
                     "text": row.text} for row in hypothesis_from_live_snapshot(
                         {"snapshot": snapshot}, corpus_start_sample=0,
                         corpus_duration_sec=duration)]

        @staticmethod
        def score_surface(case: object, rows: object):
            del case, rows
            return {
                "wer": 0.1,
                "tbsa": 0.9,
                "der": 0.25,
                "content_recall": 0.95,
                "matched_word_speaker_accuracy": 0.95,
                "reference_speech_der": 0.25,
            }

        @staticmethod
        def read_service_events(trace: Path):
            del trace
            events = [{"kind": "rolling_decode_completed", "payload": {
                "outcome": "applied", "window_index": 0,
                "start_sample": 0, "end_sample": 160000,
            }}]
            if nondecoded_rolling:
                events.append({"kind": "rolling_decode_completed", "payload": {
                    "outcome": "not_awaited", "window_index": 1,
                    "start_sample": 160000, "end_sample": 320000,
                    "decode_failure": "session_terminal",
                }})
            if terminal_final:
                events.append({"kind": "text_revision_applied", "payload": {
                    "source": "terminal", "start_sample": 0, "end_sample": 320000,
                    "finalization_status": "final",
                }})
            return events

        @staticmethod
        def event_measurements(*args: object):
            del args
            return {"rolling_queue": {"windows": [1, 2] if nondecoded_rolling else [1]}}

    def replay(*, out_dir: Path, **kwargs: object) -> None:
        del kwargs
        trace = out_dir / "run-001" / "trace.jsonl"
        trace.parent.mkdir(parents=True)
        trace.write_text(
            json.dumps({"kind": "session_created", "session_id": "private-id"}) + "\n",
            encoding="utf-8",
        )
        if stop_failure:
            from moss_transcribe_diarize.live_service_replay import ServiceReplayTransportFailure
            raise ServiceReplayTransportFailure("controlled Stop failure")

    campaign = _campaign(
        tmp_path,
        repo_root=str(ROOT),
        quality_corpus=str(corpus),
        account_a_cookie_file=str(cookies[0]),
        account_b_cookie_file=str(cookies[1]),
        https_origin="https://moss.example",
    )
    monkeypatch.setattr(external, "AccountCookieLiveReplayService", Adapter)
    external._load_surface_harness(ROOT)
    monkeypatch.setattr(external, "_load_surface_harness", lambda repo: Surface())
    monkeypatch.setattr(external, "run_service_replay", replay)
    monkeypatch.setattr(external, "_wav_duration", lambda path: 1.0)
    monkeypatch.setattr(
        external,
        "_verify_quality_inputs",
        lambda **kwargs: [
            {
                "case_id": case_id,
                "checks": {"wav_sha256": True},
                "source_present": False,
                "source_audio_match": None,
                "source_reference_match": None,
            }
            for case_id in sorted(acceptance.QUALITY_CASE_IDS)
        ],
    )
    if stop_failure:
        from moss_transcribe_diarize.live_service_replay import ServiceReplayTransportFailure
        with pytest.raises(ServiceReplayTransportFailure, match="controlled Stop failure"):
            campaign.quality_corpus()
        assert Path("quality/content-free-metrics.json") not in campaign.safe_artifacts
        from moss_transcribe_diarize.phase2_acceptance_measure import _snapshot_campaign_artifacts
        import shutil
        raw_dir = tmp_path / "retained-raw"
        raw_dir.mkdir()
        copied = _snapshot_campaign_artifacts(campaign, raw_dir)
        shutil.rmtree(campaign.artifact_root)
        diagnostic = next(raw_dir / "artifacts" / path for path in copied
                          if path.endswith("terminal-diagnostics.json"))
        text = diagnostic.read_text()
        assert "PRIVATE TRANSCRIPT" not in text and "SECRET COOKIE" not in text
        evidence = json.loads(text)
        assert evidence["session_ids"] == ["private-id"]
        assert evidence["stop_requested_monotonic_ns"] == 1
        event = evidence["events"][0]
        assert event["session_id"] == "private-id"
        assert event["seq"] == 9 and event["runtime_monotonic_ns"] == 1234
        assert event["outcome"] == "decode_failed"
        assert event["reason"] == "WindowTranscriptionError"
        assert event["refusal"] == "decode_failed"
        return
    result = campaign.quality_corpus()
    assert result["cases"] == 6
    assert result["passes"] == 2
    assert result["sessions"] == 12
    assert len(result["per_case"]) == 12
    assert result["windows"] == 12
    assert all(row["windows"] == 1 for row in result["per_case"])
    assert all(row["window_coverage"] == {
        "planned_full_windows": 2 if terminal_final else 1,
        "rolling_decoded": 1,
        "terminal_only": 1 if terminal_final else 0,
        "uncovered": 0,
    } for row in result["per_case"])
    assert set(result["per_case"][0]["surface_observations"]) == {"pre_stop_immediate", "pre_stop_settled", "post_stop_final"}
    first = result["per_case"][0]
    assert first["settled_hypothesis_speaker_intervals"] == [
        {"start_sample": 0, "end_sample": 4_000, "speaker": "S00"},
        {"start_sample": 4_000, "end_sample": 16_000, "speaker": "named:speaker-0001"},
    ]
    assert first["reference_speaker_intervals"] == [
        {"start_sample": 0, "end_sample": 16_000, "speaker": "ref:01"},
    ]
    assert first["settled_der_s00_diagnostic"] == {
        "as_is": 0.25, "without_s00_confusion": 0.0, "s00_confusion_difference": 0.25,
        "s00_mapped_reference": [], "s00_mapped_correct_seconds": 0.0,
        "unattributed_der": 0.0,
        "reference_speech_as_is": 0.25,
        "reference_speech_without_s00_confusion": 0.0,
        "reference_speech_s00_confusion_difference": 0.25,
        "reference_speech_s00_mapped_correct_seconds": 0.0,
        "reference_speech_unattributed_der": 0.0,
    }
    assert result["macro"]["diarization_error_rate"] == 0.0
    assert result["macro"]["diarization_error_rate_raw"] == 0.25
    assert Path("quality/content-free-metrics.json") in campaign.safe_artifacts
    retained = (campaign.artifact_root / "quality/content-free-metrics.json").read_text()
    assert "PRIVATE TRANSCRIPT" not in retained
    assert "REFERENCE PRIVATE" not in retained
    assert '"text"' not in retained


@pytest.mark.parametrize("has_crash", [False, True])
def test_real_g5_audio_producer_reconciles_owner_foreign_partial_and_missing_artifact(
    monkeypatch, tmp_path: Path, has_crash,
):
    audio_root = tmp_path / "meetings"
    audio_root.mkdir(mode=0o700)
    payloads: dict[str, dict[str, object]] = {}
    bodies: dict[str, bytes] = {}
    for meeting_id, state in (("file", "available"), ("live", "available"), ("crash", "partial")):
        directory = audio_root / "account" / meeting_id
        directory.mkdir(mode=0o700, parents=True)
        directory.parent.chmod(0o700)
        directory.chmod(0o700)
        name = "audio.partial.mp3" if state == "partial" else "audio.mp3"
        path = directory / name
        path.write_bytes(f"mp3-{meeting_id}".encode())
        path.chmod(0o600)
        bodies[meeting_id] = path.read_bytes()
        payloads[meeting_id] = {
            "id": meeting_id,
            "status": "interrupted" if state == "partial" else "completed",
            "audio": {
                "state": state,
                "relative_path": path.relative_to(audio_root).as_posix(),
                "byte_count": len(bodies[meeting_id]),
                "duration_ms": 1000,
                "format": "mp3",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "bit_rate_bps": 48_000,
            },
        }
    out_dir = audio_root / "account" / "out"
    out_dir.mkdir(mode=0o700, parents=True)
    out_dir.parent.chmod(0o700)
    out_dir.chmod(0o700)
    out_path = out_dir / "audio.mp3"
    out_path.write_bytes(b"mp3-out")
    out_path.chmod(0o600)
    payloads["out"] = {
        "id": "out",
        "status": "completed",
        "audio": {
            "state": "available",
            "relative_path": out_path.relative_to(audio_root).as_posix(),
            "byte_count": len(b"mp3-out"),
            "duration_ms": 1000,
            "format": "mp3",
            "sample_rate_hz": 16_000,
            "channels": 1,
            "bit_rate_bps": 48_000,
        },
    }

    class Owner:
        def request(self, method: str, path: str, **kwargs: object):
            if path.endswith("/abort"):
                lifecycle.append("abort")
                return _Response(200)
            del method, kwargs
            meeting_id = path.split("/")[3]
            if meeting_id == "out" and not out_path.exists():
                return _Response(404)
            state = payloads[meeting_id]["audio"]["state"]
            return _Response(
                200,
                content=bodies.get(meeting_id, b"mp3-out"),
                headers={
                    "content-disposition": (
                        "attachment; filename=audio.partial.mp3"
                        if state == "partial"
                        else "attachment; filename=audio.mp3"
                    )
                },
            )

        def json(self, method: str, path: str, expected: int, **kwargs: object):
            del method, expected, kwargs
            meeting_id = path.split("/")[3]
            if meeting_id == "out" and not out_path.exists():
                payloads["out"] = {
                    **payloads["out"],
                    "audio": {"state": "unavailable"},
                }
            return copy.deepcopy(payloads[meeting_id]), _Response(200)

        def close(self) -> None:
            pass

    class Denied(Owner):
        def __init__(self, status: int) -> None:
            self.status = status

        def request(self, method: str, path: str, **kwargs: object):
            return _Response(self.status)

    fixture = tmp_path / "fixture.wav"
    fixture.write_bytes(b"fixture")
    campaign = _campaign(
        tmp_path,
        meeting_audio_root=str(audio_root),
        https_origin="https://moss.example",
        file_fixture=str(fixture),
    )
    campaign._meetings.update({"file": ["file"], "live": ["live"], "crash": ["crash"] if has_crash else []})
    lifecycle = []
    monkeypatch.setattr(campaign, "_new_live_id", lambda owner: "crash")
    # Exercise the actual helper, including owner/session/clip arguments and attach.
    seed_fixture = tmp_path / "prototypes/streaming-diarization/concurrency/cpu_hf_local_fixture.json"
    seed_fixture.parent.mkdir(parents=True)
    seed_fixture.write_text(json.dumps({
        "clips": [{"expected_marker": "mp3-crash", "start_seconds": 0, "end_seconds": 1}],
        "audio": {"path": "speech.wav"},
    }))
    campaign.config["repo_root"] = str(tmp_path)
    campaign.config["account_a_cookie_file"] = str(tmp_path / "cookie")
    helper = SimpleNamespace(close=lambda: None)
    campaign._live_helpers["crash"] = (None, helper)
    class SeedAdapter:
        def attach_existing(self, meeting_id, *, helper):
            assert meeting_id == "crash"
            assert helper is campaign._live_helpers[meeting_id][1]
        def descriptor(self):
            return SimpleNamespace(frame_samples=8000)
        def accept_frame(self, meeting_id, frame):
            assert meeting_id == "crash" and frame.sample_count == 8000
            lifecycle.append("seed")
    monkeypatch.setattr(campaign, "_replay_service", lambda **kwargs: SeedAdapter())
    monkeypatch.setattr(external, "_wav_pcm_clip", lambda *args: b"\0\0" * 16000)
    campaign._clients.update(
        {"a": Owner(), "b": Denied(404), "revoked_probe": Denied(401)}
    )
    monkeypatch.setattr(
        campaign,
        "_await_meeting_terminal",
        lambda meeting_id, timeout=1800: copy.deepcopy(payloads[meeting_id]),
    )
    monkeypatch.setattr(campaign, "_submit_file", lambda fixture: "out")
    monkeypatch.setattr(
        external,
        "_probe_mp3",
        lambda content: {
            "codec": "mp3",
            "sample_rate_hz": 16_000,
            "channels": 1,
            "bit_rate_bps": 48_000,
            "bytes": len(content),
        },
    )
    monkeypatch.setattr(external.httpx, "get", lambda *args, **kwargs: _Response(401))
    result = campaign.audio_durability_download()
    assert result["partial_or_unavailable_crash_cases"] == 1
    assert lifecycle == ([] if has_crash else ["seed", "abort"])
    assert all(
        result[key] == 0
        for key in (
            "format_mismatches",
            "durability_failures",
            "cleanup_failures",
            "owner_download_failures",
            "foreign_leaks",
            "unauthenticated_failures",
            "revoked_failures",
            "partial_download_failures",
            "path_failures",
            "permission_failures",
        )
    ), result
    assert result["out_of_band_reconciled"] is True


@pytest.mark.parametrize("queue_observed", [False, True])
@pytest.mark.parametrize("has_running", [False, True])
def test_real_g6_operator_producer_interrupts_queued_item_and_records_no_late_result(
    monkeypatch, tmp_path: Path, has_running, queue_observed,
):
    socket_path = tmp_path / "control.sock"
    socket_path.write_text("", encoding="utf-8")
    socket_path.chmod(0o600)
    corpus = tmp_path / "corpus"
    case = corpus / "case"
    case.mkdir(parents=True)
    (corpus / "corpus-manifest.json").write_text(
        json.dumps({"cases": [{"case_id": "case"}]}), encoding="utf-8"
    )
    (case / "audio.wav").write_bytes(b"wav")
    cookie = tmp_path / "cookie"
    cookie.write_text("cookie", encoding="utf-8")
    cookie.chmod(0o600)
    pending_frames = 0
    interrupted = False

    def paced_sleep(_seconds):
        nonlocal pending_frames
        pending_frames = 0  # Fast decoder drains each paced live span.

    monkeypatch.setattr(external.time, "sleep", paced_sleep)

    class Adapter:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def create(self):
            return SimpleNamespace(
                session_id="meeting",
                descriptor=SimpleNamespace(frame_samples=8_000),
            )

        def accept_frame(self, *args: object, **kwargs: object) -> None:
            nonlocal pending_frames
            pending_frames += 1

        def events(self, meeting_id: str):
            del meeting_id
            if pending_frames < 10 or not queue_observed:
                return ()
            events = [SimpleNamespace(kind="canonical_queued", payload={"item_id": 2})]
            if has_running:
                events += [SimpleNamespace(kind="canonical_started", payload={"item_id": 1})]
            if interrupted:
                events += [SimpleNamespace(kind="canonical_discarded", payload={"item_id": 2})]
            return tuple(events)

        @staticmethod
        def _lane_payload(*args: object, **kwargs: object):
            del args, kwargs
            return {}

        async def abort(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("accepted interrupt must not use cleanup abort")

    meeting = {
        "id": "meeting",
        "status": "interrupted",
        "transcript": {"version": 1, "segments": [{"id": "committed", "speaker": "S00", "text": "durable"}]},
        "audio": {"state": "partial"},
    }
    from moss_transcribe_diarize.app.phase2 import _settled_transcript

    def meeting_projection():
        projected = copy.deepcopy(meeting)
        if interrupted:
            projected["transcript"] = _settled_transcript(projected["transcript"])
        return projected

    class Owner:
        def request(self, method: str, path: str, **kwargs: object):
            del kwargs
            if path in {"/api/operator/status", "/api/admin", "/api/accounts"}:
                return _Response(404)
            if path.endswith("/audio/download"):
                return _Response(200, content=b"mp3")
            if method == "POST" and path.endswith("/frames"):
                return _Response(409)
            return _Response(200)

        def json(self, method: str, path: str, expected: int, **kwargs: object):
            del method, path, expected, kwargs
            return meeting_projection(), _Response(200)

        def close(self) -> None:
            pass

    status = {
        "capacity": {
            "live": {"active": 0},
            "file": {"active": 0},
            "queues": {
                "live_canonical": 0,
                "live_refinement": 0,
                "live_provisional": 0,
                "batch": 0,
            },
        },
        "active_meetings": [],
        "accounts": [],
    }

    def control(_socket: Path, command: str, email=None, *, meeting_id=None):
        nonlocal interrupted
        del email
        if command == "status":
            return copy.deepcopy(status)
        if command == "accounts.list":
            return []
        assert command == "meetings.interrupt" and meeting_id == "meeting"
        interrupted = True
        return {"meeting_id": "meeting", "interrupted": True}

    campaign = _campaign(
        tmp_path,
        operator_socket=str(socket_path),
        account_a_cookie_file=str(cookie),
        https_origin="https://moss.example",
        quality_corpus=str(corpus),
    )
    campaign._clients["a"] = Owner()
    monkeypatch.setattr(external, "AccountCookieLiveReplayService", Adapter)
    monkeypatch.setattr(external, "_control", control)
    monkeypatch.setattr(
        external,
        "_admin_status_surfaces",
        lambda socket, forbidden: {
            "json_exact_projection": True,
            "human_exact_projection": True,
            "json_stderr_bytes": 0,
            "human_stderr_bytes": 0,
            "forbidden_matches": 0,
        },
    )
    monkeypatch.setattr(external, "_wav_pcm", lambda path: b"\0\0" * 8_000)
    monkeypatch.setattr(external, "_probe_mp3", lambda content: {"codec": "mp3"})
    monkeypatch.setattr(
        campaign,
        "_await_meeting_terminal",
        lambda meeting_id, timeout=1800: meeting_projection(),
    )
    if not queue_observed:
        with pytest.raises(external.ExternalMeasurementError, match="did not observe queued canonical"):
            campaign.operator_control()
        retained = json.loads((campaign.artifact_root / "operator/interrupt-admission.json").read_text())
        assert retained["frames_sent"] == 120
        assert retained["selected_queued_item_id"] is None
        assert interrupted is False
        return
    result = campaign.operator_control()
    assert result["interrupt_probe"]["admission"]["frames_sent"] == 10
    assert result["interrupt_probe"]["admission"]["audio_seconds_sent"] == 5
    assert acceptance._validate_raw_predicate(
        "operator_control",
        {"raw": result},
        candidate_sha="a" * 40,
        candidate_tree="b" * 40,
        uv_lock_sha256="c" * 64,
        fixtures=FIXTURES,
        wheel_record_projection_sha256="d" * 64,
        dependency_projection_sha256="e" * 64,
    ) is True
    assert Path("operator/content-free-counts.json") in campaign.safe_artifacts


def test_admin_status_surfaces_execute_human_and_json_cli_and_reject_extra_field(
    monkeypatch: pytest.MonkeyPatch,
):
    expected = {"schema": "status.v1", "ok": 1}

    def serialize(_kind: str, payload: dict[str, object]) -> dict[str, object]:
        if set(payload) != {"schema", "ok"}:
            raise ValueError("extra field")
        return dict(payload)

    monkeypatch.setattr(external, "serialize_operator_payload", serialize)
    monkeypatch.setattr(
        external,
        "render_operator_status",
        lambda payload: f"status={payload['ok']}",
    )
    calls: list[tuple[str, ...]] = []

    def run(argv: tuple[str, ...], **_kwargs: object):
        calls.append(tuple(argv))
        if "--json" in argv:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(expected).encode(),
                stderr=b"",
            )
        return SimpleNamespace(returncode=0, stdout=b"status=1\n", stderr=b"")

    monkeypatch.setattr(external, "_run_admin_status", lambda admin, path, json_output: (run((str(admin), "--json") if json_output else (str(admin),)), expected))
    surfaces = external._admin_status_surfaces(Path("/run/moss.sock"), ())
    assert surfaces == {
        "json_exact_projection": True,
        "human_exact_projection": True,
        "json_stderr_bytes": 0,
        "human_stderr_bytes": 0,
        "forbidden_matches": 0,
    }
    assert len(calls) == 2
    assert any("--json" in argv for argv in calls)

    def extra_run(argv: tuple[str, ...], **_kwargs: object):
        if "--json" in argv:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({**expected, "title": "forbidden"}).encode(),
                stderr=b"",
            )
        return SimpleNamespace(returncode=0, stdout=b"status=1\n", stderr=b"")

    monkeypatch.setattr(external, "_run_admin_status", lambda admin, path, json_output: (extra_run((str(admin), "--json") if json_output else (str(admin),)), expected))
    with pytest.raises(external.ExternalMeasurementError, match="JSON status is invalid"):
        external._admin_status_surfaces(Path("/run/moss.sock"), ())


def test_malformed_external_envelope_is_a_qualification_blocker(tmp_path: Path):
    path = tmp_path / "malformed.json"
    path.write_text(
        json.dumps({"schema": "wrong", "layer": "deployed", "candidate_sha": "a" * 40}),
        encoding="utf-8",
    )
    bundle = acceptance.AttemptBundle(tmp_path / "attempt")
    _, errors = acceptance._read_external_report(
        str(path),
        layer="deployed",
        candidate_sha="a" * 40,
        bundle=bundle,
        forbidden=(),
    )
    bundle.close()
    table = acceptance._final_gate_table(
        identity_errors=errors,
        deterministic={gate: True for gate in acceptance.CORE_GATES},
        deployed={gate: True for gate in acceptance.CORE_GATES},
        pre_admission={gate: True for gate in acceptance.CORE_GATES},
        wave=1,
    )
    assert errors == ["deployed_schema"]
    assert table["passed"] is False


def test_attempt_bundle_is_exclusive_write_once_and_completes_short_writes(monkeypatch, tmp_path: Path):
    bundle = acceptance.AttemptBundle(tmp_path / "attempt")
    real_write = acceptance.os.write
    monkeypatch.setattr(acceptance.os, "write", lambda descriptor, data: real_write(descriptor, data[:3]))
    bundle.write_bytes("raw/large", b"0123456789")
    bundle.finalize({"qualified": True, "g7": "UNCLAIMED"})
    bundle.close()
    assert (tmp_path / "attempt/raw/large").read_bytes() == b"0123456789"
    assert json.loads((tmp_path / "attempt/verdict.json").read_text()) == {
        "g7": "UNCLAIMED",
        "qualified": True,
    }
    assert not (tmp_path / "attempt/.verdict.json.stage").exists()
    with pytest.raises(FileExistsError):
        acceptance.AttemptBundle(tmp_path / "attempt")


def test_attempt_bundle_never_publishes_qualified_verdict_if_final_event_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    bundle = acceptance.AttemptBundle(tmp_path / "attempt")
    real_event = bundle.event

    def fail_event(kind: str, **fields: object) -> None:
        real_event(kind, **fields)
        raise OSError("injected final event fsync failure")

    monkeypatch.setattr(bundle, "event", fail_event)
    with pytest.raises(OSError, match="injected final event fsync failure"):
        bundle.finalize({"qualified": True, "g7": "UNCLAIMED"})
    bundle.close()
    assert not (tmp_path / "attempt/verdict.json").exists()
    assert json.loads((tmp_path / "attempt/.verdict.json.stage").read_text()) == {
        "g7": "UNCLAIMED",
        "qualified": True,
    }
    assert "attempt_finalizing" in (tmp_path / "attempt/attempts.jsonl").read_text()


def test_pytest_machine_report_binds_denominators_required_files_and_required_skips(
    tmp_path: Path,
):
    root = ET.Element("testsuites", name="pytest tests")
    suite = ET.SubElement(
        root,
        "testsuite",
        tests=str(acceptance.MINIMUM_PYTHON_TESTS),
        failures="0",
        errors="0",
        skipped="0",
    )
    for required in acceptance.REQUIRED_PYTHON_TEST_FILES:
        ET.SubElement(
            suite,
            "testcase",
            classname=required.removesuffix(".py").replace("/", "."),
            name="test_required",
        )
    for required in acceptance.REQUIRED_PYTHON_TEST_CASES:
        classname, name = required.rsplit(".", 1)
        ET.SubElement(suite, "testcase", classname=classname, name=name)
    for index in range(
        acceptance.MINIMUM_PYTHON_TESTS
        - len(acceptance.REQUIRED_PYTHON_TEST_FILES)
        - len(acceptance.REQUIRED_PYTHON_TEST_CASES)
    ):
        ET.SubElement(suite, "testcase", classname="tests.test_other", name=f"test_{index}")
    report = tmp_path / "pytest.xml"
    ET.ElementTree(root).write(report, encoding="utf-8", xml_declaration=True)
    counts, required, errors = acceptance._pytest_denominators(report, repo=ROOT)
    assert counts == {
        "collected": acceptance.MINIMUM_PYTHON_TESTS,
        "executed": acceptance.MINIMUM_PYTHON_TESTS,
        "passed": acceptance.MINIMUM_PYTHON_TESTS,
        "failed": 0,
        "skipped": 0,
        "unmeasured": 0,
    }
    assert required == acceptance.REQUIRED_PYTHON_TEST_FILES
    assert errors == []

    required_case = suite.find("testcase")
    assert required_case is not None
    ET.SubElement(required_case, "skipped")
    suite.set("skipped", "1")
    ET.ElementTree(root).write(report, encoding="utf-8", xml_declaration=True)
    _, _, errors = acceptance._pytest_denominators(report, repo=ROOT)
    assert errors == [
        f"pytest_required_file_not_all_passed:{acceptance.REQUIRED_PYTHON_TEST_FILES[0]}"
    ]

    required_node = next(
        case
        for case in suite.findall("testcase")
        if f"{case.get('classname')}.{case.get('name')}"
        == acceptance.REQUIRED_PYTHON_TEST_CASES[0]
    )
    suite.remove(required_node)
    suite.append(
        ET.Element("testcase", classname="tests.test_other", name="replacement_case")
    )
    ET.ElementTree(root).write(report, encoding="utf-8", xml_declaration=True)
    _, _, errors = acceptance._pytest_denominators(report, repo=ROOT)
    assert f"pytest_required_case_missing:{acceptance.REQUIRED_PYTHON_TEST_CASES[0]}" in errors


def test_vitest_machine_report_binds_denominators_files_and_rejects_decrease(tmp_path: Path):
    remaining = acceptance.MINIMUM_FRONTEND_TESTS
    results = []
    for index, required in enumerate(acceptance.REQUIRED_FRONTEND_TEST_FILES):
        count = 1 if index else remaining - len(acceptance.REQUIRED_FRONTEND_TEST_FILES) + 1
        remaining -= count
        results.append(
            {
                "name": str(ROOT / required),
                "status": "passed",
                "assertionResults": [
                    {"status": "passed", "title": f"case-{item}"} for item in range(count)
                ],
            }
        )
    payload = {
        "success": True,
        "numTotalTests": acceptance.MINIMUM_FRONTEND_TESTS,
        "numPassedTests": acceptance.MINIMUM_FRONTEND_TESTS,
        "numFailedTests": 0,
        "numPendingTests": 0,
        "numTodoTests": 0,
        "testResults": results,
    }
    report = tmp_path / "vitest.json"
    report.write_text(json.dumps(payload), encoding="utf-8")
    counts, required, errors = acceptance._vitest_denominators(report, repo=ROOT)
    assert counts["collected"] == acceptance.MINIMUM_FRONTEND_TESTS
    assert required == acceptance.REQUIRED_FRONTEND_TEST_FILES
    assert errors == []

    payload["numTotalTests"] -= 1
    payload["numPassedTests"] -= 1
    results[0]["assertionResults"].pop()
    report.write_text(json.dumps(payload), encoding="utf-8")
    _, _, errors = acceptance._vitest_denominators(report, repo=ROOT)
    assert errors == ["vitest_test_denominator_decreased"]


def test_record_projection_binds_candidate_when_wheel_container_bytes_differ(tmp_path: Path):
    source = {
        "git_sha": "a" * 40,
        "git_tree": "b" * 40,
        "uv_lock_sha256": "c" * 64,
        "fixtures": FIXTURES,
    }
    manifest = json.dumps({"schema": acceptance.SCHEMA, **source}, sort_keys=True).encode()
    name = "moss_transcribe_diarize/build_candidate.json"
    digest = base64.urlsafe_b64encode(hashlib.sha256(manifest).digest()).decode().rstrip("=")
    record_name = "moss_transcribe_diarize-0.1.0.dist-info/RECORD"
    rows = [[name, f"sha256={digest}", str(len(manifest))], [record_name, "", ""]]
    record = io.StringIO()
    csv.writer(record, lineterminator="\n").writerows(rows)

    wheels = []
    for index, year in enumerate((2025, 2026)):
        path = tmp_path / f"candidate-{index}.whl"
        with zipfile.ZipFile(path, "w") as archive:
            for filename, payload in ((name, manifest), (record_name, record.getvalue().encode())):
                info = zipfile.ZipInfo(filename, date_time=(year, 1, 1, 0, 0, 0))
                archive.writestr(info, payload)
        wheels.append(acceptance.inspect_candidate_wheel(path, source))
    assert wheels[0]["sha256"] != wheels[1]["sha256"]
    assert wheels[0]["record_projection_sha256"] == wheels[1]["record_projection_sha256"]
    installed_rows = [
        *rows,
        ["bin/mtd-phase2-web", "sha256=installer", "1"],
        ["moss_transcribe_diarize-0.1.0.dist-info/INSTALLER", "sha256=installer", "2"],
        ["moss_transcribe_diarize/__pycache__/x.pyc", "sha256=installer", "3"],
    ]
    assert record_projection_sha256(rows) == record_projection_sha256(installed_rows)
    assert installer_owned_empty_record("moss_transcribe_diarize/__pycache__/x.pyc")
    assert installer_owned_empty_record("moss_transcribe_diarize-0.1.dist-info/RECORD")
    assert not installer_owned_empty_record("moss_transcribe_diarize/app/phase2.py")


def test_account_replay_cookie_stays_memory_only_and_lane_payload_is_two_lane(tmp_path: Path):
    cookie = tmp_path / "cookie"
    cookie.write_text("secret-session-value\n", encoding="utf-8")
    cookie.chmod(0o600)
    adapter = AccountCookieLiveReplayService(base_url="https://moss.test", cookie_file=cookie)
    assert "secret-session-value" not in repr(adapter)
    payload = adapter._lane_payload(
        acceptance_replay_frame(), lane="system", timestamp_ns=10, silent=False
    )
    assert payload["lane"] == "system"
    assert payload["sequence"] == 3
    assert payload["capture_timestamp_ns"] == 10
    with pytest.raises(ValueError, match="https"):
        AccountCookieLiveReplayService(base_url="http://moss.test", cookie_file=cookie)


def test_profile_secrets_are_read_from_mode_0600_files_and_profile_commands_are_redacted(
    tmp_path: Path,
):
    configured = {}
    for index, role in enumerate(acceptance.REQUIRED_CONTENT_BOUNDARY_ROLES):
        secret = tmp_path / role
        secret.write_text(f"secret-{index}\n", encoding="utf-8")
        secret.chmod(0o600)
        configured[role] = str(secret)
    values, summary, errors = acceptance._load_forbidden_values(
        {"forbidden_files": configured}
    )
    assert errors == []
    assert set(values) == {f"secret-{index}".encode() for index in range(len(configured))}
    assert summary == {
        "roles": sorted(configured),
        "count": len(configured),
        "required_roles": list(acceptance.REQUIRED_CONTENT_BOUNDARY_ROLES),
    }
    embedded, _, errors = acceptance._load_forbidden_values({"forbidden_values": ["bad"]})
    assert embedded == ()
    assert errors == ["profile_must_not_embed_forbidden_values"]

    Path(configured[acceptance.REQUIRED_CONTENT_BOUNDARY_ROLES[0]]).write_text(
        "", encoding="utf-8"
    )
    Path(configured[acceptance.REQUIRED_CONTENT_BOUNDARY_ROLES[1]]).write_text(
        "secret-2\n", encoding="utf-8"
    )
    _, _, errors = acceptance._load_forbidden_values({"forbidden_files": configured})
    assert errors == [
        f"forbidden_file_empty:{acceptance.REQUIRED_CONTENT_BOUNDARY_ROLES[0]}",
        "forbidden_file_values_not_distinct",
    ]

    bundle = acceptance.AttemptBundle(tmp_path / "attempt")
    result = acceptance.execute_command(
        bundle=bundle,
        repo=tmp_path,
        name="profile-command",
        argv=("/usr/bin/true", "secret-3"),
        forbidden=values,
        record_argv=False,
    )
    bundle.close()
    assert result.argv == ("<profile-derived-command>",)
    assert "secret-3" not in (tmp_path / "attempt/attempts.jsonl").read_text()


def acceptance_replay_frame():
    from moss_transcribe_diarize.app.live_session import AudioFrame

    return AudioFrame(sequence=3, pcm=b"\0\0" * 2, sample_count=2)


def test_cutover_rehearsal_requires_exact_isolated_restore_order(tmp_path: Path):
    bundle = acceptance.AttemptBundle(tmp_path / "attempt")
    release = tmp_path / "immutable-release"
    (release / "bin").mkdir(parents=True)
    launcher = release / "bin/mtd-account-web"
    admin_launcher = release / "bin/mtd-admin"
    cutover_launcher = release / "bin/mtd-phase2-cutover"
    vllm_launcher = release / "bin/mtd-vllm"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    admin_launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cutover_launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    vllm_launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    checkout = tmp_path / "checkout"
    (checkout / "ops/systemd").mkdir(parents=True)
    web_unit = checkout / "ops/systemd/moss-web.service"
    vllm_unit = checkout / "ops/systemd/moss-vllm.service"
    web_unit.write_text("ExecStart=/candidate/bin/web\n", encoding="utf-8")
    vllm_unit.write_text("ExecStart=/shared/bin/vllm\n", encoding="utf-8")
    checkout_sha = _commit_candidate_checkout(checkout)
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema": "moss-account-candidate.v1",
                "activation_state": "staged_inert",
                "git_sha": checkout_sha,
                "release": str(release),
                "release_launcher": str(launcher),
                "release_launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
                "release_admin_launcher": str(admin_launcher),
                "release_admin_launcher_sha256": hashlib.sha256(
                    admin_launcher.read_bytes()
                ).hexdigest(),
                "release_cutover_launcher": str(cutover_launcher),
                "release_cutover_launcher_sha256": hashlib.sha256(
                    cutover_launcher.read_bytes()
                ).hexdigest(),
                "release_vllm_launcher": str(vllm_launcher),
                "release_vllm_launcher_sha256": hashlib.sha256(
                    vllm_launcher.read_bytes()
                ).hexdigest(),
                "qualification_checkout": str(checkout),
                "web_unit_path": str(web_unit),
                "web_unit_sha256": hashlib.sha256(web_unit.read_bytes()).hexdigest(),
                "vllm_unit_path": str(vllm_unit),
                "vllm_unit_sha256": hashlib.sha256(vllm_unit.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    config = {
        "original_fixture": str(ROOT / "tests/fixtures/phase2_cutover_original.json"),
        "candidate_manifest": str(candidate),
        "output": str(tmp_path / "rehearsal.json"),
    }
    passed, errors = acceptance._run_rehearsal(config, bundle=bundle, repo=ROOT, forbidden=())
    bundle.close()
    assert passed is True
    assert errors == []
    state = json.loads((tmp_path / "attempt/raw/cutover-rehearsal-state.json").read_text())
    assert state["initial_work_units"] == 5
    assert state["post_block_work_units"] == 5
    assert state["drain_transitions"] == 5
    assert state["post_block_admission_rejected"] is True
    second_bundle = acceptance.AttemptBundle(tmp_path / "second-attempt")
    passed, errors = acceptance._run_rehearsal(
        config, bundle=second_bundle, repo=ROOT, forbidden=()
    )
    second_bundle.close()
    assert passed is True
    assert errors == []

    missing_manifest = tmp_path / "missing-release.json"
    missing_manifest.write_text(
        json.dumps(
            {
                "schema": "moss-account-candidate.v1",
                "activation_state": "staged_inert",
                "release": str(tmp_path / "missing-release"),
                "release_launcher": str(tmp_path / "missing-release/bin/mtd-account-web"),
                "web_unit_path": str(web_unit),
                "vllm_unit_path": str(vllm_unit),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="install paths"):
        cutover.rehearse(
            original_fixture=ROOT / "tests/fixtures/phase2_cutover_original.json",
            candidate_manifest=missing_manifest,
        )

    zero_fixture = tmp_path / "zero-phase1.json"
    fixture_payload = json.loads(
        (ROOT / "tests/fixtures/phase2_cutover_original.json").read_text()
    )
    for row in fixture_payload["runtime_views"]:
        for key in ("entrants", "active_live", "active_jobs", "queued_jobs"):
            row[key] = 0
    zero_fixture.write_text(json.dumps(fixture_payload), encoding="utf-8")
    with pytest.raises(ValueError, match="accepted Phase-1 work"):
        cutover.rehearse(
            original_fixture=zero_fixture,
            candidate_manifest=candidate,
        )

    admin_launcher.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
    with pytest.raises(ValueError, match="install bytes"):
        cutover.rehearse(
            original_fixture=ROOT / "tests/fixtures/phase2_cutover_original.json",
            candidate_manifest=candidate,
        )
    admin_launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    (checkout / "untracked-mixed-unit").write_text("mixed\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean manifested commit"):
        cutover.rehearse(
            original_fixture=ROOT / "tests/fixtures/phase2_cutover_original.json",
            candidate_manifest=candidate,
        )


@pytest.mark.parametrize("layer", ["deployed", "pre_admission"])
def test_measurement_refuses_existing_raw_directory_before_observation(tmp_path, layer):
    raw_dir = tmp_path / "workspace" / "raw"
    raw_dir.mkdir(parents=True)
    retained = raw_dir / "old-observation.json"
    retained.write_text("existing evidence")
    with pytest.raises(FileExistsError) as error:
        measure_layer(layer=layer, candidate_sha="a" * 40, config={}, raw_dir=raw_dir)
    assert Path(error.value.filename) == raw_dir
    assert list(raw_dir.iterdir()) == [retained]
    assert retained.read_text() == "existing evidence"


@pytest.mark.parametrize("wave,expected", [(1, 14), (2, 15), (3, 18)])
@pytest.mark.parametrize("refused", [False, True])
def test_driver_verdict_counts_wave_commands_including_unmeasured(monkeypatch, tmp_path, wave, expected, refused):
    # Stub command execution and packaging only: this proves verdict accounting,
    # not the measured predicates or qualification of a candidate.
    sha = "abcdef0" + "1" * 33
    candidate = {"git_sha": sha, "git_tree": "b" * 40, "uv_lock_sha256": "c" * 64,
                 "dirty": refused, "runtime": {"sqlite": acceptance.REQUIRED_SQLITE, "aiosqlite": "0.22.1"},
                 "fixtures": {}, "dependency_projection": {"sha256": "d" * 64}}
    monkeypatch.setattr(acceptance, "discover_candidate", lambda repo: candidate)
    monkeypatch.setattr(acceptance, "build_candidate_wheel", lambda **kwargs: (
        {"record_verified": True, "record_projection_sha256": "e" * 64}, []))
    monkeypatch.setattr(acceptance, "_git", lambda *args: "")
    executed = []
    def execute(**kwargs):
        executed.append(kwargs["name"])
        # A failed executed command still belongs in the executed denominator.
        return acceptance.CommandResult(kwargs["name"], kwargs["argv"], int(len(executed) == 1), 0, 0, 0, 0), []
    monkeypatch.setattr(acceptance, "execute_deterministic_command", execute)
    boundaries = {}
    for role in acceptance.REQUIRED_CONTENT_BOUNDARY_ROLES:
        path = tmp_path / role
        path.write_text(role)
        path.chmod(0o600)
        boundaries[role] = str(path)
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps({"forbidden_files": boundaries}))
    profile.chmod(0o600)
    output = tmp_path / f"evidence/phase2/wave-{wave}/20260911T120000Z-abcdef0"
    assert acceptance.run_acceptance(wave=wave, output=output, repo=tmp_path, profile_path=profile) == 1
    verdict = json.loads((output / "verdict.json").read_text())
    counts = verdict["denominators"]
    assert counts["commands_collected"] == expected
    assert counts["commands_executed"] == (0 if refused else expected) == len(executed)
    assert counts["commands_skipped"] == 0
    assert counts["commands_unmeasured"] == (expected if refused else 0)
    assert counts["commands_failed"] == (0 if refused else 1)
    assert counts["commands_passed"] + counts["commands_failed"] == counts["commands_executed"]
    assert counts["commands_collected"] == sum(counts[f"commands_{key}"] for key in ("executed", "skipped", "unmeasured"))


def test_predicate_diagnostics_remove_credentials_browser_dom_and_subprocess_output(tmp_path):
    from playwright.sync_api import Error
    secret = tmp_path / "session.cookie"
    secret.write_text("PRIVATE_COOKIE")
    config = {"content_boundary_files": {"account_a_session_cookie": str(secret)}}
    error = Error('Locator.click: locator("PRIVATE_TRANSCRIPT") failed PRIVATE_COOKIE\nCall log:\nPRIVATE_DOM')
    raw = measurement._failure_details(error, config)
    assert raw["failure_type"] == "Error"
    assert all(value not in json.dumps(raw) for value in ("PRIVATE_COOKIE", "PRIVATE_TRANSCRIPT", "PRIVATE_DOM"))
    error = subprocess.CalledProcessError(1, ["browser", "PRIVATE_ARGUMENT"], output="PRIVATE_STDOUT", stderr="PRIVATE_STDERR")
    assert measurement._failure_details(error, config)["exit_status"] == 1


@pytest.mark.parametrize("fault", [None, "other_release", "missing_resolution", "different_exe", "different_module"])
def test_identity_evaluator_uses_recorded_resolution_without_host_files(fault):
    raw = _raw("installed_candidate_identity", "a" * 40, "wheel")
    process = raw["process"]
    process["argv"][0] = "/offline/account-current/bin/python"
    process["interpreter"]["invoked"] = process["argv"][0]
    if fault == "other_release": process["interpreter"]["release_path"] = "/srv/other-release/bin/python"
    elif fault == "missing_resolution": del process["interpreter"]
    elif fault == "different_exe": process["exe"] = "/usr/bin/other-python"
    elif fault == "different_module": process["argv"][3] = "another.module"
    assert acceptance._validate_raw_predicate(
        "installed_candidate_identity", {"raw": raw}, candidate_sha="a" * 40,
        candidate_tree="c" * 40, uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    ) is (fault is None)


def test_control_diagnostic_names_operation_and_socket(monkeypatch, tmp_path):
    async def unavailable(*args, **kwargs):
        raise external.Phase2ControlError("Phase-2 product control is unavailable.")
    monkeypatch.setattr(external, "request_control", unavailable)
    socket_path = tmp_path / "operator.sock"
    with pytest.raises(external.Phase2ControlError) as failure:
        external._control(socket_path, "status")
    assert str(failure.value) == f"Control status at {socket_path}: Phase-2 product control is unavailable."


# macro name -> (surface, per-case metric field) it is recomputed from.
_QUALITY_MACRO_SOURCES = {
    "immediate_wer": ("immediate", "wer"),
    "settled_wer": ("settled", "wer"),
    "recall": ("settled", "content_recall"),
    "time_speaker_attribution": ("settled", "tbsa"),
    "diarization_error_rate": ("settled", "der"),
    "matched_speaker_accuracy": ("settled", "matched_word_speaker_accuracy"),
    "reference_speech_der": ("settled", "reference_speech_der"),
    "final_wer": ("final", "wer"),
}


@pytest.mark.parametrize("speaker,expected", [("S00", True), ("S02", False)])
def test_d45_quality_gate_excludes_only_uncertain_speaker_confusion(speaker, expected):
    """The unchanged DER bounds admit S00 abstention, never a wrong named speaker."""
    report = _report("deployed", "a" * 40, "b" * 64)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    raw = quality["raw"]
    for row in raw["per_case"]:
        settled = row["metrics"]["settled"]
        settled["der_raw"] = 0.18
        settled["reference_speech_der_raw"] = 0.16
        settled["der"] = 0.14 if speaker == "S00" else 0.18
        settled["reference_speech_der"] = 0.12 if speaker == "S00" else 0.16
        row["settled_der_s00_diagnostic"] = {
            "as_is": 0.18,
            "without_s00_confusion": settled["der"],
            "s00_confusion_difference": 0.04 if speaker == "S00" else 0.0,
            "s00_mapped_reference": [],
            "s00_mapped_correct_seconds": 0.0,
            "unattributed_der": settled["der"],
            "reference_speech_as_is": 0.16,
            "reference_speech_without_s00_confusion": settled["reference_speech_der"],
            "reference_speech_s00_confusion_difference": 0.04 if speaker == "S00" else 0.0,
            "reference_speech_s00_mapped_correct_seconds": 0.0,
            "reference_speech_unattributed_der": settled["reference_speech_der"],
        }
    raw["macro"].update({
        "diarization_error_rate": 0.14 if speaker == "S00" else 0.18,
        "reference_speech_der": 0.12 if speaker == "S00" else 0.16,
        "diarization_error_rate_raw": 0.18,
        "reference_speech_der_raw": 0.16,
    })
    raw["duration_weighted"].update({
        "der": raw["macro"]["diarization_error_rate"],
        "reference_speech_der": raw["macro"]["reference_speech_der"],
        "der_raw": 0.18,
        "reference_speech_der_raw": 0.16,
    })
    raw["per_category"]["speech"].update({
        "der": raw["macro"]["diarization_error_rate"],
        "reference_speech_der": raw["macro"]["reference_speech_der"],
        "der_raw": 0.18,
        "reference_speech_der_raw": 0.16,
    })
    outcomes, _ = acceptance.evaluate_external_report(
        report, layer="deployed", candidate_sha="a" * 40, candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is expected
    assert raw["macro"]["diarization_error_rate_raw"] == 0.18


@pytest.mark.parametrize("speaker,expected", [("S00", True), ("S02", False)])
def test_d45_producer_projection_reaches_gate_with_real_diarization(
    tmp_path, speaker, expected
):
    """The production interval scorer and projection drive the acceptance result."""
    reference = tmp_path / "reference.jsonl"
    reference.write_text(
        '{"start":0,"end":1,"speaker":"A","text":"a"}\n'
        '{"start":1,"end":2,"speaker":"B","text":"b"}\n'
    )
    snapshot = {"session": {"effective_transcript": [], "identity_snapshot": {
        "canonical_speakers": ["speaker-0001", "speaker-0002"]}}}
    hypothesis = [
        {"start": 0.0, "end": 0.6, "speaker": "S01"},
        {"start": 0.6, "end": 1.0, "speaker": speaker},
        {"start": 1.0, "end": 2.0, "speaker": "S02"},
    ]
    scored = external._quality_speaker_intervals(snapshot, hypothesis, reference)
    diagnostic = scored["settled_der_s00_diagnostic"]
    report = _report("deployed", "a" * 40, "b" * 64)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    raw = quality["raw"]
    for row in raw["per_case"]:
        settled = row["metrics"]["settled"]
        settled["der_raw"] = diagnostic["as_is"]
        settled["der"] = diagnostic.get("unattributed_der", diagnostic["as_is"])
        settled["reference_speech_der_raw"] = 0.13
        row.update(scored)
        row["settled_der_s00_diagnostic"].update({
            "reference_speech_as_is": 0.13,
            "reference_speech_without_s00_confusion": 0.13,
            "reference_speech_s00_confusion_difference": 0.0,
            "reference_speech_unattributed_der": 0.13,
        })
    projected = external._quality_projection(
        raw["per_case"], corpus_manifest_sha256=FIXTURES["quality_corpus_manifest"]
    )
    projected["input_identities"] = raw["input_identities"]
    quality["raw"] = projected
    outcomes, _ = acceptance.evaluate_external_report(
        report, layer="deployed", candidate_sha="a" * 40, candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    )
    assert diagnostic["as_is"] == 0.2
    assert outcomes["G4"] is expected


def _quality_report_offset_from_bounds(relative: float):
    """Build a SELF-CONSISTENT report whose macros sit `relative` off every bound.

    The evaluator recomputes each macro from `per_case` and cross-checks the duration-weighted
    and per-category projections, so moving `macro` alone would fail consistency long before
    any bound is judged. Giving every case the same value per field keeps all three
    derivations equal to it, which isolates the bound decision as the only thing under test.
    """

    report = _report("deployed", "a" * 40, "b" * 64)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    raw = quality["raw"]
    targets = {}
    for name, (comparison, bound) in acceptance.QUALITY_BOUNDS.items():
        direction = 1 if comparison == "max" else -1
        targets[name] = bound * (1 + direction * relative)

    per_field = {
        source: targets[name] for name, source in _QUALITY_MACRO_SOURCES.items()
    }
    for item in raw["per_case"]:
        for (surface, field), value in per_field.items():
            item["metrics"][surface][field] = value
        diagnostic = item["settled_der_s00_diagnostic"]
        for field, raw_field, raw_diag, adjusted_diag, difference_diag, alias_diag in (
            ("der", "der_raw", "as_is", "without_s00_confusion",
             "s00_confusion_difference", "unattributed_der"),
            ("reference_speech_der", "reference_speech_der_raw", "reference_speech_as_is",
             "reference_speech_without_s00_confusion",
             "reference_speech_s00_confusion_difference", "reference_speech_unattributed_der"),
        ):
            value = item["metrics"]["settled"][field]
            item["metrics"]["settled"][raw_field] = value
            diagnostic.update({raw_diag: value, adjusted_diag: value,
                               difference_diag: 0.0, alias_diag: value})

    raw["macro"] = {
        **targets,
        "diarization_error_rate_raw": targets["diarization_error_rate"],
        "reference_speech_der_raw": targets["reference_speech_der"],
    }
    settled = {
        field: value for (surface, field), value in per_field.items() if surface == "settled"
    }
    settled["der_raw"] = settled["der"]
    settled["reference_speech_der_raw"] = settled["reference_speech_der"]
    raw["duration_weighted"] = {
        field: settled.get(field, raw["duration_weighted"][field])
        for field in raw["duration_weighted"]
    }
    for category in raw["per_category"]:
        raw["per_category"][category] = {
            field: settled.get(field, raw["per_category"][category][field])
            for field in raw["per_category"][category]
        }
    return acceptance.evaluate_external_report(
        report, layer="deployed", candidate_sha="a" * 40, candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    ), report


def test_quality_numeric_failures_are_reported_without_weakening_bounds():
    """Misses beyond the documented tolerance are still rejected, and each one is named.

    The offset is relative, not absolute: the bounds differ by two orders of magnitude in how
    much absolute room they have, so a fixed 0.01 is a large miss for an error rate and a
    rounding error for an accuracy near 1.0.
    """

    (outcomes, errors), _ = _quality_report_offset_from_bounds(
        acceptance.QUALITY_EXCEPTION_RELATIVE_TOLERANCE * 4
    )
    assert outcomes["G4"] is False
    assert "deployed:G4:quality_corpus:failed" in errors
    details = [error for error in errors if "quality_corpus:reported " in error]
    assert len(details) == 8
    for name, (comparison, bound) in acceptance.QUALITY_BOUNDS.items():
        assert any(f"reported {name}=" in detail and f"{bound:.12g}" in detail for detail in details)
    assert "exceeds maximum" in " ".join(details)
    assert "below minimum" in " ".join(details)


def test_d46_h1_rolling_shortfall_is_complete_only_with_terminal_coverage():
    report = _report("deployed", "a" * 40, "b" * 64)
    raw = next(item["raw"] for item in report["predicates"] if item["id"] == "quality_corpus")
    for index, row in enumerate(raw["per_case"]):
        planned = row["windows"]
        terminal_only = 1 if index < 6 else 0
        row["windows"] -= terminal_only
        row["window_coverage"] = {
            "planned_full_windows": planned,
            "rolling_decoded": row["windows"],
            "terminal_only": terminal_only,
            "uncovered": 0,
        }
    raw["windows"] = 116
    assert acceptance._quality_validation({"raw": raw})[0]
    projected = acceptance.external_denominator_projection(report)["quality_windows"]
    assert (projected["collected"], projected["passed"]) == (122, 122)


def test_d46_uncovered_full_window_rejects_even_with_122_rolling_count():
    report = _report("deployed", "a" * 40, "b" * 64)
    raw = next(item["raw"] for item in report["predicates"] if item["id"] == "quality_corpus")
    for row in raw["per_case"]:
        row["window_coverage"] = {
            "planned_full_windows": row["windows"],
            "rolling_decoded": row["windows"],
            "terminal_only": 0,
            "uncovered": 0,
        }
    row = raw["per_case"][0]
    row["windows"] -= 1
    raw["windows"] -= 1
    row["window_coverage"]["rolling_decoded"] -= 1
    row["window_coverage"]["uncovered"] = 1
    assert not acceptance._quality_validation({"raw": raw})[0]


def test_d46_producer_credits_public_final_revision_without_completion_event():
    rolling = [
        {"kind": "rolling_decode_completed", "payload": {
            "outcome": "applied", "window_index": index,
            "start_sample": index * 160000, "end_sample": (index + 1) * 160000,
        }}
        for index in range(4)
    ]
    revision = {"kind": "text_revision_applied", "payload": {
        "source": "terminal", "start_sample": 0, "end_sample": 800000,
        "finalization_status": "final",
    }}
    assert external._quality_window_coverage(
        rolling + [revision], accepted_samples=800000,
        finalization_status="final",
    ) == {
        "planned_full_windows": 5, "rolling_decoded": 4,
        "terminal_only": 1, "uncovered": 0,
    }


@pytest.mark.parametrize("revision_status,snapshot_status", [
    ("failed", "final"), ("refused", "final"),
    ("final", "failed"), ("final", "refused"),
])
def test_d46_nonfinal_terminal_evidence_leaves_window_uncovered(
    revision_status: str, snapshot_status: str,
):
    revision = {"kind": "text_revision_applied", "payload": {
        "source": "terminal", "start_sample": 0, "end_sample": 160000,
        "finalization_status": revision_status,
    }}
    assert external._quality_window_coverage(
        [revision], accepted_samples=160000,
        finalization_status=snapshot_status,
    )["uncovered"] == 1


def test_d46_short_terminal_range_leaves_one_window_uncovered():
    shortened = {"kind": "text_revision_applied", "payload": {
        "source": "terminal", "start_sample": 0, "end_sample": 640000,
        "finalization_status": "final",
    }}
    assert external._quality_window_coverage(
        [shortened], accepted_samples=800000,
        finalization_status="final",
    )["uncovered"] == 1


def test_d46_late_terminal_range_and_missing_revision_leave_window_uncovered():
    late = {"kind": "text_revision_applied", "payload": {
        "source": "terminal", "start_sample": 160000,
        "end_sample": 800000, "finalization_status": "final",
    }}
    assert external._quality_window_coverage(
        [late], accepted_samples=800000, finalization_status="final",
    )["uncovered"] == 1
    assert external._quality_window_coverage(
        [], accepted_samples=160000, finalization_status="final",
    )["uncovered"] == 1


def test_d46_final_terminal_range_still_rejects_duplicates_and_malformed_end():
    revision = {"kind": "text_revision_applied", "payload": {
        "source": "terminal", "start_sample": 0,
        "end_sample": 160000, "finalization_status": "final",
    }}
    with pytest.raises(external.ExternalMeasurementError, match="duplicate"):
        external._quality_window_coverage(
            [revision, revision], accepted_samples=160000,
            finalization_status="final",
        )
    invalid = {"kind": "text_revision_applied", "payload": {
        **revision["payload"], "end_sample": 160001,
    }}
    with pytest.raises(external.ExternalMeasurementError, match="range"):
        external._quality_window_coverage(
            [invalid], accepted_samples=160000,
            finalization_status="final",
        )


def test_d46_nondecoded_rolling_window_can_be_terminal_covered():
    rolling = [
        {"kind": "rolling_decode_completed", "payload": {
            "outcome": "applied", "window_index": index,
            "start_sample": index * 160000, "end_sample": (index + 1) * 160000,
        }}
        for index in range(4)
    ]
    failed_rolling = [dict(event) for event in rolling]
    failed_rolling[-1] = {"kind": "rolling_decode_completed", "payload": {
        **rolling[-1]["payload"], "outcome": "not_awaited",
        "decode_failure": "session_terminal",
    }}
    revision = {"kind": "text_revision_applied", "payload": {
        "source": "terminal", "start_sample": 0, "end_sample": 800000,
        "finalization_status": "final",
    }}
    assert external._quality_window_coverage(
        failed_rolling + [revision], accepted_samples=800000,
        finalization_status="final",
    ) == {"planned_full_windows": 5, "rolling_decoded": 3,
          "terminal_only": 2, "uncovered": 0}


def test_d46_retained_diagnostics_keep_terminal_range_without_content():
    row = external._diagnostic_event({
        "kind": "text_revision_applied", "seq": 1, "session_id": "opaque",
        "snapshot_version": 2, "payload": {
            "source": "terminal", "start_sample": 0, "end_sample": 800000,
            "text": "PRIVATE TRANSCRIPT",
        },
    })
    assert (row["source"], row["start_sample"], row["end_sample"]) == (
        "terminal", 0, 800000
    )
    assert "PRIVATE TRANSCRIPT" not in json.dumps(row)


def test_quality_misses_inside_the_documented_tolerance_are_admitted_and_named():
    """The mandate's 5 % exception, applied to a run that is otherwise complete and clean."""

    (outcomes, errors), report = _quality_report_offset_from_bounds(
        acceptance.QUALITY_EXCEPTION_RELATIVE_TOLERANCE / 5
    )
    assert outcomes["G4"] is True
    assert not [error for error in errors if "quality_corpus" in error]

    records = acceptance.quality_exception_records(report, layer="deployed")
    assert len(records) == len(acceptance.QUALITY_BOUNDS)
    assert all("relative tolerance" in record for record in records)


@pytest.mark.parametrize("target", sorted(acceptance.QUALITY_BOUNDS))
def test_each_bound_rejects_on_its_own_beyond_the_tolerance(target):
    """One macro past the band is enough; the other seven staying clean cannot rescue it."""

    report = _report("deployed", "a" * 40, "b" * 64)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    raw = quality["raw"]
    comparison, bound = acceptance.QUALITY_BOUNDS[target]
    direction = 1 if comparison == "max" else -1
    value = bound * (1 + direction * acceptance.QUALITY_EXCEPTION_RELATIVE_TOLERANCE * 4)
    surface, field = _QUALITY_MACRO_SOURCES[target]
    for item in raw["per_case"]:
        item["metrics"][surface][field] = value
    raw["macro"][target] = value
    if surface == "settled":
        raw["duration_weighted"][field] = value
        for category in raw["per_category"]:
            raw["per_category"][category][field] = value
    outcomes, errors = acceptance.evaluate_external_report(
        report, layer="deployed", candidate_sha="a" * 40, candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is False
    assert any(f"reported {target}=" in error for error in errors)
    assert acceptance.quality_exception_records(report, layer="deployed") == []


def test_an_admitted_exception_is_recorded_from_the_recomputed_macro_not_the_reported_one():
    """Admission and recording must judge identical numbers.

    Consistency between the reported macro and the recomputed one is only enforced to 1e-12,
    so a reported value sitting exactly on the bound can coexist with per-case rows whose mean
    is fractionally past it. The gate admits on the recomputed value; the record must say so.
    """

    report = _report("deployed", "a" * 40, "b" * 64)
    quality = next(item for item in report["predicates"] if item["id"] == "quality_corpus")
    raw = quality["raw"]
    _, bound = acceptance.QUALITY_BOUNDS["diarization_error_rate"]
    for item in raw["per_case"]:
        item["metrics"]["settled"]["der"] = bound + 5e-13
        item["metrics"]["settled"]["der_raw"] = bound + 5e-13
        item["settled_der_s00_diagnostic"].update({
            "as_is": bound + 5e-13,
            "without_s00_confusion": bound + 5e-13,
            "s00_confusion_difference": 0.0,
            "unattributed_der": bound + 5e-13,
        })
    raw["macro"]["diarization_error_rate"] = bound  # exactly strict, within 1e-12 of the rows
    raw["macro"]["diarization_error_rate_raw"] = bound
    raw["duration_weighted"]["der"] = bound
    raw["duration_weighted"]["der_raw"] = bound
    for category in raw["per_category"]:
        raw["per_category"][category]["der"] = bound
        raw["per_category"][category]["der_raw"] = bound

    outcomes, _ = acceptance.evaluate_external_report(
        report, layer="deployed", candidate_sha="a" * 40, candidate_tree="c" * 40,
        uv_lock_sha256="d" * 64, fixtures=FIXTURES,
        wheel_record_projection_sha256="f" * 64, dependency_projection_sha256="e" * 64,
    )
    assert outcomes["G4"] is True
    records = acceptance.quality_exception_records(report, layer="deployed")
    assert len(records) == 1
    assert "diarization_error_rate" in records[0]


def test_quality_surface_diagnostics_preserve_failed_finalization_without_transcript():
    snapshots = {name: {"snapshot": {"pending_work_items": 0, "session": {
        "finalization_status": "failed", "pending_span_ids": [2],
        "accepted_samples": 16000, "accounted_samples": 8000,
        "text_revision_version": 3, "effective_transcript": [{"text": "private words"}],
    }}, "wait": {"polls": 0, "drained": True}} for name in
        ("pre_stop_immediate", "pre_stop_settled", "post_stop_final")}
    observed = external._quality_surface_observations(snapshots)
    assert observed["post_stop_final"]["finalization_status"] == "failed"
    assert observed["pre_stop_settled"]["pending_span_count"] == 1
    assert observed["pre_stop_settled"]["accounted_samples"] == 8000
    assert "private words" not in json.dumps(observed)


@pytest.mark.parametrize("name", ["vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc"])
def test_cache_usage_reads_real_engine_gauges(monkeypatch, name):
    monkeypatch.setattr(external.httpx, "get", lambda *args, **kwargs: SimpleNamespace(status_code=200,
        text=f'# HELP {name} Cache usage\n{name}{{engine="0"}} 0.25\n{name}{{engine="1"}} 0.75\n'))
    assert external._vllm_cache_use("http://127.0.0.1:8000/metrics") == 0.75


@pytest.mark.parametrize("body", ["# no cache gauge\nvllm:num_requests_running 3\n", 'vllm:kv_cache_usage_perc{engine="0"} NaN\n'])
def test_cache_usage_still_refuses_absent_or_nonfinite_gauges(monkeypatch, body):
    monkeypatch.setattr(external.httpx, "get", lambda *args, **kwargs: SimpleNamespace(status_code=200, text=body))
    with pytest.raises(external.ExternalMeasurementError):
        external._vllm_cache_use("http://127.0.0.1:8000/metrics")


@pytest.mark.parametrize("duration", ["0.576000", None])
def test_mp3_probe_uses_private_seekable_file_and_still_requires_duration(monkeypatch, duration):
    paths = []
    def probe(argv, **kwargs):
        path = Path(argv[-1])
        paths.append(path)
        assert path.is_file()
        assert path.read_bytes() == b"mp3 fixture"
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert "input" not in kwargs
        format_row = {} if duration is None else {"duration": duration}
        return SimpleNamespace(returncode=0, stdout=json.dumps({"streams": [{"codec_name": "mp3", "sample_rate": "16000", "channels": 1, "bit_rate": "48000"}], "format": format_row}))
    monkeypatch.setattr(external.subprocess, "run", probe)
    if duration is None:
        with pytest.raises(external.ExternalMeasurementError, match="incomplete"):
            external._probe_mp3(b"mp3 fixture")
    else:
        assert external._probe_mp3(b"mp3 fixture")["duration_seconds"] == float(duration)
    assert paths and all(not path.exists() for path in paths)


def test_mp3_probe_reports_duration_for_real_encoded_audio(tmp_path):
    path = tmp_path / "audio.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.5", "-codec:a", "libmp3lame", "-b:a", "48k", str(path)], check=True)
    measured = external._probe_mp3(path.read_bytes())
    assert measured["codec"] == "mp3"
    assert measured["sample_rate_hz"] == 16000
    assert measured["channels"] == 1
    assert measured["duration_seconds"] > 0


def test_outer_acceptance_failure_never_retains_exception_content(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(acceptance, 'discover_candidate', lambda repo: {'git_sha': 'a' * 40})
    monkeypatch.setattr(acceptance, 'load_profile', lambda path: ({}, []))
    def fail(**kwargs):
        raise RuntimeError('PRIVATE_TRANSCRIPT PRIVATE_API_KEY /Users/PRIVATE_OPERATOR')
    monkeypatch.setattr(acceptance, 'build_candidate_wheel', fail)
    output = tmp_path / 'evidence/phase2/wave-1/20260912T000000Z-aaaaaaa'
    assert acceptance.run_acceptance(wave=1, output=output, repo=tmp_path) == 1
    diagnostic = json.loads((output / 'terminal-error.json').read_text())
    assert diagnostic['error'] == 'RuntimeError' and diagnostic['qualified'] is False
    assert 'PRIVATE' not in capsys.readouterr().err
    assert all(b'PRIVATE' not in path.read_bytes() for path in output.rglob('*') if path.is_file())


@pytest.mark.parametrize("duration,capacity,expected", [
    (30, 960_000, False),
    (60, 960_000, False),
    (120, 960_000, False),
    (120.5, 960_000, True),
    (121, 960_000, True),
    (120.5, 1_920_000, False),
    (240.5, 1_920_000, True),
])
def test_overload_duration_must_cover_descriptor_buffer_and_retry_margin(duration, capacity, expected):
    assert acceptance._validate_overload({"raw": _overload_raw(duration, capacity)}) is expected


@pytest.mark.parametrize("field", ["observed_429", "peer_progress", "same_sequence_retry"])
def test_sufficient_overload_duration_still_requires_each_backpressure_witness(field):
    raw = _overload_raw()
    raw["backpressure_observation"][field] = False
    assert acceptance._validate_overload({"raw": raw}) is False


@pytest.mark.parametrize("failure", ["terminal_count", "one_not_final", "missing_final_status"])
def test_overload_rejects_terminal_failure_or_any_session_not_finalized(failure):
    raw = _overload_raw()
    assert acceptance._validate_overload({"raw": raw}) is True
    if failure == "terminal_count":
        raw["terminal_failures"] = 1
    elif failure == "one_not_final":
        raw["session_observations"][1]["finalization_status"] = "failed"
    else:
        del raw["session_observations"][1]["finalization_status"]
    assert acceptance._validate_overload({"raw": raw}) is False


def test_measurement_directories_use_attempt_owned_root(monkeypatch, tmp_path):
    root = tmp_path / 'attempt' / 'measurement-workspaces'
    root.mkdir(parents=True)
    monkeypatch.setenv('MOSS_ACCEPTANCE_WORK_ROOT', str(root))
    original_load = acceptance.load_profile
    original_mkdtemp = acceptance.tempfile.mkdtemp
    created = []

    def load(*args, **kwargs):
        profile, errors = original_load(*args, **kwargs)
        profile['measurements'] = {'deployed': {}, 'pre_admission': {}}
        return profile, errors

    def mkdtemp(*args, **kwargs):
        path = original_mkdtemp(*args, **kwargs)
        created.append(Path(path))
        return path

    monkeypatch.setattr(acceptance, 'load_profile', load)
    monkeypatch.setattr(acceptance.tempfile, 'mkdtemp', mkdtemp)
    # Refused identity skips external commands but still allocates/cleans both roots.
    test_driver_verdict_counts_wave_commands_including_unmeasured(
        monkeypatch, tmp_path, wave=1, expected=14, refused=True)
    assert len(created) == 2
    assert all(path.parent == root and not path.exists() for path in created)


def test_quality_s00_diagnostic_reports_when_s00_is_the_optimal_match(tmp_path):
    """Review F1: an unattributed label that best matches a reference speaker scores as correct; say so."""
    from moss_transcribe_diarize import phase2_acceptance_external as external
    external._load_surface_harness(ROOT)

    reference = tmp_path / "reference.jsonl"
    reference.write_text(
        '{"start": 0.0, "end": 1.0, "speaker": "Alpha Person", "text": "REFERENCE PRIVATE"}\n'
        '{"start": 1.0, "end": 2.0, "speaker": "Beta Person", "text": "REFERENCE PRIVATE"}\n'
    )
    snapshot = {"session": {"effective_transcript": [], "identity_snapshot": {"canonical_speakers": ["speaker-0001"]}}}
    rows = [{"start": 0.0, "end": 1.0, "speaker": "S01"}, {"start": 1.0, "end": 2.0, "speaker": "S00"}]
    diagnostic = external._quality_speaker_intervals(
        snapshot, rows, reference, speech_regions=((0.0, 2.0),)
    )["settled_der_s00_diagnostic"]
    assert diagnostic["as_is"] == 0.0
    assert diagnostic["s00_confusion_difference"] == 0.0
    assert diagnostic["s00_mapped_reference"] == ["ref:02"]
    assert diagnostic["s00_mapped_correct_seconds"] == 1.0
    assert diagnostic["unattributed_der"] == 0.0
    assert diagnostic["unattributed_der"] == diagnostic["without_s00_confusion"]
    assert diagnostic["reference_speech_as_is"] == 0.0
    assert diagnostic["reference_speech_unattributed_der"] == 0.0
    assert (diagnostic["reference_speech_unattributed_der"]
            == diagnostic["reference_speech_without_s00_confusion"])
    assert "Beta Person" not in str(diagnostic)


@pytest.mark.parametrize("uncertain,expected", [(True, 0.0), (False, 0.2)])
def test_d45_production_der_axes_preserve_named_confusion(tmp_path, uncertain, expected):
    """Both deployed scorers keep their own mapping; only S00 confusion is unattributed."""
    external._load_surface_harness(ROOT)
    reference = tmp_path / "reference.jsonl"
    reference.write_text(
        '{"start":0,"end":1,"speaker":"A","text":"a"}\n'
        '{"start":1,"end":2,"speaker":"B","text":"b"}\n'
    )
    label = "S00" if uncertain else "S02"
    rows = [
        {"start": 0.0, "end": 0.6, "speaker": "S01"},
        {"start": 0.6, "end": 1.0, "speaker": label},
        {"start": 1.0, "end": 2.0, "speaker": "S02"},
    ]
    snapshot = {"session": {"effective_transcript": [], "identity_snapshot": {
        "canonical_speakers": ["speaker-0001", "speaker-0002"]}}}
    diag = external._quality_speaker_intervals(
        snapshot, rows, reference, speech_regions=((0.0, 2.0),)
    )["settled_der_s00_diagnostic"]
    assert diag["as_is"] == 0.2
    assert diag["reference_speech_as_is"] == 0.2
    assert diag["unattributed_der"] == expected
    assert diag["reference_speech_unattributed_der"] == expected


def test_d45_reference_speech_axis_uses_its_vad_denominator(tmp_path):
    external._load_surface_harness(ROOT)
    reference = tmp_path / "reference.jsonl"
    reference.write_text(
        '{"start":0,"end":1,"speaker":"A","text":"a"}\n'
        '{"start":1,"end":2,"speaker":"B","text":"b"}\n'
    )
    rows = [
        {"start": 0.0, "end": 0.6, "speaker": "S01"},
        {"start": 0.6, "end": 1.0, "speaker": "S00"},
        {"start": 1.0, "end": 1.8, "speaker": "S02"},
    ]
    snapshot = {"session": {"effective_transcript": [], "identity_snapshot": {
        "canonical_speakers": ["speaker-0001", "speaker-0002"]}}}
    diag = external._quality_speaker_intervals(
        snapshot, rows, reference, speech_regions=((0.0, 0.8), (1.0, 1.8))
    )["settled_der_s00_diagnostic"]
    assert diag["as_is"] == 0.3  # includes a 0.2 s miss beyond the hypothesis
    assert diag["unattributed_der"] == 0.1
    assert diag["reference_speech_as_is"] == 0.125
    assert diag["reference_speech_unattributed_der"] == 0.0
