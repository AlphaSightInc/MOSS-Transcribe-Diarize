"""One real 60-second product File decode; writes a credential-free receipt."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app.inference_scheduler import InferenceDispatchScheduler
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.runner_composition import build_file_runner


class CountingDelegate:
    def __init__(self, delegate):
        self.delegate = delegate
        self.model_path = delegate.model_path
        self.calls = 0

    @property
    def is_loaded(self):
        return self.delegate.is_loaded

    def runtime_info(self):
        return self.delegate.runtime_info()

    def transcribe(self, audio_path, **kwargs):
        self.calls += 1
        return self.delegate.transcribe(audio_path, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("hf", "vllm"), required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--audio", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--vllm-base-url")
    args = parser.parse_args()

    receipt_path = Path(args.receipt)
    scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
    runner = build_file_runner(
        model_path=args.model,
        device="auto",
        dtype="bf16",
        backend=args.backend,
        vllm_base_url=args.vllm_base_url,
        vllm_model="OpenMOSS-Team/MOSS-Transcribe-Diarize" if args.backend == "vllm" else None,
        vllm_api_key="EMPTY",
        vllm_timeout=1_800,
        file_identity="legacy",
        inference_scheduler=scheduler,
    )
    counted = CountingDelegate(runner.delegate)
    runner.delegate = counted
    started = time.monotonic()
    receipt: dict[str, object] = {
        "backend": args.backend,
        "source": str(Path(args.audio)),
        "model": str(args.model),
        "remote_request_budget": 20 if args.backend == "vllm" else 0,
        "sqlite_runtime": sqlite3.sqlite_version,
        "sqlite_semantic_store_allowance": sqlite3.sqlite_version != phase2.REQUIRED_SQLITE_RUNTIME,
    }
    try:
        if receipt["sqlite_semantic_store_allowance"]:
            phase2.sqlite3.sqlite_version = phase2.REQUIRED_SQLITE_RUNTIME
        with tempfile.TemporaryDirectory(prefix=f"moss-wp49-{args.backend}-") as scratch:
            root = Path(scratch)
            app = create_phase2_app(
                database_path=root / "state.sqlite3",
                file_runner=runner,
                file_work_root=root / "file-work",
                meeting_audio_root=root / "audio",
                file_inference_options={
                    "max_length": 131_072,
                    "max_new_tokens": 2_048,
                    "decoding": "greedy",
                    "temperature": None,
                },
                inference_scheduler=scheduler,
            )
            with TestClient(app, base_url="https://moss.test") as client:
                assert client.post("/api/workspace/bootstrap").status_code == 200
                accepted = client.post(
                    "/api/meetings/file",
                    files={
                        "file": (
                            Path(args.audio).name,
                            Path(args.audio).read_bytes(),
                            "audio/wav",
                        )
                    },
                )
                receipt["accept_status"] = accepted.status_code
                meeting_id = accepted.json()["id"]
                deadline = time.monotonic() + 1_800
                while time.monotonic() < deadline:
                    meeting = client.get(f"/api/meetings/{meeting_id}").json()
                    if meeting["status"] != "active":
                        break
                    time.sleep(0.25)
                else:
                    raise TimeoutError("real File control did not become terminal")
                receipt.update(
                    meeting_status=meeting["status"],
                    failure_code=meeting.get("failure_code"),
                    notice=meeting.get("notice"),
                    transcript=meeting.get("transcript"),
                    audio_state=(meeting.get("audio") or {}).get("state"),
                    audio_download_status=client.get(
                        f"/api/meetings/{meeting_id}/audio/download"
                    ).status_code,
                )
    except BaseException as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc))
        raise
    finally:
        receipt.update(
            delegate_calls=counted.calls,
            wall_seconds=round(time.monotonic() - started, 3),
            scheduler={
                "running": scheduler.snapshot().running_calls,
                "waiting_background": scheduler.snapshot().waiting_background_calls,
            },
        )
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt.get("meeting_status") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
