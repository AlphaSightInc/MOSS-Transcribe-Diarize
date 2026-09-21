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
CAPTURE_FIELDS = (
    "span_index",
    "source_start",
    "source_end",
    "samples",
    "terminal_local_label",
    "partition_id",
    "eligible",
    "score_by_canonical",
    "margin",
    "decision",
    "published_identity",
)


def _capture_module() -> Any:
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
    return capture


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

    capture = _capture_module()
    arms = population()
    lane_seconds = sum(arm["lane_seconds"] for arm in arms)
    return {
        "schema": "moss-r4-s17-identity-plan.v2",
        "population": {
            "cases": list(CASES),
            "arms": arms,
            "sessions": len(arms),
            "lane_seconds": lane_seconds,
            "source": "tools.qualify.run.LIVE_BENCH_SESSIONS['identity_stress']",
        },
        "capture": {
            "status": "AVAILABLE",
            "environment_variable": capture.ENVIRONMENT_VARIABLE,
            "required_fields": list(CAPTURE_FIELDS),
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
    """Group the product-emitted IDs; neither membership nor decisions are re-derived."""

    partitions: dict[str, dict[str, Any]] = {}
    for row in rows:
        missing = [field for field in CAPTURE_FIELDS if field not in row]
        if missing:
            raise RuntimeError(f"capture receipt missing fields for {case}: {', '.join(missing)}")
        partition = partitions.setdefault(
            row["partition_id"],
            {
                "partition_id": row["partition_id"],
                "terminal_local_label": row["terminal_local_label"],
                "score_by_canonical": row["score_by_canonical"],
                "margin": row["margin"],
                "decision": row["decision"],
                "spans": [],
            },
        )
        if any(
            partition[key] != row[key]
            for key in ("terminal_local_label", "score_by_canonical", "margin", "decision")
        ):
            raise RuntimeError(f"capture receipt disagrees within product partition {row['partition_id']}")
        samples = int(row["samples"])
        capture_eligible = row["eligible"]
        partition["spans"].append(
            {
                "span_index": row["span_index"],
                "source_start": row["source_start"],
                "source_end": row["source_end"],
                "eligibility": {
                    "samples": samples,
                    "floor_samples": ELIGIBILITY_FLOOR_SAMPLES,
                    "eligible": samples >= ELIGIBILITY_FLOOR_SAMPLES,
                    "captured_eligible": capture_eligible,
                    "matches_captured": (
                        None if capture_eligible is None
                        else capture_eligible == (samples >= ELIGIBILITY_FLOOR_SAMPLES)
                    ),
                },
                "published_identity": row["published_identity"],
            }
        )
    return {
        "schema": "moss-r4-s17-identity-partition-receipt.v2",
        "case": case,
        "eligibility_floor_samples": ELIGIBILITY_FLOOR_SAMPLES,
        "terminal_local_label_stream": rows,
        "product_partitions": list(partitions.values()),
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
    capture = _capture_module()
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
            if not case_rows:
                raise RuntimeError(f"capture emitted no terminal rows for {case}; receipt falsified")
            case_capture = case_dir / "terminal-labels.jsonl"
            case_capture.parent.mkdir(parents=True, exist_ok=True)
            case_capture.write_text("\n".join(case_lines) + "\n", encoding="utf-8")
            _write(case_dir / "partition-receipt.json", partition_receipt(case, case_rows))
        requests = args.out / "state/requests.jsonl"
        if requests.exists():
            shutil.copyfile(requests, args.out / "decoder-requests.jsonl")
        _write(
            args.out / "run.json",
            {
                "schema": "moss-r4-s17-identity-rerun.v2",
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
    return execute(args, plan_data)


if __name__ == "__main__":
    raise SystemExit(main())
