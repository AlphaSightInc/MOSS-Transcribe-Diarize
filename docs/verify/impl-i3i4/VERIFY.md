# I3/I4 fresh verification

Run from `/private/tmp/moss-round4-20260920/impl-i3i4` on
`round4/impl-i3i4`. These commands make zero decoder/provider requests and open no
tunnel or network connection.

## 1. Checkout, import, scope, and secret custody

```sh
test "$(pwd)" = /private/tmp/moss-round4-20260920/impl-i3i4
test "$(git branch --show-current)" = round4/impl-i3i4
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  -c 'import pathlib,moss_transcribe_diarize as m; p=pathlib.Path(m.__file__).resolve(); print(p); assert p.is_relative_to(pathlib.Path.cwd())'
test -z "$(git grep -n 'sk-or-\|OPENROUTER_API_KEY=' -- moss_transcribe_diarize tools prototypes tests docs/verify/impl-i3i4 || true)"
git diff --stat 0de56e1a -- moss_transcribe_diarize tools prototypes
```

## 2. Owned-seam invariants

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python - <<'PY'
import ast
import pathlib
import subprocess

base = "2fa9dfda"
checks = {
    "moss_transcribe_diarize/app/phase2.py": ["_assert_no_active_meetings"],
    "moss_transcribe_diarize/app/phase2_file.py": [
        "accept", "accept_url", "_retain_new_directory", "reclaim_refused_retained_work",
        "reclaim_terminal_retained_work", "_checkpoint_is_valid",
    ],
}

def functions(source):
    tree = ast.parse(source)
    return {
        node.name: ast.get_source_segment(source, node)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

for path, names in checks.items():
    before = subprocess.check_output(["git", "show", f"{base}:{path}"], text=True)
    after = pathlib.Path(path).read_text(encoding="utf-8")
    before_functions = functions(before)
    after_functions = functions(after)
    for name in names:
        assert before_functions[name] == after_functions[name], (path, name)
print("owned-seam invariants: PASS")
PY
```

## 3. Strict controls and focused lifecycle/accounting controls

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  -m pytest -q -p no:cacheprovider \
  tests/phase2/test_p_f4f3b_violating_controls.py \
  tests/phase2/test_retained_file_claim.py \
  tests/phase2/test_batch_startup_prototype_controls.py \
  tools/qualify/test_bundle.py
```

## 4. Readiness matrix and summary-only plan receipt

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  docs/verify/impl-i3i4/readiness_probe.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  prototypes/feature-rows/run.py --plan-only \
  --out docs/verify/impl-i3i4/summary-plan.json
```

## 5. Full backend suite

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. \
  /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python \
  -m pytest -q -p no:cacheprovider tests
```

## 6. Full frontend suite, typecheck, build, and asset parity

```sh
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
npm --prefix frontend run build -- --configLoader native
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
```
