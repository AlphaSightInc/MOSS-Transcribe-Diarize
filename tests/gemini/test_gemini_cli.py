import pytest

from moss_transcribe_diarize.app.phase2_web_cli import _build_live_runtime_factory, main, parse_args


def test_c4_system_and_mic_window_defaults_at_composition_root():
    from moss_transcribe_diarize.app.gemini_hybrid_engine import GrowingContextWindowScheduler
    from moss_transcribe_diarize.app.phase2_web_cli import (
        GEMINI_WINDOW_LMAX_SECONDS, GEMINI_WINDOW_STRIDE_SECONDS,
        GEMINI_MIC_WINDOW_SECONDS, GEMINI_MIC_WINDOW_STRIDE_SECONDS,
        GEMINI_CONTINUITY_E, GEMINI_CONTINUITY_W, GEMINI_BIRTH_MIN_SECONDS)
    assert (GEMINI_WINDOW_STRIDE_SECONDS, GEMINI_WINDOW_LMAX_SECONDS) == (15, 90)
    assert (GEMINI_MIC_WINDOW_STRIDE_SECONDS, GEMINI_MIC_WINDOW_SECONDS) == (15, 30)
    assert (GEMINI_CONTINUITY_E, GEMINI_CONTINUITY_W, GEMINI_BIRTH_MIN_SECONDS) == (.46, .60, 2)
    system = GrowingContextWindowScheduler(
        max_seconds=GEMINI_WINDOW_LMAX_SECONDS, stride_seconds=GEMINI_WINDOW_STRIDE_SECONDS)
    microphone = GrowingContextWindowScheduler(
        max_seconds=GEMINI_MIC_WINDOW_SECONDS, stride_seconds=GEMINI_MIC_WINDOW_STRIDE_SECONDS)
    assert system.next_window(195*16000, 180*16000) == (105*16000, 195*16000, 195*16000)
    assert microphone.next_window(195*16000, 180*16000) == (165*16000, 195*16000, 195*16000)


def test_speaker_window_presets_have_frozen_stride_and_context():
    from moss_transcribe_diarize.app.gemini_live_runtime import GEMINI_SPEAKER_WINDOW_PRESETS
    assert GEMINI_SPEAKER_WINDOW_PRESETS == {
        "balanced": (15, 90), "economy": (30, 90), "max": (15, 180)}


def test_gemini_client_options_leave_retries_to_the_counted_adapter():
    from moss_transcribe_diarize.app.phase2_web_cli import _gemini_http_options
    options = _gemini_http_options()
    assert options.retry_options.attempts == 1
    assert options.base_url is None  # GOOGLE_GEMINI_BASE_URL remains effective.


def test_gemini_cli_selects_real_composition(monkeypatch):
    argv = ["--tls-certfile", "cert", "--tls-keyfile", "key",
            "--live-provider-manifest", "manifest", "--live-helper-lease-seconds", "10"]
    assert parse_args(argv).live_engine == "moss"
    args = parse_args([*argv, "--live-engine", "gemini"])
    sentinel = object()
    monkeypatch.setattr("moss_transcribe_diarize.app.phase2_web_cli._build_gemini_live_runtime_factory",
                        lambda _args: sentinel)
    assert _build_live_runtime_factory(args, object()) is sentinel


def test_gemini_cli_never_builds_the_moss_runner(monkeypatch):
    def unexpected(_args):
        raise AssertionError("MOSS file runner loaded in Gemini path")
    monkeypatch.setattr("moss_transcribe_diarize.app.phase2_web_cli._build_file_runner", unexpected)
    monkeypatch.setattr("moss_transcribe_diarize.app.phase2_web_cli._build_gemini_file_runner",
                        lambda _args: object())
    monkeypatch.setattr("moss_transcribe_diarize.app.phase2_web_cli._build_gemini_live_runtime_factory",
                        lambda _args: (_ for _ in ()).throw(SystemExit("Gemini composition selected")))
    with pytest.raises(SystemExit, match="Gemini composition selected"):
        main(["--tls-certfile", "cert", "--tls-keyfile", "key",
              "--live-provider-manifest", "manifest", "--live-helper-lease-seconds", "10",
              "--live-engine", "gemini"])


def test_gemini_file_runner_uses_the_live_manifest_encoder(monkeypatch):
    from moss_transcribe_diarize.app import phase2_web_cli as cli
    from types import SimpleNamespace
    encoder = object()
    config = SimpleNamespace()
    monkeypatch.setattr("moss_transcribe_diarize.app.live_provider_bundle.LiveProviderBundleConfig.from_manifest",
                        lambda _path: config)
    monkeypatch.setattr("moss_transcribe_diarize.app.live_provider_bundle._identity_encoder",
                        lambda actual, **_kwargs: encoder if actual is config else None)
    monkeypatch.setattr(cli, "_gemini_key", lambda: "test-key")
    monkeypatch.setattr(cli, "_gemini_client", lambda _key: object())
    args = parse_args(["--tls-certfile", "cert", "--tls-keyfile", "key",
                       "--live-provider-manifest", "manifest", "--live-helper-lease-seconds", "10",
                       "--live-engine", "gemini"])
    runner = cli._build_gemini_file_runner(args)
    assert runner._terminal.identity_policy.encoder is encoder
    assert runner.identity_resolver._encoder is encoder
