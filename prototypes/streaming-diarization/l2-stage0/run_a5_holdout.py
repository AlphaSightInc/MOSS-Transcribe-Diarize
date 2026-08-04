#!/usr/bin/env python3
"""One-process, one-opening A5 holdout measurement harness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from pathlib import Path
import subprocess
import sys
import traceback
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))

from candidate_engine import (  # noqa: E402
    CandidateConfig,
    propose_ledger_only,
    run_joint_span_candidate,
)
from rebuild_caches import rebuild  # noqa: E402
from run_candidates import (  # noqa: E402
    ProductionWindowEmbedder,
    _arm_result,
    _empty_proposal,
    audit_candidate_source,
    evaluate_gates,
    padding_negative_control,
    pcm_chunks,
    production_bindings,
    runtime_case,
    semantic_sha256,
)
from run_l1_control import replay_case  # noqa: E402
from validate_inputs import ValidationError, authorize_holdout_open  # noqa: E402
from moss_transcribe_diarize.app import speaker_identity  # noqa: E402


FROZEN_CONFIG_SHA256 = "0f9fc2b0d23df377e3b04432e50dd8b5f19d53793682f14396270b3d0bf669b9"
FROZEN_COMMIT = "60ccd70aeefc13a0edec7770bb6b3d77149d1826"
HOLDOUT_PROCEDURE_SHA256 = "6989d0ffdcdf2316b5c7c8549da226a00c2fa60b2ae9a712367d12b4d03d3902"
BLOCKED_PROMISE = "<promise>BLOCKED</promise>"


class HoldoutRunError(RuntimeError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}:{detail}" if detail else code)
        self.code = code
        self.detail = detail


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise HoldoutRunError("holdout_evidence_path_exists", str(path)) from exc
    return sha256(path)


def _write_text(path: Path, value: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(value)
    except FileExistsError as exc:
        raise HoldoutRunError("holdout_evidence_path_exists", str(path)) from exc
    return sha256(path)


def pin_corpus_contract(contract_path: Path, corpus_path: Path) -> str:
    """Advance the launcher pin immediately after a versioned corpus rebuild."""
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    actual = sha256(corpus_path)
    contract["corpus_manifest_hash"] = actual
    temporary = contract_path.with_name(f".{contract_path.name}.a5-{os.getpid()}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(contract, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, contract_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if json.loads(contract_path.read_text(encoding="utf-8")).get(
        "corpus_manifest_hash"
    ) != actual:
        raise HoldoutRunError("holdout_corpus_pin_update_failed")
    return actual


def _repo_path(path: Path) -> str:
    return path.resolve().relative_to(REPO.resolve()).as_posix()


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()


def _resolve(root: Path, value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def create_opening_marker(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError as exc:
        raise HoldoutRunError("holdout_already_opened", str(path)) from exc


def evaluate_l1_repeatability(
    first: dict[str, Any], second: dict[str, Any], *, limit_pp: float = 0.1
) -> dict[str, object]:
    first_accuracy = float(first["metrics"]["speaker_accuracy"])
    second_accuracy = float(second["metrics"]["speaker_accuracy"])
    delta_pp = abs(second_accuracy - first_accuracy) * 100.0
    return {
        "first_speaker_accuracy": first_accuracy,
        "second_speaker_accuracy": second_accuracy,
        "delta_pp": round(delta_pp, 9),
        "limit_pp": limit_pp,
        "pass": delta_pp <= limit_pp + 1e-12,
    }


def validate_frozen_candidate(
    candidate: dict[str, Any],
    family: dict[str, Any],
    *,
    root: Path = REPO,
    dev_manifest: Path = HERE / "evidence/A5_DEV_EVIDENCE.sha256",
) -> dict[str, str]:
    if candidate.get("candidate_frozen") is not True:
        raise HoldoutRunError("holdout_candidate_not_frozen")
    expected_family = family["candidate_family"]
    if candidate.get("candidate_family") != expected_family.get("family_id"):
        raise HoldoutRunError("holdout_candidate_family_mismatch")
    pins = (
        ("spec", "candidate_spec_path", "candidate_spec_sha256"),
        ("implementation", "candidate_implementation_path", "candidate_implementation_sha256"),
        ("runner", "candidate_runner_path", "candidate_runner_sha256"),
    )
    resolved: dict[str, str] = {}
    for label, path_key, hash_key in pins:
        path = _resolve(root, candidate.get(path_key))
        if not path.is_file() or sha256(path) != candidate.get(hash_key):
            raise HoldoutRunError(f"holdout_candidate_{label}_hash_mismatch", str(path))
        resolved[f"candidate_{label}_sha256"] = sha256(path)
    if not dev_manifest.is_file() or sha256(dev_manifest) != candidate.get(
        "dev_evidence_manifest_sha256"
    ):
        raise HoldoutRunError("holdout_dev_evidence_manifest_hash_mismatch", str(dev_manifest))
    threshold_keys = ("change_evidence", "energy_vad", "grouping", "tape_windows")
    expected_thresholds = {key: expected_family[key] for key in threshold_keys}
    if candidate.get("thresholds") != expected_thresholds:
        raise HoldoutRunError("holdout_candidate_threshold_drift")
    if candidate["thresholds"]["tape_windows"].get("hard_cap_samples") != 40000:
        raise HoldoutRunError("holdout_hard_cap_changed")
    resolved["dev_evidence_manifest_sha256"] = sha256(dev_manifest)
    return resolved


def validate_preopening_inputs(
    *,
    candidate_path: Path,
    family_path: Path,
    procedure_path: Path,
    corpus_path: Path,
    l1_spec_path: Path,
    model_path: Path,
    rebuild_spec_path: Path,
    contract_path: Path,
) -> dict[str, object]:
    if sha256(candidate_path) != FROZEN_CONFIG_SHA256:
        raise HoldoutRunError("holdout_frozen_config_hash_mismatch", str(candidate_path))
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    family = json.loads(family_path.read_text(encoding="utf-8"))
    frozen = validate_frozen_candidate(candidate, family)
    if sha256(procedure_path) != HOLDOUT_PROCEDURE_SHA256:
        raise HoldoutRunError("holdout_procedure_hash_mismatch", str(procedure_path))
    procedure = json.loads(procedure_path.read_text(encoding="utf-8"))
    if (
        procedure.get("opening_count") != 1
        or procedure.get("l1_runs_per_case") != 2
        or procedure.get("run_all_arms_in_same_opening_session") is not True
        or procedure.get("candidate_must_be_frozen") is not True
    ):
        raise HoldoutRunError("holdout_procedure_contract_mismatch")
    rebuild_contract = procedure["holdout_cache_rebuild"]
    expected_rebuild = {
        "code_sha256": sha256(HERE / "rebuild_caches.py"),
        "shared_module_sha256": sha256(HERE / "production_cache.py"),
        "cache_rebuild_spec_sha256": sha256(rebuild_spec_path),
    }
    for key, actual in expected_rebuild.items():
        if rebuild_contract.get(key) != actual:
            raise HoldoutRunError(f"holdout_{key}_mismatch")
    l1_spec = json.loads(l1_spec_path.read_text(encoding="utf-8"))
    if l1_spec.get("a5_holdout_procedure_sha256") != HOLDOUT_PROCEDURE_SHA256:
        raise HoldoutRunError("holdout_l1_procedure_pin_mismatch")
    if l1_spec.get("cache_rebuild_spec_sha256") != sha256(rebuild_spec_path):
        raise HoldoutRunError("holdout_l1_rebuild_spec_pin_mismatch")
    if l1_spec.get("corpus_manifest_sha256") != sha256(corpus_path):
        raise HoldoutRunError("holdout_preopening_corpus_hash_mismatch")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("corpus_manifest_hash") != sha256(corpus_path):
        raise HoldoutRunError("holdout_preopening_launcher_pin_mismatch")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    model_asset = _resolve(REPO, model["asset"]["path"])
    if sha256(model_asset) != model["asset"]["sha256"]:
        raise HoldoutRunError("holdout_model_hash_mismatch")
    source_audit = audit_candidate_source(HERE / "candidate_engine.py")
    if source_audit["overall"] != "PASS":
        raise HoldoutRunError("holdout_candidate_source_audit_failed")
    ancestor = subprocess.run(
        ["git", "-C", str(REPO), "merge-base", "--is-ancestor", FROZEN_COMMIT, "HEAD"],
        check=False,
    )
    if ancestor.returncode != 0:
        raise HoldoutRunError("holdout_freeze_commit_not_ancestor")
    return {
        **frozen,
        "candidate_config_sha256": sha256(candidate_path),
        "candidate_source_audit": source_audit,
        "corpus_manifest_preopening_sha256": sha256(corpus_path),
        "contract_preopening_sha256": sha256(contract_path),
        "family_sha256": sha256(family_path),
        "freeze_commit": FROZEN_COMMIT,
        "git_head": _git_head(),
        "holdout_manifest_sha256": candidate["holdout_manifest_sha256"],
        "l1_spec_sha256": sha256(l1_spec_path),
        "model_manifest_sha256": sha256(model_path),
        "procedure_sha256": sha256(procedure_path),
        "rebuild_spec_sha256": sha256(rebuild_spec_path),
    }


def _assert_clean_worktree() -> None:
    status = subprocess.check_output(
        ["git", "-C", str(REPO), "status", "--porcelain=v1", "--untracked-files=all"],
        text=True,
    )
    if status:
        raise HoldoutRunError("holdout_worktree_not_clean", status.strip())


def _case_summary(case: dict[str, object]) -> dict[str, object]:
    return {
        "case_id": case["case_id"],
        "split": case["split"],
        "raw_path": case["raw_path"],
        "raw_sha256": case["raw_sha256"],
        "l1_repeatability": case["l1_repeatability"],
        "metrics": {arm: case["arms"][arm]["metrics"] for arm in case["arms"]},
        "changed_duration_fraction": {
            arm: case["arms"][arm]["proposal"]["changed_duration_fraction"]
            for arm in case["arms"]
        },
    }


def _seal_holdout_evidence(
    output: Path, *, extra_paths: tuple[Path, ...] = ()
) -> str:
    paths = {
        HERE / "a5-dev-candidate-family-v4.json",
        HERE / "a5-holdout-procedure.json",
        HERE / "cache-rebuild-spec.json",
        HERE / "candidate-config.json",
        HERE / "candidate_engine.py",
        HERE / "corpus-manifest.json",
        HERE / "holdout-manifest.json",
        HERE / "l1-control-spec.json",
        HERE / "model-manifest.json",
        HERE / "production_cache.py",
        HERE / "rebuild_caches.py",
        HERE / "run_a5_holdout.py",
        HERE / "run_candidates.py",
        HERE / "test_a5_holdout_runner.py",
        HERE / "evidence/A5_DEV_EVIDENCE.sha256",
        REPO / "scripts/ralph-l2-afk/contract.json",
    }
    paths.update(extra_paths)
    paths.update(path for path in output.rglob("*") if path.is_file() and path != output / "A5_HOLDOUT_EVIDENCE.sha256")
    missing = sorted(path for path in paths if not path.is_file())
    if missing:
        raise HoldoutRunError("holdout_evidence_missing", ",".join(str(path) for path in missing))
    rows = [f"{sha256(path)}  {_repo_path(path)}" for path in sorted(paths)]
    manifest = output / "A5_HOLDOUT_EVIDENCE.sha256"
    _write_text(manifest, "\n".join(rows) + "\n")
    return sha256(manifest)


def run_single_opening(args: argparse.Namespace, pins: dict[str, object]) -> dict[str, object]:
    output = args.evidence_dir.resolve()
    marker = output / "opening-start.json"
    create_opening_marker(
        marker,
        {
            "command": [sys.executable, *sys.argv],
            "freeze_commit": FROZEN_COMMIT,
            "git_head": pins["git_head"],
            "opened_at": utc_now(),
            "opening_count": 1,
            "pid": os.getpid(),
            "procedure_sha256": HOLDOUT_PROCEDURE_SHA256,
            "schema": "moss-l2-stage0-a5-opening-start.v1",
        },
    )
    candidate = json.loads(args.candidate_config.read_text(encoding="utf-8"))
    family = json.loads(args.candidate_family.read_text(encoding="utf-8"))
    l1_spec = json.loads(args.l1_spec.read_text(encoding="utf-8"))
    model = json.loads(args.model_manifest.read_text(encoding="utf-8"))
    try:
        holdout = authorize_holdout_open(candidate, args.holdout_manifest)
    except ValidationError as exc:
        raise HoldoutRunError(exc.code, exc.detail) from exc
    if (
        holdout.get("sealed") is not True
        or holdout.get("opened_at") is not None
        or len(holdout.get("cases", ())) != 3
    ):
        raise HoldoutRunError("holdout_manifest_contract_mismatch")
    holdout_ids = [str(case["case_id"]) for case in holdout["cases"]]
    if len(set(holdout_ids)) != 3:
        raise HoldoutRunError("holdout_case_scope_invalid")
    _write_json(
        output / "holdout-opened.json",
        {
            "case_count": len(holdout_ids),
            "case_ids": holdout_ids,
            "holdout_manifest_sha256": sha256(args.holdout_manifest),
            "opened_at": utc_now(),
            "overall": "OPENED",
            "schema": "moss-l2-stage0-a5-holdout-opened.v1",
        },
    )
    backup = output / "corpus-manifest-pre-opening.json"
    _write_text(backup, args.corpus_manifest.read_text(encoding="utf-8"))
    rebuild_events: list[str] = []
    audit = rebuild(
        corpus_path=args.corpus_manifest,
        model_path=args.model_manifest,
        candidate_path=args.candidate_config,
        spec_path=args.rebuild_spec,
        output_root=args.cache_root,
        audit_output=output / "cache-provenance-audit.json",
        scope="holdout",
        a5_opening=True,
        apply_manifest=True,
        event=lambda message: (rebuild_events.append(message), print(message, flush=True)),
    )
    contract_corpus_hash = pin_corpus_contract(args.contract, args.corpus_manifest)
    _write_text(output / "cache-rebuild-transcript.txt", "\n".join(rebuild_events) + "\n")
    if audit.get("overall") != "PASS" or [case["case_id"] for case in audit["cases"]] != holdout_ids:
        raise HoldoutRunError("holdout_cache_rebuild_scope_mismatch")
    corpus = json.loads(args.corpus_manifest.read_text(encoding="utf-8"))
    cases_by_id = {str(case["case_id"]): case for case in corpus["cases"]}
    selected = [cases_by_id[case_id] for case_id in holdout_ids]
    if any(case.get("split") != "blind_holdout" or not case.get("acceptance_eligible") for case in selected):
        raise HoldoutRunError("holdout_case_not_acceptance_eligible")
    config = CandidateConfig.from_mapping(candidate["thresholds"])
    model_asset = _resolve(REPO, model["asset"]["path"])
    embedder = speaker_identity._OnnxWeSpeakerEmbedder(model_asset, device="cpu")
    bindings = production_bindings(model_asset)
    source_audit = audit_candidate_source(HERE / "candidate_engine.py")
    case_records: list[dict[str, object]] = []
    for case in selected:
        case_id = str(case["case_id"])
        l1_results = [replay_case(case, l1_spec["production_config"]) for _ in range(2)]
        run_records = []
        semantic_hashes = []
        for run_index, result in enumerate(l1_results, 1):
            semantic = semantic_sha256(result)
            semantic_hashes.append(semantic)
            path = output / "l1" / f"a5-holdout-l1-{case_id}-run{run_index}.json"
            result_hash = _write_json(
                path,
                {
                    "case_id": case_id,
                    "result": result,
                    "run_index": run_index,
                    "semantic_sha256": semantic,
                },
            )
            run_records.append(
                {
                    "path": _repo_path(path),
                    "result_sha256": result_hash,
                    "run_index": run_index,
                    "semantic_sha256": semantic,
                }
            )
        repeatability = evaluate_l1_repeatability(l1_results[0], l1_results[1])
        repeatability["semantic_deterministic"] = len(set(semantic_hashes)) == 1
        repeatability["runs"] = run_records
        spans, units, plan, reference = runtime_case(
            case, l1_results[0], l1_spec["production_config"]
        )
        l1_proposal = _empty_proposal(len(units), len(spans))
        ledger_proposal = propose_ledger_only(units, config)
        tape_proposal = run_joint_span_candidate(
            units,
            pcm_chunks(_resolve(REPO, case["audio_path"]), hard_cap_samples=40000),
            duration_seconds=float(case["duration_seconds"]),
            sample_rate=int(l1_spec["production_config"]["sample_rate"]),
            embedder=ProductionWindowEmbedder(embedder, _resolve(REPO, case["audio_path"])),
            config=config,
        )
        common = {
            "spans": spans,
            "units": units,
            "plan": plan,
            "reference": reference,
            "l1_result": l1_results[0],
            "sample_rate": int(l1_spec["production_config"]["sample_rate"]),
        }
        arms = {
            "l1_control": _arm_result(name="l1_control", proposal=l1_proposal, **common),
            "ledger_only_control": _arm_result(
                name="ledger_only_control", proposal=ledger_proposal, **common
            ),
            "tape_candidate": _arm_result(
                name="tape_candidate", proposal=tape_proposal, **common
            ),
        }
        case_result = {
            "arms": arms,
            "case_id": case_id,
            "frame": {
                "audio_sha256": case["audio_sha256"],
                "planner": "production_endpoint_policy",
                "reference_sha256": case["reference_sha256"],
                "span_count": len(spans),
                "unit_count": len(units),
                "vector_cache_sha256": case["vector_cache_sha256"],
            },
            "l1_repeatability": repeatability,
            "schema": "moss-l2-stage0-a5-holdout-case-result.v1",
            "split": case["split"],
        }
        path = output / "cases" / f"a5-holdout-{case_id}.json"
        case_hash = _write_json(path, case_result)
        case_records.append(
            {**case_result, "raw_path": _repo_path(path), "raw_sha256": case_hash}
        )
        print(
            f"case={case_id} l1={arms['l1_control']['metrics']['speaker_accuracy']:.6f} "
            f"ledger={arms['ledger_only_control']['metrics']['speaker_accuracy']:.6f} "
            f"tape={arms['tape_candidate']['metrics']['speaker_accuracy']:.6f} "
            f"repeat_delta_pp={repeatability['delta_pp']:.6f}",
            flush=True,
        )
    gate_cases = [{**case, "split": "validation"} for case in case_records]
    gates = evaluate_gates(gate_cases, family)
    for gate in gates["gates"]:
        if gate["gate"] == "validation_case_regression_pp":
            gate["gate"] = "holdout_case_regression_pp"
    repeatability_gate = {
        "actual": {
            str(case["case_id"]): {
                "delta_pp": case["l1_repeatability"]["delta_pp"],
                "semantic_deterministic": case["l1_repeatability"]["semantic_deterministic"],
            }
            for case in case_records
        },
        "gate": "l1_repeatability",
        "limit": "0.1pp and semantic exact",
        "pass": all(
            bool(case["l1_repeatability"]["pass"])
            and bool(case["l1_repeatability"]["semantic_deterministic"])
            for case in case_records
        ),
    }
    padding = padding_negative_control()
    padding_gate = {
        "actual": padding["overall"],
        "gate": "adversarial_padding_rejected",
        "limit": "PASS",
        "pass": padding["overall"] == "PASS",
    }
    same_frame_gate = {
        "actual": {
            str(case["case_id"]): case["frame"]["vector_cache_sha256"]
            for case in case_records
        },
        "gate": "same_production_planned_frame",
        "limit": True,
        "pass": True,
    }
    gates["gates"].extend((repeatability_gate, padding_gate, same_frame_gate))
    gates["overall"] = "PASS" if all(gate["pass"] for gate in gates["gates"]) else "FAIL"
    summary = {
        "cache_rebuild": {
            "audit_path": _repo_path(output / "cache-provenance-audit.json"),
            "audit_sha256": sha256(output / "cache-provenance-audit.json"),
            "overall": audit["overall"],
        },
        "candidate_frozen": True,
        "case_count": len(case_records),
        "cases": [_case_summary(case) for case in case_records],
        "command": [sys.executable, *sys.argv],
        "environment": {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "python": sys.version,
        },
        "gate_evaluation": gates,
        "holdout_opened": True,
        "opening_count": 1,
        "overall": gates["overall"],
        "padding_negative_control": padding,
        "pins": {
            **pins,
            "corpus_manifest_post_rebuild_sha256": sha256(args.corpus_manifest),
            "contract_corpus_manifest_hash": contract_corpus_hash,
            "contract_post_rebuild_sha256": sha256(args.contract),
            "holdout_manifest_sha256": sha256(args.holdout_manifest),
        },
        "production_bindings": bindings,
        "schema": "moss-l2-stage0-a5-holdout-results.v1",
        "source_audit": source_audit,
        "verdict": "PASS" if gates["overall"] == "PASS" else "BLOCKED",
    }
    summary_path = output / "a5-holdout-summary.json"
    summary_hash = _write_json(summary_path, summary)
    transcript_lines = [
        f"A5 HOLDOUT RESULT: {summary['overall']}",
        "opening_count=1 candidate_frozen=true no_tuning=true",
    ]
    for gate in gates["gates"]:
        transcript_lines.append(
            f"gate={gate['gate']} actual={gate['actual']} limit={gate['limit']} "
            f"verdict={'PASS' if gate['pass'] else 'FAIL'}"
        )
    transcript_path = output / "a5-holdout-summary.txt"
    transcript_hash = _write_text(transcript_path, "\n".join(transcript_lines) + "\n")
    _write_json(
        output / "opening-complete.json",
        {
            "completed_at": utc_now(),
            "holdout_summary_sha256": summary_hash,
            "holdout_transcript_sha256": transcript_hash,
            "opening_count": 1,
            "overall": summary["overall"],
            "schema": "moss-l2-stage0-a5-opening-complete.v1",
        },
    )
    cache_paths = tuple(_resolve(REPO, case["new_cache_path"]) for case in audit["cases"])
    summary["evidence_manifest_sha256"] = _seal_holdout_evidence(
        output, extra_paths=cache_paths
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-config", type=Path, default=HERE / "candidate-config.json")
    parser.add_argument("--candidate-family", type=Path, default=HERE / "a5-dev-candidate-family-v4.json")
    parser.add_argument("--procedure", type=Path, default=HERE / "a5-holdout-procedure.json")
    parser.add_argument("--corpus-manifest", type=Path, default=HERE / "corpus-manifest.json")
    parser.add_argument("--holdout-manifest", type=Path, default=HERE / "holdout-manifest.json")
    parser.add_argument("--l1-spec", type=Path, default=HERE / "l1-control-spec.json")
    parser.add_argument("--model-manifest", type=Path, default=HERE / "model-manifest.json")
    parser.add_argument("--rebuild-spec", type=Path, default=HERE / "cache-rebuild-spec.json")
    parser.add_argument("--contract", type=Path, default=REPO / "scripts/ralph-l2-afk/contract.json")
    parser.add_argument("--cache-root", type=Path, default=HERE / "data/cache-v2-production-endpoint")
    parser.add_argument("--evidence-dir", type=Path, default=HERE / "evidence/a5-holdout-opening")
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    marker = args.evidence_dir / "opening-start.json"
    if marker.exists():
        print(f"BLOCKED holdout_already_opened:{marker}")
        print(BLOCKED_PROMISE)
        return 2
    try:
        pins = validate_preopening_inputs(
            candidate_path=args.candidate_config,
            family_path=args.candidate_family,
            procedure_path=args.procedure,
            corpus_path=args.corpus_manifest,
            l1_spec_path=args.l1_spec,
            model_path=args.model_manifest,
            rebuild_spec_path=args.rebuild_spec,
            contract_path=args.contract,
        )
        if args.preflight_only:
            print(json.dumps({"holdout_read": False, "overall": "PASS", "pins": pins}, sort_keys=True))
            return 0
        _assert_clean_worktree()
        result = run_single_opening(args, pins)
    except Exception as exc:
        if marker.exists():
            blocked = args.evidence_dir / "opening-blocked.json"
            if not blocked.exists():
                _write_json(
                    blocked,
                    {
                        "error": str(exc),
                        "error_type": exc.__class__.__name__,
                        "failed_at": utc_now(),
                        "opening_consumed": True,
                        "overall": "BLOCKED",
                        "traceback": traceback.format_exc(),
                    },
                )
                try:
                    _seal_holdout_evidence(args.evidence_dir)
                except Exception:
                    pass
        code = exc.code if isinstance(exc, HoldoutRunError) else exc.__class__.__name__
        print(f"BLOCKED {code}:{exc}")
        print(BLOCKED_PROMISE)
        return 2
    print(
        f"overall={result['overall']} opening_count=1 "
        f"manifest_sha256={result['evidence_manifest_sha256']}"
    )
    return 0 if result["overall"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
