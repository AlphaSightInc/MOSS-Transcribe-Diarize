"""Acceptance for the tracked live-service deployment bundle.

The deployment runs *two* web services from one adapter: the plaintext batch service on the
contract port 7860, and a TLS live service on 7861 that only exists when a host loads the
live profile. `--live` hands the certificate to uvicorn, so TLS covers the whole listener —
the two services therefore cannot be one process, and the property that matters most here is
that adding the second one leaves the first byte-for-byte alone.

Covered:
  * `ops/start-web.sh` produces the recorded batch argv when the live profile is absent, and
    the full live argv from `ops/moss-live.env.example` verbatim.
  * every live variable is required, and the port/runs-dir relations that keep the two
    services apart are refused rather than deployed.
  * `ops/systemd/moss-live-web.service` is a second unit over the same adapter, fail-closed on
    a missing profile, and every unit agrees on one deployment root.
  * `ops/install-services.sh` installs the tracked units with dry-run/rollback/unchanged
    discipline and never enables the live unit implicitly.
  * `ops/configure-windows-network.ps1` forwards the batch port unconditionally and the live
    port only under `-IncludeLive`.

Everything runs against scratch paths. No unit is installed outside `tmp_path`, no service is
started, and `systemctl`/`getent` are stubbed on PATH — the real ones are Linux-side and this
suite runs on the orchestrator.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "ops"
UNITS = OPS / "systemd"
TIMEOUT = 60.0

# The deployment root the tracked units are written for. Not derived from the checkout: the
# units carry absolute paths because systemd resolves nothing, so this is the value they must
# all agree on.
DEPLOYMENT_ROOT = "/mnt/d/Coding/MOSS-Transcribe-Diarize"

# The batch invocation, recorded from `ops/start-web.sh` before the live service existed. This
# list is the contract the PRD's "batch service unharmed" clause rests on: the adapter must
# still produce exactly this argv when no live profile is loaded.
BATCH_ARGV = [
    "--backend", "vllm",
    "--model", "{state}/model",
    "--vllm-base-url", "http://127.0.0.1:8000/v1",
    "--vllm-model", "OpenMOSS-Team/MOSS-Transcribe-Diarize",
    "--vllm-timeout", "1800",
    "--runs-dir", f"{DEPLOYMENT_ROOT}/runs",
    "--host", "0.0.0.0",
    "--port", "7860",
    "--max-len", "16384",
    "--max-new-tokens", "12000",
]

LIVE_FLAGS = (
    "--live",
    "--live-provider-manifest",
    "--live-auth-state",
    "--live-tls-certfile",
    "--live-tls-keyfile",
    "--live-helper-lease-seconds",
)


def read_env_file(path: Path) -> dict[str, str]:
    """The subset of EnvironmentFile syntax these profiles use: `KEY=value`, `#` comments."""
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip()
    return values


BATCH_ENV = read_env_file(OPS / "moss.env")
LIVE_ENV_EXAMPLE = read_env_file(OPS / "moss-live.env.example")


@pytest.fixture()
def home(tmp_path: Path) -> Path:
    """A scratch Linux home, published through a `getent` stub the adapter can read."""
    scratch_home = tmp_path / "home" / "operator"
    (scratch_home / ".local" / "share" / "moss-transcribe-diarize" / "venv" / "bin").mkdir(
        parents=True
    )
    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    getent = stub_dir / "getent"
    getent.write_text(
        "#!/bin/sh\n"
        f"printf 'operator:x:1000:1000::{scratch_home}:/bin/bash\\n'\n"
    )
    getent.chmod(0o755)
    return scratch_home


def run_adapter(home: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run `ops/start-web.sh` with the venv entrypoint replaced by an argv recorder."""
    entrypoint = home / ".local/share/moss-transcribe-diarize/venv/bin/mtd-subtitle-web"
    entrypoint.write_text('#!/bin/sh\nfor arg in "$@"; do printf \'%s\\n\' "$arg"; done\n')
    entrypoint.chmod(0o755)
    stub_dir = home.parents[1] / "stub-bin"
    merged = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("MOSS_")
    }
    merged["PATH"] = f"{stub_dir}:{os.environ['PATH']}"
    merged.update(env)
    return subprocess.run(
        ["/bin/bash", str(OPS / "start-web.sh")],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env=merged,
    )


def argv_of(completed: subprocess.CompletedProcess[str]) -> list[str]:
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.splitlines()


def expected_batch_argv(home: Path) -> list[str]:
    state = home / ".local/share/moss-transcribe-diarize"
    return [item.format(state=state) for item in BATCH_ARGV]


def test_batch_profile_reproduces_the_recorded_plaintext_invocation(home: Path) -> None:
    """The committed batch environment still yields the pre-live argv, exactly."""
    result = run_adapter(home, BATCH_ENV)
    assert argv_of(result) == expected_batch_argv(home)
    assert not [arg for arg in argv_of(result) if arg.startswith("--live")]


def test_live_profile_example_yields_the_complete_tls_invocation(home: Path) -> None:
    """The tracked template, used verbatim, is a runnable live profile."""
    result = run_adapter(home, LIVE_ENV_EXAMPLE)
    argv = argv_of(result)

    batch = expected_batch_argv(home)
    port = argv.index("--port")
    runs = argv.index("--runs-dir")
    assert argv[port + 1] == "7861"
    assert argv[runs + 1] == LIVE_ENV_EXAMPLE["MOSS_RUNS_DIR"]
    assert argv[runs + 1] != batch[batch.index("--runs-dir") + 1]

    # Everything the batch service sends is still sent, with only the two overrides differing.
    rewritten = list(argv[: len(batch)])
    rewritten[port + 1] = "7860"
    rewritten[runs + 1] = batch[batch.index("--runs-dir") + 1]
    assert rewritten == batch

    assert argv[len(batch):] == [
        "--live",
        "--live-provider-manifest", LIVE_ENV_EXAMPLE["MOSS_LIVE_PROVIDER_MANIFEST"],
        "--live-auth-state", LIVE_ENV_EXAMPLE["MOSS_LIVE_AUTH_STATE"],
        "--live-tls-certfile", LIVE_ENV_EXAMPLE["MOSS_LIVE_TLS_CERTFILE"],
        "--live-tls-keyfile", LIVE_ENV_EXAMPLE["MOSS_LIVE_TLS_KEYFILE"],
        "--live-helper-lease-seconds", LIVE_ENV_EXAMPLE["MOSS_LIVE_HELPER_LEASE_SECONDS"],
    ]


def test_every_live_profile_variable_is_required(home: Path) -> None:
    """Dropping any one live-profile key refuses the start and names the missing key."""
    required = [key for key in LIVE_ENV_EXAMPLE if key != "MOSS_LIVE_ENABLED"]
    assert set(required) == {
        "MOSS_WEB_PORT",
        "MOSS_RUNS_DIR",
        "MOSS_LIVE_PROVIDER_MANIFEST",
        "MOSS_LIVE_AUTH_STATE",
        "MOSS_LIVE_TLS_CERTFILE",
        "MOSS_LIVE_TLS_KEYFILE",
        "MOSS_LIVE_HELPER_LEASE_SECONDS",
    }
    for key in required:
        partial = {name: value for name, value in LIVE_ENV_EXAMPLE.items() if name != key}
        result = run_adapter(home, partial)
        assert result.returncode != 0, f"{key} was not required"
        assert key in result.stderr
        assert result.stdout == ""


def test_disabled_live_mode_generates_no_live_flag_whatever_else_is_set(home: Path) -> None:
    """`MOSS_LIVE_ENABLED=0` is the whole switch: no live path can leak into the argv."""
    env = dict(LIVE_ENV_EXAMPLE)
    env["MOSS_LIVE_ENABLED"] = "0"
    argv = argv_of(run_adapter(home, env))
    assert not [arg for arg in argv if arg.startswith("--live")]
    for value in (
        LIVE_ENV_EXAMPLE["MOSS_LIVE_TLS_CERTFILE"],
        LIVE_ENV_EXAMPLE["MOSS_LIVE_TLS_KEYFILE"],
        LIVE_ENV_EXAMPLE["MOSS_LIVE_AUTH_STATE"],
        LIVE_ENV_EXAMPLE["MOSS_LIVE_PROVIDER_MANIFEST"],
    ):
        assert value not in argv

    missing = dict(LIVE_ENV_EXAMPLE)
    del missing["MOSS_LIVE_ENABLED"]
    assert not [arg for arg in argv_of(run_adapter(home, missing)) if arg.startswith("--live")]


def test_live_mode_refuses_to_take_over_the_plaintext_batch_port(home: Path) -> None:
    """TLS covers the whole listener, so 7860 under `--live` would remove plaintext batch."""
    env = dict(LIVE_ENV_EXAMPLE)
    env["MOSS_WEB_PORT"] = "7860"
    result = run_adapter(home, env)
    assert result.returncode != 0
    assert "7860" in result.stderr
    assert result.stdout == ""


def test_live_mode_refuses_to_share_the_batch_runs_directory(home: Path) -> None:
    env = dict(LIVE_ENV_EXAMPLE)
    env["MOSS_RUNS_DIR"] = f"{DEPLOYMENT_ROOT}/runs"
    result = run_adapter(home, env)
    assert result.returncode != 0
    assert "runs" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "port",
    ["", "0", "65536", "99999999999999999999", "78 61", "7861a", "-1", "0x1ec5"],
)
def test_malformed_ports_are_refused_before_the_service_starts(home: Path, port: str) -> None:
    env = dict(BATCH_ENV)
    env["MOSS_WEB_PORT"] = port
    result = run_adapter(home, env)
    assert result.returncode != 0, f"accepted port {port!r}"
    assert "MOSS_WEB_PORT" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize("enabled", ["2", "true", "yes", "-1"])
def test_live_enablement_stays_a_two_value_switch(home: Path, enabled: str) -> None:
    env = dict(BATCH_ENV)
    env["MOSS_LIVE_ENABLED"] = enabled
    result = run_adapter(home, env)
    assert result.returncode != 0
    assert "MOSS_LIVE_ENABLED must be 0 or 1" in result.stderr


def test_live_profile_sets_only_variables_the_adapter_reads() -> None:
    """A typo in the template would otherwise be a silently ignored line."""
    adapter = (OPS / "start-web.sh").read_text()
    for key in LIVE_ENV_EXAMPLE:
        assert re.search(rf"\b{key}\b", adapter), f"{key} is set but never read"
    for key in BATCH_ENV:
        assert re.search(rf"\b{key}\b", adapter) or key.startswith("MOSS_GPU") or key.startswith(
            "MOSS_MAX_NUM"
        ), f"{key} is set but never read"


def test_live_profile_example_is_a_template_not_a_host_file() -> None:
    """Host paths belong to the host; the tracked file must not pretend to know them."""
    text = (OPS / "moss-live.env.example").read_text()
    assert "REPLACE_WITH_" in text
    for key in (
        "MOSS_LIVE_PROVIDER_MANIFEST",
        "MOSS_LIVE_AUTH_STATE",
        "MOSS_LIVE_TLS_CERTFILE",
        "MOSS_LIVE_TLS_KEYFILE",
    ):
        assert LIVE_ENV_EXAMPLE[key].startswith("REPLACE_WITH_")
    # The filled-in file is host-local and must never be committable.
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "ops/moss-live.env"],
        cwd=str(ROOT),
        timeout=TIMEOUT,
    )
    assert ignored.returncode == 0, "ops/moss-live.env is not gitignored"


def parse_unit(path: Path) -> dict[str, list[str]]:
    parsed: dict[str, list[str]] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("["):
            continue
        key, _, value = stripped.partition("=")
        parsed.setdefault(key, []).append(value)
    return parsed


def test_the_live_unit_is_a_second_service_over_the_same_adapter() -> None:
    batch = parse_unit(UNITS / "moss-web.service")
    live = parse_unit(UNITS / "moss-live-web.service")

    # One adapter: the two services differ only by the profile they load.
    assert live["ExecStart"] == batch["ExecStart"]

    # Shared tuning first, live profile second — systemd lets the later file win.
    assert live["EnvironmentFile"] == [
        f"-{DEPLOYMENT_ROOT}/ops/moss.env",
        f"{DEPLOYMENT_ROOT}/ops/moss-live.env",
    ]
    # Fail-closed: a missing profile must fail the unit, not start a second batch server.
    assert not live["EnvironmentFile"][1].startswith("-")
    # ...and the batch unit stays optional-profile and live-blind.
    assert batch["EnvironmentFile"] == [f"-{DEPLOYMENT_ROOT}/ops/moss.env"]
    assert "moss-live" not in (UNITS / "moss-web.service").read_text()

    assert "moss-vllm.service" in live["After"][0]
    assert "moss-vllm.service" in live["Wants"][0]


def test_every_tracked_unit_agrees_on_one_deployment_root() -> None:
    for unit in sorted(UNITS.glob("*.service")):
        for path in re.findall(r"(/[\w./-]+)", unit.read_text()):
            if path.startswith("/bin/") or path.startswith("/usr/"):
                continue
            assert path.startswith(DEPLOYMENT_ROOT), f"{unit.name} escapes the root: {path}"


@pytest.fixture()
def installer(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A scratch checkout of `ops/` plus stubbed `systemctl`/`getent`, so nothing real moves."""
    scratch_root = tmp_path / "checkout"
    shutil.copytree(OPS, scratch_root / "ops")
    scratch_home = tmp_path / "home" / "operator"
    scratch_home.mkdir(parents=True)

    stub_dir = tmp_path / "stub-bin"
    stub_dir.mkdir()
    calls = tmp_path / "systemctl-calls.txt"
    unit_state = tmp_path / "unit-state"
    unit_state.mkdir()
    # A stub that remembers: `enable`/`start` leave a marker and `is-enabled`/`is-active`
    # answer from it, so a second run really does observe the state the first run created.
    systemctl = stub_dir / "systemctl"
    systemctl.write_text(
        "#!/bin/sh\n"
        f'printf \'%s\\n\' "$*" >> "{calls}"\n'
        f'state="{unit_state}"\n'
        'verb="$2"\n'
        'shift 2\n'
        'case "$verb" in\n'
        '  is-enabled) [ -f "$state/enabled-$1" ] ;;\n'
        '  is-active) [ -f "$state/active-$1" ] ;;\n'
        '  enable) for unit in "$@"; do : > "$state/enabled-$unit"; done ;;\n'
        '  start) for unit in "$@"; do : > "$state/active-$unit"; done ;;\n'
        '  disable)\n'
        '    for unit in "$@"; do\n'
        '      case "$unit" in -*) continue ;; esac\n'
        '      rm -f "$state/enabled-$unit" "$state/active-$unit"\n'
        '    done ;;\n'
        '  *) : ;;\n'
        "esac\n"
    )
    systemctl.chmod(0o755)
    getent = stub_dir / "getent"
    getent.write_text(
        f"#!/bin/sh\nprintf 'operator:x:1000:1000::{scratch_home}:/bin/bash\\n'\n"
    )
    getent.chmod(0o755)
    return scratch_root, scratch_home, calls


def run_installer(
    installer: tuple[Path, Path, Path], *args: str
) -> subprocess.CompletedProcess[str]:
    scratch_root, _, calls = installer
    stub_dir = calls.parent / "stub-bin"
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}:{os.environ['PATH']}"
    return subprocess.run(
        ["/bin/bash", str(scratch_root / "ops" / "install-services.sh"), *args],
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
        env=env,
    )


def lines(completed: subprocess.CompletedProcess[str], prefix: str) -> list[str]:
    return [
        line[len(prefix):].strip()
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]


def systemctl_calls(installer: tuple[Path, Path, Path]) -> list[str]:
    calls = installer[2]
    return calls.read_text().splitlines() if calls.exists() else []


def test_the_installer_leaves_the_live_unit_alone_by_default(
    installer: tuple[Path, Path, Path]
) -> None:
    scratch_root, scratch_home, _ = installer
    (scratch_root / "ops" / "moss-live.env").write_text("MOSS_LIVE_ENABLED=1\n")

    result = run_installer(installer)
    assert result.returncode == 0, result.stderr

    unit_dir = scratch_home / ".config/systemd/user"
    assert sorted(p.name for p in unit_dir.iterdir()) == [
        "moss-vllm.service",
        "moss-web.service",
    ]
    # Even with a profile sitting there, nothing enables or starts the live service.
    assert not [call for call in systemctl_calls(installer) if "moss-live-web" in call]
    for unit in ("moss-vllm.service", "moss-web.service"):
        assert (unit_dir / unit).read_bytes() == (UNITS / unit).read_bytes()
        assert stat.S_IMODE((unit_dir / unit).stat().st_mode) == 0o644


def test_the_installer_refuses_a_live_unit_without_its_profile(
    installer: tuple[Path, Path, Path]
) -> None:
    scratch_root, scratch_home, _ = installer
    result = run_installer(installer, "--with-live")
    assert result.returncode != 0
    assert "moss-live.env" in result.stderr
    # Refused before the first mutation: no unit directory, no systemctl call at all.
    assert not (scratch_home / ".config/systemd/user").exists()
    assert systemctl_calls(installer) == []
    assert lines(result, "change:") == []


def test_installing_the_live_unit_is_explicit_and_reversible(
    installer: tuple[Path, Path, Path]
) -> None:
    scratch_root, scratch_home, _ = installer
    (scratch_root / "ops" / "moss-live.env").write_text("MOSS_LIVE_ENABLED=1\n")

    result = run_installer(installer, "--with-live")
    assert result.returncode == 0, result.stderr
    unit_dir = scratch_home / ".config/systemd/user"
    assert (unit_dir / "moss-live-web.service").read_bytes() == (
        UNITS / "moss-live-web.service"
    ).read_bytes()

    calls = systemctl_calls(installer)
    assert "--user enable moss-live-web.service" in calls
    assert "--user start moss-live-web.service" in calls
    # The batch units are enabled and started in the same call they always were.
    assert "--user enable moss-vllm.service moss-web.service" in calls
    assert "--user start moss-vllm.service moss-web.service" in calls

    rollbacks = lines(result, "rollback:")
    assert f"systemctl --user disable --now moss-live-web.service" in rollbacks
    assert any(
        line.startswith(f"rm -f '{unit_dir}/moss-live-web.service'") for line in rollbacks
    )

    # A re-run is a no-op on every unit file, inode included, and on the activation too.
    inode = (unit_dir / "moss-live-web.service").stat().st_ino
    again = run_installer(installer, "--with-live")
    assert again.returncode == 0, again.stderr
    assert sorted(lines(again, "unchanged:")) == [
        "moss-live-web.service already matches the tracked unit",
        "moss-live-web.service is already enabled and running",
        "moss-vllm.service already matches the tracked unit",
        "moss-web.service already matches the tracked unit",
    ]
    assert lines(again, "change:") == []
    assert "restart_required=none" in again.stdout
    assert (unit_dir / "moss-live-web.service").stat().st_ino == inode


def test_a_replaced_unit_is_backed_up_and_the_printed_rollback_restores_it(
    installer: tuple[Path, Path, Path]
) -> None:
    scratch_root, scratch_home, _ = installer
    unit_dir = scratch_home / ".config/systemd/user"
    unit_dir.mkdir(parents=True)
    previous = b"[Service]\nExecStart=/bin/true\n"
    (unit_dir / "moss-web.service").write_bytes(previous)

    result = run_installer(installer)
    assert result.returncode == 0, result.stderr
    body = result.stdout.splitlines()
    first_change = next(i for i, line in enumerate(body) if line.startswith("change:"))
    last_rollback = max(i for i, line in enumerate(body) if line.startswith("rollback:"))
    assert last_rollback < first_change, "rollback must be printed before the first mutation"

    restore = next(line for line in lines(result, "rollback:") if "moss-web.service" in line)
    assert (unit_dir / "moss-web.service").read_bytes() == (
        UNITS / "moss-web.service"
    ).read_bytes()

    stub_dir = installer[2].parent / "stub-bin"
    env = dict(os.environ)
    env["PATH"] = f"{stub_dir}:{os.environ['PATH']}"
    undo = subprocess.run(
        ["/bin/bash", "-c", restore], capture_output=True, text=True, timeout=TIMEOUT, env=env
    )
    assert undo.returncode == 0, undo.stderr
    assert (unit_dir / "moss-web.service").read_bytes() == previous


def test_the_installer_dry_run_plans_everything_and_mutates_nothing(
    installer: tuple[Path, Path, Path]
) -> None:
    scratch_root, scratch_home, _ = installer
    (scratch_root / "ops" / "moss-live.env").write_text("MOSS_LIVE_ENABLED=1\n")

    result = run_installer(installer, "--with-live", "--dry-run")
    assert result.returncode == 0, result.stderr
    plans = lines(result, "plan:")
    assert any("moss-live-web.service" in line for line in plans)
    assert "systemctl --user daemon-reload" in plans
    assert lines(result, "rollback:")
    assert lines(result, "change:") == []
    assert not (scratch_home / ".config/systemd/user").exists()
    # Reading unit state is allowed; changing it is not.
    mutating = [
        call
        for call in systemctl_calls(installer)
        if call.split()[1] in {"daemon-reload", "enable", "start", "restart", "disable"}
    ]
    assert mutating == []


def test_every_operator_run_ops_tool_is_documented() -> None:
    """A tracked deployment tool nobody documents is one no operator will run."""
    doc = (ROOT / "LOCAL_DEPLOYMENT.md").read_text()
    unit_text = "\n".join(unit.read_text() for unit in UNITS.glob("*.service"))
    undocumented = []
    for tool in sorted(OPS.iterdir()):
        if tool.is_dir() or tool.suffix not in {".sh", ".ps1", ".py"}:
            continue
        if tool.name.endswith("-lib.sh"):
            continue  # sourced, never invoked
        if tool.name in unit_text:
            continue  # started by systemd, not by an operator
        if tool.name not in doc:
            undocumented.append(tool.name)
    assert undocumented == []


def test_the_deployment_document_states_the_two_service_layout() -> None:
    doc = (ROOT / "LOCAL_DEPLOYMENT.md").read_text()
    for required in (
        "moss-live-web.service",
        "moss-live.env.example",
        "--with-live",
        "-IncludeLive",
        "7861",
    ):
        assert required in doc, f"LOCAL_DEPLOYMENT.md does not mention {required}"
    # The one rule that keeps the pairing secret a secret.
    assert "never be redirected to a file" in doc
    # Rollback for every live mutation this bundle can make.
    assert "systemctl --user disable --now moss-live-web.service" in doc


def powershell_guarded_lines(text: str, guard: str) -> set[int]:
    """Line numbers inside `if (<guard>) { ... }` blocks, by brace matching."""
    guarded: set[int] = set()
    lines_ = text.splitlines()
    for index, line in enumerate(lines_):
        if not line.strip().startswith(f"if ({guard})"):
            continue
        depth = 0
        for offset in range(index, len(lines_)):
            depth += lines_[offset].count("{") - lines_[offset].count("}")
            guarded.add(offset)
            if depth == 0 and offset > index:
                break
    return guarded


def test_windows_forwarding_keeps_the_batch_port_unconditional_and_gates_the_live_port() -> None:
    text = (OPS / "configure-windows-network.ps1").read_text()
    guarded = powershell_guarded_lines(text, "$IncludeLive")
    assert guarded, "no -IncludeLive guard found"

    assert "[switch]$RefreshOnly" in text
    assert "[switch]$IncludeLive" in text

    for index, line in enumerate(text.splitlines()):
        mentions_live = "7861" in line or "moss-live-web.service" in line
        if mentions_live:
            assert index in guarded, f"live forwarding is unconditional: {line.strip()}"
        if "7860" in line or "MOSS-Transcribe-Diarize-Web'" in line:
            assert index not in guarded, f"batch forwarding became conditional: {line.strip()}"

    # The batch row is what it always was, and the live row is a distinct firewall rule.
    assert "Port        = 7860" in text
    assert "RuleName    = 'MOSS-Transcribe-Diarize-Web'" in text
    assert "Port        = 7861" in text
    assert "RuleName    = 'MOSS-Transcribe-Diarize-Live'" in text

    # Both ports go through the same loop: no netsh line may name a port literal.
    for line in text.splitlines():
        if "netsh.exe" in line:
            assert not re.search(r"listenport=\d", line)
            assert not re.search(r"connectport=\d", line)

    # A refresh after sign-in must forward the same ports as the run that registered it.
    assert "$argumentList += ' -IncludeLive'" in text
    assert text.index("$argumentList += ' -IncludeLive'") > text.index("-RefreshOnly\"")
