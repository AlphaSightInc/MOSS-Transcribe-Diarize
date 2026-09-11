"""Missing binary detection never converts a launch/product failure into a skip."""
from pathlib import Path
from types import SimpleNamespace
import pytest
from tests.phase2 import browser_support as support


def test_missing_executable_skips_with_checked_path(monkeypatch):
    monkeypatch.setattr(Path, 'is_file', lambda self: False)
    monkeypatch.setattr(support.shutil, 'which', lambda name: None)
    p = SimpleNamespace(chromium=SimpleNamespace(executable_path='/missing/chrome-headless-shell'))
    with pytest.raises(pytest.skip.Exception, match='Missing supported Chrome/Chromium executable; checked:') as skip:
        support.require_browser(p)
    assert '/missing/chrome-headless-shell' in str(skip.value)


def test_installed_bundled_executable_is_used(monkeypatch, tmp_path):
    binary = tmp_path/'chrome'
    binary.write_text('#!/bin/sh\nexit 9\n'); binary.chmod(0o755)
    actual = Path.is_file
    monkeypatch.setattr(Path, 'is_file', lambda self: self == binary and actual(self))
    monkeypatch.setattr(support.shutil, 'which', lambda name: None)
    p = SimpleNamespace(chromium=SimpleNamespace(executable_path=str(binary)))
    assert support.require_browser(p) == binary  # launch failure is not caught by this guard
