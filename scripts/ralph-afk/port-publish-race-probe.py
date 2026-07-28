"""Measure the port-publish race the keeper merge lost.

Reproduces exactly the two sides of tests/test_live_deployment_credentials.py:
  writer: publishes a port into a file the reader is polling
  reader: treats Path.exists() as "the port is readable", then int()s the contents

`plain` is the shipped write_text; `atomic` is the staging-file + os.replace form.
Reports how many times the reader observed an existing-but-incomplete file.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
import tempfile

ROUNDS = 4000


def publish_plain(port_file: Path, port: str) -> None:
    port_file.write_text(port, encoding="ascii")


def publish_atomic(port_file: Path, port: str) -> None:
    staging = port_file.with_name(port_file.name + ".partial")
    staging.write_text(port, encoding="ascii")
    os.replace(staging, port_file)


def run(mode: str) -> tuple[int, int]:
    publish = publish_plain if mode == "plain" else publish_atomic
    torn = 0
    observed = 0
    with tempfile.TemporaryDirectory() as d:
        for i in range(ROUNDS):
            port_file = Path(d) / f"server.{i}.port"
            start = threading.Barrier(2)

            def writer() -> None:
                start.wait()
                publish(port_file, "54321")

            t = threading.Thread(target=writer)
            t.start()
            start.wait()
            # The reader's loop, verbatim in shape: exists() -> read -> int().
            while True:
                if port_file.exists():
                    observed += 1
                    text = port_file.read_text(encoding="ascii")
                    try:
                        int(text)
                    except ValueError:
                        torn += 1
                    break
                if not t.is_alive() and port_file.exists():
                    continue
            t.join()
    return torn, observed


if __name__ == "__main__":
    mode = sys.argv[1]
    torn, observed = run(mode)
    print(f"{mode}: rounds={ROUNDS} reads={observed} torn={torn}")
    sys.exit(1 if torn else 0)
