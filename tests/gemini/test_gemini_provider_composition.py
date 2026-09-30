"""Per-meeting provider clients at the Gemini composition root (plan r3 I-2/I-3, Q4)."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from moss_transcribe_diarize.app import phase2_web_cli as cli
from moss_transcribe_diarize.app.gemini_live_runtime import ApiKeyRequired, validate_engine_settings
from moss_transcribe_diarize.app.live_service_runtime import LiveServiceBounds


class FakeGenaiClient:
    made: list["FakeGenaiClient"] = []

    def __init__(self, *, api_key, http_options=None):
        self.api_key = api_key
        self.interactions = SimpleNamespace(sdk_configuration=SimpleNamespace(
            retry_config=SimpleNamespace(strategy="default")))
        FakeGenaiClient.made.append(self)


class FakePreviewSource:
    def __init__(self, client, report_usage):
        self.client = client


class FakeNoPreviewWords:
    pass


class FakeAdapter:
    """The I-5 call surface: diarize(pcm16, *, deadline, kind, diarize=True) -> GeminiWords."""

    def __init__(self, url, model, api_key, report_usage):
        self.url, self.model, self.api_key = url, model, api_key
        self.report_usage = report_usage

    def diarize(self, pcm16, *, deadline, kind="rolling", diarize=True):
        raise AssertionError("not called in composition tests")


@pytest.fixture
def composition(monkeypatch, tmp_path):
    FakeGenaiClient.made = []
    monkeypatch.setattr("google.genai.Client", FakeGenaiClient)
    monkeypatch.setattr("moss_transcribe_diarize.app.gemini_live_words.GeminiLiveWordSource",
                        FakePreviewSource)
    adapter = ModuleType("moss_transcribe_diarize.app.openai_compatible_provider")
    adapter.OpenAICompatibleDiarizer = FakeAdapter
    adapter.NoPreviewWords = FakeNoPreviewWords
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    config = SimpleNamespace(source_revision="test",
                             bounds_config={"max_tape_bytes": 64000, "frame_samples": 16000})
    encoder = SimpleNamespace(spec=SimpleNamespace(
        provider="wespeaker", revision="pinned", state_sha256="ab" * 32, embedding_dimension=4))
    monkeypatch.setattr("moss_transcribe_diarize.app.live_provider_bundle.LiveProviderBundleConfig"
                        ".from_manifest", lambda _path: config)
    monkeypatch.setattr("moss_transcribe_diarize.app.live_provider_bundle._identity_encoder",
                        lambda _config, **_kwargs: encoder)
    monkeypatch.setattr("moss_transcribe_diarize.app.live_provider_bundle._bounds",
                        lambda _payload: LiveServiceBounds(
                            max_frame_samples=16000, max_queue_depth=4, max_retained_samples=32000,
                            max_identity_speakers=8, max_events=64, max_tape_bytes=64000))
    args = cli.parse_args(["--tls-certfile", "cert", "--tls-keyfile", "key",
                           "--live-provider-manifest", "manifest",
                           "--live-helper-lease-seconds", "10", "--live-engine", "gemini",
                           "--file-work-root", str(tmp_path / "file-work")])
    return cli._build_gemini_live_runtime_factory(args)


def engine(runtime, settings):
    return runtime._engine_factory("meeting", lambda _update: None, lambda **_usage: None,
                                   validate_engine_settings(settings))


def test_server_starts_without_any_key_and_advertises_v3_options(composition, monkeypatch):
    monkeypatch.delenv("MOSS_GEMINI_API_KEY", raising=False)
    runtime = composition()
    assert FakeGenaiClient.made == []  # No client, and no key, exists before a meeting.
    assert not hasattr(cli, "_gemini_key")
    assert runtime.descriptor.to_dict()["engine_options"] == {
        "transcription_vendors": ["gemini", "openai_compatible"],
        "default_model": "gemini-3.5-transcribe",
        "refresh_seconds": {"min": 5, "max": 60, "default": 15},
        "context_seconds": {"min": 90, "max": 300, "default": 90},
        "cleanup_after_stop": {"available": True, "default": True}}


def test_each_gemini_meeting_builds_its_own_client_from_its_key(composition):
    runtime = composition()
    first = engine(runtime, {"transcription": {"api_key": "key-one", "model": "gemini-x"},
                             "refresh_seconds": 20, "context_seconds": 180})
    second = engine(runtime, {"transcription": {"api_key": "key-two"}})
    try:
        assert [client.api_key for client in FakeGenaiClient.made] == ["key-one", "key-two"]
        assert FakeGenaiClient.made[0].interactions.sdk_configuration.retry_config.strategy == "none"
        system, mic = first._engines["system"], first._engines["microphone"]
        for lane in (system, mic):
            assert lane.diarizer.diarizer.client is FakeGenaiClient.made[0]
            assert lane.diarizer.diarizer.model == "gemini-x"  # Rolling + clean-up model.
            assert lane.word_source.source_factory().client is FakeGenaiClient.made[0]
        assert (system.window_scheduler.stride_seconds, system.window_scheduler.max_seconds) == (20, 180)
        # The microphone lane keeps its measured 30 s context / 15 s refresh.
        assert (mic.window_scheduler.stride_seconds, mic.window_scheduler.max_seconds) == (15, 30)
        default = second._engines["system"]
        assert default.diarizer.diarizer.model == "gemini-3.5-transcribe"
        assert (default.window_scheduler.stride_seconds, default.window_scheduler.max_seconds) == (15, 90)
    finally:
        first.close()
        second.close()


def test_openai_compatible_meeting_uses_the_adapter_without_instant_words(composition):
    runtime = composition()
    lane_engine = engine(runtime, {"transcription": {
        "vendor": "openai_compatible", "url": "http://127.0.0.1:18720/v1", "model": "whisper-1",
        "api_key": "local-key"}, "cleanup_after_stop": True})
    try:
        assert FakeGenaiClient.made == []
        for lane in lane_engine._engines.values():
            adapter = lane.diarizer.diarizer
            assert isinstance(adapter, FakeAdapter)
            assert (adapter.url, adapter.model, adapter.api_key) == (
                "http://127.0.0.1:18720/v1", "whisper-1", "local-key")
            assert lane.word_source.source_factory is FakeNoPreviewWords
    finally:
        lane_engine.close()


def test_meeting_without_a_key_never_falls_back_to_a_process_key(composition, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "process-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "process-key")
    runtime = composition()
    with pytest.raises(ApiKeyRequired):
        runtime._engine_factory("meeting", lambda _update: None, lambda **_usage: None)
    assert FakeGenaiClient.made == []


def test_file_jobs_build_the_diarizer_from_the_jobs_settings(composition):
    gemini = cli._file_transcription_diarizer(
        {"vendor": "gemini", "url": None, "model": "gemini-x", "api_key": "job-key"})
    assert (gemini.client.api_key, gemini.model) == ("job-key", "gemini-x")
    compatible = cli._file_transcription_diarizer(
        {"vendor": "openai_compatible", "url": "http://127.0.0.1:18720/v1", "model": "m",
         "api_key": None})
    assert isinstance(compatible, FakeAdapter) and compatible.api_key is None
    # A job resumed after a restart has no key and fails through the File failure path.
    with pytest.raises(RuntimeError, match="not kept across a restart"):
        cli._file_transcription_diarizer(None)
