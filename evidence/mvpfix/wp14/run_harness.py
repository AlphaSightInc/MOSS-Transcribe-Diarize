"""Use only this worktree's Playwright Chromium, with its own temporary profile."""
import runpy, sys
from pathlib import Path
from tests.phase2 import browser_support
browser_support.browser_executable = lambda p: Path(p.chromium.executable_path)
script = sys.argv.pop(1)
runpy.run_path(script, run_name='__main__')
