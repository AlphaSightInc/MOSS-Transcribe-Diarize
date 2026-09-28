import pytest

from moss_transcribe_diarize.app.phase2_web_cli import _build_live_runtime_factory, main, parse_args


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
    monkeypatch.setattr("moss_transcribe_diarize.app.phase2_web_cli._build_gemini_live_runtime_factory",
                        lambda _args: (_ for _ in ()).throw(SystemExit("Gemini composition selected")))
    with pytest.raises(SystemExit, match="Gemini composition selected"):
        main(["--tls-certfile", "cert", "--tls-keyfile", "key",
              "--live-provider-manifest", "manifest", "--live-helper-lease-seconds", "10",
              "--live-engine", "gemini"])
