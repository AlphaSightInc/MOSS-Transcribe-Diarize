from __future__ import annotations

import asyncio
import base64
import time
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.phase2 import create_phase2_app
from tests.phase2 import test_owner_bound_live_meeting as fixture


FAILED_NOTICE = (
    "Final transcript refinement failed for some audio. "
    "Previously committed words were kept."
)
TRUNCATED_NOTICE = (
    "The speech decoder reached its output limit. This transcript may be incomplete."
)
UNAVAILABLE_NOTICE = (
    "Final transcript refinement was unavailable for some audio. "
    "Previously committed words were kept."
)


def _feed_distinct_lanes(client: TestClient, meeting_id: str, *, signal: bool) -> None:
    for sequence in range(3):
        for lane, sample in (("system", 1), ("microphone", 2)):
            frame = fixture.v2_frame(sequence, lane)
            value = sample if signal else 0
            frame["pcm_base64"] = base64.b64encode(
                value.to_bytes(2, byteorder="little", signed=True) * 2
            ).decode("ascii")
            response = client.post(f"/api/live/sessions/{meeting_id}/frames", json=frame)
            assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    (
        "case",
        "failed_lanes",
        "signal",
        "truncated",
        "max_tape_bytes",
        "expected_review",
        "expected_notice",
    ),
    (
        ("healthy", frozenset(), True, False, 32_000, False, None),
        (
            "system_lane_failure",
            frozenset({"system"}),
            True,
            False,
            32_000,
            True,
            FAILED_NOTICE,
        ),
        (
            "microphone_lane_failure",
            frozenset({"microphone"}),
            True,
            False,
            32_000,
            True,
            FAILED_NOTICE,
        ),
        (
            "total_decode_failure",
            frozenset({"system", "microphone"}),
            True,
            False,
            32_000,
            True,
            FAILED_NOTICE,
        ),
        ("truncated", frozenset(), True, True, 32_000, True, TRUNCATED_NOTICE),
        (
            "unavailable_refinement",
            frozenset(),
            True,
            False,
            32_000,
            True,
            UNAVAILABLE_NOTICE,
        ),
        ("tape_gaps", frozenset(), True, False, 4, True, UNAVAILABLE_NOTICE),
        ("digital_silence", frozenset(), False, False, 32_000, False, None),
    ),
)
def test_terminal_outcome_is_truthful_live_saved_and_after_reopen(
    tmp_path: Path,
    case: str,
    failed_lanes: frozenset[str],
    signal: bool,
    truncated: bool,
    max_tape_bytes: int,
    expected_review: bool,
    expected_notice: str | None,
) -> None:
    database = tmp_path / "account.sqlite3"
    sessions = asyncio.run(fixture.provision(database))
    scheduler = fixture._ManualTerminalScheduler()
    app = fixture.make_app(
        database,
        terminal_text="[0][S01]refined words[0.000375]",
        terminal_scheduler=scheduler,
        max_tape_bytes=max_tape_bytes,
    )

    class LaneAwareRunner:
        def transcribe(self, path: Path, **_kwargs: object) -> SimpleNamespace:
            with wave.open(str(path), "rb") as reader:
                sample = int.from_bytes(
                    reader.readframes(1), byteorder="little", signed=True
                )
            lane = "system" if sample == 1 else "microphone"
            if lane in failed_lanes:
                raise RuntimeError(f"controlled {lane} lane failure")
            return SimpleNamespace(
                text="[0][S01]refined words[0.000375]",
                possibly_truncated=truncated,
            )

    with TestClient(app, base_url="https://moss.test") as client:
        fixture.session(client, sessions["a"])
        app.state.phase2_live.runtime._terminal_finalizer.runner = LaneAwareRunner()
        meeting_id = client.post("/api/live/sessions").json()["id"]
        _feed_distinct_lanes(client, meeting_id, signal=signal)
        if signal:
            fixture.wait_snapshot(
                client,
                meeting_id,
                lambda body: body["meeting_transcript_version"] > 0,
            )
        if case == "unavailable_refinement":
            app.state.phase2_live.runtime._sessions[meeting_id].coordinator.tape = None
        stopped = client.post(
            f"/api/live/sessions/{meeting_id}/stop", json={"deadline": 0.5}
        )
        assert stopped.status_code in {200, 202}, stopped.text
        if scheduler.pending:
            assert scheduler.run_one()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            saved = client.get(f"/api/meetings/{meeting_id}").json()
            if saved["status"] != "active":
                break
            time.sleep(0.01)
        else:
            raise AssertionError(f"{case}: durable terminal state not reached")
        live = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()

    reopened_app = create_phase2_app(
        database_path=database,
        meeting_audio_root=tmp_path / "meetings",
    )
    with TestClient(reopened_app, base_url="https://moss.test") as reopened_client:
        fixture.session(reopened_client, sessions["a"])
        reopened = reopened_client.get(f"/api/meetings/{meeting_id}").json()

    assert saved["needs_review"] is expected_review
    assert reopened["needs_review"] is expected_review
    assert live.get("needs_review") is expected_review
    assert reopened["transcript"] == saved["transcript"]
    assert reopened["audio"] == saved["audio"]
    if expected_notice:
        assert saved["notice"] == expected_notice
        assert reopened["notice"] == expected_notice
        assert saved["transcript"]["segments"]
    else:
        assert saved.get("notice") is None
        assert reopened.get("notice") is None


def test_interrupted_outcome_is_reviewable_live_saved_and_after_reopen(
    tmp_path: Path,
) -> None:
    database = tmp_path / "account.sqlite3"
    sessions = asyncio.run(fixture.provision(database))
    app = fixture.make_app(
        database,
        terminal_text="[0][S01]refined words[0.000375]",
    )

    with TestClient(app, base_url="https://moss.test") as client:
        fixture.session(client, sessions["a"])
        meeting_id = client.post("/api/live/sessions").json()["id"]
        _feed_distinct_lanes(client, meeting_id, signal=True)
        fixture.wait_snapshot(
            client,
            meeting_id,
            lambda body: body["meeting_transcript_version"] > 0,
        )
        aborted = client.post(
            f"/api/live/sessions/{meeting_id}/abort",
            json={"reason": "controlled_interruption"},
        )
        assert aborted.status_code == 200, aborted.text
        saved = client.get(f"/api/meetings/{meeting_id}").json()
        live = client.get(f"/api/live/sessions/{meeting_id}/snapshot").json()

    reopened_app = create_phase2_app(
        database_path=database,
        meeting_audio_root=tmp_path / "meetings",
    )
    with TestClient(reopened_app, base_url="https://moss.test") as reopened_client:
        fixture.session(reopened_client, sessions["a"])
        reopened = reopened_client.get(f"/api/meetings/{meeting_id}").json()

    assert saved["status"] == reopened["status"] == "interrupted"
    assert saved["needs_review"] is True
    assert reopened["needs_review"] is True
    assert live["needs_review"] is True
    assert reopened["transcript"] == saved["transcript"]
    assert reopened["audio"] == saved["audio"]
