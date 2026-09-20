"""Optional local-HF File smoke through the real FastAPI lifespan."""

from __future__ import annotations

import json
import os
import tempfile
import time
import wave
from pathlib import Path

from fastapi.testclient import TestClient

from moss_transcribe_diarize.app import phase2
from moss_transcribe_diarize.app.phase2 import create_phase2_app
from moss_transcribe_diarize.app.runner_composition import build_file_runner


MODEL = Path(
    "/Users/gao/.cache/huggingface/hub/"
    "models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/"
    "e8681d68e7042738ffca8ac8212bc8fcb1131ab8"
)
SOURCE = Path(
    "/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/"
    "evidence/live-policy-sweep-20260825/corpus/mono_javier_intro_50s/audio.wav"
)


def _crop(source: Path, destination: Path, seconds: float = 10.0) -> None:
    with wave.open(str(source), "rb") as reader:
        params = reader.getparams()
        frames = reader.readframes(int(params.framerate * seconds))
    with wave.open(str(destination), "wb") as writer:
        writer.setparams(params)
        writer.writeframes(frames)


def run() -> dict[str, object]:
    if not MODEL.is_dir():
        return {"verdict": "BLOCKED-ON-MODEL", "model": str(MODEL)}
    actual_sqlite = phase2.sqlite3.sqlite_version
    phase2.sqlite3.sqlite_version = phase2.REQUIRED_SQLITE_RUNTIME
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix="moss-r4-real-smoke-") as temporary:
            root = Path(temporary)
            clip = root / "human-speech-10s.wav"
            _crop(SOURCE, clip)
            runner = build_file_runner(
                model_path=MODEL,
                device="auto",
                dtype="bf16",
                backend="hf",
                vllm_base_url=None,
                vllm_model=None,
                vllm_api_key=None,
                vllm_timeout=1800.0,
                file_identity="album",
            )
            app = create_phase2_app(
                database_path=root / "state.sqlite3",
                file_runner=runner,
                file_work_root=root / "file-work",
                meeting_audio_root=root / "meetings",
                open_workspace=True,
            )
            with TestClient(app, base_url="https://moss.test") as client:
                with clip.open("rb") as source:
                    response = client.post(
                        "/api/meetings/file",
                        files={"file": (clip.name, source, "audio/wav")},
                    )
                response.raise_for_status()
                meeting_id = response.json()["id"]
                deadline = time.monotonic() + 900.0
                while True:
                    meeting = client.get(f"/api/meetings/{meeting_id}").json()
                    if meeting["status"] != "active":
                        break
                    if time.monotonic() >= deadline:
                        raise TimeoutError("local-HF File smoke exceeded 900 seconds")
                    time.sleep(0.25)
            transcript = meeting.get("transcript") or {}
            segments = transcript.get("segments") or []
            return {
                "verdict": (
                    "SUPPORTED"
                    if meeting["status"] == "completed" and len(segments) > 0
                    else "FALSIFIED"
                ),
                "real_app_lifespan": True,
                "backend": "local-hf",
                "network_allowed": False,
                "remote_decoder_requests": 0,
                "source": "mono_javier_intro_50s first 10 seconds",
                "meeting_status": meeting["status"],
                "transcript_segments": len(segments),
                "generated_text_characters": sum(
                    len(str(segment.get("text", ""))) for segment in segments
                ),
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "sqlite_runtime": actual_sqlite,
                "sqlite_semantic_store_allowance": (
                    actual_sqlite != phase2.REQUIRED_SQLITE_RUNTIME
                ),
            }
    except Exception as exc:
        return {
            "verdict": "FALSIFIED",
            "real_app_lifespan": True,
            "backend": "local-hf",
            "network_allowed": False,
            "remote_decoder_requests": 0,
            "reason_type": type(exc).__name__,
            "reason": str(exc),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "sqlite_runtime": actual_sqlite,
            "sqlite_semantic_store_allowance": (
                actual_sqlite != phase2.REQUIRED_SQLITE_RUNTIME
            ),
        }
    finally:
        phase2.sqlite3.sqlite_version = actual_sqlite


if __name__ == "__main__":
    result = run()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if os.environ.get("MOSS_R4_NO_WRITE") != "1":
        destination = Path(__file__).with_name("real-runner-smoke.json")
        destination.write_text(rendered)
        evidence = Path(__file__).parents[2] / "evidence" / "round4" / "batch"
        evidence.mkdir(parents=True, exist_ok=True)
        (evidence / "real-runner-smoke.json").write_text(rendered)
    print(rendered, end="")
    raise SystemExit(0 if result["verdict"] == "SUPPORTED" else 1)
