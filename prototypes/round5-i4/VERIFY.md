# D34 fresh-process verification

Run from `/private/tmp/moss-round5-i4` with the prescribed interpreter. This
verification performs no decoder/provider dispatch; it only reads the recorded
loopback receipts and exercises focused offline/browser controls.

## 1. Custody and scope

```sh
test "$(git branch --show-current)" = round5/impl-row10
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -c 'import pathlib,moss_transcribe_diarize as m; p=pathlib.Path(m.__file__).resolve(); print(p); assert p.is_relative_to(pathlib.Path.cwd())'
git diff --check
```

## 2. D34 structure and controls

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python - <<'PY'
import ast
from pathlib import Path
from tests.e2e.verify_workspace import retained_metadata

source = Path('tests/e2e/verify_workspace.py').read_text()
tree = ast.parse(source)
constants = {node.targets[0].id: ast.unparse(node.value) for node in tree.body
             if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
assert constants['FIRST_ENROLLED_LABEL_BOUND_SECONDS'] == '2.5 + 1.5 + 0.5'
assert constants['ROW10_MAX_ATTEMPTS'] == '5'
methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)}
assert {'bank', 'bank_attempt', '_fresh_row10_context', '_row10_prior_durability'} <= methods
assert 'BEST_EFFORT_FAIL' in source
assert 'required=not (row==\'10\' and value[\'status\']==\'BEST_EFFORT_FAIL\')' in Path('tools/qualify/run.py').read_text()
assert retained_metadata({'timing_attribution': 'COMPLETE'}) == {'timing_attribution': 'COMPLETE'}
assert retained_metadata({'timing_attribution': 'INCOMPLETE'}) == {'timing_attribution': 'INCOMPLETE'}
print('D34 structure: PASS')
PY
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/phase2/test_voiceprint_latency_measurement.py \
  tools/qualify/test_bundle.py tests/test_qualification_verdict.py
```

## 3. Loopback receipt boundary

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python - <<'PY'
import json
from pathlib import Path

receipt = json.loads(Path('evidence/round5/i4/loopback-retry-4/result.json').read_text())
assert receipt['status'] == 'FALSIFIED'
assert receipt['decoder_requests_real'] == 0
assert receipt['row10']['attempt_count'] == 0
assert receipt['proxy']['accepted'] == receipt['proxy']['completed'] == 76
assert not any(receipt['listeners_after'].values())
print('loopback receipt: PARKED_CRITICAL (row-5 seed timeout before row 10)')
PY
```
