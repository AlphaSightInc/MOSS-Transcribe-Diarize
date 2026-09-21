#!/usr/bin/env python3
"""Frozen-SHA R4-10 feature-row receipt runner.

Default invocation is deliberately non-dispatching: it runs only rows whose named
controls do not need a decoder or external provider, and marks every unmet
prerequisite INCOMPLETE.  A real campaign must opt into both decoder and provider
use explicitly; this runner never opens a tunnel or starts a shared service.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FROZEN_SHA = "71f23c0c7f353d64593020f8ef93157b86951c10"
EVIDENCE = ROOT / "evidence/round4/features"
PYTHON = sys.executable
CORPUS = ROOT / "evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s"
KEY_FILE = Path.home() / ".config/moss/openrouter.env"
ALLOWED_MUTATION_PREFIXES = ("prototypes/feature-rows/", "evidence/round4/features/")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def product_tree() -> dict[str, object]:
    changed = set(filter(None, git("diff", "--name-only", FROZEN_SHA, "HEAD").splitlines()))
    for line in git("status", "--porcelain=v1", "--untracked-files=all").splitlines():
        changed.add(line[3:])
    product_changes = sorted(path for path in changed if not path.startswith(ALLOWED_MUTATION_PREFIXES))
    return {
        "frozen_sha": FROZEN_SHA,
        "head": git("rev-parse", "HEAD"),
        "product_changes_since_frozen_sha": product_changes,
        "frozen_product_tree": not product_changes,
    }


def command_result(command: list[str], *, env: dict[str, str] | None = None, timeout: int = 1800) -> dict[str, object]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    return {
        "command": command,
        "exit_code": completed.returncode,
        "seconds": round(time.monotonic() - started, 3),
        # Output can include model/provider diagnostics.  The receipt retains only
        # bounded count-derived facts, never raw process output.
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def safe_command(record: dict[str, object]) -> dict[str, object]:
    return {key: record[key] for key in ("command", "exit_code", "seconds")}


def pytest_denominator(output: str) -> dict[str, int | None]:
    match = re.search(r"(\d+) passed(?:, (\d+) skipped)?", output)
    return {"passed": int(match.group(1)) if match else None,
            "skipped": int(match.group(2) or 0) if match else None}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def loopback_command(command: list[str]) -> list[str]:
    return ["sandbox-exec", "-f", str(ROOT / "prototypes/surfaces/loopback.sb"), *command]


def disabled_summary(row_dir: Path) -> dict[str, object]:
    """Run the standalone browser-stress case 13 on its existing loopback fixture."""
    row_dir.mkdir(parents=True, exist_ok=True)
    prerequisites = [name for name in ("openssl", "sandbox-exec")
                     if shutil.which(name) is None]
    if prerequisites:
        return {"status": "INCOMPLETE", "reason": "Missing local prerequisite: " + ", ".join(prerequisites),
                "denominators": {"browser_cases": 1, "provider_posts_expected": 0}, "artifacts": []}
    with tempfile.TemporaryDirectory(prefix="moss-r4-feature-disabled-", dir="/private/tmp") as temporary:
        work = Path(temporary)
        certificate, key = work / "cert.pem", work / "key.pem"
        app_port, provider_port = free_port(), free_port()
        certificate_command = command_result([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
            "-keyout", str(key), "-out", str(certificate),
        ])
        if certificate_command["exit_code"]:
            return {"status": "INCOMPLETE", "reason": "Loopback certificate creation failed",
                    "commands": [safe_command(certificate_command)],
                    "denominators": {"browser_cases": 1, "provider_posts_expected": 0}, "artifacts": []}
        ready, provider_receipt = work / "ready.json", work / "provider-requests.jsonl"
        fixture_command = loopback_command([
            PYTHON, "prototypes/surfaces/summary_fixture.py", "--state", str(work / "state"),
            "--app-port", str(app_port), "--provider-port", str(provider_port), "--cert", str(certificate),
            "--key", str(key), "--receipt", str(provider_receipt), "--ready", str(ready),
        ])
        fixture_env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT))
        fixture = subprocess.Popen(fixture_command, cwd=ROOT, env=fixture_env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 30
            while not ready.exists() and fixture.poll() is None and time.monotonic() < deadline:
                time.sleep(0.1)
            if not ready.exists():
                return {"status": "INCOMPLETE", "reason": "Loopback summary fixture did not become ready",
                        "commands": [safe_command(certificate_command),
                                     {"command": fixture_command, "exit_code": fixture.poll(), "seconds": None}],
                        "denominators": {"browser_cases": 1, "provider_posts_expected": 0}, "artifacts": []}
            case_dir = work / "case-13"
            browser_command = loopback_command([
                PYTHON, "prototypes/browser-stress/run.py", "13", "--base", f"https://127.0.0.1:{app_port}",
                "--output", str(case_dir),
            ])
            browser = command_result(browser_command, env=fixture_env, timeout=180)
            result_path = case_dir / "campaign-results.json"
            results = json.loads(result_path.read_text()) if result_path.exists() else {}
            case = results.get("13", {})
            retained_result = row_dir / "case-13-results.json"
            retained_provider = row_dir / "provider-requests.jsonl"
            if result_path.exists():
                shutil.copyfile(result_path, retained_result)
            if provider_receipt.exists():
                shutil.copyfile(provider_receipt, retained_provider)
            provider_posts = case.get("provider_posts")
            local_provider_posts = len(provider_receipt.read_text().splitlines()) if provider_receipt.exists() else None
            passed = (browser["exit_code"] == 0 and case.get("status") == "PASS" and provider_posts == 0
                      and local_provider_posts == 0)
            return {
                "status": "PASS" if passed else "FAIL",
                "commands": [safe_command(certificate_command), safe_command(browser)],
                "denominators": {"browser_cases": 1, "provider_posts_expected": 0,
                                 "provider_posts_observed": provider_posts,
                                 "loopback_provider_posts_observed": local_provider_posts},
                "artifacts": [str(retained_result.relative_to(ROOT)), str(retained_provider.relative_to(ROOT))],
            }
        finally:
            fixture.terminate()
            try:
                fixture.wait(timeout=15)
            except subprocess.TimeoutExpired:
                fixture.kill()
                fixture.wait()


STATIC_ROWS = {
    "voice-bank": [
        "tests/phase2/test_voiceprint_matching.py",
        "tests/phase2/test_voiceprint_bank_operations.py",
    ],
    "rename-reassign": ["tests/phase2/test_settled_passage_correction.py"],
    "exports": [
        "tests/phase2/test_export_oracle.py",
        "tests/test_live_export_surface.py",
        "tests/test_subtitle_export.py",
    ],
    "url-ingestion": [
        "tests/phase2/test_multi_file_url_meetings.py",
        "tests/phase2/test_multi_file_url_browser.py",
    ],
}


def static_control(name: str, row_dir: Path) -> dict[str, object]:
    command = [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", *STATIC_ROWS[name]]
    result = command_result(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT)))
    return {
        "command": safe_command(result),
        "denominators": pytest_denominator(str(result["stdout"])),
        "artifacts": [str((row_dir / "receipt.json").relative_to(ROOT))],
        "passed": result["exit_code"] == 0,
    }


def require_runtime(args: argparse.Namespace, *, provider: bool = False) -> str | None:
    if not args.allow_decoder:
        return "Decoder use is not authorised; rerun with a cap-authorised --base and --allow-decoder."
    if not args.base:
        return "Missing --base for an isolated stack launched from this frozen product tree."
    if provider and not args.allow_provider:
        return "External-provider use is not authorised; rerun with --allow-provider."
    if provider and not KEY_FILE.is_file():
        return f"Missing provider key file: {KEY_FILE}"
    return None


def browser_bundle(args: argparse.Namespace, selected: set[str], run_dir: Path) -> tuple[dict[str, object] | None, str | None]:
    needs_browser = bool(selected & {"rename-reassign", "exports"})
    if not needs_browser:
        return None, None
    reason = require_runtime(args)
    if reason:
        return None, reason
    cases = [11] if "rename-reassign" in selected else []
    if "exports" in selected:
        cases = [8, 11, 10]
    command = [PYTHON, "prototypes/browser-stress/run.py", ",".join(map(str, cases)), "--base", args.base,
               "--output", str(run_dir / "browser")]
    result = command_result(command, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT)), timeout=1800)
    output = run_dir / "browser/campaign-results.json"
    rows = json.loads(output.read_text()) if output.exists() else {}
    retained = run_dir / "browser-results.json"
    if output.exists():
        shutil.copyfile(output, retained)
    return {"command": safe_command(result), "rows": rows,
            "artifact": str(retained.relative_to(ROOT)) if retained.exists() else None}, None


def run_external_summary(args: argparse.Namespace, row_dir: Path) -> dict[str, object]:
    reason = require_runtime(args, provider=True)
    planned_calls = 2 * 3
    if reason:
        return {"status": "INCOMPLETE", "reason": reason,
                "denominators": {"transcripts": 2, "trials": 3, "provider_calls_planned": planned_calls,
                                 "provider_call_cap": 10}, "artifacts": []}
    # verify_summaries has two fixed transcript inputs and one non-retrying browser attempt
    # per trial.  The population is six calls, strictly below the user-provided cap of ten.
    shell = (
        "set -a; . \"$HOME/.config/moss/openrouter.env\"; set +a; "
        f"MOSS_BASE={args.base!r} MOSS_SUMMARY_PROVIDERS=external "
        "MOSS_SUMMARY_ENDPOINT=https://openrouter.ai/api/v1 "
        "MOSS_SUMMARY_MODEL=google/gemini-2.5-flash-lite TRIALS=3 "
        f"PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. {PYTHON!r} tests/e2e/verify_summaries.py"
    )
    result = command_result(["/bin/zsh", "-lc", shell], env=dict(os.environ), timeout=1800)
    attempts = len(re.findall(r"^\s*(?:PASS|FAIL)\s+", str(result["stdout"]), flags=re.MULTILINE))
    passed = result["exit_code"] == 0 and attempts == planned_calls
    return {
        "status": "PASS" if passed else "FAIL",
        "commands": [safe_command(result)],
        "denominators": {"transcripts": 2, "trials": 3, "summary_attempts_observed": attempts,
                         "provider_calls_planned": planned_calls, "provider_call_cap": 10},
        "artifacts": [str((row_dir / "receipt.json").relative_to(ROOT))],
    }


def run_url(args: argparse.Namespace, row_dir: Path) -> dict[str, object]:
    reason = require_runtime(args)
    if reason:
        return {"status": "INCOMPLETE", "reason": reason,
                "denominators": {"success_urls": 1, "failure_controls": 3}, "artifacts": []}
    extra_tls = ["--allow-local-self-signed"] if urlsplit(args.base).hostname in {"127.0.0.1", "localhost", "::1"} else []
    success_dir, failure_dir = row_dir / "url-success", row_dir / "url-failures"
    success = command_result([
        PYTHON, "tests/e2e/verify_workspace.py", "--base", args.base, *extra_tls,
        "--corpus", str(CORPUS), "--output", str(success_dir), "--rows", "1,3",
    ], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT)), timeout=1800)
    failures = command_result([
        PYTHON, "prototypes/browser-stress/run.py", "9", "--base", args.base,
        "--output", str(failure_dir),
    ], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONPATH=str(ROOT)), timeout=600)
    success_rows = json.loads((success_dir / "results.json").read_text()) if (success_dir / "results.json").exists() else {}
    failure_rows = json.loads((failure_dir / "campaign-results.json").read_text()) if (failure_dir / "campaign-results.json").exists() else {}
    success_row, failures_row = success_rows.get("rows", {}).get("3", {}), failure_rows.get("9", {})
    passed = (success["exit_code"] == 0 and failures["exit_code"] == 0
              and success_row.get("status") == "PASS" and failures_row.get("status") == "PASS")
    return {
        "status": "PASS" if passed else "FAIL", "commands": [safe_command(success), safe_command(failures)],
        "denominators": {"success_urls": 1, "failure_controls": len(failures_row.get("variants", []))},
        "artifacts": [str(path.relative_to(ROOT)) for path in
                      (success_dir / "results.json", failure_dir / "campaign-results.json") if path.exists()],
    }


def plan() -> dict[str, object]:
    from tools.qualify.run import request_plan

    return {
        "schema": "moss-r4-feature-rows.v1",
        "product": product_tree(),
        "decoder_plan": request_plan(long=False),
        "feature_population": {
            "external_summaries": {"transcripts": ["50s", "180s"], "trials": 3,
                                   "provider_calls_planned": 6, "provider_call_cap": 10},
            "disabled_summary": {"browser_cases": [13], "provider_posts_expected": 0},
            "voice_bank": {"enrol_and_recognise_controls": 1},
            "rename_reassign": {"browser_cases": [11], "reserved_name_matrix": 1},
            "exports": {"browser_cases": [10], "formats": ["md", "txt", "json", "srt", "vtt"]},
            "url_ingestion": {"success_urls": 1, "failure_controls": 3},
        },
        "real_run_needs": [
            "a private candidate stack launched from this frozen product tree and supplied as --base",
            "an explicit, leased decoder authority plus --allow-decoder for live/file/URL rows",
            "the operator key file plus --allow-provider for the six-call external-summary row",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--rows", default="all", choices=("all", "external-summary", "disabled-summary", "voice-bank", "rename-reassign", "exports", "url-ingestion"))
    parser.add_argument("--base", help="Private candidate stack URL; never a shared deployment URL.")
    parser.add_argument("--allow-decoder", action="store_true", help="Explicitly authorise rows that consume the supplied decoder authority.")
    parser.add_argument("--allow-provider", action="store_true", help="Explicitly authorise the capped external-summary row.")
    args = parser.parse_args(argv)
    if args.base:
        parsed = urlsplit(args.base)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            parser.error("--base must be an HTTP(S) origin without credentials")
        args.base = args.base.rstrip("/")

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    document = plan()
    write(EVIDENCE / "plan.json", document)
    if args.plan_only:
        print(json.dumps({"population": document["decoder_plan"]["population"],
                          "planned_decoder_requests": document["decoder_plan"]["planned_requests"]}, indent=2))
        return 0

    selected = {"external-summary", "disabled-summary", "voice-bank", "rename-reassign", "exports", "url-ingestion"}
    if args.rows != "all":
        selected = {args.rows}
    run_dir = EVIDENCE / f"run-{utc_stamp()}"
    run_dir.mkdir()
    rows: dict[str, object] = {}
    frozen = document["product"]["frozen_product_tree"]
    if not frozen:
        reason = "Frozen product paths differ from the requested SHA."
        for name in selected:
            rows[name] = {"status": "INCOMPLETE", "reason": reason, "commands": [], "denominators": {}, "artifacts": []}
    else:
        if "disabled-summary" in selected:
            rows["disabled-summary"] = disabled_summary(run_dir / "disabled-summary")
        for name in selected & set(STATIC_ROWS):
            row_dir = run_dir / name
            row_dir.mkdir(parents=True, exist_ok=True)
            control = static_control(name, row_dir)
            rows[name] = {"status": "PASS" if control["passed"] and name == "voice-bank" else "INCOMPLETE",
                          "reason": None if control["passed"] and name == "voice-bank" else
                                    "Static control retained; browser/decoder feature exercise remains required.",
                          "static_control": control, "commands": [control["command"]],
                          "denominators": control["denominators"], "artifacts": control["artifacts"]}
        if "external-summary" in selected:
            rows["external-summary"] = run_external_summary(args, run_dir / "external-summary")
        browser, browser_reason = browser_bundle(args, selected, run_dir)
        if browser is not None:
            browser_rows = browser["rows"]
            for name, required_case in (("rename-reassign", "11"), ("exports", "10")):
                if name not in selected:
                    continue
                case = browser_rows.get(required_case, {})
                current = rows[name]
                static_ok = current.get("static_control", {}).get("passed", True)
                current.update({"status": "PASS" if static_ok and case.get("status") == "PASS" else "FAIL",
                                "reason": None, "browser_case": required_case,
                                "commands": [*current["commands"], browser["command"]],
                                "artifacts": [*current["artifacts"], browser["artifact"]]})
        elif browser_reason:
            for name in selected & {"rename-reassign", "exports"}:
                rows[name]["reason"] = browser_reason
        if "url-ingestion" in selected:
            rows["url-ingestion"] = run_url(args, run_dir / "url-ingestion") if args.allow_decoder and args.base else rows["url-ingestion"]

    for name, row in rows.items():
        write(run_dir / name / "receipt.json", row)
    receipt = {"schema": "moss-r4-feature-row-receipts.v1", "product": document["product"],
               "rows": rows, "decoder_requests_used": 0 if not args.allow_decoder else "delegated_to supplied authority",
               "external_provider_calls_used": 0 if not args.allow_provider else "bounded by external-summary population"}
    write(run_dir / "receipts.json", receipt)
    print(json.dumps({"receipt": str((run_dir / "receipts.json").relative_to(ROOT)),
                      "statuses": {name: row["status"] for name, row in rows.items()}}, indent=2))
    return 0 if all(row["status"] == "PASS" for row in rows.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
