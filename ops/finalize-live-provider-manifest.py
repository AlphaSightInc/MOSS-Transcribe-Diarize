#!/usr/bin/env python3
"""Tracked deployment tool: finalize the host live provider manifest bounds.

Run from the deployed checkout so the generated bounds and config hashes come from the
reviewed revision, not from whatever copy of the package happens to be installed.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moss_transcribe_diarize.app.live_manifest_finalizer import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
