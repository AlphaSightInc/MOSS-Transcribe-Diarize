"""R5-F1 ($0): the product's existing preview/lane tests with arm C patched in, and unpatched (throwaway).

    PYTHONDONTWRITEBYTECODE=1 ../MOSS-Transcribe-Diarize-wt-r5-f1.venv/bin/python \
        prototypes/gemini-live/mic-speaker-echo/f1/existing_tests.py

No test or product file is edited; nothing is written to the worktree (no cache, no bytecode).
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE)]
import trim as arms  # noqa: E402

FILES = ["tests/gemini/test_gemini_preview_duplication.py", "tests/gemini/test_gemini_lane_engine.py",
         "tests/gemini/test_gemini_live_runtime.py"]
FILES = [f for f in FILES if (arms.ROOT / f).is_file()]


class Patch:
    def __init__(self, arm):
        self.arm = arm

    def pytest_sessionstart(self, session):
        arms.runtime._trim_committed_preview = self.arm


for name in ("base", "C"):
    code = pytest.main([*FILES, "-q", "-p", "no:cacheprovider", "--rootdir", str(arms.ROOT), "-x", "--no-header"],
                       plugins=[Patch(arms.ARMS[name])])
    print(f"== arm {name}: pytest exit code {int(code)} on {FILES}")
