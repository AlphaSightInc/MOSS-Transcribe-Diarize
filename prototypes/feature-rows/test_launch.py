from __future__ import annotations

import json
import importlib.util
import socket
import subprocess
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "prototypes/feature-rows/launch.py"


def load_launcher() -> ModuleType:
    spec = importlib.util.spec_from_file_location("r4_f3s_launcher", LAUNCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load {LAUNCHER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_is_three_decoder_and_six_provider() -> None:
    plan = load_launcher().request_plan("freeze-sha")
    assert [clip["planned_decoder"] for clip in plan["clips"]] == [1, 2]
    assert plan["planned_decoder"] == 3
    assert plan["planned_provider"] == 6
    assert plan["actual_calls"] == {"decoder": 0, "provider": 0}


def test_plan_only_opens_no_socket_or_subprocess(monkeypatch, tmp_path: Path) -> None:
    def forbidden(*_args, **_kwargs):
        raise AssertionError("plan-only attempted dispatch")

    module = load_launcher()
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    output = tmp_path / "plan.json"
    assert module.main(["--plan-only", "--frozen-sha", "freeze-sha", "--out", str(output)]) == 0
    assert json.loads(output.read_text())["actual_calls"] == {"decoder": 0, "provider": 0}


@pytest.mark.parametrize("authorities", [[], ["--allow-decoder"], ["--allow-provider"]])
def test_run_refuses_without_both_authorities(monkeypatch, tmp_path: Path, authorities: list[str]) -> None:
    module = load_launcher()
    monkeypatch.setenv("OPENROUTER_API_KEY", "present")
    monkeypatch.setattr(module, "_product_diff", lambda _sha: (_ for _ in ()).throw(AssertionError("dispatched")))
    with pytest.raises(SystemExit, match="REFUSE: missing explicit row authority"):
        module.main([
            "--run", "--frozen-sha", "freeze-sha", "--out", str(tmp_path / "out"),
            "--decoder-upstream-port", "18400", "--budget", "3", *authorities,
        ])


def test_provider_key_is_inherited_only_and_never_written_or_in_argv(monkeypatch, tmp_path: Path) -> None:
    module = load_launcher()
    sentinel = "provider-secret-" + "sentinel-123456789"
    monkeypatch.setenv("OPENROUTER_API_KEY", sentinel)
    model = tmp_path / "model"
    model.mkdir()
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}\n")
    output = tmp_path / "out"
    seen: list[tuple[list[str], dict[str, str]]] = []

    class FakeProcess:
        pid = 12345

        def poll(self):
            return None

    class FakeDecoder:
        def __init__(self, _port, _upstream, _budget, log):
            self.log = log

        def set_row_owner(self, _row):
            self.log.write_text("")

        def clear_row_owner(self, _row):
            pass

        def start(self):
            pass

        def close(self):
            pass

    def fake_certificate(state: Path):
        cert, key = state / "cert.pem", state / "key.pem"
        cert.write_text("certificate")
        key.write_text("tls-key")
        return cert, key

    def fake_popen(argv, **kwargs):
        seen.append((list(argv), dict(kwargs["env"])))
        return FakeProcess()

    def fake_run(argv, **kwargs):
        seen.append((list(argv), dict(kwargs["env"])))
        receipt_path = Path(argv[argv.index("--out") + 1])
        receipt_path.write_text(json.dumps({
            **module.request_plan("freeze-sha"),
            "mode": "EXECUTED",
            "status": "PASS",
            "actual_calls": {"decoder": 3, "provider": 6},
        }) + "\n")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module, "Decoder", FakeDecoder)
    monkeypatch.setattr(module, "_product_diff", lambda _sha: [])
    monkeypatch.setattr(module, "_certificate", fake_certificate)
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_wait_ready", lambda _base, _process: 0.25)
    monkeypatch.setattr(module, "_stop_stack", lambda _process: None)

    args = SimpleNamespace(
        allow_decoder=True,
        allow_provider=True,
        decoder_upstream_port=18400,
        budget=3,
        out=output,
        model=model,
        manifest=manifest,
        frozen_sha="freeze-sha",
        port=17836,
        proxy_port=19136,
    )
    assert module.execute(args, module.request_plan(args.frozen_sha)) == 0
    assert seen[0][1].get("OPENROUTER_API_KEY") is None
    assert seen[1][1]["OPENROUTER_API_KEY"] == sentinel
    assert all(sentinel not in json.dumps(argv) for argv, _env in seen)
    assert all(sentinel.encode() not in path.read_bytes() for path in output.rglob("*") if path.is_file())
