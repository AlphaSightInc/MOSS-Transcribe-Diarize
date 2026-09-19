# Fresh verification result — pane 3.4 — attempt 1

## Verdict: FAIL

Custody SHA: `599c4fd45d5a803a1ba9e45c8f886b26cd599ed4`

Branch: `round3/publication`

Base: `a7a738cf9f9ff246f64c52c112e0bf597ba58241` is an ancestor of the custody SHA.

The backend suite failed one test, and the invariant scan emitted one added line. No product, test, evidence, or `VERIFY.md` file was edited. No decoder, GPU, network, tunnel, push, merge, deploy, GitHub, or other pane was used.

## 1. Custody and clean tree — PASS

Literal command:

```sh
git branch --show-current && git rev-parse HEAD && git merge-base --is-ancestor a7a738cf9f9ff246f64c52c112e0bf597ba58241 HEAD && git status --short
```

Result: exit `0`.

```text
round3/publication
599c4fd45d5a803a1ba9e45c8f886b26cd599ed4
```

`git status --short` produced no output before verification.

## 2. Import custody — PASS

Literal command:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -c "import moss_transcribe_diarize as m; print(m.__file__)"
```

Result: exit `0`; import resolved inside this clone.

```text
/private/tmp/moss-round3-20260919/publication/moss_transcribe_diarize/__init__.py
```

## 3. Backend tests — FAIL

Literal command:

```sh
/usr/bin/time -p env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
```

Result: exit `1`.

Exact counts: `1 failed, 2054 passed, 5 skipped, 21 warnings, 37 subtests passed`.

Exact timings:

```text
pytest: 187.86s (0:03:07)
real 189.02
user 130.51
sys 53.71
```

Falsifier:

```text
FAILED tests/phase2/test_tls_preparation.py::test_verify_layout_current_tree
FAIL: VERIFY.md belongs under docs/verify/<wp>/
subprocess.CalledProcessError: Command '['bash', '/private/tmp/moss-round3-20260919/publication/scripts/check_verify_layout.sh']' returned non-zero exit status 1.
```

The expected `2055 passed, 5 skipped, 37 subtests` with zero failures/errors was not met.

## 4. Frontend tests — PASS

Literal command:

```sh
/usr/bin/time -p npm --prefix frontend test -- --run
```

Result: exit `0`.

Exact counts: `310 passed (310)` across `28 passed (28)` files.

Exact timings:

```text
Duration 2.72s (transform 2.38s, setup 0ms, import 3.71s, tests 8.05s, environment 6.07s)
real 3.22
user 11.65
sys 4.01
```

## 5. Typecheck, build, diff, and generated assets — PASS

Literal command:

```sh
npm --prefix frontend run typecheck && npm --prefix frontend run build && git diff --check && git status --short
```

Result: exit `0`.

- Typecheck passed.
- Build passed: `34 modules transformed`; `built in 64ms`.
- Output sizes: `styles.css 53.79 kB` (`gzip 10.79 kB`); `app.js 131.71 kB` (`gzip 42.91 kB`, map `413.27 kB`).
- `git diff --check` passed.
- `git status --short` produced no output; no generated-asset drift.

## 6. Settled-invariant scan — FAIL

Literal command:

```sh
git diff --unified=0 a7a738cf9f9ff246f64c52c112e0bf597ba58241..HEAD -- . ':(exclude)moss_transcribe_diarize/app/frontend_assets/**' | rg '^[+-][^+-].*(QUALITY_BOUNDS|ALBUM_MIN_MATCH_SCORE|MARGIN|LIVE_MEETING_LIMIT|min_segment_samples|durable.admission|readiness|poll.*delay|Refresh sentinel|frame protocol)' || true
```

Result: shell exit `0` because of `|| true`, but the required no-output condition failed.

Exact output/falsifier:

```text
+6. `git diff --unified=0 a7a738cf9f9ff246f64c52c112e0bf597ba58241..HEAD -- . ':(exclude)moss_transcribe_diarize/app/frontend_assets/**' | rg '^[+-][^+-].*(QUALITY_BOUNDS|ALBUM_MIN_MATCH_SCORE|MARGIN|LIVE_MEETING_LIMIT|min_segment_samples|durable.admission|readiness|poll.*delay|Refresh sentinel|frame protocol)' || true`
```

The match is the added command line in root-level `VERIFY.md`; it includes the searched invariant terms. This independently violates the prescribed expectation of no output and is consistent with the backend layout falsifier.

## Final custody

Final SHA: `599c4fd45d5a803a1ba9e45c8f886b26cd599ed4` (unchanged).

Only `VERIFY-RESULT.md` was created by this verification.
