"""Acceptance Stop uses the product browser's drain duration, never an omitted body."""
import ast
import asyncio
from pathlib import Path

from moss_transcribe_diarize import phase2_acceptance_replay as replay


def test_acceptance_replay_stop_payload_has_positive_browser_deadline(monkeypatch):
    calls = []
    adapter = object.__new__(replay.AccountCookieLiveReplayService)
    adapter._json = lambda *args: calls.append(args) or {'snapshot': {}}
    adapter._forget = lambda session_id: None
    monkeypatch.setattr(replay, '_snapshot_from_dict', lambda value: value)
    asyncio.run(adapter.stop('probe', replay.ACCEPTANCE_STOP_DEADLINE_SECONDS))
    assert calls == [('POST', '/api/live/sessions/probe/stop', {'deadline': 5.0})]
    browser = Path('frontend/src/components/ControlPanel.tsx').read_text()
    assert 'await client.stop(5)' in browser


def test_every_direct_acceptance_stop_has_explicit_browser_deadline():
    seen = 0
    for path in Path('moss_transcribe_diarize').glob('phase2_acceptance_*.py'):
        for call in ast.walk(ast.parse(path.read_text())):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            if call.func.attr not in ('request', 'json'):
                continue
            routes = [arg for arg in call.args if isinstance(arg, ast.JoinedStr)
                      and any(isinstance(v, ast.Constant) and str(v.value).endswith('/stop') for v in arg.values)]
            if not routes:
                continue
            payload = next((kw.value for kw in call.keywords if kw.arg == 'json'), None)
            assert isinstance(payload, ast.Dict), path
            deadline = next((value for key, value in zip(payload.keys, payload.values)
                             if isinstance(key, ast.Constant) and key.value == 'deadline'), None)
            assert isinstance(deadline, ast.Name), path
            assert deadline.id == 'ACCEPTANCE_STOP_DEADLINE_SECONDS', path
            seen += 1
    assert seen == 3
    assert replay.ACCEPTANCE_STOP_DEADLINE_SECONDS > 0


def test_capacity_stop_uses_duration_not_monotonic_timestamp():
    tree = ast.parse(Path('moss_transcribe_diarize/phase2_acceptance_external.py').read_text())
    stops = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == 'stop']
    assert len(stops) == 1
    assert isinstance(stops[0].args[1], ast.Name)
    assert stops[0].args[1].id == 'ACCEPTANCE_STOP_DEADLINE_SECONDS'
