"""IDEA-003 red-first contracts for cross-window speaker continuity."""

from __future__ import annotations

import importlib
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from moss_transcribe_diarize.app.model_runner import TranscriptionResult
from moss_transcribe_diarize.app.windowed_transcription import WindowPlan
from moss_transcribe_diarize.transcript_parser import TranscriptSegment


def test_overlap_permutation_relabels_both_full_window_copies(identity_api):
    resolution = resolve_identity(
        identity_api,
        [
            window(0, 0, 150, 0, 135),
            window(1, 120, 270, 135, 270),
        ],
        [
            [
                segment(10, 20, "S01", "alice intro"),
                segment(125, 134, "S01", "alice overlap"),
                segment(136, 146, "S02", "bob overlap"),
            ],
            [
                segment(4, 14, "S02", "alice overlap copy"),
                segment(16, 26, "S01", "bob overlap copy"),
                segment(40, 55, "S02", "alice after"),
            ],
        ],
    )

    speakers = speakers_by_text(resolution)
    assert speakers["alice overlap copy"] == "S01"
    assert speakers["bob overlap copy"] == "S02"
    assert speakers["alice after"] == "S01"
    assert resolution.summary["accepted_edges"] == 2
    assert edge_reasons(resolution.diagnostics) == ["accepted_overlap", "accepted_overlap"]


def test_absent_overlap_recurrence_stays_unresolved_when_tier_b_is_default_off(identity_api):
    tier_b = ExplodingTierBEncoder()

    resolution = resolve_identity(
        identity_api,
        [
            window(0, 0, 150, 0, 135),
            window(1, 120, 270, 135, 255),
            window(2, 240, 390, 255, 390),
        ],
        [
            [segment(20, 30, "S01", "speaker first")],
            [segment(20, 30, "S02", "other speaker")],
            [segment(40, 50, "S01", "speaker returns")],
        ],
        tier_b_encoder=tier_b,
    )

    speakers = speakers_by_text(resolution)
    assert speakers["speaker first"] == "S01"
    assert speakers["speaker returns"] != "S01"
    assert resolution.summary["tier_b_status"] == "disabled"
    assert "unmatched_birth_or_return" in edge_reasons(resolution.diagnostics)
    assert tier_b.calls == 0


def test_ambiguous_overlap_abstains_instead_of_forcing_a_merge(identity_api):
    resolution = resolve_identity(
        identity_api,
        [
            window(0, 0, 150, 0, 135),
            window(1, 120, 270, 135, 270),
        ],
        [
            [
                segment(122, 130, "S01", "left option one"),
                segment(130, 138, "S02", "left option two"),
            ],
            [segment(2, 18, "S01", "right ambiguous")],
        ],
    )

    assert resolution.summary["accepted_edges"] == 0
    assert speakers_by_text(resolution)["right ambiguous"] not in {"S01", "S02"}
    assert "low_margin" in edge_reasons(resolution.diagnostics)


def test_within_window_cannot_link_blocks_tier_b_component_merge(identity_api):
    tier_b = CannotLinkMergingTierBEncoder()

    resolution = resolve_identity(
        identity_api,
        [
            window(0, 0, 150, 0, 135),
            window(1, 120, 270, 135, 270),
        ],
        [
            [
                segment(10, 30, "S01", "same window one"),
                segment(40, 60, "S02", "same window two"),
            ],
            [segment(160, 180, "S01", "remote candidate")],
        ],
        tier_b_enabled=True,
        tier_b_encoder=tier_b,
    )

    speakers = speakers_by_text(resolution)
    assert speakers["same window one"] != speakers["same window two"]
    assert resolution.summary["tier_b_accepted"] == 0
    assert "cannot_link_conflict" in edge_reasons(resolution.diagnostics)


def test_resolution_replay_is_byte_deterministic(identity_api):
    windows = [
        window(0, 0, 150, 0, 135),
        window(1, 120, 270, 135, 270),
    ]
    local_results = [
        [segment(125, 134, "S02", "stable left")],
        [segment(5, 14, "S01", "stable right")],
    ]

    first = resolve_identity(identity_api, windows, local_results)
    second = resolve_identity(identity_api, list(reversed(windows)), list(reversed(local_results)))

    assert serialized_resolution(first) == serialized_resolution(second)


def test_canonical_labels_continue_beyond_s08(identity_api):
    first_window = [
        segment(float(i * 10), float(i * 10 + 3), f"S{i + 1:02d}", f"speaker {i + 1}")
        for i in range(9)
    ]
    resolution = resolve_identity(
        identity_api,
        [
            window(0, 0, 150, 0, 135),
            window(1, 120, 270, 135, 270),
        ],
        [
            first_window,
            [segment(40, 45, "S01", "new tenth speaker")],
        ],
    )

    assert speakers_by_text(resolution)["speaker 9"] == "S09"
    assert speakers_by_text(resolution)["new tenth speaker"] == "S10"


def test_identity_summary_and_artifact_persist_through_job_api_reload():
    fastapi = pytest.importorskip("fastapi")
    assert fastapi is not None
    from fastapi.testclient import TestClient
    from moss_transcribe_diarize.app.server import create_app

    with tempfile.TemporaryDirectory() as tmpdir:
        app = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=5)
        app.state.manager.model_runner = IdentityMetadataRunner()
        client = TestClient(app)

        created = client.post(
            "/api/jobs",
            files={"file": ("sample.wav", b"audio", "audio/wav")},
        )
        assert created.status_code == 200
        job_id = created.json()["id"]
        finished = wait_terminal(client, job_id)

        assert finished["status"] == "waiting_review", finished.get("error")
        assert finished["identity_summary"] == {"schema_version": 2, "accepted_edges": 1}
        artifact_path = Path(finished["files"]["identity_resolution"])
        assert artifact_path.exists()
        assert json.loads(artifact_path.read_text(encoding="utf-8")) == {
            "schema_version": 2,
            "summary": {"accepted_edges": 1},
        }

        reloaded = create_app(model_path="fake-model", runs_dir=tmpdir, max_new_tokens=5)
        reloaded.state.manager.model_runner = IdentityMetadataRunner()
        persisted = TestClient(reloaded).get(f"/api/jobs/{job_id}").json()
        assert persisted["identity_summary"] == {"schema_version": 2, "accepted_edges": 1}
        assert persisted["files"]["identity_resolution"] == str(artifact_path)


@pytest.fixture
def identity_api():
    module = importlib.import_module("moss_transcribe_diarize.app.speaker_identity")
    return SimpleNamespace(
        IdentityResolver=module.IdentityResolver,
        IdentityResolverConfig=module.IdentityResolverConfig,
    )


def resolve_identity(
    identity_api,
    windows: list[WindowPlan],
    local_results: list[list[TranscriptSegment]],
    *,
    tier_b_enabled: bool = False,
    tier_b_encoder=None,
):
    config = identity_api.IdentityResolverConfig(tier_b_enabled=tier_b_enabled)
    resolver = identity_api.IdentityResolver(config=config, tier_b_encoder=tier_b_encoder)
    return resolver.resolve(windows, local_results, window_audio_paths=[])


def window(index: int, start: float, end: float, own_start: float, own_end: float) -> WindowPlan:
    return WindowPlan(index=index, start=start, end=end, own_start=own_start, own_end=own_end)


def segment(start: float, end: float, speaker: str, text: str) -> TranscriptSegment:
    return TranscriptSegment(start=start, end=end, speaker=speaker, text=text)


def speakers_by_text(resolution) -> dict[str, str]:
    return {
        segment.text: segment.speaker
        for window_result in resolution.relabeled_results
        for segment in window_result
    }


def edge_reasons(diagnostics: dict) -> list[str]:
    reasons: list[str] = []
    for boundary in diagnostics.get("boundaries", []):
        for edge in boundary.get("edges", []):
            reasons.append(edge["reason"])
    for proposal in diagnostics.get("tier_b", {}).get("proposals", []):
        reasons.append(proposal["reason"])
    return reasons


def serialized_resolution(resolution) -> str:
    return json.dumps(
        {
            "relabeled_results": [
                [
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "speaker": segment.speaker,
                        "text": segment.text,
                    }
                    for segment in window_result
                ]
                for window_result in resolution.relabeled_results
            ],
            "diagnostics": resolution.diagnostics,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


class ExplodingTierBEncoder:
    descriptor = {"provider": "test-exploding"}

    def __init__(self):
        self.calls = 0

    def embed(self, wav_path, intervals):
        self.calls += 1
        raise AssertionError("Tier B must not be invoked when disabled by default.")


class CannotLinkMergingTierBEncoder:
    descriptor = {"provider": "test-cannot-link"}

    def embed(self, wav_path, intervals):
        return [1.0, 0.0, 0.0]


class IdentityMetadataRunner:
    model_path = "fake-model"

    def transcribe(self, audio_path, **kwargs):
        return TranscriptionResult(
            text="[0][S01]hello[1]",
            prompt_len=10,
            generated_tokens=5,
            elapsed_sec=0.01,
            model=self.model_path,
            audio=str(audio_path),
            decoding="greedy",
            temperature=None,
            identity_summary={"schema_version": 2, "accepted_edges": 1},
            identity_resolution={"schema_version": 2, "summary": {"accepted_edges": 1}},
        )


def wait_terminal(client, job_id: str) -> dict:
    job = {}
    for _ in range(80):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in {"waiting_review", "done", "failed", "cancelled"}:
            return job
        time.sleep(0.025)
    raise AssertionError(f"job {job_id} did not finish: {job}")
