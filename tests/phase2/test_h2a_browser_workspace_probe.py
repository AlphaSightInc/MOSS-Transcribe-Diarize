"""The deterministic browser probe must seed completed speech before testing history."""
import subprocess
import sys
from pathlib import Path


def test_browser_workspace_probe_completes_its_speech_fixture():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "prototypes/phase2-account-lifecycle/browser_workspace_probe.py"],
        cwd=repo, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert '"collector_semantics": "pass"' in result.stdout
    assert '"collector_removed_lock_mutation": "rejected"' in result.stdout
