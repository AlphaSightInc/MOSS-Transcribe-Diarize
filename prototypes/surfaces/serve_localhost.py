"""PROTOTYPE launcher: candidate Account app over HTTP on loopback only.

HTTP localhost is a browser secure context. This avoids certificate/deployment work
for an attended SSH-forwarded session while preserving the production app factory.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from types import SimpleNamespace


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18442)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--vllm-base-url")
    parser.add_argument("--live-provider-manifest", type=Path)
    parser.add_argument("--web-only-smoke", action="store_true")
    parser.add_argument("--allow-current-sqlite-for-smoke", action="store_true")
    args = parser.parse_args()
    if not args.web_only_smoke and not all((args.model, args.vllm_base_url, args.live_provider_manifest)):
        parser.error("full attended launch requires model metadata, vLLM URL, and Live provider manifest")
    if args.allow_current_sqlite_for_smoke and not args.web_only_smoke:
        parser.error("the SQLite exception is permitted only for web-only smoke")

    args.state.mkdir(parents=True, exist_ok=True)
    from moss_transcribe_diarize.app import phase2, phase2_web_cli
    if args.allow_current_sqlite_for_smoke:
        phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version

    file_runner = None
    live_runtime_factory = None
    scheduler = None
    if not args.web_only_smoke:
        from moss_transcribe_diarize.app.inference_scheduler import InferenceDispatchScheduler
        scheduler = InferenceDispatchScheduler(max_calls=2, max_background_calls=1)
        runtime = SimpleNamespace(
            model=str(args.model), device="auto", dtype="bf16", backend="vllm",
            vllm_base_url=args.vllm_base_url,
            vllm_model="OpenMOSS-Team/MOSS-Transcribe-Diarize",
            vllm_api_key="EMPTY", vllm_timeout=1800.0, file_identity="album",
            live_provider_manifest=str(args.live_provider_manifest),
            file_work_root=str(args.state / "file-work"), prompt=None,
            max_len=16384, max_new_tokens=12000, decoding="greedy", temperature=1.0,
            live_helper_lease_seconds=30.0, live_draft_lane_seconds=None,
            _inference_scheduler=scheduler,
        )
        file_runner = phase2_web_cli._build_file_runner(runtime)
        live_runtime_factory = phase2_web_cli._build_live_runtime_factory(runtime, file_runner)

    app = phase2.create_phase2_app(
        database_path=args.state / "phase2.sqlite3",
        file_runner=file_runner,
        file_work_root=args.state / "file-work",
        meeting_audio_root=args.state / "meeting-audio",
        live_runtime_factory=live_runtime_factory,
        live_helper_lease_seconds=None if args.web_only_smoke else 30.0,
        control_socket_path=args.state / "control.sock",
        inference_scheduler=scheduler,
    )
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
