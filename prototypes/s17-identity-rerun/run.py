"""Budgeted S17 identity rerun, with a zero-request planning mode.

Plan only::

  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. python prototypes/s17-identity-rerun/run.py \
    --plan-only --out evidence/round4/labels2/s17-identity-plan.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.qualify.run import (
    LIVE_BENCH_SESSIONS,
    MEASURED_REQUEST_RATE,
    MEASURED_REQUEST_RATE_UNIT,
)


CASES = ("single", "gap", "alternating")
ELIGIBILITY_FLOOR_SAMPLES = 8_000
RAW_SPAN_FIELDS = (
    "record_type",
    "schema_version",
    "meeting_owner",
    "run_owner",
    "source_lane",
    "raw_index",
    "terminal_local_label",
    "start",
    "end",
    "samples",
)
RAW_MAPPING_FIELDS = (
    "record_type",
    "schema_version",
    "meeting_owner",
    "run_owner",
    "source_lane",
    "raw_index",
    "normalized_partition_id",
    "disposition",
)


class IncompleteCaptureReceipt(RuntimeError):
    """The captured evidence cannot support an S17 qualification verdict."""


NORMALIZED_PARTITION_FIELDS = (
    "record_type",
    "schema_version",
    "meeting_owner",
    "run_owner",
    "terminal_local_label",
    "partition_id",
    "member_raw_indexes",
    "start",
    "end",
    "samples",
    "eligibility_floor_samples",
    "eligible",
    "score_by_canonical",
    "margin",
    "decision",
    "published_identity",
)


def _capture_module(*, require_raw: bool) -> tuple[Any, bool]:
    """Refuse before stack startup if this product lacks the capture facility."""

    try:
        from moss_transcribe_diarize.app import terminal_label_capture as capture
    except Exception as exc:
        raise SystemExit(
            "REFUSE: terminal-label capture is unavailable; no decoder request dispatched"
        ) from exc
    required = (
        isinstance(getattr(capture, "ENVIRONMENT_VARIABLE", None), str),
        callable(getattr(capture, "capture_from_environment", None)),
        callable(getattr(capture, "TerminalLabelCapture", None)),
        callable(getattr(capture.TerminalLabelCapture, "record_partitions", None)),
    )
    if not all(required):
        raise SystemExit(
            "REFUSE: terminal-label capture contract is unavailable; no decoder request dispatched"
        )
    raw_ready = callable(
        getattr(capture.TerminalLabelCapture, "record_diagnostics", None)
    )
    if require_raw and not raw_ready:
        raise SystemExit(
            "REFUSE: raw terminal-span capture is unavailable; no decoder request dispatched"
        )
    return capture, raw_ready


def population() -> list[dict[str, Any]]:
    """Use the merged qualification population, rather than restating it locally."""

    sessions = tuple(LIVE_BENCH_SESSIONS["identity_stress"])
    if len(sessions) != len(CASES):
        raise RuntimeError("identity-stress planner population no longer maps to its three cases")
    return [
        {
            "case": case,
            "session_seconds": session_seconds,
            "lanes_per_session": lanes_per_session,
            "lane_seconds": session_seconds * lanes_per_session,
        }
        for case, (session_seconds, lanes_per_session) in zip(CASES, sessions, strict=True)
    ]


def plan() -> dict[str, Any]:
    """Read the measured lane-second rate without importing a decoder client."""

    capture, raw_ready = _capture_module(require_raw=False)
    arms = population()
    lane_seconds = sum(arm["lane_seconds"] for arm in arms)
    return {
        "schema": "moss-r4-s17-identity-plan.v3",
        "population": {
            "cases": list(CASES),
            "arms": arms,
            "sessions": len(arms),
            "lane_seconds": lane_seconds,
            "source": "tools.qualify.run.LIVE_BENCH_SESSIONS['identity_stress']",
        },
        "capture": {
            "status": "READY" if raw_ready else "REQUIRED-BEFORE-RUN",
            "environment_variable": capture.ENVIRONMENT_VARIABLE,
            "schema_version": "moss.terminal-identity-diagnostics.v3",
            "required_observer_method": "TerminalLabelCapture.record_diagnostics",
            "streams": {
                "raw_terminal_spans": {
                    "record_type": "raw_terminal_span",
                    "required_fields": list(RAW_SPAN_FIELDS),
                    "timing": "before resolve_segment_overlaps",
                },
                "raw_to_normalized": {
                    "record_type": "raw_to_normalized",
                    "required_fields": list(RAW_MAPPING_FIELDS),
                },
                "normalized_partitions": {
                    "record_type": "normalized_partition",
                    "required_fields": list(NORMALIZED_PARTITION_FIELDS),
                    "timing": "native partition decision result",
                },
            },
        },
        "measured_request_rate": MEASURED_REQUEST_RATE,
        "measured_request_rate_unit": MEASURED_REQUEST_RATE_UNIT,
        "planned_requests": math.ceil(lane_seconds * MEASURED_REQUEST_RATE),
        "request_derivation": {
            "calculation": (
                f"ceil({lane_seconds:g} lane_seconds * {MEASURED_REQUEST_RATE:g} "
                f"{MEASURED_REQUEST_RATE_UNIT})"
            ),
            "merged_lane_seconds": lane_seconds,
        },
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _lines(path: Path) -> list[str]:
    return [] if not path.exists() else [line for line in path.read_text().splitlines() if line]


def partition_receipt(case: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate and retain the product's separate raw and normalized streams."""

    fields_by_type = {
        "raw_terminal_span": RAW_SPAN_FIELDS,
        "raw_to_normalized": RAW_MAPPING_FIELDS,
        "normalized_partition": NORMALIZED_PARTITION_FIELDS,
    }
    for row in rows:
        record_type = row.get("record_type")
        if record_type not in fields_by_type:
            raise RuntimeError(f"capture receipt has unknown record type for {case}: {record_type}")
        missing = [field for field in fields_by_type[record_type] if field not in row]
        if missing:
            raise IncompleteCaptureReceipt(
                f"INCOMPLETE: capture receipt missing fields for {case}: {', '.join(missing)}"
            )
    raw = [row for row in rows if row["record_type"] == "raw_terminal_span"]
    mapping = [row for row in rows if row["record_type"] == "raw_to_normalized"]
    partitions = [row for row in rows if row["record_type"] == "normalized_partition"]
    if not raw or not mapping or not partitions:
        raise RuntimeError(f"capture receipt lacks one or more required streams for {case}")
    raw_indexes = {int(row["raw_index"]) for row in raw}
    if {int(row["raw_index"]) for row in mapping} != raw_indexes:
        raise RuntimeError(f"capture raw/mapping indexes disagree for {case}")
    partition_ids = {row["partition_id"] for row in partitions}
    if any(
        row["normalized_partition_id"] is not None
        and row["normalized_partition_id"] not in partition_ids
        for row in mapping
    ):
        raise RuntimeError(f"capture mapping names an absent partition for {case}")
    if any(
        int(row["eligibility_floor_samples"]) != ELIGIBILITY_FLOOR_SAMPLES
        for row in partitions
    ):
        raise RuntimeError(f"capture changed the eligibility floor for {case}")
    return {
        "schema": "moss-r4-s17-identity-partition-receipt.v3",
        "case": case,
        "eligibility_floor_samples": ELIGIBILITY_FLOOR_SAMPLES,
        "raw_terminal_spans": raw,
        "raw_to_normalized": mapping,
        "product_partitions": partitions,
    }


def incomplete_capture_receipt(case: str, reason: str) -> dict[str, Any]:
    """Make missing raw custody explicit; it is never an identity FAIL or PASS."""

    return {
        "schema": "moss-r4-s17-identity-partition-receipt.v3",
        "case": case,
        "status": "INCOMPLETE",
        "reason": reason,
    }


def _certificate(out: Path) -> tuple[Path, Path]:
    cert, key = out / "cert.pem", out / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "2", "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
            "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert, key


def _wait_for_stack(base: str, process: subprocess.Popen[bytes]) -> None:
    import ssl

    from tests.e2e.verify_demo_lanes import Client

    client = Client(base, ssl._create_unverified_context())
    for _ in range(120):
        if process.poll() is not None:
            raise RuntimeError("S17 receipt stack exited before readiness")
        try:
            client.call("GET", "/api/live/descriptor")
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("S17 receipt stack did not become ready")


def execute(args: argparse.Namespace, plan_data: dict[str, Any]) -> int:
    capture, _ = _capture_module(require_raw=True)
    if args.budget < plan_data["planned_requests"]:
        raise SystemExit(
            f"REFUSE: budget={args.budget} < planned_requests={plan_data['planned_requests']}; "
            "no decoder request dispatched"
        )
    if not args.decoder_base_url:
        raise SystemExit("REFUSE: --decoder-base-url is required with --run; no decoder request dispatched")
    if args.out.exists():
        raise SystemExit(f"REFUSE: output already exists: {args.out}; no decoder request dispatched")

    args.out.mkdir(parents=True)
    cert, key = _certificate(args.out)
    raw_capture = args.out / "terminal-labels.jsonl"
    stack_command = [
        sys.executable,
        str(ROOT / "prototypes/streaming-diarization/draft-lane/run_local_stack.py"),
        "--state", str(args.out / "state"),
        "--cert", str(cert),
        "--key", str(key),
        "--port", str(args.port),
        "--model", str(args.model),
        "--manifest", str(args.manifest),
        "--vllm-base-url", args.decoder_base_url,
        "--max-requests", str(args.budget),
    ]
    server_env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": ".",
        capture.ENVIRONMENT_VARIABLE: str(raw_capture),
    }
    client_env = dict(server_env)
    del client_env[capture.ENVIRONMENT_VARIABLE]
    process = subprocess.Popen(stack_command, cwd=ROOT, env=server_env)
    base = f"https://127.0.0.1:{args.port}"
    try:
        _wait_for_stack(base, process)
        capture_offset = 0
        for case in CASES:
            case_dir = args.out / case
            identity_dir = case_dir / "identity"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "prototypes/identity-stress/run.py"),
                    case,
                    "--base", base,
                    "--out", str(identity_dir),
                    "--scratch", str(case_dir / "scratch"),
                ],
                cwd=ROOT,
                env=client_env,
                check=True,
            )
            all_lines = _lines(raw_capture)
            case_lines = all_lines[capture_offset:]
            capture_offset = len(all_lines)
            case_rows = [json.loads(line) for line in case_lines]
            case_capture = case_dir / "terminal-labels.jsonl"
            case_capture.parent.mkdir(parents=True, exist_ok=True)
            if case_lines:
                case_capture.write_text("\n".join(case_lines) + "\n", encoding="utf-8")
            try:
                if not case_rows:
                    raise RuntimeError(
                        f"capture emitted no terminal rows for {case}; receipt falsified"
                    )
                receipt = partition_receipt(case, case_rows)
            except RuntimeError as exc:
                _write(
                    case_dir / "partition-receipt.json",
                    incomplete_capture_receipt(case, str(exc)),
                )
                _write(
                    args.out / "run.json",
                    {
                        "schema": "moss-r4-s17-identity-rerun.v3",
                        "status": "INCOMPLETE",
                        "reason": str(exc),
                        "plan": plan_data,
                        "budget": args.budget,
                        "capture": str(raw_capture),
                        "completed_cases": list(CASES[: CASES.index(case)]),
                        "incomplete_case": case,
                    },
                )
                raise SystemExit(2) from exc
            _write(case_dir / "partition-receipt.json", receipt)
        requests = args.out / "state/requests.jsonl"
        if requests.exists():
            shutil.copyfile(requests, args.out / "decoder-requests.jsonl")
        _write(
            args.out / "run.json",
            {
                "schema": "moss-r4-s17-identity-rerun.v3",
                "plan": plan_data,
                "budget": args.budget,
                "capture": str(raw_capture),
                "cases": list(CASES),
            },
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--decoder-base-url")
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--port", type=int, default=18345)
    parser.add_argument(
        "--model",
        type=Path,
        default=Path.home()
        / ".cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/e8681d68e7042738ffca8ac8212bc8fcb1131ab8",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json",
    )
    args = parser.parse_args(argv)
    if args.plan_only == args.run:
        parser.error("choose exactly one of --plan-only or --run")
    plan_data = plan()
    if args.plan_only:
        _write(args.out, plan_data)
        print(json.dumps(plan_data, indent=2))
        return 0
    try:
        return execute(args, plan_data)
    except IncompleteCaptureReceipt as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
