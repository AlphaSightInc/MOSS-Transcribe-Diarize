"""Rerun the original file order, its reverse, and the exact-runtime gate."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
FILES = '''tests/test_live_mixer.py tests/test_live_session.py tests/test_live_session_v2.py tests/test_live_vad.py tests/test_live_terminal_finalizer.py tests/phase2/test_owner_bound_live_meeting.py tests/phase2/test_wave1_qualification.py tests/test_live_service_runtime.py tests/test_live_terminal_lifecycle.py tests/test_live_terminal_tape.py tests/test_live_transcript_convergence.py tests/phase2/test_pre_stop_terminal_boundary.py'''.split()
if __name__ == '__main__':
    scratch = ROOT / '.wp6-tmp'
    scratch.mkdir(exist_ok=True)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONPATH=str(ROOT), TMPDIR=str(scratch))
    failed = False
    for name, paths in [('forward', FILES), ('reverse', FILES[::-1]), ('runtime-pin', ['tests/phase2/test_workspace_lifecycle.py'])]:
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider', *paths], cwd=ROOT, env=env, capture_output=True, text=True)
        (Path(__file__).parent / f'part0-{name}.txt').write_text(result.stdout + result.stderr)
        print(name, result.returncode, result.stdout.splitlines()[-1], flush=True)
        failed |= result.returncode != 0
    sys.exit(int(failed))
