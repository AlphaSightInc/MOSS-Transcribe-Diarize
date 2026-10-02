"""Process-local R4 candidate on the existing real routes; no product file writes."""
import ast
import runpy
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from moss_transcribe_diarize.app import live_transport, phase2_live

baseline = subprocess.check_output(['git', 'show',
    'a6117c0a:moss_transcribe_diarize/app/live_transport.py'], text=True)
route = next(node for node in ast.parse(baseline).body
             if isinstance(node, ast.FunctionDef) and node.name == 'attach_live_routes')
source = '\n'.join(baseline.splitlines()[route.lineno - 1:route.end_lineno])
old = '''            interruption = {"start_sample": mixer.mixed_sample_at(last_end, mixed_samples, origin_ns=cursor),
                            "end_sample": None}'''
new = '''            interruption = None
            if mixed_samples or any(lane["next_sequence"] for lane in lanes.values()):
                interruption = {"start_sample": mixer.mixed_sample_at(last_end, mixed_samples, origin_ns=cursor),
                                "end_sample": None}'''
source = source.replace(old, new)
assert new in source
source = source.replace('writer.interruption_index = await adapter.record_interruption(authority, interruption)',
    'writer.interruption_index = (None if interruption is None else\n                await adapter.record_interruption(authority, interruption))')
source = source.replace('"interruption": dict(interruption),',
    '"interruption": None if interruption is None else dict(interruption),')
if '--origin-probe' in sys.argv:
    # Measurement only: pin the existing unmixed prefix before a resumed peer arrives.
    source = source.replace('            writer.instance_id = instance',
        '            if interruption is not None and mixer.capture_cursor_ns is None:\n'
        '                mixer._cursor_ns = cursor\n'
        '            writer.instance_id = instance')
namespace = dict(vars(live_transport))
exec(compile(source, '<throwaway-R4-route>', 'exec'), namespace)
phase2_live.attach_live_routes = namespace['attach_live_routes']
runpy.run_path('/Users/gao/Documents/Codex/2026-09-28/moss-gemini/evidence/P74/review1/standards_no_prefix_both.py', run_name='__main__')
import pytest
raise SystemExit(pytest.main(['-q', '-p', 'no:cacheprovider',
    'tests/phase2/test_live_resume.py', '-k',
    'late_start or one_accepted_lane or without_new_audio or early_resume']))
