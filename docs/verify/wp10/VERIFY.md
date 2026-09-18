# VERIFY — WP10, relocating the all-zero span guard

Verify that digital silence is decided at dispatch and that no decoder-seam contract depends
on it. Everything below is offline: no decoder, no tunnel, no network, no shared service.

## Setup

```
WT=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp10-zero-guard-seams
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
cd "$WT"
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
```

`frontend/node_modules` must be a symlink to the dev tree's (`tests/phase2` shells out to
node). Create it if missing:
`ln -s /Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize/frontend/node_modules frontend/node_modules`

## 1 — the package under test is this worktree

```
$PY -c "import moss_transcribe_diarize as m; print(m.__file__)"
```
**Expect** a path under `…-wt-wp10-zero-guard-seams/`. Anything else invalidates every result
below.

## 2 — the nineteen decoder-seam contracts WP3 broke

```
$PY -m pytest -q -p no:cacheprovider \
  tests/test_live_pipeline_seams.py tests/phase2/test_draft_lane.py \
  tests/phase2/test_runner_composition.py tests/test_live_rolling_wiring.py \
  tests/test_live_service_replay.py
```
**Expect** `147 passed` (plus 9 subtests), 0 failed. On `integration/mvp-fix-20260917` the
same command gives `19 failed, 128 passed`.

## 3 — WP3's guard contracts, at their relocated seam

```
$PY -m pytest -q -p no:cacheprovider \
  tests/test_live_capture_guard.py tests/test_live_terminal_finalizer.py
```
**Expect** `40 passed` (plus 19 subtests), 0 failed.

## 4 — the WP10 guarantees

```
$PY -m pytest -q -p no:cacheprovider tests/test_live_zero_span_dispatch.py
```
**Expect** `9 passed`. These are the load-bearing ones: an all-zero span makes no model
request and no identity birth while its audio stays accounted for; every deployed lane is
built through the guarded dispatch; the terminal surface still reaches `final`; a meeting that
never held a nonzero sample is refused by name rather than decoded.

## 5 — the requirements falsifier (real runtime, real tape)

```
$PY prototypes/zero-guard-seams/falsify.py
```
**Expect** `verdict 7/7 requirements met` and exit status 0. It drives the real
`LiveServiceRuntime`, `LiveCoordinator` and `CompleteMixedTape` with a runner that raises if
it is ever asked to decode.

## 6 — full Python suite

```
$PY -m pytest -q -p no:cacheprovider tests
```
**Expect** `1792 passed, 2 skipped` (37 subtests), **0 failed**. Zero tolerated failures on
this branch: WP4's latency fixture fix is already merged here.

## 7 — frontend

```
npm --prefix frontend test -- --run
npm --prefix frontend run typecheck
git status --short
```
**Expect** `26 passed (26)` / `230 passed (230)`, a clean typecheck, and a clean working tree.
(The frontend suite rewrites `evidence/mvpfix/wp2/production-*.png`; if `git status` shows
them modified, `git checkout -- evidence/mvpfix/wp2/` — they belong to another WP and this
branch must not change them.) No frontend source changed in WP10, so
`moss_transcribe_diarize/app/frontend_assets/*` must be untouched.

## What would falsify this work

* Any failure in steps 2–4, or fewer than 7/7 in step 5.
* A model request reaching a runner for exact digital zeros on any lane — canonical, rolling
  witness, draft or terminal. `falsify.py`'s `MustNotDecode` records and raises on one.
* An identity preparation offered evidence from an all-zero span (a speaker born from silence).
* A span of zeros that stalls the timeline instead of committing empty and named
  (`empty_reason == "span_was_digital_silence"`, `committed_samples` advancing).
* Quiet speech — one nonzero least-significant bit among zeros — failing to reach the decoder.
* A deployed lane constructed with `RunnerBoundedWavInference` directly rather than through
  `live_provider_bundle.bounded_live_inference`.
