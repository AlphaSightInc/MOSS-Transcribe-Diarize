# Retained-resume fix verification

Run from `/private/tmp/moss-round4-20260920/fix-i3i4` on
`round4/fix-i3i4`. These checks make zero decoder, provider, network, or tunnel
calls.

## 1. Checkout and import

```sh
test "$(pwd)" = /private/tmp/moss-round4-20260920/fix-i3i4
test "$(git branch --show-current)" = round4/fix-i3i4
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -c 'import pathlib,moss_transcribe_diarize as m; p=pathlib.Path(m.__file__).resolve(); print(p); assert p.is_relative_to(pathlib.Path.cwd())'
```

## 2. Retained-resume controls

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/phase2/test_fix_i3i4_diagnosis.py \
  tests/phase2/test_fix_i3i4_review_controls.py \
  tests/phase2/test_fix_i3i4_resume_binding_controls.py
```

Expected: `22 passed`. This includes unbound single- and multi-window restart,
digital-silence suppression, mix- and input-bound resume, exponential retry,
single resolver hashing, truthful registration failure, audio reconciliation,
same-boot reclaim, per-owner isolation, bound-4 validation, interrupt, and revoke.

## 3. Full gates

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. MOSS_TEST_REAL_SQLITE=1 \
  /private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
```

## 4. Protected seam and scope

```sh
/private/tmp/moss-round4-20260920/runtime-prefix/venv/bin/python - <<'PY'
import ast
import pathlib
import subprocess

path = "moss_transcribe_diarize/app/phase2.py"
before = subprocess.check_output(["git", "show", f"0de56e1a:{path}"], text=True)
after = pathlib.Path(path).read_text(encoding="utf-8")

def target(source):
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_assert_no_active_meetings":
            return ast.dump(node, include_attributes=False)
    raise AssertionError("_assert_no_active_meetings missing")

assert target(before) == target(after)
print("_assert_no_active_meetings AST: identical")
PY
git diff --check 85aec978..HEAD
git diff --stat 85aec978 -- moss_transcribe_diarize tools prototypes
test -z "$(git grep -nE 'sk-or-v1-[A-Za-z0-9]{16,}|OPENROUTER_API_KEY=[A-Za-z0-9]' -- moss_transcribe_diarize tests || true)"
```

Expected product diff: only `phase2.py`, `phase2_file.py`, and
`windowed_transcription.py`; protected assertion AST identical; secret scan empty.
