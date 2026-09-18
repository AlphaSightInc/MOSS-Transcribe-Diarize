"""WP28 test invocation only: redirect hardcoded /tmp fixture paths into this tree.
No product monkeypatches or test assertions change. Short relative socket addresses
avoid macOS's Unix socket length limit for this long worktree path.
"""
from pathlib import Path
import inspect
import os
import tempfile
import pytest

SOCKETS = Path('runs/wp28/sockets')
MODULES = {'test_operator_status', 'test_owner_bound_live_meeting',
           'test_workspace_lifecycle', 'test_file_mp3_artifact',
           'test_owner_bound_file_meeting'}

@pytest.fixture(autouse=True)
def confined_fixture_paths(request, monkeypatch):
    item = request.node
    name = item.module.__name__.rsplit('.', 1)[-1]
    if name in MODULES and (name == 'test_workspace_lifecycle' or 'Path("/tmp")' in inspect.getsource(item.function)):
        SOCKETS.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(item.module, 'Path', lambda *a, **kw: SOCKETS if a == ('/tmp',) else Path(*a, **kw))
    if name == 'test_admin_status_capture':
        SOCKETS.mkdir(parents=True, exist_ok=True)
        original = tempfile.TemporaryDirectory
        enter = original.__enter__
        monkeypatch.setattr(original, '__enter__', lambda obj: os.path.relpath(enter(obj), Path.cwd()))
        monkeypatch.setattr(tempfile, 'TemporaryDirectory', lambda *a, **kw: original(*a, **{**kw, 'dir':str(SOCKETS)}))
