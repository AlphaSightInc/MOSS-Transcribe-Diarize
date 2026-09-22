# I4b fresh-context verification

Run from a clean process in this clone with the prescribed interpreter:

```sh
test "$(git branch --show-current)" = round5/impl-row10b
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python - <<'PY'
import ast
from pathlib import Path

source = Path('tests/e2e/verify_workspace.py').read_text()
method = next(node for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.AsyncFunctionDef) and node.name == '_fresh_row10_context')
calls = [ast.unparse(node.value.value.func) for node in method.body if isinstance(node, ast.Expr)
         and isinstance(node.value, ast.Await) and isinstance(node.value.value, ast.Call)]
assert 'self.open' in calls
print('fresh-context workspace reopen: PASS')
PY
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/phase2/test_voiceprint_latency_measurement.py \
  tools/qualify/test_bundle.py tests/test_qualification_verdict.py
git diff --check
```

The separate lead-shaped loopback receipt is outside the clone:
`/private/tmp/moss-i4b-focused-green/summary.json`. It establishes browser
control flow only, not real decoder quality or latency.
