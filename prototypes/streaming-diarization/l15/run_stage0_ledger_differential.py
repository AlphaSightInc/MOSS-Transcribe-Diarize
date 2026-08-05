#!/usr/bin/env python3
"""Run the immutable Stage-0 A5 ledger proposal over L1.5 D8-safe dev units."""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

from runtime_fixture import sha256_file
from runtime_l1 import decision_units, load_runtime_case


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
STAGE0_REPO = Path(
    "/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-l2-stage0"
)
OWNING_COMMIT = "a16c6d811031cac826878200256af0b69224add8"
STAGE0_ROOT = "prototypes/streaming-diarization/l2-stage0"
ENGINE_SHA256 = "fbed07c2a06efee9f1efab24000ae3e7c7f083761fa21b5ab544a7afce538467"
FAMILY_SHA256 = "280041b25865c0ce912ab3d05afdf8636561296723832deadeb6e328ea7b7a0f"
F1_DECISIONS = HERE / "evidence/f1/f1-dev-decisions.json"
F1_DECISIONS_SHA256 = "a47d94f464213ea045461adb300624c79be99bb413fb65bf514f66d36d0dc6f1"
RUNTIME_MANIFEST = HERE / "runtime-input-manifest.json"
RUNTIME_MANIFEST_SHA256 = "886ce7a6b53f1f55c1966753b8e691113c074fee11bd3b4fdd6e650d0712209e"
DEFAULT_OUTPUT = (
    HERE / "evidence/f1-stage0-ledger-differential/stage0-ledger-decisions.json"
)


@dataclass(frozen=True, slots=True)
class LedgerUnitAdapter:
    """Exact fields read by Stage-0 propose_ledger_only; preserves L1.5 seed values."""

    span_id: int
    local_speaker: str
    current_speaker: str | None
    duration_seconds: float
    vector: tuple[float, ...] | None


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def semantic_sha256(payload: object) -> str:
    return sha256_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def read_owning_blob(name: str) -> bytes:
    if name not in {"candidate_engine.py", "a5-dev-candidate-family-v4.json"}:
        raise RuntimeError(f"stage0_blob_not_allowlisted:{name}")
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(STAGE0_REPO),
            "show",
            f"{OWNING_COMMIT}:{STAGE0_ROOT}/{name}",
        ],
        check=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout


def ledger_unit_read_set(engine_bytes: bytes) -> list[str]:
    tree = ast.parse(engine_bytes, filename="candidate_engine.py")
    selected = {
        "propose_ledger_only",
        "_speaker_references",
        "_finalize_proposals",
        "_map_clusters",
        "_normalize",
    }
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in selected
    ]
    if {node.name for node in functions} != selected:
        raise RuntimeError("stage0_ledger_read_set_function_missing")
    return sorted(
        {
            node.attr
            for function in functions
            for node in ast.walk(function)
            if isinstance(node, ast.Attribute)
        }
    )


def load_stage0_engine() -> tuple[Any, dict[str, object]]:
    engine_bytes = read_owning_blob("candidate_engine.py")
    family_bytes = read_owning_blob("a5-dev-candidate-family-v4.json")
    if sha256_bytes(engine_bytes) != ENGINE_SHA256:
        raise RuntimeError("stage0_candidate_engine_hash_drift")
    if sha256_bytes(family_bytes) != FAMILY_SHA256:
        raise RuntimeError("stage0_candidate_family_hash_drift")
    with tempfile.TemporaryDirectory(prefix="moss-stage0-ledger-") as directory:
        engine_path = Path(directory) / "candidate_engine.py"
        engine_path.write_bytes(engine_bytes)
        spec = importlib.util.spec_from_file_location(
            "stage0_candidate_engine_a16c6d8", engine_path
        )
        if spec is None or spec.loader is None:
            raise RuntimeError("stage0_candidate_engine_import_spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    family = json.loads(family_bytes)
    read_set = ledger_unit_read_set(engine_bytes)
    forbidden_geometry = {"intervals", "span_start", "span_end"} & set(read_set)
    if forbidden_geometry:
        raise RuntimeError(f"stage0_ledger_reads_interval_geometry:{sorted(forbidden_geometry)}")
    module._l15_family_payload = family  # diagnosis-only carrier; source bytes unchanged
    return module, {
        "owning_commit": OWNING_COMMIT,
        "candidate_engine_path": f"{STAGE0_ROOT}/candidate_engine.py",
        "candidate_engine_sha256": ENGINE_SHA256,
        "candidate_family_path": f"{STAGE0_ROOT}/a5-dev-candidate-family-v4.json",
        "candidate_family_sha256": FAMILY_SHA256,
        "stage0_worktree": str(STAGE0_REPO),
        "stage0_worktree_read_only": True,
        "ledger_helper_attribute_read_set": read_set,
    }


def _runtime_units(module: Any, runtime: dict[str, Any], l1: dict[str, Any]) -> tuple[Any, ...]:
    del module
    units = decision_units(runtime, l1)
    return tuple(
        LedgerUnitAdapter(
            span_id=int(unit["span_id"]),
            local_speaker=str(unit["local_speaker"]),
            current_speaker=(
                None if unit["current_speaker"] is None else str(unit["current_speaker"])
            ),
            duration_seconds=float(unit["duration_seconds"]),
            vector=(
                None
                if unit["vector"] is None
                else tuple(float(value) for value in unit["vector"])
            ),
        )
        for unit in units
    )


def _proposal_payload(proposal: Any) -> dict[str, object]:
    return {
        "revision": proposal.revision.to_dict(),
        "correction_evidence": list(proposal.correction_evidence),
        "changed_duration_fraction": proposal.changed_duration_fraction,
        "trace": proposal.trace,
    }


def _apply_proposal(units: tuple[Any, ...], l1_labels: list[str | None], proposal: Any) -> list[str | None]:
    labels = list(l1_labels)
    by_address = {
        (int(unit.span_id), str(unit.local_speaker)): index
        for index, unit in enumerate(units)
    }
    if len(by_address) != len(units):
        raise RuntimeError("stage0_ledger_duplicate_runtime_address")
    for correction in proposal.revision.corrections:
        address = (int(correction.span_id), str(correction.local_speaker))
        if address not in by_address:
            raise RuntimeError(f"stage0_ledger_unknown_address:{address}")
        index = by_address[address]
        if labels[index] != correction.previous_speaker:
            raise RuntimeError(f"stage0_ledger_previous_label_drift:{address}")
        labels[index] = correction.canonical_speaker
    return labels


def main(output: Path) -> int:
    if output.exists():
        raise RuntimeError(f"stage0_ledger_output_exists:{output}")
    if sha256_file(F1_DECISIONS) != F1_DECISIONS_SHA256:
        raise RuntimeError("stage0_ledger_f1_decisions_hash_drift")
    if sha256_file(RUNTIME_MANIFEST) != RUNTIME_MANIFEST_SHA256:
        raise RuntimeError("stage0_ledger_runtime_manifest_hash_drift")
    module, source = load_stage0_engine()
    family = module._l15_family_payload
    config = module.CandidateConfig.from_mapping(family["candidate_family"])
    f1_payload = json.loads(F1_DECISIONS.read_text(encoding="utf-8"))
    cases = []
    for position, case in enumerate(f1_payload["cases"], 1):
        case_id = str(case["case_id"])
        runtime = load_runtime_case(case_id)
        if runtime["split"] != "development":
            raise RuntimeError(f"stage0_ledger_nondev_case:{case_id}")
        units = _runtime_units(module, runtime, case["l1"])
        first = module.propose_ledger_only(units, config)
        second = module.propose_ledger_only(units, config)
        first_payload = _proposal_payload(first)
        second_payload = _proposal_payload(second)
        first_hash = semantic_sha256(first_payload)
        second_hash = semantic_sha256(second_payload)
        if first_hash != second_hash:
            raise RuntimeError(f"stage0_ledger_nondeterministic:{case_id}")
        labels = _apply_proposal(units, case["l1"]["final_unit_labels"], first)
        f1_same_config = next(
            item for item in case["decisions"] if item["config_id"] == "f1-s035-m010-b005"
        )
        case_result = {
            "case_id": case_id,
            "split": runtime["split"],
            "runtime_shape_sha256": runtime["runtime_shape_sha256"],
            "l1_semantic_sha256": case["l1_semantic_sha256"],
            "runtime_unit_count": len(units),
            "eligible_vector_unit_count": sum(unit.vector is not None for unit in units),
            "stage0_proposal": first_payload,
            "stage0_proposal_run1_semantic_sha256": first_hash,
            "stage0_proposal_run2_semantic_sha256": second_hash,
            "stage0_deterministic": True,
            "stage0_final_unit_labels": labels,
            "stage0_final_labels_semantic_sha256": semantic_sha256(labels),
            "f1_same_config": {
                "config_id": f1_same_config["config_id"],
                "proposal_count": f1_same_config["decision"]["trace"]["proposal_count"],
                "accepted_correction_count": f1_same_config["decision"]["trace"][
                    "accepted_correction_count"
                ],
                "final_labels_semantic_sha256": semantic_sha256(
                    f1_same_config["decision"]["final_unit_labels"]
                ),
            },
            "scoring_executed": False,
            "golden_path_opened": False,
            "holdout_opened": False,
        }
        cases.append(case_result)
        print(
            f"DECISION {position}/8 {case_id} eligible={case_result['eligible_vector_unit_count']} "
            f"stage0_proposals={first.trace['candidate_proposal_count']} "
            f"stage0_accepted={first.trace['accepted_correction_count']} "
            f"f1_proposals={case_result['f1_same_config']['proposal_count']}"
        )
    payload = {
        "schema": "moss-l15-stage0-ledger-differential-decisions.v1",
        "diagnosis_step": 2,
        "source": source,
        "adapter": {
            "attempt1_failure": "Stage-0 RuntimeUnit rejected overlapping/non-monotonic L1.5 ASR pieces before output",
            "resolution": "pass an immutable duck-typed unit carrying only the exact attributes read by propose_ledger_only and its helpers",
            "intervals_retimed_or_merged": False,
            "duration_or_vector_changed": False,
            "stage0_source_changed": False,
            "rationale": "interval geometry is not in the sealed ledger helper read-set; bypassing constructor-only validation preserves the identical L1.5 duration/vector/label seed",
        },
        "config": {
            "canonical_min_score": config.canonical_min_score,
            "canonical_min_margin": config.canonical_min_margin,
            "max_changed_duration_fraction": config.max_changed_duration_fraction,
        },
        "inputs": {
            "f1_dev_decisions_path": F1_DECISIONS.relative_to(REPO).as_posix(),
            "f1_dev_decisions_sha256": F1_DECISIONS_SHA256,
            "runtime_manifest_path": RUNTIME_MANIFEST.relative_to(REPO).as_posix(),
            "runtime_manifest_sha256": RUNTIME_MANIFEST_SHA256,
        },
        "case_count": len(cases),
        "cases": cases,
        "candidate_process_imports_scorer": False,
        "scoring_executed": False,
        "golden_path_opened": False,
        "holdout_opened": False,
        "overall": "PASS",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"PASS decisions sha256={sha256_file(output)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    raise SystemExit(main(args.output))
