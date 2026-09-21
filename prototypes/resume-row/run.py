#!/usr/bin/env python3
"""F3r: retained File resume confirmation, planned now and real-decoder gated.

Plan only::

  python prototypes/resume-row/run.py --plan-only --frozen-sha "$FROZEN_SHA" \
    --out /tmp/f3r-plan.json

The real row requires an already-owned decoder tunnel port. It never opens a
tunnel, reads a provider credential, or opens a microphone.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import ssl
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


DURATION_SECONDS = 360
CHECKPOINT_WINDOWS = 1
REQUEST_CAP = 12
DEFAULT_PORT = 17835
DEFAULT_PROXY_PORT = 19135
CORPUS = ROOT / "evidence/live-policy-sweep-20260825/corpus"
SOURCE_CLIPS = (
    CORPUS / "interview_bill_ackman_60s/audio.wav",
    CORPUS / "interview_keyu_jin_60s/audio.wav",
)


def request_plan(frozen_sha: str) -> dict[str, Any]:
    from moss_transcribe_diarize.app.windowed_transcription import plan_windows

    windows = plan_windows(DURATION_SECONDS)
    n = len(windows)
    k = CHECKPOINT_WINDOWS
    if n < 3 or not 1 <= k < n:
        raise RuntimeError("resume-row population no longer has a strict committed prefix")
    reference = n
    before_crash = k
    after_restart = n - k
    actual_total = reference + before_crash + after_restart
    stated_formula = 2 * n - k
    if actual_total > REQUEST_CAP:
        raise RuntimeError("resume-row request plan exceeds its cap")
    return {
        "schema": "moss-r4-f3r-resume-plan.v1",
        "mode": "PLAN_ONLY",
        "frozen_sha": frozen_sha,
        "population": {
            "source": "existing round-4 public corpus; alternating two retained 60-second clips",
            "duration_seconds": DURATION_SECONDS,
            "windows": [
                {"index": window.index, "start": window.start, "end": window.end}
                for window in windows
            ],
            "n": n,
            "k": k,
        },
        "requests": {
            "uninterrupted_reference": reference,
            "before_sigkill": before_crash,
            "after_restart": after_restart,
            "planned_decoder": actual_total,
            "cap": REQUEST_CAP,
        },
        "brief_arithmetic": {
            "stated_formula": "2n-k",
            "stated_value": stated_formula,
            "status": "UNDERCOUNTS_PRE_SIGKILL_K",
            "correct_formula": "n+k+(n-k)=2n",
        },
        "provider_calls": 0,
        "capacity_2x1800": "REQUIRED-NOT-RUN",
        "gated_on": "pane 3.3 F1 fix merged and product re-frozen",
        "actual_calls": {"decoder": 0, "provider": 0},
    }


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def row_status(checks: dict[str, bool], *, upstream_error: bool = False) -> str:
    """Missing evidence and upstream errors are INCOMPLETE, never product FAIL."""

    return "PASS" if checks and all(checks.values()) and not upstream_error else "INCOMPLETE"


class Client:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.context = ssl._create_unverified_context()
        self.cookies: dict[str, str] = {}

    def _headers(self, content_type: str) -> dict[str, str]:
        headers = {"Content-Type": content_type}
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{key}={value}" for key, value in self.cookies.items())
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        timeout: int = 120,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method=method,
            headers=self._headers(content_type),
        )
        with urllib.request.urlopen(request, context=self.context, timeout=timeout) as response:
            for header in response.headers.get_all("Set-Cookie") or []:
                name, _, value = header.partition("=")
                self.cookies[name] = value.split(";", 1)[0]
            return json.loads(response.read() or b"{}")

    def json(self, method: str, path: str, body: Any | None = None) -> dict[str, Any]:
        raw = None if body is None else json.dumps(body).encode("utf-8")
        return self.request(method, path, body=raw)

    def upload(self, path: Path) -> dict[str, Any]:
        boundary = "----moss-f3r-resume"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="resume.wav"\r\n'
            "Content-Type: audio/wav\r\n\r\n"
        ).encode("ascii") + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode("ascii")
        return self.request(
            "POST",
            "/api/meetings/file",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            timeout=300,
        )


def _compose_source(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as output:
        output.setparams((1, 2, 16_000, 0, "NONE", "not compressed"))
        for index in range(6):
            with wave.open(str(SOURCE_CLIPS[index % len(SOURCE_CLIPS)]), "rb") as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16_000):
                    raise RuntimeError("resume-row corpus geometry changed")
                frames = source.readframes(60 * 16_000)
                if len(frames) != 60 * 16_000 * 2:
                    raise RuntimeError("resume-row corpus clip is shorter than 60 seconds")
                output.writeframes(frames)


def _certificate(directory: Path) -> tuple[Path, Path]:
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-days", "1", "-subj", "/CN=127.0.0.1",
            "-addext", "subjectAltName=IP:127.0.0.1",
            "-keyout", str(key), "-out", str(cert),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return cert, key


def _stack_command(args: argparse.Namespace, cert: Path, key: Path) -> list[str]:
    return [
        sys.executable,
        str(ROOT / "prototypes/streaming-diarization/draft-lane/run_local_stack.py"),
        "--state", str(args.out / "state"),
        "--cert", str(cert),
        "--key", str(key),
        "--port", str(args.port),
        "--model", str(args.model),
        "--manifest", str(args.manifest),
        "--vllm-base-url", f"http://127.0.0.1:{args.proxy_port}/v1",
        "--max-requests", str(args.budget),
    ]


def _start_stack(args: argparse.Namespace, cert: Path, key: Path, name: str) -> tuple[subprocess.Popen[bytes], Any]:
    log = (args.out / f"{name}.log").open("wb")
    process = subprocess.Popen(
        _stack_command(args, cert, key),
        cwd=ROOT,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT)},
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return process, log


def _stop_stack(process: subprocess.Popen[bytes] | None, *, crash: bool = False) -> None:
    if process is None or process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGKILL if crash else signal.SIGTERM)
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def _ready(client: Client, process: subprocess.Popen[bytes], *, bootstrap: bool) -> tuple[dict[str, Any], float]:
    started = time.monotonic()
    last_error: Exception | None = None
    for _ in range(240):
        if process.poll() is not None:
            raise RuntimeError("stack exited before readiness")
        try:
            if bootstrap:
                workspace = client.json("POST", "/api/workspace/bootstrap")
            else:
                workspace = {}
            descriptor = client.json("GET", "/api/live/descriptor")
            return {"workspace": workspace, "descriptor": descriptor}, time.monotonic() - started
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    raise RuntimeError("stack did not become ready") from last_error


def _wait_terminal(client: Client, meeting_id: str, timeout: int = 1800) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        meeting = client.json("GET", f"/api/meetings/{meeting_id}")
        if meeting.get("status") != "active":
            return meeting
        time.sleep(0.25)
    raise RuntimeError("meeting did not become terminal")


def _owner_dir(args: argparse.Namespace, workspace_id: str, meeting_id: str) -> Path:
    return args.out / "state/file-retained" / workspace_id / meeting_id


def _wait_prefix(
    owner_dir: Path,
    proxy: Any,
    *,
    accepted_before: int,
    k: int,
    timeout: int = 1800,
) -> dict[str, int]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        records = tuple((owner_dir / "checkpoint/windows").glob("w*.json"))
        counters = proxy.snapshot()
        accepted = counters.accepted - accepted_before
        completed = counters.completed - accepted_before
        if len(records) > k or accepted > k:
            raise RuntimeError("pre-crash work advanced beyond the planned prefix")
        if len(records) == k and accepted == completed == k and counters.active == 0:
            return {"checkpoint_records": len(records), "accepted": accepted, "completed": completed}
        time.sleep(0.01)
    raise RuntimeError("planned checkpoint prefix was not observed")


def _reservation_held(owner_dir: Path) -> bool:
    lock_path = owner_dir / "resume.lock"
    if not lock_path.exists():
        return False
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return False


def _product_diff(frozen_sha: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", frozen_sha, "--", "moss_transcribe_diarize", "frontend"],
        cwd=ROOT,
        text=True,
    )
    return [line for line in output.splitlines() if line]


def execute(args: argparse.Namespace, plan: dict[str, Any]) -> int:
    from tools.qualify.decoder import Decoder

    if args.out.exists():
        raise SystemExit(f"REFUSE: output exists: {args.out}")
    if args.decoder_upstream_port is None:
        raise SystemExit("REFUSE: --decoder-upstream-port is required; no tunnel is opened")
    if args.budget != int(plan["requests"]["planned_decoder"]):
        raise SystemExit("REFUSE: --budget must equal the exact F3r request plan")
    if args.budget > REQUEST_CAP:
        raise SystemExit("REFUSE: request cap exceeded")
    if not args.model.is_dir() or not args.manifest.is_file():
        raise SystemExit("REFUSE: model or manifest is unavailable")
    product_changes = _product_diff(args.frozen_sha)
    if product_changes:
        raise SystemExit("REFUSE: product differs from --frozen-sha")

    args.out.mkdir(parents=True)
    source = args.out / "source-360s.wav"
    cert, key = args.out / "cert.pem", args.out / "key.pem"
    proxy: Any | None = None
    proxy_started = False
    stack: subprocess.Popen[bytes] | None = None
    logs: list[Any] = []
    upstream_error = False
    receipt: dict[str, Any] = {
        **plan,
        "mode": "EXECUTED",
        "product_changes_since_frozen_sha": product_changes,
    }
    try:
        _compose_source(source)
        cert, key = _certificate(args.out)
        proxy = Decoder(
            args.proxy_port,
            args.decoder_upstream_port,
            args.budget,
            args.out / "decoder-requests.jsonl",
        )
        proxy.start()
        proxy_started = True
        stack, log = _start_stack(args, cert, key, "stack-initial")
        logs.append(log)
        client = Client(f"https://127.0.0.1:{args.port}")
        ready, initial_ready_seconds = _ready(client, stack, bootstrap=True)
        workspace_id = str(ready["workspace"]["workspace_id"])

        reference_before = proxy.snapshot()
        reference_created = client.upload(source)
        reference = _wait_terminal(client, str(reference_created["id"]))
        reference_after = proxy.snapshot()
        reference_requests = reference_after.accepted - reference_before.accepted
        reference_owner = _owner_dir(args, workspace_id, str(reference_created["id"]))

        crash_created = client.upload(source)
        crash_id = str(crash_created["id"])
        crash_owner = _owner_dir(args, workspace_id, crash_id)
        prefix = _wait_prefix(
            crash_owner,
            proxy,
            accepted_before=reference_after.accepted,
            k=int(plan["population"]["k"]),
        )
        _stop_stack(stack, crash=True)
        stack = None
        owner_persisted_after_sigkill = crash_owner.exists()

        restart_before = proxy.snapshot()
        stack, log = _start_stack(args, cert, key, "stack-restart")
        logs.append(log)
        restart_ready, restart_ready_seconds = _ready(client, stack, bootstrap=False)
        reservation_held = _reservation_held(crash_owner)
        resumed = _wait_terminal(client, crash_id)
        restart_after = proxy.snapshot()
        post_restart_requests = restart_after.accepted - restart_before.accepted

        checks = {
            "initial_stack_ready": bool(ready["descriptor"].get("descriptor")),
            "reference_completed": reference.get("status") == "completed",
            "reference_requests_exact": reference_requests == int(plan["requests"]["uninterrupted_reference"]),
            "reference_owner_reclaimed": not reference_owner.exists(),
            "checkpoint_prefix_exact": prefix["checkpoint_records"] == int(plan["population"]["k"]),
            "sigkill_preserved_owner": owner_persisted_after_sigkill,
            "restart_descriptor_served": bool(restart_ready["descriptor"].get("descriptor")),
            "meeting_reserved_at_readiness": reservation_held,
            "checkpoint_validation_accepted": (
                resumed.get("status") == "completed"
                and post_restart_requests == int(plan["requests"]["after_restart"])
                and post_restart_requests < int(plan["population"]["n"])
            ),
            "post_restart_requests_exact": post_restart_requests == int(plan["requests"]["after_restart"]),
            "meeting_done": resumed.get("status") == "completed",
            "transcript_equals_uninterrupted": resumed.get("transcript") == reference.get("transcript"),
            "owner_reclaimed": not crash_owner.exists(),
            "total_requests_exact": restart_after.accepted == int(plan["requests"]["planned_decoder"]),
            "proxy_completed_exact": restart_after.completed == restart_after.accepted,
            "proxy_active_zero": restart_after.active == 0,
            "proxy_rejected_zero": restart_after.rejected == 0,
            "peak_in_flight_at_most_two": restart_after.peak_in_flight <= 2,
        }
        upstream_error = any(
            meeting.get("status") == "failed"
            for meeting in (reference, resumed)
        )
        receipt.update(
            status=row_status(checks, upstream_error=upstream_error),
            checks=checks,
            timings={
                "initial_ready_seconds": round(initial_ready_seconds, 3),
                "restart_ready_seconds": round(restart_ready_seconds, 3),
            },
            counters={
                "reference": reference_requests,
                "before_sigkill": prefix["accepted"],
                "after_restart": post_restart_requests,
                "total": restart_after.accepted,
                "completed": restart_after.completed,
                "rejected": restart_after.rejected,
                "peak_in_flight": restart_after.peak_in_flight,
            },
            actual_calls={"decoder": restart_after.accepted, "provider": 0},
            meetings={
                "reference_status": reference.get("status"),
                "resumed_status": resumed.get("status"),
                "reference_segments": len((reference.get("transcript") or {}).get("segments") or []),
                "resumed_segments": len((resumed.get("transcript") or {}).get("segments") or []),
            },
        )
    except Exception as exc:
        receipt.update(
            status="INCOMPLETE",
            reason=f"{type(exc).__name__}; inspect private stack logs",
        )
    finally:
        _stop_stack(stack)
        if proxy is not None:
            counters = proxy.snapshot()
            receipt["actual_calls"] = {"decoder": counters.accepted, "provider": 0}
        if proxy_started:
            try:
                proxy.close()
            except Exception:
                receipt["status"] = "INCOMPLETE"
                receipt["reason"] = "proxy teardown failed"
        for log in logs:
            log.close()
        for private in (source, cert, key):
            private.unlink(missing_ok=True)
        _write(args.out / "receipt.json", receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("status") == "PASS" else 2


def _stub_server(state: Path, mode: str) -> int:
    state.mkdir(parents=True, exist_ok=True)
    events = state / "requests.jsonl"
    checkpoint = state / "owner/checkpoint/windows"
    checkpoint.mkdir(parents=True, exist_ok=True)
    (state / f"ready-{mode}").write_text("ready\n", encoding="utf-8")
    count = {"reference": 3, "crash": 1, "restart": 2}[mode]
    for index in range(count):
        with events.open("a", encoding="utf-8") as output:
            output.write(json.dumps({"mode": mode, "index": index}) + "\n")
        if mode == "crash":
            (checkpoint / "w000000.json").write_text("{}\n", encoding="utf-8")
    if mode == "crash":
        while True:
            time.sleep(60)
    if mode == "restart":
        (state / "owner-reclaimed").write_text("yes\n", encoding="utf-8")
    (state / f"done-{mode}").write_text("done\n", encoding="utf-8")
    return 0


def fake_dry_run(out: Path, frozen_sha: str) -> int:
    if out.exists():
        raise SystemExit(f"REFUSE: output exists: {out}")
    state = out / "state"
    out.mkdir(parents=True)
    command = [sys.executable, str(Path(__file__).resolve()), "--stub-server", "--stub-state", str(state)]
    subprocess.run([*command, "--stub-mode", "reference"], check=True)
    crash = subprocess.Popen([*command, "--stub-mode", "crash"], start_new_session=True)
    deadline = time.monotonic() + 10
    checkpoint = state / "owner/checkpoint/windows/w000000.json"
    while not checkpoint.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    killed = checkpoint.exists()
    if killed:
        os.killpg(crash.pid, signal.SIGKILL)
    crash.wait(timeout=10)
    subprocess.run([*command, "--stub-mode", "restart"], check=True)
    events = [json.loads(line) for line in (state / "requests.jsonl").read_text().splitlines()]
    checks = {
        "checkpoint_observed": checkpoint.exists(),
        "sigkill_observed": crash.returncode == -signal.SIGKILL,
        "restart_completed": (state / "done-restart").is_file(),
        "owner_reclaimed": (state / "owner-reclaimed").is_file(),
        "phase_counts_exact": {
            mode: sum(event["mode"] == mode for event in events)
            for mode in ("reference", "crash", "restart")
        } == {"reference": 3, "crash": 1, "restart": 2},
    }
    receipt = {
        **request_plan(frozen_sha),
        "mode": "FAKE_DRY_RUN",
        "status": row_status(checks),
        "checks": checks,
        "actual_calls": {"decoder": 0, "provider": 0},
    }
    _write(out / "receipt.json", receipt)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["status"] == "PASS" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--fake-dry-run", action="store_true")
    mode.add_argument("--stub-server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--frozen-sha")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--decoder-upstream-port", type=int)
    parser.add_argument("--budget", type=int, default=0)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--proxy-port", type=int, default=DEFAULT_PROXY_PORT)
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
    parser.add_argument("--stub-state", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--stub-mode", choices=("reference", "crash", "restart"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.stub_server:
        if args.stub_state is None or args.stub_mode is None:
            parser.error("stub state and mode are required")
        return _stub_server(args.stub_state, args.stub_mode)
    if not args.frozen_sha or args.out is None:
        parser.error("--frozen-sha and --out are required")
    plan = request_plan(args.frozen_sha)
    if args.plan_only:
        _write(args.out, plan)
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.fake_dry_run:
        return fake_dry_run(args.out, args.frozen_sha)
    return execute(args, plan)


if __name__ == "__main__":
    raise SystemExit(main())
