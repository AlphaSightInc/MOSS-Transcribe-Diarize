"""Resolve an open descriptor path for storage-root assertions on macOS and Linux."""

import fcntl
import os
import sys
from pathlib import Path


def open_fd_path(fd: int) -> Path:
    if sys.platform == "darwin":
        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
        return Path(raw.split(b"\0", 1)[0].decode())
    if sys.platform == "linux":
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    raise RuntimeError(f"Unsupported descriptor path platform: {sys.platform}")
