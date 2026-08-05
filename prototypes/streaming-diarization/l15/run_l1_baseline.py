#!/usr/bin/env python3
"""Run the calibrated A2 L1 instrument on the frozen L1.5 dev/validation split."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
BLOCKED_PROMISE = "<promise>BLOCKED</promise>"


class BaselineError(RuntimeError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def semantic_sha256(payload: object) -> str:
    encoded = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def resolve(path_value: object) -> Path:
    path = Path(str(path_value))
    return path if path.is_absolute() else REPO / path


def load_a2_instrument(spec: dict[str, Any]) -> ModuleType:
    binding = spec["a2_instrument"]
    path = resolve(binding["path"])
    actual = sha256_file(path)
    if actual != binding["sha256"]:
        raise BaselineError("l15_a2_instrument_hash_mismatch", actual)
    product_diff = subprocess.run(
        [
            "git",
            "-C",
            str(REPO),
            "diff",
            "--quiet",
            spec["production_source_commit"],
            "HEAD",
            "--",
            "moss_transcribe_diarize",
        ],
        check=False,
    )
    if product_diff.returncode != 0:
        raise BaselineError("l15_product_tree_drift", spec["production_source_commit"])
    sys.path.insert(0, str(path.parent))
    module_spec = importlib.util.spec_from_file_location("l15_calibrated_a2", path)
    if module_spec is None or module_spec.loader is None:
        raise BaselineError("l15_a2_instrument_import_failed", str(path))
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    bindings = module.production_bindings()
    if bindings["sweep"] != "moss_transcribe_diarize.app.live_identity_sweep.sweep":
        raise BaselineError("l15_sweep_binding_mismatch", bindings["sweep"])
    return module


def percentile_type7(values: list[float], percentile: float) -> float:
    if not values:
        raise BaselineError("l15_percentile_empty", str(percentile))
    if percentile < 0 or percentile > 100:
        raise BaselineError("l15_percentile_invalid", str(percentile))
    ordered = sorted(float(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * percentile / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def select_cases(
    split: dict[str, Any], requested_ids: list[str]
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for group, cases in split["groups"].items():
        for source in cases:
            case = dict(source)
            case["split"] = group
            by_id[case["case_id"]] = case
    selected = []
    for case_id in requested_ids:
        case = by_id.get(case_id)
        if case is None:
            raise BaselineError("l15_l1_case_unknown", case_id)
        if case["split"] == "blind_holdout":
            raise BaselineError("l15_l1_holdout_sealed", case_id)
        if case["split"] not in {"development", "validation"}:
            raise BaselineError("l15_l1_split_invalid", f"{case_id}:{case['split']}")
        selected.append(case)
    return selected


def _validate_hash_binding(binding: dict[str, Any], code: str) -> Path:
    path = resolve(binding["path"])
    if not path.is_file():
        raise BaselineError(f"{code}_missing", str(path))
    actual = sha256_file(path)
    if actual != binding["sha256"]:
        raise BaselineError(f"{code}_hash_mismatch", actual)
    return path


def validate_inputs(
    spec: dict[str, Any], split: dict[str, Any], selected: list[dict[str, Any]], instrument: ModuleType
) -> tuple[dict[str, Any], dict[str, Any]]:
    corpus_path = _validate_hash_binding(spec["corpus_manifest"], "l15_corpus")
    split_path = _validate_hash_binding(spec["split_manifest"], "l15_split")
    procedure_path = _validate_hash_binding(spec["holdout_procedure"], "l15_procedure")
    model_path = _validate_hash_binding(spec["model_manifest"], "l15_model_manifest")
    _validate_hash_binding(spec["cache_rebuild_spec"], "l15_cache_spec")
    if split_path != HERE / "split-manifest.json":
        raise BaselineError("l15_split_path_mismatch", str(split_path))
    requested = [case["case_id"] for case in selected]
    if requested != spec["case_ids"] or len(selected) != spec["expected_case_count"]:
        raise BaselineError("l15_l1_case_scope_mismatch", json.dumps(requested))
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    corpus_by_id = {case["case_id"]: case for case in corpus["cases"]}
    for case in selected:
        source = corpus_by_id.get(case["case_id"])
        if source is None or not source.get("acceptance_eligible"):
            raise BaselineError("l15_l1_case_not_eligible", case["case_id"])
        for field in (
            "audio_path",
            "audio_sha256",
            "duration_seconds",
            "reference_path",
            "reference_sha256",
            "vector_cache_path",
            "vector_cache_sha256",
        ):
            if case[field] != source[field]:
                raise BaselineError("l15_split_corpus_case_drift", f"{case['case_id']}:{field}")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    compat_spec = {
        "a5_holdout_procedure_path": spec["holdout_procedure"]["path"],
        "a5_holdout_procedure_sha256": spec["holdout_procedure"]["sha256"],
        "cache_rebuild_spec_path": spec["cache_rebuild_spec"]["path"],
        "cache_rebuild_spec_sha256": spec["cache_rebuild_spec"]["sha256"],
        "case_ids": spec["case_ids"],
        "corpus_manifest_sha256": spec["corpus_manifest"]["sha256"],
        "expected_case_count": spec["expected_case_count"],
        "production_config": spec["production_config"],
        "source_commit": spec["production_source_commit"],
    }
    a2_provenance = instrument.validate_control_inputs(
        compat_spec,
        corpus,
        selected,
        model,
        corpus_manifest=corpus_path,
    )
    procedure = json.loads(procedure_path.read_text(encoding="utf-8"))
    missing_holdout_files = []
    present_holdout_files = []
    for case in split["groups"]["blind_holdout"]:
        for label in ("audio", "reference", "vector_cache"):
            path = resolve(case[f"{label}_path"])
            (present_holdout_files if path.exists() else missing_holdout_files).append(
                f"{case['case_id']}:{label}"
            )
    if present_holdout_files:
        raise BaselineError(
            "l15_holdout_input_present_before_open", ",".join(present_holdout_files)
        )
    return model, {
        "a2_instrument_sha256": spec["a2_instrument"]["sha256"],
        "a2_production_bindings": a2_provenance["production_bindings"],
        "cache_rebuild_spec_sha256": spec["cache_rebuild_spec"]["sha256"],
        "corpus_manifest_sha256": spec["corpus_manifest"]["sha256"],
        "holdout_files_absent": missing_holdout_files,
        "holdout_opened": False,
        "holdout_procedure_sha256": spec["holdout_procedure"]["sha256"],
        "model_asset_sha256": model["asset"]["sha256"],
        "model_manifest_sha256": spec["model_manifest"]["sha256"],
        "procedure_l1_runs_per_case": procedure["rules"]["l1_runs_per_case"],
        "production_source_commit": spec["production_source_commit"],
        "split_manifest_sha256": spec["split_manifest"]["sha256"],
    }


def timed_replay(
    instrument: ModuleType, case: dict[str, Any], config: dict[str, Any], *, measure_sweep: bool
) -> tuple[dict[str, Any], list[float]]:
    if not measure_sweep:
        return instrument.replay_case(case, config), []
    target_code = instrument.sweep.__code__
    starts: dict[int, float] = {}
    durations: list[float] = []

    def profile(frame: Any, event: str, _arg: Any) -> None:
        if frame.f_code is not target_code:
            return
        key = id(frame)
        if event == "call":
            starts[key] = time.perf_counter()
        elif event in {"return", "exception"}:
            started = starts.pop(key, None)
            if started is not None:
                durations.append(time.perf_counter() - started)

    previous = sys.getprofile()
    sys.setprofile(profile)
    try:
        result = instrument.replay_case(case, config)
    finally:
        sys.setprofile(previous)
    return result, durations


def write_json(path: Path, payload: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sha256_file(path)


def run_baseline(
    spec: dict[str, Any], selected: list[dict[str, Any]], provenance: dict[str, Any],
    instrument: ModuleType, *, evidence_dir: Path
) -> tuple[dict[str, Any], str]:
    run_count = int(spec["repeatability"]["runs_per_case"])
    timing_ids = set(spec["sweep_timing"]["case_ids"])
    cases = []
    failures: list[str] = []
    all_timing: dict[str, list[float]] = {case_id: [] for case_id in timing_ids}
    transcript = [
        f"L1.a calibrated baseline scope={len(selected)} dev/validation holdout=SEALED",
        f"a2_instrument={provenance['a2_instrument_sha256']}",
    ]
    for case in selected:
        runs = []
        for run_index in range(1, run_count + 1):
            result, sweep_times = timed_replay(
                instrument,
                case,
                spec["production_config"],
                measure_sweep=case["case_id"] in timing_ids,
            )
            semantic_hash = semantic_sha256(result)
            timing = {
                "call_count": len(sweep_times),
                "p95_seconds": percentile_type7(sweep_times, 95) if sweep_times else None,
                "samples_seconds": sweep_times,
                "total_seconds": sum(sweep_times),
            }
            all_timing.get(case["case_id"], []).extend(sweep_times)
            wrapper = {
                "case_id": case["case_id"],
                "result": result,
                "run_index": run_index,
                "semantic_sha256": semantic_hash,
                "sweep_wall_time": timing,
            }
            path = evidence_dir / "runs" / f"l15-l1-{case['case_id']}-run{run_index}.json"
            file_hash = write_json(path, wrapper)
            runs.append(
                {
                    "path": path.relative_to(REPO).as_posix(),
                    "result_sha256": file_hash,
                    "run_index": run_index,
                    "semantic_sha256": semantic_hash,
                    "sweep_call_count": len(sweep_times),
                    "sweep_p95_seconds": timing["p95_seconds"],
                }
            )
        deterministic = len({run["semantic_sha256"] for run in runs}) == 1
        if not deterministic:
            failures.append(f"l15_l1_repeatability_failed:{case['case_id']}")
        first = json.loads(resolve(runs[0]["path"]).read_text(encoding="utf-8"))["result"]
        cases.append(
            {
                "case_id": case["case_id"],
                "changed_duration_fraction": first["changed_duration_fraction"],
                "deterministic": deterministic,
                "metrics": first["metrics"],
                "runs": runs,
                "split": case["split"],
            }
        )
        transcript.append(
            f"{'PASS' if deterministic else 'FAIL'} {case['case_id']} "
            f"split={case['split']} accuracy={first['metrics']['speaker_accuracy']:.6f} "
            f"der={first['metrics']['diarization_error_rate']:.6f} repeat={runs[0]['semantic_sha256']}"
        )
    gate = spec["accepted_alphabet_gate"]
    alphabet = next(case for case in cases if case["case_id"] == gate["case_id"])
    alphabet_result = instrument.evaluate_alphabet_gate(
        alphabet["metrics"]["speaker_accuracy"], gate
    )
    if not alphabet_result["passed"]:
        failures.append("l15_l1_alphabet_anchor_failed")
    transcript.append(
        f"{'PASS' if alphabet_result['passed'] else 'FAIL'} accepted_alphabet "
        f"actual={alphabet_result['actual_speaker_accuracy']:.6f} "
        f"deltas={alphabet_result['absolute_deltas']} tolerance={gate['absolute_tolerance']:.6f}"
    )
    timing_summary = {}
    for case_id, values in all_timing.items():
        timing_summary[case_id] = {
            "call_count": len(values),
            "p95_seconds": percentile_type7(values, 95),
            "percentile_method": spec["sweep_timing"]["percentile_method"],
            "runs": run_count,
            "samples_seconds": values,
            "total_seconds": sum(values),
        }
        transcript.append(
            f"PASS sweep_timing {case_id} calls={len(values)} "
            f"p95_seconds={timing_summary[case_id]['p95_seconds']:.9f}"
        )
    overall = "PASS" if not failures else "FAIL"
    transcript.append(f"RESULT {overall} failures={','.join(failures) if failures else 'none'}")
    summary = {
        "accepted_alphabet_gate": alphabet_result,
        "case_count": len(cases),
        "cases": cases,
        "environment": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform": platform.platform(),
            "python": sys.version,
            "python_executable": sys.executable,
        },
        "failures": failures,
        "holdout": {
            "case_ids": [case["case_id"] for case in json.loads((HERE / "split-manifest.json").read_text())["groups"]["blind_holdout"]],
            "opened": False,
            "status": "SEALED_UNTIL_POST_FREEZE_OPENING",
        },
        "overall": overall,
        "provenance": provenance,
        "repeatability": spec["repeatability"],
        "schema": "moss-l15-l1-baseline-results.v1",
        "sweep_compute_baseline": timing_summary,
    }
    return summary, "\n".join(transcript) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, default=HERE / "l1-baseline-spec.json")
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--transcript-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    split_path = resolve(spec["split_manifest"]["path"])
    split = json.loads(split_path.read_text(encoding="utf-8"))
    requested = args.case_id or list(spec["case_ids"])
    try:
        selected = select_cases(split, requested)
        instrument = load_a2_instrument(spec)
        _model, provenance = validate_inputs(spec, split, selected, instrument)
        provenance.update(
            {
                "runner_sha256": sha256_file(Path(__file__)),
                "spec_sha256": sha256_file(args.spec),
            }
        )
        if args.preflight_only:
            print(json.dumps({"case_ids": requested, "holdout": "SEALED", "overall": "PASS"}, sort_keys=True))
            return 0
        if args.evidence_dir is None or args.json_output is None or args.transcript_output is None:
            raise BaselineError("l15_l1_evidence_paths_required", "use all output arguments")
        summary, transcript = run_baseline(
            spec,
            selected,
            provenance,
            instrument,
            evidence_dir=resolve(args.evidence_dir),
        )
    except (BaselineError, Exception) as exc:
        if isinstance(exc, BaselineError):
            code, detail = exc.code, exc.detail
        else:
            code, detail = "l15_l1_unexpected_failure", f"{type(exc).__name__}: {exc}"
        if args.preflight_only or args.json_output is None or args.transcript_output is None:
            print(f"BLOCKED {code}: {detail}")
            print(BLOCKED_PROMISE)
            return 2
        summary = {"detail": detail, "error": code, "overall": "FAIL"}
        transcript = f"FAIL {code}: {detail}\n"
    json_output = resolve(args.json_output)
    transcript_output = resolve(args.transcript_output)
    write_json(json_output, summary)
    transcript_output.parent.mkdir(parents=True, exist_ok=True)
    transcript_output.write_text(transcript, encoding="utf-8")
    print(transcript, end="")
    return 0 if summary["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
