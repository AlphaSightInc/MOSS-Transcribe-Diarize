"""Keep test temp files/sockets in this worktree; leave test assertions unchanged."""
from pathlib import Path
import inspect
import os
import tempfile
import types

TEMP = Path('.wp1/test-tmp')
TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP)
_original_mkdtemp = tempfile.mkdtemp


def relative_mkdtemp(*args, **kwargs):
    path = _original_mkdtemp(*args, **kwargs)
    if Path(path).resolve().parent == TEMP.resolve():
        return os.path.relpath(path)
    return path


tempfile.mkdtemp = relative_mkdtemp


def local_socket_paths(code):
    # Some existing tests hardcode Path('/tmp') for their control sockets.
    # Redirect only those constants, without replacing pathlib or assertions.
    constants = tuple(local_socket_paths(value) if isinstance(value, types.CodeType)
                      else str(TEMP) if isinstance(value, str) and value in ('/tmp', '/private/tmp')
                      else value for value in code.co_consts)
    return code.replace(co_consts=constants)


def pytest_collection_modifyitems(items):
    for module in {item.module for item in items if hasattr(item, 'module')}:
        for value in vars(module).values():
            if inspect.isfunction(value) and value.__module__ == module.__name__:
                value.__code__ = local_socket_paths(value.__code__)
