"""Acceptance for the tracked Mac packaging and install tools.

These tests exercise the real scripts, but only ever against scratch paths: no certificate,
no keychain, no keychain search list, no `/Applications` entry and no `~/.local/bin` entry is
touched. Anything that would need a real signing identity is proven by the tools' refusals and
by their dry-run plans instead — a build signed by the project identity is E1/E2 work on the
target Mac, and the identity itself is created there, once, by a human-initiated run.

Bundles here are ad-hoc signed. That is deliberate: an ad-hoc designated requirement is
cdhash-based, so identical inputs give an identical DR, which is exactly what makes
"a rebuild reproduces one bundle" testable without a certificate.
"""

from __future__ import annotations

import json
import os
import platform
import plistlib
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "macos" / "scripts"
PACKAGE_ROOT = ROOT / "macos" / "MOSSCapture"
BUNDLE_IDENTIFIER = "com.alphasight.moss.capture"
TIMEOUT = 180.0

pytestmark = pytest.mark.skipif(
    platform.system() != "Darwin",
    reason="The Mac packaging tools are Darwin-only (codesign, security, ditto, plutil).",
)


def run_tool(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(SCRIPTS / script), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT,
    )


def lines(completed: subprocess.CompletedProcess[str], prefix: str) -> list[str]:
    return [
        line[len(prefix) :].strip()
        for line in completed.stdout.splitlines()
        if line.startswith(prefix)
    ]


def evidence(completed: subprocess.CompletedProcess[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in lines(completed, "evidence:"):
        key, _, value = line.partition("=")
        found[key] = value
    return found


def first_index(completed: subprocess.CompletedProcess[str], prefix: str) -> int:
    for index, line in enumerate(completed.stdout.splitlines()):
        if line.startswith(prefix):
            return index
    return -1


def build_scratch_bundle(output: Path) -> subprocess.CompletedProcess[str]:
    """Build output only — `--no-build` reuses the products the Swift gate already built."""
    completed = run_tool(
        "build-app.sh",
        "--configuration",
        "debug",
        "--no-build",
        "--output",
        str(output),
        "--sign-identity",
        "-",
    )
    assert completed.returncode == 0, (
        f"build-app.sh failed (build both Swift products first):\n{completed.stderr}"
    )
    return completed


def embedded_entitlements(bundle: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["codesign", "-d", "--entitlements", "-", "--xml", str(bundle)],
        capture_output=True,
        timeout=TIMEOUT,
    )
    assert completed.returncode == 0, completed.stderr.decode("utf-8", errors="replace")
    return plistlib.loads(completed.stdout)


def resign_with_new_version(bundle: Path, entitlements: Path, version: str) -> None:
    """A realistic 'next build': same sources, different bundle bytes, still validly signed."""
    subprocess.run(
        ["plutil", "-replace", "CFBundleShortVersionString", "-string", version,
         str(bundle / "Contents" / "Info.plist")],
        check=True,
        capture_output=True,
        timeout=TIMEOUT,
    )
    subprocess.run(
        ["codesign", "--force", "--options", "runtime", "--timestamp=none",
         "--identifier", BUNDLE_IDENTIFIER, "--entitlements", str(entitlements),
         "--sign", "-", str(bundle)],
        check=True,
        capture_output=True,
        timeout=TIMEOUT,
    )


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    output = tmp_path_factory.mktemp("build")
    build_scratch_bundle(output)
    return {
        "output": output,
        "bundle": output / "MOSSCapture.app",
        "cli": output / "mtd-capture",
        "entitlements": output / "MOSSCapture.signing.entitlements",
    }


def test_build_app_signs_without_the_entitlement_the_identity_cannot_satisfy(built):
    bundle = built["bundle"]
    info = plistlib.loads((bundle / "Contents" / "Info.plist").read_bytes())

    assert info["CFBundleIdentifier"] == BUNDLE_IDENTIFIER
    assert info["CFBundleExecutable"] == "MOSSCaptureApp"
    # Without a usage string macOS terminates the process instead of prompting, so the lane
    # could never be granted at all.
    for key in ("NSAudioCaptureUsageDescription", "NSMicrophoneUsageDescription"):
        assert info[key].strip()
    # And without the transport declaration the shipped bundle cannot reach the live server at
    # all: ATS applies to a bundle and not to a bare executable, and it rejects the pinned
    # self-signed leaf after the pinning delegate has already accepted it. Asserted on the
    # composed bundle, not on the tracked source, because this tool is what installs it.
    # Keep it un-siblinged: NSAllowsLocalNetworking or either NSAllowsArbitraryLoadsIn* key
    # makes the OS ignore NSAllowsArbitraryLoads.
    assert info["NSAppTransportSecurity"] == {"NSAllowsArbitraryLoads": True}

    tracked = plistlib.loads((PACKAGE_ROOT / "Resources" / "MOSSCapture.entitlements").read_bytes())
    assert "keychain-access-groups" in tracked, (
        "the tracked entitlements are the input this tool has to sanitize; if the key is gone "
        "the derivation below is no longer proving anything"
    )

    signed = embedded_entitlements(bundle)
    assert signed["com.apple.security.device.audio-input"] is True
    # `$(AppIdentifierPrefix)` is never substituted by SwiftPM and a self-signed identity has
    # no Team ID, so signing this key would assert an identity the certificate cannot satisfy.
    assert "keychain-access-groups" not in signed

    assert subprocess.run(
        ["codesign", "--verify", "--strict", str(bundle)], capture_output=True, timeout=TIMEOUT
    ).returncode == 0
    assert subprocess.run(
        ["codesign", "--verify", "--strict", str(built["cli"])],
        capture_output=True,
        timeout=TIMEOUT,
    ).returncode == 0


def test_build_app_reproduces_one_bundle_across_runs(built, tmp_path):
    """Same sources and identity must give one bundle: DR churn is what resets TCC grants."""
    second = tmp_path / "again"
    second.mkdir()
    reported = evidence(build_scratch_bundle(second))

    first = json.loads((built["output"] / "build-evidence.json").read_text(encoding="utf-8"))
    assert first["schema"] == "moss-capture-build-evidence.v1"
    assert first["bundle_identifier"] == BUNDLE_IDENTIFIER
    assert reported["bundle_digest"] == first["bundle_digest"]
    assert reported["designated_requirement"] == first["bundle_designated_requirement"]

    # And a re-run over an existing output signs nothing again.
    repeat = run_tool(
        "build-app.sh", "--configuration", "debug", "--no-build",
        "--output", str(built["output"]), "--sign-identity", "-",
    )
    assert repeat.returncode == 0
    assert lines(repeat, "unchanged:"), repeat.stdout
    assert not lines(repeat, "change:"), repeat.stdout


def test_build_app_refuses_to_write_into_an_install_location():
    completed = run_tool("build-app.sh", "--output", "/Applications/scratch", "--dry-run")
    assert completed.returncode != 0
    assert "refusing to build into an install location" in completed.stderr


def test_install_app_leaves_an_identical_installed_bundle_untouched(built, tmp_path):
    applications = tmp_path / "Applications"
    bin_dir = tmp_path / "bin"
    args = (
        "--bundle", str(built["bundle"]), "--cli", str(built["cli"]),
        "--applications", str(applications), "--bin-dir", str(bin_dir),
    )

    first = run_tool("install-app.sh", *args)
    assert first.returncode == 0, first.stderr
    installed = applications / "MOSSCapture.app"
    executable = installed / "Contents" / "MacOS" / "MOSSCaptureApp"
    assert installed.is_dir() and (bin_dir / "mtd-capture").is_file()
    assert first_index(first, "rollback:") < first_index(first, "change:"), (
        "the rollback command has to be printed before the mutation it undoes"
    )
    before = executable.stat()

    second = run_tool("install-app.sh", *args)
    assert second.returncode == 0, second.stderr
    assert not lines(second, "change:"), second.stdout
    assert len(lines(second, "unchanged:")) == 2, second.stdout

    after = executable.stat()
    # Same inode and mtime: the bundle was never replaced, so its TCC grants survive.
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_install_app_backs_up_a_replacement_and_its_rollback_restores_it(built, tmp_path):
    applications = tmp_path / "Applications"
    bin_dir = tmp_path / "bin"

    def install(bundle: Path) -> subprocess.CompletedProcess[str]:
        return run_tool(
            "install-app.sh", "--bundle", str(bundle), "--cli", str(built["cli"]),
            "--applications", str(applications), "--bin-dir", str(bin_dir),
        )

    assert install(built["bundle"]).returncode == 0
    installed = applications / "MOSSCapture.app"
    original_version = plistlib.loads(
        (installed / "Contents" / "Info.plist").read_bytes()
    )["CFBundleShortVersionString"]

    successor = tmp_path / "next" / "MOSSCapture.app"
    successor.parent.mkdir()
    shutil.copytree(built["bundle"], successor, symlinks=True)
    resign_with_new_version(successor, built["entitlements"], "9.9.9")

    replaced = install(successor)
    assert replaced.returncode == 0, replaced.stderr
    assert first_index(replaced, "rollback:") < first_index(replaced, "change:")
    reported = evidence(replaced)
    backup = Path(reported["backup_bundle"])
    assert backup.is_dir(), reported
    assert plistlib.loads(
        (installed / "Contents" / "Info.plist").read_bytes()
    )["CFBundleShortVersionString"] == "9.9.9"
    # An ad-hoc DR is cdhash-based, so replacing the bundle really does change it — and the
    # tool has to say so, because that is when the human loses the grants.
    assert any("designated requirement changes" in line for line in lines(replaced, "change:"))

    command = next(
        line for line in lines(replaced, "rollback:") if str(backup) in line
    )
    assert str(tmp_path) in command and command.count(str(tmp_path)) == command.count("'") // 2
    assert subprocess.run(
        ["/bin/bash", "-c", command], capture_output=True, text=True, timeout=TIMEOUT
    ).returncode == 0
    assert not backup.exists()
    assert plistlib.loads(
        (installed / "Contents" / "Info.plist").read_bytes()
    )["CFBundleShortVersionString"] == original_version


def test_install_app_refuses_a_tampered_bundle_and_installs_nothing(built, tmp_path):
    applications = tmp_path / "Applications"
    tampered = tmp_path / "tampered" / "MOSSCapture.app"
    tampered.parent.mkdir()
    shutil.copytree(built["bundle"], tampered, symlinks=True)
    executable = tampered / "Contents" / "MacOS" / "MOSSCaptureApp"
    with executable.open("ab") as handle:
        handle.write(b"\x00")

    completed = run_tool(
        "install-app.sh", "--bundle", str(tampered), "--cli", str(built["cli"]),
        "--applications", str(applications), "--bin-dir", str(tmp_path / "bin"),
    )
    assert completed.returncode != 0
    assert "codesign --verify --strict" in completed.stderr
    assert not applications.exists(), "a refused install must not create the destination"


def test_every_tool_plans_and_records_a_rollback_without_mutating_anything(built, tmp_path):
    scratch = tmp_path / "never-created"
    invocations = (
        ("bootstrap-signing-identity.sh", (
            "--keychain", str(scratch / "moss-signing.keychain-db"),
            "--password-file", str(scratch / "password"),
        )),
        ("build-app.sh", ("--output", str(scratch / "product"))),
        ("install-app.sh", (
            "--bundle", str(built["bundle"]), "--cli", str(built["cli"]),
            "--applications", str(scratch / "Applications"), "--bin-dir", str(scratch / "bin"),
        )),
    )

    for script, args in invocations:
        completed = run_tool(script, "--dry-run", *args)
        assert completed.returncode == 0, f"{script}: {completed.stderr}"
        assert lines(completed, "plan:"), f"{script} printed no plan"
        assert lines(completed, "rollback:"), f"{script} printed no rollback command"
        assert not lines(completed, "change:"), f"{script} mutated something in dry-run"

    assert not scratch.exists(), "a dry run created something on disk"


def test_bootstrap_refuses_the_session_keychain_and_never_gates_on_find_identity(tmp_path):
    home_keychains = Path.home() / "Library" / "Keychains"
    for target in (
        home_keychains / "login.keychain-db",
        Path("/Library/Keychains/System.keychain"),
    ):
        refused = run_tool(
            "bootstrap-signing-identity.sh", "--dry-run", "--keychain", str(target)
        )
        assert refused.returncode != 0, f"{target} was not refused"
        assert "refusing to manage" in refused.stderr

    scratch = tmp_path / "kc" / "moss-signing.keychain-db"
    planned = run_tool(
        "bootstrap-signing-identity.sh", "--dry-run",
        "--keychain", str(scratch), "--password-file", str(tmp_path / "kc" / "password"),
    )
    assert planned.returncode == 0, planned.stderr
    plan = lines(planned, "plan:")
    # D7's caveat: `security find-identity -v -p codesigning` reports 0 valid identities for a
    # self-signed leaf even where codesign succeeds, so acceptance is codesign's exit status.
    assert any("signing a scratch binary with codesign" in line for line in plan), plan
    assert any("never gate on security find-identity" in line for line in plan), plan
    assert any("keychain search list" in line for line in plan), plan
    assert not scratch.parent.exists()
    assert not (home_keychains / "moss-signing.keychain-db").exists(), (
        "the test suite must never create the real signing keychain"
    )


def test_tools_are_executable_and_share_one_library():
    for name in ("bootstrap-signing-identity.sh", "build-app.sh", "install-app.sh"):
        script = SCRIPTS / name
        assert os.access(script, os.X_OK), f"{name} is not executable"
        assert "moss-tool-lib.sh" in script.read_text(encoding="utf-8")
