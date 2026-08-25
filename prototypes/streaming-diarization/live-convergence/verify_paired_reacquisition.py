"""Check the M0(d) paired re-acquisition gates against the checked-in 2026-08-24 baseline.

Preregistered gates (PRD acceptance M0(d)):

  G1  file arms byte-identical to `prototypes/live-file-gap-baseline-20260824/`
      (every case the baseline holds, trio + the 5-minute case)
  G2  fresh-vs-fresh live transcripts hash-identical (run A vs run B)
  G3  the 5-minute terminal snapshot shows the revisions its `identity_finalized`
      event reports (label_revision_version == identity_revision_version, and > 0
      or the gate is vacuous and says so)
  G4  the measured service is running campaign code, proven from the trace itself:
      `canonical_processed` events carry `canonical_decode_generated_tokens`
      (added in iteration 2), which the deployed pre-campaign build cannot emit
  G5  every run shares one provenance (descriptor + config hash + windowing)

Usage:
  python verify_paired_reacquisition.py --fresh-root /tmp/m0d-<stamp> [--output out.json]

Exit 0 iff every non-vacuous gate passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BASELINE = REPO / "prototypes/live-file-gap-baseline-20260824"


def sha256_bytes(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hypothesis_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def transcript_hash(path: Path) -> str | None:
    """Hash of the published words alone -- the text surface the gate names."""
    rows = hypothesis_rows(path)
    if not rows:
        return None
    joined = "\n".join((row.get("text") or "") for row in rows)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def trace_facts(trace: Path) -> dict:
    """Read the facts G3/G4 need out of one replay trace."""
    facts = {
        "exists": trace.exists(),
        "terminal_label_revision_version": None,
        "identity_finalized_revision_version": None,
        "identity_finalized_count": 0,
        "canonical_processed": 0,
        "canonical_processed_with_token_field": 0,
        "canonical_decode_generated_tokens_total": 0,
    }
    if not trace.exists():
        return facts
    for line in trace.read_text().splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        kind = entry.get("kind")
        if kind == "terminal":
            session = ((entry.get("snapshot") or {}).get("session")) or {}
            facts["terminal_label_revision_version"] = session.get("label_revision_version")
        elif kind == "service_event":
            event = entry.get("event") or {}
            payload = event.get("payload") or {}
            if event.get("kind") == "identity_finalized":
                facts["identity_finalized_count"] += 1
                facts["identity_finalized_revision_version"] = payload.get("identity_revision_version")
            elif event.get("kind") == "canonical_processed":
                facts["canonical_processed"] += 1
                if "canonical_decode_generated_tokens" in payload:
                    facts["canonical_processed_with_token_field"] += 1
                    facts["canonical_decode_generated_tokens_total"] += int(
                        payload.get("canonical_decode_generated_tokens") or 0
                    )
    return facts


def trio_cases() -> list[str]:
    results = json.loads((BASELINE / "trio-60s/results.json").read_text())
    return [case["case_id"] for case in results["cases"]]


def collect(fresh_root: Path) -> dict:
    cases = trio_cases()
    report: dict = {"trio_cases": cases, "arms": {}, "provenance": {}, "traces": {}}

    for run in ("A", "B"):
        trio = fresh_root / f"trio-{run}"
        for case in cases:
            for arm in ("file", "live"):
                path = trio / case / f"{arm}-hypothesis.jsonl"
                report["arms"].setdefault(case, {}).setdefault(arm, {})[run] = {
                    "path": str(path),
                    "sha256": sha256_bytes(path),
                    "transcript_sha256": transcript_hash(path),
                    "rows": len(hypothesis_rows(path)),
                }
            report["traces"].setdefault(case, {})[run] = trace_facts(
                trio / case / "live/run-001/trace.jsonl"
            )
        results_path = trio / "results.json"
        if results_path.exists():
            report["provenance"][f"trio-{run}"] = json.loads(results_path.read_text())["provenance"]

        five = fresh_root / f"keyu5m-{run}"
        for arm in ("file", "live"):
            path = five / f"{arm}-hypothesis.jsonl"
            report["arms"].setdefault("keyu-5m", {}).setdefault(arm, {})[run] = {
                "path": str(path),
                "sha256": sha256_bytes(path),
                "transcript_sha256": transcript_hash(path),
                "rows": len(hypothesis_rows(path)),
            }
        report["traces"].setdefault("keyu-5m", {})[run] = trace_facts(five / "live/run-001/trace.jsonl")

    for case in cases:
        for arm in ("file", "live"):
            path = BASELINE / "trio-60s" / case / f"{arm}-hypothesis.jsonl"
            report["arms"][case][arm]["baseline"] = {
                "path": str(path),
                "sha256": sha256_bytes(path),
                "transcript_sha256": transcript_hash(path),
                "rows": len(hypothesis_rows(path)),
            }
    for arm in ("file", "live"):
        path = BASELINE / "keyu-5m" / f"{arm}-hypothesis.jsonl"
        report["arms"]["keyu-5m"][arm]["baseline"] = {
            "path": str(path),
            "sha256": sha256_bytes(path),
            "transcript_sha256": transcript_hash(path),
            "rows": len(hypothesis_rows(path)),
        }
    report["traces"]["keyu-5m"]["baseline"] = trace_facts(
        BASELINE / "keyu-5m/live/run-001/trace.jsonl"
    )
    return report


def evaluate(report: dict) -> dict:
    cases = report["trio_cases"] + ["keyu-5m"]
    gates: dict[str, dict] = {}

    # G1 -- file arms byte-identical to the checked-in baseline, both fresh runs.
    g1: dict[str, dict] = {}
    for case in cases:
        node = report["arms"][case]["file"]
        base = node["baseline"]["sha256"]
        g1[case] = {
            "baseline_sha256": base,
            "A": node["A"]["sha256"],
            "B": node["B"]["sha256"],
            "A_matches_baseline": base is not None and node["A"]["sha256"] == base,
            "B_matches_baseline": base is not None and node["B"]["sha256"] == base,
            "A_matches_B": node["A"]["sha256"] is not None and node["A"]["sha256"] == node["B"]["sha256"],
        }
    gates["G1_file_byte_identical_to_baseline"] = {
        "pass": all(v["A_matches_baseline"] and v["B_matches_baseline"] for v in g1.values()),
        "per_case": g1,
    }

    # G2 -- fresh-vs-fresh live transcripts hash-identical.
    g2: dict[str, dict] = {}
    for case in cases:
        node = report["arms"][case]["live"]
        g2[case] = {
            "A_transcript_sha256": node["A"]["transcript_sha256"],
            "B_transcript_sha256": node["B"]["transcript_sha256"],
            "transcript_identical": node["A"]["transcript_sha256"] is not None
            and node["A"]["transcript_sha256"] == node["B"]["transcript_sha256"],
            "full_hypothesis_identical": node["A"]["sha256"] is not None
            and node["A"]["sha256"] == node["B"]["sha256"],
            "A_rows": node["A"]["rows"],
            "B_rows": node["B"]["rows"],
        }
    gates["G2_live_transcript_reproducible"] = {
        "pass": all(v["transcript_identical"] for v in g2.values()),
        "per_case": g2,
    }

    # G3 -- the 5-minute terminal snapshot reports the revisions identity_finalized reports.
    g3: dict[str, dict] = {}
    vacuous = []
    for run in ("A", "B", "baseline"):
        facts = report["traces"]["keyu-5m"][run]
        reported = facts["identity_finalized_revision_version"]
        terminal = facts["terminal_label_revision_version"]
        agrees = reported is not None and terminal == reported
        if reported in (None, 0):
            vacuous.append(run)
        g3[run] = {
            "identity_finalized_revision_version": reported,
            "terminal_label_revision_version": terminal,
            "agrees": agrees,
            "nonzero_revisions": bool(reported),
        }
    gates["G3_terminal_snapshot_shows_revisions"] = {
        "pass": g3["A"]["agrees"] and g3["B"]["agrees"] and g3["A"]["nonzero_revisions"],
        "vacuous_runs": vacuous,
        "note": "baseline is expected to DISAGREE (that is the M0a defect this re-acquisition retires)",
        "per_run": g3,
    }

    # G4 -- the measured service ran campaign code (iteration-2 field present in every trace).
    g4: dict[str, dict] = {}
    for case in cases:
        for run in ("A", "B"):
            facts = report["traces"][case][run]
            g4[f"{case}/{run}"] = {
                "canonical_processed": facts["canonical_processed"],
                "with_token_field": facts["canonical_processed_with_token_field"],
                "complete": facts["canonical_processed"] > 0
                and facts["canonical_processed"] == facts["canonical_processed_with_token_field"],
            }
    baseline_facts = report["traces"]["keyu-5m"]["baseline"]
    gates["G4_service_runs_campaign_code"] = {
        "pass": all(v["complete"] for v in g4.values()),
        "baseline_control": {
            "canonical_processed": baseline_facts["canonical_processed"],
            "with_token_field": baseline_facts["canonical_processed_with_token_field"],
            "expected": "0 -- the pre-campaign build cannot emit this field",
        },
        "per_run": g4,
    }

    # G5 -- one provenance across runs.
    provs = report["provenance"]
    keys = ("live_source_revision", "combined_config_hash", "model", "windowing", "decoding", "max_new_tokens")
    distinct = {json.dumps({k: p.get(k) for k in keys}, sort_keys=True) for p in provs.values()}
    baseline_prov = json.loads((BASELINE / "trio-60s/results.json").read_text())["provenance"]
    baseline_key = json.dumps({k: baseline_prov.get(k) for k in keys}, sort_keys=True)
    gates["G5_single_provenance"] = {
        "pass": len(distinct) == 1,
        "runs": list(provs),
        "matches_baseline_provenance": distinct == {baseline_key},
        "provenance": sorted(distinct),
    }
    return gates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh-root", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = collect(args.fresh_root.resolve())
    gates = evaluate(report)
    payload = {"fresh_root": str(args.fresh_root.resolve()), "baseline": str(BASELINE), "gates": gates, "detail": report}
    if args.output:
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    ok = True
    for name, gate in gates.items():
        verdict = "PASS" if gate["pass"] else "FAIL"
        ok = ok and gate["pass"]
        print(f"[{verdict}] {name}")
        for line in json.dumps({k: v for k, v in gate.items() if k != "pass"}, indent=2).splitlines():
            print("    " + line)
    print("ALL GATES PASS" if ok else "GATE FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
