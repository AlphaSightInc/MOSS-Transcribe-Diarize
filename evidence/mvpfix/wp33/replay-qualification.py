"""Compare actual baseline/current bundle cleanup and harness exit expression; no GPU."""
import ast
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from tools.qualify.run import Bundle
from tests.e2e.verify_workspace import required_rows_verdict, verdict_exit_code

root = Path.cwd()
source = subprocess.check_output(['git', 'show', '0e97c71b:tools/qualify/run.py'], text=True)
old = {'__file__': str(root/'tools/qualify/run.py'), '__name__': 'wp33_baseline'}
exec(compile(source, old['__file__'], 'exec'), old)
rows = {str(i): {'status': 'SKIP' if i == 9 else 'PASS'} for i in range(1, 15)}
old_harness = subprocess.check_output(['git', 'show', '0e97c71b:tests/e2e/verify_workspace.py'], text=True)
expression = next(node.value for node in ast.walk(ast.parse(old_harness))
                  if isinstance(node, ast.Return) and isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Name) and node.value.func.id == 'int')
before_exit = eval(compile(ast.Expression(expression), '<baseline exit>', 'eval'),
                   {'self': SimpleNamespace(state={'rows': rows})})
for label, cls in [('before', old['Bundle']), ('after', Bundle)]:
    b = object.__new__(cls)
    b.processes, b.handles, b.proxy, b.monitor = [], [], None, None
    b.monitor_stop = SimpleNamespace(set=lambda: None)
    b.args = SimpleNamespace(budget=1, compare=None)
    b.out = root/'evidence/mvpfix/wp33'
    b.data = {'gates': [{'name': 'workspace_row_'+n, **row} for n, row in rows.items()]}
    b.gate = lambda name, status, **kw: b.data['gates'].append({'name': name, 'status': status})
    b.flush = lambda: None
    b.cleanup()
    print(json.dumps(dict(step=label, passed=13, skipped=1, expected=14,
        harness_exit=before_exit if label == 'before' else verdict_exit_code(required_rows_verdict(rows)),
        qualified=b.data['qualified'], verdict=b.data.get('verdict'))))
    assert b.data['qualified'] is (label == 'before')
assert before_exit == 0
assert verdict_exit_code(required_rows_verdict(rows)) == 2
