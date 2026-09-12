"""Local Phase-2 stack for E2E + latency measurement on MacStudio.
Only the sqlite version pin is patched (local harness only; product code untouched)."""
import os, sqlite3, sys
from pathlib import Path
S = Path(__file__).resolve().parent
sys.path.insert(0, '/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-llm-relay-0911')  # run the auto-mvp-0911 checkout, not the venv's editable target
os.environ["MOSS_LLM_UPSTREAMS"] = '[{"name": "macstudio", "base_url": "http://macstudio.tailnet.aisight.us:1234/v1", "models": ["qwen/qwen3.6-35b-a3b"]}, {"name": "rtx4090", "base_url": "http://ga0-rtx4090.tailnet.aisight.us:1235/v1", "models": ["qwen38-27b-mtp"]}]'
from moss_transcribe_diarize.app import phase2
phase2.REQUIRED_SQLITE_RUNTIME = sqlite3.sqlite_version  # local harness only
from moss_transcribe_diarize.app import phase2_web_cli
snap = sorted(Path.home().glob(".cache/huggingface/hub/models--OpenMOSS-Team--MOSS-Transcribe-Diarize/snapshots/*"))[-1]
argv = [
    "--database", str(S / "state" / "phase2.sqlite"),
    "--control-socket", str(S / "control.sock"),
    "--tls-certfile", '/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/8867e7b4-6afc-448e-a8c6-d0a8dbab723a/scratchpad/localstack/cert.pem', "--tls-keyfile", '/private/tmp/claude-501/-Users-gao-Desktop-AI-Projects-Github-Projects-MOSS-Transcribe-Diarize/8867e7b4-6afc-448e-a8c6-d0a8dbab723a/scratchpad/localstack/key.pem',
    "--backend", "vllm", "--model", str(snap),
    "--vllm-base-url", "http://127.0.0.1:18000/v1", "--vllm-model", "OpenMOSS-Team/MOSS-Transcribe-Diarize",
    "--vllm-timeout", "1800",
    "--file-work-root", str(S / "state" / "file-work"), "--meeting-audio-root", str(S / "state" / "meeting-audio"),
    "--live-provider-manifest", str(Path.home() / ".local/share/moss-transcribe-diarize/live/live-provider-manifest.json"),
    "--live-helper-lease-seconds", "30",
    "--host", "127.0.0.1", "--port", "17863", "--max-len", "16384", "--max-new-tokens", "12000",
]
argv += ["--live-draft-lane-seconds", "1.0"]
phase2_web_cli.main(argv)
