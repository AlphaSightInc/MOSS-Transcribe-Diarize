# Fresh verification result — PANE 3.3

**Verdict: PASS**

- Worktree: `/private/tmp/moss-round3-20260919/runner`
- Branch: `round3/runner`
- Initial SHA: `e802889d59687064b9c225b5079e51425713a5b8`
- Final SHA: `e802889d59687064b9c225b5079e51425713a5b8`
- Initial worktree status: clean; `git status --short` produced no output.
- Final verification-gate worktree status: clean; `git diff --exit-code && git status --short` exited 0 and produced no output.
- Production/tests edited: no.

## Commands and exact results

### 1. Initial branch and status

```sh
git branch --show-current && git status --short
```

Exit: `0`

```text
round3/runner
```

The status portion produced no output.

Initial SHA capture:

```sh
git rev-parse HEAD
```

Exit: `0`; result: `e802889d59687064b9c225b5079e51425713a5b8`.

### 2. Durable batch owner prototype

```sh
prototypes/durable-batch-owner-p2/run.sh
```

Exit: `0`; verdict: `SUPPORTED`.

- File arm: 40 committed before restart; decoder windows 40–100 inclusive; 61 new decoder calls; 101 reopened segments; 101 unique reopened segments; completed; retained local source; 0 remote URL fetches on resume; published version 1; second publication refused; terminal artifacts absent.
- URL arm: 40 committed before restart; decoder windows 40–100 inclusive; 61 new decoder calls; 101 reopened segments; 101 unique reopened segments; completed; retained local source; 0 remote URL fetches on resume; published version 1; second publication refused; terminal artifacts absent.
- Violating controls: `wrong_account`, `wrong_meeting`, `wrong_source`, `changed_inference`, and `broken_prefix` all refused; each recorded 0 decoder calls and 0 publication calls.
- Cancellation arm: status `interrupted`; order was `resume_cancelled_before_later_dispatch`, `durable_terminal_transition`, `artifacts_removed`; 1 decoder call at window 40; 0 publication calls; terminal artifacts absent.
- SQLite runtime: `3.50.4`; semantic-store allowance: `true`.

### 3. Backend suite

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python -m pytest -q -p no:cacheprovider tests
```

Exit: `0`.

```text
2052 passed, 5 skipped, 21 warnings, 37 subtests passed in 179.72s (0:02:59)
```

The run also emitted Playwright asynchronous-cleanup diagnostics after progress reached 100%: `Task was destroyed but it is pending!` and a retrieved `TargetClosedError`. They did not change the exit code or expected test counts. Warning summary: 1 Starlette deprecation warning, 17 `tarfile.extractall` deprecation warnings, and 3 deprecated Python audio-module warnings (`aifc`, `audioop`, `sunau`).

### 4. Frontend suite

```sh
npm --prefix frontend test -- --run
```

Exit: `0`.

```text
Test Files  28 passed (28)
Tests  288 passed (288)
Duration  2.58s
```

The run emitted Node warnings that `--localstorage-file` was provided without a valid path. There were 0 failed test files and 0 failed tests.

### 5. Frontend typecheck

```sh
npm --prefix frontend run typecheck
```

Exit: `0`; `tsc --noEmit` produced no diagnostics.

### 6. Frontend build

```sh
npm --prefix frontend run build
```

Exit: `0`; Vite `8.2.1` built successfully in `59ms`, transforming 34 modules.

```text
styles.css   53.79 kB | gzip: 10.79 kB
app.js      131.29 kB | gzip: 42.81 kB | map: 411.24 kB
```

### 7. Final byte-for-byte and status gate

```sh
git diff --exit-code && git status --short
```

Exit: `0`; no output. The prototype and build reproduced tracked outputs byte-for-byte, and the worktree remained clean at the verification gate.

Final SHA capture:

```sh
git rev-parse HEAD
```

Exit: `0`; result: `e802889d59687064b9c225b5079e51425713a5b8`.

## Falsifier assessment

None reached: no nonzero exit, count mismatch, pre-report dirty output, prototype rejection, violating-control decode/publication, replay outside windows 40–100, duplicate or missing segment, second publication, URL refetch, cancellation-order change, or retained terminal artifact.
