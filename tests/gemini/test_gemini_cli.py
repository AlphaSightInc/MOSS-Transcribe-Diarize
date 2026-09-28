import pytest

from moss_transcribe_diarize.app.phase2_web_cli import _build_live_runtime_factory, main, parse_args


def test_gemini_cli_selection_fails_before_starting_an_unmeasured_provider():
    argv = ["--tls-certfile", "cert", "--tls-keyfile", "key",
            "--live-provider-manifest", "manifest", "--live-helper-lease-seconds", "10"]
    assert parse_args(argv).live_engine == "moss"
    args = parse_args([*argv, "--live-engine", "gemini"])
    with pytest.raises(SystemExit, match="await the bake-off adapter"):
        _build_live_runtime_factory(args, object())


def test_gemini_cli_never_builds_the_moss_runner(monkeypatch):
    def unexpected(_args):
        raise AssertionError("MOSS file runner loaded before Gemini fail-fast")

    monkeypatch.setattr("moss_transcribe_diarize.app.phase2_web_cli._build_file_runner", unexpected)
    with pytest.raises(SystemExit, match="await the bake-off adapter"):
        main(["--tls-certfile", "cert", "--tls-keyfile", "key",
              "--live-provider-manifest", "manifest", "--live-helper-lease-seconds", "10",
              "--live-engine", "gemini"])
