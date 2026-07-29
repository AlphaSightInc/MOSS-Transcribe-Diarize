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
  * `ops/configure-windows-network.ps1` uses portproxy under WSL NAT, removes stale proxies under
    mirrored networking, and includes the live port only under `-IncludeLive`.

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


# --- the retention declaration (ADR-0003) --------------------------------------------------
#
# The tape recorder is on the live path and inert: it holds `None` unless a deployment declares
# a root. These nodes cover the declaration itself, end to end -- the tracked template says how,
# the adapter turns the profile into flags, and the CLI turns the flags into a store or refuses
# them. The property that matters most is the one the certification runs rest on: the template
# used verbatim still produces a service that retains nothing.

RETENTION_KEYS = (
    "MOSS_LIVE_RETENTION_ROOT",
    "MOSS_LIVE_RETENTION_MAX_BYTES",
    "MOSS_LIVE_RETENTION_TTL_SECONDS",
)


def commented_keys(path: Path) -> set[str]:
    """Keys the template documents as commented-out lines, which `read_env_file` skips."""
    found = set()
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        key, sep, _ = stripped.lstrip("#").strip().partition("=")
        if sep and re.fullmatch(r"[A-Z0-9_]+", key.strip()):
            found.add(key.strip())
    return found


def test_the_tracked_live_profile_retains_nothing(home: Path) -> None:
    """Off by default is a property of the template, not of an operator's restraint."""
    argv = argv_of(run_adapter(home, LIVE_ENV_EXAMPLE))
    assert not [arg for arg in argv if arg.startswith("--live-retention")]
    assert not [key for key in LIVE_ENV_EXAMPLE if key.startswith("MOSS_LIVE_RETENTION")]
    # Documented all the same: an opt-in nobody can find is an opt-in nobody takes.
    assert set(RETENTION_KEYS) <= commented_keys(OPS / "moss-live.env.example")


def test_the_commented_retention_keys_are_read_by_the_adapter() -> None:
    """`test_live_profile_sets_only_variables_the_adapter_reads` cannot see a comment."""
    adapter = (OPS / "start-web.sh").read_text()
    for key in commented_keys(OPS / "moss-live.env.example"):
        assert re.search(rf"\b{key}\b", adapter), f"{key} is documented but never read"


def test_a_declared_retention_root_reaches_the_service_as_flags(home: Path) -> None:
    env = dict(LIVE_ENV_EXAMPLE)
    env["MOSS_LIVE_RETENTION_ROOT"] = "/srv/moss-live-tapes"
    env["MOSS_LIVE_RETENTION_MAX_BYTES"] = "2147483648"
    argv = argv_of(run_adapter(home, env))
    assert argv[-4:] == [
        "--live-retention-root", "/srv/moss-live-tapes",
        "--live-retention-max-bytes", "2147483648",
    ]
    # An unstated TTL is not a flag: zero is the tool's choice and it belongs in one place.
    assert "--live-retention-ttl-seconds" not in argv

    env["MOSS_LIVE_RETENTION_TTL_SECONDS"] = "3600"
    assert argv_of(run_adapter(home, env))[-2:] == ["--live-retention-ttl-seconds", "3600"]


def test_a_declared_retention_root_requires_its_cap(home: Path) -> None:
    env = dict(LIVE_ENV_EXAMPLE)
    env["MOSS_LIVE_RETENTION_ROOT"] = "/srv/moss-live-tapes"
    result = run_adapter(home, env)
    assert result.returncode != 0
    assert "MOSS_LIVE_RETENTION_MAX_BYTES" in result.stderr
    assert result.stdout == ""


@pytest.mark.parametrize(
    "stated",
    [
        {"MOSS_LIVE_RETENTION_MAX_BYTES": "2147483648"},
        {"MOSS_LIVE_RETENTION_TTL_SECONDS": "3600"},
        {"MOSS_LIVE_RETENTION_MAX_BYTES": "1", "MOSS_LIVE_RETENTION_TTL_SECONDS": "3600"},
    ],
)
def test_retention_values_without_a_root_are_refused_not_ignored(
    home: Path, stated: dict[str, str]
) -> None:
    """An operator who states a cap believes audio is being kept. Silence would lie to them."""
    env = dict(LIVE_ENV_EXAMPLE)
    env.update(stated)
    result = run_adapter(home, env)
    assert result.returncode != 0
    assert "MOSS_LIVE_RETENTION_ROOT" in result.stderr
    assert result.stdout == ""


def test_an_empty_retention_root_is_a_typo_not_a_request_for_the_default(home: Path) -> None:
    env = dict(LIVE_ENV_EXAMPLE)
    env["MOSS_LIVE_RETENTION_ROOT"] = ""
    env["MOSS_LIVE_RETENTION_MAX_BYTES"] = "2147483648"
    result = run_adapter(home, env)
    assert result.returncode != 0
    assert "MOSS_LIVE_RETENTION_ROOT" in result.stderr
    assert result.stdout == ""


def cli_args(monkeypatch: pytest.MonkeyPatch, *argv: str):
    """The real flags through the real parser -- so a renamed flag fails here, not on a host."""
    from moss_transcribe_diarize.app import web_cli

    monkeypatch.setattr("sys.argv", ["mtd-subtitle-web", *argv])
    return web_cli, web_cli.parse_args()


def test_the_cli_builds_no_store_when_no_root_is_declared(monkeypatch) -> None:
    web_cli, args = cli_args(monkeypatch, "--live")
    assert web_cli._live_tape_store(args) is None


def test_the_cli_declares_the_store_the_deployment_stated(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "tapes"
    web_cli, args = cli_args(
        monkeypatch,
        "--live",
        "--runs-dir", str(tmp_path / "absent-runs"),
        "--live-retention-root", str(root),
        "--live-retention-max-bytes", "4096",
    )
    store = web_cli._live_tape_store(args)
    assert store is not None
    assert store.root == root.resolve()
    assert store.max_bytes_per_session == 4096
    # ADR-0003 D3: unstated is zero, and zero is the only value a tool may choose.
    assert store.retention_ttl_seconds == 0.0
    assert root.stat().st_mode & 0o777 == 0o700

    web_cli, args = cli_args(
        monkeypatch,
        "--live",
        "--runs-dir", str(tmp_path / "absent-runs"),
        "--live-retention-root", str(root),
        "--live-retention-max-bytes", "4096",
        "--live-retention-ttl-seconds", "3600",
    )
    assert web_cli._live_tape_store(args).retention_ttl_seconds == 3600.0


@pytest.mark.parametrize(
    "argv, named",
    [
        (("--live-retention-max-bytes", "4096"), "--live-retention-root"),
        (("--live-retention-ttl-seconds", "3600"), "--live-retention-root"),
    ],
)
def test_the_cli_refuses_retention_values_without_a_root(
    monkeypatch, argv: tuple[str, ...], named: str
) -> None:
    web_cli, parsed = cli_args(monkeypatch, "--live", *argv)
    with pytest.raises(SystemExit) as refusal:
        web_cli._live_tape_store(parsed)
    assert named in str(refusal.value)


def test_the_cli_refuses_a_root_without_a_cap_and_a_root_without_live(
    monkeypatch, tmp_path: Path
) -> None:
    web_cli, args = cli_args(monkeypatch, "--live", "--live-retention-root", str(tmp_path))
    with pytest.raises(SystemExit) as refusal:
        web_cli._live_tape_store(args)
    assert "--live-retention-max-bytes" in str(refusal.value)

    web_cli, args = cli_args(
        monkeypatch,
        "--live-retention-root", str(tmp_path),
        "--live-retention-max-bytes", "4096",
    )
    with pytest.raises(SystemExit) as refusal:
        web_cli._live_tape_store(args)
    assert "--live" in str(refusal.value)


def test_the_declared_store_reaches_the_application(monkeypatch, tmp_path: Path) -> None:
    """The last link: a store nobody hands to `create_app` is a declaration that does nothing.

    The two live-startup helpers are stubbed because they want a manifest and a certificate;
    `_live_tape_store` and the `create_app` call are the seam this node exists for.
    """
    from moss_transcribe_diarize.app import web_cli

    recorded: dict[str, object] = {}
    monkeypatch.setattr(web_cli, "_live_runtime_factory", lambda args: None)
    monkeypatch.setattr(
        web_cli,
        "_live_startup_config",
        lambda args: dict.fromkeys(
            (
                "live_auth_state_path",
                "live_server_cert_sha256",
                "live_helper_lease_seconds",
                "ssl_certfile",
                "ssl_keyfile",
            )
        ),
    )
    monkeypatch.setattr(web_cli, "create_app", lambda **kwargs: recorded.update(kwargs))
    monkeypatch.setitem(
        __import__("sys").modules, "uvicorn", type("_U", (), {"run": staticmethod(lambda *a, **k: None)})
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "mtd-subtitle-web",
            "--live",
            "--runs-dir", str(tmp_path / "absent-runs"),
            "--live-retention-root", str(tmp_path / "tapes"),
            "--live-retention-max-bytes", "4096",
        ],
    )
    web_cli.main()
    store = recorded["live_tape_store"]
    assert store is not None and store.root == (tmp_path / "tapes").resolve()

    monkeypatch.setattr("sys.argv", ["mtd-subtitle-web", "--live"])
    recorded.clear()
    web_cli.main()
    assert recorded["live_tape_store"] is None


def test_the_cli_hands_the_runs_directory_to_the_admission_check(
    monkeypatch, tmp_path: Path
) -> None:
    """D4(3) is unreachable unless the wiring tells the store what the runs tree is."""
    from moss_transcribe_diarize.app.live_tape import LiveTapeRootError

    runs = tmp_path / "live-runs"
    runs.mkdir()
    web_cli, args = cli_args(
        monkeypatch,
        "--live",
        "--runs-dir", str(runs),
        "--live-retention-root", str(tmp_path / "tapes"),
        "--live-retention-max-bytes", "4096",
    )
    with pytest.raises(LiveTapeRootError) as refusal:
        web_cli._live_tape_store(args)
    assert "filesystem" in str(refusal.value)


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


def test_windows_forwarding_does_not_reserve_mirrored_wsl_ports_with_portproxy() -> None:
    text = (OPS / "configure-windows-network.ps1").read_text()

    assert "wslinfo --networking-mode" in text
    assert "$usesPortProxy = $networkingMode -ne 'mirrored'" in text
    assert "ip -4 -o addr show dev eth0 scope global" in text
    delete = text.index("portproxy delete")
    guarded_add = text.index("if ($usesPortProxy)", delete)
    add = text.index("portproxy add", guarded_add)
    assert delete < guarded_add < add
    assert "Mirrored networking ready" in text
