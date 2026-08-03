#!/usr/bin/env python3
"""Campaign-A launcher and deterministic A0 dry-run evidence generator."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from guardrails import (
    BLOCKED_PROMISE,
    COMPLETE_PROMISE,
    GuardrailError,
    WriterSentinel,
    blocked_text,
    changed_paths_since,
    classify_promise,
    load_contract,
    run_git,
    sha256_file,
    validate_changed_paths,
    validate_corpus_pin,
    validate_iteration_budget,
    verify_repository,
)


SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_PATH = SCRIPT_DIR / "contract.json"
REPO = SCRIPT_DIR.parents[1]


def _case(name: str, check: Callable[[], None], detail: str) -> dict[str, str]:
    try:
        check()
    except Exception as exc:  # dry-run must preserve unexpected failure detail
        return {"name": name, "status": "FAIL", "detail": f"{type(exc).__name__}: {exc}"}
    return {"name": name, "status": "PASS", "detail": detail}


def _expects(code: str, action: Callable[[], None]) -> None:
    try:
        action()
    except GuardrailError as exc:
        if exc.code == code:
            return
        raise AssertionError(f"expected {code}, got {exc.code}") from exc
    raise AssertionError(f"expected {code}, action passed")


def _write_evidence(
    evidence_dir: Path, payload: dict[str, Any], transcript: str, label: str
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / f"{label}.json"
    transcript_path = evidence_dir / f"{label}-transcript.txt"
    manifest_path = evidence_dir / f"{label.upper().replace('-', '_')}_EVIDENCE.sha256"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    transcript_path.write_text(transcript, encoding="utf-8")
    manifest_lines = [
        f"{sha256_file(json_path)}  {json_path.name}",
        f"{sha256_file(transcript_path)}  {transcript_path.name}",
    ]
    manifest_path.write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")


def dry_run(evidence_dir: Path | None, evidence_label: str) -> int:
    contract = load_contract(CONTRACT_PATH)
    unfrozen_contract = copy.deepcopy(contract)
    unfrozen_contract["corpus_manifest_hash"] = "UNFROZEN"
    cases: list[dict[str, str]] = []

    cases.append(
        _case(
            "contract_pins",
            lambda: (
                contract["required_ancestor"]
                == "9089b33210401111865da7abc160ab0bcb4aa266"
                and contract["branch"] == "ralph/l2-retained-identity-v1"
                and contract["contract_id"] == "moss-l2-retained-identity-v1"
                and (
                    contract["corpus_manifest_hash"] == "UNFROZEN"
                    or (
                        len(contract["corpus_manifest_hash"]) == 64
                        and all(
                            char in "0123456789abcdef"
                            for char in contract["corpus_manifest_hash"]
                        )
                    )
                )
            )
            or (_ for _ in ()).throw(AssertionError("pin mismatch")),
            "ancestor, branch, contract, and corpus state pinned",
        )
    )
    cases.append(
        _case(
            "allowlist_accepts_campaign_a",
            lambda: validate_changed_paths(
                [
                    "scripts/ralph-l2-afk/guardrails.py",
                    "prototypes/streaming-diarization/l2-stage0/README.md",
                    "prototypes/streaming-diarization/NOTES.md",
                ],
                contract,
            ),
            "Campaign-A prototype, shared NOTES, and new bundle accepted",
        )
    )
    for name, path in [
        ("deny_product_python", "moss_transcribe_diarize/app/live_tape.py"),
        ("deny_macos", "macos/MOSSCapture/Sources/x.swift"),
        ("deny_ops", "ops/service.json"),
        ("deny_product_tests", "tests/test_live_tape.py"),
    ]:
        cases.append(
            _case(
                name,
                lambda path=path: _expects(
                    "product_path_denied",
                    lambda: validate_changed_paths([path], contract),
                ),
                f"refused {path} with product_path_denied",
            )
        )
    cases.append(
        _case(
            "deny_unlisted_path",
            lambda: _expects(
                "path_not_allowlisted",
                lambda: validate_changed_paths(["docs/unrelated.md"], contract),
            ),
            "refused non-product path outside allowlist",
        )
    )
    cases.append(
        _case(
            "iteration_10_allowed",
            lambda: validate_iteration_budget(10, contract["max_campaign_a_iterations"]),
            "iteration budget 10 accepted",
        )
    )
    cases.append(
        _case(
            "iteration_11_refused",
            lambda: _expects(
                "iteration_cap_exceeded",
                lambda: validate_iteration_budget(11, contract["max_campaign_a_iterations"]),
            ),
            "iteration budget 11 refused with iteration_cap_exceeded",
        )
    )
    cases.append(
        _case(
            "corpus_manifest_unfrozen",
            lambda: _expects(
                "corpus_manifest_unfrozen",
                lambda: validate_corpus_pin(unfrozen_contract, REPO),
            ),
            f"gated iteration refused with corpus_manifest_unfrozen and {BLOCKED_PROMISE}",
        )
    )
    try:
        validate_iteration_budget(1, unfrozen_contract["max_campaign_a_iterations"])
        validate_corpus_pin(unfrozen_contract, REPO)
    except GuardrailError as exc:
        gated_refusal_status = 2
        gated_refusal_output = blocked_text(exc) + "\n"
    else:
        gated_refusal_status = 0
        gated_refusal_output = "unexpected pass\n"
    cases.append(
        _case(
            "gated_unfrozen_run_refused",
            lambda: (
                gated_refusal_status == 2
                and "corpus_manifest_unfrozen" in gated_refusal_output
                and classify_promise(gated_refusal_output) == "BLOCKED"
            )
            or (_ for _ in ()).throw(AssertionError(gated_refusal_output.strip())),
            "exit=2 output=" + " | ".join(gated_refusal_output.strip().splitlines()),
        )
    )
    if contract["corpus_manifest_hash"] != "UNFROZEN":
        cases.append(
            _case(
                "active_corpus_pin_matches",
                lambda: validate_corpus_pin(contract, REPO),
                "active launcher pin equals corpus-manifest.json SHA-256",
            )
        )
    with tempfile.TemporaryDirectory(prefix="ralph-l2-a0-") as temp:
        temp_root = Path(temp)
        manifest = temp_root / contract["corpus_manifest_path"]
        manifest.parent.mkdir(parents=True)
        manifest.write_text('{"frozen":true}\n', encoding="utf-8")
        frozen = copy.deepcopy(contract)
        frozen["corpus_manifest_hash"] = sha256_file(manifest)
        cases.append(
            _case(
                "frozen_manifest_hash_accepts",
                lambda: validate_corpus_pin(frozen, temp_root),
                "matching frozen manifest hash accepted",
            )
        )
        manifest.write_text('{"frozen":false}\n', encoding="utf-8")
        cases.append(
            _case(
                "manifest_hash_drift_refused",
                lambda: _expects(
                    "corpus_manifest_hash_mismatch",
                    lambda: validate_corpus_pin(frozen, temp_root),
                ),
                "manifest mutation refused with corpus_manifest_hash_mismatch",
            )
        )
        sentinel = WriterSentinel(temp_root / ".state")
        sentinel.acquire()
        try:
            cases.append(
                _case(
                    "single_writer_refusal",
                    lambda: _expects("single_writer_active", sentinel.acquire),
                    "second writer refused with single_writer_active",
                )
            )
        finally:
            sentinel.release()
    with tempfile.TemporaryDirectory(prefix="ralph-l2-git-a0-") as temp:
        git_root = Path(temp)
        subprocess.run(
            ["git", "init", "-q", "-b", "a0-test"], cwd=git_root, check=True
        )
        run_git(git_root, "config", "user.name", "A0 Guardrail")
        run_git(git_root, "config", "user.email", "a0-guardrail@example.invalid")
        plan = git_root / "plan.md"
        plan.write_text("frozen plan\n", encoding="utf-8")
        run_git(git_root, "add", "plan.md")
        run_git(git_root, "commit", "-q", "-m", "fixture")
        fixture_head = run_git(git_root, "rev-parse", "HEAD")
        fixture_contract = copy.deepcopy(contract)
        fixture_contract.update(
            {
                "branch": "a0-test",
                "plan_path": "plan.md",
                "plan_sha256": sha256_file(plan),
                "required_ancestor": fixture_head,
                "worktree": str(git_root),
            }
        )
        cases.append(
            _case(
                "clean_expected_head_accepts",
                lambda: verify_repository(
                    git_root,
                    fixture_contract,
                    expected_previous_commit=fixture_head,
                ),
                "clean tree at expected previous commit accepted",
            )
        )
        cases.append(
            _case(
                "expected_head_drift_refused",
                lambda: _expects(
                    "expected_previous_commit_mismatch",
                    lambda: verify_repository(
                        git_root,
                        fixture_contract,
                        expected_previous_commit="0" * 40,
                    ),
                ),
                "unexpected HEAD refused with expected_previous_commit_mismatch",
            )
        )
        dirty = git_root / "dirty.txt"
        dirty.write_text("dirty\n", encoding="utf-8")
        cases.append(
            _case(
                "dirty_tree_refused",
                lambda: _expects(
                    "worktree_dirty",
                    lambda: verify_repository(
                        git_root,
                        fixture_contract,
                        expected_previous_commit=fixture_head,
                    ),
                ),
                "dirty tree refused with worktree_dirty",
            )
        )
        dirty.unlink()
    cases.extend(
        [
            _case(
                "blocked_stop_promise",
                lambda: (
                    classify_promise(f"reason\n{BLOCKED_PROMISE}\n") == "BLOCKED"
                )
                or (_ for _ in ()).throw(AssertionError("BLOCKED not recognized")),
                "BLOCKED promise stops with exit 2",
            ),
            _case(
                "complete_stop_promise",
                lambda: (
                    classify_promise(f"done\n{COMPLETE_PROMISE}\n") == "COMPLETE"
                )
                or (_ for _ in ()).throw(AssertionError("COMPLETE not recognized")),
                "COMPLETE promise stops with exit 0",
            ),
            _case(
                "missing_promise_continues",
                lambda: (classify_promise("working") == "CONTINUE")
                or (_ for _ in ()).throw(AssertionError("missing promise misclassified")),
                "output without terminal promise continues",
            ),
            _case(
                "unfrozen_refusal_is_blocked",
                lambda: (
                    classify_promise(
                        blocked_text(
                            GuardrailError("corpus_manifest_unfrozen", "refused")
                        )
                    )
                    == "BLOCKED"
                )
                or (_ for _ in ()).throw(AssertionError("refusal lacks BLOCKED promise")),
                "UNFROZEN named refusal terminates through BLOCKED promise",
            ),
        ]
    )

    passed = sum(case["status"] == "PASS" for case in cases)
    overall = "PASS" if passed == len(cases) else "FAIL"
    transcript_lines = [
        f"A0 dry-run contract={contract['contract_id']}",
        *(f"{case['status']} {case['name']}: {case['detail']}" for case in cases),
        f"RESULT {overall} {passed}/{len(cases)}",
    ]
    transcript = "\n".join(transcript_lines) + "\n"
    payload = {
        "campaign": "A",
        "contract_id": contract["contract_id"],
        "corpus_manifest_hash": contract["corpus_manifest_hash"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guardrails_sha256": sha256_file(SCRIPT_DIR / "guardrails.py"),
        "launch_sha256": sha256_file(Path(__file__)),
        "overall": overall,
        "plan_sha256": contract["plan_sha256"],
        "reproduce": "scripts/ralph-l2-afk/launch.sh --dry-run --evidence-dir scripts/ralph-l2-afk/evidence",
        "results": cases,
    }
    if evidence_dir is not None:
        _write_evidence(evidence_dir, payload, transcript, evidence_label)
    sys.stdout.write(transcript)
    return 0 if overall == "PASS" else 1


def gated_run(iterations: int, command: list[str]) -> int:
    contract = load_contract(CONTRACT_PATH)
    try:
        validate_iteration_budget(iterations, contract["max_campaign_a_iterations"])
        validate_corpus_pin(contract, REPO)
    except GuardrailError as exc:
        print(blocked_text(exc))
        return 2
    if not command:
        print(blocked_text(GuardrailError("iteration_command_missing", "use -- command")))
        return 2

    state_dir = SCRIPT_DIR / ".state"
    expected_previous = run_git(REPO, "rev-parse", "HEAD")
    try:
        with WriterSentinel(state_dir):
            for iteration in range(1, iterations + 1):
                if (SCRIPT_DIR / ".stop").exists():
                    print("STOP stop_file_present")
                    return 0
                verify_repository(
                    REPO, contract, expected_previous_commit=expected_previous
                )
                env = os.environ.copy()
                env.update(
                    {
                        "RALPH_L2_CONTRACT": contract["contract_id"],
                        "RALPH_L2_ITERATION": str(iteration),
                        "RALPH_L2_ITERATION_CAP": str(iterations),
                    }
                )
                result = subprocess.run(
                    command,
                    cwd=REPO,
                    check=False,
                    text=True,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
                output = result.stdout or ""
                sys.stdout.write(output)
                post_verdict = (
                    REPO
                    / "prototypes/streaming-diarization/l2-stage0/L2_STAGE0_VERDICT.json"
                ).is_file()
                validate_changed_paths(
                    changed_paths_since(REPO, expected_previous),
                    contract,
                    post_verdict=post_verdict,
                )
                if run_git(REPO, "status", "--porcelain=v1"):
                    raise GuardrailError(
                        "worktree_dirty_after_iteration",
                        "iteration must commit its allowlisted change before returning",
                    )
                promise = classify_promise(output)
                if promise == "BLOCKED":
                    return 2
                if promise == "COMPLETE":
                    return 0
                if result.returncode != 0:
                    raise GuardrailError(
                        "iteration_command_failed", f"exit={result.returncode}"
                    )
                new_head = run_git(REPO, "rev-parse", "HEAD")
                if new_head == expected_previous:
                    raise GuardrailError("iteration_no_commit", str(iteration))
                expected_previous = new_head
    except GuardrailError as exc:
        print(blocked_text(exc))
        return 2
    print(blocked_text(GuardrailError("iteration_budget_exhausted", str(iterations))))
    return 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--evidence-label", default="a0-dry-run")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if args.dry_run:
        return dry_run(args.evidence_dir, args.evidence_label)
    return gated_run(args.iterations, command)


if __name__ == "__main__":
    raise SystemExit(main())
