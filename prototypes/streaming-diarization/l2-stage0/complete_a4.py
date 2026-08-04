#!/usr/bin/env python3
"""Complete A4 under the operator-authorized warm-finalizer Gate F."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
HISTORICAL_BLOCKED_COMMIT = "9b9b3f2209f91dd7e6699bab0add9efb448a1f08"
PINNED = {
    "optimized": "8f7714eaf45504dadbc11cb1afec38fff1503ba8c22ad5112cf374fb0058de1a",
    "blocked_verdict": "5861323145436792f81cbf3e7ac4011e8be93fe2550d4857fa239a89a082da15",
    "blocked_manifest": "1e0125fe94d56a0d8a9eac4bb56893accb59a74025ee8dc5510be6b9a2fe958d",
}
OPERATOR_DECISION = {
    "authorized_date": "2026-08-03",
    "adopted_option": "A",
    "gate_f_definition": (
        "steady-state warm/reused finalizer RTF <= 0.10 and 30-minute wall <= 180 s; "
        "one-time first-finalizer wall may be <= 5 s over steady state"
    ),
    "option_d_server_gpu_embedding": "post-MVP",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _duration_30m(result: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in result["measurements"] if row["duration_seconds"] == 1800]
    if len(rows) != 1:
        raise ValueError("a4_30m_measurement_missing_or_duplicate")
    runs = {run["phase"]: run for run in rows[0]["runs"]}
    expected = {"cached_session_first_finalizer", "cached_session_reused_finalizer"}
    if set(runs) != expected:
        raise ValueError("a4_finalizer_phase_contract_failed")
    return runs


def evaluate_revised_gates(result: dict[str, Any]) -> dict[str, Any]:
    runs = _duration_30m(result)
    first = runs["cached_session_first_finalizer"]
    steady = runs["cached_session_reused_finalizer"]
    overhead = first["wall_seconds"] - steady["wall_seconds"]
    allowance = {
        "first_finalizer_wall_seconds": first["wall_seconds"],
        "steady_state_wall_seconds": steady["wall_seconds"],
        "overhead_seconds": overhead,
        "limit_seconds": 5.0,
        "pass": 0.0 <= overhead <= 5.0,
    }
    old = {gate["gate"]: gate for gate in result["verdict"]["gates"]}
    rtf_pass = steady["rtf"] <= 0.10 and allowance["pass"]
    wall_pass = steady["wall_seconds"] <= 180.0 and allowance["pass"]
    gates = [
        {
            "gate": "finalizer_rtf_30m_steady_state_with_first_allowance",
            "actual": steady["rtf"],
            "limit": 0.10,
            "first_finalizer_allowance_pass": allowance["pass"],
            "pass": rtf_pass,
        },
        {
            "gate": "analysis_30m_steady_state_seconds_with_first_allowance",
            "actual": steady["wall_seconds"],
            "limit": 180.0,
            "first_finalizer_allowance_pass": allowance["pass"],
            "pass": wall_pass,
        },
    ]
    for name in (
        "no_whole_tape_in_memory_read",
        "one_active_finalizer_maximum",
        "new_session_contention_p95_ms_prototype_proxy",
        "stop_ack_p95_over_l2_off_ms_prototype_proxy",
    ):
        gate = dict(old[name])
        gates.append(gate)
    return {"gates": gates, "first_finalizer_allowance": allowance}


def _historical_integrity(path: Path) -> dict[str, Any]:
    relative = path.relative_to(REPO).as_posix()
    current = path.read_bytes()
    committed = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{HISTORICAL_BLOCKED_COMMIT}:{relative}"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    result = {
        "path": relative,
        "current_sha256": sha256_bytes(current),
        "owning_commit_sha256": sha256_bytes(committed),
        "byte_identical_to_owning_commit": current == committed,
    }
    if not result["byte_identical_to_owning_commit"]:
        raise SystemExit(f"historical_blocked_artifact_drift:{relative}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--optimized",
        type=Path,
        default=HERE / "evidence/a4/optimized/a4-runtime-optimized.json",
    )
    parser.add_argument(
        "--blocked-verdict", type=Path, default=HERE / "evidence/a4/a4-verdict.json"
    )
    parser.add_argument(
        "--blocked-manifest", type=Path, default=HERE / "evidence/A4_EVIDENCE.sha256"
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=HERE / "evidence/a4-completion/a4-completion-verdict.json",
    )
    parser.add_argument(
        "--transcript-output",
        type=Path,
        default=HERE / "evidence/a4-completion/a4-completion-verdict.txt",
    )
    parser.add_argument(
        "--integrity-output",
        type=Path,
        default=HERE / "evidence/a4-completion/historical-blocked-integrity.json",
    )
    args = parser.parse_args()

    for label, path in (
        ("optimized", args.optimized),
        ("blocked_verdict", args.blocked_verdict),
        ("blocked_manifest", args.blocked_manifest),
    ):
        actual = sha256(path)
        if actual != PINNED[label]:
            raise SystemExit(f"a4_pinned_artifact_hash_mismatch:{label}:{actual}")

    historical = {
        "owning_commit": HISTORICAL_BLOCKED_COMMIT,
        "artifacts": [
            _historical_integrity(args.blocked_verdict),
            _historical_integrity(args.blocked_manifest),
        ],
    }
    args.integrity_output.write_text(
        json.dumps(historical, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    optimized = json.loads(args.optimized.read_text(encoding="utf-8"))
    revised = evaluate_revised_gates(optimized)
    all_pass = len(revised["gates"]) == 6 and all(gate["pass"] for gate in revised["gates"])
    if not all_pass:
        raise SystemExit("a4_revised_gate_failed")

    result = {
        "schema": "moss-l2-stage0-a4-completion-verdict.v1",
        "status": "COMPLETE",
        "overall": "PASS",
        "campaign_stop": False,
        "a5_authorized": True,
        "operator_decision": OPERATOR_DECISION,
        "revised_gate_table": revised["gates"],
        "first_finalizer_allowance": revised["first_finalizer_allowance"],
        "retired_gate": {
            "definition": "both first and reused finalizers must independently meet RTF <= 0.10 and wall <= 180 s",
            "historical_result": "BLOCKED",
            "retired_on": "2026-08-03",
            "authority": "operator Option A ruling",
        },
        "historical_blocked_evidence": {
            "owning_commit": HISTORICAL_BLOCKED_COMMIT,
            "blocked_verdict_sha256": PINNED["blocked_verdict"],
            "blocked_manifest_sha256": PINNED["blocked_manifest"],
            "optimized_raw_sha256": PINNED["optimized"],
            "immutable_history": True,
            "integrity_proof": str(args.integrity_output.relative_to(REPO)),
            "integrity_proof_sha256": sha256(args.integrity_output),
        },
        "holdout_opened": False,
        "product_or_deployment_changes": False,
    }
    args.json_output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "A4 COMPLETION VERDICT: PASS",
        "operator_option=A",
        "operator_authorized_date=2026-08-03",
        "option_d_server_gpu_embedding=deferred_to_post-MVP",
    ]
    for gate in revised["gates"]:
        lines.append(
            f"gate={gate['gate']} actual={gate['actual']} limit={gate['limit']} verdict=PASS"
        )
    allowance = revised["first_finalizer_allowance"]
    lines.append(
        "first_finalizer_allowance "
        f"first={allowance['first_finalizer_wall_seconds']} "
        f"steady={allowance['steady_state_wall_seconds']} "
        f"overhead={allowance['overhead_seconds']} limit=5.0 verdict=PASS"
    )
    lines.extend(
        [
            f"historical_blocked_commit={HISTORICAL_BLOCKED_COMMIT}",
            f"historical_blocked_verdict_sha256={PINNED['blocked_verdict']}",
            f"historical_blocked_manifest_sha256={PINNED['blocked_manifest']}",
            "historical_blocked_evidence_immutable=true",
            "holdout_opened=false",
        ]
    )
    args.transcript_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"status=COMPLETE gates=6/6 output={args.json_output.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
