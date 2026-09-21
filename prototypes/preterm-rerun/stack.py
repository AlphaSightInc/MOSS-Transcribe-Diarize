"""Private R4-10 stack: records raw decoder responses beside the production seam."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True); parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--cert", type=Path, required=True); parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True); parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--decoder-base-url", required=True); parser.add_argument("--budget", type=int, required=True)
    parser.add_argument("--raw-events", type=Path, required=True)
    args = parser.parse_args()
    from moss_transcribe_diarize.app import phase2, phase2_web_cli
    from moss_transcribe_diarize.app.live_coordinator import LiveCoordinator
    from moss_transcribe_diarize.app.vllm_runner import VllmRunner
    args.state.mkdir(parents=True); args.raw_events.parent.mkdir(parents=True, exist_ok=True)
    local = threading.local(); lock = threading.Lock(); sent = 0
    original_post, original_decode = VllmRunner._post_multipart, LiveCoordinator._decode
    def post(self, *call_args, **kwargs):
        nonlocal sent
        with lock:
            if sent >= args.budget: raise RuntimeError("R4-10 receipt budget exhausted")
            sent += 1
        response = original_post(self, *call_args, **kwargs); local.response = response; return response
    def decode(self, span, pcm):
        matches = [lane for lane, retained in self._lane_pcm.items()
                   if retained.extract(span.start_sample, span.end_sample) == pcm]
        if len(matches) != 1:
            raise RuntimeError(f"raw decoder lane attribution ambiguous: {matches}")
        try:
            return original_decode(self, span, pcm)
        finally:
            response = getattr(local, "response", None)
            if response is None: raise RuntimeError("raw decoder response absent")
            with args.raw_events.open("a") as stream:
                stream.write(json.dumps({"session_id": self.session_key, "lane": matches[0], "monotonic": time.monotonic(),
                    "span": {"id": span.id, "start_sample": span.start_sample, "end_sample": span.end_sample, "reason": span.reason},
                    "response": response}) + "\n")
            local.response = None
    VllmRunner._post_multipart, LiveCoordinator._decode = post, decode
    # No SQLite bypass: frozen R4-10 must run on the supported runtime receipt from R4-7.
    phase2_web_cli.main(["--database", str(args.state / "phase2.sqlite"), "--control-socket", str(args.state / "control.sock"),
        "--tls-certfile", str(args.cert), "--tls-keyfile", str(args.key), "--backend", "vllm", "--model", str(args.model),
        "--vllm-base-url", args.decoder_base_url, "--vllm-model", "OpenMOSS-Team/MOSS-Transcribe-Diarize", "--vllm-timeout", "1800",
        "--file-work-root", str(args.state / "file-work"), "--meeting-audio-root", str(args.state / "meeting-audio"),
        "--live-provider-manifest", str(args.manifest), "--live-helper-lease-seconds", "30", "--host", "127.0.0.1", "--port", str(args.port),
        "--max-len", "16384", "--max-new-tokens", "12000"])


if __name__ == "__main__":
    main()
