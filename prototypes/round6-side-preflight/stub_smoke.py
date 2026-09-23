#!/usr/bin/env python3
"""One-command zero-real-request smoke for the copied vLLM HTTP stub."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from driver import _metrics


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="side-preflight-stub-") as root:
        root = Path(root)
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).with_name("loopback_vllm_stub.py")),
             "--port", "0", "--out", str(root / "stub")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(50):
                try:
                    port = json.loads((root / "stub/server.json").read_text())["port"]
                    url = f"http://127.0.0.1:{port}/metrics"
                    count = _metrics(url)
                    break
                except Exception:
                    if process.poll() is not None:
                        raise RuntimeError("stub failed to start")
                    time.sleep(.1)
            else:
                raise RuntimeError("stub readiness timeout")
            model_status = urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2).status
            print(json.dumps({"stub_http_models_status": model_status,
                              "requests_before": count, "requests_after": _metrics(url),
                              "real_decoder_requests": 0}, sort_keys=True))
            return 0
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
