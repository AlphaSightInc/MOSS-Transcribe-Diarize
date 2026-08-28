#!/usr/bin/env python3
"""Falsify the Wave-1 qualification manifest and attempt-bundle policy."""

from __future__ import annotations

import json
import math
import struct
import tempfile
import copy
import inspect
import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path

from moss_transcribe_diarize import phase2_acceptance as acceptance
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
    from moss_transcribe_diarize.phase2_cutover_rehearsal import rehearse

    root.mkdir()
    release = root / "candidate-release"
    (release / "bin").mkdir(parents=True)
    launcher = release / "bin/mtd-account-web"
    launcher.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    web_unit = root / "moss-web.service"
    vllm_unit = root / "moss-vllm.service"
    web_unit.write_text("ExecStart=/candidate/bin/mtd-account-web\n", encoding="utf-8")
    vllm_unit.write_text("ExecStart=/shared/bin/vllm\n", encoding="utf-8")
    candidate = root / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema": "moss-account-candidate.v1",
                "activation_state": "staged_inert",
                "release": str(release),
                "release_launcher": str(launcher),
                "release_launcher_sha256": hashlib.sha256(launcher.read_bytes()).hexdigest(),
                "web_unit_path": str(web_unit),
                "web_unit_sha256": hashlib.sha256(web_unit.read_bytes()).hexdigest(),
                "vllm_unit_path": str(vllm_unit),
                "vllm_unit_sha256": hashlib.sha256(vllm_unit.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    fixture = root / "phase1.json"
    fixture.write_text(
        json.dumps(
            {
                "schema": "moss-isolated-cutover-fixture.v2",
                "service_identity": "phase1-control",
                "vllm_runtime_file": "runtime/vllm.json",
                "runtime_views": [
                    {"name": name, "entrants": 0, "active_live": 0, "active_jobs": 0, "queued_jobs": 0}
                    for name in ("studio", "live")
                ],
                "snapshot_files": {
                    "profiles/moss.env": "MOSS_PHASE=1\n",
                    "runtime/vllm.json": "{\"pid\":9001,\"argv\":[\"vllm\",\"serve\"]}\n",
                    "state/meeting.json": "{\"version\":1}\n",
                    "systemd/moss-web.service": "ExecStart=/phase1/bin/web\n",
                },
            }
        ),
        encoding="utf-8",
    )
    return rehearse(original_fixture=fixture, candidate_manifest=candidate)


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


def valid_output_enters_attempt(root: Path) -> dict[str, object]:
    """Exercise the production entrypoint through its candidate-shaped identity boundary."""

    class AttemptReached(RuntimeError):
        pass

    class SentinelBundle:
        def __init__(self, _path: Path) -> None:
            raise AttemptReached

    original_discover = acceptance.discover_candidate
    original_profile = acceptance.load_profile
    original_bundle = acceptance.AttemptBundle
    acceptance.discover_candidate = lambda _repo: {"git_sha": "a" * 40}  # type: ignore[assignment]
    acceptance.load_profile = lambda _path: ({}, [])  # type: ignore[assignment]
    acceptance.AttemptBundle = SentinelBundle  # type: ignore[assignment]
    try:
        output = root / "evidence/phase2/wave-1/20260828T120000Z-aaaaaaa"
        try:
            acceptance.run_acceptance(
                wave=1,
                output=output,
                repo=root,
                profile_path=root / "profile.json",
            )
        except AttemptReached:
            return {"reached_attempt_bundle": True, "failure": None}
        except Exception as exc:
            return {
                "reached_attempt_bundle": False,
                "failure": type(exc).__name__,
            }
        return {"reached_attempt_bundle": False, "failure": "returned"}
    finally:
        acceptance.discover_candidate = original_discover
        acceptance.load_profile = original_profile
        acceptance.AttemptBundle = original_bundle


def capacity_raw() -> dict[str, object]:
    sessions: list[dict[str, object]] = []
    for ordinal in range(1, 5):
        sessions.append(
            {
                "session_ordinal": ordinal,
                "account_ordinal": 1 if ordinal % 2 else 2,
                "frames": 1200,
                "lags": [1.0, 2.0],
                "accepted_samples": 9_600_000,
                "accounted_samples": 9_600_000,
                "maximum_pending_work_items": 1,
                "own_marker_present": True,
                "foreign_markers_absent": True,
                "events": [
                    {
                        "kind": "canonical_queued",
                        "runtime_monotonic_ns": ordinal,
                        "item_id": ordinal,
                    },
                    {
                        "kind": "canonical_started",
                        "runtime_monotonic_ns": 10 + ordinal,
                        "item_id": ordinal,
                    },
                    {
                        "kind": "canonical_processed",
                        "runtime_monotonic_ns": 20 + ordinal,
                        "item_id": ordinal,
                        "canonical_decode_elapsed_sec": 0.9,
                        "frozen_span_duration_sec": 1.0,
                    },
                    {
                        "kind": "rolling_decode_queued",
                        "runtime_monotonic_ns": 30 + ordinal,
                        "admitted": True,
                        "item_id": 10 + ordinal,
                    },
                    {
                        "kind": "rolling_decode_completed",
                        "runtime_monotonic_ns": 40 + ordinal,
                        "item_id": 10 + ordinal,
                        "outcome": "published",
                    },
                ],
            }
        )
    lifecycle = [
        {
            "session_id": str(session["session_ordinal"]),
            "kind": event["kind"],
            "payload": {key: value for key, value in event.items() if key != "kind"},
        }
        for session, event in sorted(
            (
                (session, event)
                for session in sessions
                for event in session["events"]  # type: ignore[index]
                if str(event["kind"]).startswith("canonical_")
            ),
            key=lambda pair: pair[1]["runtime_monotonic_ns"],
        )
    ]
    fairness = acceptance.canonical_lifecycle_fairness(
        lifecycle, {"1", "2", "3", "4"}, maximum_skew=1
    )
    return {
        "sessions": 4,
        "accounts": 2,
        "requested_duration_seconds": 600,
        "duration_seconds": 600,
        "campaign_interval": {
            "started_monotonic_ns": 1_000_000_000,
            "finished_monotonic_ns": 601_000_000_000,
        },
        "real_human_speech": True,
        "ingress_cadence_seconds": 0.5,
        "dispatch_skew": 1,
        "fairness_measured": True,
        "fairness_observation": fairness,
        "prestop_inference_rtf": 0.9,
        "refinement_queue_depth": 1,
        "vllm_gpu_cache_use": 0.9,
        "rss_growth_bytes": 4 * 1024**3,
        "rss_samples": [0, 4 * 1024**3],
        "vllm_gpu_cache_samples": [0.8, 0.9],
        "session_observations": sessions,
        "wrong_owner_observations": [
            {
                "session_ordinal": ordinal,
                "sequence": sequence,
                "status": 404,
                "foreign_matches": 0,
            }
            for sequence in range(1200)
            for ordinal in range(1, 5)
        ],
        "log_match_counts": {"oom": 0, "accelerator": 0},
        "backpressure_observation": {
            "observed_429": True,
            "peer_progress": True,
            "same_sequence_retry": True,
        },
    }


def fairness_false_pass() -> dict[str, object]:
    baseline = capacity_raw()
    absent = copy.deepcopy(baseline)
    for session in absent["session_observations"]:  # type: ignore[index]
        session["events"] = [  # type: ignore[index]
            event
            for event in session["events"]  # type: ignore[index]
            if event["kind"] not in {"canonical_queued", "canonical_started"}
        ]
    absent["fairness_measured"] = False
    absent["dispatch_skew"] = 0
    absent["fairness_observation"] = {
        "applicability": "not_applicable",
        "passes": None,
        "contended_pair_dispatch_observations": 0,
        "maximum_contended_pair_dispatch_skew": 0,
    }
    return {
        "baseline_passed": acceptance._validate_capacity({"raw": baseline}),
        "absent_fairness_passed": acceptance._validate_capacity({"raw": absent}),
    }


def session_boundary_state() -> dict[str, object]:
    from moss_transcribe_diarize.phase2_acceptance_external import FixedAccountCampaign

    sessions = {"b": "valid", "b_peer": "valid", "revoked_probe": "valid"}
    sessions["revoked_probe"] = "revoked"  # G1 invalid/revoked authority probe.
    source = inspect.getsource(FixedAccountCampaign.audio_durability_download)
    selected = "revoked_probe" if "self.revoked_probe.request(" in source else "b_peer"
    current_audio_probe = sessions[selected]
    sessions["b"] = sessions["b_peer"] = "revoked"  # Later Account revoke.
    return {
        "selected_g5_probe": selected,
        "g5_current_probe_status": 200 if current_audio_probe == "valid" else 401,
        "later_account_revoke_status": dict(sessions),
    }


def denominator_projection_state() -> dict[str, object]:
    projection = getattr(acceptance, "external_denominator_projection", None)
    if projection is None:
        return {"available": False}
    measured = projection(
        {
            "predicates": [
                {
                    "id": "cross_owner_matrix",
                    "raw": {"cases": [{"id": f"action-{index}"} for index in range(15)]},
                },
                {"id": "four_session_capacity", "raw": {"session_observations": [{}, {}, {}, {}]}},
                {"id": "eight_session_overload", "raw": {"session_observations": [{} for _ in range(8)]}},
                {
                    "id": "quality_corpus",
                    "raw": {
                        "per_case": [
                            {"windows": 11 if index < 2 else 10}
                            for index in range(12)
                        ],
                        "windows": 122,
                    },
                },
            ]
        }
    )
    return {
        "available": True,
        **{name: counts["collected"] for name, counts in measured.items()},
    }


def missing_release_rehearsal(root: Path) -> dict[str, object]:
    from moss_transcribe_diarize.phase2_cutover_rehearsal import rehearse

    root.mkdir()
    fixture = root / "phase1.json"
    fixture.write_text(
        json.dumps(
            {
                "schema": "moss-isolated-cutover-fixture.v2",
                "service_identity": "phase1",
                "runtime_views": [
                    {"name": name, "entrants": 0, "active_live": 0, "active_jobs": 0, "queued_jobs": 0}
                    for name in ("studio", "live")
                ],
                "snapshot_files": {"state/meeting.json": "{}\n"},
            }
        ),
        encoding="utf-8",
    )
    candidate = root / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema": "moss-account-candidate.v1",
                "activation_state": "staged_inert",
                "release": str(root / "missing-release"),
            }
        ),
        encoding="utf-8",
    )
    try:
        result = rehearse(original_fixture=fixture, candidate_manifest=candidate)
    except (OSError, ValueError, RuntimeError) as exc:
        return {"missing_release_refused": True, "failure": type(exc).__name__}
    return {"missing_release_refused": False, "passed": result.get("passed")}


def operator_cli_evidence_state() -> dict[str, object]:
    raw = {
        "socket_mode": "0600",
        "tcp_admin_surfaces": 0,
        "forbidden_content_matches": 0,
        "count_mismatches": 0,
        "interrupt_probe": {
            "admitted_work_observed": True,
            "command_interrupted": True,
            "durable_interrupted": True,
            "transcript_unchanged": True,
            "target_active_after": 0,
            "queue_depth_after": 0,
            "queued_item_started_events": 0,
            "admitted_item_processed_events": 0,
            "queued_item_discarded_events": 1,
            "audio_partial_playable": True,
            "late_frame_status": 409,
        },
    }
    return {
        "missing_cli_surfaces_passed": acceptance._validate_raw_predicate(
            "operator_control",
            {"raw": raw},
            candidate_sha="a" * 40,
            candidate_tree="b" * 40,
            uv_lock_sha256="c" * 64,
            fixtures={},
            wheel_record_projection_sha256="d" * 64,
            dependency_projection_sha256="e" * 64,
        )
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
        root = Path(directory)
        attempt = root / "attempt"
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
        rehearsal = rehearse_cutover(root / "rehearsal")
        audio_oracle = production_audio_oracle(root / "audio-oracle")
        output_entry = valid_output_enters_attempt(root / "output-entry")
        missing_release = missing_release_rehearsal(root / "missing-release-rehearsal")

    fairness = fairness_false_pass()
    session_boundaries = session_boundary_state()
    denominators = denominator_projection_state()
    operator_cli = operator_cli_evidence_state()

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
                {
                    "name": "candidate_output_identity",
                    "boundary": "the canonical git_sha selects the one legal attempt directory; it grants no runtime authority",
                    "irreducible": "without one candidate key, a valid invocation can fail before evidence or target another commit",
                },
                {
                    "name": "measured_fairness",
                    "boundary": "queued, started, and processed lifecycle events establish dispatch skew only during real joint readiness",
                    "irreducible": "zero skew without a contended dispatch is missing evidence, not fairness",
                },
                {
                    "name": "disposable_revoked_session",
                    "boundary": "one already-revoked Sign-in session proves G5's 401 without consuming later Account-revoke peers",
                    "irreducible": "one session cannot be both valid for a later revoke and already revoked for the earlier audio check",
                },
                {
                    "name": "campaign_unit_denominators",
                    "boundary": "terminal evidence reports ruled actions, capacity sessions, quality sessions, and windows in addition to predicate totals",
                    "irreducible": "one predicate sample cannot prove the 15/4/8/12/122 executed units",
                },
                {
                    "name": "mechanical_cutover_rehearsal",
                    "boundary": "an isolated host performs real block, drain, snapshot, candidate verification, pointer activation, forced failure, and whole restore; it never admits production",
                    "irreducible": "step labels and a dangling symlink do not prove install or rollback tooling",
                },
                {
                    "name": "operator_cli_projection",
                    "boundary": "installed mtd-admin human and JSON output cross the same exact allowlist as the UDS status",
                    "irreducible": "a direct socket read does not prove the required human or machine product surfaces",
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
                "a valid exact-SHA output reaches the exclusive attempt bundle",
                "capacity cannot pass without measured canonical contention",
                "G5 revoked authority does not consume the later G2 Account-revoke sessions",
                "terminal verdict exposes 15 actions, 4 and 8 capacity sessions, and 12 sessions/122 windows",
                "cutover rehearsal rejects a missing candidate release and restores actual isolated host bytes",
                "both mtd-admin status surfaces match the exact operator allowlist",
            ],
            "assumptions_unknowns": [
                "real OAuth, deployed campaigns, TLS, rollback host state, and production canary are externally unmeasured",
                "the committed external campaigns remain unqualified until their real OAuth, host, and speech prerequisites are measured",
            ],
            "falsifier": "any dirty/wrong-runtime/wrong-SHA/missing/raw-false case passes, a valid exact output fails before its bundle, absent contention passes G4, a valid peer is called revoked, 15/4/8/12/122 disappear, a missing release rehearses successfully, mtd-admin is unexercised, a failed artifact can be replaced, G7 becomes claimed, or equal accepted PCM produces different archive bytes/metadata",
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
                {
                    "tool": "production acceptance entry and reducers",
                    "necessary": "the confirmed failures are exact release-command and false-pass behavior, not an abstract model",
                    "decision_change": "KeyError before AttemptBundle or acceptance of absent fairness/operator evidence rejects the current production seams",
                },
                {
                    "tool": "isolated filesystem cutover host",
                    "necessary": "block/install/restore mechanics require real paths and bytes while production admission remains forbidden",
                    "decision_change": "accepting a missing release or failing exact restore rejects the rehearsal tooling",
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
        "candidate_output_entry": output_entry,
        "capacity_fairness": fairness,
        "session_boundaries": session_boundaries,
        "campaign_denominators": denominators,
        "missing_release_rehearsal": missing_release,
        "operator_cli_projection": operator_cli,
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
        output_entry["reached_attempt_bundle"] is True,
        fairness == {"baseline_passed": True, "absent_fairness_passed": False},
        session_boundaries["selected_g5_probe"] == "revoked_probe",
        session_boundaries["g5_current_probe_status"] == 401,
        denominators
        == {
            "available": True,
            "cross_owner_actions": 15,
            "four_session_capacity": 4,
            "eight_session_overload": 8,
            "quality_sessions": 12,
            "quality_windows": 122,
        },
        missing_release["missing_release_refused"] is True,
        operator_cli["missing_cli_surfaces_passed"] is False,
    ]
    verdict = "PASS" if all(assertions) else "FAIL"
    print(json.dumps({"assertions_passed": sum(assertions), "assertions_total": len(assertions), "verdict": verdict}))
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
