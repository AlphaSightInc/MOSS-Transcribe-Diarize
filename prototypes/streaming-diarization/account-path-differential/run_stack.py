import os
"""Local Phase-2 stack for E2E + latency measurement on MacStudio.
Only the sqlite version pin is patched (local harness only; product code untouched)."""
import os, sqlite3, sys
from pathlib import Path
S = Path(os.environ["MOSS_DIFFERENTIAL_SCRATCH"])
sys.path.insert(0, os.environ["MOSS_DIFFERENTIAL_REPO"])  # run the auto-mvp-0911 checkout, not the venv's editable target
import instrument
from moss_transcribe_diarize.app import phase2
phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version  # local harness only
from moss_transcribe_diarize.app import phase2_web_cli
snap = sorted(Path.home().glob(".cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/*"))[-1]
argv = [
    "--database", str(S / "state" / "phase2.sqlite"),
    "--control-socket", str(S / "control.sock"),
    "--tls-certfile", str(S / "cert.pem"), "--tls-keyfile", str(S / "key.pem"),
    "--backend", "vllm", "--model", str(snap),
    "--vllm-base-url", "http://127.0.0.1:18000/v1", "--vllm-model", "OpenMOSS-Team/MOSS-Transcribe-Diarize",
    "--vllm-timeout", "1800",
    "--file-work-root", str(S / "state" / "file-work"), "--meeting-audio-root", str(S / "state" / "meeting-audio"),
    "--live-provider-manifest", str(Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"),
    "--live-helper-lease-seconds", "30",
    "--host", "127.0.0.1", "--port", "17862", "--max-len", "16384", "--max-new-tokens", "12000",
]
phase2_web_cli.main(argv)
