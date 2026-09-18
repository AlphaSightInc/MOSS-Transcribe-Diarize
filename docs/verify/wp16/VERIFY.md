# WP16 — fresh-context verification

First cd `/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-wp16-file-url-long`.
This is the verification after user-requested `/new` in MOSS:3.4. Do not repeat `/new`.
Read AGENTS.md, `evidence/mvpfix/wp16/NOTES.md`, `COMMANDS.md`, and prototype NOTES.
Modify nothing outside this worktree. No push/merge/rebase/deploy/GitHub, messages to peers,
GPU requests, tunnels or shared services. All measurement services should already be stopped.
Use only this document and committed evidence; no prior conversation is needed.

Run literally, from this worktree (do not stop on a failing command; record every result):
```sh
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.
export TMPDIR="$PWD/.wp16runtime/tmp"
export XDG_CACHE_HOME="$PWD/.wp16runtime/cache"
export NUMBA_CACHE_DIR="$PWD/.wp16runtime/numba"
export npm_config_cache="$PWD/.wp16runtime/npm-cache"
PY=/Users/gao/Desktop/AI_Projects/Github_Projects/MOSS-Transcribe-Diarize-wt-auto-mvp-0911/.venv/bin/python
git status --short --branch
git rev-parse HEAD
"$PY" -c 'import moss_transcribe_diarize as m; from pathlib import Path; print(m.__file__); assert Path(m.__file__).resolve().is_relative_to(Path.cwd())'
"$PY" -m pytest -q -p no:cacheprovider -p evidence.mvpfix.wp16.local_scratch --basetemp=.wp16runtime/pytest-fresh tests > .wp16runtime/fresh-python.log 2>&1
npm --prefix frontend test -- --run --configLoader native > .wp16runtime/fresh-frontend.log 2>&1
npm --prefix frontend run typecheck > .wp16runtime/fresh-typecheck.log 2>&1
npm --prefix frontend run build -- --configLoader native > .wp16runtime/fresh-build.log 2>&1
"$PY" prototypes/streaming-diarization/wp16-file-url-long/verify_evidence.py > .wp16runtime/fresh-evidence.log 2>&1
bash scripts/check_verify_layout.sh
git diff --exit-code -- moss_transcribe_diarize/app/frontend_assets
git diff --check
lsof -nP -iTCP:17876 -iTCP:17877 -iTCP:17878 -iTCP:18116 -sTCP:LISTEN
```
Expected: branch `mvpfix/wp16-file-url-long`; clean tracked/untracked initial state;
Python **1870 passed, 2 skipped, 37 subtests**, no failures (21 existing deprecation warnings).
Frontend **244 passed / 27 files**; typecheck/build success and built assets unchanged.
Evidence verifier: 16 latest cases, 5 typed failures, 50/50 exports, 5 long cases,
fixed digital silence and actual huge-file capacity refusal; 50 retained browser downloads
independently compared again with saved API snapshots. Decoder total <=200 in summary.
Ports have no listeners (lsof exit 1 with no output is the expected stopped state).
Any mismatch is a failure to report/diagnose, not a waived pre-existing exception.

Inspect `git diff 5179368e --stat` and product diff. Changes should be only file dispatch
silence, shared existing capacity check + metadata preflight endpoint/UI, associated tests,
shipped assets, scoped evidence/bench/docs, and own scratch ignore. No shared decoder,
windowing, identity, thresholds, QUALITY_BOUNDS, readiness, frame keys or lifecycle changes.
Read `test-summary.json`: initial test-author errors and the two-failure deliberate mutation
are not product passes. Existing MP3 assertions remain unchanged; only PCM input changed.
Read `summary.json` and `word-scores.json` for final counts/timings/RSS and exact edit counts.
Retain limitations: 31 identities versus 3 reference voices; repeated corpus is not natural
30-minute diversity; 60%-byte truncated MP3 completes a 7.167 s prefix without a notice.
This is local browser evidence, not deployment, attended capture or general quality acceptance.

Write `docs/verify/wp16/VERIFY-RESULT.md`: fresh context, tested SHA, exact per-gate counts,
PASS/FAIL, evidence findings, scope/limitations and deviations. Commit that result and a
compact `evidence/mvpfix/wp16/fresh-summary.json` (not raw logs) locally. Recheck clean status;
report <=60 lines in this pane with branch/final SHA, prototype verdict, changes, exact
counts, measured cases, decoder usage, remaining limitations and deviations. No permission
question. No report before the fresh checks finish.

Preparation used memory only as a caution to distinguish local evidence from deployment;
live facts above are freshly measured. If citing that use in the final report, append:
<oai-mem-citation>
<citation_entries>
MEMORY.md:5545-5548|note=[local evidence and deployment remain distinct]
</citation_entries>
<rollout_ids>
01a0a346-ad32-7180-aaa1-7f57555f2ad9
</rollout_ids>
</oai-mem-citation>
