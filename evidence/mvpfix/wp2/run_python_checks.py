"""Run authorized suites; confine scratch/socket files to this long worktree.
Relative Unix socket paths avoid macOS's 104-byte address limit without changing tests.
"""
import os
from pathlib import Path
import tempfile
import time
import pytest

ROOT = Path(__file__).resolve().parents[3]
os.chdir(ROOT)
SCRATCH = ROOT/'evidence/mvpfix/wp2/tmp'
SCRATCH.mkdir(exist_ok=True)
os.environ['TMPDIR'] = str(SCRATCH)
tempfile.tempdir = str(SCRATCH)

class LocalSockets:
    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_setup(self, item):
        if item.module.__name__.endswith('test_workspace_lifecycle'):
            item.module.control_socket_path = lambda: Path('evidence/mvpfix/wp2/tmp')/f'control-{time.time_ns()}.sock'
        if item.name == 'test_operator_revocation_uses_workspace_id_without_content_or_credentials':
            self.original = tempfile.TemporaryDirectory.__enter__
            original = self.original
            tempfile.TemporaryDirectory.__enter__ = lambda obj: os.path.relpath(original(obj), ROOT)

    def pytest_runtest_teardown(self, item):
        if hasattr(self, 'original'):
            tempfile.TemporaryDirectory.__enter__ = self.original
            del self.original

suites = ['lane_consumer_store', 'workspace_lifecycle', 'browser_workspace', 'shared_meeting_history',
          'manual_speaker_voiceprints', 'voiceprint_bank_operations', 'legacy_model_exports',
          'workspace_demo_geometry', 'acceptance_locator_sentinels', 'lane_consumer_geometry']
raise SystemExit(pytest.main(['-q','-p','no:cacheprovider','--basetemp='+str(SCRATCH/'verified')]+
    ['tests/phase2/test_'+s+'.py' for s in suites], plugins=[LocalSockets()]))
