#!/usr/bin/env python3
"""Run A1 boundary tests while preserving raw transcript and JSON."""

from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()

    suite = unittest.TestSuite(
        unittest.defaultTestLoader.discover(str(HERE), pattern=pattern)
        for pattern in ("test_validate_inputs.py", "test_production_cache.py")
    )
    stream = io.StringIO()
    with redirect_stdout(stream), redirect_stderr(stream):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    transcript = stream.getvalue()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = args.evidence_dir / f"a1-{args.label}-transcript.txt"
    json_path = args.evidence_dir / f"a1-{args.label}.json"
    transcript_path.write_text(transcript, encoding="utf-8")
    payload = {
        "errors": [test.id() for test, _ in result.errors],
        "failures": [test.id() for test, _ in result.failures],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "label": args.label,
        "successful": result.wasSuccessful(),
        "tests_run": result.testsRun,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(transcript, end="")
    print(json.dumps(payload, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
