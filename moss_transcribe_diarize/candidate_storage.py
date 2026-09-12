"""Disk admission and bounded candidate retention; standard library only.

GB means 1,000,000,000 bytes. Retention never traverses a symlink or prunes live
application state. Use the same host lock as cutover while selecting/deleting.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import time

GB = 10**9
DAY = 24 * 60 * 60


class StorageRefused(RuntimeError):
    pass


def is_wsl() -> bool:
    return 'microsoft' in platform.release().lower() or bool(os.environ.get('WSL_INTEROP'))


def windows_free_bytes() -> int | None:
    # Only query /mnt/c if mounted: an ordinary directory would report Linux space.
    if os.path.ismount('/mnt/c'):
        try:
            return shutil.disk_usage('/mnt/c').free
        except OSError:
            pass
    try:
        result = subprocess.run(
            ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
             "[Console]::Write((Get-PSDrive -Name C).Free)"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        value = int(result.stdout.strip())
        return value if value >= 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _minimum(name: str, default: int) -> int:
    try:
        value = float(os.environ.get(name, str(default)))
        if not math.isfinite(value) or value <= 0:
            raise ValueError()
        return int(value * GB)
    except ValueError as exc:
        raise StorageRefused(f'{name} must be a positive GB value') from exc


def check_space() -> list[dict]:
    root_min = _minimum('MOSS_MIN_ROOT_FREE_GB', 20)
    windows_min = _minimum('MOSS_MIN_WINDOWS_FREE_GB', 10)
    try:
        root_free = shutil.disk_usage('/').free
    except OSError as exc:
        raise StorageRefused('root_disk_space_unavailable') from exc
    rows = [{'filesystem': 'root', 'free_bytes': root_free, 'minimum_bytes': root_min, 'status': 'ok'}]
    if is_wsl():
        free = windows_free_bytes()
        rows.append({'filesystem': 'windows_c', 'free_bytes': free,
                     'minimum_bytes': windows_min, 'status': 'unavailable' if free is None else 'ok'})
    for row in rows:
        if row['free_bytes'] is not None and row['free_bytes'] < row['minimum_bytes']:
            raise StorageRefused(f"insufficient_disk_space: {row['filesystem']} free_bytes={row['free_bytes']} "
                                 f"required_bytes={row['minimum_bytes']}; Phase-1 untouched")
    return rows


def _children(parent: Path, home: Path) -> list[Path]:
    # Reject symlinks anywhere between the allowed root and the direct child.
    if any(p.is_symlink() for p in (parent, *parent.parents) if p != home and home in p.parents):
        return []
    if not parent.is_dir():
        return []
    return sorted((p for p in parent.iterdir() if p.is_dir() and not p.is_symlink()),
                  key=lambda p: (p.stat().st_mtime, p.name), reverse=True)


def _json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _allocated(path: Path) -> int:
    total = path.lstat().st_blocks * 512
    for directory, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            total += (Path(directory) / name).lstat().st_blocks * 512
    return total


def _remove_readonly(function, path, error):
    if not isinstance(error[1], PermissionError):
        raise error[1]
    target = Path(path)
    # Only directories need writable bits to unlink immutable runtime contents.
    target.parent.chmod(target.parent.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
    if target.is_dir() and not target.is_symlink():
        target.chmod(target.stat().st_mode | stat.S_IWUSR | stat.S_IXUSR)
    function(path)


def prune(home: Path, *, keep: int = 2, dry_run: bool = False,
          now: float | None = None, protect: tuple[Path, ...] = ()) -> list[dict]:
    """Caller holds phase2-cutover.lock. Only explicit directory families are eligible."""
    if keep < 1:
        raise StorageRefused('retention keep must be at least 1')
    home = home.resolve()
    share = home / '.local/share/moss-transcribe-diarize'
    state = home / '.local/state/moss-transcribe-diarize'
    now = time.time() if now is None else now
    pins = {p.resolve() for p in protect}
    active = share / 'account-current'
    if active.is_symlink():
        pins.add(active.resolve())
    attempts = _children(state / 'cutover-attempts', home)
    saved = set(attempts[:keep])
    unknown_candidate = False
    for attempt in attempts:
        # Unknown, interrupted and SAFE_STOPPED attempts contain recovery state.
        terminal = _json(attempt / 'result.json').get('terminal')
        if terminal not in {'restored', 'preadmission'} or attempt.resolve() in pins:
            saved.add(attempt)
        if attempt in saved:
            manifest = _json(attempt / 'candidate-manifest.json')
            if terminal not in {'restored', 'preadmission'} and not manifest.get('release'):
                unknown_candidate = True
            for key in ('release', 'qualification_checkout'):
                if isinstance(manifest.get(key), str):
                    pins.add(Path(manifest[key]).resolve())
    pins.update(p.resolve() for p in saved)
    runtimes = _children(share / 'account-runtimes', home)
    complete = [p for p in runtimes if not p.name.startswith('.')]
    pins.update(p.resolve() for p in complete[:keep])
    for p in complete:
        if p.resolve() in pins:
            pins.add((share / 'candidate-checkouts' / p.name).resolve())
    candidates = [('attempt', p) for p in attempts if p not in saved]
    if not unknown_candidate:
        candidates += [('runtime', p) for p in complete if p.resolve() not in pins]
        stale_roots = [share / 'candidate-checkouts', share / 'staging',
                       state / 'qualification-workspaces']
        for parent in stale_roots:
            candidates += [('stale_workspace', p) for p in _children(parent, home)
                           if now - p.stat().st_mtime > DAY]
        candidates += [('stale_runtime_stage', p) for p in runtimes
                       if p.name.startswith('.') and now - p.stat().st_mtime > DAY]
    rows = []
    for kind, path in candidates:
        resolved = path.resolve()
        if any(resolved == pin or resolved in pin.parents or pin in resolved.parents for pin in pins):
            continue
        size = _allocated(path)
        if not dry_run:
            shutil.rmtree(path, onerror=_remove_readonly)
        rows.append({'kind': kind, 'path': str(path.relative_to(home)),
                     'bytes': size, 'status': 'would_remove' if dry_run else 'removed'})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prune', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--keep', type=int, default=os.environ.get('MOSS_RETAIN_CANDIDATES', '2'))
    parser.add_argument('--protect', type=Path, action='append', default=[])
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--lock-fd', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.prune or args.dry_run:
            lock = args.home / '.local/state/moss-transcribe-diarize/phase2-cutover.lock'
            lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.dup(args.lock_fd) if args.lock_fd is not None else os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
            with os.fdopen(fd, 'r+'):
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise StorageRefused('cutover_or_staging_in_progress; pruning refused') from exc
                free_before = shutil.disk_usage(args.home).free
                rows = prune(args.home, keep=args.keep, dry_run=args.dry_run, protect=tuple(args.protect))
                for row in rows:
                    print(json.dumps(row), flush=True)
                print(json.dumps({'status': 'dry_run' if args.dry_run else 'pruned',
                                  'filesystem_free_bytes_delta': 0 if args.dry_run else shutil.disk_usage(args.home).free - free_before,
                                  'allocated_bytes_' + ('reclaimable' if args.dry_run else 'removed'): sum(r['bytes'] for r in rows)}))
        else:
            for row in check_space():
                print(json.dumps(row), flush=True)
    except (StorageRefused, OSError) as exc:
        print(str(exc) if isinstance(exc, StorageRefused) else type(exc).__name__)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
