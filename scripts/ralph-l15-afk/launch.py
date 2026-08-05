#!/usr/bin/env python3
"""Campaign L1.5 launcher and deterministic L0 proof generator."""

from __future__ import annotations

import argparse
import copy
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
    validate_gated_pins,
    validate_iteration_budget,
    validate_split_pin,
    verify_repository,
)


SCRIPT_DIR = Path(__file__).resolve().parent
CONTRACT_PATH = SCRIPT_DIR / "contract.json"
REPO = SCRIPT_DIR.parents[1]


def _case(name: str, check: Callable[[], None], detail: str) -> dict[str, str]:
    try:
        check()
    except Exception as exc:
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


def _assert(condition: bool, detail: str) -> None:
    if not condition:
        raise AssertionError(detail)


def _write_evidence(
    evidence_dir: Path, payload: dict[str, Any], transcript: str
) -> None:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    json_path = evidence_dir / "l0-dry-run.json"
    transcript_path = evidence_dir / "l0-dry-run-transcript.txt"
    manifest_path = evidence_dir / "L0_EVIDENCE.sha256"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    transcript_path.write_text(transcript, encoding="utf-8")
    manifest_path.write_text(
        f"{sha256_file(json_path)}  {json_path.name}\n"
        f"{sha256_file(transcript_path)}  {transcript_path.name}\n",
        encoding="utf-8",
    )


def dry_run(evidence_dir: Path | None) -> int:
    contract = load_contract(CONTRACT_PATH)
    cases: list[dict[str, str]] = []

    cases.append(
        _case(
            "contract_pins",
            lambda: _assert(
                contract["required_ancestor"]
                == "15d45afc418e2cc83e3967110553371010da1784"
                and contract["branch"] == "ralph/l15-live-uplift-v1"
                and contract["contract_id"] == "moss-l15-live-uplift-v1"
                and contract["corpus_manifest_hash"]
                == "7c60cb1aaba807adcf6969c616130f0c71b7d8ffb9014d9221d60e1c333f27cb"
                and contract["split_manifest_hash"] == "UNFROZEN",
                "contract pin mismatch",
            ),
            "ancestor, branch, corpus, and UNFROZEN split pinned",
        )
    )
    cases.append(
        _case(
            "active_corpus_pin_matches",
            lambda: validate_corpus_pin(contract, REPO),
            "promoted corpus-manifest hash matches",
        )
    )
    cases.append(
        _case(
            "split_manifest_unfrozen",
            lambda: _expects(
                "split_manifest_unfrozen", lambda: validate_split_pin(contract, REPO)
            ),
            "split-dependent work refused with split_manifest_unfrozen",
        )
    )
    try:
        validate_gated_pins(contract, REPO)
    except GuardrailError as exc:
        gated_status = 2
        gated_output = blocked_text(exc) + "\n"
    else:
        gated_status = 0
        gated_output = "unexpected pass\n"
    cases.append(
        _case(
            "gated_unfrozen_run_refused",
            lambda: _assert(
                gated_status == 2
                and "split_manifest_unfrozen" in gated_output
                and classify_promise(gated_output) == "BLOCKED",
                gated_output.strip(),
            ),
            "exit=2 named refusal ending with BLOCKED promise",
        )
    )
    cases.append(
        _case(
            "allowlist_accepts_l15",
            lambda: validate_changed_paths(
                [
                    "scripts/ralph-l15-afk/guardrails.py",
                    "prototypes/streaming-diarization/l15/README.md",
                    "prototypes/streaming-diarization/NOTES.md",
                    "prototypes/streaming-diarization/README.md",
                ],
                contract,
            ),
            "L1.5 prototype, shared notes/readme, and bundle accepted",
        )
    )
    for name, path in [
        ("deny_product_python", "moss_transcribe_diarize/app/live_identity.py"),
        ("deny_macos", "macos/MOSSCapture/Sources/x.swift"),
        ("deny_ops", "ops/service.json"),
        ("deny_product_tests", "tests/test_live_identity.py"),
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
            "refused path outside allowlist",
        )
    )
    cases.append(
        _case(
            "iteration_12_allowed",
            lambda: validate_iteration_budget(12, contract["max_iterations"]),
            "iteration budget 12 accepted",
        )
    )
    cases.append(
        _case(
            "iteration_13_refused",
            lambda: _expects(
                "iteration_cap_exceeded",
                lambda: validate_iteration_budget(13, contract["max_iterations"]),
            ),
            "iteration budget 13 refused",
        )
    )

    with tempfile.TemporaryDirectory(prefix="ralph-l15-pins-") as temp:
        temp_root = Path(temp)
        corpus = temp_root / contract["corpus_manifest_path"]
        split = temp_root / contract["split_manifest_path"]
        corpus.parent.mkdir(parents=True)
        split.parent.mkdir(parents=True)
        corpus.write_text('{"corpus":true}\n', encoding="utf-8")
        split.write_text('{"split":true}\n', encoding="utf-8")
        frozen = copy.deepcopy(contract)
        frozen["corpus_manifest_hash"] = sha256_file(corpus)
        frozen["split_manifest_hash"] = sha256_file(split)
        cases.append(
            _case(
                "frozen_pins_accept",
                lambda: validate_gated_pins(frozen, temp_root),
                "matching corpus and split pins accepted",
            )
        )
        split.write_text('{"split":false}\n', encoding="utf-8")
        cases.append(
            _case(
                "split_hash_drift_refused",
                lambda: _expects(
                    "split_manifest_hash_mismatch",
                    lambda: validate_split_pin(frozen, temp_root),
                ),
                "split mutation refused",
            )
        )
        split.write_text('{"split":true}\n', encoding="utf-8")
        corpus.write_text('{"corpus":false}\n', encoding="utf-8")
        cases.append(
            _case(
                "corpus_hash_drift_refused",
                lambda: _expects(
                    "corpus_manifest_hash_mismatch",
                    lambda: validate_corpus_pin(frozen, temp_root),
                ),
                "corpus mutation refused",
            )
        )
        sentinel = WriterSentinel(temp_root / ".state")
        sentinel.acquire()
        try:
            cases.append(
                _case(
                    "single_writer_refusal",
                    lambda: _expects("single_writer_active", sentinel.acquire),
                    "second writer refused",
                )
            )
        finally:
            sentinel.release()

    with tempfile.TemporaryDirectory(prefix="ralph-l15-git-") as temp:
        git_root = Path(temp)
        subprocess.run(["git", "init", "-q", "-b", "l15-test"], cwd=git_root, check=True)
        run_git(git_root, "config", "user.name", "L15 Guardrail")
        run_git(git_root, "config", "user.email", "l15@example.invalid")
        plan = git_root / "plan.md"
        plan.write_text("frozen plan\n", encoding="utf-8")
        run_git(git_root, "add", "plan.md")
        run_git(git_root, "commit", "-q", "-m", "fixture")
        head = run_git(git_root, "rev-parse", "HEAD")
        fixture = copy.deepcopy(contract)
        fixture.update(
            {
                "branch": "l15-test",
                "plan_path": "plan.md",
                "plan_sha256": sha256_file(plan),
                "required_ancestor": head,
                "worktree": str(git_root),
            }
        )
        cases.append(
            _case(
                "clean_expected_head_accepts",
                lambda: verify_repository(git_root, fixture, expected_previous_commit=head),
                "clean tree at expected commit accepted",
            )
        )
        cases.append(
            _case(
                "expected_head_drift_refused",
                lambda: _expects(
                    "expected_previous_commit_mismatch",
                    lambda: verify_repository(
                        git_root, fixture, expected_previous_commit="0" * 40
                    ),
                ),
                "unexpected HEAD refused",
            )
        )
        dirty = git_root / "dirty.txt"
        dirty.write_text("dirty\n", encoding="utf-8")
        cases.append(
            _case(
                "dirty_tree_refused",
                lambda: _expects(
                    "worktree_dirty",
                    lambda: verify_repository(git_root, fixture, expected_previous_commit=head),
                ),
                "dirty tree refused",
            )
        )

    cases.extend(
        [
            _case(
                "blocked_stop_promise",
                lambda: _assert(
                    classify_promise(f"reason\n{BLOCKED_PROMISE}\n") == "BLOCKED",
                    "BLOCKED not recognized",
                ),
                "BLOCKED promise recognized",
            ),
            _case(
                "complete_stop_promise",
                lambda: _assert(
                    classify_promise(f"done\n{COMPLETE_PROMISE}\n") == "COMPLETE",
                    "COMPLETE not recognized",
                ),
                "COMPLETE promise recognized",
            ),
            _case(
                "missing_promise_continues",
                lambda: _assert(
                    classify_promise("working") == "CONTINUE",
                    "missing promise misclassified",
                ),
                "missing terminal promise continues",
            ),
        ]
    )

    passed = sum(case["status"] == "PASS" for case in cases)
    overall = "PASS" if passed == len(cases) else "FAIL"
    transcript = "\n".join(
        [
            f"L0 dry-run contract={contract['contract_id']}",
            *(f"{case['status']} {case['name']}: {case['detail']}" for case in cases),
            f"RESULT {overall} {passed}/{len(cases)}",
        ]
    ) + "\n"
    payload = {
        "campaign": "L1.5",
        "contract_id": contract["contract_id"],
        "corpus_manifest_hash": contract["corpus_manifest_hash"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "guardrails_sha256": sha256_file(SCRIPT_DIR / "guardrails.py"),
        "launch_sha256": sha256_file(Path(__file__)),
        "overall": overall,
        "plan_sha256": contract["plan_sha256"],
        "reproduce": "scripts/ralph-l15-afk/launch.sh --dry-run --evidence-dir scripts/ralph-l15-afk/evidence",
        "results": cases,
        "split_manifest_hash": contract["split_manifest_hash"],
    }
    if evidence_dir is not None:
        _write_evidence(evidence_dir, payload, transcript)
    sys.stdout.write(transcript)
    return 0 if overall == "PASS" else 1


def gated_run(iterations: int, command: list[str]) -> int:
    contract = load_contract(CONTRACT_PATH)
    try:
        validate_iteration_budget(iterations, contract["max_iterations"])
        validate_gated_pins(contract, REPO)
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
                        "RALPH_L15_CONTRACT": contract["contract_id"],
                        "RALPH_L15_ITERATION": str(iteration),
                        "RALPH_L15_ITERATION_CAP": str(iterations),
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
                validate_changed_paths(changed_paths_since(REPO, expected_previous), contract)
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
                    raise GuardrailError("iteration_command_failed", f"exit={result.returncode}")
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
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if args.dry_run:
        return dry_run(args.evidence_dir)
    return gated_run(args.iterations, command)


if __name__ == "__main__":
    raise SystemExit(main())
