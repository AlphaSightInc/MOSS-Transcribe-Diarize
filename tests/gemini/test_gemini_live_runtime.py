import asyncio
import hashlib
import time
from dataclasses import replace

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
from moss_transcribe_diarize.app.gemini_hybrid_engine import GeminiHybridEngine, FixedWindowScheduler, OverlapRegistry
from moss_transcribe_diarize.app.gemini_provider import GeminiWord, GeminiWords


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
    terminal_events = [event for event in rt.events("one") if event.kind == "text_revision_applied" and event.payload.get("source") == "terminal"]
    assert len(terminal_events) == 1
    assert {key: terminal_events[0].payload[key] for key in ("start_sample", "end_sample", "finalization_status")} == {"start_sample": 0, "end_sample": 16000, "finalization_status": "final"}


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
        rt._sessions["one"].tape.release()  # Simulate a real tape loss before Stop.
        stopped = await rt.stop("one", 1.0)
        assert stopped.session.finalization_status == "unavailable"
        assert rt._sessions["one"].tape.accounting(through_sample=16000).released

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
    assert {key: first[key] for key in ("calls_by_kind", "errors_by_code", "retries_by_code", "timing_anomalies", "audio_seconds_sent", "cost_usd")} == {
        "calls_by_kind": {"live": 1, "rolling": 2}, "errors_by_code": {"429": 1},
        "retries_by_code": {"429": 1},
        "timing_anomalies": {"clamped": 1, "dropped": 2},
        "audio_seconds_sent": 10.0, "cost_usd": 0.03,
    }
    first["calls_by_kind"]["rolling"] = 999
    assert rt.engine_diagnostics("one")["calls_by_kind"]["rolling"] == 2
    assert rt.engine_diagnostics("two")["calls_by_kind"] == {"live": 1, "terminal": 1}
    reporters["one"](kind="live_preview", count_call=False, audio_seconds_sent=2.5,
                     cost_usd=2.5 * 0.005 / 60, cost_basis="list_price_estimate")
    estimated = rt.engine_diagnostics("one")
    assert estimated["calls_by_kind"] == {"live": 1, "rolling": 2}
    assert estimated["audio_seconds_sent"] == 12.5
    assert estimated["live_list_price_estimate_usd"] == pytest.approx(2.5 * 0.005 / 60)
    assert estimated["cost_usd_basis"] == "provider_usage_plus_live_list_price_estimate"
    with pytest.raises(ValueError):
        reporters["one"](kind="rolling", error_code="meeting words")


def test_stale_preview_after_degraded_commit_is_ignored(tmp_path):
    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=[], terminal=()),
    )
    rt.create(session_id="one")
    for sequence in range(50):
        rt.accept_frame("one", frame(sequence))
    rt.publish_update("one", GeminiBase(10*16000, (), degraded=True))
    rt.publish_update("one", GeminiPreview(5*16000, (GeminiSegment(0, 16000, "stale"),)))
    snap = rt.snapshot("one")
    assert snap.session.status == "active"
    assert snap.session.committed_samples == 10*16000
    assert rt.engine_diagnostics("one")["degraded_path_activations"] == 1


def test_account_stage_is_terminal_source_and_survives_view_release(tmp_path):
    from moss_transcribe_diarize.app.phase2_audio import LiveMeetingAudioStages, MeetingAudioArchive
    stages = LiveMeetingAudioStages(MeetingAudioArchive(tmp_path / "archive"), max_bytes=115_200_000)
    stages.reserve("owner", "one")
    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path / "scratch",
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=[], terminal=(GeminiSegment(0, 16000, "hello", "speaker-0001"),)),
    )
    rt.bind_account_audio_stages(stages)
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))  # Legacy mono route writes into the same stage.
    assert stages.get("one").path.stat().st_size == 32000
    async def finish():
        await rt.stop("one", 1.0)
        await rt.wait_terminal("one")
    asyncio.run(finish())
    assert rt.snapshot("one").session.finalization_status == "final"
    assert stages.get("one").path.exists()  # Account owns durable audio settlement.
    assert not (tmp_path / "scratch").exists()  # No duplicate whole-recording tape.
    stages.discard("owner", "one")


def test_rolling_public_snapshot_contains_speaker_turns(tmp_path):
    class Diarizer:
        def diarize(self, _pcm, *, deadline, kind, diarize=True):
            del deadline, kind, diarize
            return GeminiWords((GeminiWord("a", "spk:0", 0, 8000),
                                GeminiWord("b", "spk:0", 12800, 24000),
                                GeminiWord("c", "spk:0", 51200, 64000),
                                GeminiWord("d", "spk:1", 67200, 80000)))
    class EmptyWords:
        def words(self, _pcm, *, deadline):
            del deadline
            return ()
    class Terminal:
        def transcribe(self, _tape):
            return ()
    base = descriptor()
    full = replace(base, bounds=replace(base.bounds, max_retained_samples=60*16000,
                                        max_tape_bytes=20*32000))
    rt = GeminiLiveRuntime(
        descriptor=full, tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: GeminiHybridEngine(
            publish, word_source=EmptyWords(), window_scheduler=FixedWindowScheduler(),
            registry=OverlapRegistry(), diarizer=Diarizer(), terminal=Terminal()),
    )
    rt.create(session_id="one")
    for sequence in range(20):
        rt.accept_frame("one", frame(sequence))
    until = time.monotonic() + 2
    while rt.snapshot("one").session.canonical_through_sample < 10*16000 and time.monotonic() < until:
        time.sleep(0.01)
    rows = rt.snapshot("one").to_dict()["session"]["effective_transcript"]
    assert [(row["text"], row["start_sample"], row["end_sample"]) for row in rows] == [
        ("a b", 0, 24000), ("c", 51200, 64000), ("d", 67200, 80000)]
    assert rows[0]["canonical_speaker"] == rows[1]["canonical_speaker"]
    assert rows[1]["canonical_speaker"] != rows[2]["canonical_speaker"]
    rt._sessions["one"].engine.close()


def test_stop_drains_rolling_tail_before_session_closes(tmp_path):
    async def run():
        first = GeminiSegment(0, 16000, "first", "speaker-0001")
        tail = GeminiSegment(16000, 32000, "tail", "speaker-0001")
        class DrainingEngine(ScriptedGeminiEngine):
            async def drain_tail(self, deadline):
                assert deadline > 0
                self._publish(GeminiBase(32000, ()))
                self._publish(GeminiRolling(16000, 32000, (tail,)))
                return True
        rt = GeminiLiveRuntime(
            descriptor=descriptor(tape_bytes=16000), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage: DrainingEngine(
                publish, batches=[(GeminiBase(16000, ()), GeminiRolling(0, 16000, (first,))), ()],
                terminal=()),
        )
        rt.create(session_id="one")
        rt.accept_frame("one", frame(0))
        rt.accept_frame("one", frame(1))
        before = rt.snapshot("one").session
        assert before.canonical_through_sample == 16000
        stopped = await rt.stop("one", 1.0)
        assert stopped.session.status == "closed"
        assert stopped.session.canonical_through_sample == stopped.session.accepted_samples == 32000
        assert [(row.text, row.authority) for row in stopped.session.effective_transcript] == [
            ("first", "rolling"), ("tail", "rolling")]
    asyncio.run(run())


def test_streaming_preview_reaches_public_snapshot_before_rolling(tmp_path):
    class FastSource:
        def bind(self, listener): self.listener = listener
        def push_audio(self, start_sample, pcm16):
            self.listener("fast words", start_sample, start_sample + len(pcm16)//2, False)
        async def finish(self): pass
        def close(self): pass
    class Diarizer:
        def diarize(self, _pcm, *, deadline, kind, diarize=True):
            return GeminiWords(())
    class Terminal:
        def transcribe(self, _tape): return ()
    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: GeminiHybridEngine(
            publish, word_source=FastSource(), window_scheduler=FixedWindowScheduler(),
            registry=OverlapRegistry(), diarizer=Diarizer(), terminal=Terminal()),
    )
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))
    session = rt.snapshot("one").to_dict()["session"]
    assert session["committed_samples"] == 0
    assert session["effective_transcript"] == []
    assert "[S00]fast words" in session["provisional"]["transcript"]
    rt._sessions["one"].engine.close()


def test_snapshot_pending_work_tracks_uncovered_accepted_audio(tmp_path):
    first = GeminiSegment(0, 16000, "first", "speaker-0001")
    tail = GeminiSegment(16000, 32000, "tail", "speaker-0001")
    rt = runtime(tmp_path, {"one": ([
        (GeminiBase(16000, ()), GeminiRolling(0, 16000, (first,))),
        (),
    ], ())})
    assert rt.create(session_id="one").snapshot.pending_work_items == 0
    rt.accept_frame("one", frame(0))
    assert rt.snapshot("one").pending_work_items == 0
    rt.accept_frame("one", frame(1))
    payload = rt.snapshot("one").to_dict()
    assert payload["pending_work_items"] == 1
    assert payload["session"]["accepted_samples"] == 32000
    assert payload["session"]["canonical_through_sample"] == 16000
    rt.publish_update("one", GeminiBase(32000, ()))
    assert rt.snapshot("one").session.committed_samples == 32000
    assert rt.snapshot("one").pending_work_items == 1  # Empty base is not labelled coverage.
    rt.publish_update("one", GeminiRolling(16000, 32000, (tail,)))
    assert rt.snapshot("one").pending_work_items == 0


def test_idle_ingress_drains_accepted_tail_before_stop_and_not_during_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(GeminiHybridEngine, "_IDLE_SECONDS", .08)
    calls = []
    class StreamingWords:
        def bind(self, listener): self.listener = listener
        def push_audio(self, start_sample, pcm16): pass
        async def finish(self): pass
        def close(self): pass
    class Diarizer:
        def diarize(self, pcm, *, deadline, kind, diarize=True):
            calls.append((len(pcm)//2, kind))
            end = len(pcm)//2
            return GeminiWords((GeminiWord("tail", "local", end-16000, end),))
    class Terminal:
        def transcribe(self, tape): return ()
    base = descriptor(tape_bytes=20*32000)
    full = replace(base, bounds=replace(base.bounds, max_retained_samples=60*16000))
    rt = GeminiLiveRuntime(descriptor=full, tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: GeminiHybridEngine(
            publish, word_source=StreamingWords(), window_scheduler=FixedWindowScheduler(),
            registry=OverlapRegistry(), diarizer=Diarizer(), terminal=Terminal()))
    rt.create(session_id="one")
    for sequence in range(6):
        rt.accept_frame("one", frame(sequence))
        assert rt.snapshot("one").pending_work_items == 1
        time.sleep(.02)
    assert calls == []  # Continuous ingress kept resetting the idle clock.
    until = time.monotonic() + 2
    while rt.snapshot("one").pending_work_items and time.monotonic() < until:
        time.sleep(.01)
    settled = rt.snapshot("one")
    assert settled.pending_work_items == 0
    assert settled.session.status == "active"
    assert settled.session.accepted_samples == settled.session.canonical_through_sample == 6*16000
    assert [row.text for row in settled.session.effective_transcript] == ["tail"]
    assert calls == [(6*16000, "rolling")]
    rt._sessions["one"].engine.close()
