import asyncio
import hashlib

import pytest

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase,
    GeminiLiveRuntime,
    GeminiPreview,
    GeminiRolling,
    GeminiRelabel,
    GeminiSegment,
    ScriptedGeminiEngine,
)
from moss_transcribe_diarize.app.live_service_runtime import (
    LiveServiceBounds,
    LiveServiceConfigHashes,
    LiveServiceDescriptor,
)
from moss_transcribe_diarize.app.live_session import AudioFrame


def descriptor(*, tape_bytes=64000):
    return LiveServiceDescriptor(
        source_revision="test", provider_name="gemini", provider_revision="phase1-fake",
        provider_manifest_hash=hashlib.sha256(b"gemini").hexdigest(),
        config_hashes=LiveServiceConfigHashes.from_parts(
            endpoint_config={}, identity_config={}, decoder_config={}
        ),
        bounds=LiveServiceBounds(
            max_frame_samples=16000, max_queue_depth=4, max_retained_samples=32000,
            max_identity_speakers=8, max_events=64, max_tape_bytes=tape_bytes,
        ),
        frame_samples=16000,
    )


def frame(sequence):
    return AudioFrame(sequence=sequence, pcm=b"\0" * 32000, sample_count=16000)


def runtime(tmp_path, scripts):
    def engine_factory(session_id, publish, _report_usage):
        batches, terminal = scripts[session_id]
        return ScriptedGeminiEngine(publish, batches=batches, terminal=terminal)

    return GeminiLiveRuntime(descriptor=descriptor(), engine_factory=engine_factory,
                             tape_storage_root=tmp_path)


def test_create_frame_preview_and_diarized_commit_are_poller_shaped(tmp_path):
    row = GeminiSegment(0, 8000, "hello", "speaker-0001")
    scripts = {"one": ([
        (GeminiPreview(end_sample=16000, segments=(GeminiSegment(0, 8000, "hello"),)),),
        (GeminiBase(through_sample=16000, segments=(GeminiSegment(0, 8000, "hello"),)),
         GeminiRolling(start_sample=0, end_sample=16000, segments=(row,))),
    ], (row,))}
    rt = runtime(tmp_path, scripts)
    assert rt.create(session_id="one").snapshot.session.status == "active"
    rt.accept_frame("one", frame(0))
    preview = rt.snapshot("one").to_dict()
    assert preview["session"]["provisional"]["transcript"] == "[0][S00]hello[0.5]"
    rt.accept_frame("one", frame(1))
    payload = rt.snapshot("one").to_dict()
    session = payload["session"]
    assert session["identity_snapshot"]["canonical_speakers"] == ["speaker-0001"]
    assert session["effective_transcript"][0]["canonical_speaker"] == "speaker-0001"
    assert session["effective_transcript"][0]["text"] == "hello"
    assert "source_lane" not in session["effective_transcript"][0]
    assert session["provisional"] is None
    assert payload["descriptor"]["sample_rate"] == 16000


def test_relabel_and_terminal_revision_replace_visible_rows(tmp_path):
    asyncio.run(_relabel_and_terminal_revision_replace_visible_rows(tmp_path))


async def _relabel_and_terminal_revision_replace_visible_rows(tmp_path):
    first = GeminiSegment(0, 8000, "hello world", "speaker-0001")
    terminal = (GeminiSegment(0, 4000, "hello ", "speaker-0001"),
                GeminiSegment(4000, 8000, "world", "speaker-0002"))
    scripts = {"one": ([(GeminiBase(through_sample=16000, segments=(first,)),
                         GeminiRolling(0, 16000, (first,)),
                         GeminiRelabel(0, 8000, terminal))], terminal)}
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))
    live = rt.snapshot("one").session
    assert [row.canonical_speaker for row in live.effective_transcript] == [
        "speaker-0001", "speaker-0002"
    ]
    stopped = await rt.stop("one", 1.0)
    assert stopped.session.status == "closed"
    assert stopped.session.finalization_status in {"running", "final"}
    await rt.wait_terminal("one")
    final = rt.snapshot("one").session
    assert final.finalization_status == "final"
    assert [row.authority for row in final.effective_transcript] == ["terminal", "terminal"]
    assert final.accepted_samples == final.accounted_samples == 16000


def test_two_sessions_abort_and_engine_failure_are_isolated(tmp_path):
    asyncio.run(_two_sessions_abort_and_engine_failure_are_isolated(tmp_path))


async def _two_sessions_abort_and_engine_failure_are_isolated(tmp_path):
    scripts = {
        "one": ([(GeminiBase(16000, (GeminiSegment(0, 8000, "one"),)),)], ()),
        "two": ([()], ()),
    }
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")
    rt.create(session_id="two")
    rt.accept_frame("one", frame(0))
    rt.accept_frame("two", frame(0))
    assert rt.snapshot("one").session.effective_transcript[0].text == "one"
    assert rt.snapshot("two").session.effective_transcript == ()
    await rt.abort("two", "operator_abort")
    assert rt.snapshot("two").session.status == "aborted"
    assert rt.snapshot("one").session.status == "active"

    async def broken(_tape):
        raise ConnectionError("provider unavailable")

    rt._sessions["one"].engine.finish = broken
    await rt.stop("one", 1.0)
    await rt.wait_terminal("one")
    failed = rt.snapshot("one")
    assert failed.session.finalization_status == "failed"
    assert failed.session.status == "closed"
    assert failed.session.accepted_samples == 16000
    assert failed.terminal_failure is None
    assert "terminal_finalization_failed" in [event.kind for event in rt.events("one")]


def test_live_engine_error_is_visible_and_fences_only_its_session(tmp_path):
    scripts = {"one": ([()], ()), "two": ([()], ())}
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")
    rt.create(session_id="two")

    def broken(_start, _pcm):
        raise ConnectionError("GoAway")

    rt._sessions["one"].engine.push_audio = broken
    with pytest.raises(ConnectionError, match="GoAway"):
        rt.accept_frame("one", frame(0))
    assert rt.snapshot("one").session.status == "failed"
    assert rt.snapshot("one").session.finalization_status == "failed"
    assert rt.snapshot("one").terminal_failure.code == "gemini_live_failed"
    assert "session_tape_released" in [event.kind for event in rt.events("one")]
    assert rt.snapshot("two").session.status == "active"


def test_tape_degradation_is_unavailable_and_releases_scratch(tmp_path):
    async def run():
        rt = GeminiLiveRuntime(
            descriptor=descriptor(tape_bytes=16000), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _report_usage: ScriptedGeminiEngine(
                publish, batches=[()], terminal=(),
            ),
        )
        rt.create(session_id="one")
        rt.accept_frame("one", frame(0))
        stopped = await rt.stop("one", 1.0)
        assert stopped.session.finalization_status == "unavailable"
        assert "session_tape_released" in [event.kind for event in rt.events("one")]

    asyncio.run(run())


def test_engine_usage_counters_are_per_session_content_free_and_copied(tmp_path):
    reporters = {}

    def engine_factory(session_id, publish, report_usage):
        reporters[session_id] = report_usage
        report_usage(kind="live")  # Engine setup may make a provider request.
        return ScriptedGeminiEngine(publish, batches=[], terminal=())

    rt = GeminiLiveRuntime(descriptor=descriptor(), engine_factory=engine_factory,
                           tape_storage_root=tmp_path)
    rt.create(session_id="one")
    rt.create(session_id="two")
    reporters["one"](kind="rolling", audio_seconds_sent=10.0, cost_usd=0.03,
                     clamped_words=1, dropped_words=2)
    reporters["one"](kind="rolling", error_code="429", retry_code="429")
    reporters["two"](kind="terminal", audio_seconds_sent=20.0, cost_usd=0.02)
    first = rt.engine_diagnostics("one")
    assert first == {
        "calls_by_kind": {"live": 1, "rolling": 2}, "errors_by_code": {"429": 1},
        "retries_by_code": {"429": 1},
        "timing_anomalies": {"clamped": 1, "dropped": 2},
        "audio_seconds_sent": 10.0, "cost_usd": 0.03,
    }
    first["calls_by_kind"]["rolling"] = 999
    assert rt.engine_diagnostics("one")["calls_by_kind"]["rolling"] == 2
    assert rt.engine_diagnostics("two")["calls_by_kind"] == {"live": 1, "terminal": 1}
    with pytest.raises(ValueError):
        reporters["one"](kind="rolling", error_code="meeting words")
