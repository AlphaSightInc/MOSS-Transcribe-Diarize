#!/usr/bin/env python3
"""Fail-closed Campaign-A guardrails. Standard library only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Iterable


COMPLETE_PROMISE = "<promise>COMPLETE</promise>"
BLOCKED_PROMISE = "<promise>BLOCKED</promise>"
UNFROZEN = "UNFROZEN"


class GuardrailError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_contract(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        contract = json.load(handle)
    required = {
        "allowlist",
        "branch",
        "contract_id",
        "corpus_manifest_hash",
        "corpus_manifest_path",
        "denylist",
        "max_campaign_a_iterations",
        "plan_path",
        "plan_sha256",
        "post_verdict_allowlist",
        "required_ancestor",
        "worktree",
    }
    missing = sorted(required - contract.keys())
    if missing:
        raise GuardrailError("contract_incomplete", ",".join(missing))
    if contract["contract_id"] != "moss-l2-retained-identity-v1":
        raise GuardrailError("contract_id_mismatch", str(contract["contract_id"]))
    if contract["max_campaign_a_iterations"] != 10:
        raise GuardrailError(
            "iteration_cap_mismatch", str(contract["max_campaign_a_iterations"])
        )
    return contract


def validate_iteration_budget(requested: int, maximum: int) -> None:
    if requested < 1:
        raise GuardrailError("iteration_budget_invalid", str(requested))
    if requested > maximum:
        raise GuardrailError("iteration_cap_exceeded", f"{requested}>{maximum}")


def _matches(rule: str, path: str) -> bool:
    if rule.endswith("/**"):
        return path.startswith(rule[:-2])
    return path == rule


def validate_changed_paths(
    paths: Iterable[str], contract: dict[str, Any], *, post_verdict: bool = False
) -> None:
    allowlist = list(contract["allowlist"])
    if post_verdict:
        allowlist.extend(contract["post_verdict_allowlist"])
    for raw_path in paths:
        path = raw_path.strip().lstrip("./")
        if not path:
            continue
        if any(_matches(rule, path) for rule in contract["denylist"]):
            raise GuardrailError("product_path_denied", path)
        if not any(_matches(rule, path) for rule in allowlist):
            raise GuardrailError("path_not_allowlisted", path)


def validate_corpus_pin(contract: dict[str, Any], repo: Path) -> None:
    expected = contract["corpus_manifest_hash"]
    if expected == UNFROZEN:
        raise GuardrailError(
            "corpus_manifest_unfrozen",
            "Campaign A gated iteration refused until A1 freezes corpus-manifest.json",
        )
    manifest = repo / contract["corpus_manifest_path"]
    if not manifest.is_file():
        raise GuardrailError("corpus_manifest_missing", str(manifest))
    actual = sha256_file(manifest)
    if actual != expected:
        raise GuardrailError(
            "corpus_manifest_hash_mismatch", f"expected={expected} actual={actual}"
        )


def classify_promise(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if lines and lines[-1] == BLOCKED_PROMISE:
        return "BLOCKED"
    if lines and lines[-1] == COMPLETE_PROMISE:
        return "COMPLETE"
    return "CONTINUE"


def blocked_text(error: GuardrailError) -> str:
    return f"BLOCKED {error.code}: {error.detail}\n{BLOCKED_PROMISE}"


def run_git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        raise GuardrailError(
            "git_command_failed", f"git {' '.join(args)}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def verify_repository(
    repo: Path, contract: dict[str, Any], *, expected_previous_commit: str
) -> None:
    if repo.resolve() != Path(contract["worktree"]).resolve():
        raise GuardrailError("worktree_mismatch", str(repo.resolve()))
    branch = run_git(repo, "branch", "--show-current")
    if branch != contract["branch"]:
        raise GuardrailError("branch_mismatch", branch)
    head = run_git(repo, "rev-parse", "HEAD")
    if head != expected_previous_commit:
        raise GuardrailError(
            "expected_previous_commit_mismatch",
            f"expected={expected_previous_commit} actual={head}",
        )
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", contract["required_ancestor"], "HEAD"],
        cwd=repo,
        check=False,
    )
    if ancestor_check.returncode != 0:
        raise GuardrailError("required_ancestor_missing", contract["required_ancestor"])
    if run_git(repo, "status", "--porcelain=v1"):
        raise GuardrailError("worktree_dirty", str(repo))
    plan = repo / contract["plan_path"]
    if not plan.is_file() or sha256_file(plan) != contract["plan_sha256"]:
        raise GuardrailError("plan_hash_mismatch", str(plan))


def changed_paths_since(repo: Path, previous_commit: str) -> list[str]:
    tracked = run_git(repo, "diff", "--name-only", previous_commit).splitlines()
    untracked = run_git(repo, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked + untracked))


class WriterSentinel:
    def __init__(self, state_dir: Path) -> None:
        self.lock_dir = state_dir / "writer.lock"

    def acquire(self) -> None:
        self.lock_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock_dir.mkdir()
        except FileExistsError as exc:
            raise GuardrailError("single_writer_active", str(self.lock_dir)) from exc
        (self.lock_dir / "owner.json").write_text(
            json.dumps({"pid": os.getpid()}, sort_keys=True) + "\n", encoding="utf-8"
        )

    def release(self) -> None:
        owner = self.lock_dir / "owner.json"
        if owner.exists():
            owner.unlink()
        if self.lock_dir.exists():
            self.lock_dir.rmdir()

    def __enter__(self) -> "WriterSentinel":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
