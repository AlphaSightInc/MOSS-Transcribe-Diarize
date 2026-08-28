#!/usr/bin/env python3
"""Falsify the Wave-1 qualification manifest and attempt-bundle policy."""

from __future__ import annotations

import json
import math
import struct
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from moss_transcribe_diarize.app.phase2_audio import MeetingAudioArchive


REQUIRED_SQLITE = "3.53.4"
CORE_GATES = ("G0", "G1", "G2", "G3", "G4", "G5", "G6", "G10")
LAYERS = ("deterministic", "deployed", "pre_admission")
REQUIRED_OWNER_ACTIONS = {"read", "cursor", "feed", "stop", "abort", "rename", "rerun", "retry", "download"}


@dataclass(frozen=True)
class Candidate:
    git_sha: str
    dirty_paths: tuple[str, ...]
    sqlite_runtime: str


@dataclass(frozen=True)
class Observation:
    layer: str
    candidate_sha: str
    gate: str
    predicate: str
    measured: bool
    passed: bool


def qualify(candidate: Candidate, observations: tuple[Observation, ...]) -> dict[str, object]:
    identity_failures: list[str] = []
    if candidate.dirty_paths:
        identity_failures.append("dirty_candidate")
    if candidate.sqlite_runtime != REQUIRED_SQLITE:
        identity_failures.append("sqlite_runtime_mismatch")
    if any(item.candidate_sha != candidate.git_sha for item in observations):
        identity_failures.append("candidate_sha_mismatch")

    gates: dict[str, dict[str, object]] = {}
    for gate in CORE_GATES:
        selected = [item for item in observations if item.gate == gate]
        seen_layers = {item.layer for item in selected if item.measured}
        failures = [item.predicate for item in selected if item.measured and not item.passed]
        missing = sorted(set(LAYERS) - seen_layers)
        gates[gate] = {
            "passed": not identity_failures and not failures and not missing,
            "failures": failures,
            "missing_layers": missing,
        }
    return {
        "identity_failures": identity_failures,
        "gates": gates,
        "cumulative_core_passed": all(item["passed"] for item in gates.values()),
        "g7_claimed": False,
    }


def write_once(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def suite_qualifies(
    counts: dict[str, int], *, minimum: int, required_files: set[str], observed_files: set[str]
) -> bool:
    return (
        counts
        == {
            "collected": counts["collected"],
            "executed": counts["collected"],
            "passed": counts["collected"],
            "failed": 0,
            "skipped": 0,
            "unmeasured": 0,
        }
        and counts["collected"] >= minimum
        and observed_files == required_files
    )


def boundaries_qualify(values: dict[str, str], required: set[str]) -> bool:
    selected = [values.get(role, "") for role in required]
    return all(selected) and len(set(selected)) == len(selected)


def owner_matrix_qualifies(rows: list[dict[str, object]]) -> bool:
    indexed = {row.get("id"): row for row in rows}
    return set(indexed) == REQUIRED_OWNER_ACTIONS and all(
        row.get("before") == row.get("after") and row.get("status") in {401, 404}
        for row in indexed.values()
    )


def complete_observations(sha: str) -> tuple[Observation, ...]:
    return tuple(
        Observation(layer, sha, gate, f"{layer.lower()}_{gate.lower()}", True, True)
        for gate in CORE_GATES
        for layer in LAYERS
    )


def rehearse_cutover(root: Path) -> dict[str, object]:
    root.mkdir()
    original = root / "phase1.json"
    original.write_text(
        json.dumps(
            {
                "service_identity": "phase1-control",
                "creation_blocked": False,
                "entrants": 0,
                "active_live": 0,
                "active_jobs": 0,
                "queued_jobs": 0,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    original_bytes = original.read_bytes()
    snapshot = root / "snapshot"
    current = root / "account-current"
    candidate = root / "candidate-release"
    candidate.mkdir()
    steps: list[str] = []
    state = json.loads(original.read_text())
    state["creation_blocked"] = True
    original.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
    steps.append("block")
    if any(state[key] for key in ("entrants", "active_live", "active_jobs", "queued_jobs")):
        raise AssertionError("drain was not zero")
    steps.append("drain")
    snapshot.write_bytes(original_bytes)
    steps.append("snapshot")
    current.symlink_to(candidate)
    steps.extend(("install", "verify", "forced_failure"))
    current.unlink()
    original.write_bytes(snapshot.read_bytes())
    steps.extend(("restore", "prove_original"))
    return {
        "steps": steps,
        "original_restored": original.read_bytes() == original_bytes,
        "candidate_pointer_absent": not current.exists(),
    }


def production_audio_oracle(root: Path) -> dict[str, object]:
    root.mkdir()
    samples = 16_000 * 3 + 2_731
    pcm = b"".join(
        struct.pack("<h", int(8_000 * math.sin(2 * math.pi * 347 * index / 16_000)))
        for index in range(samples)
    )
    source = root / "accepted-prefix.pcm"
    source.write_bytes(pcm)
    archive = MeetingAudioArchive(root / "archive")
    first = archive.publish_live_prefix("account-a", "meeting-a", source, partial=True)
    second = archive.publish_live_prefix("account-b", "meeting-b", source, partial=True)
    first_bytes = first.path.read_bytes()
    second_bytes = second.path.read_bytes()
    return {
        "accepted_samples": samples,
        "first_bytes": len(first_bytes),
        "second_bytes": len(second_bytes),
        "bytes_equal": first_bytes == second_bytes,
        "metadata_equal": (
            first.byte_count,
            first.duration_ms,
        )
        == (
            second.byte_count,
            second.duration_ms,
        ),
        "duration_ms": first.duration_ms,
    }


def main() -> int:
    sha = "a" * 40
    valid = Candidate(sha, (), REQUIRED_SQLITE)
    complete = complete_observations(sha)
    cases: dict[str, dict[str, object]] = {
        "complete_core": qualify(valid, complete),
        "wrong_sqlite": qualify(Candidate(sha, (), "3.50.4"), complete),
        "dirty": qualify(Candidate(sha, ("moss.py",), REQUIRED_SQLITE), complete),
        "wrong_sha": qualify(valid, complete[:-1] + (Observation("pre_admission", "b" * 40, "G10", "pre_admission_g10", True, True),)),
        "missing_deployed": qualify(
            valid,
            tuple(item for item in complete if item.layer != "deployed"),
        ),
        "raw_failure": qualify(
            valid,
            complete[:-1]
            + (Observation("pre_admission", sha, "G10", "real_bundle_fidelity", True, False),),
        ),
    }

    with tempfile.TemporaryDirectory(prefix="moss-wave1-probe-") as directory:
        attempt = Path(directory) / "attempt"
        attempt.mkdir()
        candidate_path = attempt / "candidate-manifest.json"
        write_once(candidate_path, asdict(valid))
        overwrite_refused = False
        try:
            write_once(candidate_path, {"git_sha": "replaced"})
        except FileExistsError:
            overwrite_refused = True
        failed_attempt = attempt / "verdict.json"
        write_once(failed_attempt, cases["missing_deployed"])
        preserved_failure = json.loads(failed_attempt.read_text(encoding="utf-8"))
        rehearsal = rehearse_cutover(Path(directory) / "rehearsal")
        audio_oracle = production_audio_oracle(Path(directory) / "audio-oracle")

    suite_counts = {
        "collected": 12,
        "executed": 12,
        "passed": 12,
        "failed": 0,
        "skipped": 0,
        "unmeasured": 0,
    }
    suite_cases = {
        "complete": suite_qualifies(
            suite_counts, minimum=12, required_files={"a", "b"}, observed_files={"a", "b"}
        ),
        "decreased": suite_qualifies(
            {**suite_counts, "collected": 11, "executed": 11, "passed": 11},
            minimum=12,
            required_files={"a", "b"},
            observed_files={"a", "b"},
        ),
        "required_skip": suite_qualifies(
            {**suite_counts, "executed": 11, "passed": 11, "skipped": 1},
            minimum=12,
            required_files={"a", "b"},
            observed_files={"a", "b"},
        ),
        "missing_file": suite_qualifies(
            suite_counts, minimum=12, required_files={"a", "b"}, observed_files={"a"}
        ),
    }
    boundary_roles = {"sentinel_a", "sentinel_b", "cookie_a", "cookie_b"}
    boundary_cases = {
        "complete": boundaries_qualify(
            {role: f"private-{index}" for index, role in enumerate(sorted(boundary_roles))},
            boundary_roles,
        ),
        "missing": boundaries_qualify(
            {"sentinel_a": "a", "sentinel_b": "b", "cookie_a": "c"}, boundary_roles
        ),
        "duplicate": boundaries_qualify(
            {role: "same" for role in boundary_roles}, boundary_roles
        ),
    }
    complete_matrix = [
        {"id": action, "status": 404, "before": {"version": 1}, "after": {"version": 1}}
        for action in sorted(REQUIRED_OWNER_ACTIONS)
    ]
    changed_matrix = [dict(row) for row in complete_matrix]
    changed_matrix[0] = {**changed_matrix[0], "after": {"version": 2}}
    matrix_cases = {
        "complete": owner_matrix_qualifies(complete_matrix),
        "missing": owner_matrix_qualifies(complete_matrix[:-1]),
        "changed": owner_matrix_qualifies(changed_matrix),
    }

    full_state = {
        "contract": {
            "question": "Can one immutable candidate and write-once attempt prove the cumulative core without manufacturing deployed or G7 evidence?",
            "hypothesis": "Identity-first refusal plus required-layer predicate reduction is sufficient.",
            "minimum_primitives": [
                {
                    "name": "candidate_manifest",
                    "boundary": "immutable candidate identity and prerequisites; no commands or runtime authority",
                    "irreducible": "without it, evidence from different commits or runtimes can be combined",
                },
                {
                    "name": "attempt_bundle",
                    "boundary": "one write-once record of observations and verdict",
                    "irreducible": "without it, failed evidence can be overwritten or retried green",
                },
                {
                    "name": "gate_predicates",
                    "boundary": "pure reduction of raw measured observations; no external mutation",
                    "irreducible": "without it, prose or command exit codes can substitute for required gate facts",
                },
                {
                    "name": "authorized_adapters",
                    "boundary": "existing test, browser, CLI, UDS, and campaign surfaces only",
                    "irreducible": "observations need collection, but a second runtime or direct database path would grant new authority",
                },
                {
                    "name": "machine_denominators",
                    "boundary": "runner-produced case counts plus the fixed required-file inventory",
                    "irreducible": "a zero exit code alone cannot reveal deleted, skipped, or unmeasured required cases",
                },
                {
                    "name": "content_boundaries",
                    "boundary": "distinct nonempty Account sentinels and secrets held only in memory during scans",
                    "irreducible": "without concrete ruled values, a zero-match privacy scan is vacuous",
                },
                {
                    "name": "production_archive_oracle",
                    "boundary": "maps one exact accepted PCM prefix to the retained MP3 bytes and metadata; it grants no Meeting authority",
                    "irreducible": "without the production encoder result, maximal-prefix recovery needs an unsupported duration tolerance",
                },
            ],
            "invariants": [
                "every observation names the one candidate SHA",
                "all three layers are measured for every cumulative-core gate",
                "missing, false, dirty, mismatched, or unsupported-runtime evidence cannot pass",
                "attempt artifacts are never overwritten",
                "G7 is never inferred from G0-G6/G10",
                "every required test file and owner action remains represented",
                "privacy output scans use all distinct ruled Account and secret boundaries",
                "identical accepted PCM and production archive policy yield exact identical retained bytes and metadata",
            ],
            "assumptions_unknowns": [
                "real OAuth, deployed campaigns, TLS, rollback host state, and production canary are externally unmeasured",
                "the committed production command and evidence schema remain unqualified until their external prerequisites are measured",
            ],
            "falsifier": "any dirty/wrong-runtime/wrong-SHA/missing/raw-false case passes, a failed artifact can be replaced, G7 becomes claimed, or equal accepted PCM produces different archive bytes/metadata",
            "tool_decisions": [
                {
                    "tool": "state-reducer prototype",
                    "necessary": "the layer and write-once rules are new release policy",
                    "decision_change": "any false-positive case rejects this primitive set before production",
                },
                {
                    "tool": "temporary filesystem",
                    "necessary": "write-once behavior cannot be established by in-memory state",
                    "decision_change": "successful overwrite rejects the attempt-bundle design",
                },
                {
                    "tool": "machine test reports",
                    "necessary": "test-runner exit codes do not expose exact case denominators",
                    "decision_change": "missing, decreased, skipped, failed, or unmeasured required cases reject G10",
                },
                {
                    "tool": "no provider/browser/deployment execution",
                    "necessary": "those external prerequisites are unavailable and cannot close a gate here",
                    "decision_change": "none; their absence must remain explicit unmeasured evidence",
                },
                {
                    "tool": "production MeetingAudioArchive",
                    "necessary": "only the shipped encoder can establish a no-threshold maximal-prefix oracle",
                    "decision_change": "different bytes or metadata for equal PCM rejects exact recovery comparison",
                },
            ],
        },
        "cases": cases,
        "write_once": {
            "overwrite_refused": overwrite_refused,
            "failed_attempt_preserved": not preserved_failure["cumulative_core_passed"],
        },
        "cutover_rehearsal": rehearsal,
        "machine_denominators": suite_cases,
        "content_boundaries": boundary_cases,
        "owner_matrix": matrix_cases,
        "production_audio_oracle": audio_oracle,
    }
    print(json.dumps(full_state, indent=2, sort_keys=True))

    assertions = [
        cases["complete_core"]["cumulative_core_passed"] is True,
        cases["complete_core"]["g7_claimed"] is False,
        cases["wrong_sqlite"]["cumulative_core_passed"] is False,
        cases["dirty"]["cumulative_core_passed"] is False,
        cases["wrong_sha"]["cumulative_core_passed"] is False,
        cases["missing_deployed"]["cumulative_core_passed"] is False,
        cases["raw_failure"]["cumulative_core_passed"] is False,
        overwrite_refused,
        not preserved_failure["cumulative_core_passed"],
        rehearsal["steps"]
        == ["block", "drain", "snapshot", "install", "verify", "forced_failure", "restore", "prove_original"],
        rehearsal["original_restored"],
        rehearsal["candidate_pointer_absent"],
        suite_cases == {"complete": True, "decreased": False, "required_skip": False, "missing_file": False},
        boundary_cases == {"complete": True, "missing": False, "duplicate": False},
        matrix_cases == {"complete": True, "missing": False, "changed": False},
        audio_oracle["bytes_equal"] is True,
        audio_oracle["metadata_equal"] is True,
        audio_oracle["first_bytes"] > 0,
    ]
    verdict = "PASS" if all(assertions) else "FAIL"
    print(json.dumps({"assertions_passed": sum(assertions), "assertions_total": len(assertions), "verdict": verdict}))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
