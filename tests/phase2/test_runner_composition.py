from __future__ import annotations

from pathlib import Path
import sys
from types import ModuleType

import pytest

from moss_transcribe_diarize.app import runner_composition


def test_inference_options_share_file_defaults_and_drop_greedy_temperature():
    assert runner_composition.resolve_inference_options(
        prompt=" ",
        max_length=None,
        max_new_tokens=None,
        decoding=None,
        temperature=0.25,
        default_prompt="deployed prompt",
        default_max_length=4096,
        default_max_new_tokens=512,
        default_decoding="greedy",
        default_temperature=1.0,
        max_length_cap=4096,
    ) == {
        "prompt": "deployed prompt",
        "max_length": 4096,
        "max_new_tokens": 512,
        "decoding": "greedy",
        "temperature": None,
    }


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"decoding": "beam"}, "decoding must be greedy or sample"),
        ({"max_length": 0}, "max_length must be greater than 0"),
        ({"max_length": 4097}, "max_len must be less than or equal to 4096"),
        ({"max_new_tokens": 0}, "max_new_tokens must be greater than 0"),
        ({"decoding": "sample", "temperature": 0}, "temperature must be greater than 0"),
    ],
)
def test_inference_options_retain_the_deployed_refusal_contract(overrides, message):
    values = {
        "prompt": None,
        "max_length": None,
        "max_new_tokens": None,
        "decoding": None,
        "temperature": None,
        "default_prompt": None,
        "default_max_length": 4096,
        "default_max_new_tokens": 512,
        "default_decoding": "greedy",
        "default_temperature": 1.0,
        "max_length_cap": 4096,
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        runner_composition.resolve_inference_options(**values)


def test_live_runner_stays_lazy_and_reuses_one_runner(monkeypatch, tmp_path: Path):
    built: list[tuple[Path, str, str]] = []

    class Runner:
        model_path = "loaded-model"

        def __init__(self, model_path, *, device, dtype):
            built.append((model_path, device, dtype))

        def transcribe(self, audio_path, **kwargs):
            return (audio_path, kwargs)

    model_runner = ModuleType("moss_transcribe_diarize.app.model_runner")
    model_runner.ModelRunner = Runner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, model_runner.__name__, model_runner)
    lazy = runner_composition.LazyLiveRunner(
        model_path=tmp_path / "model",
        device="cpu",
        dtype="float32",
        backend="hf",
        vllm_base_url=None,
        vllm_model=None,
        vllm_api_key=None,
        vllm_timeout=30,
    )

    assert built == []
    assert lazy.transcribe("first.wav", decoding="greedy") == (
        "first.wav",
        {"decoding": "greedy"},
    )
    assert lazy.transcribe("second.wav") == ("second.wav", {})
    assert built == [(tmp_path / "model", "cpu", "float32")]
    assert lazy.model_path == "loaded-model"


def test_terminal_composition_none_prompt_builds_default_prompt_fields():
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT
    finalizer = runner_composition.build_terminal_finalizer(
        runner=object(), prompt=None, max_length=16384, max_new_tokens=12000,
        decoding='greedy', temperature=1., max_length_cap=16384,
    )
    options = finalizer.transcribe_kwargs
    assert options['prompt'] == DEFAULT_PROMPT
    fields = VllmRunner(base_url='http://unused/v1', model='test')._build_fields(
        **{key: options[key] for key in ('prompt', 'max_new_tokens', 'decoding', 'temperature')})
    assert fields['prompt'] == DEFAULT_PROMPT


def test_launcher_without_prompt_finalizer_builds_http_request(monkeypatch):
    import io
    import json
    from moss_transcribe_diarize.app.phase2_web_cli import parse_args, _build_file_runner
    from moss_transcribe_diarize.app.live_transcript_convergence import TerminalDecodePlan, RollingStatus
    from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT

    # Mirrors account-web-launcher.sh: deliberately no --prompt.
    args = parse_args([
        '--database', '/tmp/account.sqlite', '--control-socket', '/tmp/control.sock',
        '--tls-certfile', '/tmp/cert.pem', '--tls-keyfile', '/tmp/key.pem',
        '--backend', 'vllm', '--model', '/tmp/model',
        '--vllm-base-url', 'http://127.0.0.1:8000/v1',
        '--vllm-model', 'OpenMOSS-Team/MOSS-Transcribe-Diarize', '--vllm-timeout', '1800',
        '--file-work-root', '/tmp/file-work', '--meeting-audio-root', '/tmp/audio',
        '--live-provider-manifest', '/tmp/provider.json', '--live-helper-lease-seconds', '30',
        '--host', '0.0.0.0', '--port', '7861', '--max-len', '16384', '--max-new-tokens', '12000',
    ])
    assert args.prompt is None
    requests = []
    class Response(io.BytesIO):
        headers = {'Content-Type': 'application/json'}
    def fake_urlopen(request, **kwargs):
        requests.append(request)
        return Response(json.dumps({'text': '[0][S01]test[2.5]',
                        'usage': {'completion_tokens': 12, 'prompt_tokens': 10}}).encode())
    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    finalizer = runner_composition.build_terminal_finalizer(
        runner=_build_file_runner(args), prompt=args.prompt, max_length=args.max_len,
        max_new_tokens=args.max_new_tokens, decoding=args.decoding,
        temperature=args.temperature, max_length_cap=args.max_len,
    )
    class Tape:
        def gaps(self, end_sample): return ()
        def read(self, *, start_sample, end_sample): return b'\1\0' * (end_sample-start_sample)
    finalizer.finalize(
        plan=TerminalDecodePlan(epoch=0, end_sample=40000, rolling_through_sample=0,
            rolling_status=RollingStatus.ROLLING, windows_completed=0, windows_failed=0),
        tape=Tape(), base_text_revision_version=0,
    )
    assert len(requests) == 1
    assert requests[0].full_url == 'http://127.0.0.1:8000/v1/audio/transcriptions'
    assert DEFAULT_PROMPT.encode() in requests[0].data
    assert b'name="max_completion_tokens"\r\n\r\n12000' in requests[0].data


@pytest.mark.parametrize('prompt', [None, '', '   ', 'explicit instruction'])
def test_live_and_terminal_share_prompt_resolution(prompt):
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    from moss_transcribe_diarize.inference_utils import DEFAULT_PROMPT
    runner = VllmRunner(base_url='http://unused/v1', model='test')
    terminal = runner_composition.build_terminal_finalizer(
        runner=runner, prompt=prompt, max_length=16384, max_new_tokens=12000,
        decoding='greedy', temperature=1., max_length_cap=16384,
    )
    live_fields = runner._build_fields(prompt=prompt, max_new_tokens=286,
                                       decoding='greedy', temperature=None)
    assert live_fields['prompt'] == terminal.transcribe_kwargs['prompt']
    assert live_fields['prompt'] == (prompt if prompt and prompt.strip() else DEFAULT_PROMPT)


def test_file_album_default_legacy_fallback_and_live_terminal_isolation():
    from moss_transcribe_diarize.app.file_identity_album import AlbumIdentityResolver
    from moss_transcribe_diarize.app.speaker_identity import IdentityResolver
    config=dict(model_path='test',device='cpu',dtype='bf16',backend='vllm',
                vllm_base_url='http://unused/v1',vllm_model='test',vllm_api_key=None,vllm_timeout=30)
    file=runner_composition.build_file_runner(**config)
    assert isinstance(file.identity_resolver,AlbumIdentityResolver)
    fallback=runner_composition.build_file_runner(**config,file_identity='legacy')
    assert isinstance(fallback.identity_resolver,IdentityResolver)
    assert not fallback.identity_resolver.config.tier_b_enabled
    terminal=runner_composition.build_terminal_finalizer(runner=file,prompt=None,max_length=16384,
        max_new_tokens=12000,decoding='greedy',temperature=None,max_length_cap=16384)
    assert terminal.runner.delegate is file.delegate
    assert isinstance(terminal.runner.identity_resolver,IdentityResolver)
    assert isinstance(file.identity_resolver,AlbumIdentityResolver)
    with pytest.raises(ValueError):
        runner_composition.build_file_runner(**config,file_identity='typo')
