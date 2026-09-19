# Fresh verification attempt 2 — PASS

**Verdict:** PASS

**Custody:** branch `round3/publication`; final tested SHA `12b244e09b542926e1c44c857e63e11c32346605`; required base `a7a738cf9f9ff246f64c52c112e0bf597ba58241` is an ancestor. Initial tree was clean.

## 1. Clone and custody

```sh
git branch --show-current && git rev-parse HEAD && git merge-base --is-ancestor a7a738cf9f9ff246f64c52c112e0bf597ba58241 HEAD && git status --short
```

Exit 0. Output:

```text
round3/publication
12b244e09b542926e1c44c857e63e11c32346605
```

`git status --short` produced no output.

## 2. Python import custody

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c "import moss_transcribe_diarize as m; print(m.__file__)"
```

Exit 0. Output:

```text
/private/tmp/moss-round3-20260919/publication/moss_transcribe_diarize/__init__.py
```

The imported package was inside this clone.

## 3. Python tests

```sh
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
```

Exit 0. Exact result and timing:

```text
2055 passed, 5 skipped, 21 warnings, 37 subtests passed in 192.66s (0:03:12)
real 193.78
user 130.18
sys 56.11
```

Zero failures and zero errors.

## 4. Frontend tests

```sh
/usr/bin/time -p npm --prefix frontend test -- --run
```

Exit 0. Exact result and timing:

```text
Test Files  28 passed (28)
Tests  310 passed (310)
Start at  19:50:14
Duration  2.70s (transform 2.53s, setup 0ms, import 3.64s, tests 8.02s, environment 6.77s)
real 3.16
user 11.57
sys 4.79
```

## 5. Typecheck, build, diff, and generated assets

```sh
npm --prefix frontend run typecheck && npm --prefix frontend run build && git diff --check && git status --short
```

Exit 0. TypeScript `tsc --noEmit` passed. Vite transformed 34 modules and built in 71ms:

```text
../moss_transcribe_diarize/app/frontend_assets/styles.css   53.79 kB │ gzip: 10.79 kB
../moss_transcribe_diarize/app/frontend_assets/app.js      131.71 kB │ gzip: 42.91 kB │ map: 413.27 kB
✓ built in 71ms
```

`git diff --check` and `git status --short` produced no output: no generated-asset drift.

## 6. Invariant-line scan

```sh
git diff --unified=0 a7a738cf9f9ff246f64c52c112e0bf597ba58241..HEAD -- . ':(exclude)moss_transcribe_diarize/app/frontend_assets/**' ':(exclude)docs/verify/**' | rg '^[+-][^+-].*(QUALITY_BOUNDS|ALBUM_MIN_MATCH_SCORE|MARGIN|LIVE_MEETING_LIMIT|min_segment_samples|durable.admission|readiness|poll.*delay|Refresh sentinel|frame protocol)' || true
```

Exit 0. No output.

## Falsifier

None observed. No changed invariant line, wrong custody, dirty generated asset, test failure, typecheck failure, or build failure occurred.
