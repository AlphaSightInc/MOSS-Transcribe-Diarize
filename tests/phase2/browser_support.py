"""One executable guard for real browser tests and standalone verification probes.

Only missing executables are skippable. A present browser that fails to launch, or
an assertion that fails after launch, remains a failure.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil


class BrowserExecutableMissing(RuntimeError):
    pass


def browser_executable(playwright=None) -> Path:
    candidates = [
        Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
        Path('/usr/bin/google-chrome'), Path('/usr/bin/chromium'),
        Path('/usr/bin/chromium-browser'),
    ]
    for name in ('google-chrome', 'chromium', 'chromium-browser'):
        if found := shutil.which(name):
            candidates.append(Path(found))
    if playwright is not None:
        bundled = Path(playwright.chromium.executable_path)
        candidates.append(bundled)
        # Playwright may install only its headless shell, without full Chromium.
        for root in bundled.parents:
            if root.name in ('ms-playwright', '.local-browsers') or root == Path(os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '/nonexistent')):
                for pattern in ('chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell',
                                'chromium_headless_shell-*/chrome-*/headless_shell'):
                    candidates.extend(sorted(root.glob(pattern)))
                break
    for candidate in dict.fromkeys(candidates):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise BrowserExecutableMissing('Missing supported Chrome/Chromium executable; checked: ' + ', '.join(map(str, dict.fromkeys(candidates))))


def require_browser(playwright=None) -> Path:
    """Pytest convention: explicit skip only for a missing supported executable."""
    import pytest
    try:
        return browser_executable(playwright)
    except BrowserExecutableMissing as exc:
        pytest.skip(str(exc))
