import asyncio
import hashlib
import time
import wave
from dataclasses import replace

import pytest

from moss_transcribe_diarize.app.gemini_live_runtime import (
    GeminiBase,
    GeminiLiveRuntime,
    GeminiPreview,
    GeminiRolling,
    GeminiRelabel,
    GeminiSegment,
    GeminiTurnBridge,
    LiveServiceStopPending,
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


def settings(**overrides):
    """A complete v3 engine settings payload (I-2) with a test Gemini key."""
    return {"transcription": {"vendor": "gemini", "model": "gemini-3.5-transcribe",
                              "api_key": "test-key"}, **overrides}


def test_stop_request_timeout_does_not_cut_off_server_tail_drain(tmp_path):
    async def run():
        class LateTail:
            def __init__(self, publish): self.publish = publish
            def push_audio(self, start, pcm):
                if start == 0:
                    self.publish(GeminiBase(16000, ()))
                    self.publish(GeminiRolling(0, 16000, (
                        GeminiSegment(0, 8000, "first", "speaker-0001"),)))
            async def drain_tail(self, deadline):
                assert deadline > .05
                await asyncio.sleep(.05)
                self.publish(GeminiBase(32000, ()))
                self.publish(GeminiRolling(16000, 32000, (
                    GeminiSegment(16000, 24000, "tail", "speaker-0001"),)))
                return True
            def close(self): pass
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings=None: LateTail(publish))
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=False))
        rt.accept_frame("one", frame(0))
        rt.accept_frame("one", frame(1))
        with pytest.raises(LiveServiceStopPending):
            await rt.stop("one", .01)
        await asyncio.sleep(.1)
        snap = rt.snapshot("one").session
        assert snap.finalization_status == "final"
        assert [row.text for row in snap.effective_transcript] == ["first", "tail"]
    asyncio.run(run())


def test_cleanup_stop_commits_live_text_before_held_refinement(tmp_path):
    async def run():
        release = asyncio.Event()

        class HeldTerminal(ScriptedGeminiEngine):
            async def finish(self, tape):
                await release.wait()
                return (GeminiSegment(0, 8000, "improved", "terminal-a"),)

        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings: HeldTerminal(
                publish, batches=[], terminal=()))
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
        rt.accept_frame("one", frame(0))
        rt.publish_update("one", GeminiBase(16000, ()))
        rt.publish_update("one", GeminiRolling(0, 16000, (
            GeminiSegment(0, 8000, "live", "speaker-0001"),)))
        stopped = await rt.stop("one", 1)
        assert stopped.session.status == "closed"
        assert stopped.session.finalization_status == "running"
        assert [row.text for row in stopped.session.effective_transcript] == ["live"]
        assert [row.authority for row in stopped.session.effective_transcript] == ["rolling"]
        release.set()
        await rt.wait_terminal("one")
        assert [row.text for row in rt.snapshot("one").session.effective_transcript] == ["improved"]

    asyncio.run(run())


def test_refinement_timeout_keeps_live_text(tmp_path, monkeypatch):
    import moss_transcribe_diarize.app.gemini_live_runtime as module
    monkeypatch.setattr(module, "GEMINI_REFINEMENT_TIMEOUT_SECONDS", .01, raising=False)

    class HungTerminal(ScriptedGeminiEngine):
        async def finish(self, tape):
            await asyncio.Event().wait()

    async def run():
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings: HungTerminal(
                publish, batches=[], terminal=()))
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
        rt.accept_frame("one", frame(0))
        rt.publish_update("one", GeminiBase(16000, ()))
        rt.publish_update("one", GeminiRolling(0, 16000, (
            GeminiSegment(0, 8000, "live", "speaker-0001"),)))
        await rt.stop("one", 1)
        await rt.wait_terminal("one")
        snapshot = rt.snapshot("one").session
        assert snapshot.finalization_status == "failed"
        assert [row.text for row in snapshot.effective_transcript] == ["live"]

    asyncio.run(run())


def test_stop_tail_recovery_failure_is_incomplete_not_final(tmp_path):
    async def run():
        class FailedTail:
            def __init__(self, publish): self.publish = publish
            def push_audio(self, start, pcm):
                if start == 0:
                    self.publish(GeminiBase(16000, ()))
                    self.publish(GeminiRolling(0, 16000, (
                        GeminiSegment(0, 8000, "first", "speaker-0001"),)))
            async def drain_tail(self, deadline): return False
            async def recover_tail(self, deadline): raise RuntimeError("terminal unavailable")
            def close(self): pass
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage: FailedTail(publish))
        rt.create(session_id="one")
        rt.accept_frame("one", frame(0))
        rt.accept_frame("one", frame(1))
        snap = (await rt.stop("one", 1)).session
        assert snap.finalization_status == "unavailable"
        assert [row.text for row in snap.effective_transcript] == ["first"]
    asyncio.run(run())


def test_stop_uses_terminal_tail_recovery_after_drain_refusal(tmp_path):
    async def run():
        class RecoveringTail:
            def __init__(self, publish): self.publish = publish
            def push_audio(self, start, pcm):
                if start == 0:
                    self.publish(GeminiBase(16000, ()))
                    self.publish(GeminiRolling(0, 16000, (
                        GeminiSegment(0, 8000, "first", "speaker-0001"),)))
            async def drain_tail(self, deadline): return False
            async def recover_tail(self, deadline):
                self.publish(GeminiBase(32000, ()))
                self.publish(GeminiRolling(16000, 32000, (
                    GeminiSegment(16000, 24000, "recovered", "speaker-0001"),)))
                return True
            def close(self): pass
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings=None: RecoveringTail(publish))
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=False))
        rt.accept_frame("one", frame(0))
        rt.accept_frame("one", frame(1))
        snap = (await rt.stop("one", 1)).session
        assert snap.finalization_status == "final"
        assert [row.text for row in snap.effective_transcript] == ["first", "recovered"]
    asyncio.run(run())


def runtime(tmp_path, scripts):
    def engine_factory(session_id, publish, _report_usage, _settings=None):
        batches, terminal = scripts[session_id]
        return ScriptedGeminiEngine(publish, batches=batches, terminal=terminal)

    return GeminiLiveRuntime(descriptor=descriptor(), engine_factory=engine_factory,
                             tape_storage_root=tmp_path)


def test_meeting_settings_reach_engine_and_are_recorded(tmp_path):
    seen = []
    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _sid, publish, _usage, settings: (
            seen.append(settings) or ScriptedGeminiEngine(publish, batches=[], terminal=())))
    rt.create(session_id="one", engine_settings=settings(
        refresh_seconds=20, context_seconds=180, cleanup_after_stop=True))
    expected = {"transcription": {"vendor": "gemini", "url": None,
                                  "model": "gemini-3.5-transcribe", "api_key": "test-key"},
                "refresh_seconds": 20, "context_seconds": 180, "cleanup_after_stop": True}
    assert seen == [expected]
    # The engine factory alone receives the key; diagnostics carry a redacted copy.
    assert rt.engine_diagnostics("one")["engine_settings"] == {
        **expected, "transcription": {**expected["transcription"], "api_key": "[redacted]"}}
    assert "test-key" not in repr(rt.snapshot("one").to_dict())


def test_omitted_gemini_settings_default_to_background_cleanup(tmp_path):
    rt = runtime(tmp_path, {"one": ([], ())})
    rt.create(session_id="one")
    assert rt.engine_diagnostics("one")["engine_settings"] == {
        "transcription": {"vendor": "gemini", "url": None,
                          "model": "gemini-3.5-transcribe", "api_key": None},
        "refresh_seconds": 15, "context_seconds": 90, "cleanup_after_stop": True}


def test_engine_options_are_advertised_only_when_supplied():
    assert "engine_options" not in descriptor().to_dict()
    options = {"transcription_vendors": ["gemini", "openai_compatible"],
               "default_model": "gemini-3.5-transcribe",
               "refresh_seconds": {"min": 5, "max": 60, "default": 15},
               "context_seconds": {"min": 90, "max": 300, "default": 90},
               "cleanup_after_stop": {"available": True, "default": True}}
    assert replace(descriptor(), engine_options=options).to_dict()["engine_options"] == options


@pytest.mark.parametrize("value", [
    {"speaker_window": "balanced"}, {"cleanup_after_stop": "false"},
    {"other": 1}, {"refresh_seconds": 4}, {"refresh_seconds": 61}, {"refresh_seconds": 15.0},
    {"refresh_seconds": True}, {"context_seconds": 89}, {"context_seconds": 301},
    {"transcription": {"vendor": "other", "api_key": "k"}},
    {"transcription": {"api_key": "k", "extra": 1}},
    {"transcription": {"api_key": 7}},
    {"transcription": {"vendor": "openai_compatible", "model": "m"}},
    {"transcription": {"vendor": "openai_compatible", "url": "ftp://x", "model": "m"}},
    {"transcription": {"vendor": "openai_compatible", "url": "http://x"}}, []])
def test_meeting_settings_reject_unknown_keys_and_values(tmp_path, value):
    rt = runtime(tmp_path, {})
    payload = value if not isinstance(value, dict) or "transcription" in value else settings(**value)
    with pytest.raises(ValueError):
        rt.create(session_id="one", engine_settings=payload)


@pytest.mark.parametrize("transcription", [None, {}, {"api_key": ""}, {"api_key": "  "},
                                           {"vendor": "gemini", "api_key": None}])
def test_gemini_transcription_requires_the_users_key(tmp_path, transcription):
    from moss_transcribe_diarize.app.gemini_live_runtime import ApiKeyRequired
    rt = runtime(tmp_path, {})
    payload = {} if transcription is None else {"transcription": transcription}
    with pytest.raises(ApiKeyRequired):
        rt.create(session_id="one", engine_settings=payload)


def test_openai_compatible_settings_force_cleanup_off_and_ignore_gemini_defaults():
    from moss_transcribe_diarize.app.gemini_live_runtime import validate_engine_settings
    validated = validate_engine_settings({
        "transcription": {"vendor": "openai_compatible", "url": " http://127.0.0.1:18720/v1/ ",
                          "model": "whisper-1", "api_key": ""},
        "cleanup_after_stop": True})
    assert validated["transcription"] == {"vendor": "openai_compatible",
                                          "url": "http://127.0.0.1:18720/v1",
                                          "model": "whisper-1", "api_key": None}
    assert validated["cleanup_after_stop"] is False
    gemini = validate_engine_settings({"transcription": {
        "vendor": "gemini", "url": "https://ignored", "model": "", "api_key": "k"}})
    assert gemini["transcription"] == {"vendor": "gemini", "url": None,
                                       "model": "gemini-3.5-transcribe", "api_key": "k"}
    # The multipart File/URL field carries the same object as a JSON string.
    from moss_transcribe_diarize.app.gemini_live_runtime import validate_transcription
    assert validate_transcription('{"api_key": "k"}') == gemini["transcription"]


def test_cost_and_veto_counters_are_content_free_and_per_lane(tmp_path):
    rt = runtime(tmp_path, {"one": ([], ())})
    rt.create(session_id="one")
    rt.record_engine_call("one", kind="system_rolling", audio_seconds_sent=90,
                          cost_usd=.01, output_cost_estimate_usd=.003, veto_fired=2)
    rt.record_engine_call("one", kind="microphone_gate", count_call=False,
                          mic_echo_dropped_by_voice=3)
    diagnostic = rt.engine_diagnostics("one")
    assert diagnostic["cost_usd"] == .01
    assert diagnostic["output_cost_estimate_usd"] == .003
    assert diagnostic["veto_fired"] == 2
    assert diagnostic["mic_echo_dropped_by_voice"] == 3
    assert diagnostic["lanes"]["system"]["veto_fired"] == 2
    assert diagnostic["lanes"]["microphone"]["mic_echo_dropped_by_voice"] == 3


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


def test_combined_rolling_revision_keeps_overlapping_capture_lanes(tmp_path):
    system = GeminiSegment(0, 12000, "remote", "speaker-0001", "system")
    microphone = GeminiSegment(4000, 14000, "local", "speaker-0002", "microphone")
    scripts = {"one": ([(GeminiBase(16000, ()),
                         GeminiRolling(0, 16000, (system, microphone),
                                       revision_lanes=("system", "microphone")))],
                       (system, microphone))}
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")
    rt.accept_frame("one", AudioFrame(0, bytes(32000), 16000,
                                     lane_pcm=(("system", bytes(32000)),
                                               ("microphone", bytes(32000)))))
    snapshot = rt.snapshot("one").to_dict()
    assert [(row["source_lane"], row["canonical_speaker"]) for row in
            snapshot["session"]["effective_transcript"]] == [
                ("system", "speaker-0001"), ("microphone", "speaker-0002")]
    assert rt._sessions["one"].session._lane_revision_frontiers == {
        "system": 16000, "microphone": 16000}


def test_unborn_continuity_word_renders_s00_without_registering_speaker(tmp_path):
    unknown = GeminiSegment(0, 8000, "brief", None, "system")
    scripts = {"one": ([(GeminiBase(16000, ()),
                         GeminiRolling(0, 16000, (unknown,),
                                       revision_lanes=("system",)))], ())}
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")
    rt.accept_frame("one", AudioFrame(0, bytes(32000), 16000,
                                     lane_pcm=(("system", bytes(32000)),
                                               ("microphone", bytes(32000)))))
    session = rt.snapshot("one").to_dict()["session"]
    assert session["identity_snapshot"]["canonical_speakers"] == []
    assert [(row["text"], row["canonical_speaker"], row["source_lane"])
            for row in session["effective_transcript"]] == [("brief", None, "system")]


def test_runtime_passes_aligned_pcm_lanes_to_lane_engine(tmp_path):
    got = []
    class Engine:
        def push_audio(self, start_sample, pcm16):
            raise AssertionError("lane engine must receive source lanes")
        def push_lanes(self, start_sample, lane_pcm):
            got.append((start_sample, dict(lane_pcm)))
        async def drain_tail(self, deadline): return False
        async def finish(self, tape): return ()
    rt = GeminiLiveRuntime(descriptor=descriptor(),
        engine_factory=lambda _sid, _publish, _usage: Engine(),
        tape_storage_root=tmp_path)
    rt.create(session_id="one")
    rt.accept_frame("one", AudioFrame(0, bytes(32000), 16000,
        lane_pcm=(("system", b"\x01\x00"*16000),
                  ("microphone", b"\x02\x00"*16000))))
    assert len(got) == 1 and got[0][0] == 0
    assert {lane: (len(audio), audio[:2]) for lane, audio in got[0][1].items()} == {
        "system": (32000, b"\x01\x00"), "microphone": (32000, b"\x02\x00")}


def test_engine_diagnostics_exposes_content_free_per_lane_totals(tmp_path):
    rt = runtime(tmp_path, {"one": ([], ())})
    rt.create(session_id="one")
    rt.record_engine_call("one", kind="system_rolling", audio_seconds_sent=30,
                          cost_usd=.01, metered_output_usd=.003, clamped_words=1)
    rt.record_engine_call("one", kind="microphone_rolling", audio_seconds_sent=30,
                          cost_usd=.01, metered_output_usd=.002, dropped_words=2)
    rt.record_engine_call("one", kind="microphone_rolling", count_call=False,
                          skipped_window_ticks=1)
    lanes = rt.snapshot("one").to_dict()["engine_diagnostics"]["lanes"]
    assert lanes["system"]["calls_by_kind"] == {"rolling": 1}
    assert lanes["system"]["timing_anomalies"] == {"clamped": 1, "dropped": 0}
    assert lanes["system"]["skipped_window_ticks"] == 0
    assert lanes["microphone"]["calls_by_kind"] == {"rolling": 1}
    assert lanes["microphone"]["timing_anomalies"] == {"clamped": 0, "dropped": 2}
    assert lanes["microphone"]["skipped_window_ticks"] == 1
    assert lanes["microphone"]["audio_seconds_sent"] == 30
    assert lanes["microphone"]["cost_usd"] == .01
    assert lanes["microphone"]["metered_output_usd"] == .002
    assert lanes["system"]["metered_output_usd"] == .003
    assert rt.engine_diagnostics("one")["metered_output_usd"] == .005


def test_engine_diagnostics_records_repaired_words_and_chunked_terminal(tmp_path):
    rt = runtime(tmp_path, {"one": ([], ()), "two": ([], ())})
    rt.create(session_id="one")
    rt.create(session_id="two")
    rt.record_engine_call("one", kind="system_rolling", repaired_words=2,
                          audio_seconds_sent=60)
    rt.record_engine_call("one", kind="system_terminal", count_call=False,
                          chunked=True)
    one = rt.engine_diagnostics("one")
    assert one["repaired_words"] == 2 and one["chunked"] is True
    assert one["calls_by_kind"] == {"system_rolling": 1}
    assert one["lanes"]["system"]["repaired_words"] == 2
    assert one["lanes"]["system"]["chunked"] is True
    assert rt.engine_diagnostics("two")["chunked"] is False
    assert rt.engine_diagnostics("two")["repaired_words"] == 0


def test_terminal_maps_overlapping_labels_within_each_capture_lane(tmp_path):
    async def run():
        system = GeminiSegment(0, 14000, "remote", "speaker-0001", "system")
        microphone = GeminiSegment(0, 14000, "local", "speaker-microphone", "microphone")
        terminal = (GeminiSegment(0, 14000, "remote", "terminal-a", "system"),
                    GeminiSegment(0, 14000, "local", "terminal-b", "microphone"))
        rt = runtime(tmp_path, {"one": ([(GeminiBase(16000, ()),
                                           GeminiRolling(0, 16000, (system, microphone),
                                               revision_lanes=("system", "microphone")))],
                                 terminal)})
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
        rt.accept_frame("one", frame(0))
        await rt.stop("one", 1.0)
        await rt.wait_terminal("one")
        final = rt.snapshot("one").session
        assert final.finalization_status == "final"
        assert [row.source_lane for row in final.effective_transcript] == [
            "system", "microphone"]
        assert len({row.canonical_speaker for row in final.effective_transcript}) == 2
    asyncio.run(run())


def test_terminal_coverage_gap_preserves_live_rows_in_final_revision(tmp_path):
    async def run():
        class GapEngine(ScriptedGeminiEngine):
            terminal_coverage_gaps = (("system", 2*16000, 20*16000),)
        final = (GeminiSegment(0, 2*16000, "opening final", "terminal-a", "system"),)
        rt = GeminiLiveRuntime(
            descriptor=descriptor(tape_bytes=20*32000), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings: GapEngine(
                publish, batches=(), terminal=final))
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
        for second in range(20):
            rt.accept_frame("one", frame(second))
        rt.publish_update("one", GeminiBase(20*16000, ()))
        rt.publish_update("one", GeminiRolling(0, 20*16000, (
            GeminiSegment(0, 2*16000, "opening live", "speaker-0001", "system"),
            GeminiSegment(2*16000, 20*16000, "protected live speech", "speaker-0001", "system")),
            revision_lanes=("system",)))
        await rt.stop("one", 1.0)
        await rt.wait_terminal("one")
        session = rt.snapshot("one").session
        assert session.finalization_status == "final"
        assert [(row.text, row.canonical_speaker) for row in session.effective_transcript] == [
            ("opening final", "speaker-0001"),
            ("protected live speech", "speaker-0001")]
    asyncio.run(run())


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
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
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


def test_f13_relabel_counts_only_previously_speakerless_rows(tmp_path):
    unknown = GeminiSegment(0, 8000, "brief", None)
    known = GeminiSegment(0, 8000, "brief", "speaker-0001")
    rt = runtime(tmp_path, {"one": ([(GeminiBase(16000, ()),
                                      GeminiRolling(0, 16000, (unknown,)),
                                      GeminiRelabel(0, 8000, (known,)))], ())})
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))
    assert rt.snapshot("one").session.effective_transcript[0].canonical_speaker == "speaker-0001"
    assert rt.engine_diagnostics("one")["f13_relabels"] == 1


def test_f13_relabel_keeps_overlapping_other_lane_row(tmp_path):
    system = GeminiSegment(0, 8000, "remote", None, "system")
    mic = GeminiSegment(0, 8000, "local", "local-0001", "microphone")
    known = GeminiSegment(0, 8000, "remote", "speaker-0001", "system")
    rt = runtime(tmp_path, {"one": ([(GeminiBase(16000, ()),
        GeminiRolling(0, 16000, (system, mic), revision_lanes=("system", "microphone")),
        GeminiRelabel(0, 8000, (known,)))], ())})
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))
    assert [(row.text, row.canonical_speaker) for row in
            rt.snapshot("one").session.effective_transcript] == [
                ("remote", "speaker-0001"), ("local", "local-0001")]


def test_refused_stale_f13_relabel_does_not_fail_live_meeting(tmp_path):
    first = GeminiSegment(0, 4000, "first", None)
    second = GeminiSegment(6000, 8000, "second", None)
    known = GeminiSegment(0, 4000, "first", "speaker-0001")
    rt = runtime(tmp_path, {"one": ([(GeminiBase(16000, ()),
        GeminiRolling(0, 16000, (first, second)),
        GeminiTurnBridge(0, 4000, 6000), GeminiRelabel(0, 4000, (known,)))], ())})
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))
    assert rt.snapshot("one").session.status == "active"
    assert rt.snapshot("one").session.effective_transcript[0].canonical_speaker is None
    diagnostic = rt.engine_diagnostics("one")
    assert diagnostic["f13_relabel_refused"] == 1
    assert diagnostic["f13_relabels"] == 0


def test_refused_stale_f13_relabel_during_stop_still_finalizes(tmp_path):
    first = GeminiSegment(0, 4000, "first", None)
    second = GeminiSegment(6000, 8000, "second", None)
    known = GeminiSegment(0, 4000, "first", "speaker-0001")
    class TailEngine(ScriptedGeminiEngine):
        async def drain_tail(self, deadline):
            self._publish(GeminiRelabel(0, 4000, (known,)))
            return True
    rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage, _settings: TailEngine(publish,
            batches=[(GeminiBase(16000, ()), GeminiRolling(0, 16000, (first, second)),
                      GeminiTurnBridge(0, 4000, 6000))], terminal=()))
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
    rt.accept_frame("one", frame(0))
    async def finish():
        await rt.stop("one", 1.0)
        await rt.wait_terminal("one")
    asyncio.run(finish())
    assert rt.snapshot("one").session.finalization_status == "final"
    assert rt.engine_diagnostics("one")["f13_relabel_refused"] == 1


def _orphan_stop_runtime(tmp_path, *, orphan_audio: int, cleanup: bool = False,
                         second_lane: str = "system"):
    class Encoder:
        spec = type("Spec", (), {"provider": "fake", "revision": "one",
                                "embedding_dimension": 2, "state_sha256": "0" * 64})()
        def embed(self, path, intervals):
            with wave.open(path, "rb") as source:
                value = int.from_bytes(source.readframes(1), "little", signed=True)
            return {1: (1., 0.), 2: (0., 1.), 3: (-1., 0.)}[value]
    second_id = "speaker-0002" if second_lane == "system" else "local-0001"
    rows = (GeminiSegment(0, 40000, "first", "speaker-0001", "system"),
            GeminiSegment(48000, 88000, "second", second_id, second_lane),
            GeminiSegment(88000, 91200, "yeah", "speaker-0003", "system"))
    batches = [()] * 5 + [(GeminiBase(96000, ()),
                           GeminiRolling(0, 96000, rows,
                                         revision_lanes=tuple(dict.fromkeys(r.source_lane for r in rows))))]
    rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage, _settings: ScriptedGeminiEngine(
            publish, batches=batches, terminal=rows), voiceprint_encoder=Encoder())
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=cleanup))
    for sequence in range(6):
        if sequence == 5:
            pcm = b"\x02\x00" * 8000 + orphan_audio.to_bytes(2, "little") * 8000
        else:
            pcm = (1 if sequence < 3 else 2).to_bytes(2, "little") * 16000
        rt.accept_frame("one", AudioFrame(sequence=sequence, pcm=pcm, sample_count=16000))
    return rt


def test_stop_absorbs_short_orphan_into_nearest_same_lane_speaker(tmp_path):
    rt = _orphan_stop_runtime(tmp_path, orphan_audio=2)
    stopped = asyncio.run(rt.stop("one", 1.0))
    rows = stopped.session.effective_transcript
    assert [(row.text, row.canonical_speaker) for row in rows] == [
        ("first", "speaker-0001"), ("second", "speaker-0002"),
        ("yeah", "speaker-0002")]
    assert rt.engine_diagnostics("one")["orphan_speakers_absorbed"] == 1


def test_stop_orphan_without_fingerprint_match_becomes_tbd(tmp_path):
    rt = _orphan_stop_runtime(tmp_path, orphan_audio=3)
    stopped = asyncio.run(rt.stop("one", 1.0))
    assert stopped.session.effective_transcript[-1].canonical_speaker is None
    assert stopped.session.effective_transcript[-1].text == "yeah"
    assert rt.engine_diagnostics("one")["orphan_speakers_absorbed"] == 0


def test_stop_does_not_absorb_orphan_into_other_lane(tmp_path):
    rt = _orphan_stop_runtime(tmp_path, orphan_audio=2, second_lane="microphone")
    stopped = asyncio.run(rt.stop("one", 1.0))
    assert stopped.session.effective_transcript[-1].canonical_speaker is None
    assert rt.engine_diagnostics("one")["orphan_speakers_absorbed"] == 0


def test_refused_orphan_relabel_is_counted_without_failing_stop(tmp_path, monkeypatch):
    rt = _orphan_stop_runtime(tmp_path, orphan_audio=2)
    session = rt._sessions["one"].session
    monkeypatch.setattr(session, "revise_rolling_interval", lambda **_kwargs:
                        session._text_revision_outcome(
                            applied=False, refusal="rolling_interval_not_owned"))
    stopped = asyncio.run(rt.stop("one", 1.0))
    assert stopped.session.finalization_status == "final"
    assert stopped.session.effective_transcript[-1].canonical_speaker == "speaker-0003"
    assert rt.engine_diagnostics("one")["orphan_relabel_refused"] == 1


def test_stop_keeps_manually_named_short_speaker(tmp_path):
    rt = _orphan_stop_runtime(tmp_path, orphan_audio=2)
    rt.note_manual_speaker("one", "speaker-0003")
    stopped = asyncio.run(rt.stop("one", 1.0))
    assert stopped.session.effective_transcript[-1].canonical_speaker == "speaker-0003"
    assert rt.engine_diagnostics("one")["orphan_speakers_absorbed"] == 0


def test_cleanup_on_keeps_terminal_short_speaker(tmp_path):
    rt = _orphan_stop_runtime(tmp_path, orphan_audio=2, cleanup=True)
    async def finish():
        await rt.stop("one", 1.0)
        await rt.wait_terminal("one")
    asyncio.run(finish())
    assert rt.snapshot("one").session.effective_transcript[-1].canonical_speaker != "speaker-0003"
    assert rt.engine_diagnostics("one")["orphan_speakers_absorbed"] >= 0


@pytest.mark.parametrize("cleanup,expected_text,terminal_calls", [
    (False, "live words", 0), (True, "terminal words", 1)])
def test_stop_cleanup_setting_controls_terminal_pass(tmp_path, cleanup, expected_text,
                                                     terminal_calls):
    calls = []
    class Engine(ScriptedGeminiEngine):
        def __init__(self, publish):
            super().__init__(publish, batches=[(GeminiBase(16000, ()),
                GeminiRolling(0, 16000, (GeminiSegment(0, 8000, "live words", "speaker-0001"),)))],
                terminal=(GeminiSegment(0, 8000, "terminal words", "speaker-0001"),))
        async def drain_tail(self, deadline): return True
        async def finish(self, tape):
            calls.append("terminal")
            return await super().finish(tape)
    async def run():
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings: Engine(publish))
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=cleanup))
        rt.accept_frame("one", frame(0))
        await rt.stop("one", 1.0)
        await rt.wait_terminal("one")
        final = rt.snapshot("one").session
        assert final.finalization_status == "final"
        assert [row.text for row in final.effective_transcript] == [expected_text]
        assert [row.authority for row in final.effective_transcript] == ["terminal"]
        assert len(calls) == terminal_calls
    asyncio.run(run())


def test_live_only_final_preserves_both_lanes(tmp_path):
    system = GeminiSegment(0, 40000, "remote", "speaker-0001", "system")
    mic = GeminiSegment(0, 40000, "local", "local-0001", "microphone")
    rt = runtime(tmp_path, {"one": (((), (), (GeminiBase(48000, ()),
        GeminiRolling(0, 48000, (system, mic), revision_lanes=("system", "microphone")))), ())})
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=False))
    for sequence in range(3):
        rt.accept_frame("one", frame(sequence))
    stopped = asyncio.run(rt.stop("one", 1.0))
    assert stopped.session.finalization_status == "final"
    assert [(row.source_lane, row.text, row.canonical_speaker) for row in
            stopped.session.effective_transcript] == [
                ("system", "remote", "speaker-0001"),
                ("microphone", "local", "local-0001")]


@pytest.mark.parametrize("vector,expected", [((1., 0.), "speaker-0001"), ((0., 1.), None)])
def test_stop_fingerprint_relabels_remaining_speakerless_row(tmp_path, vector, expected):
    class Encoder:
        spec = type("Spec", (), {"provider": "fake", "revision": "one",
                                 "embedding_dimension": 2, "state_sha256": "0" * 64})()
        def embed(self, path, intervals):
            assert intervals == [(0.0, .5)]
            return vector
    class WaitingEngine(ScriptedGeminiEngine):
        def __init__(self, publish):
            super().__init__(publish, batches=[(GeminiBase(16000, ()),
                                                GeminiRolling(0, 16000,
                                                    (GeminiSegment(0, 8000, "brief", None),)))],
                             terminal=())
            self.release = asyncio.Event()
        async def drain_tail(self, deadline): return True
        async def finish(self, tape):
            await self.release.wait()
            return ()
    async def run():
        engines = []
        rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
            engine_factory=lambda _id, publish, _usage, _settings: (
                engines.append(WaitingEngine(publish)) or engines[-1]),
            voiceprint_encoder=Encoder())
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
        rt.accept_frame("one", frame(0))
        rt._sessions["one"].voice_observations["speaker-0001"] = type(
            "Observation", (), {"centroid": (1., 0.)})()
        rt.note_manual_speaker("one", "speaker-0001")
        stopped = await rt.stop("one", 1.0)
        assert stopped.session.effective_transcript[0].canonical_speaker == expected
        assert rt.engine_diagnostics("one")["f13_relabels"] == int(expected is not None)
        engines[0].release.set()
        await rt.wait_terminal("one")
    asyncio.run(run())


def test_two_sessions_abort_and_engine_failure_are_isolated(tmp_path):
    asyncio.run(_two_sessions_abort_and_engine_failure_are_isolated(tmp_path))


async def _two_sessions_abort_and_engine_failure_are_isolated(tmp_path):
    scripts = {
        "one": ([(GeminiBase(16000, (GeminiSegment(0, 8000, "one"),)),)], ()),
        "two": ([()], ()),
    }
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
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
    rt.publish_update("one", GeminiRolling(0, 16000, (
        GeminiSegment(0, 8000, "one", "speaker-0001"),)))
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
            engine_factory=lambda _id, publish, _report_usage, _settings: ScriptedGeminiEngine(
                publish, batches=[()], terminal=(),
            ),
        )
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
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
    reporters["one"](kind="microphone_gate", count_call=False,
                     acoustic_gate_dropped_words=3, text_guard_dropped_words=2)
    gates = rt.engine_diagnostics("one")
    assert gates["mic_words_dropped_by_acoustic_gate"] == 3
    assert gates["mic_words_dropped_by_text_guard"] == 2
    assert gates["lanes"]["microphone"]["mic_words_dropped_by_acoustic_gate"] == 3
    assert gates["lanes"]["microphone"]["mic_words_dropped_by_text_guard"] == 2
    assert "microphone_gate" not in gates["calls_by_kind"]
    reporters["one"](kind="system_live_preview", count_call=False,
                     preview_stall_restarts=1)
    reporters["one"](kind="system_rolling", count_call=False, coverage_retry=1,
                     coverage_preview_fallbacks=1)
    reporters["one"](kind="system_terminal", count_call=False,
                     coverage_retry=1, terminal_coverage_fallbacks=1)
    diagnostics = rt.engine_diagnostics("one")
    assert (diagnostics["preview_stall_restarts"], diagnostics["coverage_retries"],
            diagnostics["terminal_coverage_fallbacks"]) == (1, 2, 1)
    assert diagnostics["coverage_preview_fallbacks"] == 1
    assert diagnostics["lanes"]["system"]["coverage_retries"] == 2
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


def test_account_stage_keeps_recording_past_the_first_hour(tmp_path):
    """Issue #1: a 1 h floor stopped the stage at 60 min; saved audio went partial, no post-Stop pass."""
    import os
    from moss_transcribe_diarize.app.phase2_audio import LiveMeetingAudioStages, MeetingAudioArchive
    rt = GeminiLiveRuntime(
        descriptor=descriptor(tape_bytes=9_600_000),  # the deployed manifest's own bound
        tape_storage_root=tmp_path / "scratch",
        engine_factory=lambda _id, publish, _usage, _settings: ScriptedGeminiEngine(
            publish, batches=[], terminal=()),
    )
    assert rt.descriptor.bounds.max_tape_bytes >= 3 * 60 * 60 * 16000 * 2
    stages = LiveMeetingAudioStages(MeetingAudioArchive(tmp_path / "archive"),
                                    max_bytes=rt.descriptor.bounds.max_tape_bytes)
    stages.reserve("owner", "one")
    rt.bind_account_audio_stages(stages)
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
    stage = stages.get("one")
    os.ftruncate(stage._fd, 60 * 60 * 16000 * 2)  # an hour already staged (sparse)
    os.lseek(stage._fd, 0, os.SEEK_END)
    rt.accept_frame("one", frame(0))
    assert not stage.degraded
    assert stage.path.stat().st_size == 60 * 60 * 16000 * 2 + 32000
    stages.release("one")
    stages.discard("owner", "one")


def test_meeting_longer_than_the_refinement_bound_keeps_its_live_transcript(tmp_path, monkeypatch):
    """The post-Stop pass holds whole lanes in RAM (~0.9 GB/h measured); past its bound the
    meeting settles on the live transcript instead of attempting it."""
    from moss_transcribe_diarize.app import gemini_live_runtime
    from moss_transcribe_diarize.app.phase2_audio import LiveMeetingAudioStages, MeetingAudioArchive
    monkeypatch.setattr(gemini_live_runtime, "GEMINI_MAX_REFINEMENT_SECONDS", 1)
    stages = LiveMeetingAudioStages(MeetingAudioArchive(tmp_path / "archive"), max_bytes=10**9)
    stages.reserve("owner", "one")
    finished = []

    class Engine(ScriptedGeminiEngine):
        async def finish(self, tape):
            finished.append(tape)
            return ()

    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path / "scratch",
        engine_factory=lambda _id, publish, _usage, _settings: Engine(publish, batches=[], terminal=()))
    rt.bind_account_audio_stages(stages)
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
    for sequence in range(2):
        rt.accept_frame("one", frame(sequence))
    rt.publish_update("one", GeminiBase(32000, ()))
    rt.publish_update("one", GeminiRolling(0, 32000, (GeminiSegment(0, 32000, "live", "speaker-0001"),)))
    asyncio.run(rt.stop("one", 1.0))
    assert rt.snapshot("one").session.finalization_status == "unavailable"
    assert [event.payload.get("reason") for event in rt.events("one")
            if event.kind == "terminal_finalization_unavailable"] == ["meeting_exceeds_refinement_bound"]
    assert finished == []
    assert not stages.get("one").degraded  # The saved audio stays whole.
    stages.release("one")
    stages.discard("owner", "one")


def test_account_stage_is_terminal_source_and_survives_view_release(tmp_path):
    from moss_transcribe_diarize.app.phase2_audio import LiveMeetingAudioStages, MeetingAudioArchive
    stages = LiveMeetingAudioStages(MeetingAudioArchive(tmp_path / "archive"), max_bytes=115_200_000)
    stages.reserve("owner", "one")
    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path / "scratch",
        engine_factory=lambda _id, publish, _usage, _settings: ScriptedGeminiEngine(
            publish, batches=[], terminal=(GeminiSegment(0, 16000, "hello", "speaker-0001"),)),
    )
    rt.bind_account_audio_stages(stages)
    rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=True))
    rt.accept_frame("one", frame(0))  # Legacy mono route writes into the same stage.
    rt.publish_update("one", GeminiBase(16000, ()))
    rt.publish_update("one", GeminiRolling(0, 16000, (
        GeminiSegment(0, 16000, "live", "speaker-0001"),)))
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


def test_system_first_voiced_word_reaches_public_preview_after_silent_ingress(tmp_path):
    import wave
    from pathlib import Path
    from moss_transcribe_diarize.app.gemini_lane_engine import VoicedLiveWords, WebRtcSpeechDetector
    from moss_transcribe_diarize.app.gemini_hybrid_engine import GrowingContextWindowScheduler
    opened = []
    class LiveSource:
        def __init__(self): opened.append(time.monotonic())
        def bind(self, listener): self.listener = listener
        def push_audio(self, start_sample, pcm16):
            self.listener("first", start_sample, start_sample + 8000, False)
        async def finish(self): pass
        def close(self): pass
    class NoBatch:
        def diarize(self, *_args, **_kwargs):
            raise AssertionError("2 s ingress must not open a batch window")
        def transcribe(self, _tape): return ()
    rt = GeminiLiveRuntime(
        descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: GeminiHybridEngine(
            publish,
            word_source=VoicedLiveWords(LiveSource, voiced_audio=WebRtcSpeechDetector()),
            window_scheduler=GrowingContextWindowScheduler(max_seconds=180, stride_seconds=15),
            registry=OverlapRegistry(), diarizer=NoBatch(), terminal=NoBatch(),
            source_lane="system"),
    )
    rt.create(session_id="one")
    rt.accept_frame("one", frame(0))
    assert not opened and rt.snapshot("one").session.provisional is None
    with wave.open(str(Path(__file__).parents[1] / "fixtures/idea_020_provider_smoke.wav"), "rb") as wav:
        voice = wav.readframes(16000)
    started = time.monotonic()
    rt.accept_frame("one", AudioFrame(sequence=1, pcm=voice, sample_count=16000))
    provisional = rt.snapshot("one").to_dict()["session"]["provisional"]
    assert len(opened) == 1
    assert time.monotonic() - started < 1.0
    assert provisional["transcript"] == "[1][S00]first[1.5]"
    rt._sessions["one"].engine.close()


def test_public_provisional_suffix_collapses_overlapping_echo_preview(tmp_path):
    import re
    from moss_transcribe_diarize.app.gemini_lane_engine import LaneGeminiEngine
    from moss_transcribe_diarize.app.gemini_live_runtime import GeminiPreview

    class IdleLane:
        def __init__(self, publish): self.publish = publish
        def push_audio(self, start_sample, pcm16): pass
        def close(self): pass

    engines = []
    def factory(_id, publish, _usage):
        engine = LaneGeminiEngine(
            publish, system_factory=IdleLane, microphone_factory=IdleLane,
            tape_root=tmp_path)
        engines.append(engine)
        return engine

    rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
                           engine_factory=factory)
    rt.create(session_id="one")
    for second in range(10):
        rt.accept_frame("one", frame(second))
    system_text = "After researching Nvidia for something like 500 hours"
    echoed_text = "After researching NVIDIA forsomething like 500 hours. At the time"
    engines[0]._on_update("system", GeminiPreview(10*16000, (
        GeminiSegment(0, round(8.5*16000), system_text, source_lane="system"),)))
    engines[0]._on_update("microphone", GeminiPreview(10*16000, (
        GeminiSegment(0, 10*16000, echoed_text, source_lane="microphone"),)))
    transcript = rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"]
    assert transcript == f"[0][S00]{system_text}[8.5]"
    engines[0]._on_update("microphone", GeminiPreview(10*16000, (
        GeminiSegment(0, 10*16000, "local operator", source_lane="microphone"),)))
    transcript = rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"]
    assert "local operator" in transcript and system_text in transcript

    # P64 lead-final-merged-E1 at committed_samples=4560000: the two W3 lanes
    # chunk the same speech at 0/4.5/10.5/17.5 s, so neither pair has equal starts.
    for second in range(10, 18):
        rt.accept_frame("one", frame(second))
    system_long = (
        "NVIDIA 1 and NVIDIA 2 were based on forward texture mapping, no triangles but curves "
        "and it tessellated the curves and because we were rendering higher level objects we "
        "essentially avoided using z-buffers and we thought that that was going to be a good "
        "rendering approach and turns out to have been completely the wrong answer.what Riva "
        "128 was was a reset of our company. Now remember, at the time that we started the "
        "company in 1993, we were the only consumer 3D graphics company ever created and we "
        "we were focused on transforming the PC into an accelerated PC because at the time "
        "Windows was really a software rendered system. And so anyways, Riva 128"
    )
    mic_head = (
        "So what Revo 128 was was a reset of our company. Now remember at the time that we "
        "started the company 1993 we were the only consumer 3D graphics company ever created "
        "and we we were focused on transforming the PC into an accelerator PC because at the time"
    )
    mic_tail = (
        "was really a software rendered system. And so anyways, Riva 128was a reset of our "
        "company because by the time that we realized we had gone down the wrong road, "
        "Microsoft had already rolled out Direct"
    )
    system_tail = (
        "was a reset of our company because by the time that we realized we had gone down "
        "the wrong road, Microsoft had already rolled out Direct"
    )
    sec = lambda value: round(value * 16000)
    engines[0]._on_update("system", GeminiPreview(sec(18), (
        GeminiSegment(0, sec(10.5), system_long, source_lane="system"),
        GeminiSegment(sec(10.5), sec(17.5), system_tail, source_lane="system"))))
    engines[0]._on_update("microphone", GeminiPreview(sec(18), (
        GeminiSegment(0, sec(4.5), mic_head, source_lane="microphone"),
        GeminiSegment(sec(4.5), sec(17.5), mic_tail, source_lane="microphone"))))
    def visible_texts():
        rendered = rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"]
        return re.findall(r"\[S00\](.*?)\[[0-9.]+\]", rendered)
    assert visible_texts() == [system_long, system_tail]

    operator = "Can you pause? I need to check my microphone."
    engines[0]._on_update("microphone", GeminiPreview(sec(18), (
        GeminiSegment(0, sec(4.5), mic_head, source_lane="microphone"),
        GeminiSegment(sec(4.5), sec(17.5), mic_tail, source_lane="microphone"),
        GeminiSegment(sec(12), sec(17.5), operator, source_lane="microphone"))))
    assert visible_texts() == [system_long, system_tail, operator]

    engines[0]._on_update("system", GeminiPreview(sec(18), ()))
    engines[0]._on_update("microphone", GeminiPreview(sec(18), (
        GeminiSegment(0, sec(4.5), "stale replay", source_lane="microphone"),
        GeminiSegment(0, sec(5), "replacement", source_lane="microphone"))))
    assert visible_texts() == ["replacement"]
    engines[0].close()


def test_public_preview_trims_committed_speech_in_same_lane(tmp_path):
    rt = GeminiLiveRuntime(
        descriptor=descriptor(tape_bytes=15 * 32000), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=(), terminal=()),
    )
    rt.create(session_id="one")
    for second in range(15):
        rt.accept_frame("one", frame(second))
    committed = (
        "and you guys have about 6 months of cash left. And so you decide to do the entire "
        "testing in simulation rather than ever receiving a physical prototype. You commission "
        "the production run sight unseen with the rest of the company's money. So you're "
        "betting it all right here on the"
    )
    repeated = (
        "you guys have about six months of cash left. And you're running out of money. "
        "And so you decide to do the entire testing in simulation rather than ever receiving "
        "a physical prototype. You commission the production run sight unseen with the rest "
        "of the company's money. So you're betting it all right here on the Rivian 120"
    )
    rt.publish_update("one", GeminiBase(10 * 16000, ()))
    rt.publish_update("one", GeminiRolling(0, 10 * 16000, (
        GeminiSegment(0, 10 * 16000, committed, "speaker-0001", "system"),),
        revision_lanes=("system",)))
    rt.publish_update("one", GeminiPreview(15 * 16000, (
        GeminiSegment(10 * 16000, 15 * 16000, repeated, source_lane="system"),)))
    session = rt.snapshot("one").to_dict()["session"]
    assert session["effective_transcript"][-1]["text"] == committed
    assert session["provisional"]["transcript"] == "[0][S00]Rivian 120[5]"

    rt.publish_update("one", GeminiPreview(15 * 16000, (
        GeminiSegment(10 * 16000, 15 * 16000, committed,
                      source_lane="system"),)))
    assert rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"] == ""
    fresh = "The next prototype is ready for testing."
    rt.publish_update("one", GeminiPreview(15 * 16000, (
        GeminiSegment(10 * 16000, 15 * 16000, fresh,
                      source_lane="system"),)))
    assert rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"] == (
        f"[0][S00]{fresh}[5]")

    rt.publish_update("one", GeminiPreview(15 * 16000, (
        GeminiSegment(10 * 16000, 15 * 16000,
                      "Can you pause? I need to check my microphone.",
                      source_lane="microphone"),)))
    assert "Can you pause? I need to check my microphone." in (
        rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"])


def test_public_preview_keeps_new_speech_that_shares_common_words(tmp_path):
    """E1 regression (lead, 2026-09-28): scattered common words must not trim new speech."""
    rt = GeminiLiveRuntime(
        descriptor=descriptor(tape_bytes=15 * 32000), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=(), terminal=()),
    )
    rt.create(session_id="one")
    for second in range(15):
        rt.accept_frame("one", frame(second))
    committed = (
        "and you guys have about 6 months of cash left. And so you decide to do the entire "
        "testing in simulation rather than ever receiving a physical prototype. You commission "
        "the production run sight unseen with the rest of the company's money. So you're "
        "betting it all right here on the"
    )
    fresh = (
        "Yeah. It comes back and of the 32 DirectX blend modes, it supports eight of them. "
        "And you have to convince the market to buy it, and you got to convince developers "
        "not to use anything but those eight blend modes."
    )
    rt.publish_update("one", GeminiBase(10 * 16000, ()))
    rt.publish_update("one", GeminiRolling(0, 10 * 16000, (
        GeminiSegment(0, 10 * 16000, committed, "speaker-0001", "system"),),
        revision_lanes=("system",)))
    rt.publish_update("one", GeminiPreview(15 * 16000, (
        GeminiSegment(10 * 16000, 15 * 16000, fresh, source_lane="system"),)))
    assert rt.snapshot("one").to_dict()["session"]["provisional"]["transcript"] == (
        f"[0][S00]{fresh}[5]")


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
            engine_factory=lambda _id, publish, _usage, _settings=None: DrainingEngine(
                publish, batches=[(GeminiBase(16000, ()), GeminiRolling(0, 16000, (first,))), ()],
                terminal=()),
        )
        rt.create(session_id="one", engine_settings=settings(cleanup_after_stop=False))
        rt.accept_frame("one", frame(0))
        rt.accept_frame("one", frame(1))
        before = rt.snapshot("one").session
        assert before.canonical_through_sample == 16000
        stopped = await rt.stop("one", 1.0)
        assert stopped.session.status == "closed"
        assert stopped.session.canonical_through_sample == stopped.session.accepted_samples == 32000
        assert [(row.text, row.authority) for row in stopped.session.effective_transcript] == [
            ("first", "terminal"), ("tail", "terminal")]
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


def test_skipped_window_ticks_are_per_session_content_free_diagnostics(tmp_path):
    rt = runtime(tmp_path, {"one": ([], ()), "two": ([], ())})
    rt.create(session_id="one")
    rt.create(session_id="two")
    rt.record_engine_call("one", kind="rolling", count_call=False, skipped_window_ticks=2)
    rt.record_engine_call("one", kind="rolling", count_call=False, skipped_window_ticks=1)
    one = rt.snapshot("one").to_dict()["engine_diagnostics"]
    two = rt.snapshot("two").to_dict()["engine_diagnostics"]
    assert one["skipped_window_ticks"] == 3
    assert one["calls_by_kind"] == {}
    assert two["skipped_window_ticks"] == 0
    with pytest.raises(ValueError):
        rt.record_engine_call("one", kind="rolling", count_call=False,
                              skipped_window_ticks=-1)


def test_preview_snapshot_keeps_lane_and_tentative_identity_outside_transcript(tmp_path):
    scripts = {"one": ([()], ())}
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")

    class Guesses:
        def __init__(self):
            self.audio = []
        def accept_audio(self, lane, start, pcm):
            self.audio.append((lane, start, len(pcm)))
        def spans(self, lane, start, end):
            if lane != "system":
                return ()
            return ({"start_sample": 8000, "end_sample": 16000,
                     "source_lane": "system", "speaker": "speaker-0001"},)
        def diagnostics(self):
            return {"tentative_shown_s": .5, "tentative_abstained_s": 0.0,
                    "tentative_embed_p50_ms": 12.0, "tentative_embed_p95_ms": 12.0,
                    "tentative_busy_ticks": 0}

    guesses = Guesses()
    rt._sessions["one"].tentative = guesses
    rt.accept_frame("one", AudioFrame(0, bytes(32000), 16000,
        lane_pcm=(("system", bytes(32000)), ("microphone", bytes(32000)))))
    rt.publish_update("one", GeminiPreview(16000, (
        GeminiSegment(8000, 16000, "hello", source_lane="system"),
        GeminiSegment(8000, 16000, "local", source_lane="microphone"))))
    snapshot = rt.snapshot("one").to_dict()
    provisional = snapshot["session"]["provisional"]
    assert provisional["segments"] == [
        {"start_sample": 8000, "end_sample": 16000, "text": "hello",
         "source_lane": "system", "tentative_speaker": "speaker-0001"},
        {"start_sample": 8000, "end_sample": 16000, "text": "local",
         "source_lane": "microphone", "tentative_speaker": None},
    ]
    assert "speaker-0001" not in provisional["transcript"]
    assert guesses.audio == [("system", 0, 32000), ("microphone", 0, 32000)]
    assert snapshot["engine_diagnostics"]["tentative_shown_s"] == .5
    assert all("speaker-0001" not in str(event.payload) for event in rt.events("one"))


def test_new_settled_speaker_seeds_tentative_centroid_in_its_first_window(tmp_path):
    from moss_transcribe_diarize.app.live_provider_bundle import LiveSpeakerJournalObservation

    class Encoder:
        spec = type("Spec", (), {"provider": "fake", "revision": "one",
                                 "embedding_dimension": 2, "state_sha256": "0" * 64})()
        def embed(self, path, intervals):
            return (0.0, 1.0)

    first = LiveSpeakerJournalObservation(
        speaker_label="speaker-0001", centroid=(1.0, 0.0), sample_seconds=2.0,
        exemplar_count=1, provisional=False, embedder_id="fake:one",
        embedder_state_sha="0" * 64)
    rt = GeminiLiveRuntime(descriptor=descriptor(), tape_storage_root=tmp_path,
        engine_factory=lambda _id, publish, _usage: ScriptedGeminiEngine(
            publish, batches=[], terminal=()), voiceprint_encoder=Encoder())
    rt.create(session_id="one")
    for sequence in range(4):
        rt.accept_frame("one", AudioFrame(sequence, b"\x01\x00" * 16000, 16000))
    rt.publish_update("one", GeminiBase(2 * 16000, ()))
    rt.publish_update("one", GeminiRolling(0, 2 * 16000,
        (GeminiSegment(0, 2 * 16000, "first", "speaker-0001", "system"),),
        (first,), ("system",)))
    rt.publish_update("one", GeminiBase(4 * 16000, ()))
    rt.publish_update("one", GeminiRolling(2 * 16000, 4 * 16000,
        (GeminiSegment(2 * 16000, 4 * 16000, "second", "speaker-0002", "system"),),
        (), ("system",)))
    state = rt._sessions["one"]
    assert set(state.voice_observations) == {"speaker-0001", "speaker-0002"}
    assert set(state.tentative._centroids["system"]) == {"speaker-0001", "speaker-0002"}
    state.tentative.close()


def test_failing_tentative_labeler_disables_guesses_but_never_fails_the_meeting(tmp_path):
    scripts = {"one": ([()], ())}
    rt = runtime(tmp_path, scripts)
    rt.create(session_id="one")

    class Broken:
        closed = False
        def accept_audio(self, lane, start, pcm):
            raise ValueError("tentative lane audio is not contiguous")
        def spans(self, lane, start, end):
            raise RuntimeError("spans")
        def observe(self, observations, *, lane="system"):
            raise RuntimeError("observe")
        def diagnostics(self):
            raise RuntimeError("diagnostics")
        def close(self):
            Broken.closed = True

    rt._sessions["one"].tentative = Broken()
    rt.accept_frame("one", AudioFrame(0, bytes(32000), 16000))
    rt.accept_frame("one", AudioFrame(1, bytes(32000), 16000))
    rt.publish_update("one", GeminiPreview(32000, (GeminiSegment(8000, 16000, "hello", source_lane="system"),)))
    snapshot = rt.snapshot("one").to_dict()
    assert snapshot["session"]["status"] == "active"
    assert snapshot.get("terminal_failure") is None
    assert snapshot["session"]["provisional"]["segments"][0]["tentative_speaker"] is None
    assert snapshot["engine_diagnostics"]["tentative_errors"] == 1
    assert Broken.closed and rt._sessions["one"].tentative is None
